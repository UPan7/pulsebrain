"""Subscription billing — plan catalog, per-user subscription state,
usage metering, and quota enforcement.

Hosted-SaaS model: PulseBrain pays the LLM + proxy costs, so every user
has a plan (trial / basic / pro / lifetime) that caps tracked channels
and items processed per monthly period. Plans live in ``plans.yml``.

Per-user state, all under ``data/users/{chat_id}/`` with atomic writes:

    subscription.yaml — plan, status, expiry, last Telegram charge id
    usage.json        — current-period item counter (lazy monthly rollover)

No database — the same JSON/YAML + thread-lock + atomic-write pattern as
:mod:`src.pending` / :mod:`src.profile`. Caches and locks are partitioned
per ``chat_id``.

Statuses returned by :func:`subscription_status`:

    active   — trial or paid plan within its window (or lifetime)
    expired  — the entitlement window has lapsed
    none     — the user has no subscription file at all
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from src.config import user_subscription_file, user_usage_file

logger = logging.getLogger(__name__)

# plans.yml sits at the repo root next to channels.yml. Resolved relative
# to this file so it is independent of any per-test BASE_DIR patching —
# the plan catalog is static committed config, not per-user state.
_PLANS_PATH = Path(__file__).resolve().parent.parent / "plans.yml"
_FALLBACK_PLAN_KEY = "trial"

# Built-in fallback so the bot still boots if plans.yml is missing/corrupt.
_FALLBACK_PLANS: dict[str, dict[str, Any]] = {
    "trial": {
        "name_key": "plan_name_trial", "price_xtr": 0, "period_days": 14,
        "subscription_period_days": 0, "max_channels": 3,
        "max_items_per_period": 30, "purchasable": False,
    },
    "lifetime": {
        "name_key": "plan_name_lifetime", "price_xtr": 0, "period_days": 0,
        "subscription_period_days": 0, "max_channels": 100000,
        "max_items_per_period": 100000, "purchasable": False,
    },
}


# ── Plan catalog ────────────────────────────────────────────────────────────

_plans_cache: dict[str, dict[str, Any]] | None = None
_plans_lock = threading.Lock()


def load_plans() -> dict[str, dict[str, Any]]:
    """Return the plan catalog from plans.yml, cached after first read."""
    global _plans_cache
    with _plans_lock:
        if _plans_cache is not None:
            return _plans_cache
        try:
            with open(_PLANS_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError) as exc:
            logger.warning("Failed to read plans.yml (%s) — using fallback.", exc)
            data = {}
        if not isinstance(data, dict) or not data:
            data = {k: dict(v) for k, v in _FALLBACK_PLANS.items()}
        _plans_cache = data
        return _plans_cache


def get_plan(plan_key: str) -> dict[str, Any]:
    """Resolved plan dict for ``plan_key``; falls back to the trial plan."""
    plans = load_plans()
    plan = plans.get(plan_key)
    if plan is None:
        plan = plans.get(_FALLBACK_PLAN_KEY) or _FALLBACK_PLANS["trial"]
    return plan


def purchasable_plans() -> list[tuple[str, dict[str, Any]]]:
    """(key, plan) pairs a user can buy via /subscribe, cheapest first."""
    items = [
        (key, plan) for key, plan in load_plans().items()
        if plan.get("purchasable")
    ]
    items.sort(key=lambda kv: int(kv[1].get("price_xtr", 0)))
    return items


# ── Per-user caches + lock registry ─────────────────────────────────────────

_subscription_caches: dict[int, dict[str, Any]] = {}
_subscription_locks: dict[int, threading.Lock] = {}
_usage_caches: dict[int, dict[str, Any]] = {}
_usage_locks: dict[int, threading.Lock] = {}
_billing_meta_lock = threading.Lock()


def _sub_lock_for(chat_id: int) -> threading.Lock:
    with _billing_meta_lock:
        lock = _subscription_locks.get(chat_id)
        if lock is None:
            lock = threading.Lock()
            _subscription_locks[chat_id] = lock
        return lock


def _usage_lock_for(chat_id: int) -> threading.Lock:
    with _billing_meta_lock:
        lock = _usage_locks.get(chat_id)
        if lock is None:
            lock = threading.Lock()
            _usage_locks[chat_id] = lock
        return lock


# ── Helpers ─────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_dt(value: Any) -> datetime | None:
    """Parse an ISO-8601 string (or datetime) into an aware UTC datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── Subscription state ──────────────────────────────────────────────────────

_DEFAULT_SUBSCRIPTION: dict[str, Any] = {
    "plan": "",
    "status": "none",
    "started_at": "",
    "expires_at": None,
    "source": "",
    "telegram_charge_id": None,
    "updated_at": "",
}


def _fresh_subscription() -> dict[str, Any]:
    return dict(_DEFAULT_SUBSCRIPTION)


def _load_subscription_from_disk(chat_id: int) -> dict[str, Any]:
    path = user_subscription_file(chat_id)
    if not path.exists():
        return _fresh_subscription()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (yaml.YAMLError, OSError) as exc:
        logger.warning("Failed to read %s: %s — treating as no subscription.", path, exc)
        return _fresh_subscription()
    if not isinstance(data, dict):
        return _fresh_subscription()
    merged = _fresh_subscription()
    merged.update(data)
    return merged


