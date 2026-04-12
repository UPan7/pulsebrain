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


def test_truncate_with_unicode():
    """Multi-byte (Cyrillic) text near the limit truncates to char count, not bytes."""
    from src.telegram_bot import _truncate_message
    # 5000 cyrillic chars; len() works on chars, not bytes
    text = "я" * 5000
    result = _truncate_message(text)
    assert len(result) == 4096
    assert result.endswith("...")


# ── Authorization short-circuit ────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "handler_name",
    [
        "cmd_start", "cmd_help", "cmd_list", "cmd_add", "cmd_remove",
        "cmd_categories", "cmd_search", "cmd_recent", "cmd_status",
        "cmd_stats", "cmd_run", "handle_message",
    ],
)
async def test_unauthorized_short_circuits_every_command(handler_name):
    """Wrong chat_id → handler returns without calling reply_text."""
    import src.telegram_bot as tb

    handler = getattr(tb, handler_name)
    update = _make_update(chat_id=99999, text="hello")
    ctx = _make_context()
    with patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345):
        await handler(update, ctx)

    update.message.reply_text.assert_not_called()


# ── Command handlers ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cmd_help_replies_with_command_list():
    from src.telegram_bot import cmd_help

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345):
        await cmd_help(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    for cmd in ("/add", "/remove", "/list", "/search", "/recent", "/status", "/stats", "/run"):
        assert cmd in text


@pytest.mark.asyncio
async def test_cmd_list_no_channels():
    from src.telegram_bot import cmd_list

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345),
        patch("src.telegram_bot.load_channels", return_value=[]),
    ):
        await cmd_list(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "Нет отслеживаемых каналов" in text


@pytest.mark.asyncio
async def test_cmd_list_with_channels():
    from src.telegram_bot import cmd_list

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    channels = [
        {"name": "Active", "id": "UC1", "category": "ai-news", "enabled": True},
        {"name": "Disabled", "id": "UC2", "category": "wp", "enabled": False},
    ]
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345),
        patch("src.telegram_bot.load_channels", return_value=channels),
    ):
        await cmd_list(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "Active" in text
    assert "Disabled" in text
    assert "ai-news" in text


@pytest.mark.asyncio
async def test_cmd_add_no_args():
    from src.telegram_bot import cmd_add

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=[])
    with patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345):
        await cmd_add(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "/add" in text


@pytest.mark.asyncio
async def test_cmd_add_unresolvable_url():
    from src.telegram_bot import cmd_add

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=["https://youtube.com/@nope"])
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345),
        patch("src.telegram_bot.resolve_channel_id", return_value=(None, None)),
    ):
        await cmd_add(update, ctx)

    last_text = update.message.reply_text.call_args_list[-1][0][0]
    assert "Не удалось" in last_text


@pytest.mark.asyncio
async def test_cmd_add_already_monitored():
    from src.telegram_bot import cmd_add

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=["https://youtube.com/@known", "ai-news"])
    existing = [{"name": "Known", "id": "UC_known", "category": "ai-news", "enabled": True}]
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345),
        patch("src.telegram_bot.resolve_channel_id", return_value=("UC_known", "Known")),
        patch("src.telegram_bot.load_channels", return_value=existing),
        patch("src.telegram_bot.save_channels") as mock_save,
    ):
        await cmd_add(update, ctx)

    last_text = update.message.reply_text.call_args_list[-1][0][0]
    assert "уже отслеживается" in last_text
    mock_save.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_add_with_category_persists_immediately():
    from src.telegram_bot import cmd_add

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=["https://youtube.com/@new", "ai-news"])
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345),
        patch("src.telegram_bot.resolve_channel_id", return_value=("UC_new", "NewChan")),
        patch("src.telegram_bot.load_channels", return_value=[]),
        patch("src.telegram_bot.save_channels") as mock_save,
    ):
        await cmd_add(update, ctx)

    mock_save.assert_called_once()
    saved = mock_save.call_args[0][0]
    assert any(ch["id"] == "UC_new" and ch["category"] == "ai-news" for ch in saved)


