"""Tests for src.categorize — slug validation, LLM fallback."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _isolate_categories(tmp_path, monkeypatch):
    """Isolate categories file."""
    import src.config
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(src.config, "DATA_DIR", data)
    monkeypatch.setattr(src.config, "CATEGORIES_FILE", data / "categories.yml")


def _mock_llm_response(text: str):
    """Build a mock OpenAI client returning given text."""
    mock_choice = MagicMock()
    mock_choice.message.content = text
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    client = MagicMock()
    client.chat.completions.create.return_value = mock_response
    return client


def test_categorize_returns_existing_category():
    """Known slug returned by LLM → (slug, False)."""
    from src.categorize import categorize_content

    with patch("src.categorize.openai.OpenAI", return_value=_mock_llm_response("ai-agents")):
        slug, is_new = categorize_content("AI Agents Tutorial", "content here")
        assert slug == "ai-agents"
        assert is_new is False


def test_categorize_returns_new_valid_slug():
    """Unknown but valid slug → (slug, True)."""
    from src.categorize import categorize_content

    with patch("src.categorize.openai.OpenAI", return_value=_mock_llm_response("machine-learning")):
        slug, is_new = categorize_content("ML Tutorial", "content")
        assert slug == "machine-learning"
        assert is_new is True


def test_categorize_rejects_long_slug():
    """Slug > 30 chars → fallback to ai-news."""
    from src.categorize import categorize_content

    long_slug = "a" * 50
    with patch("src.categorize.openai.OpenAI", return_value=_mock_llm_response(long_slug)):
        slug, is_new = categorize_content("Title", "content")
        assert slug == "ai-news"
        assert is_new is False


def test_categorize_rejects_non_alnum_slug():
    """Slug with special chars → fallback."""
    from src.categorize import categorize_content

    with patch("src.categorize.openai.OpenAI", return_value=_mock_llm_response("cat/../hack")):
        slug, is_new = categorize_content("Title", "content")
        assert slug == "ai-news"
        assert is_new is False


def test_categorize_fallback_on_api_error():
    """API exception → ('ai-news', False)."""
    from src.categorize import categorize_content

    client = MagicMock()
    client.chat.completions.create.side_effect = Exception("API down")
    with patch("src.categorize.openai.OpenAI", return_value=client):
        slug, is_new = categorize_content("Title", "content")
        assert slug == "ai-news"
        assert is_new is False


# ── Auto-merge (SequenceMatcher similarity) ─────────────────────────────────


def test_auto_merge_returns_existing_for_near_duplicate():
    """A one-char-off slug from the LLM should merge into the existing one."""
    from src.categorize import _auto_merge

    existing = {"ai-agents": "AI Agents", "wordpress": "WordPress"}
    # "ai-agent" (no trailing s) is ~0.94 similarity to "ai-agents"
    assert _auto_merge("ai-agent", existing) == "ai-agents"


def test_auto_merge_returns_none_for_dissimilar_slug():
    """A genuinely new topic should not be merged into anything."""
    from src.categorize import _auto_merge

    existing = {"ai-agents": "AI Agents", "wordpress": "WordPress"}
    assert _auto_merge("robotics", existing) is None


def test_auto_merge_picks_closest_match():
    """When multiple existing slugs are similar, pick the closest one."""
    from src.categorize import _auto_merge

    existing = {
        "ai-agents": "AI Agents",
        "ai-news": "AI News",
        "wordpress": "WP",
    }
    # "ai-agent" is closer to "ai-agents" than to "ai-news"
    assert _auto_merge("ai-agent", existing) == "ai-agents"


def test_auto_merge_empty_categories_returns_none():
    from src.categorize import _auto_merge

    assert _auto_merge("anything", {}) is None


def test_categorize_llm_near_duplicate_is_auto_merged():
    """End-to-end: LLM returns 'ai-agent', categorize_content returns 'ai-agents'."""
    from src.categorize import categorize_content

    client = MagicMock()
    choice = MagicMock()
    choice.message.content = "ai-agent"
    resp = MagicMock()
    resp.choices = [choice]
    client.chat.completions.create.return_value = resp

    with patch("src.categorize.openai.OpenAI", return_value=client):
        slug, is_new = categorize_content("AI Agents Tutorial", "some content")

    assert slug == "ai-agents"   # existing default category
    assert is_new is False       # merged, not created


def test_categorize_llm_genuinely_new_slug_is_new():
    """End-to-end: dissimilar slug stays as new."""
    from src.categorize import categorize_content

    client = MagicMock()
    choice = MagicMock()
    choice.message.content = "robotics"
    resp = MagicMock()
    resp.choices = [choice]
    client.chat.completions.create.return_value = resp

    with patch("src.categorize.openai.OpenAI", return_value=client):
        slug, is_new = categorize_content("Robot Arms Tutorial", "content")

    assert slug == "robotics"
    assert is_new is True
