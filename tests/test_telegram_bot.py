"""Tests for src.telegram_bot — async handlers, truncation, auth, routing."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _allow_default_chat_id(monkeypatch):
    """Most tests in this file use chat_id=12345 — allowlist it for every test.

    Tests that specifically test the unauthorized path still use explicit
    patch/monkeypatch to override this fixture's list.
    """
    import src.telegram_bot
    monkeypatch.setattr(src.telegram_bot, "TELEGRAM_CHAT_IDS", [12345])


# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_update(chat_id: int = 12345, text: str = "", language_code: str = "en-US"):
    """Build a minimal mock Update.

    *language_code* emulates Telegram's `effective_user.language_code`
    hint — set to "en-US" by default so existing tests keep working
    without touching it.
    """
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_user.language_code = language_code

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
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        assert _authorized(update) is True


def test_unauthorized_wrong_id():
    """Wrong chat ID → not authorized."""
    from src.telegram_bot import _authorized

    update = _make_update(chat_id=99999)
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        assert _authorized(update) is False


# ── Command handlers ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cmd_start_replies_when_profile_exists():
    """Returning users get the localized welcome."""
    from src.telegram_bot import cmd_start

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.profile_exists", return_value=True),
        patch("src.telegram_bot.get_language", return_value="ru"),
    ):
        await cmd_start(update, ctx)
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "PulseBrain" in text
    assert "готов" in text


@pytest.mark.asyncio
async def test_cmd_start_replies_in_english_when_profile_is_en():
    """Returning en-user gets the English welcome."""
    from src.telegram_bot import cmd_start

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.profile_exists", return_value=True),
        patch("src.telegram_bot.get_language", return_value="en"),
    ):
        await cmd_start(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "ready" in text
    assert "готов" not in text


@pytest.mark.asyncio
async def test_cmd_start_first_run_shows_welcome_in_detected_language():
    """Phase 7.4 + 7.6: fresh install → welcome rendered in the language
    hinted by update.effective_user.language_code (normalized and filtered
    through SUPPORTED_LANGS). Falls back to English for unrecognized hints.
    """
    from src.telegram_bot import cmd_start

    # User locale = German → welcome rendered in German
    update = _make_update(chat_id=12345, language_code="de-DE")
    ctx = _make_context()
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.profile_exists", return_value=False),
    ):
        await cmd_start(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "Hallo" in text  # German welcome
    # Draft should be pre-seeded with the detected language
    assert ctx.user_data["onboarding_draft"]["language"] == "de"


@pytest.mark.asyncio
async def test_cmd_start_first_run_falls_back_to_english_for_unknown_locale():
    """Locale outside SUPPORTED_LANGS → English welcome + draft."""
    from src.telegram_bot import cmd_start

    update = _make_update(chat_id=12345, language_code="sw")  # Swahili: unsupported
    ctx = _make_context()
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.profile_exists", return_value=False),
    ):
        await cmd_start(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "Hi" in text  # English welcome
    assert ctx.user_data["onboarding_draft"]["language"] == "en"


# ── URL routing in handle_message ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_message_routes_youtube():
    """YouTube URL → _handle_youtube_video."""
    from src.telegram_bot import handle_message

    update = _make_update(chat_id=12345, text="https://www.youtube.com/watch?v=abc123")
    ctx = _make_context()

    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
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
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
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
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot._handle_question", new_callable=AsyncMock) as mock_q,
    ):
        await handle_message(update, ctx)
        mock_q.assert_called_once()


# ── Async non-blocking: asyncio.to_thread must be used ─────────────────────


def _fake_pending_entry(source_type="youtube_video"):
    return {
        "id": "deadbeef",
        "content_id": "yt:x",
        "source_url": "https://example.com/x",
        "source_type": source_type,
        "source_name": "TestSource",
        "title": "Test Title",
        "date_str": "2025-06-15",
        "category": "ai-news",
        "is_new_category": False,
        "relevance": 7,
        "topics": ["t"],
        "summary_bullets": ["b"],
        "detailed_notes": "n",
        "key_insights": ["i"],
        "action_items": ["a"],
        "author": None,
        "sitename": "example.com" if source_type == "web_article" else None,
        "created_at": "2025-06-15T12:00:00",
    }


@pytest.mark.asyncio
async def test_handle_youtube_video_uses_to_thread():
    """_handle_youtube_video wraps process_youtube_video in asyncio.to_thread."""
    from src.telegram_bot import _handle_youtube_video

    update = _make_update(chat_id=12345)
    ctx = _make_context()

    fake_result = {"pending_id": "deadbeef", "title": "T",
                   "category": "ai-news", "source_type": "youtube_video"}

    with (
        patch("src.telegram_bot.asyncio.to_thread", new_callable=AsyncMock, return_value=fake_result) as mock_tt,
        patch("src.telegram_bot.get_pending", return_value=_fake_pending_entry()),
    ):
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

    fake_result = {"pending_id": "deadbeef", "title": "T",
                   "category": "ai-news", "source_type": "web_article"}

    with (
        patch("src.telegram_bot.asyncio.to_thread", new_callable=AsyncMock, return_value=fake_result) as mock_tt,
        patch("src.telegram_bot.get_pending", return_value=_fake_pending_entry("web_article")),
    ):
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
        "cmd_stats", "cmd_run", "cmd_pending", "cmd_rejected",
        "cmd_onboarding", "cmd_cancel", "cmd_language", "handle_message",
    ],
)
async def test_unauthorized_short_circuits_every_command(handler_name):
    """Wrong chat_id → handler returns without calling reply_text."""
    import src.telegram_bot as tb

    handler = getattr(tb, handler_name)
    update = _make_update(chat_id=99999, text="hello")
    ctx = _make_context()
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await handler(update, ctx)

    update.message.reply_text.assert_not_called()


# ── Command handlers ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cmd_help_replies_with_command_list():
    from src.telegram_bot import cmd_help

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.get_language", return_value="ru"),
    ):
        await cmd_help(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    for cmd in ("/add", "/remove", "/list", "/search", "/recent", "/status",
                "/stats", "/run", "/language", "/rejected"):
        assert cmd in text


@pytest.mark.asyncio
async def test_cmd_help_in_english():
    """When the profile language is en, /help renders the English catalog."""
    from src.telegram_bot import cmd_help

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.get_language", return_value="en"),
    ):
        await cmd_help(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    # English marker phrase
    assert "Commands" in text
    # Core commands still present
    assert "/language" in text


@pytest.mark.asyncio
async def test_cmd_list_no_channels():
    from src.telegram_bot import cmd_list

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.load_channels", return_value=[]),
    ):
        await cmd_list(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "No monitored channels" in text


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
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
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
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await cmd_add(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "/add" in text


@pytest.mark.asyncio
async def test_cmd_add_unresolvable_url():
    from src.telegram_bot import cmd_add

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=["https://youtube.com/@nope"])
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.resolve_channel_id", return_value=(None, None)),
    ):
        await cmd_add(update, ctx)

    last_text = update.message.reply_text.call_args_list[-1][0][0]
    assert "Couldn't resolve" in last_text


@pytest.mark.asyncio
async def test_cmd_add_already_monitored():
    from src.telegram_bot import cmd_add

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=["https://youtube.com/@known", "ai-news"])
    existing = [{"name": "Known", "id": "UC_known", "category": "ai-news", "enabled": True}]
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.resolve_channel_id", return_value=("UC_known", "Known")),
        patch("src.telegram_bot.load_channels", return_value=existing),
        patch("src.telegram_bot.save_channels") as mock_save,
    ):
        await cmd_add(update, ctx)

    last_text = update.message.reply_text.call_args_list[-1][0][0]
    assert "already being tracked" in last_text
    mock_save.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_add_with_category_persists_immediately():
    from src.telegram_bot import cmd_add

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=["https://youtube.com/@new", "ai-news"])
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.resolve_channel_id", return_value=("UC_new", "NewChan")),
        patch("src.telegram_bot.load_channels", return_value=[]),
        patch("src.telegram_bot.save_channels") as mock_save,
    ):
        await cmd_add(update, ctx)

    mock_save.assert_called_once()
    saved = mock_save.call_args[0][1]
    assert any(ch["id"] == "UC_new" and ch["category"] == "ai-news" for ch in saved)


@pytest.mark.asyncio
async def test_cmd_add_without_category_offers_keyboard():
    from src.telegram_bot import cmd_add

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=["https://youtube.com/@new"])
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
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
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
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
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
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
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.load_channels", return_value=[]),
        patch("src.telegram_bot.save_channels") as mock_save,
    ):
        await cmd_remove(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "not found" in text
    mock_save.assert_not_called()


@pytest.mark.asyncio
async def test_cmd_categories_empty():
    from src.telegram_bot import cmd_categories

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.get_stats", return_value={
            "by_category": {}, "category_health": {},
        }),
    ):
        await cmd_categories(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "No entries yet" in text


@pytest.mark.asyncio
async def test_cmd_categories_with_entries():
    from src.telegram_bot import cmd_categories

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    stats = {
        "by_category": {"ai-news": 3},
        "category_health": {
            "ai-news": {
                "count": 3, "last_entry": "2025-06-15",
                "avg_relevance": 7.5, "stale": False,
            },
        },
    }
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.get_stats", return_value=stats),
    ):
        await cmd_categories(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "ai-news" in text
    assert "3" in text
    assert "7.5" in text            # avg_relevance
    assert "2025-06-15" in text      # last_entry
    assert "✅" in text              # not stale


@pytest.mark.asyncio
async def test_cmd_categories_marks_stale():
    from src.telegram_bot import cmd_categories

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    stats = {
        "by_category": {"wordpress": 2},
        "category_health": {
            "wordpress": {
                "count": 2, "last_entry": "2025-01-01",
                "avg_relevance": 5.0, "stale": True,
            },
        },
    }
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.get_stats", return_value=stats),
    ):
        await cmd_categories(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "⚠" in text
    assert "(stale)" in text


@pytest.mark.asyncio
async def test_cmd_search_no_args():
    from src.telegram_bot import cmd_search

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=[])
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await cmd_search(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "/search" in text


@pytest.mark.asyncio
async def test_cmd_search_no_results():
    from src.telegram_bot import cmd_search

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=["unicorn"])
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.search_knowledge", return_value=[]),
    ):
        await cmd_search(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "Nothing found" in text


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
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
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
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.get_recent_entries", return_value=[]) as mock_get,
    ):
        await cmd_recent(update, ctx)

    mock_get.assert_called_once_with(12345, 5)


@pytest.mark.asyncio
async def test_cmd_recent_custom_count():
    from src.telegram_bot import cmd_recent

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=["10"])
    entry = {"title": "T", "type": "web_article", "source": "S", "date": "2025-06-01",
             "category": "ai-news"}
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.get_recent_entries", return_value=[entry]) as mock_get,
    ):
        await cmd_recent(update, ctx)

    mock_get.assert_called_once_with(12345, 10)
    text = update.message.reply_text.call_args[0][0]
    assert "T" in text


@pytest.mark.asyncio
async def test_cmd_recent_empty():
    from src.telegram_bot import cmd_recent

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.get_recent_entries", return_value=[]),
    ):
        await cmd_recent(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "No entries yet" in text


@pytest.mark.asyncio
async def test_cmd_status_summary():
    from src.telegram_bot import cmd_status

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    stats = {"total": 10, "videos": 6, "articles": 4, "avg_relevance": 7.5, "this_week": 2}
    channels = [{"enabled": True}, {"enabled": False}]
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
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
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
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
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
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
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.scheduler.run_channel_check", new_callable=AsyncMock, return_value=0),
    ):
        await cmd_run(update, ctx)

    last_text = update.message.reply_text.call_args_list[-1][0][0]
    assert "No new videos found" in last_text


@pytest.mark.asyncio
async def test_cmd_pending_empty():
    from src.telegram_bot import cmd_pending

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.list_pending", return_value=[]),
    ):
        await cmd_pending(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "queue is empty" in text


@pytest.mark.asyncio
async def test_cmd_pending_lists_entries():
    from src.telegram_bot import cmd_pending

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    entries = [_fake_pending_entry(), {**_fake_pending_entry(), "id": "cafef00d", "title": "Second"}]
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.list_pending", return_value=entries),
    ):
        await cmd_pending(update, ctx)

    # Header + one message per entry
    assert update.message.reply_text.call_count == 3
    # Each entry's reply has the keyboard attached
    for call in update.message.reply_text.call_args_list[1:]:
        assert "reply_markup" in call.kwargs


# ── cmd_rejected (Phase 2.0) ──────────────────────────────────────────────


def _fake_rejected_record(title: str = "Бесполезное видео", relevance: int = 3,
                          reason: str = "low_relevance"):
    return {
        "ts": "2026-04-12T10:30:00+00:00",
        "pending_id": "cafef00d",
        "title": title,
        "source_name": "NoiseMaker",
        "source_url": "https://youtube.com/watch?v=xyz",
        "source_type": "youtube_video",
        "relevance": relevance,
        "reason": reason,
    }


@pytest.mark.asyncio
async def test_cmd_rejected_empty_log():
    from src.telegram_bot import cmd_rejected

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.read_rejected_log", return_value=[]),
    ):
        await cmd_rejected(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "log is empty" in text


@pytest.mark.asyncio
async def test_cmd_rejected_shows_records_with_score_and_reason():
    from src.telegram_bot import cmd_rejected

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    records = [
        _fake_rejected_record("Docker 101", 2, "low_relevance"),
        _fake_rejected_record("Generic listicle", 3, "low_relevance"),
    ]
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.read_rejected_log", return_value=records) as mock_read,
    ):
        await cmd_rejected(update, ctx)

    mock_read.assert_called_once_with(12345, 10)  # default
    text = update.message.reply_text.call_args[0][0]
    assert "Docker 101" in text
    assert "Generic listicle" in text
    assert "relevance 2/10" in text
    assert "relevance 3/10" in text
    assert "low relevance" in text
    assert "NoiseMaker" in text


@pytest.mark.asyncio
async def test_cmd_rejected_honors_numeric_arg():
    from src.telegram_bot import cmd_rejected

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=["3"])
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.read_rejected_log", return_value=[]) as mock_read,
    ):
        await cmd_rejected(update, ctx)

    mock_read.assert_called_once_with(12345, 3)


@pytest.mark.asyncio
async def test_cmd_rejected_caps_limit_at_50():
    """Paranoid cap so a bogus /rejected 1000000 doesn't blow the message size."""
    from src.telegram_bot import cmd_rejected

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=["999"])
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.read_rejected_log", return_value=[]) as mock_read,
    ):
        await cmd_rejected(update, ctx)

    mock_read.assert_called_once_with(12345, 50)