@pytest.mark.asyncio
async def test_cmd_add_without_category_offers_keyboard():
    from src.telegram_bot import cmd_add

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=["https://youtube.com/@new"])
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345),
        patch("src.telegram_bot.resolve_channel_id", return_value=("UC_new", "NewChan")),
        patch("src.telegram_bot.load_channels", return_value=[]),
        patch("src.telegram_bot.load_categories", return_value={"ai-news": "AI News"}),
        patch("src.telegram_bot.save_channels") as mock_save,
    ):
        await cmd_add(update, ctx)

    mock_save.assert_not_called()
    assert ctx.user_data["pending_channel"]["id"] == "UC_new"
    # The last reply_text call should include reply_markup
    last_kwargs = update.message.reply_text.call_args_list[-1][1]
    assert "reply_markup" in last_kwargs


@pytest.mark.asyncio
async def test_cmd_remove_no_args():
    from src.telegram_bot import cmd_remove

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=[])
    with patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345):
        await cmd_remove(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "/remove" in text


@pytest.mark.asyncio
async def test_cmd_remove_substring_match():
    from src.telegram_bot import cmd_remove

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=["fire"])
    channels = [{"name": "Fireship", "id": "UC1", "category": "ai-news", "enabled": True}]
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345),
        patch("src.telegram_bot.load_channels", return_value=channels),
        patch("src.telegram_bot.save_channels") as mock_save,
    ):
        await cmd_remove(update, ctx)

    mock_save.assert_called_once()
    assert channels[0]["enabled"] is False


@pytest.mark.asyncio
async def test_cmd_remove_not_found():
    from src.telegram_bot import cmd_remove

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=["nope"])
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345),
        patch("src.telegram_bot.load_channels", return_value=[]),
        patch("src.telegram_bot.save_channels") as mock_save,
    ):
        await cmd_remove(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "не найден" in text
    mock_save.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_categories_empty():
    from src.telegram_bot import cmd_categories

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345),
        patch("src.telegram_bot.get_stats", return_value={"by_category": {}}),
        patch("src.telegram_bot.load_categories", return_value={"ai-news": "AI News"}),
    ):
        await cmd_categories(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "Пока нет записей" in text


@pytest.mark.asyncio
async def test_cmd_categories_with_entries():
    from src.telegram_bot import cmd_categories

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345),
        patch("src.telegram_bot.get_stats", return_value={"by_category": {"ai-news": 3}}),
        patch("src.telegram_bot.load_categories", return_value={"ai-news": "AI News"}),
    ):
        await cmd_categories(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "ai-news" in text
    assert "3" in text


@pytest.mark.asyncio
async def test_cmd_search_no_args():
    from src.telegram_bot import cmd_search

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=[])
    with patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345):
        await cmd_search(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "/search" in text


@pytest.mark.asyncio
async def test_cmd_search_no_results():
    from src.telegram_bot import cmd_search

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=["unicorn"])
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345),
        patch("src.telegram_bot.search_knowledge", return_value=[]),
    ):
        await cmd_search(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "ничего не найдено" in text


@pytest.mark.asyncio
async def test_cmd_search_with_results():
    from src.telegram_bot import cmd_search

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=["ai"])
    results = [
        {"title": "Hit One", "type": "youtube_video", "source": "Ch", "date": "2025-06-01",
         "category": "ai-news", "relevance": "8", "summary_preview": "• preview line"},
    ]
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345),
        patch("src.telegram_bot.search_knowledge", return_value=results),
    ):
        await cmd_search(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "Hit One" in text
    assert "ai-news" in text


@pytest.mark.asyncio
async def test_cmd_recent_default_count():
    from src.telegram_bot import cmd_recent

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=[])
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345),
        patch("src.telegram_bot.get_recent_entries", return_value=[]) as mock_get,
    ):
        await cmd_recent(update, ctx)

    mock_get.assert_called_once_with(5)


@pytest.mark.asyncio
async def test_cmd_recent_custom_count():
    from src.telegram_bot import cmd_recent

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=["10"])
    entry = {"title": "T", "type": "web_article", "source": "S", "date": "2025-06-01",
             "category": "ai-news"}
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345),
        patch("src.telegram_bot.get_recent_entries", return_value=[entry]) as mock_get,
    ):
        await cmd_recent(update, ctx)

    mock_get.assert_called_once_with(10)
    text = update.message.reply_text.call_args[0][0]
    assert "T" in text


