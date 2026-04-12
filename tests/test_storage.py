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


# ── move_entry ─────────────────────────────────────────────────────────────


def test_move_entry_relocates_file_and_rewrites_category(tmp_knowledge_dir, sample_entry_kwargs):
    from src.storage import save_entry, move_entry

    old = save_entry(**sample_entry_kwargs, update_index=False)
    new_path = move_entry(str(old), "new-cat")

    assert new_path is not None
    assert not old.exists()
    assert Path(new_path).exists()
    content = Path(new_path).read_text("utf-8")
    assert "**Category:** new-cat" in content
    # Year/month preserved
    assert "/2025/06/" in new_path


def test_move_entry_returns_none_when_file_missing(tmp_knowledge_dir):
    from src.storage import move_entry

    result = move_entry("/nonexistent/path.md", "new-cat")
    assert result is None


def test_move_entry_handles_short_path(tmp_knowledge_dir):
    """File directly in KNOWLEDGE_DIR (no year/month dirs) — falls back to flat target."""
    import src.config
    from src.storage import move_entry

    old = src.config.KNOWLEDGE_DIR / "old-cat" / "stray.md"
    old.parent.mkdir(parents=True, exist_ok=True)
    old.write_text("# Stray\n\n- **Category:** old-cat\n", encoding="utf-8")

    new_path = move_entry(str(old), "new-cat")
    assert new_path is not None
    assert Path(new_path).exists()
    assert "new-cat" in new_path


def test_move_entry_invalidates_cache(tmp_knowledge_dir, sample_entry_kwargs):
    import src.storage
    from src.storage import save_entry, move_entry, get_recent_entries

    old = save_entry(**sample_entry_kwargs, update_index=False)
    get_recent_entries(5)  # populate cache
    assert src.storage._entry_cache is not None

    move_entry(str(old), "new-cat")
    assert src.storage._entry_cache is None


# ── search_for_question ────────────────────────────────────────────────────


def test_search_for_question_finds_relevant_entries(tmp_knowledge_dir, sample_entry_kwargs):
    from src.storage import save_entry, search_for_question

    save_entry(**{**sample_entry_kwargs, "title": "Quantum Computing Basics"},
               update_index=False)
    results = search_for_question("quantum")

    assert len(results) >= 1
    assert "Quantum" in results[0]["title"]
    assert "extracted_text" in results[0]


def test_search_for_question_skips_no_match(tmp_knowledge_dir, sample_entry_kwargs):
    from src.storage import save_entry, search_for_question

    save_entry(**sample_entry_kwargs, update_index=False)
    results = search_for_question("nonexistent-keyword-xyz")
    assert results == []


def test_search_for_question_recency_bonus(tmp_knowledge_dir, sample_entry_kwargs):
    """Recent entry ranks above older entry with the same keyword score."""
    from datetime import datetime, timezone
    from src.storage import save_entry, search_for_question

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    save_entry(**{**sample_entry_kwargs, "title": "Quantum old", "date_str": "2020-01-01"},
               update_index=False)
    save_entry(**{**sample_entry_kwargs, "title": "Quantum new", "date_str": today},
               update_index=False)

    results = search_for_question("quantum")
    assert len(results) >= 2
    assert "new" in results[0]["title"]


def test_search_for_question_relevance_bonus(tmp_knowledge_dir, sample_entry_kwargs):
    """Higher relevance entry ranks above lower one with the same keyword score."""
    from src.storage import save_entry, search_for_question

    save_entry(**{**sample_entry_kwargs, "title": "Quantum low", "relevance": 1},
               update_index=False)
    save_entry(**{**sample_entry_kwargs, "title": "Quantum high", "relevance": 10},
               update_index=False)

    results = search_for_question("quantum")
    assert "high" in results[0]["title"]


def test_search_for_question_handles_invalid_date(tmp_knowledge_dir, sample_entry_kwargs):
    """Entry with unparseable date doesn't crash recency calculation."""
    from src.storage import save_entry, search_for_question

    save_entry(**{**sample_entry_kwargs, "title": "Quantum bad", "date_str": "not-a-date"},
               update_index=False)
    results = search_for_question("quantum")
    assert len(results) >= 1


# ── _extract_sections ──────────────────────────────────────────────────────