@pytest.mark.asyncio
async def test_cmd_rejected_handles_non_numeric_arg():
    """/rejected foo → falls back to default 10."""
    from src.telegram_bot import cmd_rejected

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=["foo"])
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.read_rejected_log", return_value=[]) as mock_read,
    ):
        await cmd_rejected(update, ctx)

    mock_read.assert_called_once_with(12345, 10)


@pytest.mark.asyncio
async def test_cmd_rejected_maps_manual_reason():
    from src.telegram_bot import cmd_rejected

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    records = [_fake_rejected_record("User rejected this", 7, "manual")]
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.read_rejected_log", return_value=records),
    ):
        await cmd_rejected(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "manual" in text


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
    assert "Unknown error" in text


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
    assert "already being tracked" in text


@pytest.mark.asyncio
async def test_handle_youtube_channel_unresolvable():
    from src.telegram_bot import _handle_youtube_channel

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with patch("src.telegram_bot.resolve_channel_id", return_value=(None, None)):
        await _handle_youtube_channel(update, ctx, "https://youtube.com/@nope")

    text = update.message.reply_text.return_value.edit_text.call_args[0][0]
    assert ("Couldn't resolve" in text or "Failed" in text)


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
    assert "Unknown error" in text


# ── Question handler ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_question_no_results():
    from src.telegram_bot import _handle_question

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with patch("src.telegram_bot.search_for_question", return_value=[]):
        await _handle_question(update, ctx, "What is X?")

    text = update.message.reply_text.return_value.edit_text.call_args[0][0]
    assert "Nothing collected" in text


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
    assert ("Couldn't resolve" in text or "Failed" in text)


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
    assert "Invalid slug" in text


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

    mock_add.assert_called_once_with(12345, "machine-learning", "ML Stuff")
    mock_save.assert_called_once()
    assert "pending_channel" not in ctx.user_data


@pytest.mark.asyncio
async def test_handle_new_category_input_pending_branch():
    """The 'pending:{id}' action updates the staged entry and re-renders."""
    from src.telegram_bot import _handle_new_category_input

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with (
        patch("src.telegram_bot.add_category") as mock_add,
        patch("src.telegram_bot.update_pending_category", return_value=True) as mock_upd,
        patch("src.telegram_bot.get_pending", return_value=_fake_pending_entry()),
    ):
        await _handle_new_category_input(update, ctx, "robotics", "pending:deadbeef")

    mock_add.assert_called_once_with(12345, "robotics", "Robotics")
    mock_upd.assert_called_once_with(12345, "deadbeef", "robotics", is_new_category=True)
    # The reply has the new keyboard attached
    last_kwargs = update.message.reply_text.call_args_list[-1][1]
    assert "reply_markup" in last_kwargs


@pytest.mark.asyncio
async def test_handle_new_category_input_pending_lost_entry():
    from src.telegram_bot import _handle_new_category_input

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with (
        patch("src.telegram_bot.add_category"),
        patch("src.telegram_bot.update_pending_category", return_value=False),
    ):
        await _handle_new_category_input(update, ctx, "robotics", "pending:deadbeef")

    text = update.message.reply_text.call_args[0][0]
    assert "no longer in the queue" in text


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
    assert "lost" in text


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
async def test_callback_psave_commits_and_persists_new_category():
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="psave:deadbeef")
    ctx = _make_context()
    entry = _fake_pending_entry()
    entry["is_new_category"] = True
    entry["category"] = "robotics"
    with (
        patch("src.telegram_bot.get_pending", return_value=entry),
        patch("src.telegram_bot.add_category") as mock_add,
        patch("src.telegram_bot.asyncio.to_thread",
              new_callable=AsyncMock,
              return_value="/app/knowledge/robotics/2025/06/x.md") as mock_tt,
    ):
        await callback_handler(update, ctx)

    mock_add.assert_called_once()
    mock_tt.assert_called_once()
    # First positional arg of to_thread should be commit_pending
    from src.pending import commit_pending
    assert mock_tt.call_args[0][0] is commit_pending
    update.callback_query.edit_message_text.assert_called_once()
    text = update.callback_query.edit_message_text.call_args[0][0]
    assert "Saved" in text


