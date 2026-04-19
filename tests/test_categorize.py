"""Tests for src.categorize — per-user slug validation, LLM fallback."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _mock_llm_response(text: str):
    """Build a mock OpenAI client returning given text."""
    mock_choice = MagicMock()
    mock_choice.message.content = text
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    client = MagicMock()
    client.chat.completions.create.return_value = mock_response
    return client


def test_categorize_returns_existing_category(tmp_knowledge_dir, chat_id):
    """Known slug returned by LLM → (slug, False)."""
    from src.categorize import categorize_content
    from src.config import ensure_user_dirs

    ensure_user_dirs(chat_id)
    with patch("src.categorize.openai.OpenAI", return_value=_mock_llm_response("ai-agents")):
        slug, is_new = categorize_content(chat_id, "AI Agents Tutorial", "content here")
        assert slug == "ai-agents"
        assert is_new is False


def test_categorize_returns_new_valid_slug(tmp_knowledge_dir, chat_id):
    """Unknown but valid slug → (slug, True)."""
    from src.categorize import categorize_content
    from src.config import ensure_user_dirs

    ensure_user_dirs(chat_id)
    with patch("src.categorize.openai.OpenAI", return_value=_mock_llm_response("machine-learning")):
        slug, is_new = categorize_content(chat_id, "ML Tutorial", "content")
        assert slug == "machine-learning"
        assert is_new is True


def test_categorize_rejects_long_slug(tmp_knowledge_dir, chat_id):
    """Slug > 30 chars → fallback to ai-news."""
    from src.categorize import categorize_content
    from src.config import ensure_user_dirs

    ensure_user_dirs(chat_id)
    long_slug = "a" * 50
    with patch("src.categorize.openai.OpenAI", return_value=_mock_llm_response(long_slug)):
        slug, is_new = categorize_content(chat_id, "Title", "content")
        assert slug == "ai-news"
        assert is_new is False


def test_categorize_rejects_non_alnum_slug(tmp_knowledge_dir, chat_id):
    """Slug with special chars → fallback."""
    from src.categorize import categorize_content
    from src.config import ensure_user_dirs

    ensure_user_dirs(chat_id)
    with patch("src.categorize.openai.OpenAI", return_value=_mock_llm_response("cat/../hack")):
        slug, is_new = categorize_content(chat_id, "Title", "content")
        assert slug == "ai-news"
        assert is_new is False


def test_categorize_fallback_on_api_error(tmp_knowledge_dir, chat_id):
    """API exception → ('ai-news', False)."""
    from src.categorize import categorize_content
    from src.config import ensure_user_dirs

    ensure_user_dirs(chat_id)
    client = MagicMock()
    client.chat.completions.create.side_effect = Exception("API down")
    with patch("src.categorize.openai.OpenAI", return_value=client):
        slug, is_new = categorize_content(chat_id, "Title", "content")
        assert slug == "ai-news"
        assert is_new is False


# ── Auto-merge (pure — no chat_id) ─────────────────────────────────────────


def test_auto_merge_returns_existing_for_near_duplicate():
    from src.categorize import _auto_merge

    existing = {"ai-agents": "AI Agents", "wordpress": "WordPress"}
    assert _auto_merge("ai-agent", existing) == "ai-agents"


def test_auto_merge_returns_none_for_dissimilar_slug():
    from src.categorize import _auto_merge

    existing = {"ai-agents": "AI Agents", "wordpress": "WordPress"}
    assert _auto_merge("robotics", existing) is None


def test_auto_merge_picks_closest_match():
    from src.categorize import _auto_merge

    existing = {
        "ai-agents": "AI Agents",
        "ai-news": "AI News",
        "wordpress": "WP",
    }
    assert _auto_merge("ai-agent", existing) == "ai-agents"


def test_auto_merge_empty_categories_returns_none():
    from src.categorize import _auto_merge

    assert _auto_merge("anything", {}) is None


def test_categorize_llm_near_duplicate_is_auto_merged(tmp_knowledge_dir, chat_id):
    from src.categorize import categorize_content
    from src.config import ensure_user_dirs

    ensure_user_dirs(chat_id)
    client = MagicMock()
    choice = MagicMock()
    choice.message.content = "ai-agent"
    resp = MagicMock()
    resp.choices = [choice]
    client.chat.completions.create.return_value = resp

    with patch("src.categorize.openai.OpenAI", return_value=client):
        slug, is_new = categorize_content(chat_id, "AI Agents Tutorial", "some content")

    assert slug == "ai-agents"
    assert is_new is False


def test_categorize_llm_genuinely_new_slug_is_new(tmp_knowledge_dir, chat_id):
    from src.categorize import categorize_content
    from src.config import ensure_user_dirs

    ensure_user_dirs(chat_id)
    client = MagicMock()
    choice = MagicMock()
    choice.message.content = "robotics"
    resp = MagicMock()
    resp.choices = [choice]
    client.chat.completions.create.return_value = resp

    with patch("src.categorize.openai.OpenAI", return_value=client):
        slug, is_new = categorize_content(chat_id, "Robot Arms Tutorial", "content")

    assert slug == "robotics"
    assert is_new is True
