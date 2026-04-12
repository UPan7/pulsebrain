"""User profile — persona, learning targets, language, known stack.

The profile is the single source of truth for (a) what language the UI
speaks and (b) what the user actually cares about when the summarize
prompt scores relevance. It is seeded by the onboarding wizard
(Phase 5.3), refinable by hand in data/user_profile.yaml, and read at
scoring time by src.summarize. The bot itself never mutates the file
except via explicit user action (wizard, /language, /profile).

Persistence uses the same thread-lock + atomic-write pattern as
src.pending — safe for concurrent extractor threads and the bot's
async tasks.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

import yaml

from src.config import DATA_DIR, PROFILE_FILE

logger = logging.getLogger(__name__)


# ── Default seed ──────────────────────────────────────────────────────────

_DEFAULT_PROFILE: dict[str, Any] = {
    "language": "ru",
    "persona": "",
    "skill_level": "",
    "known_stack": [],
    "already_comfortable_with": [],
    "actively_learning": [],
    "not_interested_in": [],
}

# Keys we guarantee exist in any loaded profile. Missing keys are
# back-filled from _DEFAULT_PROFILE on read so downstream code can
# .get() without worrying about KeyError.
_REQUIRED_KEYS: tuple[str, ...] = tuple(_DEFAULT_PROFILE.keys())


# ── In-memory cache + lock ────────────────────────────────────────────────

_profile_lock = threading.Lock()
_profile_cache: dict[str, Any] | None = None


def _fresh_default() -> dict[str, Any]:
    """A deep-enough copy of the default profile (lists are separate instances)."""
    return {
        "language": _DEFAULT_PROFILE["language"],
        "persona": _DEFAULT_PROFILE["persona"],
        "skill_level": _DEFAULT_PROFILE["skill_level"],
        "known_stack": list(_DEFAULT_PROFILE["known_stack"]),
        "already_comfortable_with": list(_DEFAULT_PROFILE["already_comfortable_with"]),
        "actively_learning": list(_DEFAULT_PROFILE["actively_learning"]),
        "not_interested_in": list(_DEFAULT_PROFILE["not_interested_in"]),
    }


def _load_profile_from_disk() -> dict[str, Any]:
    """Read user_profile.yaml from disk, backfilling any missing keys.

    Returns a fresh default profile on missing file or parse error.
    """
    if not PROFILE_FILE.exists():
        return _fresh_default()
    try:
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (yaml.YAMLError, OSError) as exc:
        logger.warning("Failed to read %s: %s — using defaults.", PROFILE_FILE, exc)
        return _fresh_default()

    if not isinstance(data, dict):
        logger.warning("%s is not a mapping — using defaults.", PROFILE_FILE)
        return _fresh_default()

    # Backfill missing keys with defaults so downstream code never KeyErrors.
    merged = _fresh_default()
    merged.update(data)
    return merged


def _flush_profile() -> None:
    """Atomically write _profile_cache to disk (caller must hold lock)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = PROFILE_FILE.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        yaml.dump(
            _profile_cache,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
    os.replace(tmp_path, PROFILE_FILE)


# ── Public API ────────────────────────────────────────────────────────────


def init_profile() -> None:
    """Load user_profile.yaml into memory. Call once at startup.

    If the file doesn't exist, a default profile is seeded in memory but
    NOT written to disk — the onboarding wizard owns first-run writing so
    we can distinguish "never onboarded" from "onboarded, all defaults".
    """
    global _profile_cache
    with _profile_lock:
        _profile_cache = _load_profile_from_disk()


def load_profile() -> dict[str, Any]:
    """Return the current profile (cached if init_profile was called).

    Safe to call without init_profile — falls back to reading from disk
    on demand, and to defaults if the file is missing. Returns a copy so
    callers can't mutate the cache by accident.
    """
    with _profile_lock:
        cache = _profile_cache if _profile_cache is not None else _load_profile_from_disk()
        return dict(cache)


def save_profile(profile: dict[str, Any]) -> None:
    """Replace the profile with *profile* and persist it atomically.

    Missing required keys are backfilled from defaults, so callers can
    pass a partial dict (e.g. just {"language": "en"} wouldn't be useful
    here, but {"language": "en", "persona": "..."} works without
    collapsing the rest to None).
    """
    global _profile_cache
    merged = _fresh_default()
    merged.update(profile)
    with _profile_lock:
        _profile_cache = merged
        _flush_profile()
    logger.info("Profile saved (language=%s)", merged.get("language"))


def profile_exists() -> bool:
    """True if data/user_profile.yaml is on disk (i.e. user was onboarded)."""
    return PROFILE_FILE.exists()


def get_language() -> str:
    """Shortcut for load_profile()['language'] with a hard fallback to 'ru'."""
    try:
        lang = load_profile().get("language", "ru")
    except Exception:
        return "ru"
    if lang not in ("ru", "en"):
        return "ru"
    return lang