@pytest.mark.asyncio
async def test_cmd_recent_empty():
    from src.telegram_bot import cmd_recent

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345),
        patch("src.telegram_bot.get_recent_entries", return_value=[]),
    ):
        await cmd_recent(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "Пока нет записей" in text


@pytest.mark.asyncio
async def test_cmd_status_summary():
    from src.telegram_bot import cmd_status

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    stats = {"total": 10, "videos": 6, "articles": 4, "avg_relevance": 7.5, "this_week": 2}
    channels = [{"enabled": True}, {"enabled": False}]
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345),
        patch("src.telegram_bot.get_stats", return_value=stats),
        patch("src.telegram_bot.load_channels", return_value=channels),
    ):
        await cmd_status(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "10" in text
    assert "6" in text
    assert "4" in text
    assert "1/2" in text  # active/total channels


@pytest.mark.asyncio
async def test_cmd_stats_summary():
    from src.telegram_bot import cmd_stats

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    stats = {
        "total": 5, "videos": 3, "articles": 2,
        "by_category": {"ai-news": 5},
        "this_week": 1, "avg_relevance": 8,
        "top_sources": [("Ch", 3)],
    }
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345),
        patch("src.telegram_bot.get_stats", return_value=stats),
    ):
        await cmd_stats(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "ai-news" in text
    assert "Ch" in text


@pytest.mark.asyncio
async def test_cmd_run_processes_videos():
    from src.telegram_bot import cmd_run

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345),
        patch("src.scheduler.run_channel_check", new_callable=AsyncMock, return_value=3),
    ):
        await cmd_run(update, ctx)

    last_text = update.message.reply_text.call_args_list[-1][0][0]
    assert "3" in last_text


@pytest.mark.asyncio
async def test_cmd_run_no_new_videos():
    from src.telegram_bot import cmd_run

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345),
        patch("src.scheduler.run_channel_check", new_callable=AsyncMock, return_value=0),
    ):
        await cmd_run(update, ctx)

    last_text = update.message.reply_text.call_args_list[-1][0][0]
    assert "не найдено" in last_text


# ── URL handlers ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_youtube_video_error_dict_shows_error():
    from src.telegram_bot import _handle_youtube_video

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with patch(
        "src.telegram_bot.asyncio.to_thread",
        new_callable=AsyncMock,
        return_value={"error": "Транскрипт недоступен"},
    ):
        await _handle_youtube_video(update, ctx, "https://youtube.com/watch?v=x")

    msg = update.message.reply_text.return_value
    msg.edit_text.assert_called()
    text = msg.edit_text.call_args[0][0]
    assert "Транскрипт недоступен" in text


@pytest.mark.asyncio
async def test_handle_youtube_video_none_result():
    from src.telegram_bot import _handle_youtube_video

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with patch("src.telegram_bot.asyncio.to_thread", new_callable=AsyncMock, return_value=None):
        await _handle_youtube_video(update, ctx, "https://youtube.com/watch?v=x")

    text = update.message.reply_text.return_value.edit_text.call_args[0][0]
    assert "неизвестная ошибка" in text


@pytest.mark.asyncio
async def test_handle_youtube_channel_offers_categories():
    from src.telegram_bot import _handle_youtube_channel

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with (
        patch("src.telegram_bot.resolve_channel_id", return_value=("UC1", "Chan")),
        patch("src.telegram_bot.load_channels", return_value=[]),
        patch("src.telegram_bot.load_categories", return_value={"ai-news": "AI News"}),
    ):
        await _handle_youtube_channel(update, ctx, "https://youtube.com/@chan")

    assert ctx.user_data["pending_channel"]["id"] == "UC1"
    edit_kwargs = update.message.reply_text.return_value.edit_text.call_args[1]
    assert "reply_markup" in edit_kwargs


@pytest.mark.asyncio
async def test_handle_youtube_channel_already_monitored():
    from src.telegram_bot import _handle_youtube_channel

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    existing = [{"name": "Chan", "id": "UC1", "category": "x", "enabled": True}]
    with (
        patch("src.telegram_bot.resolve_channel_id", return_value=("UC1", "Chan")),
        patch("src.telegram_bot.load_channels", return_value=existing),
    ):
        await _handle_youtube_channel(update, ctx, "https://youtube.com/@chan")

    text = update.message.reply_text.return_value.edit_text.call_args[0][0]
    assert "уже отслеживается" in text


