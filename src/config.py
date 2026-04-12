"""Load environment variables, channels.yml, and constants."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any

import yaml

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
DATA_DIR = BASE_DIR / "data"
CHANNELS_FILE = BASE_DIR / "channels.yml"
PROCESSED_FILE = DATA_DIR / "processed.json"
PENDING_FILE = DATA_DIR / "pending.json"
REJECTED_LOG_FILE = DATA_DIR / "rejected_log.jsonl"

# ── Environment ──────────────────────────────────────────────────────────────
OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")
TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: int = int(os.environ.get("TELEGRAM_CHAT_ID", "0"))
CHECK_INTERVAL_MINUTES: int = int(os.environ.get("CHECK_INTERVAL_MINUTES", "30"))
# Default minimum relevance for auto-fetched videos from subscribed channels.
# Below this threshold, the scheduler silently rejects the entry (no
# notification, no .md file) to keep low-signal content out of the queue.
# Per-channel overrides live in channels.yml as `min_relevance: <int>`.
MIN_RELEVANCE_THRESHOLD: int = int(os.environ.get("MIN_RELEVANCE_THRESHOLD", "4"))
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
TRANSCRIPT_LANGUAGES: list[str] = os.environ.get(
    "TRANSCRIPT_LANGUAGES", "en,de,ru"
).split(",")

# ── Proxy (rotating residential) ────────────────────────────────────────────
PROXY_CREDENTIALS_FILE = BASE_DIR / "proxy-credentials"

# ── LLM model (OpenRouter) ──────────────────────────────────────────────────
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
LLM_MODEL = "openai/gpt-5.4-nano"

# ── Categories ───────────────────────────────────────────────────────────────
_DEFAULT_CATEGORIES: dict[str, str] = {
    "ai-agents": "AI Agents & Multi-Agent",
    "claude-code": "Claude Code & AI Dev",
    "wordpress": "WordPress & WooCommerce",
    "devops": "DevOps & Infrastructure",
    "n8n-automation": "N8N & Automation",
    "ai-news": "AI News & Releases",
    "business": "Business & Freelancing",
}

CATEGORIES_FILE = DATA_DIR / "categories.yml"

_categories_lock = threading.Lock()


def load_categories() -> dict[str, str]:
    """Load categories: defaults + user-added from categories.yml."""
    with _categories_lock:
        cats = dict(_DEFAULT_CATEGORIES)
        if CATEGORIES_FILE.exists():
            with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
                custom = yaml.safe_load(f) or {}
            cats.update(custom)
        return cats


def add_category(slug: str, description: str) -> None:
    """Add a new category and persist it."""
    global CATEGORIES
    with _categories_lock:
        existing: dict[str, str] = {}
        if CATEGORIES_FILE.exists():
            with open(CATEGORIES_FILE, "r", encoding="utf-8") as f:
                existing = yaml.safe_load(f) or {}
        existing[slug] = description
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(CATEGORIES_FILE, "w", encoding="utf-8") as f:
            yaml.dump(existing, f, allow_unicode=True, default_flow_style=False)
    CATEGORIES = load_categories()


CATEGORIES: dict[str, str] = load_categories()

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
