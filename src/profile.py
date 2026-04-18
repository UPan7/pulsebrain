"""User profile — per-user persona, learning targets, language, known stack.

Each allowed ``chat_id`` has an independent profile on disk at
``data/users/{chat_id}/profile.yaml``. The profile is the single source
of truth for (a) what language the UI speaks for this user and
(b) what the user actually cares about when the summarize prompt
scores relevance.

Profiles are seeded by the onboarding wizard, refinable by hand in the
YAML, and read at scoring time by :mod:`src.summarize`. The bot itself
never mutates the file except via explicit user action (wizard,
``/language``, ``/profile``).

Persistence uses the same thread-lock + atomic-write pattern as
:mod:`src.pending` — safe for concurrent extractor threads and the
bot's async tasks. Caches and locks are partitioned per ``chat_id``.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

import yaml

from src.config import user_profile_file

logger = logging.getLogger(__name__)


# ── Default seed ──────────────────────────────────────────────────────────

_DEFAULT_PROFILE: dict[str, Any] = {
    "language": "en",
    "persona": "",
    "skill_level": "",
    "known_stack": [],
    "already_comfortable_with": [],
    "actively_learning": [],
    "not_interested_in": [],
}


# ── Per-user cache + lock registry ────────────────────────────────────────

_profile_caches: dict[int, dict[str, Any]] = {}
_profile_locks: dict[int, threading.Lock] = {}
_profile_meta_lock = threading.Lock()


def _lock_for(chat_id: int) -> threading.Lock:
    with _profile_meta_lock:
        lock = _profile_locks.get(chat_id)
        if lock is None:
            lock = threading.Lock()
            _profile_locks[chat_id] = lock
        return lock


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


def _load_from_disk(chat_id: int) -> dict[str, Any]:
    """Read a user's profile.yaml, backfilling any missing keys.

    Returns a fresh default on missing file or parse error.
    """
    path = user_profile_file(chat_id)
    if not path.exists():
        return _fresh_default()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (yaml.YAMLError, OSError) as exc:
        logger.warning("Failed to read %s: %s — using defaults.", path, exc)
        return _fresh_default()

    if not isinstance(data, dict):
        logger.warning("%s is not a mapping — using defaults.", path)
        return _fresh_default()

    merged = _fresh_default()
    merged.update(data)
    return merged


def _flush(chat_id: int) -> None:
    """Atomically write a user's cached profile to disk (caller holds lock)."""
    path = user_profile_file(chat_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        yaml.dump(
            _profile_caches[chat_id],
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
    os.replace(tmp_path, path)


# ── Public API ────────────────────────────────────────────────────────────


def init_profile(chat_id: int) -> None:
    """Load a user's profile.yaml into memory. Call once per chat_id at startup.

    If the file doesn't exist, a default profile is seeded in memory but
    NOT written to disk — the onboarding wizard owns first-run writing so
    we can distinguish "never onboarded" from "onboarded, all defaults".
    """
    with _lock_for(chat_id):
        _profile_caches[chat_id] = _load_from_disk(chat_id)


def load_profile(chat_id: int) -> dict[str, Any]:
    """Return the current profile for ``chat_id``.

    Safe to call without :func:`init_profile` — falls back to reading from
    disk on demand, and to defaults if the file is missing. Returns a
    copy so callers can't mutate the cache by accident.
    """
    with _lock_for(chat_id):
        cache = _profile_caches.get(chat_id)
        if cache is None:
            cache = _load_from_disk(chat_id)
            _profile_caches[chat_id] = cache
        return dict(cache)


def save_profile(chat_id: int, profile: dict[str, Any]) -> None:
    """Replace ``chat_id``'s profile with *profile* and persist it atomically.

    Missing required keys are backfilled from defaults so callers can
    pass a partial dict.
    """
    merged = _fresh_default()
    merged.update(profile)
    with _lock_for(chat_id):
        _profile_caches[chat_id] = merged
        _flush(chat_id)
    logger.info("Profile saved (chat_id=%s, language=%s)", chat_id, merged.get("language"))


def profile_exists(chat_id: int) -> bool:
    """True if this user's profile.yaml is on disk (i.e. user was onboarded)."""
    return user_profile_file(chat_id).exists()


def get_language(chat_id: int) -> str:
    """Shortcut for load_profile(chat_id)['language'] with a hard 'en' fallback.

    Returns one of :data:`src.strings.SUPPORTED_LANGS`. Anything else
    (unset, corrupted, an old 'ru' profile from before Phase 7) normalizes
    to English.
    """
    from src.strings import SUPPORTED_LANGS
    try:
        lang = load_profile(chat_id).get("language", "en")
    except Exception:
        return "en"
    if lang not in SUPPORTED_LANGS:
        return "en"
    return lang


# ── Dynamic signal aggregation ────────────────────────────────────────────

# How many entries to consider when computing recent_approved_avg. Small
# window (20) so new onboarding choices visibly move the average.
_RECENT_APPROVED_WINDOW = 20

# Limits on aggregator output size — keeps the LLM prompt bounded.
_TOP_CATEGORIES = 5
_TOP_TOPICS = 10
_REJECTED_TOPICS = 10


def build_relevance_context(chat_id: int) -> dict[str, Any]:
    """Build the dynamic signal block for ``chat_id``'s summarize prompt.

    Merges the static per-user profile with live stats from that user's
    knowledge base (top categories, top topics, recent relevance
    average) plus negative signal from their rejected log. Returns a
    single dict that :mod:`src.summarize` injects into
    ``SUMMARIZE_PROMPT``.

    Pure read-only — no LLM calls, no mutations.
    """
    profile = load_profile(chat_id)

    top_categories: list[tuple[str, int]] = []
    top_topics: list[tuple[str, int]] = []
    recent_avg: float = 0.0

    try:
        from src.storage import _get_all_entries

        entries = list(_get_all_entries(chat_id))
    except Exception as exc:
        logger.warning("Failed to load entries for relevance context: %s", exc)
        entries = []

    if entries:
        entries_by_date = sorted(
            entries,
            key=lambda e: e.get("date", ""),
            reverse=True,
        )

        cat_counts: dict[str, int] = {}
        topic_counts: dict[str, int] = {}
        for e in entries:
            cat = e.get("category")
            if cat:
                cat_counts[cat] = cat_counts.get(cat, 0) + 1
            topics_raw = e.get("topics", "")
            if topics_raw:
                for topic in topics_raw.split(","):
                    topic = topic.strip()
                    if topic:
                        topic_counts[topic] = topic_counts.get(topic, 0) + 1

        top_categories = sorted(
            cat_counts.items(), key=lambda kv: kv[1], reverse=True
        )[:_TOP_CATEGORIES]
        top_topics = sorted(
            topic_counts.items(), key=lambda kv: kv[1], reverse=True
        )[:_TOP_TOPICS]

        recent = entries_by_date[:_RECENT_APPROVED_WINDOW]
        scores: list[float] = []
        for e in recent:
            try:
                scores.append(float(e.get("relevance", 0) or 0))
            except (TypeError, ValueError):
                continue
        if scores:
            recent_avg = round(sum(scores) / len(scores), 1)

    rejected_topics: list[str] = []
    try:
        from src.pending import read_rejected_log

        records = read_rejected_log(chat_id, limit=_REJECTED_TOPICS * 3)
        for r in records:
            title = r.get("title", "").strip()
            if title and title not in rejected_topics:
                rejected_topics.append(title)
            if len(rejected_topics) >= _REJECTED_TOPICS:
                break
    except Exception as exc:
        logger.warning("Failed to read rejected log for context: %s", exc)

    return {
        "language": profile.get("language", "en"),
        "persona": profile.get("persona", ""),
        "skill_level": profile.get("skill_level", ""),
        "known_stack": list(profile.get("known_stack", [])),
        "already_comfortable_with": list(profile.get("already_comfortable_with", [])),
        "actively_learning": list(profile.get("actively_learning", [])),
        "not_interested_in": list(profile.get("not_interested_in", [])),
        "top_categories": top_categories,
        "top_topics": top_topics,
        "recent_approved_avg": recent_avg,
        "recently_rejected_titles": rejected_topics,
    }


def format_relevance_context(ctx: dict[str, Any]) -> str:
    """Flatten the :func:`build_relevance_context` dict into a prompt-ready
    multi-line string. Used by :mod:`src.summarize` when rendering the
    USER CONTEXT block.
    """
    lines: list[str] = ["USER CONTEXT:"]
    if ctx.get("persona"):
        lines.append(f"  Persona: {ctx['persona']}")
    if ctx.get("skill_level"):
        lines.append(f"  Skill level: {ctx['skill_level']}")
    if ctx.get("known_stack"):
        lines.append(f"  Known stack: {', '.join(ctx['known_stack'])}")
    if ctx.get("already_comfortable_with"):
        lines.append(
            f"  Already comfortable with: "
            f"{', '.join(ctx['already_comfortable_with'])}"
        )
    if ctx.get("actively_learning"):
        lines.append(
            f"  Actively learning: {', '.join(ctx['actively_learning'])}"
        )
    if ctx.get("not_interested_in"):
        lines.append(
            f"  NOT interested in: {', '.join(ctx['not_interested_in'])}"
        )
    if ctx.get("top_categories"):
        tops = ", ".join(f"{slug}({n})" for slug, n in ctx["top_categories"])
        lines.append(f"  Base top categories: {tops}")
    if ctx.get("top_topics"):
        tops = ", ".join(f"{t}({n})" for t, n in ctx["top_topics"])
        lines.append(f"  Base top topics: {tops}")
    if ctx.get("recent_approved_avg"):
        lines.append(
            f"  Recent relevance avg (last 20): "
            f"{ctx['recent_approved_avg']}/10"
        )
    if ctx.get("recently_rejected_titles"):
        lines.append(
            "  Recently rejected: "
            + "; ".join(ctx["recently_rejected_titles"][:5])
        )
    return "\n".join(lines)
