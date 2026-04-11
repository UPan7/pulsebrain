"""Tests for src.telegram_bot — async handlers, truncation, auth, routing."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_update(chat_id: int = 12345, text: str = ""):
    """Build a minimal mock Update."""
    update = MagicMock()
    update.effective_chat.id = chat_id

    # reply_text returns a message with edit_text
    reply_msg = MagicMock()
    reply_msg.edit_text = AsyncMock()
    update.message.text = text
    update.message.reply_text = AsyncMock(return_value=reply_msg)
    update.callback_query = None
    return update


def _make_context(args=None, user_data=None):
    ctx = MagicMock()
    ctx.args = args or []
    ctx.user_data = user_data if user_data is not None else {}
    return ctx


# ── Authorization ──────────────────────────────────────────────────────────


def test_authorized_correct_id():
    """Correct chat ID → authorized."""
    from src.telegram_bot import _authorized

    update = _make_update(chat_id=12345)
    with patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345):
        assert _authorized(update) is True


def test_unauthorized_wrong_id():
    """Wrong chat ID → not authorized."""
    from src.telegram_bot import _authorized

    update = _make_update(chat_id=99999)
    with patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345):
        assert _authorized(update) is False


# ── Command handlers ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cmd_start_replies():
    """cmd_start sends reply with greeting."""
    from src.telegram_bot import cmd_start

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345):
        await cmd_start(update, ctx)
        update.message.reply_text.assert_called_once()
        text = update.message.reply_text.call_args[0][0]
        assert "PulseBrain" in text


# ── URL routing in handle_message ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_message_routes_youtube():
    """YouTube URL → _handle_youtube_video."""
    from src.telegram_bot import handle_message

    update = _make_update(chat_id=12345, text="https://www.youtube.com/watch?v=abc123")
    ctx = _make_context()

    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345),
        patch("src.telegram_bot._handle_youtube_video", new_callable=AsyncMock) as mock_yt,
        patch("src.telegram_bot._handle_web_article", new_callable=AsyncMock),
    ):
        await handle_message(update, ctx)
        mock_yt.assert_called_once()


@pytest.mark.asyncio
async def test_handle_message_routes_web():
    """Non-YouTube URL → _handle_web_article."""
    from src.telegram_bot import handle_message

    update = _make_update(chat_id=12345, text="https://example.com/article")
    ctx = _make_context()

    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345),
        patch("src.telegram_bot._handle_youtube_video", new_callable=AsyncMock),
        patch("src.telegram_bot._handle_web_article", new_callable=AsyncMock) as mock_web,
    ):
        await handle_message(update, ctx)
        mock_web.assert_called_once()


@pytest.mark.asyncio
async def test_handle_message_routes_question():
    """Plain text (no URL) → _handle_question."""
    from src.telegram_bot import handle_message

    update = _make_update(chat_id=12345, text="What is machine learning?")
    ctx = _make_context()

    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345),
        patch("src.telegram_bot._handle_question", new_callable=AsyncMock) as mock_q,
    ):
        await handle_message(update, ctx)
        mock_q.assert_called_once()


# ── Async non-blocking: asyncio.to_thread must be used ─────────────────────


@pytest.mark.asyncio
async def test_handle_youtube_video_uses_to_thread():
    """_handle_youtube_video wraps process_youtube_video in asyncio.to_thread."""
    from src.telegram_bot import _handle_youtube_video

    update = _make_update(chat_id=12345)
    ctx = _make_context()

    fake_result = {
        "title": "T", "channel": "C", "date": "2025-01-01",
        "category": "ai-news", "relevance": 7,
        "topics": ["t"], "summary_bullets": ["b"],
        "file_path": "/app/knowledge/ai-news/2025/01/test.md",
        "source_url": "https://youtube.com/watch?v=x", "source_type": "youtube_video",
    }

    with patch("src.telegram_bot.asyncio.to_thread", new_callable=AsyncMock, return_value=fake_result) as mock_tt:
        await _handle_youtube_video(update, ctx, "https://youtube.com/watch?v=x")
        mock_tt.assert_called_once()
        # First arg to to_thread should be the pipeline function
        args = mock_tt.call_args[0]
        from src.pipeline import process_youtube_video
        assert args[0] is process_youtube_video


@pytest.mark.asyncio
async def test_handle_web_article_uses_to_thread():
    """_handle_web_article wraps process_web_article in asyncio.to_thread."""
    from src.telegram_bot import _handle_web_article

    update = _make_update(chat_id=12345)
    ctx = _make_context()

    fake_result = {
        "title": "T", "source_name": "example.com",
        "date": "2025-01-01", "category": "ai-news", "relevance": 7,
        "topics": ["t"], "summary_bullets": ["b"],
        "file_path": "/app/knowledge/ai-news/2025/01/test.md",
        "source_url": "https://example.com/article", "source_type": "web_article",
        "sitename": "example.com", "author": None,
    }

    with patch("src.telegram_bot.asyncio.to_thread", new_callable=AsyncMock, return_value=fake_result) as mock_tt:
        await _handle_web_article(update, ctx, "https://example.com/article")
        mock_tt.assert_called_once()
        args = mock_tt.call_args[0]
        from src.pipeline import process_web_article
        assert args[0] is process_web_article


# ── Message truncation ─────────────────────────────────────────────────────


def test_truncate_under_limit():
    """Short messages pass through unchanged."""
    from src.telegram_bot import _truncate_message
    assert _truncate_message("hello") == "hello"


def test_truncate_over_limit():
    """Long messages are truncated to 4096 chars."""
    from src.telegram_bot import _truncate_message
    long_text = "x" * 5000
    result = _truncate_message(long_text)
    assert len(result) == 4096
    assert result.endswith("...")