@pytest.mark.asyncio
async def test_callback_psave_unknown_id():
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="psave:deadbeef")
    ctx = _make_context()
    with patch("src.telegram_bot.get_pending", return_value=None):
        await callback_handler(update, ctx)

    text = update.callback_query.edit_message_text.call_args[0][0]
    assert "no longer in queue" in text


@pytest.mark.asyncio
async def test_callback_psave_commit_fails():
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="psave:deadbeef")
    ctx = _make_context()
    with (
        patch("src.telegram_bot.get_pending", return_value=_fake_pending_entry()),
        patch("src.telegram_bot.asyncio.to_thread", new_callable=AsyncMock, return_value=None),
    ):
        await callback_handler(update, ctx)

    text = update.callback_query.edit_message_text.call_args[0][0]
    assert ("Couldn't resolve" in text or "Failed" in text)


@pytest.mark.asyncio
async def test_callback_pskip_rejects_entry():
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="pskip:deadbeef")
    ctx = _make_context()
    with (
        patch("src.telegram_bot.get_pending", return_value=_fake_pending_entry()),
        patch("src.telegram_bot.reject_pending", return_value=True) as mock_rej,
    ):
        await callback_handler(update, ctx)

    mock_rej.assert_called_once_with(12345, "deadbeef")
    text = update.callback_query.edit_message_text.call_args[0][0]
    assert "Rejected" in text


@pytest.mark.asyncio
async def test_callback_pskip_unknown_id():
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="pskip:deadbeef")
    ctx = _make_context()
    with patch("src.telegram_bot.get_pending", return_value=None):
        await callback_handler(update, ctx)

    text = update.callback_query.edit_message_text.call_args[0][0]
    assert "no longer in queue" in text


@pytest.mark.asyncio
async def test_callback_pcat_shows_category_keyboard():
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="pcat:deadbeef")
    ctx = _make_context()
    with (
        patch("src.telegram_bot.get_pending", return_value=_fake_pending_entry()),
        patch("src.telegram_bot.load_categories", return_value={"ai-news": "AI"}),
    ):
        await callback_handler(update, ctx)

    update.callback_query.edit_message_reply_markup.assert_called_once()


