"""Auto-categorization of content via OpenRouter LLM."""

from __future__ import annotations

import json
import logging
from difflib import SequenceMatcher

import openai

from src.config import LLM_MODEL, OPENROUTER_API_KEY, OPENROUTER_BASE_URL, load_categories

logger = logging.getLogger(__name__)

_AUTO_MERGE_THRESHOLD = 0.75
_FALLBACK_SLUG = "uncategorized"
_FALLBACK_DESCRIPTION = "Uncategorized"

CATEGORIZE_PROMPT = """\
Based on this content, assign ONE category from this list:
{categories_list}

If none fits well, suggest a new short slug.

Title: {title}
First 500 chars of content: {content_preview}

Respond with ONLY the category slug, nothing else."""

GENERATE_CATEGORY_PROMPT = """\
Create ONE fresh topic category for the following content. Respond with ONLY a
compact JSON object on a single line: {{"slug": "kebab-case-slug", "description": "2-5 word human label"}}.
The slug must be lowercase kebab-case, letters + digits + dashes only, 30 characters or fewer.

Title: {title}
First 500 chars of content: {content_preview}"""


def _valid_slug_shape(slug: str) -> bool:
    return bool(slug) and len(slug) <= 30 and slug.replace("-", "").isalnum()


def _generate_fresh_category(
    client: openai.OpenAI, title: str, content: str
) -> tuple[str, str] | None:
    """Second-chance LLM call: ask for a fresh slug + description for this content.

    Returns (slug, description) on a shape-valid response, else None.
    """
    prompt = GENERATE_CATEGORY_PROMPT.format(title=title, content_preview=content[:500])
    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            max_tokens=80,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content.strip()
        start, end = raw.find("{"), raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        data = json.loads(raw[start : end + 1])
    except Exception as exc:
        logger.error("Fresh-category generation failed: %s", exc)
        return None

    slug = str(data.get("slug", "")).strip().lower().replace(" ", "-")
    description = str(data.get("description", "")).strip()
    if not _valid_slug_shape(slug) or not description:
        return None
    return slug, description


def _auto_merge(slug: str, existing: dict[str, str]) -> str | None:
    """Return an existing slug if *slug* is sufficiently similar to one, else None.

    Pure function — no I/O. Extracted for testability.
    """
    best_match: str | None = None
    best_ratio = 0.0
    for candidate in existing:
        ratio = SequenceMatcher(None, slug, candidate).ratio()
        if ratio > best_ratio:
            best_ratio, best_match = ratio, candidate
    if best_match is not None and best_ratio >= _AUTO_MERGE_THRESHOLD:
        return best_match
    return None


def categorize_content(chat_id: int, title: str, content: str) -> tuple[str, bool]:
    """Determine the best category for content, scoped to ``chat_id``'s category list.

    Returns (slug, is_new) — is_new=True when the LLM proposed a genuinely
    new slug that doesn't exist in this user's categories and isn't close
    enough to auto-merge into an existing one.
    """
    categories = load_categories(chat_id)
    client = openai.OpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY)

    cat_lines = "\n".join(f"- {slug} ({desc})" for slug, desc in categories.items())
    prompt = CATEGORIZE_PROMPT.format(
        categories_list=cat_lines,
        title=title,
        content_preview=content[:500],
    )

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            max_tokens=50,
            messages=[{"role": "user", "content": prompt}],
        )
        slug = response.choices[0].message.content.strip().lower().replace(" ", "-")

        # Exact hit on an existing slug — the common case.
        if slug in categories:
            return slug, False

        # LLM proposed a new slug. Before we create a new category, see if
        # it's just a near-duplicate of one we already have.
        merged = _auto_merge(slug, categories)
        if merged is not None:
            logger.info("Auto-merged '%s' → '%s'", slug, merged)
            return merged, False

        # Genuinely new and validly-shaped slug → new category.
        if _valid_slug_shape(slug):
            return slug, True

        logger.warning("Malformed category slug from LLM: %r — generating fresh", slug)
    except Exception as exc:
        logger.error("Primary categorization call failed: %s", exc)

    # Fallback: second LLM call dedicated to generating a fresh category
    # from the content itself. Per-user, never a shared hardcoded slug.
    fresh = _generate_fresh_category(client, title, content)
    if fresh is not None:
        slug, _desc = fresh
        if slug in categories:
            return slug, False
        merged = _auto_merge(slug, categories)
        if merged is not None:
            logger.info("Fresh-category auto-merged '%s' → '%s'", slug, merged)
            return merged, False
        return slug, True

    # Safety net: per-user `uncategorized`. Becomes a real entry in the
    # user's own categories.yml on approval — never shared across tenants.
    logger.warning("Falling back to per-user '%s' for chat_id=%s", _FALLBACK_SLUG, chat_id)
    return _FALLBACK_SLUG, _FALLBACK_SLUG not in categories