def test_extract_sections_returns_summary_only_when_compact():
    from src.storage import _extract_sections

    md = (
        "# Title\n\n"
        "## Summary\n\n• one\n\n"
        "## Key Insights\n\n- a\n\n"
        "## Detailed Notes\n\nlong notes\n"
    )
    out = _extract_sections(md, compact=True)
    assert "## Summary" in out
    assert "Key Insights" not in out
    assert "Detailed Notes" not in out


def test_extract_sections_returns_all_three_sections():
    from src.storage import _extract_sections

    md = (
        "# Title\n\n"
        "## Summary\n\n• one\n\n"
        "## Key Insights\n\n- insight\n\n"
        "## Detailed Notes\n\ndetailed\n"
    )
    out = _extract_sections(md, compact=False)
    assert "## Summary" in out
    assert "## Key Insights" in out
    assert "## Detailed Notes" in out


def test_extract_sections_falls_back_to_first_1000_chars():
    from src.storage import _extract_sections

    md = "x" * 2000  # No section headings
    out = _extract_sections(md)
    assert len(out) == 1000


# ── _update_index branches ─────────────────────────────────────────────────


def test_update_index_groups_by_category(tmp_knowledge_dir, sample_entry_kwargs):
    import src.config
    from src.storage import save_entry, _update_index

    save_entry(**{**sample_entry_kwargs, "title": "A", "category": "ai-news"},
               update_index=False)
    save_entry(**{**sample_entry_kwargs, "title": "B", "category": "wp"},
               update_index=False)
    _update_index()

    text = (src.config.KNOWLEDGE_DIR / "_index.md").read_text("utf-8")
    assert "### ai-news" in text
    assert "### wp" in text


def test_update_index_caps_category_entries_at_20(tmp_knowledge_dir, sample_entry_kwargs):
    import src.config
    from src.storage import save_entry, _update_index

    for i in range(25):
        save_entry(**{**sample_entry_kwargs, "title": f"Entry {i:02d}"},
                   update_index=False)
    _update_index()

    text = (src.config.KNOWLEDGE_DIR / "_index.md").read_text("utf-8")
    # Total category line shows full count, but rows under it cap at 20
    assert "(25 entries)" in text
    # Count rows in the ai-agents category section (lines starting with "| 2")
    cat_section = text.split("### ai-agents")[1].split("###")[0]
    row_count = sum(1 for line in cat_section.splitlines() if line.startswith("| 2"))
    assert row_count == 20


# ── _parse_entry_metadata ──────────────────────────────────────────────────


def test_parse_entry_metadata_returns_none_without_title(tmp_knowledge_dir):
    import src.config
    from src.storage import _parse_entry_metadata

    md = src.config.KNOWLEDGE_DIR / "no_title.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text("- **Source:** http://x\n", encoding="utf-8")

    assert _parse_entry_metadata(md) is None


def test_parse_entry_metadata_handles_web_article(tmp_knowledge_dir):
    import src.config
    from src.storage import _parse_entry_metadata

    md = src.config.KNOWLEDGE_DIR / "web.md"
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(
        "# Web Title\n\n"
        "- **Source:** https://example.com/x\n"
        "- **Type:** web_article\n"
        "- **Site:** example.com\n"
        "- **Date:** 2025-06-15\n"
        "- **Category:** ai-news\n"
        "- **Relevance:** 7/10\n",
        encoding="utf-8",
    )

    info = _parse_entry_metadata(md)
    assert info is not None
    assert info["title"] == "Web Title"
    assert info["type"] == "web_article"
    assert info["source"] == "example.com"
    assert info["category"] == "ai-news"
    assert info["relevance"] == "7"


# ── get_recent_entries / get_stats edges ───────────────────────────────────


def test_get_recent_entries_sorts_by_date_desc(tmp_knowledge_dir, sample_entry_kwargs):
    from src.storage import save_entry, get_recent_entries

    save_entry(**{**sample_entry_kwargs, "title": "Old", "date_str": "2020-01-01"},
               update_index=False)
    save_entry(**{**sample_entry_kwargs, "title": "New", "date_str": "2025-06-15"},
               update_index=False)

    entries = get_recent_entries(5)
    assert entries[0]["title"] == "New"
    assert entries[1]["title"] == "Old"


