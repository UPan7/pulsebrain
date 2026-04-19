"""Tests for src.config — thread-safe per-user categories and channels."""

from __future__ import annotations

import threading


CHAT_ID = 12345


# ── Allowlist parser (TELEGRAM_CHAT_IDS) ──────────────────────────────────


def test_parse_chat_entries_id_only():
    from src.config import _parse_chat_entries

    ids, labels = _parse_chat_entries("12345,67890")
    assert ids == [12345, 67890]
    assert labels == {}


def test_parse_chat_entries_with_labels():
    from src.config import _parse_chat_entries

    ids, labels = _parse_chat_entries("12345:Admin,67890:Paolo Santoro")
    assert ids == [12345, 67890]
    assert labels == {12345: "Admin", 67890: "Paolo Santoro"}


def test_parse_chat_entries_mixed():
    from src.config import _parse_chat_entries

    ids, labels = _parse_chat_entries("12345:Owner, 67890 ,99999:Alena")
    assert ids == [12345, 67890, 99999]
    assert labels == {12345: "Owner", 99999: "Alena"}


def test_parse_chat_entries_skips_duplicates_and_invalid():
    from src.config import _parse_chat_entries

    ids, labels = _parse_chat_entries("12345:A,,abc:X,12345:Duplicate,67890")
    assert ids == [12345, 67890]
    assert labels == {12345: "A"}  # first label wins


def test_load_categories_empty_when_no_file(tmp_knowledge_dir, chat_id):
    """Brand-new user with no categories.yml gets an empty dict — no shared defaults."""
    from src.config import ensure_user_dirs, load_categories

    ensure_user_dirs(chat_id)
    assert load_categories(chat_id) == {}


def test_load_categories_returns_only_user_entries(tmp_knowledge_dir, chat_id):
    """categories.yml is the sole source of truth — no defaults injected."""
    import yaml
    from src.config import ensure_user_dirs, load_categories, user_categories_file

    ensure_user_dirs(chat_id)
    user_categories_file(chat_id).write_text(
        yaml.dump({"custom-cat": "Custom Category", "another": "Another"}),
        encoding="utf-8",
    )

    cats = load_categories(chat_id)
    assert cats == {"custom-cat": "Custom Category", "another": "Another"}


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
