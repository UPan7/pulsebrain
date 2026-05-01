"""Tests for the legacy -> per-user one-shot migration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


def _write_legacy_fixture(tmp_path: Path) -> Path:
    """Seed tmp_path with a realistic legacy single-user layout."""
    from src.config import (
        KNOWLEDGE_DIR,
        LEGACY_CATEGORIES_FILE,
        LEGACY_CHANNELS_FILE,
        LEGACY_PENDING_FILE,
        LEGACY_PROCESSED_FILE,
        LEGACY_PROFILE_FILE,
        LEGACY_REJECTED_LOG_FILE,
    )

    LEGACY_PROCESSED_FILE.write_text(
        json.dumps({"yt:abc123": {"status": "ok", "processed_at": "2026-04-01T00:00:00Z"}}),
        encoding="utf-8",
    )
    LEGACY_PENDING_FILE.write_text(json.dumps({}), encoding="utf-8")
    LEGACY_PROFILE_FILE.write_text(
        yaml.dump({"language": "en", "persona": "Test user", "known_stack": ["Python"]}),
        encoding="utf-8",
    )
    LEGACY_CATEGORIES_FILE.write_text(
        yaml.dump({"custom-cat": "Custom category"}),
        encoding="utf-8",
    )
    LEGACY_REJECTED_LOG_FILE.write_text('{"title":"junk","reason":"manual"}\n', encoding="utf-8")
    LEGACY_CHANNELS_FILE.write_text(
        yaml.dump({"channels": [{"name": "Ch1", "id": "UC123", "category": "ai-news", "enabled": True}]}),
        encoding="utf-8",
    )

    # Seed a legacy knowledge entry under the old flat tree
    old_entry_dir = KNOWLEDGE_DIR / "ai-news" / "2026" / "04"
    old_entry_dir.mkdir(parents=True, exist_ok=True)
    (old_entry_dir / "testsrc_foo_2026-04-01.md").write_text(
        "# Foo\n\n- **Source:** https://example.com\n- **Type:** web_article\n",
        encoding="utf-8",
    )
    (KNOWLEDGE_DIR / "_index.md").write_text("# old index\n", encoding="utf-8")
    return tmp_path


def test_migration_moves_legacy_files_to_admin_namespace(tmp_knowledge_dir, chat_id):
    """All legacy files land under data/users/{admin_chat_id}/ after migration."""
    _write_legacy_fixture(tmp_knowledge_dir)

    from src.config import (
        LEGACY_PROCESSED_FILE,
        LEGACY_CHANNELS_FILE,
        MIGRATION_MARKER_FILE,
        user_channels_file,
        user_knowledge_dir,
        user_processed_file,
        user_profile_file,
    )
    from src.migration import migrate_legacy_to_admin

    ran = migrate_legacy_to_admin(chat_id)
    assert ran is True

    assert not LEGACY_PROCESSED_FILE.exists()
    assert not LEGACY_CHANNELS_FILE.exists()
    assert user_processed_file(chat_id).exists()
    assert user_channels_file(chat_id).exists()
    assert user_profile_file(chat_id).exists()
    assert MIGRATION_MARKER_FILE.exists()

    # Knowledge tree moved into admin namespace
    admin_root = user_knowledge_dir(chat_id)
    assert (admin_root / "ai-news" / "2026" / "04" / "testsrc_foo_2026-04-01.md").exists()


def test_migration_is_idempotent(tmp_knowledge_dir, chat_id):
    """Running migration twice is a no-op on the second call."""
    _write_legacy_fixture(tmp_knowledge_dir)

    from src.migration import migrate_legacy_to_admin

    assert migrate_legacy_to_admin(chat_id) is True
    assert migrate_legacy_to_admin(chat_id) is False


def test_migration_on_fresh_install_just_writes_marker(tmp_knowledge_dir, chat_id):
    """Fresh install (no legacy data) creates the marker and returns False."""
    from src.config import MIGRATION_MARKER_FILE
    from src.migration import migrate_legacy_to_admin

    ran = migrate_legacy_to_admin(chat_id)
    assert ran is False
    assert MIGRATION_MARKER_FILE.exists()


def test_migration_skipped_for_invalid_admin(tmp_knowledge_dir):
    from src.migration import migrate_legacy_to_admin

    assert migrate_legacy_to_admin(0) is False
    assert migrate_legacy_to_admin(-1) is False
