"""Auto-categorization of content via OpenRouter LLM."""

from __future__ import annotations

import logging
from difflib import SequenceMatcher

import openai

from src.config import LLM_MODEL, OPENROUTER_API_KEY, OPENROUTER_BASE_URL, load_categories

logger = logging.getLogger(__name__)

# Similarity threshold for auto-merging a proposed new slug into an
# existing category. 0.75 is tight enough to catch "ai-agent" vs "ai-agents"
# and "claude-code-tools" vs "claude-code", while leaving genuinely new
# topics (e.g. "robotics" vs "ai-agents" = ~0.14) untouched.
_AUTO_MERGE_THRESHOLD = 0.75

CATEGORIZE_PROMPT = """\
Based on this content, assign ONE category from this list:
{categories_list}

If none fits well, suggest a new short slug.

Title: {title}
First 500 chars of content: {content_preview}

Respond with ONLY the category slug, nothing else."""


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
        if len(slug) <= 30 and slug.replace("-", "").isalnum():
            return slug, True

        logger.warning("Unexpected category slug: %s, defaulting to ai-news", slug)
        return "ai-news", False
    except Exception as exc:
        logger.error("Categorization failed: %s", exc)
        return "ai-news", False
