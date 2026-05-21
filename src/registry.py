"""Dynamic user registry — replaces the static TELEGRAM_CHAT_IDS allowlist.

Hosted SaaS: a stranger can ``/start`` the bot and register themselves.
The registry is the single source of truth for "who may use the bot" and
the set the scheduler iterates. The env var ``TELEGRAM_CHAT_IDS`` now only
seeds *admin* accounts at startup.

One shared file at ``data/users/registry.json`` — small (one record per
user) and written only on registration / role / block changes. Atomic
write uses the same thread-lock + ``.tmp`` + ``os.replace`` pattern as
:mod:`src.pending` and :mod:`src.profile`.

Registry record shape::

    {"role": "admin"|"user", "registered_at": iso8601,
     "label": str, "blocked": bool}
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

from src.config import registry_file

logger = logging.getLogger(__name__)

_REGISTRY_VERSION = 1

# Single in-memory copy of the whole registry. Loaded once at startup,
# mutated in place on registration. Guarded by _registry_lock.
_registry_cache: dict[str, Any] | None = None
_registry_lock = threading.Lock()


def _empty_registry() -> dict[str, Any]:
    return {"version": _REGISTRY_VERSION, "users": {}}


def _load_from_disk() -> dict[str, Any]:
    path = registry_file()
    if not path.exists():
        return _empty_registry()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Failed to read %s: %s — starting empty.", path, exc)
        return _empty_registry()
    if not isinstance(data, dict) or not isinstance(data.get("users"), dict):
        return _empty_registry()
    data.setdefault("version", _REGISTRY_VERSION)
    return data


def _flush() -> None:
    """Atomically write the cache to disk. Caller must hold _registry_lock."""
    path = registry_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(_registry_cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _ensure_cache() -> dict[str, Any]:
    """Return the registry cache, loading from disk if needed.

    Caller must hold :data:`_registry_lock`.
    """
    global _registry_cache
    if _registry_cache is None:
        _registry_cache = _load_from_disk()
    return _registry_cache


def init_registry() -> None:
    """Load registry.json into memory. Call once at startup."""
    global _registry_cache
    with _registry_lock:
        _registry_cache = _load_from_disk()


# ── Public API ─────────────────────────────────────────────────────────────


def all_user_ids() -> list[int]:
    """Every registered, non-blocked chat_id. Replaces TELEGRAM_CHAT_IDS.

    Re-read on every call so newly self-registered users are picked up by
    the next scheduler cycle without a restart.
    """
    with _registry_lock:
        users = _ensure_cache()["users"]
        return [int(cid) for cid, rec in users.items() if not rec.get("blocked", False)]


def is_registered(chat_id: int) -> bool:
    with _registry_lock:
        return str(chat_id) in _ensure_cache()["users"]


def is_admin(chat_id: int) -> bool:
    with _registry_lock:
        rec = _ensure_cache()["users"].get(str(chat_id))
        return bool(rec) and rec.get("role") == "admin"


def is_blocked(chat_id: int) -> bool:
    with _registry_lock:
        rec = _ensure_cache()["users"].get(str(chat_id))
        return bool(rec) and bool(rec.get("blocked", False))


def get_user(chat_id: int) -> dict[str, Any] | None:
    """Return a copy of the registry record for ``chat_id``, or None."""
    with _registry_lock:
        rec = _ensure_cache()["users"].get(str(chat_id))
        return dict(rec) if rec else None


def register_user(chat_id: int, *, label: str = "", role: str = "user") -> bool:
    """Register ``chat_id``. Idempotent. Returns True if newly created.

    For an already-registered user this never downgrades an admin to a
    user; it only upgrades to admin and backfills a missing label.
    """
    if chat_id <= 0:
        return False
    with _registry_lock:
        users = _ensure_cache()["users"]
        key = str(chat_id)
        existing = users.get(key)
        if existing is not None:
            changed = False
            if role == "admin" and existing.get("role") != "admin":
                existing["role"] = "admin"
                changed = True
            if label and not existing.get("label"):
                existing["label"] = label
                changed = True
            if changed:
                _flush()
            return False
        users[key] = {
            "role": role,
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "label": label,
            "blocked": False,
        }
        _flush()
    logger.info("Registered new user chat_id=%s role=%s", chat_id, role)
    return True


def set_blocked(chat_id: int, blocked: bool) -> None:
    """Block/unblock a user — the SaaS kill-switch for abuse."""
    with _registry_lock:
        rec = _ensure_cache()["users"].get(str(chat_id))
        if rec is None:
            return
        rec["blocked"] = bool(blocked)
        _flush()
    logger.info("Set blocked=%s for chat_id=%s", blocked, chat_id)


def seed_admins(admin_ids: Iterable[int], labels: dict[int, str] | None = None) -> int:
    """Register env-provided admin ids at startup. Returns count newly created."""
    labels = labels or {}
    created = 0
    for cid in admin_ids:
        if register_user(cid, label=labels.get(cid, ""), role="admin"):
            created += 1
    return created
