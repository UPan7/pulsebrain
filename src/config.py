"""Load environment variables, per-user paths, and constants.

Multi-tenant: one container, one bot, routing by ``chat_id``.
Every per-user artifact lives under ``data/users/{chat_id}/`` or
``knowledge/{chat_id}/``.  The legacy single-user layout (files at the
root of ``data/`` and ``channels.yml``) is migrated to the admin's
namespace on first startup by :mod:`src.migration`.
"""

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
USERS_DIR = DATA_DIR / "users"
MIGRATION_MARKER_FILE = DATA_DIR / ".migrated_v1"

# Legacy single-user paths — kept so the one-shot migrator can find them.
# All runtime code must use the per-user helpers (user_*_file / user_*_dir).
LEGACY_CHANNELS_FILE = BASE_DIR / "channels.yml"
LEGACY_PROCESSED_FILE = DATA_DIR / "processed.json"
LEGACY_PENDING_FILE = DATA_DIR / "pending.json"
LEGACY_REJECTED_LOG_FILE = DATA_DIR / "rejected_log.jsonl"
LEGACY_PROFILE_FILE = DATA_DIR / "user_profile.yaml"
LEGACY_CATEGORIES_FILE = DATA_DIR / "categories.yml"


# ── Environment ──────────────────────────────────────────────────────────────
def _parse_chat_ids(raw: str) -> list[int]:
    result: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            cid = int(part)
        except ValueError:
            continue
        if cid > 0 and cid not in result:
            result.append(cid)
    return result


def _resolve_allowed_chat_ids() -> list[int]:
    """Prefer TELEGRAM_CHAT_IDS; fall back to legacy TELEGRAM_CHAT_ID."""
    ids = _parse_chat_ids(os.environ.get("TELEGRAM_CHAT_IDS", ""))
    if ids:
        return ids
    legacy = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if legacy:
        return _parse_chat_ids(legacy)
    return []


OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")
TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_IDS: list[int] = _resolve_allowed_chat_ids()
ADMIN_CHAT_ID: int = TELEGRAM_CHAT_IDS[0] if TELEGRAM_CHAT_IDS else 0

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

# ── Default categories ──────────────────────────────────────────────────────
_DEFAULT_CATEGORIES: dict[str, str] = {
    "ai-agents": "AI Agents & Multi-Agent",
    "claude-code": "Claude Code & AI Dev",
    "wordpress": "WordPress & WooCommerce",
    "devops": "DevOps & Infrastructure",
    "n8n-automation": "N8N & Automation",
    "ai-news": "AI News & Releases",
    "business": "Business & Freelancing",
}


# ── Per-user path helpers ───────────────────────────────────────────────────
def user_dir(chat_id: int) -> Path:
    return USERS_DIR / str(chat_id)


def user_profile_file(chat_id: int) -> Path:
    return user_dir(chat_id) / "profile.yaml"


def user_channels_file(chat_id: int) -> Path:
    return user_dir(chat_id) / "channels.yml"


def user_categories_file(chat_id: int) -> Path:
    return user_dir(chat_id) / "categories.yml"


def user_processed_file(chat_id: int) -> Path:
    return user_dir(chat_id) / "processed.json"


def user_pending_file(chat_id: int) -> Path:
    return user_dir(chat_id) / "pending.json"


def user_rejected_log_file(chat_id: int) -> Path:
    return user_dir(chat_id) / "rejected_log.jsonl"


def user_knowledge_dir(chat_id: int) -> Path:
    return KNOWLEDGE_DIR / str(chat_id)


def ensure_user_dirs(chat_id: int) -> None:
    """Create per-user directories if they don't exist yet (idempotent)."""
    user_dir(chat_id).mkdir(parents=True, exist_ok=True)
    user_knowledge_dir(chat_id).mkdir(parents=True, exist_ok=True)


# ── Categories (per-user) ────────────────────────────────────────────────────
_categories_locks: dict[int, threading.Lock] = {}
_categories_meta_lock = threading.Lock()


def _categories_lock_for(chat_id: int) -> threading.Lock:
    with _categories_meta_lock:
        lock = _categories_locks.get(chat_id)
        if lock is None:
            lock = threading.Lock()
            _categories_locks[chat_id] = lock
        return lock


def load_categories(chat_id: int) -> dict[str, str]:
    """Return defaults merged with per-user additions from categories.yml."""
    path = user_categories_file(chat_id)
    with _categories_lock_for(chat_id):
        cats = dict(_DEFAULT_CATEGORIES)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                custom = yaml.safe_load(f) or {}
            cats.update(custom)
        return cats


def add_category(chat_id: int, slug: str, description: str) -> None:
    """Add a new category for ``chat_id`` and persist it."""
    path = user_categories_file(chat_id)
    with _categories_lock_for(chat_id):
        existing: dict[str, str] = {}
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                existing = yaml.safe_load(f) or {}
        existing[slug] = description
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(existing, f, allow_unicode=True, default_flow_style=False)


# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("pulsebrain")


# ── Channels (per-user) ──────────────────────────────────────────────────────
def load_channels(chat_id: int) -> list[dict[str, Any]]:
    """Load channel list for ``chat_id`` from their channels.yml."""
    path = user_channels_file(chat_id)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("channels", [])


def save_channels(chat_id: int, channels: list[dict[str, Any]]) -> None:
    """Write channel list back to ``chat_id``'s channels.yml."""
    path = user_channels_file(chat_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump({"channels": channels}, f, allow_unicode=True, default_flow_style=False)