def test_get_recent_entries_respects_count(tmp_knowledge_dir, sample_entry_kwargs):
    from src.storage import save_entry, get_recent_entries

    for i in range(5):
        save_entry(**{**sample_entry_kwargs, "title": f"E{i}"}, update_index=False)

    assert len(get_recent_entries(2)) == 2


def test_get_stats_top_sources_ordering(tmp_knowledge_dir, sample_entry_kwargs):
    from src.storage import save_entry, get_stats

    for i in range(3):
        save_entry(**{**sample_entry_kwargs, "title": f"A{i}", "source_name": "Big"},
                   update_index=False)
    save_entry(**{**sample_entry_kwargs, "title": "Solo", "source_name": "Small"},
               update_index=False)

    stats = get_stats()
    assert stats["top_sources"][0][0] == "Big"
    assert stats["top_sources"][0][1] == 3


def test_get_stats_avg_relevance_with_no_scores(tmp_knowledge_dir):
    """Empty knowledge base → avg_relevance is 0."""
    from src.storage import get_stats

    stats = get_stats()
    assert stats["avg_relevance"] == 0
    assert stats["total"] == 0


def test_get_stats_this_week_filter(tmp_knowledge_dir, sample_entry_kwargs):
    from datetime import datetime, timezone
    from src.storage import save_entry, get_stats

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    save_entry(**{**sample_entry_kwargs, "title": "Recent", "date_str": today},
               update_index=False)
    save_entry(**{**sample_entry_kwargs, "title": "Old", "date_str": "2020-01-01"},
               update_index=False)

    stats = get_stats()
    assert stats["this_week"] == 1


# ── category_health ────────────────────────────────────────────────────────


def test_get_stats_category_health_counts_and_avg(tmp_knowledge_dir, sample_entry_kwargs):
    from src.storage import save_entry, get_stats

    save_entry(**{**sample_entry_kwargs, "title": "A", "category": "ai-agents",
                  "relevance": 8}, update_index=False)
    save_entry(**{**sample_entry_kwargs, "title": "B", "category": "ai-agents",
                  "relevance": 6}, update_index=False)
    save_entry(**{**sample_entry_kwargs, "title": "C", "category": "wordpress",
                  "relevance": 9}, update_index=False)

    health = get_stats()["category_health"]
    assert health["ai-agents"]["count"] == 2
    assert health["ai-agents"]["avg_relevance"] == 7.0
    assert health["wordpress"]["count"] == 1
    assert health["wordpress"]["avg_relevance"] == 9.0


def test_get_stats_category_health_tracks_last_entry(tmp_knowledge_dir, sample_entry_kwargs):
    from src.storage import save_entry, get_stats

    save_entry(**{**sample_entry_kwargs, "title": "Old", "date_str": "2024-01-01"},
               update_index=False)
    save_entry(**{**sample_entry_kwargs, "title": "Newer", "date_str": "2025-06-15"},
               update_index=False)

    health = get_stats()["category_health"]
    assert health["ai-agents"]["last_entry"] == "2025-06-15"


def test_get_stats_category_health_marks_stale(tmp_knowledge_dir, sample_entry_kwargs):
    """Category with no entries in the last 30 days is stale."""
    from datetime import datetime, timedelta, timezone
    from src.storage import save_entry, get_stats

    long_ago = (datetime.now(timezone.utc) -
                timedelta(days=60)).strftime("%Y-%m-%d")
    save_entry(**{**sample_entry_kwargs, "title": "Ancient", "date_str": long_ago},
               update_index=False)

    health = get_stats()["category_health"]
    assert health["ai-agents"]["stale"] is True


def test_get_stats_category_health_recent_not_stale(tmp_knowledge_dir, sample_entry_kwargs):
    from datetime import datetime, timezone
    from src.storage import save_entry, get_stats

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    save_entry(**{**sample_entry_kwargs, "title": "Fresh", "date_str": today},
               update_index=False)

    health = get_stats()["category_health"]
    assert health["ai-agents"]["stale"] is False


def test_get_stats_category_health_empty(tmp_knowledge_dir):
    from src.storage import get_stats

    assert get_stats()["category_health"] == {}


# ── search_knowledge edges ────────────────────────────────────────────────