@pytest.mark.asyncio
async def test_callback_pcat_unknown_id():
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="pcat:deadbeef")
    ctx = _make_context()
    with patch("src.telegram_bot.get_pending", return_value=None):
        await callback_handler(update, ctx)

    text = update.callback_query.edit_message_text.call_args[0][0]
    assert "no longer in queue" in text


@pytest.mark.asyncio
async def test_callback_psetc_updates_category():
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="psetc:deadbeef:robotics")
    ctx = _make_context()
    with (
        patch("src.telegram_bot.update_pending_category", return_value=True) as mock_upd,
        patch("src.telegram_bot.get_pending", return_value=_fake_pending_entry()),
    ):
        await callback_handler(update, ctx)

    mock_upd.assert_called_once_with(12345, "deadbeef", "robotics")
    update.callback_query.edit_message_text.assert_called_once()


@pytest.mark.asyncio
async def test_callback_psetc_new_category_prompts_for_slug():
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="psetc:deadbeef:__new__")
    ctx = _make_context()
    await callback_handler(update, ctx)

    assert ctx.user_data["waiting_new_category"] == "pending:deadbeef"
    update.callback_query.message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_callback_psetc_unknown_id():
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="psetc:deadbeef:robotics")
    ctx = _make_context()
    with patch("src.telegram_bot.update_pending_category", return_value=False):
        await callback_handler(update, ctx)

    text = update.callback_query.edit_message_text.call_args[0][0]
    assert "no longer in queue" in text


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
    assert "lost" in text


@pytest.mark.asyncio
async def test_callback_new_category_prompt_add_channel():
    from src.telegram_bot import callback_handler

    update = _make_callback_update(data="add_channel:__new__")
    ctx = _make_context()
    await callback_handler(update, ctx)

    assert ctx.user_data["waiting_new_category"] == "add_channel"
    update.callback_query.message.reply_text.assert_called_once()


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
    assert "OK" in text


# ── Notifications + setup ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_notification_youtube_format():
    from src.telegram_bot import send_notification

    app = MagicMock()
    app.bot.send_message = AsyncMock()
    result = {"pending_id": "deadbeef"}
    entry = _fake_pending_entry()
    entry["source_name"] = "Ch"
    entry["title"] = "T"
    entry["summary_bullets"] = ["b1", "b2"]
    entry["topics"] = ["ai"]
    entry["relevance"] = 8
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.get_pending", return_value=entry),
    ):
        await send_notification(app, 12345, result)

    text = app.bot.send_message.call_args.kwargs["text"]
    assert "Ch" in text
    assert "T" in text
    assert "b1" in text
    assert "#ai" in text
    # Approve/reject keyboard attached
    assert app.bot.send_message.call_args.kwargs.get("reply_markup") is not None


@pytest.mark.asyncio
async def test_send_notification_web_format():
    from src.telegram_bot import send_notification

    app = MagicMock()
    app.bot.send_message = AsyncMock()
    result = {"pending_id": "deadbeef"}
    entry = _fake_pending_entry("web_article")
    entry["title"] = "Web Title"
    entry["sitename"] = "example.com"
    entry["summary_bullets"] = ["b1"]
    entry["topics"] = ["web"]
    entry["relevance"] = 7
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.get_pending", return_value=entry),
    ):
        await send_notification(app, 12345, result)

    text = app.bot.send_message.call_args.kwargs["text"]
    assert "Web Title" in text
    assert "example.com" in text


@pytest.mark.asyncio
async def test_send_notification_silent_when_no_pending_id():
    from src.telegram_bot import send_notification

    app = MagicMock()
    app.bot.send_message = AsyncMock()
    await send_notification(app, 12345, {"title": "no pid"})

    app.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_send_notification_silent_when_entry_dropped():
    from src.telegram_bot import send_notification

    app = MagicMock()
    app.bot.send_message = AsyncMock()
    with patch("src.telegram_bot.get_pending", return_value=None):
        await send_notification(app, 12345, {"pending_id": "deadbeef"})

    app.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_send_error_notification():
    from src.telegram_bot import send_error_notification

    app = MagicMock()
    app.bot.send_message = AsyncMock()
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await send_error_notification(app, 12345, "T", "boom")

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
    # 17 commands (incl. /pending, /rejected, /get, /onboarding, /cancel,
    # /language) + 1 callback + 1 message = 19 handlers
    assert fake_app.add_handler.call_count == 19


# ── Onboarding wizard (Phase 5.3) ────────────────────────────────────────


def _make_callback_update(chat_id: int = 12345, data: str = ""):
    """Build an Update with a callback_query, for inline button presses."""
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.callback_query = MagicMock()
    update.callback_query.data = data
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.edit_message_reply_markup = AsyncMock()
    update.callback_query.message = MagicMock()
    update.callback_query.message.reply_text = AsyncMock()
    return update


@pytest.mark.asyncio
async def test_cmd_start_fresh_triggers_wizard(tmp_knowledge_dir):
    """No profile on disk → cmd_start starts the wizard instead of welcome."""
    from src.profile import init_profile
    from src.telegram_bot import cmd_start

    init_profile(12345)
    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await cmd_start(update, ctx)

    # State initialized
    assert ctx.user_data["onboarding_step"] == 0
    assert "onboarding_draft" in ctx.user_data
    # Single-language welcome (Phase 7.4 — defaults to English because
    # the _make_update helper's default language_code is "en-US") + 10-lang keyboard
    call = update.message.reply_text.call_args
    text = call[0][0]
    assert "Hi" in text
    assert "reply_markup" in call.kwargs
    # 10-lang picker has 5 rows × 2 buttons
    keyboard = call.kwargs["reply_markup"]
    assert len(keyboard.inline_keyboard) == 5


@pytest.mark.asyncio
async def test_cmd_start_returning_skips_wizard(tmp_knowledge_dir):
    """Existing profile → plain welcome."""
    from src.profile import init_profile, save_profile
    from src.telegram_bot import cmd_start

    init_profile(12345)
    save_profile(12345, {"language": "ru", "persona": "X"})

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await cmd_start(update, ctx)

    assert "onboarding_step" not in ctx.user_data
    text = update.message.reply_text.call_args[0][0]
    assert "готов" in text


@pytest.mark.asyncio
async def test_wizard_lang_callback_advances_to_welcome(tmp_knowledge_dir):
    """Clicking the English button writes language=en and advances to welcome."""
    from src.profile import init_profile
    from src.telegram_bot import callback_handler, cmd_start

    init_profile(12345)
    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await cmd_start(update, ctx)

    # Now click the English button
    cb = _make_callback_update(12345, "onb:lang:en")
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await callback_handler(cb, ctx)

    assert ctx.user_data["onboarding_draft"]["language"] == "en"
    assert ctx.user_data["onboarding_step"] == 1  # welcome
    # After lang save, bot renders welcome body in English
    rendered = cb.callback_query.message.reply_text.call_args[0][0]
    assert "questions" in rendered or "walk" in rendered


