"""Tests for src.profile — per-user profile load/save with defaults + language."""

from __future__ import annotations

import threading

import pytest
import yaml


# ── init_profile + defaults ──────────────────────────────────────────────


def test_init_profile_on_missing_file_does_not_write(tmp_knowledge_dir, chat_id):
    """First-run behavior: no file → in-memory defaults, nothing on disk yet."""
    from src.config import user_profile_file
    from src.profile import init_profile, load_profile

    init_profile(chat_id)
    assert not user_profile_file(chat_id).exists()

    profile = load_profile(chat_id)
    assert profile["language"] == "en"
    assert profile["persona"] == ""
    assert profile["known_stack"] == []
    assert profile["actively_learning"] == []


def test_default_profile_language_is_en(tmp_knowledge_dir, chat_id):
    from src.profile import init_profile, load_profile

    init_profile(chat_id)
    assert load_profile(chat_id)["language"] == "en"


def test_load_profile_backfills_missing_keys(tmp_knowledge_dir, chat_id):
    """A partial YAML file is merged with defaults on read."""
    from src.config import ensure_user_dirs, user_profile_file
    from src.profile import init_profile, load_profile

    ensure_user_dirs(chat_id)
    user_profile_file(chat_id).write_text(
        "language: en\npersona: Partial persona\n", encoding="utf-8"
    )

    init_profile(chat_id)
    profile = load_profile(chat_id)
    assert profile["language"] == "en"
    assert profile["persona"] == "Partial persona"
    assert profile["known_stack"] == []
    assert profile["actively_learning"] == []
    assert profile["not_interested_in"] == []


def test_load_profile_falls_back_on_corrupt_yaml(tmp_knowledge_dir, chat_id):
    from src.config import ensure_user_dirs, user_profile_file
    from src.profile import init_profile, load_profile

    ensure_user_dirs(chat_id)
    user_profile_file(chat_id).write_text("NOT VALID: YAML: [{{{", encoding="utf-8")

    init_profile(chat_id)
    profile = load_profile(chat_id)
    assert profile["language"] == "en"


def test_load_profile_falls_back_on_non_mapping(tmp_knowledge_dir, chat_id):
    """A YAML file containing a list (not a dict) is treated as invalid."""
    from src.config import ensure_user_dirs, user_profile_file
    from src.profile import init_profile, load_profile

    ensure_user_dirs(chat_id)
    user_profile_file(chat_id).write_text("- just\n- a\n- list\n", encoding="utf-8")

    init_profile(chat_id)
    assert load_profile(chat_id)["language"] == "en"


# ── save_profile ─────────────────────────────────────────────────────────


def test_save_profile_writes_yaml(tmp_knowledge_dir, chat_id):
    from src.config import user_profile_file
    from src.profile import init_profile, load_profile, save_profile

    init_profile(chat_id)
    save_profile(chat_id, {
        "language": "en",
        "persona": "Senior dev",
        "known_stack": ["docker", "n8n"],
        "actively_learning": ["AI agents"],
    })

    path = user_profile_file(chat_id)
    assert path.exists()
    data = yaml.safe_load(path.read_text("utf-8"))
    assert data["language"] == "en"
    assert data["persona"] == "Senior dev"
    assert data["known_stack"] == ["docker", "n8n"]
    assert data["actively_learning"] == ["AI agents"]
    assert data["not_interested_in"] == []

    profile = load_profile(chat_id)
    assert profile["persona"] == "Senior dev"


def test_save_profile_atomic_no_tmp_leak(tmp_knowledge_dir, chat_id):
    from src.config import user_profile_file
    from src.profile import init_profile, save_profile

    init_profile(chat_id)
    save_profile(chat_id, {"language": "ru", "persona": "X"})
    assert not user_profile_file(chat_id).with_suffix(".tmp").exists()


def test_save_profile_roundtrip_preserves_unicode(tmp_knowledge_dir, chat_id):
    from src.profile import init_profile, load_profile, save_profile

    init_profile(chat_id)
    save_profile(chat_id, {
        "language": "ru",
        "persona": "Старший IT-консультант / DevOps",
        "actively_learning": ["AI агенты", "RAG"],
    })

    profile = load_profile(chat_id)
    assert profile["persona"] == "Старший IT-консультант / DevOps"
    assert "AI агенты" in profile["actively_learning"]


# ── load_profile returns a copy ──────────────────────────────────────────