def _flush_subscription(chat_id: int) -> None:
    """Atomically persist a user's cached subscription. Caller holds the lock."""
    path = user_subscription_file(chat_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        yaml.dump(
            _subscription_caches[chat_id], f,
            allow_unicode=True, default_flow_style=False, sort_keys=False,
        )
    os.replace(tmp_path, path)


def subscription_file_exists(chat_id: int) -> bool:
    """True if this user already has a subscription.yaml on disk."""
    return user_subscription_file(chat_id).exists()


def load_subscription(chat_id: int) -> dict[str, Any]:
    """Return a copy of ``chat_id``'s subscription (defaults if none)."""
    with _sub_lock_for(chat_id):
        cache = _subscription_caches.get(chat_id)
        if cache is None:
            cache = _load_subscription_from_disk(chat_id)
            _subscription_caches[chat_id] = cache
        return dict(cache)


def save_subscription(chat_id: int, sub: dict[str, Any]) -> None:
    """Replace ``chat_id``'s subscription and persist it atomically."""
    merged = _fresh_subscription()
    merged.update(sub)
    merged["updated_at"] = _now_iso()
    with _sub_lock_for(chat_id):
        _subscription_caches[chat_id] = merged
        _flush_subscription(chat_id)


def start_trial(chat_id: int) -> dict[str, Any]:
    """Write a fresh trial subscription for a newly-registered user."""
    plan = get_plan("trial")
    now = _now()
    days = int(plan.get("period_days", 14))
    sub = {
        "plan": "trial",
        "status": "active",
        "started_at": now.isoformat(),
        "expires_at": (now + timedelta(days=days)).isoformat(),
        "source": "trial",
        "telegram_charge_id": None,
    }
    save_subscription(chat_id, sub)
    logger.info("Started %d-day trial for chat_id=%s", days, chat_id)
    return sub


def activate_paid(
    chat_id: int,
    plan_key: str,
    *,
    charge_id: str,
    period_days: int | None = None,
    source: str = "telegram_stars",
    expires_at: Any = None,
) -> dict[str, Any]:
    """Activate / extend a paid plan after a successful Telegram payment.

    *expires_at* — when Telegram reports a subscription expiry date, pass
    it through verbatim; otherwise the new window is ``period_days`` from
    the later of now and the current expiry (so a renewal extends, never
    truncates).
    """
    plan = get_plan(plan_key)
    now = _now()
    current = load_subscription(chat_id)

    explicit = _parse_dt(expires_at)
    if explicit is not None:
        new_expiry = explicit
    else:
        days = int(period_days if period_days is not None else plan.get("period_days", 30))
        base = now
        cur_exp = _parse_dt(current.get("expires_at"))
        if cur_exp and cur_exp > now and current.get("plan") == plan_key:
            base = cur_exp
        new_expiry = base + timedelta(days=days)

    sub = {
        "plan": plan_key,
        "status": "active",
        "started_at": current.get("started_at") or now.isoformat(),
        "expires_at": new_expiry.isoformat(),
        "source": source,
        "telegram_charge_id": charge_id,
    }
    save_subscription(chat_id, sub)
    logger.info("Activated plan=%s for chat_id=%s until %s", plan_key, chat_id, sub["expires_at"])
    return sub


def grandfather(chat_id: int) -> dict[str, Any]:
    """Assign the internal unlimited 'lifetime' plan (migration / admin)."""
    now = _now()
    sub = {
        "plan": "lifetime",
        "status": "active",
        "started_at": now.isoformat(),
        "expires_at": None,
        "source": "grandfathered",
        "telegram_charge_id": None,
    }
    save_subscription(chat_id, sub)
    logger.info("Grandfathered chat_id=%s to lifetime plan", chat_id)
    return sub


def cancel_subscription(chat_id: int) -> dict[str, Any]:
    """Mark the subscription cancelled — access continues until period end."""
    sub = load_subscription(chat_id)
    sub["status"] = "cancelled"
    save_subscription(chat_id, sub)
    logger.info("Cancelled subscription for chat_id=%s", chat_id)
    return sub


def subscription_status(chat_id: int) -> str:
    """'active' | 'expired' | 'none', derived defensively from expires_at.

    The stored ``status`` field is only a cache — a paid plan whose
    ``expires_at`` has lapsed (e.g. a missed recurring renewal) is always
    reported as ``expired`` regardless of what the file says.
    """
    sub = load_subscription(chat_id)
    plan = sub.get("plan")
    if not plan or sub.get("status") == "none":
        return "none"
    if plan == "lifetime":
        return "active"
    exp = _parse_dt(sub.get("expires_at"))
    if exp is None:
        return "active"
    return "expired" if exp <= _now() else "active"


def is_active(chat_id: int) -> bool:
    """True if the user has a usable (non-expired) subscription."""
    return subscription_status(chat_id) == "active"


def current_plan(chat_id: int) -> dict[str, Any]:
    """Resolved plan dict for this user's subscription."""
    sub = load_subscription(chat_id)
    return get_plan(sub.get("plan") or _FALLBACK_PLAN_KEY)


# ── Usage metering (monthly, lazy rollover) ─────────────────────────────────

def _current_period() -> str:
    return _now().strftime("%Y-%m")


def _fresh_usage() -> dict[str, Any]:
    return {
        "period": _current_period(),
        "items_processed": 0,
        "tokens_total": 0,
        "by_source": {},
        "last_processed_at": "",
    }


def _load_usage_from_disk(chat_id: int) -> dict[str, Any]:
    path = user_usage_file(chat_id)
    if not path.exists():
        return _fresh_usage()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return _fresh_usage()
    if not isinstance(data, dict):
        return _fresh_usage()
    merged = _fresh_usage()
    merged.update(data)
    if not isinstance(merged.get("by_source"), dict):
        merged["by_source"] = {}
    return merged


def _flush_usage(chat_id: int) -> None:
    """Atomically persist a user's cached usage. Caller holds the usage lock."""
    path = user_usage_file(chat_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(_usage_caches[chat_id], f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def _ensure_usage(chat_id: int) -> dict[str, Any]:
    """Return the usage cache with monthly rollover applied.

    Caller must hold :func:`_usage_lock_for(chat_id)`. When the stored
    period is stale the counters reset in place and are flushed — no cron.
    """
    cache = _usage_caches.get(chat_id)
    if cache is None:
        cache = _load_usage_from_disk(chat_id)
        _usage_caches[chat_id] = cache
    current = _current_period()
    if cache.get("period") != current:
        cache["period"] = current
        cache["items_processed"] = 0
        cache["tokens_total"] = 0
        cache["by_source"] = {}
        _flush_usage(chat_id)
    return cache


def load_usage(chat_id: int) -> dict[str, Any]:
    """Return a copy of ``chat_id``'s current-period usage."""
    with _usage_lock_for(chat_id):
        return dict(_ensure_usage(chat_id))


def record_usage(chat_id: int, *, source: str, tokens: int = 0) -> None:
    """Increment the processed-item counter for ``chat_id`` atomically.

    Called once per successfully-staged pipeline item. *source* is
    ``"add"`` (interactive) or ``"scheduler"`` (periodic).
    """
    with _usage_lock_for(chat_id):
        cache = _ensure_usage(chat_id)
        cache["items_processed"] = int(cache.get("items_processed", 0)) + 1
        cache["tokens_total"] = int(cache.get("tokens_total", 0)) + int(tokens)
        by_source = cache["by_source"]
        by_source[source] = int(by_source.get(source, 0)) + 1
        cache["last_processed_at"] = _now_iso()
        _flush_usage(chat_id)


# ── Quota checks ────────────────────────────────────────────────────────────

def quota_check(chat_id: int) -> tuple[bool, str]:
    """Pre-flight gate for the content pipeline.

    Returns ``(allowed, reason_key)`` where *reason_key* is a strings.py
    key — one of ``""`` / ``"quota_expired"`` / ``"quota_items_exceeded"``.
    """
    if subscription_status(chat_id) != "active":
        return False, "quota_expired"
    plan = current_plan(chat_id)
    usage = load_usage(chat_id)
    limit = int(plan.get("max_items_per_period", 0))
    if int(usage.get("items_processed", 0)) >= limit:
        return False, "quota_items_exceeded"
    return True, ""


def channel_quota_check(chat_id: int, current_channel_count: int) -> tuple[bool, str]:
    """Gate for adding a new tracked channel. Returns ``(allowed, reason_key)``."""
    if subscription_status(chat_id) != "active":
        return False, "quota_expired"
    plan = current_plan(chat_id)
    limit = int(plan.get("max_channels", 0))
    if current_channel_count >= limit:
        return False, "quota_channels_exceeded"
    return True, ""


def usage_summary(chat_id: int) -> dict[str, Any]:
    """Compact billing snapshot for the /billing command."""
    sub = load_subscription(chat_id)
    plan = current_plan(chat_id)
    usage = load_usage(chat_id)
    return {
        "plan": sub.get("plan") or "none",
        "status": subscription_status(chat_id),
        "expires_at": sub.get("expires_at"),
        "items_used": int(usage.get("items_processed", 0)),
        "items_limit": int(plan.get("max_items_per_period", 0)),
        "channels_limit": int(plan.get("max_channels", 0)),
        "period": usage.get("period", ""),
    }


# ── Startup housekeeping ────────────────────────────────────────────────────

def prune_billing_state(valid_ids: Iterable[int]) -> int:
    """Drop subscription/usage caches + locks for chat_ids outside ``valid_ids``."""
    keep = set(valid_ids)
    pruned = 0
    with _billing_meta_lock:
        for registry in (_subscription_caches, _usage_caches):
            for cid in [c for c in registry if c not in keep]:
                registry.pop(cid, None)
                pruned += 1
        for registry in (_subscription_locks, _usage_locks):
            for cid in [c for c in registry if c not in keep]:
                del registry[cid]
                pruned += 1
    return pruned