@pytest.mark.asyncio
async def test_wizard_persona_text_step(tmp_knowledge_dir):
    """After lang+welcome, bot asks for persona; user types it → advance."""
    from src.profile import init_profile
    from src.telegram_bot import callback_handler, cmd_start, handle_message

    init_profile(12345)
    ctx = _make_context()
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        # /start → step 0
        await cmd_start(_make_update(12345), ctx)
        # onb:lang:ru → step 1
        await callback_handler(_make_callback_update(12345, "onb:lang:ru"), ctx)
        # onb:next (welcome → persona, step 2)
        await callback_handler(_make_callback_update(12345, "onb:next"), ctx)

    assert ctx.user_data["onboarding_step"] == 2  # persona step

    # User types their persona
    update = _make_update(12345, text="Senior dev, 10 years")
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await handle_message(update, ctx)

    assert ctx.user_data["onboarding_draft"]["persona"] == "Senior dev, 10 years"
    assert ctx.user_data["onboarding_step"] == 3  # learning step


@pytest.mark.asyncio
async def test_wizard_multiline_text_parsed(tmp_knowledge_dir):
    """Multiline 'learning' answer is split on newlines into a list."""
    from src.profile import init_profile
    from src.telegram_bot import callback_handler, cmd_start, handle_message

    init_profile(12345)
    ctx = _make_context()
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await cmd_start(_make_update(12345), ctx)
        await callback_handler(_make_callback_update(12345, "onb:lang:ru"), ctx)
        await callback_handler(_make_callback_update(12345, "onb:next"), ctx)
        await handle_message(_make_update(12345, text="Senior"), ctx)  # persona → 3

        # Now at learning step
        assert ctx.user_data["onboarding_step"] == 3
        await handle_message(
            _make_update(12345, text="AI agents\nRAG\n\n  docker  "),
            ctx,
        )

    draft = ctx.user_data["onboarding_draft"]
    assert draft["actively_learning"] == ["AI agents", "RAG", "docker"]
    assert ctx.user_data["onboarding_step"] == 4  # stack step


@pytest.mark.asyncio
async def test_wizard_category_toggle_persists_in_draft(tmp_knowledge_dir):
    """Clicking a category button toggles it in the draft and re-renders."""
    from src.onboarding import new_draft
    from src.profile import init_profile
    from src.telegram_bot import callback_handler

    init_profile(12345)
    ctx = _make_context()
    ctx.user_data["onboarding_step"] = 6  # categories step
    ctx.user_data["onboarding_draft"] = new_draft()

    cb1 = _make_callback_update(12345, "onb:cat:ai-agents")
    cb2 = _make_callback_update(12345, "onb:cat:devops-selfhost")
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await callback_handler(cb1, ctx)
        await callback_handler(cb2, ctx)

    selected = ctx.user_data["onboarding_draft"]["selected_categories"]
    assert "ai-agents" in selected
    assert "devops-selfhost" in selected


@pytest.mark.asyncio
async def test_wizard_category_toggle_twice_removes(tmp_knowledge_dir):
    """Clicking a category a second time unselects it."""
    from src.onboarding import new_draft
    from src.profile import init_profile
    from src.telegram_bot import callback_handler

    init_profile(12345)
    ctx = _make_context()
    ctx.user_data["onboarding_step"] = 6
    ctx.user_data["onboarding_draft"] = new_draft()

    cb = _make_callback_update(12345, "onb:cat:ai-agents")
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await callback_handler(cb, ctx)
        await callback_handler(cb, ctx)

    assert ctx.user_data["onboarding_draft"]["selected_categories"] == {}


@pytest.mark.asyncio
async def test_wizard_done_applies_draft_and_clears_state(tmp_knowledge_dir):
    """onb:done on categories step → auto-skip channels (empty presets) → done."""
    import src.config
    from src.onboarding import new_draft
    from src.profile import init_profile, profile_exists
    from src.telegram_bot import callback_handler

    init_profile(12345)
    ctx = _make_context()
    draft = new_draft()
    draft["language"] = "en"
    draft["persona"] = "Tester"
    draft["selected_categories"] = {"ai-agents": "AI Agents desc"}
    ctx.user_data["onboarding_step"] = 6  # categories
    ctx.user_data["onboarding_draft"] = draft

    cb = _make_callback_update(12345, "onb:done")
    with (
        patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.telegram_bot.PRESET_CHANNELS", []),  # skip channels step
    ):
        await callback_handler(cb, ctx)

    # State cleared
    assert "onboarding_step" not in ctx.user_data
    assert "onboarding_draft" not in ctx.user_data
    # Profile + categories committed
    assert profile_exists(12345)
    assert src.config.user_categories_file(12345).exists()


@pytest.mark.asyncio
async def test_wizard_skip_button_on_optional_step(tmp_knowledge_dir):
    """Skip on notinterested (optional) step advances to categories."""
    from src.onboarding import new_draft
    from src.profile import init_profile
    from src.telegram_bot import callback_handler

    init_profile(12345)
    ctx = _make_context()
    ctx.user_data["onboarding_step"] = 5  # notinterested
    ctx.user_data["onboarding_draft"] = new_draft()

    cb = _make_callback_update(12345, "onb:skip")
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await callback_handler(cb, ctx)

    assert ctx.user_data["onboarding_step"] == 6


@pytest.mark.asyncio
async def test_wizard_stale_callback_noop(tmp_knowledge_dir):
    """A wizard callback arriving after /cancel is a gentle no-op."""
    from src.profile import init_profile
    from src.telegram_bot import callback_handler

    init_profile(12345)
    ctx = _make_context()
    # No onboarding_step set

    cb = _make_callback_update(12345, "onb:lang:ru")
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await callback_handler(cb, ctx)

    # No crash, reply_markup clear called
    cb.callback_query.edit_message_reply_markup.assert_called_once()


# ── /cancel ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cmd_cancel_wipes_flow_state(tmp_knowledge_dir):
    from src.profile import init_profile
    from src.telegram_bot import cmd_cancel

    init_profile(12345)
    ctx = _make_context(user_data={
        "pending_channel": {"id": "UC_x"},
        "waiting_new_category": "add_channel",
        "onboarding_step": 3,
        "onboarding_draft": {"persona": "x"},
    })
    update = _make_update(12345)
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await cmd_cancel(update, ctx)

    assert "pending_channel" not in ctx.user_data
    assert "waiting_new_category" not in ctx.user_data
    assert "onboarding_step" not in ctx.user_data
    assert "onboarding_draft" not in ctx.user_data
    text = update.message.reply_text.call_args[0][0]
    assert "Отменено" in text or "Cancelled" in text


