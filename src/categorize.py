"""Auto-categorization of content via OpenRouter LLM."""

from __future__ import annotations

import logging

import openai

from src.config import LLM_MODEL, OPENROUTER_API_KEY, OPENROUTER_BASE_URL, load_categories

logger = logging.getLogger(__name__)

CATEGORIZE_PROMPT = """\
Based on this content, assign ONE category from this list:
{categories_list}

If none fits well, suggest a new short slug.

Title: {title}
First 500 chars of content: {content_preview}

Respond with ONLY the category slug, nothing else."""


def categorize_content(title: str, content: str) -> tuple[str, bool]:
    """Determine the best category for content.

    Returns (slug, is_new) — is_new=True when LLM suggested a category
    that doesn't exist yet.
    """
    categories = load_categories()
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
        if slug in categories:
            return slug, False
        if len(slug) <= 30 and slug.replace("-", "").isalnum():
            return slug, True
        logger.warning("Unexpected category slug: %s, defaulting to ai-news", slug)
        return "ai-news", False
    except Exception as exc:
        logger.error("Categorization failed: %s", exc)
        return "ai-news", False
