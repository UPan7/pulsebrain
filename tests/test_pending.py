"""Tests for src.pending — staging registry and approval lifecycle."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest


# ── stage_pending ──────────────────────────────────────────────────────────


def test_stage_pending_returns_id_and_persists(tmp_knowledge_dir, sample_pending_kwargs):
    import src.config
    from src.pending import init_pending, stage_pending, get_pending

    init_pending()
    pending_id = stage_pending(**sample_pending_kwargs)

    assert isinstance(pending_id, str)
    assert len(pending_id) == 8

    entry = get_pending(pending_id)
    assert entry is not None
    assert entry["title"] == "Test Video Title"
    assert entry["category"] == "ai-agents"
    assert entry["content_id"] == "yt:abc123"
    assert "created_at" in entry

    # Persisted to disk
    assert src.config.PENDING_FILE.exists()
    data = json.loads(src.config.PENDING_FILE.read_text("utf-8"))
    assert pending_id in data


def test_stage_pending_id_is_stable_for_same_content_id(tmp_knowledge_dir, sample_pending_kwargs):
    """Re-staging the same content_id produces the same pending_id."""
    from src.pending import init_pending, stage_pending

    init_pending()
    id1 = stage_pending(**sample_pending_kwargs)
    id2 = stage_pending(**sample_pending_kwargs)
    assert id1 == id2


def test_stage_pending_rejects_invalid_category(tmp_knowledge_dir, sample_pending_kwargs):
    from src.pending import init_pending, stage_pending

    init_pending()
    with pytest.raises(ValueError, match="Invalid category"):
        stage_pending(**{**sample_pending_kwargs, "category": "../etc"})


def test_stage_pending_atomic_write(tmp_knowledge_dir, sample_pending_kwargs):
    """No leftover .tmp file after a successful stage."""
    import src.config
    from src.pending import init_pending, stage_pending

    init_pending()
    stage_pending(**sample_pending_kwargs)
    assert not src.config.PENDING_FILE.with_suffix(".tmp").exists()


def test_stage_pending_supports_web_article_fields(tmp_knowledge_dir, sample_pending_kwargs):
    """Author/sitename are stored for web articles."""
    from src.pending import init_pending, stage_pending, get_pending

    init_pending()
    web_kwargs = {
        **sample_pending_kwargs,
        "source_type": "web_article",
        "content_id": "web:abcdef",
        "author": "Jane Doe",
        "sitename": "blog.example.com",
    }
    pending_id = stage_pending(**web_kwargs)

    entry = get_pending(pending_id)
    assert entry["author"] == "Jane Doe"
    assert entry["sitename"] == "blog.example.com"


def test_stage_pending_supports_unknown_source_type(tmp_knowledge_dir, sample_pending_kwargs):
    """Future content types (e.g. pdf) round-trip without changes."""
    from src.pending import init_pending, stage_pending, get_pending

    init_pending()
    pdf_kwargs = {
        **sample_pending_kwargs,
        "source_type": "pdf_document",
        "content_id": "pdf:xyz",
    }
    pending_id = stage_pending(**pdf_kwargs)

    entry = get_pending(pending_id)
    assert entry["source_type"] == "pdf_document"


# ── get_pending / list_pending ─────────────────────────────────────────────


def test_get_pending_returns_none_for_unknown(tmp_knowledge_dir):
    from src.pending import init_pending, get_pending

    init_pending()
    assert get_pending("nonexistent") is None


def test_list_pending_sorted_newest_first(tmp_knowledge_dir, sample_pending_kwargs):
    import time
    from src.pending import init_pending, stage_pending, list_pending

    init_pending()
    stage_pending(**{**sample_pending_kwargs, "content_id": "yt:first"})
    time.sleep(0.01)
    stage_pending(**{**sample_pending_kwargs, "content_id": "yt:second"})

    entries = list_pending()
    assert len(entries) == 2
    assert entries[0]["content_id"] == "yt:second"
    assert entries[1]["content_id"] == "yt:first"


def test_list_pending_empty(tmp_knowledge_dir):
    from src.pending import init_pending, list_pending

    init_pending()
    assert list_pending() == []


# ── update_pending_category ────────────────────────────────────────────────


def test_update_pending_category_changes_slug(tmp_knowledge_dir, sample_pending_kwargs):
    from src.pending import init_pending, stage_pending, get_pending, update_pending_category

    init_pending()
    pending_id = stage_pending(**sample_pending_kwargs)
    assert update_pending_category(pending_id, "robotics", is_new_category=True) is True

    entry = get_pending(pending_id)
    assert entry["category"] == "robotics"
    assert entry["is_new_category"] is True


def test_update_pending_category_returns_false_for_unknown(tmp_knowledge_dir):
    from src.pending import init_pending, update_pending_category

    init_pending()
    assert update_pending_category("nope", "ai-news") is False


def test_update_pending_category_rejects_invalid_slug(tmp_knowledge_dir, sample_pending_kwargs):
    from src.pending import init_pending, stage_pending, update_pending_category

    init_pending()
    pending_id = stage_pending(**sample_pending_kwargs)
    with pytest.raises(ValueError):
        update_pending_category(pending_id, "../etc")


# ── commit_pending ─────────────────────────────────────────────────────────


def test_commit_pending_writes_file_and_marks_processed(tmp_knowledge_dir, sample_pending_kwargs):
    from src.pending import init_pending, stage_pending, commit_pending, get_pending
    from src.storage import init_processed, is_processed

    init_processed()
    init_pending()
    pending_id = stage_pending(**sample_pending_kwargs)

    file_path = commit_pending(pending_id)
    assert file_path is not None
    assert Path(file_path).exists()

    # Status flips to ok and entry drops out of pending
    assert is_processed("yt:abc123")
    assert get_pending(pending_id) is None


def test_commit_pending_returns_none_for_unknown(tmp_knowledge_dir):
    from src.pending import init_pending, commit_pending

    init_pending()
    assert commit_pending("nope") is None


def test_commit_pending_uses_updated_category(tmp_knowledge_dir, sample_pending_kwargs):
    """A category change before commit ends up on disk."""
    from src.pending import init_pending, stage_pending, update_pending_category, commit_pending
    from src.storage import init_processed

    init_processed()
    init_pending()
    pending_id = stage_pending(**sample_pending_kwargs)
    update_pending_category(pending_id, "robotics")
    file_path = commit_pending(pending_id)

    assert "/robotics/" in str(file_path)
    content = Path(file_path).read_text("utf-8")
    assert "**Category:** robotics" in content


# ── reject_pending ─────────────────────────────────────────────────────────


def test_reject_pending_drops_entry_and_marks_rejected(tmp_knowledge_dir, sample_pending_kwargs):
    from src.pending import init_pending, stage_pending, reject_pending, get_pending
    from src.storage import init_processed, is_processed, _processed_cache  # noqa: F401

    init_processed()
    init_pending()
    pending_id = stage_pending(**sample_pending_kwargs)

    assert reject_pending(pending_id) is True
    assert get_pending(pending_id) is None
    # is_processed still True so scheduler skips it
    assert is_processed("yt:abc123")

    # Verify status is "rejected"
    import src.storage
    assert src.storage._processed_cache["yt:abc123"]["status"] == "rejected"


def test_reject_pending_returns_false_for_unknown(tmp_knowledge_dir):
    from src.pending import init_pending, reject_pending

    init_pending()
    assert reject_pending("nope") is False


def test_reject_pending_does_not_create_file(tmp_knowledge_dir, sample_pending_kwargs):
    import src.config
    from src.pending import init_pending, stage_pending, reject_pending
    from src.storage import init_processed

    init_processed()
    init_pending()
    pending_id = stage_pending(**sample_pending_kwargs)
    reject_pending(pending_id)

    md_files = list(src.config.KNOWLEDGE_DIR.rglob("*.md"))
    assert md_files == []


# ── Concurrency / persistence ──────────────────────────────────────────────


def test_concurrent_stage_pending(tmp_knowledge_dir, sample_pending_kwargs):
    """10 threads staging different IDs — all entries survive."""
    from src.pending import init_pending, stage_pending, get_pending

    init_pending()

    def stage(i: int):
        kwargs = {**sample_pending_kwargs, "content_id": f"yt:t{i}",
                  "title": f"Title {i}"}
        stage_pending(**kwargs)

    threads = [threading.Thread(target=stage, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    from src.pending import list_pending
    assert len(list_pending()) == 10


def test_pending_survives_corrupt_json(tmp_knowledge_dir):
    """Corrupt pending.json → graceful empty load."""
    import src.config
    from src.pending import init_pending, list_pending

    src.config.PENDING_FILE.write_text("NOT JSON {{{", encoding="utf-8")
    init_pending()
    assert list_pending() == []


def test_load_pending_at_startup(tmp_knowledge_dir, sample_pending_kwargs):
    """Pre-existing pending.json is loaded into memory at init."""
    import src.config
    from src.pending import init_pending, get_pending

    src.config.PENDING_FILE.write_text(
        json.dumps({"abc12345": {**sample_pending_kwargs, "id": "abc12345"}}),
        encoding="utf-8",
    )

    init_pending()
    assert get_pending("abc12345") is not None
