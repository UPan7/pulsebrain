"""Tests for src.onboarding — pure state machine + draft commit."""

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
    # Clamped at last index
    assert next_step(len(STEPS) - 1) == len(STEPS) - 1


def test_callback_steps_set():
    from src.onboarding import CALLBACK_STEPS
    # These steps don't accept text input
    assert "lang" in CALLBACK_STEPS
    assert "welcome" in CALLBACK_STEPS
    assert "categories" in CALLBACK_STEPS
    assert "channels" in CALLBACK_STEPS
    # And these DO accept text
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
    assert d["language"] == "ru"
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


def test_apply_draft_writes_profile(tmp_knowledge_dir):
    import src.config
    from src.onboarding import apply_draft
    from src.profile import init_profile, load_profile

    init_profile()
    summary = apply_draft(_sample_draft())

    assert summary["profile_saved"] == 1
    assert src.config.PROFILE_FILE.exists()

    profile = load_profile()
    assert profile["language"] == "en"
    assert profile["persona"] == "Senior DevOps consultant"
    assert profile["actively_learning"] == ["AI agents", "RAG"]
    assert profile["known_stack"] == ["docker", "n8n"]
    assert profile["not_interested_in"] == ["crypto"]


def test_apply_draft_creates_selected_categories(tmp_knowledge_dir):
    import src.config
    from src.onboarding import apply_draft
    from src.profile import init_profile

    init_profile()
    summary = apply_draft(_sample_draft())

    assert summary["categories_added"] == 2
    assert src.config.CATEGORIES_FILE.exists()
    data = yaml.safe_load(src.config.CATEGORIES_FILE.read_text("utf-8"))
    assert "ai-agents" in data
    assert "devops-selfhost" in data


def test_apply_draft_writes_channels_when_selected(tmp_knowledge_dir):
    import src.config
    from src.onboarding import apply_draft
    from src.profile import init_profile

    init_profile()
    draft = _sample_draft()
    draft["selected_channels"] = [
        {"name": "FakeCh", "id": "UC_fake", "category": "ai-agents", "enabled": True},
    ]
    summary = apply_draft(draft)

    assert summary["channels_added"] == 1
    data = yaml.safe_load(src.config.CHANNELS_FILE.read_text("utf-8"))
    assert data["channels"][0]["id"] == "UC_fake"


def test_apply_draft_skips_channels_when_none_selected(tmp_knowledge_dir):
    """No channels selected → channels.yml is not touched."""
    import src.config
    from src.onboarding import apply_draft
    from src.profile import init_profile

    init_profile()
    assert not src.config.CHANNELS_FILE.exists()
    apply_draft(_sample_draft())  # no channels
    assert not src.config.CHANNELS_FILE.exists()


def test_apply_draft_idempotent_for_channels(tmp_knowledge_dir):
    """Re-running apply_draft with the same channel doesn't duplicate it."""
    import src.config
    from src.onboarding import apply_draft
    from src.profile import init_profile

    init_profile()
    ch = {"name": "FakeCh", "id": "UC_fake", "category": "ai-agents", "enabled": True}
    draft = {**_sample_draft(), "selected_channels": [ch]}

    apply_draft(draft)
    apply_draft(draft)

    data = yaml.safe_load(src.config.CHANNELS_FILE.read_text("utf-8"))
    ids = [c["id"] for c in data["channels"]]
    assert ids.count("UC_fake") == 1


def test_apply_draft_normalizes_unknown_language(tmp_knowledge_dir):
    from src.onboarding import apply_draft
    from src.profile import init_profile, load_profile

    init_profile()
    draft = _sample_draft()
    draft["language"] = "klingon"
    apply_draft(draft)
    assert load_profile()["language"] == "ru"  # fallback


def test_apply_draft_handles_empty_draft(tmp_knowledge_dir):
    """An empty-ish draft still writes a valid profile."""
    from src.onboarding import apply_draft, new_draft
    from src.profile import init_profile, load_profile

    init_profile()
    apply_draft(new_draft())

    profile = load_profile()
    assert profile["language"] == "ru"
    assert profile["persona"] == ""
    assert profile["known_stack"] == []
