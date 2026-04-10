"""Load environment variables, channels.yml, and constants."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
DATA_DIR = BASE_DIR / "data"
CHANNELS_FILE = BASE_DIR / "channels.yml"
PROCESSED_FILE = DATA_DIR / "processed.json"

# ── Environment ──────────────────────────────────────────────────────────────
OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")
TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: int = int(os.environ.get("TELEGRAM_CHAT_ID", "0"))
CHECK_INTERVAL_MINUTES: int = int(os.environ.get("CHECK_INTERVAL_MINUTES", "30"))
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
TRANSCRIPT_LANGUAGES: list[str] = os.environ.get(
    "TRANSCRIPT_LANGUAGES", "en,de,ru"
).split(",")

# ── LLM model (OpenRouter) ──────────────────────────────────────────────────
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
LLM_MODEL = "openai/gpt-5.4-nano"

# ── Categories ───────────────────────────────────────────────────────────────
CATEGORIES: dict[str, str] = {
    "ai-agents": "AI Agents & Multi-Agent",
    "claude-code": "Claude Code & AI Dev",
    "wordpress": "WordPress & WooCommerce",
    "devops": "DevOps & Infrastructure",
    "n8n-automation": "N8N & Automation",
    "ai-news": "AI News & Releases",
    "business": "Business & Freelancing",
}

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pulsebrain")


def load_channels() -> list[dict[str, Any]]:
    """Load channel list from channels.yml."""
    if not CHANNELS_FILE.exists():
        return []
    with open(CHANNELS_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("channels", [])


def save_channels(channels: list[dict[str, Any]]) -> None:
    """Write channel list back to channels.yml."""
    with open(CHANNELS_FILE, "w", encoding="utf-8") as f:
        yaml.dump({"channels": channels}, f, allow_unicode=True, default_flow_style=False)
