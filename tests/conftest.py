"""Shared fixtures for PulseBrain tests (multi-tenant)."""

from __future__ import annotations

# Stub heavy native deps so tests run in minimal environments where
# feedparser / trafilatura are not installed. Real installs (if present)
# take precedence because we only stub when the module is missing.
import sys
import types

if "feedparser" not in sys.modules:
    _fp = types.ModuleType("feedparser")
    _fp.parse = lambda *a, **k: types.SimpleNamespace(entries=[])
    sys.modules["feedparser"] = _fp

if "trafilatura" not in sys.modules:
    _tf = types.ModuleType("trafilatura")
    _tf.fetch_url = lambda *a, **k: None
    _tf.extract = lambda *a, **k: None
    _tf.extract_metadata = lambda *a, **k: None
    sys.modules["trafilatura"] = _tf

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


# Canonical chat_ids used across tests.
CHAT_ID = 12345
OTHER_CHAT_ID = 67890


# ---------------------------------------------------------------------------
# Filesystem isolation: redirect DATA_DIR / KNOWLEDGE_DIR / USERS_DIR to tmp
# ---------------------------------------------------------------------------

@pytest.fixture()
def chat_id() -> int:
    """Primary chat_id for single-user-flavored tests."""
    return CHAT_ID


@pytest.fixture()
def other_chat_id() -> int:
    """Second chat_id for multi-tenant isolation tests."""
    return OTHER_CHAT_ID


@pytest.fixture()
def tmp_knowledge_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect the root data/ and knowledge/ directories into tmp_path.

    Per-user paths (``data/users/{chat_id}/...``, ``knowledge/{chat_id}/...``)
    are derived from these at call time, so patching the roots is enough —
    no need to patch each per-user path individually.
    """
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    users = data / "users"
    users.mkdir()
    migration_marker = data / ".migrated_v1"
    # Legacy paths (root of BASE_DIR / DATA_DIR) — tests that still
    # reference them directly can use these tmp copies.
    legacy_processed = data / "processed.json"
    legacy_pending = data / "pending.json"
    legacy_rejected = data / "rejected_log.jsonl"
    legacy_profile = data / "user_profile.yaml"
    legacy_categories = data / "categories.yml"
    legacy_channels = tmp_path / "channels.yml"

    import src.config
    import src.migration
    import src.pending
    import src.profile
    import src.storage

    monkeypatch.setattr(src.config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(src.config, "KNOWLEDGE_DIR", knowledge)
    monkeypatch.setattr(src.config, "DATA_DIR", data)
    monkeypatch.setattr(src.config, "USERS_DIR", users)
    monkeypatch.setattr(src.config, "MIGRATION_MARKER_FILE", migration_marker)
    monkeypatch.setattr(src.config, "LEGACY_PROCESSED_FILE", legacy_processed)
    monkeypatch.setattr(src.config, "LEGACY_PENDING_FILE", legacy_pending)
    monkeypatch.setattr(src.config, "LEGACY_REJECTED_LOG_FILE", legacy_rejected)
    monkeypatch.setattr(src.config, "LEGACY_PROFILE_FILE", legacy_profile)
    monkeypatch.setattr(src.config, "LEGACY_CATEGORIES_FILE", legacy_categories)
    monkeypatch.setattr(src.config, "LEGACY_CHANNELS_FILE", legacy_channels)

    # Mirror the rebound paths on modules that imported them at load time.
    for mod in (src.storage, src.pending, src.profile, src.migration):
        if hasattr(mod, "KNOWLEDGE_DIR"):
            monkeypatch.setattr(mod, "KNOWLEDGE_DIR", knowledge)

    # src.migration imported every LEGACY_* and the marker at load time,
    # so patching on src.config alone isn't enough — rebind the mirrors.
    monkeypatch.setattr(src.migration, "DATA_DIR", data)
    monkeypatch.setattr(src.migration, "MIGRATION_MARKER_FILE", migration_marker)
    monkeypatch.setattr(src.migration, "LEGACY_PROCESSED_FILE", legacy_processed)
    monkeypatch.setattr(src.migration, "LEGACY_PENDING_FILE", legacy_pending)
    monkeypatch.setattr(src.migration, "LEGACY_REJECTED_LOG_FILE", legacy_rejected)
    monkeypatch.setattr(src.migration, "LEGACY_PROFILE_FILE", legacy_profile)
    monkeypatch.setattr(src.migration, "LEGACY_CATEGORIES_FILE", legacy_categories)
    monkeypatch.setattr(src.migration, "LEGACY_CHANNELS_FILE", legacy_channels)

    # Per-user helpers read these module globals via the closure, so just
    # reset the caches so tests start clean.
    monkeypatch.setattr(src.storage, "_processed_caches", {})
    monkeypatch.setattr(src.storage, "_processed_locks", {})
    monkeypatch.setattr(src.storage, "_entry_caches", {})
    monkeypatch.setattr(src.pending, "_pending_caches", {})
    monkeypatch.setattr(src.pending, "_pending_locks", {})
    monkeypatch.setattr(src.profile, "_profile_caches", {})
    monkeypatch.setattr(src.profile, "_profile_locks", {})
    monkeypatch.setattr(src.config, "_categories_locks", {})

    return tmp_path


@pytest.fixture()
def tmp_user(tmp_knowledge_dir: Path, chat_id: int):
    """Bring up a single chat_id's dirs inside the isolated tmp_knowledge_dir."""
    from src.config import ensure_user_dirs

    ensure_user_dirs(chat_id)
    return chat_id