@pytest.mark.asyncio
async def test_handle_youtube_channel_unresolvable():
    from src.telegram_bot import _handle_youtube_channel

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with patch("src.telegram_bot.resolve_channel_id", return_value=(None, None)):
        await _handle_youtube_channel(update, ctx, "https://youtube.com/@nope")

    text = update.message.reply_text.return_value.edit_text.call_args[0][0]
    assert "Не удалось" in text


@pytest.mark.asyncio
async def test_handle_web_article_error_dict_shows_error():
    from src.telegram_bot import _handle_web_article

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with patch(
        "src.telegram_bot.asyncio.to_thread",
        new_callable=AsyncMock,
        return_value={"error": "Парсинг сорвался"},
    ):
        await _handle_web_article(update, ctx, "https://example.com/foo")

    text = update.message.reply_text.return_value.edit_text.call_args[0][0]
    assert "Парсинг сорвался" in text


@pytest.mark.asyncio
async def test_handle_web_article_none_result():
    from src.telegram_bot import _handle_web_article

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with patch("src.telegram_bot.asyncio.to_thread", new_callable=AsyncMock, return_value=None):
        await _handle_web_article(update, ctx, "https://example.com/foo")

    text = update.message.reply_text.return_value.edit_text.call_args[0][0]
    assert "неизвестная ошибка" in text


# ── Question handler ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_question_no_results():
    from src.telegram_bot import _handle_question

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with patch("src.telegram_bot.search_for_question", return_value=[]):
        await _handle_question(update, ctx, "What is X?")

    text = update.message.reply_text.return_value.edit_text.call_args[0][0]
    assert "ничего не собрано" in text


@pytest.mark.asyncio
async def test_handle_question_answer_returned():
    from src.telegram_bot import _handle_question

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    sources = [{"title": "T", "type": "youtube_video", "source": "Ch", "date": "2025-06-01",
                "extracted_text": "x"}]
    with (
        patch("src.telegram_bot.search_for_question", return_value=sources),
        patch("src.telegram_bot.answer_question", return_value="Это ответ"),
    ):
        await _handle_question(update, ctx, "Что?")

    text = update.message.reply_text.return_value.edit_text.call_args[0][0]
    assert "Это ответ" in text
    assert "T" in text  # source listing


@pytest.mark.asyncio
async def test_handle_question_answer_failure():
    from src.telegram_bot import _handle_question

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    sources = [{"title": "T", "extracted_text": "x"}]
    with (
        patch("src.telegram_bot.search_for_question", return_value=sources),
        patch("src.telegram_bot.answer_question", return_value=None),
    ):
        await _handle_question(update, ctx, "Q")

    text = update.message.reply_text.return_value.edit_text.call_args[0][0]
    assert "Не удалось" in text


# ── New-category input ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_new_category_input_invalid_slug_reprompts():
    from src.telegram_bot import _handle_new_category_input

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with patch("src.telegram_bot.add_category") as mock_add:
        await _handle_new_category_input(update, ctx, "!!!", "add_channel")

    mock_add.assert_not_called()
    assert ctx.user_data["waiting_new_category"] == "add_channel"
    text = update.message.reply_text.call_args[0][0]
    assert "Некорректный" in text


@pytest.mark.asyncio
async def test_handle_new_category_input_persists_and_adds_channel():
    from src.telegram_bot import _handle_new_category_input

    update = _make_update(chat_id=12345)
    ctx = _make_context(user_data={"pending_channel": {"name": "Chan", "id": "UC1"}})
    with (
        patch("src.telegram_bot.add_category") as mock_add,
        patch("src.telegram_bot.load_channels", return_value=[]),
        patch("src.telegram_bot.save_channels") as mock_save,
    ):
        await _handle_new_category_input(update, ctx, "machine-learning ML Stuff", "add_channel")

    mock_add.assert_called_once_with("machine-learning", "ML Stuff")
    mock_save.assert_called_once()
    assert "pending_channel" not in ctx.user_data