@pytest.mark.asyncio
async def test_cmd_cancel_without_state(tmp_knowledge_dir):
    """/cancel with no active flow → 'nothing to cancel' message."""
    from src.profile import init_profile
    from src.telegram_bot import cmd_cancel

    init_profile(12345)
    ctx = _make_context()
    update = _make_update(12345)
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await cmd_cancel(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "Нечего" in text or "Nothing" in text


# ── /onboarding ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cmd_onboarding_fresh_starts_wizard(tmp_knowledge_dir):
    """No profile → /onboarding runs _start_wizard directly."""
    from src.profile import init_profile
    from src.telegram_bot import cmd_onboarding

    init_profile(12345)
    ctx = _make_context()
    update = _make_update(12345)
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await cmd_onboarding(update, ctx)

    assert ctx.user_data["onboarding_step"] == 0


@pytest.mark.asyncio
async def test_cmd_onboarding_existing_profile_asks_confirm(tmp_knowledge_dir):
    """Existing profile → confirm keyboard."""
    from src.profile import init_profile, save_profile
    from src.telegram_bot import cmd_onboarding

    init_profile(12345)
    save_profile(12345, {"language": "ru", "persona": "X"})
    ctx = _make_context()
    update = _make_update(12345)
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await cmd_onboarding(update, ctx)

    # No wizard state set yet
    assert "onboarding_step" not in ctx.user_data
    call = update.message.reply_text.call_args
    assert "reply_markup" in call.kwargs


@pytest.mark.asyncio
async def test_onboarding_rerun_no_keeps_profile(tmp_knowledge_dir):
    from src.profile import init_profile, save_profile
    from src.telegram_bot import callback_handler

    init_profile(12345)
    save_profile(12345, {"language": "ru", "persona": "X"})
    ctx = _make_context()

    cb = _make_callback_update(12345, "onb:rerun:no")
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await callback_handler(cb, ctx)

    text = cb.callback_query.edit_message_text.call_args[0][0]
    assert "как есть" in text or "as is" in text
    assert "onboarding_step" not in ctx.user_data


@pytest.mark.asyncio
async def test_onboarding_rerun_yes_starts_wizard(tmp_knowledge_dir):
    from src.profile import init_profile, save_profile
    from src.telegram_bot import callback_handler

    init_profile(12345)
    save_profile(12345, {"language": "en", "persona": "X"})
    ctx = _make_context()

    cb = _make_callback_update(12345, "onb:rerun:yes")
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await callback_handler(cb, ctx)

    assert ctx.user_data["onboarding_step"] == 0


# ── /language command (Phase 5.4) ────────────────────────────────────────


@pytest.mark.asyncio
async def test_cmd_language_shows_picker_keyboard(tmp_knowledge_dir):
    from src.profile import init_profile, save_profile
    from src.telegram_bot import cmd_language

    init_profile(12345)
    save_profile(12345, {"language": "ru", "persona": "X"})
    ctx = _make_context()
    update = _make_update(12345)
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await cmd_language(update, ctx)

    call = update.message.reply_text.call_args
    text = call[0][0]
    assert "язык" in text.lower() or "language" in text.lower()
    assert "reply_markup" in call.kwargs


@pytest.mark.asyncio
async def test_cmd_language_in_english(tmp_knowledge_dir):
    """When current language is en, the prompt is in English."""
    from src.profile import init_profile, save_profile
    from src.telegram_bot import cmd_language

    init_profile(12345)
    save_profile(12345, {"language": "en", "persona": "X"})
    ctx = _make_context()
    update = _make_update(12345)
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await cmd_language(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "language" in text.lower()


@pytest.mark.asyncio
async def test_language_callback_writes_profile(tmp_knowledge_dir):
    """lang:en callback persists the choice."""
    from src.profile import init_profile, load_profile, save_profile
    from src.telegram_bot import callback_handler

    init_profile(12345)
    save_profile(12345, {"language": "ru", "persona": "X"})
    ctx = _make_context()

    cb = _make_callback_update(12345, "lang:en")
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await callback_handler(cb, ctx)

    assert load_profile(12345)["language"] == "en"


@pytest.mark.asyncio
async def test_language_callback_confirmation_in_new_language(tmp_knowledge_dir):
    """After switching to en, the confirmation text is English."""
    from src.profile import init_profile, save_profile
    from src.telegram_bot import callback_handler

    init_profile(12345)
    save_profile(12345, {"language": "ru", "persona": "X"})
    ctx = _make_context()

    cb = _make_callback_update(12345, "lang:en")
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await callback_handler(cb, ctx)

    text = cb.callback_query.edit_message_text.call_args[0][0]
    assert "English" in text
    assert "switched" in text.lower() or "language" in text.lower()


@pytest.mark.asyncio
async def test_language_callback_ignores_unknown_code(tmp_knowledge_dir):
    """lang:klingon is silently ignored — profile stays put."""
    from src.profile import init_profile, load_profile, save_profile
    from src.telegram_bot import callback_handler

    init_profile(12345)
    save_profile(12345, {"language": "ru", "persona": "X"})
    ctx = _make_context()

    cb = _make_callback_update(12345, "lang:klingon")
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await callback_handler(cb, ctx)

    assert load_profile(12345)["language"] == "ru"


@pytest.mark.asyncio
async def test_language_roundtrip_ru_to_en_to_ru(tmp_knowledge_dir):
    from src.profile import init_profile, load_profile, save_profile
    from src.telegram_bot import callback_handler

    init_profile(12345)
    save_profile(12345, {"language": "ru", "persona": "X"})
    ctx = _make_context()

    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await callback_handler(_make_callback_update(12345, "lang:en"), ctx)
        assert load_profile(12345)["language"] == "en"
        await callback_handler(_make_callback_update(12345, "lang:ru"), ctx)
        assert load_profile(12345)["language"] == "ru"


# ── /get command + entry file downloads (Phase 7.9) ─────────────────────────


@pytest.mark.asyncio
async def test_cmd_get_no_args_empty_base_shows_helpful_message(tmp_knowledge_dir):
    """/get with no args and nothing in the knowledge base → empty-base
    reply, no keyboard."""
    from src.profile import init_profile
    from src.telegram_bot import cmd_get

    init_profile(12345)
    update = _make_update(chat_id=12345)
    ctx = _make_context(args=[])
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await cmd_get(update, ctx)

    call = update.message.reply_text.call_args
    text = call[0][0]
    assert "empty" in text.lower() or "📭" in text
    assert call.kwargs.get("reply_markup") is None


@pytest.mark.asyncio
async def test_cmd_get_no_args_shows_categories_list(
    tmp_knowledge_dir, sample_entry_kwargs
):
    """/get with no args + entries present → category picker keyboard."""
    from src.profile import init_profile
    from src.storage import _invalidate_entry_cache, save_entry
    from src.telegram_bot import cmd_get

    init_profile(12345)
    save_entry(12345, **sample_entry_kwargs, update_index=False)
    _invalidate_entry_cache(12345)

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=[])
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await cmd_get(update, ctx)

    call = update.message.reply_text.call_args
    keyboard = call.kwargs["reply_markup"]
    buttons = [btn for row in keyboard.inline_keyboard for btn in row]
    assert len(buttons) == 1
    assert "ai-agents" in buttons[0].text
    assert "(1)" in buttons[0].text
    assert buttons[0].callback_data == "getcat:ai-agents"


@pytest.mark.asyncio
async def test_cmd_get_not_found_for_unknown_id(tmp_knowledge_dir):
    """Unknown ID → 'not found' message with the offending id echoed back."""
    from src.profile import init_profile
    from src.telegram_bot import cmd_get

    init_profile(12345)
    update = _make_update(chat_id=12345)
    ctx = _make_context(args=["deadbeef"])
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await cmd_get(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "deadbeef" in text
    assert "not found" in text.lower()


@pytest.mark.asyncio
async def test_cmd_get_returns_body_with_download_buttons(
    tmp_knowledge_dir, sample_entry_kwargs
):
    """Happy path: save an entry, look it up by ID, verify the body text
    and the download keyboard show up."""
    from src.profile import init_profile
    from src.storage import (
        _invalidate_entry_cache,
        entry_id,
        save_entry,
    )
    from src.telegram_bot import cmd_get

    init_profile(12345)
    path = save_entry(12345, 
        **{**sample_entry_kwargs, "raw_text": "raw transcript body"},
        update_index=False,
    )
    _invalidate_entry_cache(12345)

    target = entry_id(12345, path)

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=[target])
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await cmd_get(update, ctx)

    call = update.message.reply_text.call_args
    text = call[0][0]
    # Body content surfaced
    assert "Summary" in text
    assert sample_entry_kwargs["title"] in text
    assert sample_entry_kwargs["source_url"] in text
    # Keyboard attached with both [md] and [raw] buttons (since raw_text
    # was written, the sidecar exists)
    keyboard = call.kwargs["reply_markup"]
    buttons = [btn for row in keyboard.inline_keyboard for btn in row]
    assert len(buttons) == 2
    assert any("md" in b.callback_data.lower() for b in buttons)
    assert any("raw" in b.callback_data.lower() for b in buttons)


@pytest.mark.asyncio
async def test_cmd_get_keyboard_always_shows_both_buttons(
    tmp_knowledge_dir, sample_entry_kwargs
):
    """Both [summary] and [full source] buttons are always shown, even
    when the raw-text sidecar doesn't exist on disk."""
    from src.profile import init_profile
    from src.storage import _invalidate_entry_cache, entry_id, save_entry
    from src.telegram_bot import cmd_get

    init_profile(12345)
    path = save_entry(12345, **sample_entry_kwargs, update_index=False)
    _invalidate_entry_cache(12345)

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=[entry_id(12345, path)])
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await cmd_get(update, ctx)

    call = update.message.reply_text.call_args
    keyboard = call.kwargs["reply_markup"]
    buttons = [btn for row in keyboard.inline_keyboard for btn in row]
    assert len(buttons) == 2
    assert any("md" in b.callback_data for b in buttons)
    assert any("raw" in b.callback_data for b in buttons)


