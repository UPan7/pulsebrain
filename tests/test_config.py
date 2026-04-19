"""Tests for src.config — thread-safe per-user categories and channels."""

from __future__ import annotations

import threading


CHAT_ID = 12345


def test_load_categories_includes_defaults(tmp_knowledge_dir, chat_id):
    """All default categories always present."""
    from src.config import _DEFAULT_CATEGORIES, ensure_user_dirs, load_categories

    ensure_user_dirs(chat_id)
    cats = load_categories(chat_id)
    for slug in _DEFAULT_CATEGORIES:
        assert slug in cats


def test_load_categories_merges_custom(tmp_knowledge_dir, chat_id):
    """Custom categories.yml entries are merged with defaults."""
    import yaml
    from src.config import ensure_user_dirs, load_categories, user_categories_file

    ensure_user_dirs(chat_id)
    user_categories_file(chat_id).write_text(
        yaml.dump({"custom-cat": "Custom Category"}), encoding="utf-8"
    )

    cats = load_categories(chat_id)
    assert "custom-cat" in cats
    assert "ai-agents" in cats  # default still present


def test_add_category_persists(tmp_knowledge_dir, chat_id):
    """add_category writes to the user's file and reloads."""
    from src.config import add_category, ensure_user_dirs, load_categories

    ensure_user_dirs(chat_id)
    add_category(chat_id, "new-cat", "New Category")

    cats = load_categories(chat_id)
    assert "new-cat" in cats
    assert cats["new-cat"] == "New Category"


def test_add_category_thread_safe(tmp_knowledge_dir, chat_id):
    """5 threads adding categories — all survive."""
    from src.config import add_category, ensure_user_dirs, load_categories

    ensure_user_dirs(chat_id)

    def add(i: int):
        add_category(chat_id, f"thread-cat-{i}", f"Thread Category {i}")

    threads = [threading.Thread(target=add, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    cats = load_categories(chat_id)
    for i in range(5):
        assert f"thread-cat-{i}" in cats, f"thread-cat-{i} missing after concurrent writes"


# ── load_channels / save_channels ──────────────────────────────────────────


def test_load_channels_returns_empty_when_missing(tmp_knowledge_dir, chat_id):
    from src.config import ensure_user_dirs, load_channels

    ensure_user_dirs(chat_id)
    assert load_channels(chat_id) == []


def test_load_channels_returns_empty_when_yaml_empty(tmp_knowledge_dir, chat_id):
    from src.config import ensure_user_dirs, load_channels, user_channels_file

    ensure_user_dirs(chat_id)
    user_channels_file(chat_id).write_text("", encoding="utf-8")
    assert load_channels(chat_id) == []


def test_load_channels_returns_channels_from_yaml(tmp_knowledge_dir, chat_id):
    import yaml
    from src.config import ensure_user_dirs, load_channels, user_channels_file

    ensure_user_dirs(chat_id)
    data = {"channels": [
        {"name": "Ch1", "id": "UC1", "category": "ai-news", "enabled": True},
    ]}
    user_channels_file(chat_id).write_text(yaml.dump(data), encoding="utf-8")

    channels = load_channels(chat_id)
    assert len(channels) == 1
    assert channels[0]["name"] == "Ch1"


def test_save_channels_roundtrip(tmp_knowledge_dir, chat_id):
    from src.config import ensure_user_dirs, load_channels, save_channels

    ensure_user_dirs(chat_id)
    payload = [
        {"name": "Ch1", "id": "UC1", "category": "ai-news", "enabled": True},
        {"name": "Ch2", "id": "UC2", "category": "wp", "enabled": False},
    ]
    save_channels(chat_id, payload)
    loaded = load_channels(chat_id)
    assert loaded == payload