def test_search_knowledge_skips_index_file(tmp_knowledge_dir, sample_entry_kwargs):
    import src.config
    from src.storage import save_entry, search_knowledge, _update_index

    save_entry(**sample_entry_kwargs, update_index=False)
    _update_index()  # Creates _index.md

    # Searching for a term that's only in _index.md (like "Knowledge Base Index")
    # should not return _index.md itself
    results = search_knowledge("Knowledge Base Index")
    assert all("_index.md" not in r.get("path", "") for r in results)


def test_search_knowledge_no_match_returns_empty(tmp_knowledge_dir, sample_entry_kwargs):
    from src.storage import save_entry, search_knowledge

    save_entry(**sample_entry_kwargs, update_index=False)
    assert search_knowledge("xyz-no-match") == []


# ── save_entry edges ──────────────────────────────────────────────────────


def test_save_entry_handles_invalid_date_string(tmp_knowledge_dir, sample_entry_kwargs):
    """Unparseable date_str → falls back to today (no crash)."""
    from src.storage import save_entry

    path = save_entry(**{**sample_entry_kwargs, "date_str": "not-a-date"},
                      update_index=False)
    assert path.exists()


def test_save_entry_handles_long_filename(tmp_knowledge_dir, sample_entry_kwargs):
    from src.storage import save_entry

    long_title = "x" * 300
    path = save_entry(**{**sample_entry_kwargs, "title": long_title}, update_index=False)
    assert path.exists()
    assert len(path.name) <= 100


def test_save_entry_then_parse_metadata_roundtrip(tmp_knowledge_dir, sample_entry_kwargs):
    """Format written by save_entry matches what _parse_entry_metadata can read."""
    from src.storage import save_entry, _parse_entry_metadata

    path = save_entry(**sample_entry_kwargs, update_index=False)
    info = _parse_entry_metadata(path)

    assert info is not None
    assert info["title"] == "Test Video Title"
    assert info["type"] == "youtube_video"
    assert info["source"] == "TestChannel"  # from "Channel:" line
    assert info["category"] == "ai-agents"
    assert info["date"] == "2025-06-15"
    assert info["relevance"] == "8"


def test_save_entry_with_unicode_title(tmp_knowledge_dir, sample_entry_kwargs):
    """Cyrillic title slugifies safely."""
    from src.storage import save_entry

    path = save_entry(**{**sample_entry_kwargs, "title": "Привет Мир Тест"},
                      update_index=False)
    assert path.exists()
    content = path.read_text("utf-8")
    assert "Привет Мир Тест" in content


# ── raw_text sibling ───────────────────────────────────────────────────────


def test_save_entry_writes_source_sibling_when_raw_text_given(
    tmp_knowledge_dir, sample_entry_kwargs
):
    from src.storage import save_entry, _source_sibling_path

    transcript = "This is the full transcript of the video. " * 100
    path = save_entry(
        **sample_entry_kwargs,
        raw_text=transcript,
        update_index=False,
    )

    sibling = _source_sibling_path(path)
    assert sibling.exists()
    assert sibling.read_text("utf-8") == transcript
    # The sibling lives in the same dir as the .md
    assert sibling.parent == path.parent
    # And uses the .source.txt suffix
    assert sibling.name.endswith(".source.txt")


def test_save_entry_skips_sibling_when_raw_text_none(
    tmp_knowledge_dir, sample_entry_kwargs
):
    """No raw_text → no sibling file written."""
    from src.storage import save_entry, _source_sibling_path

    path = save_entry(**sample_entry_kwargs, update_index=False)
    assert not _source_sibling_path(path).exists()


def test_save_entry_returns_md_path_even_if_sibling_write_fails(
    tmp_knowledge_dir, sample_entry_kwargs, monkeypatch
):
    """A flaky filesystem on the sibling write must not abort the whole save."""
    import builtins
    from src.storage import save_entry

    real_open = builtins.open

    def flaky_open(path, *args, **kwargs):
        if str(path).endswith(".source.txt"):
            raise OSError("disk full")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", flaky_open)

    path = save_entry(
        **sample_entry_kwargs,
        raw_text="some transcript",
        update_index=False,
    )
    # The .md still landed
    assert path.exists()


