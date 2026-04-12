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


# ── Dynamic signal aggregation ────────────────────────────────────────────

# How many entries to consider when computing recent_approved_avg. Small
# window (20) so new onboarding choices visibly move the average.
_RECENT_APPROVED_WINDOW = 20

# Limits on aggregator output size — keeps the LLM prompt bounded.
_TOP_CATEGORIES = 5
_TOP_TOPICS = 10
_REJECTED_TOPICS = 10


def build_relevance_context() -> dict[str, Any]:
    """Build the dynamic signal block for the summarize prompt.

    Merges the static user profile with live stats from the knowledge
    base (top categories, top topics, recent relevance average) plus
    negative signal from the rejected log (what the user silently
    dropped recently). Returns a single dict that src.summarize
    injects into SUMMARIZE_PROMPT.

    Pure read-only — no LLM calls, no mutations. Reads via the cached
    storage._get_all_entries (60s TTL) so repeat calls are cheap.
    """
    profile = load_profile()

    top_categories: list[tuple[str, int]] = []
    top_topics: list[tuple[str, int]] = []
    recent_avg: float = 0.0

    try:
        from src.storage import _get_all_entries

        entries = list(_get_all_entries())
    except Exception as exc:
        logger.warning("Failed to load entries for relevance context: %s", exc)
        entries = []

    if entries:
        # Sort by date desc so "recent" means the last N accepted entries.
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

        # Recent relevance average (defaults to neutral 5.0 for cold base)
        recent = entries_by_date[:_RECENT_APPROVED_WINDOW]
        scores: list[float] = []
        for e in recent:
            try:
                scores.append(float(e.get("relevance", 0) or 0))
            except (TypeError, ValueError):
                continue
        if scores:
            recent_avg = round(sum(scores) / len(scores), 1)

    # Negative signal: topics the user recently rejected. Pulled from the
    # JSONL log written by Phase 2.0 so /rejected and scoring share a
    # single source of truth.
    rejected_topics: list[str] = []
    try:
        from src.pending import read_rejected_log

        records = read_rejected_log(limit=_REJECTED_TOPICS * 3)
        # The log stores title, not topics — the best we can do without
        # retrospective reparse is to pass a flat list of rejected titles.
        for r in records:
            title = r.get("title", "").strip()
            if title and title not in rejected_topics:
                rejected_topics.append(title)
            if len(rejected_topics) >= _REJECTED_TOPICS:
                break
    except Exception as exc:
        logger.warning("Failed to read rejected log for context: %s", exc)

    return {
        "language": profile.get("language", "ru"),
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
    """Flatten the build_relevance_context dict into a prompt-ready
    multi-line string. Used by src.summarize when rendering the
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
