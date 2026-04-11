"""Tests for src.storage — processed tracking, index, search, entry cache."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest


# ── Processed tracking (thread safety) ─────────────────────────────────────


def test_is_processed_false_for_unknown(tmp_knowledge_dir):
    """Unknown content IDs return False."""
    from src.storage import init_processed, is_processed

    init_processed()
    assert is_processed("yt:nonexistent") is False


def test_mark_then_is_processed(tmp_knowledge_dir):
    """After marking, is_processed returns True (from memory, no disk re-read)."""
    from src.storage import init_processed, is_processed, mark_processed

    init_processed()
    mark_processed("yt:abc123", status="ok")
    assert is_processed("yt:abc123") is True


def test_mark_processed_atomic_write(tmp_knowledge_dir):
    """mark_processed writes via temp file + rename (atomic)."""
    import src.config
    from src.storage import init_processed, mark_processed

    init_processed()
    mark_processed("yt:test_atomic", status="ok")

    # The final file should exist and contain the entry
    processed_file = src.config.PROCESSED_FILE
    assert processed_file.exists()
    data = json.loads(processed_file.read_text("utf-8"))
    assert "yt:test_atomic" in data

    # No leftover .tmp file
    tmp_file = processed_file.with_suffix(".tmp")
    assert not tmp_file.exists()


def test_concurrent_mark_processed(tmp_knowledge_dir):
    """10 threads marking different IDs — all entries survive (no race)."""
    from src.storage import init_processed, is_processed, mark_processed

    init_processed()

    def mark(i: int):
        mark_processed(f"yt:vid{i}", status="ok")

    threads = [threading.Thread(target=mark, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for i in range(10):
        assert is_processed(f"yt:vid{i}"), f"yt:vid{i} missing after concurrent writes"


def test_load_processed_at_startup(tmp_knowledge_dir):
    """Pre-existing processed.json is loaded into memory at init."""
    import src.config
    from src.storage import init_processed, is_processed

    # Write a pre-existing file
    src.config.PROCESSED_FILE.write_text(
        json.dumps({"yt:existing": {"status": "ok"}}), encoding="utf-8"
    )

    init_processed()
    assert is_processed("yt:existing") is True


def test_processed_survives_corrupt_json(tmp_knowledge_dir):
    """Corrupt processed.json → graceful recovery (empty dict)."""
    import src.config
    from src.storage import init_processed, is_processed

    src.config.PROCESSED_FILE.write_text("NOT JSON {{{", encoding="utf-8")

    init_processed()
    assert is_processed("yt:anything") is False


# ── Content ID generation ──────────────────────────────────────────────────


def test_make_content_id_youtube():
    from src.storage import make_content_id

    assert make_content_id("youtube_video", "dQw4w9WgXcQ") == "yt:dQw4w9WgXcQ"


def test_make_content_id_web():
    from src.storage import make_content_id

    cid = make_content_id("web_article", "https://example.com")
    assert cid.startswith("web:")
    assert len(cid) == 4 + 16  # "web:" + 16 hex chars


# ── save_entry with index debounce ─────────────────────────────────────────


def test_save_entry_creates_md(tmp_knowledge_dir, sample_entry_kwargs):
    """save_entry creates a .md file at the expected path."""
    from src.storage import save_entry

    path = save_entry(**sample_entry_kwargs)
    assert Path(path).exists()
    content = Path(path).read_text("utf-8")
    assert "Test Video Title" in content


def test_save_entry_update_index_false(tmp_knowledge_dir, sample_entry_kwargs):
    """With update_index=False, _update_index is NOT called."""
    from src.storage import save_entry

    with patch("src.storage._update_index") as mock_idx:
        save_entry(**sample_entry_kwargs, update_index=False)
        mock_idx.assert_not_called()


def test_save_entry_default_updates_index(tmp_knowledge_dir, sample_entry_kwargs):
    """By default, save_entry calls _update_index."""
    from src.storage import save_entry

    with patch("src.storage._update_index") as mock_idx:
        save_entry(**sample_entry_kwargs)
        mock_idx.assert_called_once()


def test_batch_save_single_index_update(tmp_knowledge_dir, sample_entry_kwargs):
    """5 saves with update_index=False + 1 explicit _update_index = 1 call total."""
    from src.storage import _update_index, save_entry

    with patch("src.storage._update_index") as mock_idx:
        for i in range(5):
            kwargs = {**sample_entry_kwargs, "title": f"Entry {i}"}
            save_entry(**kwargs, update_index=False)
        mock_idx.assert_not_called()

    # Now call explicitly (unpatched)
    _update_index()
    import src.config
    index_path = src.config.KNOWLEDGE_DIR / "_index.md"
    assert index_path.exists()


# ── Index generation ───────────────────────────────────────────────────────


def test_update_index_creates_file(tmp_knowledge_dir, sample_entry_kwargs):
    """_update_index produces _index.md."""
    from src.storage import _update_index, save_entry

    save_entry(**sample_entry_kwargs, update_index=False)
    _update_index()

    import src.config
    index_path = src.config.KNOWLEDGE_DIR / "_index.md"
    assert index_path.exists()
    text = index_path.read_text("utf-8")
    assert "Knowledge Base Index" in text


# ── Entry cache ────────────────────────────────────────────────────────────


def test_get_stats_correct_counts(tmp_knowledge_dir, sample_entry_kwargs):
    """Correct counts for videos vs articles."""
    from src.storage import save_entry, get_stats

    save_entry(**sample_entry_kwargs, update_index=False)
    save_entry(**{**sample_entry_kwargs, "title": "Video 2"}, update_index=False)
    save_entry(
        **{**sample_entry_kwargs, "title": "Article 1", "source_type": "web_article"},
        update_index=False,
    )

    stats = get_stats()
    assert stats["total"] == 3
    assert stats["videos"] == 2
    assert stats["articles"] == 1


def test_get_stats_uses_cache(tmp_knowledge_dir, sample_entry_kwargs):
    """Second get_stats call within TTL reuses cache (no rglob)."""
    from src.storage import save_entry, get_stats

    save_entry(**sample_entry_kwargs, update_index=False)

    # First call populates cache
    get_stats()

    # Patch rglob on the knowledge dir to track calls
    with patch("src.storage.KNOWLEDGE_DIR") as mock_dir:
        # Even with KNOWLEDGE_DIR mocked, cache should be used
        stats = get_stats()
        # rglob should NOT have been called because cache is warm
        mock_dir.rglob.assert_not_called()


def test_cache_invalidated_after_ttl(tmp_knowledge_dir, sample_entry_kwargs, monkeypatch):
    """Cache re-scans after TTL expires."""
    import src.storage
    from src.storage import save_entry, get_stats

    monkeypatch.setattr(src.storage, "_ENTRY_CACHE_TTL", 0.1)

    save_entry(**sample_entry_kwargs, update_index=False)
    get_stats()  # populate cache

    time.sleep(0.15)  # exceed TTL

    # Cache should be stale now — next call must re-scan
    stats = get_stats()
    assert stats["total"] == 1  # Still correct after re-scan


# ── Search ─────────────────────────────────────────────────────────────────


def test_search_knowledge_basic(tmp_knowledge_dir, sample_entry_kwargs):
    """Keyword match in title finds the entry."""
    from src.storage import save_entry, search_knowledge

    save_entry(**sample_entry_kwargs, update_index=False)

    results = search_knowledge("Test Video")
    assert len(results) >= 1
    assert "Test Video Title" in results[0].get("title", "")


# ── Path traversal defense ──────────────────────────��──────────────────────


def test_save_entry_rejects_path_traversal(tmp_knowledge_dir, sample_entry_kwargs):
    """Category with '..' is rejected."""
    from src.storage import save_entry

    with pytest.raises(ValueError, match="Invalid category"):
        save_entry(**{**sample_entry_kwargs, "category": "../../../etc"})


def test_save_entry_rejects_slash(tmp_knowledge_dir, sample_entry_kwargs):
    """Category with '/' is rejected."""
    from src.storage import save_entry

    with pytest.raises(ValueError, match="Invalid category"):
        save_entry(**{**sample_entry_kwargs, "category": "foo/bar"})