@pytest.fixture(autouse=True)
def _reset_openai_client_caches(monkeypatch: pytest.MonkeyPatch):
    """Drop the module-level cached OpenAI clients between tests.

    categorize / summarize memoize `openai.OpenAI()` at module scope to reuse
    the httpx pool in production. Tests patch `openai.OpenAI` inside a context
    manager, so the cached instance from a previous test would otherwise leak
    into the next.
    """
    import src.categorize
    import src.summarize

    monkeypatch.setattr(src.categorize, "_client_cache", None, raising=False)
    monkeypatch.setattr(src.summarize, "_client_cache", None, raising=False)


# ---------------------------------------------------------------------------
# OpenAI / OpenRouter mock
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_openai_client():
    """Return a factory that builds a mock openai.OpenAI client."""
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
    """Factory for telegram.Update mocks. Defaults to the canonical chat_id."""
    def _factory(chat_id: int = CHAT_ID, text: str = "", callback_data: str | None = None):
        update = MagicMock()
        update.effective_chat.id = chat_id
        update.effective_user = MagicMock()
        update.effective_user.language_code = "en"
        update.message.text = text
        update.message.reply_text = AsyncMock(return_value=MagicMock(
            edit_text=AsyncMock(),
        ))

        if callback_data is not None:
            update.callback_query = MagicMock()
            update.callback_query.data = callback_data
            update.callback_query.answer = AsyncMock()
            update.callback_query.edit_message_reply_markup = AsyncMock()
            update.callback_query.edit_message_text = AsyncMock()
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


@pytest.fixture()
def allowlist_env(monkeypatch: pytest.MonkeyPatch):
    """Set TELEGRAM_CHAT_IDS to [CHAT_ID, OTHER_CHAT_ID] for handler tests."""
    import src.config
    import src.telegram_bot
    import src.scheduler

    monkeypatch.setattr(src.config, "TELEGRAM_CHAT_IDS", [CHAT_ID, OTHER_CHAT_ID])
    monkeypatch.setattr(src.config, "ADMIN_CHAT_ID", CHAT_ID)
    monkeypatch.setattr(src.telegram_bot, "TELEGRAM_CHAT_IDS", [CHAT_ID, OTHER_CHAT_ID])
    monkeypatch.setattr(src.scheduler, "TELEGRAM_CHAT_IDS", [CHAT_ID, OTHER_CHAT_ID])


# ---------------------------------------------------------------------------
# Sample data helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def sample_summary_dict() -> dict[str, Any]:
    """Canonical summarize_content() output for reuse across tests.

    length_mode tracks the length budget the summarizer picked
    (short/medium/long/xlong). For the tiny ``"content"`` / ``"c"``
    inputs used in these tests, mode is always "short".
    """
    return {
        "summary_bullets": ["Bullet one", "Bullet two"],
        "detailed_notes": "Detailed notes paragraph.",
        "key_insights": ["Insight one"],
        "action_items": ["Action one"],
        "topics": ["ai", "agents"],
        "relevance_score": 8,
        "length_mode": "short",
    }


@pytest.fixture()
def sample_entry_kwargs() -> dict[str, Any]:
    """Valid kwargs for ``storage.save_entry`` (chat_id passed positionally)."""
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


@pytest.fixture()
def sample_pending_kwargs() -> dict[str, Any]:
    """Valid kwargs for ``pending.stage_pending`` (chat_id passed positionally)."""
    return {
        "content_id": "yt:abc123",
        "source_url": "https://www.youtube.com/watch?v=abc123",
        "source_type": "youtube_video",
        "source_name": "TestChannel",
        "title": "Test Video Title",
        "date_str": "2025-06-15",
        "category": "ai-agents",
        "is_new_category": False,
        "relevance": 8,
        "topics": ["ai", "agents"],
        "summary_bullets": ["Bullet one", "Bullet two"],
        "detailed_notes": "Detailed notes paragraph.",
        "key_insights": ["Insight one"],
        "action_items": ["Action one"],
    }
