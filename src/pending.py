"""Pending entry registry — per-user staged content awaiting approval.

Entries flow through three statuses (mirrored in a user's processed.json):

    pending  → in this registry, no .md file yet
    ok       → committed to knowledge/{chat_id}/, dropped from registry
    rejected → permanently rejected, dropped from registry

:func:`src.storage.is_processed` returns True for any of these so the
scheduler never re-stages content the user has already seen.

Each allowed ``chat_id`` has an independent registry on disk at
``data/users/{chat_id}/pending.json`` and a rejection log at
``data/users/{chat_id}/rejected_log.jsonl``. Caches and locks are
partitioned per chat_id.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import user_pending_file, user_rejected_log_file
from src.storage import _validate_category, mark_processed, save_entry

logger = logging.getLogger(__name__)


# ── Per-user cache + lock registry ─────────────────────────────────────────

_pending_caches: dict[int, dict[str, dict[str, Any]]] = {}
_pending_locks: dict[int, threading.Lock] = {}
_pending_meta_lock = threading.Lock()


def _lock_for(chat_id: int) -> threading.Lock:
    with _pending_meta_lock:
        lock = _pending_locks.get(chat_id)
        if lock is None:
            lock = threading.Lock()
            _pending_locks[chat_id] = lock
        return lock


def _load_from_disk(chat_id: int) -> dict[str, dict[str, Any]]:
    """Read a user's pending.json from disk (internal helper)."""
    path = user_pending_file(chat_id)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _flush(chat_id: int) -> None:
    """Atomically write this user's cache to disk (caller holds lock)."""
    path = user_pending_file(chat_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(_pending_caches[chat_id], f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def init_pending(chat_id: int) -> None:
    """Load a user's pending.json into memory. Call once per chat_id at startup."""
    with _lock_for(chat_id):
        _pending_caches[chat_id] = _load_from_disk(chat_id)


def _ensure_cache(chat_id: int) -> dict[str, dict[str, Any]]:
    """Return the cache for ``chat_id``, loading from disk if needed.

    Caller must hold :func:`_lock_for(chat_id)`.
    """
    cache = _pending_caches.get(chat_id)
    if cache is None:
        cache = _load_from_disk(chat_id)
        _pending_caches[chat_id] = cache
    return cache


def _make_pending_id(content_id: str) -> str:
    """Short stable ID derived from the content_id (8 hex chars)."""
    return hashlib.sha256(content_id.encode("utf-8")).hexdigest()[:8]


# ── Public API ─────────────────────────────────────────────────────────────


def stage_pending(
    chat_id: int,
    *,
    content_id: str,
    source_url: str,
    source_type: str,
    source_name: str,
    title: str,
    date_str: str | None,
    category: str,
    is_new_category: bool,
    relevance: int,
    topics: list[str],
    summary_bullets: list[str],
    detailed_notes: str,
    key_insights: list[str],
    action_items: list[str],
    author: str | None = None,
    sitename: str | None = None,
    raw_text: str | None = None,
    deep_dive: list[dict[str, str]] | None = None,
    length_mode: str = "",
) -> str:
    """Stage a new entry awaiting ``chat_id``'s approval. Returns pending_id.

    *raw_text* is the lossless original (transcript or article body). It is
    inlined in pending.json so :func:`commit_pending` can write the source
    sibling alongside the .md when the user approves.

    *deep_dive* is an optional list of ``{heading, body}`` dicts rendered
    as a new section in the saved markdown. Only long/xlong summarize
    modes populate it; callers from older pipelines pass ``None``.

    *length_mode* records which length budget the summarizer used
    ("short"/"medium"/"long"/"xlong") for analytics and debugging.
    """
    _validate_category(category)
    pending_id = _make_pending_id(content_id)

    entry: dict[str, Any] = {
        "id": pending_id,
        "content_id": content_id,
        "source_url": source_url,
        "source_type": source_type,
        "source_name": source_name,
        "title": title,
        "date_str": date_str,
        "category": category,
        "is_new_category": is_new_category,
        "relevance": relevance,
        "topics": topics,
        "summary_bullets": summary_bullets,
        "detailed_notes": detailed_notes,
        "deep_dive": deep_dive,
        "length_mode": length_mode,
        "key_insights": key_insights,
        "action_items": action_items,
        "author": author,
        "sitename": sitename,
        "raw_text": raw_text,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    with _lock_for(chat_id):
        cache = _ensure_cache(chat_id)
        cache[pending_id] = entry
        _flush(chat_id)

    logger.info("Staged pending entry (chat_id=%s) %s: %s", chat_id, pending_id, title)
    return pending_id


def get_pending(chat_id: int, pending_id: str) -> dict[str, Any] | None:
    """Return a pending entry by id for ``chat_id``, or None if not found."""
    with _lock_for(chat_id):
        cache = _ensure_cache(chat_id)
        return cache.get(pending_id)


def list_pending(chat_id: int) -> list[dict[str, Any]]:
    """Return all pending entries for ``chat_id``, newest first."""
    with _lock_for(chat_id):
        cache = _ensure_cache(chat_id)
        entries = list(cache.values())
    entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)
    return entries


def update_pending_category(
    chat_id: int,
    pending_id: str,
    new_category: str,
    is_new_category: bool = False,
) -> bool:
    """Change the staged category for an entry. Returns True on success."""
    _validate_category(new_category)

    with _lock_for(chat_id):
        cache = _ensure_cache(chat_id)
        entry = cache.get(pending_id)
        if entry is None:
            return False
        entry["category"] = new_category
        entry["is_new_category"] = is_new_category
        _flush(chat_id)

    return True


def commit_pending(chat_id: int, pending_id: str) -> Path | None:
    """Persist a pending entry to knowledge/{chat_id}/ and mark it as ok.

    Returns the saved file path on success, or None if the id is unknown.
    """
    with _lock_for(chat_id):
        cache = _ensure_cache(chat_id)
        entry = cache.get(pending_id)
        if entry is None:
            return None
        entry_snapshot = dict(entry)

    file_path = save_entry(
        chat_id,
        title=entry_snapshot["title"],
        source_url=entry_snapshot["source_url"],
        source_type=entry_snapshot["source_type"],
        source_name=entry_snapshot["source_name"],
        date_str=entry_snapshot["date_str"],
        category=entry_snapshot["category"],
        relevance=entry_snapshot["relevance"],
        topics=entry_snapshot["topics"],
        summary_bullets=entry_snapshot["summary_bullets"],
        detailed_notes=entry_snapshot["detailed_notes"],
        key_insights=entry_snapshot["key_insights"],
        action_items=entry_snapshot["action_items"],
        author=entry_snapshot.get("author"),
        sitename=entry_snapshot.get("sitename"),
        raw_text=entry_snapshot.get("raw_text"),
        deep_dive=entry_snapshot.get("deep_dive"),
    )

    mark_processed(chat_id, entry_snapshot["content_id"], status="ok")

    with _lock_for(chat_id):
        cache = _ensure_cache(chat_id)
        if pending_id in cache:
            del cache[pending_id]
            _flush(chat_id)

    logger.info("Committed pending entry (chat_id=%s) %s -> %s", chat_id, pending_id, file_path)
    return file_path


def _append_rejected_log(chat_id: int, entry: dict[str, Any], reason: str) -> None:
    """Append a rejection record to the user's rejected_log.jsonl.

    Never raises — log failures are swallowed so the caller's rejection still
    succeeds. The log is the source for the /rejected Telegram command.
    """
    try:
        path = user_rejected_log_file(chat_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "pending_id": entry.get("id", ""),
            "title": entry.get("title", "?"),
            "source_name": entry.get("source_name", "?"),
            "source_url": entry.get("source_url", ""),
            "source_type": entry.get("source_type", ""),
            "relevance": entry.get("relevance", 0),
            "reason": reason,
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning("Failed to append rejected log (chat_id=%s): %s", chat_id, exc)


def read_rejected_log(chat_id: int, limit: int = 10) -> list[dict[str, Any]]:
    """Return the last *limit* entries from ``chat_id``'s rejected_log, newest first.

    Returns an empty list if the log doesn't exist or can't be parsed.
    """
    path = user_rejected_log_file(chat_id)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []

    records: list[dict[str, Any]] = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(records) >= limit:
            break
    return records


def reject_pending(chat_id: int, pending_id: str, reason: str = "manual") -> bool:
    """Drop a pending entry for ``chat_id`` and mark its content_id as rejected.

    *reason* is recorded to rejected_log.jsonl for later inspection via the
    ``/rejected`` command. Scheduler callers should pass ``"low_relevance"``;
    the default ``"manual"`` covers user-initiated rejects via the
    Telegram approve/reject keyboard.

    Returns True on success.
    """
    with _lock_for(chat_id):
        cache = _ensure_cache(chat_id)
        entry = cache.get(pending_id)
        if entry is None:
            return False
        content_id = entry["content_id"]
        log_snapshot = dict(entry)
        del cache[pending_id]
        _flush(chat_id)

    _append_rejected_log(chat_id, log_snapshot, reason)
    mark_processed(chat_id, content_id, status="rejected")
    logger.info("Rejected pending entry (chat_id=%s) %s (reason=%s)", chat_id, pending_id, reason)
    return True