def test_move_entry_relocates_source_sibling(tmp_knowledge_dir, sample_entry_kwargs):
    """move_entry must carry the .source.txt sibling along with the .md."""
    from src.storage import save_entry, move_entry, _source_sibling_path

    path = save_entry(
        **sample_entry_kwargs,
        raw_text="original transcript text",
        update_index=False,
    )
    old_sibling = _source_sibling_path(path)
    assert old_sibling.exists()

    new_md_str = move_entry(str(path), "new-cat")
    new_md = Path(new_md_str)
    new_sibling = _source_sibling_path(new_md)

    # Old files gone, new files present
    assert not path.exists()
    assert not old_sibling.exists()
    assert new_md.exists()
    assert new_sibling.exists()
    assert new_sibling.read_text("utf-8") == "original transcript text"


def test_move_entry_handles_missing_sibling(tmp_knowledge_dir, sample_entry_kwargs):
    """Pre-raw_text entries (no sibling) move cleanly without errors."""
    from src.storage import save_entry, move_entry, _source_sibling_path

    path = save_entry(**sample_entry_kwargs, update_index=False)
    assert not _source_sibling_path(path).exists()

    new_md_str = move_entry(str(path), "new-cat")
    assert new_md_str is not None
    assert Path(new_md_str).exists()


# ── Entry IDs + file access (Phase 7.9) ─────────────────────────────────────


def test_entry_id_stable_for_same_path(tmp_knowledge_dir, sample_entry_kwargs):
    """Same path → same ID across calls."""
    from src.storage import entry_id, save_entry

    path = save_entry(**sample_entry_kwargs, update_index=False)
    first = entry_id(path)
    second = entry_id(path)
    assert first == second
    assert len(first) == 8
    # Hex characters only
    assert all(c in "0123456789abcdef" for c in first)


def test_entry_id_differs_between_different_paths(tmp_knowledge_dir, sample_entry_kwargs):
    """Different entries → different IDs."""
    from src.storage import entry_id, save_entry

    a = save_entry(**{**sample_entry_kwargs, "title": "Entry A"}, update_index=False)
    b = save_entry(**{**sample_entry_kwargs, "title": "Entry B"}, update_index=False)
    assert entry_id(a) != entry_id(b)


def test_parse_entry_metadata_populates_id(tmp_knowledge_dir, sample_entry_kwargs):
    """_parse_entry_metadata now surfaces the ID in every entry dict."""
    from src.storage import _parse_entry_metadata, save_entry

    path = save_entry(**sample_entry_kwargs, update_index=False)
    info = _parse_entry_metadata(path)
    assert info is not None
    assert "id" in info
    assert len(info["id"]) == 8


def test_find_entry_by_id_returns_match(tmp_knowledge_dir, sample_entry_kwargs):
    """find_entry_by_id resolves a known ID back to the entry dict."""
    from src.storage import (
        _invalidate_entry_cache,
        entry_id,
        find_entry_by_id,
        save_entry,
    )

    path = save_entry(**sample_entry_kwargs, update_index=False)
    _invalidate_entry_cache()

    target_id = entry_id(path)
    found = find_entry_by_id(target_id)
    assert found is not None
    assert found["path"] == str(path)
    assert found["id"] == target_id


def test_find_entry_by_id_returns_none_for_unknown(tmp_knowledge_dir):
    """Nonexistent ID → None (never raises)."""
    from src.storage import find_entry_by_id

    assert find_entry_by_id("deadbeef") is None
    assert find_entry_by_id("") is None


def test_read_entry_markdown_reads_full_content(tmp_knowledge_dir, sample_entry_kwargs):
    """read_entry_markdown returns the complete file content, not just the header."""
    from src.storage import read_entry_markdown, save_entry

    path = save_entry(**sample_entry_kwargs, update_index=False)
    content = read_entry_markdown(path)

    # Every section the writer produced should be present
    assert "## Summary" in content
    assert "## Detailed Notes" in content


def test_get_source_text_path_returns_sibling(tmp_knowledge_dir, sample_entry_kwargs):
    """get_source_text_path maps a .md path to its .source.txt sibling."""
    from src.storage import get_source_text_path, save_entry

    path = save_entry(
        **{**sample_entry_kwargs, "raw_text": "hello raw world"},
        update_index=False,
    )
    sibling = get_source_text_path(path)
    assert sibling.exists()
    assert sibling.read_text(encoding="utf-8") == "hello raw world"
    # Sibling is "<md-stem>.source.txt" — lives in the same directory
    assert sibling.name == path.stem + ".source.txt"
    assert sibling.parent == path.parent