def test_load_profile_returns_independent_copy(tmp_knowledge_dir, chat_id):
    from src.profile import init_profile, load_profile

    init_profile(chat_id)
    a = load_profile(chat_id)
    a["language"] = "de"

    b = load_profile(chat_id)
    assert b["language"] == "en"


# ── get_language ──────────────────────────────────────────────────────────


def test_get_language_default_en(tmp_knowledge_dir, chat_id):
    from src.profile import get_language, init_profile

    init_profile(chat_id)
    assert get_language(chat_id) == "en"


def test_get_language_reads_saved_value(tmp_knowledge_dir, chat_id):
    from src.profile import get_language, init_profile, save_profile

    init_profile(chat_id)
    save_profile(chat_id, {"language": "de", "persona": "test"})
    assert get_language(chat_id) == "de"


def test_get_language_reads_russian_profile(tmp_knowledge_dir, chat_id):
    from src.profile import get_language, init_profile, save_profile

    init_profile(chat_id)
    save_profile(chat_id, {"language": "ru", "persona": "test"})
    assert get_language(chat_id) == "ru"


def test_get_language_normalizes_unknown_to_en(tmp_knowledge_dir, chat_id):
    from src.profile import get_language, init_profile, save_profile

    init_profile(chat_id)
    save_profile(chat_id, {"language": "xx", "persona": "test"})
    assert get_language(chat_id) == "en"


# ── profile_exists ───────────────────────────────────────────────────────


def test_profile_exists_false_on_fresh(tmp_knowledge_dir, chat_id):
    from src.profile import init_profile, profile_exists

    init_profile(chat_id)
    assert profile_exists(chat_id) is False


def test_profile_exists_true_after_save(tmp_knowledge_dir, chat_id):
    from src.profile import init_profile, profile_exists, save_profile

    init_profile(chat_id)
    save_profile(chat_id, {"language": "ru", "persona": "X"})
    assert profile_exists(chat_id) is True


# ── Concurrency ──────────────────────────────────────────────────────────