def _make_callback_update_with_document(chat_id: int = 12345, data: str = ""):
    """Callback update with reply_document wired as AsyncMock."""
    update = _make_callback_update(chat_id=chat_id, data=data)
    update.callback_query.message.reply_document = AsyncMock()
    return update


@pytest.mark.asyncio
async def test_callback_entfile_md_sends_document(
    tmp_knowledge_dir, sample_entry_kwargs
):
    """`entfile:md:<id>` → reply_document called with the .md file handle."""
    from src.profile import init_profile
    from src.storage import _invalidate_entry_cache, entry_id, save_entry
    from src.telegram_bot import callback_handler

    init_profile(12345)
    path = save_entry(12345, **sample_entry_kwargs, update_index=False)
    _invalidate_entry_cache(12345)

    target_id = entry_id(12345, path)
    update = _make_callback_update_with_document(
        data=f"entfile:md:{target_id}"
    )
    ctx = _make_context()
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await callback_handler(update, ctx)

    update.callback_query.message.reply_document.assert_called_once()
    kwargs = update.callback_query.message.reply_document.call_args.kwargs
    assert kwargs["filename"] == path.name


@pytest.mark.asyncio
async def test_callback_entfile_raw_sends_sidecar(
    tmp_knowledge_dir, sample_entry_kwargs
):
    """`entfile:raw:<id>` → reply_document called with the .source.txt handle."""
    from src.profile import init_profile
    from src.storage import (
        _invalidate_entry_cache,
        entry_id,
        get_source_text_path,
        save_entry,
    )
    from src.telegram_bot import callback_handler

    init_profile(12345)
    path = save_entry(12345, 
        **{**sample_entry_kwargs, "raw_text": "raw transcript body"},
        update_index=False,
    )
    _invalidate_entry_cache(12345)

    target_id = entry_id(12345, path)
    update = _make_callback_update_with_document(
        data=f"entfile:raw:{target_id}"
    )
    ctx = _make_context()
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await callback_handler(update, ctx)

    update.callback_query.message.reply_document.assert_called_once()
    kwargs = update.callback_query.message.reply_document.call_args.kwargs
    assert kwargs["filename"] == get_source_text_path(path).name


@pytest.mark.asyncio
async def test_callback_entfile_raw_no_sidecar_falls_back_to_text(
    tmp_knowledge_dir, sample_entry_kwargs
):
    """`entfile:raw:<id>` on an entry without a sidecar → "no raw text"
    text message, NOT reply_document."""
    from src.profile import init_profile
    from src.storage import _invalidate_entry_cache, entry_id, save_entry
    from src.telegram_bot import callback_handler

    init_profile(12345)
    path = save_entry(12345, **sample_entry_kwargs, update_index=False)
    _invalidate_entry_cache(12345)

    target_id = entry_id(12345, path)
    update = _make_callback_update_with_document(
        data=f"entfile:raw:{target_id}"
    )
    ctx = _make_context()
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await callback_handler(update, ctx)

    update.callback_query.message.reply_document.assert_not_called()
    update.callback_query.message.reply_text.assert_called()
    text = update.callback_query.message.reply_text.call_args[0][0]
    assert "raw" in text.lower()


@pytest.mark.asyncio
async def test_callback_entfile_unknown_id(tmp_knowledge_dir):
    """Unknown entry id in callback → 'not found' text, no document send."""
    from src.profile import init_profile
    from src.telegram_bot import callback_handler

    init_profile(12345)
    update = _make_callback_update_with_document(data="entfile:md:cafebabe")
    ctx = _make_context()
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await callback_handler(update, ctx)

    update.callback_query.message.reply_document.assert_not_called()
    update.callback_query.message.reply_text.assert_called()
    text = update.callback_query.message.reply_text.call_args[0][0]
    assert "cafebabe" in text


# ── Phase 8: /get browser flow + multi-part rendering ─────────────────────


@pytest.mark.asyncio
async def test_cmd_get_direct_id_still_works(
    tmp_knowledge_dir, sample_entry_kwargs
):
    """Backward compat: /get <id> should still open the entry directly."""
    from src.profile import init_profile
    from src.storage import _invalidate_entry_cache, entry_id, save_entry
    from src.telegram_bot import cmd_get

    init_profile(12345)
    path = save_entry(12345, **sample_entry_kwargs, update_index=False)
    _invalidate_entry_cache(12345)

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=[entry_id(12345, path)])
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await cmd_get(update, ctx)

    call = update.message.reply_text.call_args
    text = call[0][0]
    assert sample_entry_kwargs["title"] in text
    # Has the download keyboard
    assert call.kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_callback_getcat_shows_entries_in_category(
    tmp_knowledge_dir, sample_entry_kwargs
):
    """getcat:<slug> → edits the category list into a 1-per-row file list."""
    from src.profile import init_profile
    from src.storage import _invalidate_entry_cache, entry_id, save_entry
    from src.telegram_bot import callback_handler

    init_profile(12345)
    path = save_entry(12345, **sample_entry_kwargs, update_index=False)
    _invalidate_entry_cache(12345)

    update = _make_callback_update(data="getcat:ai-agents")
    ctx = _make_context()
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await callback_handler(update, ctx)

    update.callback_query.edit_message_text.assert_called_once()
    call = update.callback_query.edit_message_text.call_args
    header = call[0][0]
    assert "ai-agents" in header
    keyboard = call.kwargs["reply_markup"]
    buttons = [btn for row in keyboard.inline_keyboard for btn in row]
    assert len(buttons) == 1
    assert sample_entry_kwargs["title"] in buttons[0].text
    assert buttons[0].callback_data == f"getent:{entry_id(12345, path)}"


