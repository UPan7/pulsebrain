"""Tests for src.main — config validation and directory bootstrap."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


# ── _validate_config ───────────────────────────────────────────────────────


def test_validate_config_passes_when_set():
    from src.main import _validate_config

    with (
        patch("src.main.TELEGRAM_BOT_TOKEN", "tok"),
        patch("src.main.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.main.OPENROUTER_API_KEY", "key"),
    ):
        _validate_config()


def test_validate_config_raises_on_missing_token():
    from src.main import _validate_config

    with (
        patch("src.main.TELEGRAM_BOT_TOKEN", ""),
        patch("src.main.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.main.OPENROUTER_API_KEY", "key"),
    ):
        with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
            _validate_config()


def test_validate_config_raises_on_empty_chat_ids():
    from src.main import _validate_config

    with (
        patch("src.main.TELEGRAM_BOT_TOKEN", "tok"),
        patch("src.main.TELEGRAM_CHAT_IDS", []),
        patch("src.main.OPENROUTER_API_KEY", "key"),
    ):
        with pytest.raises(RuntimeError, match="TELEGRAM_CHAT_IDS"):
            _validate_config()


def test_validate_config_raises_on_missing_openrouter_key():
    from src.main import _validate_config

    with (
        patch("src.main.TELEGRAM_BOT_TOKEN", "tok"),
        patch("src.main.TELEGRAM_CHAT_IDS", [12345]),
        patch("src.main.OPENROUTER_API_KEY", ""),
    ):
        with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
            _validate_config()


def test_validate_config_lists_all_missing():
    from src.main import _validate_config

    with (
        patch("src.main.TELEGRAM_BOT_TOKEN", ""),
        patch("src.main.TELEGRAM_CHAT_IDS", []),
        patch("src.main.OPENROUTER_API_KEY", ""),
    ):
        with pytest.raises(RuntimeError) as exc:
            _validate_config()

    msg = str(exc.value)
    assert "TELEGRAM_BOT_TOKEN" in msg
    assert "TELEGRAM_CHAT_IDS" in msg
    assert "OPENROUTER_API_KEY" in msg


# ── _ensure_directories ────────────────────────────────────────────────────


def test_ensure_directories_creates_missing(tmp_path: Path):
    from src.main import _ensure_directories

    knowledge = tmp_path / "knowledge"
    data = tmp_path / "data"
    assert not knowledge.exists()
    assert not data.exists()

    with (
        patch("src.main.KNOWLEDGE_DIR", knowledge),
        patch("src.main.DATA_DIR", data),
    ):
        _ensure_directories()

    assert knowledge.is_dir()
    assert data.is_dir()


def test_ensure_directories_idempotent(tmp_path: Path):
    from src.main import _ensure_directories

    knowledge = tmp_path / "knowledge"
    data = tmp_path / "data"
    knowledge.mkdir()
    data.mkdir()

    with (
        patch("src.main.KNOWLEDGE_DIR", knowledge),
        patch("src.main.DATA_DIR", data),
    ):
        _ensure_directories()
        _ensure_directories()

    assert knowledge.is_dir()
    assert data.is_dir()
