"""Tests for src.config — thread-safe categories."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest


@pytest.fixture()
def tmp_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolate config paths to tmp."""
    data = tmp_path / "data"
    data.mkdir()
    categories_file = data / "categories.yml"

    import src.config
    monkeypatch.setattr(src.config, "DATA_DIR", data)
    monkeypatch.setattr(src.config, "CATEGORIES_FILE", categories_file)
    # Reset CATEGORIES to defaults
    monkeypatch.setattr(src.config, "CATEGORIES", dict(src.config._DEFAULT_CATEGORIES))
    return tmp_path


def test_load_categories_includes_defaults(tmp_config_dir):
    """All 7 default categories always present."""
    from src.config import load_categories, _DEFAULT_CATEGORIES

    cats = load_categories()
    for slug in _DEFAULT_CATEGORIES:
        assert slug in cats


def test_load_categories_merges_custom(tmp_config_dir):
    """Custom categories.yml entries are merged with defaults."""
    import src.config
    import yaml

    src.config.CATEGORIES_FILE.write_text(
        yaml.dump({"custom-cat": "Custom Category"}), encoding="utf-8"
    )

    cats = src.config.load_categories()
    assert "custom-cat" in cats
    assert "ai-agents" in cats  # default still present


def test_add_category_persists(tmp_config_dir):
    """add_category writes to file and reloads."""
    from src.config import add_category, load_categories

    add_category("new-cat", "New Category")

    cats = load_categories()
    assert "new-cat" in cats
    assert cats["new-cat"] == "New Category"


def test_add_category_thread_safe(tmp_config_dir):
    """5 threads adding categories — all survive."""
    from src.config import add_category, load_categories

    def add(i: int):
        add_category(f"thread-cat-{i}", f"Thread Category {i}")

    threads = [threading.Thread(target=add, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    cats = load_categories()
    for i in range(5):
        assert f"thread-cat-{i}" in cats, f"thread-cat-{i} missing after concurrent writes"


# ── load_channels / save_channels ──────────────────────────────────────────


@pytest.fixture()
def tmp_channels_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import src.config
    f = tmp_path / "channels.yml"
    monkeypatch.setattr(src.config, "CHANNELS_FILE", f)
    return f


def test_load_channels_returns_empty_when_missing(tmp_channels_file):
    from src.config import load_channels
    assert load_channels() == []


def test_load_channels_returns_empty_when_yaml_empty(tmp_channels_file):
    from src.config import load_channels
    tmp_channels_file.write_text("", encoding="utf-8")
    assert load_channels() == []


def test_load_channels_returns_channels_from_yaml(tmp_channels_file):
    import yaml
    from src.config import load_channels

    data = {"channels": [
        {"name": "Ch1", "id": "UC1", "category": "ai-news", "enabled": True},
    ]}
    tmp_channels_file.write_text(yaml.dump(data), encoding="utf-8")

    channels = load_channels()
    assert len(channels) == 1
    assert channels[0]["name"] == "Ch1"


def test_save_channels_roundtrip(tmp_channels_file):
    from src.config import load_channels, save_channels

    payload = [
        {"name": "Ch1", "id": "UC1", "category": "ai-news", "enabled": True},
        {"name": "Ch2", "id": "UC2", "category": "wp", "enabled": False},
    ]
    save_channels(payload)
    loaded = load_channels()
    assert loaded == payload