def test_concurrent_save_profile(tmp_knowledge_dir, chat_id):
    """10 threads saving different profiles — no file corruption."""
    from src.profile import init_profile, load_profile, save_profile

    init_profile(chat_id)

    def save(i: int):
        save_profile(chat_id, {
            "language": "en" if i % 2 == 0 else "ru",
            "persona": f"persona-{i}",
        })

    threads = [threading.Thread(target=save, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = load_profile(chat_id)
    assert final["persona"].startswith("persona-")
    assert final["language"] in ("ru", "en")


# ── build_relevance_context ──────────────────────────────────────────────


def test_build_relevance_context_empty_base(tmp_knowledge_dir, chat_id):
    from src.profile import build_relevance_context, init_profile

    init_profile(chat_id)
    ctx = build_relevance_context(chat_id)

    assert ctx["language"] == "en"
    assert ctx["top_categories"] == []
    assert ctx["top_topics"] == []
    assert ctx["recent_approved_avg"] == 0.0
    assert ctx["recently_rejected_titles"] == []


def test_build_relevance_context_merges_profile_fields(tmp_knowledge_dir, chat_id):
    from src.profile import build_relevance_context, init_profile, save_profile

    init_profile(chat_id)
    save_profile(chat_id, {
        "language": "en",
        "persona": "Senior DevOps",
        "skill_level": "senior",
        "known_stack": ["docker"],
        "actively_learning": ["AI agents"],
        "not_interested_in": ["crypto"],
    })

    ctx = build_relevance_context(chat_id)
    assert ctx["language"] == "en"
    assert ctx["persona"] == "Senior DevOps"
    assert ctx["known_stack"] == ["docker"]
    assert ctx["actively_learning"] == ["AI agents"]
    assert ctx["not_interested_in"] == ["crypto"]


def test_build_relevance_context_top_categories_from_base(tmp_knowledge_dir, chat_id, sample_entry_kwargs):
    from src.profile import build_relevance_context, init_profile
    from src.storage import _invalidate_entry_cache, init_processed, save_entry

    init_processed(chat_id)
    init_profile(chat_id)

    save_entry(chat_id, **{**sample_entry_kwargs, "source_url": "u1", "title": "T1"})
    save_entry(chat_id, **{**sample_entry_kwargs, "source_url": "u2", "title": "T2"})
    save_entry(chat_id, **{
        **sample_entry_kwargs, "source_url": "u3", "title": "T3",
        "category": "wordpress",
    })
    _invalidate_entry_cache(chat_id)

    ctx = build_relevance_context(chat_id)
    cats = dict(ctx["top_categories"])
    assert cats["ai-agents"] == 2
    assert cats["wordpress"] == 1


def test_build_relevance_context_top_topics(tmp_knowledge_dir, chat_id, sample_entry_kwargs):
    from src.profile import build_relevance_context, init_profile
    from src.storage import _invalidate_entry_cache, init_processed, save_entry

    init_processed(chat_id)
    init_profile(chat_id)

    save_entry(chat_id, **{**sample_entry_kwargs, "source_url": "u1", "title": "T1",
                  "topics": ["docker", "ai"]})
    save_entry(chat_id, **{**sample_entry_kwargs, "source_url": "u2", "title": "T2",
                  "topics": ["docker", "n8n"]})
    save_entry(chat_id, **{**sample_entry_kwargs, "source_url": "u3", "title": "T3",
                  "topics": ["ai"]})
    _invalidate_entry_cache(chat_id)

    ctx = build_relevance_context(chat_id)
    topics = dict(ctx["top_topics"])
    assert topics["docker"] == 2
    assert topics["ai"] == 2
    assert topics["n8n"] == 1


def test_build_relevance_context_recent_avg(tmp_knowledge_dir, chat_id, sample_entry_kwargs):
    from src.profile import build_relevance_context, init_profile
    from src.storage import _invalidate_entry_cache, init_processed, save_entry

    init_processed(chat_id)
    init_profile(chat_id)

    save_entry(chat_id, **{**sample_entry_kwargs, "source_url": "u1", "title": "T1",
                  "relevance": 8})
    save_entry(chat_id, **{**sample_entry_kwargs, "source_url": "u2", "title": "T2",
                  "relevance": 6})
    save_entry(chat_id, **{**sample_entry_kwargs, "source_url": "u3", "title": "T3",
                  "relevance": 10})
    _invalidate_entry_cache(chat_id)

    ctx = build_relevance_context(chat_id)
    assert ctx["recent_approved_avg"] == 8.0


def test_build_relevance_context_rejected_titles(tmp_knowledge_dir, chat_id, sample_pending_kwargs):
    from src.pending import init_pending, reject_pending, stage_pending
    from src.profile import build_relevance_context, init_profile
    from src.storage import init_processed

    init_processed(chat_id)
    init_pending(chat_id)
    init_profile(chat_id)

    reject_pending(chat_id, stage_pending(chat_id, **{
        **sample_pending_kwargs, "content_id": "yt:spam1", "title": "Spam video"
    }), reason="low_relevance")

    ctx = build_relevance_context(chat_id)
    assert "Spam video" in ctx["recently_rejected_titles"]


def test_build_relevance_context_handles_storage_exception(tmp_knowledge_dir, chat_id):
    from unittest.mock import patch

    from src.profile import build_relevance_context, init_profile, save_profile

    init_profile(chat_id)
    save_profile(chat_id, {"language": "en", "persona": "X"})

    with patch("src.storage._get_all_entries", side_effect=RuntimeError("boom")):
        ctx = build_relevance_context(chat_id)

    assert ctx["persona"] == "X"
    assert ctx["top_categories"] == []


# ── format_relevance_context ─────────────────────────────────────────────


def test_format_relevance_context_includes_all_filled_fields():
    from src.profile import format_relevance_context

    ctx = {
        "persona": "Senior DevOps",
        "skill_level": "senior",
        "known_stack": ["docker", "n8n"],
        "already_comfortable_with": ["git"],
        "actively_learning": ["AI agents"],
        "not_interested_in": ["crypto"],
        "top_categories": [("ai-agents", 12), ("devops", 5)],
        "top_topics": [("docker", 8), ("rag", 4)],
        "recent_approved_avg": 7.4,
        "recently_rejected_titles": ["Docker 101", "Generic listicle"],
    }
    text = format_relevance_context(ctx)

    assert "USER CONTEXT" in text
    assert "Senior DevOps" in text
    assert "docker, n8n" in text
    assert "AI agents" in text
    assert "crypto" in text
    assert "ai-agents(12)" in text
    assert "docker(8)" in text
    assert "7.4" in text
    assert "Docker 101" in text


def test_format_relevance_context_skips_empty_fields():
    from src.profile import format_relevance_context

    ctx = {
        "persona": "",
        "known_stack": [],
        "actively_learning": [],
        "not_interested_in": [],
        "top_categories": [],
        "top_topics": [],
        "recent_approved_avg": 0.0,
        "recently_rejected_titles": [],
    }
    text = format_relevance_context(ctx)
    assert text == "USER CONTEXT:"
