"""Tests for src.onboarding — pure state machine + per-user draft commit."""

from __future__ import annotations

import pytest
import yaml


# ── Step order sanity ─────────────────────────────────────────────────────


def test_step_order_is_deterministic():
    from src.onboarding import STEPS
    assert STEPS[0] == "lang"
    assert STEPS[1] == "welcome"
    assert STEPS[-1] == "done"


def test_step_key_returns_keys_by_index():
    from src.onboarding import STEPS, step_key
    for i, key in enumerate(STEPS):
        assert step_key(i) == key


def test_step_key_out_of_range_returns_none():
    from src.onboarding import STEPS, step_key
    assert step_key(-1) is None
    assert step_key(len(STEPS)) is None
    assert step_key(999) is None


def test_next_step_advances_within_range():
    from src.onboarding import STEPS, next_step
    assert next_step(0) == 1
    assert next_step(1) == 2
    assert next_step(len(STEPS) - 1) == len(STEPS) - 1


def test_callback_steps_set():
    from src.onboarding import CALLBACK_STEPS
    assert "lang" in CALLBACK_STEPS
    assert "welcome" in CALLBACK_STEPS
    assert "categories" in CALLBACK_STEPS
    assert "channels" in CALLBACK_STEPS
    assert "persona" not in CALLBACK_STEPS
    assert "learning" not in CALLBACK_STEPS


def test_optional_steps_set():
    from src.onboarding import OPTIONAL_STEPS
    assert "notinterested" in OPTIONAL_STEPS
    assert "persona" not in OPTIONAL_STEPS


# ── parse_multiline ──────────────────────────────────────────────────────


def test_parse_multiline_splits_and_trims():
    from src.onboarding import parse_multiline
    text = "  docker  \nn8n\n\n  claude-code\n"
    assert parse_multiline(text) == ["docker", "n8n", "claude-code"]


def test_parse_multiline_empty_input():
    from src.onboarding import parse_multiline
    assert parse_multiline("") == []
    assert parse_multiline("   \n\n  ") == []


# ── new_draft ────────────────────────────────────────────────────────────


def test_new_draft_has_empty_fields():
    from src.onboarding import new_draft
    d = new_draft()
    assert d["language"] == "en"
    assert d["persona"] == ""
    assert d["actively_learning"] == []
    assert d["known_stack"] == []
    assert d["not_interested_in"] == []
    assert d["selected_categories"] == {}
    assert d["selected_channels"] == []


# ── apply_draft ──────────────────────────────────────────────────────────


def _sample_draft() -> dict:
    return {
        "language": "en",
        "persona": "Senior DevOps consultant",
        "actively_learning": ["AI agents", "RAG"],
        "known_stack": ["docker", "n8n"],
        "already_comfortable_with": ["docker", "n8n"],
        "not_interested_in": ["crypto"],
        "selected_categories": {
            "ai-agents": "AI Agents description",
            "devops-selfhost": "DevOps description",
        },
        "selected_channels": [],
    }


def test_apply_draft_writes_profile(tmp_knowledge_dir, chat_id):
    from src.config import user_profile_file
    from src.onboarding import apply_draft
    from src.profile import init_profile, load_profile

    init_profile(chat_id)
    summary = apply_draft(chat_id, _sample_draft())

    assert summary["profile_saved"] == 1
    assert user_profile_file(chat_id).exists()

    profile = load_profile(chat_id)
    assert profile["language"] == "en"
    assert profile["persona"] == "Senior DevOps consultant"
    assert profile["actively_learning"] == ["AI agents", "RAG"]
    assert profile["known_stack"] == ["docker", "n8n"]
    assert profile["not_interested_in"] == ["crypto"]


def test_apply_draft_creates_selected_categories(tmp_knowledge_dir, chat_id):
    from src.config import user_categories_file
    from src.onboarding import apply_draft
    from src.profile import init_profile

    init_profile(chat_id)
    summary = apply_draft(chat_id, _sample_draft())

    assert summary["categories_added"] == 2
    path = user_categories_file(chat_id)
    assert path.exists()
    data = yaml.safe_load(path.read_text("utf-8"))
    assert "ai-agents" in data
    assert "devops-selfhost" in data


def test_apply_draft_writes_channels_when_selected(tmp_knowledge_dir, chat_id):
    from src.config import user_channels_file
    from src.onboarding import apply_draft
    from src.profile import init_profile

    init_profile(chat_id)
    draft = _sample_draft()
    draft["selected_channels"] = [
        {"name": "FakeCh", "id": "UC_fake", "category": "ai-agents", "enabled": True},
    ]
    summary = apply_draft(chat_id, draft)

    assert summary["channels_added"] == 1
    data = yaml.safe_load(user_channels_file(chat_id).read_text("utf-8"))
    assert data["channels"][0]["id"] == "UC_fake"


def test_apply_draft_skips_channels_when_none_selected(tmp_knowledge_dir, chat_id):
    """No channels selected → channels.yml is not touched."""
    from src.config import user_channels_file
    from src.onboarding import apply_draft
    from src.profile import init_profile

    init_profile(chat_id)
    path = user_channels_file(chat_id)
    assert not path.exists()
    apply_draft(chat_id, _sample_draft())
    assert not path.exists()


def test_apply_draft_idempotent_for_channels(tmp_knowledge_dir, chat_id):
    """Re-running apply_draft with the same channel doesn't duplicate it."""
    from src.config import user_channels_file
    from src.onboarding import apply_draft
    from src.profile import init_profile

    init_profile(chat_id)
    ch = {"name": "FakeCh", "id": "UC_fake", "category": "ai-agents", "enabled": True}
    draft = {**_sample_draft(), "selected_channels": [ch]}

    apply_draft(chat_id, draft)
    apply_draft(chat_id, draft)

    data = yaml.safe_load(user_channels_file(chat_id).read_text("utf-8"))
    ids = [c["id"] for c in data["channels"]]
    assert ids.count("UC_fake") == 1


def test_apply_draft_normalizes_unknown_language(tmp_knowledge_dir, chat_id):
    from src.onboarding import apply_draft
    from src.profile import init_profile, load_profile

    init_profile(chat_id)
    draft = _sample_draft()
    draft["language"] = "klingon"
    apply_draft(chat_id, draft)
    assert load_profile(chat_id)["language"] == "en"


def test_apply_draft_preserves_russian_selection(tmp_knowledge_dir, chat_id):
    from src.onboarding import apply_draft
    from src.profile import init_profile, load_profile

    init_profile(chat_id)
    draft = _sample_draft()
    draft["language"] = "ru"
    apply_draft(chat_id, draft)
    assert load_profile(chat_id)["language"] == "ru"


def test_apply_draft_handles_empty_draft(tmp_knowledge_dir, chat_id):
    from src.onboarding import apply_draft, new_draft
    from src.profile import init_profile, load_profile

    init_profile(chat_id)
    apply_draft(chat_id, new_draft())

    profile = load_profile(chat_id)
    assert profile["language"] == "en"
    assert profile["persona"] == ""
    assert profile["known_stack"] == []