@pytest.mark.asyncio
async def test_handle_new_category_input_recat():
    from src.telegram_bot import _handle_new_category_input

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with patch("src.telegram_bot.add_category") as mock_add:
        await _handle_new_category_input(update, ctx, "robotics", "recat")

    mock_add.assert_called_once_with("robotics", "Robotics")
    text = update.message.reply_text.call_args[0][0]
    assert "robotics" in text


@pytest.mark.asyncio
async def test_handle_new_category_input_add_channel_lost_pending():
    from src.telegram_bot import _handle_new_category_input

    update = _make_update(chat_id=12345)
    ctx = _make_context()  # no pending_channel
    with (
        patch("src.telegram_bot.add_category"),
        patch("src.telegram_bot.save_channels") as mock_save,
    ):
        await _handle_new_category_input(update, ctx, "robotics", "add_channel")

    mock_save.assert_not_called()
    text = update.message.reply_text.call_args[0][0]
    assert "потеряны" in text


# ── Inline keyboard callbacks ──────────────────────────────────────────────


def _make_callback_update(chat_id: int = 12345, data: str = ""):
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.callback_query = MagicMock()
    update.callback_query.data = data
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_reply_markup = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.message = MagicMock()
    update.callback_query.message.reply_text = AsyncMock()
    return update


@pytest.mark.asyncio
async def test_callback_no_query_returns_silently():
    from src.telegram_bot import callback_handler

    update = MagicMock()
    update.callback_query = None
    ctx = _make_context()
    await callback_handler(update, ctx)  # should not raise


@pytest.mark.asyncio
async def test_callback_cat_ok_persists_new_category():
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="cat_ok")
    ctx = _make_context(user_data={"last_result": {"is_new_category": True, "category": "robotics"}})
    with patch("src.telegram_bot.add_category") as mock_add:
        await callback_handler(update, ctx)

    mock_add.assert_called_once()
    update.callback_query.edit_message_reply_markup.assert_called_with(reply_markup=None)


@pytest.mark.asyncio
async def test_callback_cat_ok_no_new_category():
    """cat_ok with last_result that's not a new category — no add_category call."""
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="cat_ok")
    ctx = _make_context(user_data={"last_result": {"is_new_category": False, "category": "ai-news"}})
    with patch("src.telegram_bot.add_category") as mock_add:
        await callback_handler(update, ctx)

    mock_add.assert_not_called()


@pytest.mark.asyncio
async def test_callback_cat_change_shows_keyboard():
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="cat_change")
    ctx = _make_context()
    with patch("src.telegram_bot.load_categories", return_value={"ai-news": "AI"}):
        await callback_handler(update, ctx)

    update.callback_query.edit_message_reply_markup.assert_called_once()


@pytest.mark.asyncio
async def test_callback_recat_moves_file():
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="recat:robotics")
    ctx = _make_context(user_data={"last_result": {"file_path": "/old/path.md"}})
    with patch("src.telegram_bot.move_entry", return_value="/new/path.md") as mock_move:
        await callback_handler(update, ctx)

    mock_move.assert_called_once_with("/old/path.md", "robotics")
    text = update.callback_query.message.reply_text.call_args[0][0]
    assert "Файл перемещён" in text


@pytest.mark.asyncio
async def test_callback_recat_move_fails():
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="recat:robotics")
    ctx = _make_context(user_data={"last_result": {"file_path": "/old/path.md"}})
    with patch("src.telegram_bot.move_entry", return_value=None):
        await callback_handler(update, ctx)

    text = update.callback_query.message.reply_text.call_args[0][0]
    assert "не найден" in text


@pytest.mark.asyncio
async def test_callback_recat_no_file_path():
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="recat:robotics")
    ctx = _make_context(user_data={"last_result": {}})
    with patch("src.telegram_bot.move_entry") as mock_move:
        await callback_handler(update, ctx)

    mock_move.assert_not_called()
    text = update.callback_query.message.reply_text.call_args[0][0]
    assert "robotics" in text


