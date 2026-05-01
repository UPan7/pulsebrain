"""Onboarding wizard state machine — pure logic, no Telegram imports.

The Telegram handlers in src.telegram_bot drive the user through a
series of steps and accumulate answers into a *draft* dict. When the
wizard finishes, apply_draft() commits the draft to the three
persistence layers (profile / categories / channels). Keeping the
commit logic here makes it unit-testable without any Telegram mocks.

Step order (see STEPS below) is the single source of truth for the
handler's advance() calls — the handler never hardcodes a step index.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ── Step definitions ─────────────────────────────────────────────────────

# Ordered list of step keys. The Telegram handler dispatches on the
# current step via context.user_data["onboarding_step"] = <index into
# STEPS>. advance_step() returns the next key or None when done.
STEPS: list[str] = [
    "lang",             # 0: language picker (callback-driven)
    "welcome",          # 1: welcome body + [Start] button
    "persona",          # 2: free text (required)
    "learning",         # 3: multiline (required, but user can send "-")
    "stack",            # 4: multiline (required)
    "notinterested",    # 5: multiline (optional, skip button)
    "categories",       # 6: category toggles + [Done]
    "channels",         # 7: channel toggles + [Done] (auto-skipped when empty)
    "done",             # 8: terminal — apply_draft + clear state
]

# Steps that are interactive inline-keyboard only (no free text input).
CALLBACK_STEPS: frozenset[str] = frozenset({"lang", "welcome", "categories", "channels"})

# Steps that accept an optional /skip or an empty answer.
OPTIONAL_STEPS: frozenset[str] = frozenset({"notinterested"})


def new_draft() -> dict[str, Any]:
    """Fresh draft with empty fields. Language gets set by step 0."""
    return {
        "language": "en",
        "persona": "",
        "actively_learning": [],
        "known_stack": [],
        "already_comfortable_with": [],
        "not_interested_in": [],
        "selected_categories": {},   # slug → description
        "selected_channels": [],     # list of channel dicts ready for channels.yml
    }


def step_key(index: int) -> str | None:
    """Return the step key at *index*, or None if past the end."""
    if 0 <= index < len(STEPS):
        return STEPS[index]
    return None


def next_step(index: int) -> int:
    """Return the next step index. Stays clamped to len(STEPS)-1 (done)."""
    return min(index + 1, len(STEPS) - 1)


def parse_multiline(text: str) -> list[str]:
    """Split a multi-line answer into non-empty stripped items."""
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


# ── Commit ────────────────────────────────────────────────────────────────


def apply_draft(chat_id: int, draft: dict[str, Any]) -> dict[str, int]:
    """Persist ``chat_id``'s onboarding draft to their per-user files.

    Writes ``data/users/{chat_id}/profile.yaml``,
    ``data/users/{chat_id}/categories.yml`` (appending any new slugs),
    and ``data/users/{chat_id}/channels.yml`` (merging selected
    channels with anything already saved for this user).

    Returns a summary dict with counts of what was written, suitable
    for logging and assertions in tests.
    """
    from src.config import add_category, load_channels, save_channels
    from src.profile import save_profile
    from src.strings import SUPPORTED_LANGS

    language = draft.get("language", "en")
    if language not in SUPPORTED_LANGS:
        language = "en"

    profile = {
        "language": language,
        "persona": draft.get("persona", "").strip(),
        "skill_level": draft.get("skill_level", ""),
        "known_stack": list(draft.get("known_stack", [])),
        "already_comfortable_with": list(draft.get("already_comfortable_with", [])),
        "actively_learning": list(draft.get("actively_learning", [])),
        "not_interested_in": list(draft.get("not_interested_in", [])),
    }
    save_profile(chat_id, profile)

    categories_added = 0
    for slug, desc in draft.get("selected_categories", {}).items():
        add_category(chat_id, slug, desc)
        categories_added += 1

    channels_added = 0
    selected = draft.get("selected_channels", [])
    if selected:
        existing = load_channels(chat_id)
        existing_ids = {ch.get("id") for ch in existing}
        for ch in selected:
            if ch.get("id") and ch["id"] not in existing_ids:
                existing.append(ch)
                existing_ids.add(ch["id"])
                channels_added += 1
        if channels_added:
            save_channels(chat_id, existing)

    summary = {
        "profile_saved": 1,
        "categories_added": categories_added,
        "channels_added": channels_added,
    }
    logger.info("Onboarding draft applied: %s", summary)
    return summary
