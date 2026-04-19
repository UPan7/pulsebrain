"""Acceptance tests: multi-tenant data isolation between chat_ids."""

from __future__ import annotations

import pytest


def test_processed_is_isolated_per_chat_id(tmp_knowledge_dir, chat_id, other_chat_id):
    """Marking a content_id as processed for one chat must not leak to another."""
    from src.config import ensure_user_dirs
    from src.storage import is_processed, mark_processed

    ensure_user_dirs(chat_id)
    ensure_user_dirs(other_chat_id)

    mark_processed(chat_id, "yt:abc123")

    assert is_processed(chat_id, "yt:abc123") is True
    assert is_processed(other_chat_id, "yt:abc123") is False


def test_pending_is_isolated_per_chat_id(tmp_knowledge_dir, chat_id, other_chat_id, sample_pending_kwargs):
    """Staged entries for one user are invisible to another."""
    from src.config import ensure_user_dirs
    from src.pending import list_pending, stage_pending

    ensure_user_dirs(chat_id)
    ensure_user_dirs(other_chat_id)

    stage_pending(chat_id, **sample_pending_kwargs)

    assert len(list_pending(chat_id)) == 1
    assert len(list_pending(other_chat_id)) == 0


def test_profile_language_is_isolated_per_chat_id(tmp_knowledge_dir, chat_id, other_chat_id):
    """Each chat_id keeps its own language preference."""
    from src.config import ensure_user_dirs
    from src.profile import get_language, save_profile

    ensure_user_dirs(chat_id)
    ensure_user_dirs(other_chat_id)

    save_profile(chat_id, {"language": "ru", "persona": "A"})
    save_profile(other_chat_id, {"language": "de", "persona": "B"})

    assert get_language(chat_id) == "ru"
    assert get_language(other_chat_id) == "de"


def test_channels_are_isolated_per_chat_id(tmp_knowledge_dir, chat_id, other_chat_id):
    """Adding a channel for one user doesn't add it for another."""
    from src.config import ensure_user_dirs, load_channels, save_channels

    ensure_user_dirs(chat_id)
    ensure_user_dirs(other_chat_id)

    save_channels(chat_id, [{"name": "A", "id": "UCA", "category": "ai-news", "enabled": True}])
    save_channels(other_chat_id, [{"name": "B", "id": "UCB", "category": "devops", "enabled": True}])

    a = load_channels(chat_id)
    b = load_channels(other_chat_id)
    assert len(a) == 1 and a[0]["id"] == "UCA"
    assert len(b) == 1 and b[0]["id"] == "UCB"


def test_categories_are_isolated_per_chat_id(tmp_knowledge_dir, chat_id, other_chat_id):
    """Categories are fully per-user — no shared defaults leak across tenants."""
    from src.config import add_category, ensure_user_dirs, load_categories

    ensure_user_dirs(chat_id)
    ensure_user_dirs(other_chat_id)

    add_category(chat_id, "my-custom", "My custom category")
    add_category(other_chat_id, "their-thing", "Their thing")

    cats_a = load_categories(chat_id)
    cats_b = load_categories(other_chat_id)

    assert cats_a == {"my-custom": "My custom category"}
    assert cats_b == {"their-thing": "Their thing"}
    # Explicitly: no overlap.
    assert not (set(cats_a) & set(cats_b))


def test_knowledge_is_isolated_per_chat_id(tmp_knowledge_dir, chat_id, other_chat_id, sample_entry_kwargs):
    """save_entry writes into the per-user tree only; other users don't see it."""
    from src.config import ensure_user_dirs
    from src.storage import get_recent_entries, save_entry

    ensure_user_dirs(chat_id)
    ensure_user_dirs(other_chat_id)

    save_entry(chat_id, **sample_entry_kwargs)

    assert len(get_recent_entries(chat_id)) == 1
    assert len(get_recent_entries(other_chat_id)) == 0


def test_allowlist_rejects_unknown_chat_id(allowlist_env, mock_telegram_update):
    """_authorized returns False for a chat_id not in TELEGRAM_CHAT_IDS."""
    from src.telegram_bot import _authorized

    allowed = mock_telegram_update(chat_id=12345)
    denied = mock_telegram_update(chat_id=99999)

    assert _authorized(allowed) is True
    assert _authorized(denied) is False