@pytest.mark.asyncio
async def test_callback_add_channel_persists():
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="add_channel:ai-news")
    ctx = _make_context(user_data={"pending_channel": {"name": "Chan", "id": "UC1"}})
    with (
        patch("src.telegram_bot.load_channels", return_value=[]),
        patch("src.telegram_bot.save_channels") as mock_save,
    ):
        await callback_handler(update, ctx)

    mock_save.assert_called_once()
    assert "pending_channel" not in ctx.user_data


@pytest.mark.asyncio
async def test_callback_add_channel_no_pending():
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="add_channel:ai-news")
    ctx = _make_context()  # no pending_channel
    with patch("src.telegram_bot.save_channels") as mock_save:
        await callback_handler(update, ctx)

    mock_save.assert_not_called()
    text = update.callback_query.message.reply_text.call_args[0][0]
    assert "потеряны" in text


@pytest.mark.asyncio
async def test_callback_new_category_prompt_add_channel():
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="add_channel:__new__")
    ctx = _make_context()
    await callback_handler(update, ctx)

    assert ctx.user_data["waiting_new_category"] == "add_channel"
    update.callback_query.message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_callback_new_category_prompt_recat():
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="recat:__new__")
    ctx = _make_context()
    await callback_handler(update, ctx)

    assert ctx.user_data["waiting_new_category"] == "recat"


@pytest.mark.asyncio
async def test_callback_fetch_recent_processes_videos():
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="fetch_recent:UC1:ai-news")
    ctx = _make_context()

    async def fake_to_thread(fn, *args, **kwargs):
        if fn.__name__ == "get_recent_video_ids":
            return ["v1", "v2"]
        return {"title": "T"}

    with patch("src.telegram_bot.asyncio.to_thread", side_effect=fake_to_thread):
        await callback_handler(update, ctx)

    last_text = update.callback_query.message.reply_text.call_args_list[-1][0][0]
    assert "2" in last_text


@pytest.mark.asyncio
async def test_callback_fetch_skip():
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="fetch_skip")
    ctx = _make_context()
    await callback_handler(update, ctx)

    text = update.callback_query.message.reply_text.call_args[0][0]
    assert "Хорошо" in text


# ── Notifications + setup ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_notification_youtube_format():
    from src.telegram_bot import send_notification

    app = MagicMock()
    app.bot.send_message = AsyncMock()
    result = {
        "source_type": "youtube_video",
        "title": "T", "channel": "Ch",
        "summary_bullets": ["b1", "b2"],
        "topics": ["ai"], "relevance": 8,
        "source_url": "https://yt/watch?v=x",
    }
    with patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345):
        await send_notification(app, result)

    text = app.bot.send_message.call_args.kwargs["text"]
    assert "Ch" in text
    assert "T" in text
    assert "b1" in text
    assert "#ai" in text


@pytest.mark.asyncio
async def test_send_notification_web_format():
    from src.telegram_bot import send_notification

    app = MagicMock()
    app.bot.send_message = AsyncMock()
    result = {
        "source_type": "web_article",
        "title": "Web Title", "sitename": "example.com",
        "summary_bullets": ["b1"], "topics": ["web"], "relevance": 7,
        "source_url": "https://example.com/x",
    }
    with patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345):
        await send_notification(app, result)

    text = app.bot.send_message.call_args.kwargs["text"]
    assert "Web Title" in text
    assert "example.com" in text


@pytest.mark.asyncio
async def test_send_error_notification():
    from src.telegram_bot import send_error_notification

    app = MagicMock()
    app.bot.send_message = AsyncMock()
    with patch("src.telegram_bot.TELEGRAM_CHAT_ID", 12345):
        await send_error_notification(app, "T", "boom")

    text = app.bot.send_message.call_args.kwargs["text"]
    assert "T" in text
    assert "boom" in text


def test_create_bot_application_registers_handlers():
    from src.telegram_bot import create_bot_application

    fake_app = MagicMock()
    builder = MagicMock()
    builder.token.return_value = builder
    builder.post_init.return_value = builder
    builder.build.return_value = fake_app
    with (
        patch("src.telegram_bot.TELEGRAM_BOT_TOKEN", "tok"),
        patch("src.telegram_bot.Application.builder", return_value=builder),
    ):
        app = create_bot_application()

    assert app is fake_app
    # 11 commands + 1 callback + 1 message = 13 handlers
    assert fake_app.add_handler.call_count == 13
