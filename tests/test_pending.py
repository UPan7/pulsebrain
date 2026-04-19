"""Tests for src.pending — per-user staging registry and approval lifecycle."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest


# ── stage_pending ──────────────────────────────────────────────────────────


def test_stage_pending_returns_id_and_persists(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.config import user_pending_file
    from src.pending import init_pending, stage_pending, get_pending

    init_pending(chat_id)
    pending_id = stage_pending(chat_id, **sample_pending_kwargs)

    assert isinstance(pending_id, str)
    assert len(pending_id) == 8

    entry = get_pending(chat_id, pending_id)
    assert entry is not None
    assert entry["title"] == "Test Video Title"
    assert entry["category"] == "ai-agents"
    assert entry["content_id"] == "yt:abc123"
    assert "created_at" in entry

    path = user_pending_file(chat_id)
    assert path.exists()
    data = json.loads(path.read_text("utf-8"))
    assert pending_id in data


def test_stage_pending_id_is_stable_for_same_content_id(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.pending import init_pending, stage_pending

    init_pending(chat_id)
    id1 = stage_pending(chat_id, **sample_pending_kwargs)
    id2 = stage_pending(chat_id, **sample_pending_kwargs)
    assert id1 == id2


def test_stage_pending_rejects_invalid_category(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.pending import init_pending, stage_pending

    init_pending(chat_id)
    with pytest.raises(ValueError, match="Invalid category"):
        stage_pending(chat_id, **{**sample_pending_kwargs, "category": "../etc"})


def test_stage_pending_atomic_write(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.config import user_pending_file
    from src.pending import init_pending, stage_pending

    init_pending(chat_id)
    stage_pending(chat_id, **sample_pending_kwargs)
    assert not user_pending_file(chat_id).with_suffix(".tmp").exists()


def test_stage_pending_supports_web_article_fields(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.pending import init_pending, stage_pending, get_pending

    init_pending(chat_id)
    web_kwargs = {
        **sample_pending_kwargs,
        "source_type": "web_article",
        "content_id": "web:abcdef",
        "author": "Jane Doe",
        "sitename": "blog.example.com",
    }
    pending_id = stage_pending(chat_id, **web_kwargs)

    entry = get_pending(chat_id, pending_id)
    assert entry["author"] == "Jane Doe"
    assert entry["sitename"] == "blog.example.com"


def test_stage_pending_supports_unknown_source_type(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.pending import init_pending, stage_pending, get_pending

    init_pending(chat_id)
    pdf_kwargs = {
        **sample_pending_kwargs,
        "source_type": "pdf_document",
        "content_id": "pdf:xyz",
    }
    pending_id = stage_pending(chat_id, **pdf_kwargs)

    entry = get_pending(chat_id, pending_id)
    assert entry["source_type"] == "pdf_document"


# ── get_pending / list_pending ─────────────────────────────────────────────


def test_get_pending_returns_none_for_unknown(tmp_knowledge_dir, chat_id):
    from src.pending import init_pending, get_pending

    init_pending(chat_id)
    assert get_pending(chat_id, "nonexistent") is None


def test_list_pending_sorted_newest_first(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    import time
    from src.pending import init_pending, stage_pending, list_pending

    init_pending(chat_id)
    stage_pending(chat_id, **{**sample_pending_kwargs, "content_id": "yt:first"})
    time.sleep(0.01)
    stage_pending(chat_id, **{**sample_pending_kwargs, "content_id": "yt:second"})

    entries = list_pending(chat_id)
    assert len(entries) == 2
    assert entries[0]["content_id"] == "yt:second"
    assert entries[1]["content_id"] == "yt:first"


def test_list_pending_empty(tmp_knowledge_dir, chat_id):
    from src.pending import init_pending, list_pending

    init_pending(chat_id)
    assert list_pending(chat_id) == []


# ── update_pending_category ────────────────────────────────────────────────


def test_update_pending_category_changes_slug(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.pending import init_pending, stage_pending, get_pending, update_pending_category

    init_pending(chat_id)
    pending_id = stage_pending(chat_id, **sample_pending_kwargs)
    assert update_pending_category(chat_id, pending_id, "robotics", is_new_category=True) is True

    entry = get_pending(chat_id, pending_id)
    assert entry["category"] == "robotics"
    assert entry["is_new_category"] is True


def test_update_pending_category_returns_false_for_unknown(tmp_knowledge_dir, chat_id):
    from src.pending import init_pending, update_pending_category

    init_pending(chat_id)
    assert update_pending_category(chat_id, "nope", "ai-news") is False


def test_update_pending_category_rejects_invalid_slug(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.pending import init_pending, stage_pending, update_pending_category

    init_pending(chat_id)
    pending_id = stage_pending(chat_id, **sample_pending_kwargs)
    with pytest.raises(ValueError):
        update_pending_category(chat_id, pending_id, "../etc")


# ── commit_pending ─────────────────────────────────────────────────────────


def test_commit_pending_writes_file_and_marks_processed(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.pending import init_pending, stage_pending, commit_pending, get_pending
    from src.storage import init_processed, is_processed

    init_processed(chat_id)
    init_pending(chat_id)
    pending_id = stage_pending(chat_id, **sample_pending_kwargs)

    file_path = commit_pending(chat_id, pending_id)
    assert file_path is not None
    assert Path(file_path).exists()

    assert is_processed(chat_id, "yt:abc123")
    assert get_pending(chat_id, pending_id) is None


def test_commit_pending_returns_none_for_unknown(tmp_knowledge_dir, chat_id):
    from src.pending import init_pending, commit_pending

    init_pending(chat_id)
    assert commit_pending(chat_id, "nope") is None


def test_commit_pending_uses_updated_category(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.pending import init_pending, stage_pending, update_pending_category, commit_pending
    from src.storage import init_processed

    init_processed(chat_id)
    init_pending(chat_id)
    pending_id = stage_pending(chat_id, **sample_pending_kwargs)
    update_pending_category(chat_id, pending_id, "robotics")
    file_path = commit_pending(chat_id, pending_id)

    # Path separator may be / or \\ depending on platform
    assert "robotics" in str(file_path)
    content = Path(file_path).read_text("utf-8")
    assert "**Category:** robotics" in content


# ── reject_pending ─────────────────────────────────────────────────────────


def test_reject_pending_drops_entry_and_marks_rejected(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.pending import init_pending, stage_pending, reject_pending, get_pending
    from src.storage import init_processed, is_processed

    init_processed(chat_id)
    init_pending(chat_id)
    pending_id = stage_pending(chat_id, **sample_pending_kwargs)

    assert reject_pending(chat_id, pending_id) is True
    assert get_pending(chat_id, pending_id) is None
    assert is_processed(chat_id, "yt:abc123")

    import src.storage
    assert src.storage._processed_caches[chat_id]["yt:abc123"]["status"] == "rejected"


def test_reject_pending_returns_false_for_unknown(tmp_knowledge_dir, chat_id):
    from src.pending import init_pending, reject_pending

    init_pending(chat_id)
    assert reject_pending(chat_id, "nope") is False


def test_reject_pending_does_not_create_file(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.config import user_knowledge_dir
    from src.pending import init_pending, stage_pending, reject_pending
    from src.storage import init_processed

    init_processed(chat_id)
    init_pending(chat_id)
    pending_id = stage_pending(chat_id, **sample_pending_kwargs)
    reject_pending(chat_id, pending_id)

    root = user_knowledge_dir(chat_id)
    md_files = list(root.rglob("*.md")) if root.exists() else []
    assert md_files == []


# ── Concurrency / persistence ──────────────────────────────────────────────


def test_concurrent_stage_pending(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    """10 threads staging different IDs — all entries survive."""
    from src.pending import init_pending, stage_pending, list_pending

    init_pending(chat_id)

    def stage(i: int):
        kwargs = {**sample_pending_kwargs, "content_id": f"yt:t{i}",
                  "title": f"Title {i}"}
        stage_pending(chat_id, **kwargs)

    threads = [threading.Thread(target=stage, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(list_pending(chat_id)) == 10


def test_pending_survives_corrupt_json(tmp_knowledge_dir, chat_id):
    from src.config import ensure_user_dirs, user_pending_file
    from src.pending import init_pending, list_pending

    ensure_user_dirs(chat_id)
    user_pending_file(chat_id).write_text("NOT JSON {{{", encoding="utf-8")
    init_pending(chat_id)
    assert list_pending(chat_id) == []


def test_load_pending_at_startup(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.config import ensure_user_dirs, user_pending_file
    from src.pending import init_pending, get_pending

    ensure_user_dirs(chat_id)
    user_pending_file(chat_id).write_text(
        json.dumps({"abc12345": {**sample_pending_kwargs, "id": "abc12345"}}),
        encoding="utf-8",
    )

    init_pending(chat_id)
    assert get_pending(chat_id, "abc12345") is not None


# ── raw_text round-trip ────────────────────────────────────────────────────


def test_stage_pending_stores_raw_text(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.pending import init_pending, stage_pending, get_pending

    init_pending(chat_id)
    transcript = "Full transcript body of the source video. " * 50
    pending_id = stage_pending(chat_id, **sample_pending_kwargs, raw_text=transcript)

    entry = get_pending(chat_id, pending_id)
    assert entry["raw_text"] == transcript


def test_stage_pending_raw_text_defaults_to_none(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.pending import init_pending, stage_pending, get_pending

    init_pending(chat_id)
    pending_id = stage_pending(chat_id, **sample_pending_kwargs)
    assert get_pending(chat_id, pending_id)["raw_text"] is None


def test_commit_pending_writes_source_sibling(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.pending import init_pending, stage_pending, commit_pending
    from src.storage import init_processed, _source_sibling_path

    init_processed(chat_id)
    init_pending(chat_id)
    transcript = "Lossless transcript saved alongside the summary."
    pending_id = stage_pending(chat_id, **sample_pending_kwargs, raw_text=transcript)
    file_path = commit_pending(chat_id, pending_id)

    sibling = _source_sibling_path(file_path)
    assert sibling.exists()
    assert sibling.read_text("utf-8") == transcript


# ── Rejected log ───────────────────────────────────────────────────────────


def test_reject_pending_writes_to_rejected_log(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.config import user_rejected_log_file
    from src.pending import init_pending, stage_pending, reject_pending
    from src.storage import init_processed

    init_processed(chat_id)
    init_pending(chat_id)
    pending_id = stage_pending(chat_id, **sample_pending_kwargs)
    reject_pending(chat_id, pending_id, reason="low_relevance")

    path = user_rejected_log_file(chat_id)
    assert path.exists()
    content = path.read_text("utf-8").strip()
    record = json.loads(content)
    assert record["pending_id"] == pending_id
    assert record["title"] == "Test Video Title"
    assert record["source_name"] == "TestChannel"
    assert record["reason"] == "low_relevance"
    assert record["relevance"] == 8


def test_reject_pending_defaults_reason_to_manual(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.config import user_rejected_log_file
    from src.pending import init_pending, stage_pending, reject_pending
    from src.storage import init_processed

    init_processed(chat_id)
    init_pending(chat_id)
    pending_id = stage_pending(chat_id, **sample_pending_kwargs)
    reject_pending(chat_id, pending_id)

    record = json.loads(user_rejected_log_file(chat_id).read_text("utf-8").strip())
    assert record["reason"] == "manual"


def test_rejected_log_is_appendonly_jsonl(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.config import user_rejected_log_file
    from src.pending import init_pending, stage_pending, reject_pending
    from src.storage import init_processed

    init_processed(chat_id)
    init_pending(chat_id)
    pid1 = stage_pending(chat_id, **sample_pending_kwargs)
    reject_pending(chat_id, pid1, reason="manual")

    pid2 = stage_pending(chat_id, **{**sample_pending_kwargs, "content_id": "yt:second", "title": "Second"})
    reject_pending(chat_id, pid2, reason="low_relevance")

    lines = user_rejected_log_file(chat_id).read_text("utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["title"] == "Test Video Title"
    assert second["title"] == "Second"
    assert second["reason"] == "low_relevance"


def test_read_rejected_log_returns_newest_first(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.pending import (
        init_pending,
        read_rejected_log,
        reject_pending,
        stage_pending,
    )
    from src.storage import init_processed

    init_processed(chat_id)
    init_pending(chat_id)
    reject_pending(chat_id, stage_pending(chat_id, **sample_pending_kwargs), reason="manual")
    reject_pending(
        chat_id,
        stage_pending(chat_id, **{**sample_pending_kwargs, "content_id": "yt:b", "title": "B"}),
        reason="low_relevance",
    )
    reject_pending(
        chat_id,
        stage_pending(chat_id, **{**sample_pending_kwargs, "content_id": "yt:c", "title": "C"}),
        reason="low_relevance",
    )

    records = read_rejected_log(chat_id, limit=10)
    assert [r["title"] for r in records] == ["C", "B", "Test Video Title"]


def test_read_rejected_log_respects_limit(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.pending import (
        init_pending,
        read_rejected_log,
        reject_pending,
        stage_pending,
    )
    from src.storage import init_processed

    init_processed(chat_id)
    init_pending(chat_id)
    for i in range(5):
        reject_pending(
            chat_id,
            stage_pending(chat_id, **{**sample_pending_kwargs, "content_id": f"yt:{i}", "title": f"T{i}"}),
            reason="manual",
        )

    records = read_rejected_log(chat_id, limit=3)
    assert len(records) == 3
    assert records[0]["title"] == "T4"


def test_read_rejected_log_missing_file_returns_empty(tmp_knowledge_dir, chat_id):
    from src.pending import read_rejected_log
    assert read_rejected_log(chat_id) == []


def test_read_rejected_log_skips_malformed_lines(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.config import user_rejected_log_file
    from src.pending import (
        init_pending,
        read_rejected_log,
        reject_pending,
        stage_pending,
    )
    from src.storage import init_processed

    init_processed(chat_id)
    init_pending(chat_id)
    reject_pending(chat_id, stage_pending(chat_id, **sample_pending_kwargs), reason="manual")

    with open(user_rejected_log_file(chat_id), "a", encoding="utf-8") as f:
        f.write("NOT JSON {{{\n")
        f.write(json.dumps({
            "ts": "2026-04-12T00:00:00Z",
            "pending_id": "xyz",
            "title": "Recovered",
            "relevance": 2,
            "reason": "manual",
        }) + "\n")

    records = read_rejected_log(chat_id, limit=10)
    assert len(records) == 2
    assert records[0]["title"] == "Recovered"
