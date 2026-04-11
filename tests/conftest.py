"""Shared fixtures for PulseBrain tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Filesystem isolation: redirect all config paths to tmp_path
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_knowledge_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect KNOWLEDGE_DIR, DATA_DIR, PROCESSED_FILE, CATEGORIES_FILE to tmp."""
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    processed = data / "processed.json"
    categories = data / "categories.yml"
    channels = tmp_path / "channels.yml"

    targets = {
        "KNOWLEDGE_DIR": knowledge,
        "DATA_DIR": data,
        "PROCESSED_FILE": processed,
        "CATEGORIES_FILE": categories,
        "CHANNELS_FILE": channels,
    }

    # Patch on src.config AND every module that imported at load time
    import src.config
    import src.storage

    for attr, val in targets.items():
        monkeypatch.setattr(src.config, attr, val)
        if hasattr(src.storage, attr):
            monkeypatch.setattr(src.storage, attr, val)

    # Reset storage caches so tests start clean
    if hasattr(src.storage, "_processed_cache"):
        monkeypatch.setattr(src.storage, "_processed_cache", None)
    if hasattr(src.storage, "_entry_cache"):
        monkeypatch.setattr(src.storage, "_entry_cache", None)

    return tmp_path


# ---------------------------------------------------------------------------
# OpenAI / OpenRouter mock
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_openai_client():
    """Return a factory that builds a mock openai.OpenAI client.

    Usage:
        client = mock_openai_client('{"key": "value"}')
    The client's chat.completions.create() will return that content.
    """
    def _factory(response_content: str = '{}'):
        mock_choice = MagicMock()
        mock_choice.message.content = response_content
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        client = MagicMock()
        client.chat.completions.create.return_value = mock_response
        return client

    return _factory


# ---------------------------------------------------------------------------
# Telegram mocks
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_telegram_update():
    """Factory for telegram.Update mocks.

    Usage:
        update = mock_telegram_update(chat_id=12345, text="hello")
    """
    def _factory(chat_id: int = 12345, text: str = "", callback_data: str | None = None):
        update = MagicMock()
        update.effective_chat.id = chat_id
        update.message.text = text
        update.message.reply_text = AsyncMock(return_value=MagicMock(
            edit_text=AsyncMock(),
        ))

        if callback_data is not None:
            update.callback_query = MagicMock()
            update.callback_query.data = callback_data
            update.callback_query.answer = AsyncMock()
            update.callback_query.edit_message_reply_markup = AsyncMock()
            update.callback_query.message.reply_text = AsyncMock()
        else:
            update.callback_query = None

        return update

    return _factory


@pytest.fixture()
def mock_telegram_context():
    """Factory for ContextTypes.DEFAULT_TYPE mocks."""
    def _factory(args: list[str] | None = None, user_data: dict | None = None):
        ctx = MagicMock()
        ctx.args = args or []
        ctx.user_data = user_data if user_data is not None else {}
        return ctx

    return _factory


# ---------------------------------------------------------------------------
# Sample data helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_entry_kwargs() -> dict[str, Any]:
    """Valid kwargs for storage.save_entry."""
    return {
        "title": "Test Video Title",
        "source_url": "https://www.youtube.com/watch?v=abc123",
        "source_type": "youtube_video",
        "source_name": "TestChannel",
        "date_str": "2025-06-15",
        "category": "ai-agents",
        "relevance": 8,
        "topics": ["ai", "agents"],
        "summary_bullets": ["Bullet one", "Bullet two"],
        "detailed_notes": "Detailed notes paragraph.",
        "key_insights": ["Insight one"],
        "action_items": ["Action one"],
    }
