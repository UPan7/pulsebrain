"""One-shot migration: legacy single-user layout -> per-user namespace.

Before the multi-tenant refactor the bot kept all state in flat paths:

    data/processed.json
    data/pending.json
    data/user_profile.yaml
    data/categories.yml
    data/rejected_log.jsonl
    channels.yml                        (at repo root)
    knowledge/{category}/{year}/{month}/*.md

After the refactor every artifact lives under a chat_id namespace:

    data/users/{chat_id}/processed.json
    data/users/{chat_id}/pending.json
    data/users/{chat_id}/profile.yaml
    data/users/{chat_id}/categories.yml
    data/users/{chat_id}/rejected_log.jsonl
    data/users/{chat_id}/channels.yml
    knowledge/{chat_id}/{category}/{year}/{month}/*.md

This module moves the legacy files into the admin's namespace the very
first time the new code boots. It is idempotent — a marker file
``data/.migrated_v1`` is created after a successful run and subsequent
boots skip the whole procedure.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone

from src.config import (
    DATA_DIR,
    KNOWLEDGE_DIR,
    LEGACY_CATEGORIES_FILE,
    LEGACY_CHANNELS_FILE,
    LEGACY_PENDING_FILE,
    LEGACY_PROCESSED_FILE,
    LEGACY_PROFILE_FILE,
    LEGACY_REJECTED_LOG_FILE,
    MIGRATION_MARKER_FILE,
    ensure_user_dirs,
    user_categories_file,
    user_channels_file,
    user_knowledge_dir,
    user_pending_file,
    user_processed_file,
    user_profile_file,
    user_rejected_log_file,
)

logger = logging.getLogger(__name__)


def _write_marker() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MIGRATION_MARKER_FILE.write_text(
        datetime.now(timezone.utc).isoformat() + "\n",
        encoding="utf-8",
    )


def _safe_move(src, dst) -> bool:
    """Move ``src`` -> ``dst`` if ``src`` exists and ``dst`` doesn't.

    Returns True if the move happened. Never raises on common failures
    — logs a warning and returns False instead.
    """
    if not src.exists():
        return False
    if dst.exists():
        logger.warning(
            "Migration: destination %s already exists, skipping move from %s",
            dst,
            src,
        )
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(src), str(dst))
        logger.info("Migrated: %s -> %s", src, dst)
        return True
    except OSError as exc:
        logger.warning("Migration: failed to move %s -> %s: %s", src, dst, exc)
        return False


def _migrate_knowledge_tree(admin_chat_id: int) -> int:
    """Move every category directory out of ``knowledge/`` into
    ``knowledge/{admin_chat_id}/``.

    Returns the number of top-level entries moved. Skips the marker
    directory itself if it already exists.
    """
    if not KNOWLEDGE_DIR.exists():
        return 0

    target = user_knowledge_dir(admin_chat_id)
    # Skip legacy knowledge migration entirely if the admin's namespace
    # already has any content — we don't want to silently merge trees.
    if target.exists() and any(target.iterdir()):
        logger.warning(
            "Migration: %s already has content, skipping knowledge tree move",
            target,
        )
        return 0

    target.mkdir(parents=True, exist_ok=True)
    moved = 0
    for item in list(KNOWLEDGE_DIR.iterdir()):
        # Don't move the admin's own namespace into itself.
        if item == target:
            continue
        # Skip non-directories except _index.md (which we regenerate anyway).
        if item.name == "_index.md":
            try:
                item.unlink()
            except OSError:
                pass
            continue
        # Skip anything that looks like another user's namespace (all-digit name).
        if item.is_dir() and item.name.isdigit():
            continue
        dst = target / item.name
        if _safe_move(item, dst):
            moved += 1
    return moved


def migrate_legacy_to_admin(admin_chat_id: int) -> bool:
    """Idempotent one-shot migrator. Returns True if migration ran this call."""
    if admin_chat_id <= 0:
        logger.warning("Migration skipped: invalid admin_chat_id=%s", admin_chat_id)
        return False

    if MIGRATION_MARKER_FILE.exists():
        return False

    # Nothing to migrate if no legacy files exist at all.
    legacy_sources = [
        LEGACY_PROCESSED_FILE,
        LEGACY_PENDING_FILE,
        LEGACY_PROFILE_FILE,
        LEGACY_CATEGORIES_FILE,
        LEGACY_REJECTED_LOG_FILE,
        LEGACY_CHANNELS_FILE,
    ]
    has_legacy_data = any(p.exists() for p in legacy_sources) or (
        KNOWLEDGE_DIR.exists()
        and any(
            c
            for c in KNOWLEDGE_DIR.iterdir()
            if c.name != "_index.md" and not (c.is_dir() and c.name.isdigit())
        )
    )
    if not has_legacy_data:
        logger.info("Migration: no legacy data found — fresh install, marking done.")
        _write_marker()
        return False

    logger.info("Migration: starting legacy -> chat_id=%s", admin_chat_id)
    ensure_user_dirs(admin_chat_id)

    _safe_move(LEGACY_PROCESSED_FILE, user_processed_file(admin_chat_id))
    _safe_move(LEGACY_PENDING_FILE, user_pending_file(admin_chat_id))
    _safe_move(LEGACY_PROFILE_FILE, user_profile_file(admin_chat_id))
    _safe_move(LEGACY_CATEGORIES_FILE, user_categories_file(admin_chat_id))
    _safe_move(LEGACY_REJECTED_LOG_FILE, user_rejected_log_file(admin_chat_id))
    _safe_move(LEGACY_CHANNELS_FILE, user_channels_file(admin_chat_id))

    moved_tree = _migrate_knowledge_tree(admin_chat_id)
    logger.info("Migration: moved %d knowledge tree entries", moved_tree)

    _write_marker()
    logger.info("Migration: complete. Marker written to %s", MIGRATION_MARKER_FILE)
    return True