@pytest.mark.asyncio
async def test_callback_getcat_empty_category_message(tmp_knowledge_dir):
    """getcat:<unknown> → 'no entries' reply, no keyboard edit."""
    from src.profile import init_profile
    from src.telegram_bot import callback_handler

    init_profile(12345)
    update = _make_callback_update(data="getcat:ghost-category")
    ctx = _make_context()
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await callback_handler(update, ctx)

    update.callback_query.edit_message_text.assert_not_called()
    update.callback_query.message.reply_text.assert_called_once()
    text = update.callback_query.message.reply_text.call_args[0][0]
    assert "📭" in text or "no" in text.lower() or "нет" in text.lower()


@pytest.mark.asyncio
async def test_callback_getent_shows_detail_with_buttons(
    tmp_knowledge_dir, sample_entry_kwargs
):
    """getent:<id> → replies with detail body + download keyboard."""
    from src.profile import init_profile
    from src.storage import _invalidate_entry_cache, entry_id, save_entry
    from src.telegram_bot import callback_handler

    init_profile(12345)
    path = save_entry(12345, 
        **{**sample_entry_kwargs, "raw_text": "raw transcript body"},
        update_index=False,
    )
    _invalidate_entry_cache(12345)

    update = _make_callback_update(data=f"getent:{entry_id(12345, path)}")
    ctx = _make_context()
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await callback_handler(update, ctx)

    update.callback_query.message.reply_text.assert_called_once()
    call = update.callback_query.message.reply_text.call_args
    text = call[0][0]
    assert sample_entry_kwargs["title"] in text
    keyboard = call.kwargs["reply_markup"]
    buttons = [btn for row in keyboard.inline_keyboard for btn in row]
    assert len(buttons) == 2
    assert any("md" in b.callback_data.lower() for b in buttons)
    assert any("raw" in b.callback_data.lower() for b in buttons)


@pytest.mark.asyncio
async def test_callback_getent_unknown_id_error_message(tmp_knowledge_dir):
    """getent:<missing> → not-found text, no detail."""
    from src.profile import init_profile
    from src.telegram_bot import callback_handler

    init_profile(12345)
    update = _make_callback_update(data="getent:cafebabe")
    ctx = _make_context()
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await callback_handler(update, ctx)

    update.callback_query.message.reply_text.assert_called_once()
    text = update.callback_query.message.reply_text.call_args[0][0]
    assert "cafebabe" in text


# ── _split_long_message unit tests ────────────────────────────────────────


def test_split_long_message_single_chunk():
    from src.telegram_bot import _split_long_message

    assert _split_long_message("short text", limit=100) == ["short text"]


def test_split_long_message_paragraph_boundary():
    from src.telegram_bot import _split_long_message

    text = "A" * 40 + "\n\n" + "B" * 40 + "\n\n" + "C" * 40
    chunks = _split_long_message(text, limit=90)
    assert len(chunks) >= 2
    assert chunks[0].startswith("A")
    assert all(len(c) <= 90 for c in chunks)
    # Recombined content preserves all payload characters (whitespace
    # between chunks may collapse, so we check per-chunk presence).
    assert any("A" * 40 in c for c in chunks)
    assert any("B" * 40 in c for c in chunks)
    assert any("C" * 40 in c for c in chunks)


def test_split_long_message_line_boundary_fallback():
    from src.telegram_bot import _split_long_message

    # No paragraph breaks, just line breaks
    text = "line-A" * 20 + "\n" + "line-B" * 20
    chunks = _split_long_message(text, limit=80)
    assert len(chunks) >= 2
    assert all(len(c) <= 80 for c in chunks)


def test_split_long_message_hard_cut_fallback():
    from src.telegram_bot import _split_long_message

    # One long line with no breaks — force the hard-cut fallback.
    text = "x" * 500
    chunks = _split_long_message(text, limit=100)
    assert len(chunks) == 5
    assert all(len(c) <= 100 for c in chunks)
    assert "".join(chunks) == text


@pytest.mark.asyncio
async def test_long_summary_sends_multipart_with_numbering(
    tmp_knowledge_dir, sample_entry_kwargs
):
    """A summary longer than 4096 chars is split into (1/N) … (N/N)
    messages, and only the final message carries the keyboard."""
    from src.profile import init_profile
    from src.storage import _invalidate_entry_cache, entry_id, save_entry
    from src.telegram_bot import cmd_get

    init_profile(12345)
    # ~9 KB of detailed notes → forces at least 2 chunks after wrapping
    big_notes = "\n\n".join([f"Paragraph {i} " + ("x" * 200) for i in range(40)])
    path = save_entry(12345, 
        **{**sample_entry_kwargs, "detailed_notes": big_notes},
        update_index=False,
    )
    _invalidate_entry_cache(12345)

    update = _make_update(chat_id=12345)
    ctx = _make_context(args=[entry_id(12345, path)])
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await cmd_get(update, ctx)

    calls = update.message.reply_text.call_args_list
    assert len(calls) >= 2
    first_text = calls[0][0][0]
    last_text = calls[-1][0][0]
    assert first_text.startswith(f"(1/{len(calls)}) ")
    assert last_text.startswith(f"({len(calls)}/{len(calls)}) ")
    # Keyboard only on the last chunk
    assert calls[0].kwargs.get("reply_markup") is None
    assert calls[-1].kwargs.get("reply_markup") is not None


@pytest.mark.asyncio
async def test_cmd_recent_shows_title_and_url(
    tmp_knowledge_dir, sample_entry_kwargs
):
    """/recent shows title, source_url, and /get hint — no entry_id."""
    from src.profile import init_profile
    from src.storage import _invalidate_entry_cache, entry_id, save_entry
    from src.telegram_bot import cmd_recent

    init_profile(12345)
    path = save_entry(12345, **sample_entry_kwargs, update_index=False)
    _invalidate_entry_cache(12345)

    update = _make_update(chat_id=12345)
    ctx = _make_context()
    with patch("src.telegram_bot.TELEGRAM_CHAT_IDS", [12345]):
        await cmd_recent(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    # Title and source URL present
    assert sample_entry_kwargs["title"] in text
    assert sample_entry_kwargs["source_url"] in text
    # Entry ID is NOT displayed to the user
    assert f"[{entry_id(12345, path)}]" not in text
    # Discoverability hint for /get is appended
    assert "/get" in text
