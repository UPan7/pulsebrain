"""Pending entry registry — staged content awaiting user approval.

Entries flow through three statuses (mirrored in processed.json):

    pending  → in this registry, no .md file yet
    ok       → committed to knowledge/, dropped from registry
    rejected → permanently rejected, dropped from registry

is_processed() returns True for any of these so the scheduler never re-stages
content the user has already seen.

The registry is persisted to data/pending.json with the same atomic-write +
threading.Lock pattern used by storage._processed_cache, so multiple
extractor threads and the bot's async tasks can safely stage and commit
without races.
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

from src.config import DATA_DIR, PENDING_FILE
from src.storage import _validate_category, mark_processed, save_entry

logger = logging.getLogger(__name__)


# ── In-memory cache + lock ─────────────────────────────────────────────────

_pending_lock = threading.Lock()
_pending_cache: dict[str, dict[str, Any]] | None = None


def _load_pending_from_disk() -> dict[str, dict[str, Any]]:
    """Read pending.json from disk (internal helper)."""
    if not PENDING_FILE.exists():
        return {}
    try:
        with open(PENDING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _flush_pending() -> None:
    """Atomically write _pending_cache to disk (caller must hold lock)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = PENDING_FILE.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(_pending_cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, PENDING_FILE)


def init_pending() -> None:
    """Load pending.json into memory. Call once at startup."""
    global _pending_cache
    with _pending_lock:
        _pending_cache = _load_pending_from_disk()


def _make_pending_id(content_id: str) -> str:
    """Short stable ID derived from the content_id (8 hex chars)."""
    return hashlib.sha256(content_id.encode("utf-8")).hexdigest()[:8]


# ── Public API ─────────────────────────────────────────────────────────────


def stage_pending(
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
) -> str:
    """Stage a new entry awaiting user approval. Returns a short pending_id.

    *raw_text* is the lossless original (transcript or article body). It is
    inlined in pending.json so commit_pending can write the source sibling
    alongside the .md when the user approves.
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
        "key_insights": key_insights,
        "action_items": action_items,
        "author": author,
        "sitename": sitename,
        "raw_text": raw_text,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    global _pending_cache
    with _pending_lock:
        if _pending_cache is None:
            _pending_cache = _load_pending_from_disk()
        _pending_cache[pending_id] = entry
        _flush_pending()

    logger.info("Staged pending entry %s: %s", pending_id, title)
    return pending_id


def get_pending(pending_id: str) -> dict[str, Any] | None:
    """Return a pending entry by id, or None if not found."""
    with _pending_lock:
        if _pending_cache is None:
            return _load_pending_from_disk().get(pending_id)
        return _pending_cache.get(pending_id)


def list_pending() -> list[dict[str, Any]]:
    """Return all pending entries, newest first."""
    with _pending_lock:
        cache = _pending_cache if _pending_cache is not None else _load_pending_from_disk()
        entries = list(cache.values())
    entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)
    return entries


def update_pending_category(
    pending_id: str,
    new_category: str,
    is_new_category: bool = False,
) -> bool:
    """Change the staged category for an entry. Returns True on success."""
    _validate_category(new_category)

    global _pending_cache
    with _pending_lock:
        if _pending_cache is None:
            _pending_cache = _load_pending_from_disk()
        entry = _pending_cache.get(pending_id)
        if entry is None:
            return False
        entry["category"] = new_category
        entry["is_new_category"] = is_new_category
        _flush_pending()

    return True


def commit_pending(pending_id: str) -> Path | None:
    """Persist a pending entry to knowledge/ and mark its content_id as ok.

    Returns the saved file path on success, or None if the id is unknown.
    """
    global _pending_cache
    with _pending_lock:
        if _pending_cache is None:
            _pending_cache = _load_pending_from_disk()
        entry = _pending_cache.get(pending_id)
        if entry is None:
            return None

    file_path = save_entry(
        title=entry["title"],
        source_url=entry["source_url"],
        source_type=entry["source_type"],
        source_name=entry["source_name"],
        date_str=entry["date_str"],
        category=entry["category"],
        relevance=entry["relevance"],
        topics=entry["topics"],
        summary_bullets=entry["summary_bullets"],
        detailed_notes=entry["detailed_notes"],
        key_insights=entry["key_insights"],
        action_items=entry["action_items"],
        author=entry.get("author"),
        sitename=entry.get("sitename"),
        raw_text=entry.get("raw_text"),
    )

    mark_processed(entry["content_id"], status="ok")

    with _pending_lock:
        if _pending_cache is not None and pending_id in _pending_cache:
            del _pending_cache[pending_id]
            _flush_pending()

    logger.info("Committed pending entry %s -> %s", pending_id, file_path)
    return file_path


def reject_pending(pending_id: str) -> bool:
    """Drop a pending entry and mark its content_id as rejected. Returns True on success."""
    global _pending_cache
    with _pending_lock:
        if _pending_cache is None:
            _pending_cache = _load_pending_from_disk()
        entry = _pending_cache.get(pending_id)
        if entry is None:
            return False
        content_id = entry["content_id"]
        del _pending_cache[pending_id]
        _flush_pending()

    mark_processed(content_id, status="rejected")
    logger.info("Rejected pending entry %s", pending_id)
    return True
