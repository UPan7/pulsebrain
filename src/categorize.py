"""Auto-categorization of content via OpenRouter LLM."""

from __future__ import annotations

import logging

import openai

from src.config import CATEGORIES, LLM_MODEL, OPENROUTER_API_KEY, OPENROUTER_BASE_URL

logger = logging.getLogger(__name__)

CATEGORIZE_PROMPT = """\
Based on this content, assign ONE category from this list:
- ai-agents (AI agents, MCP, multi-agent systems, LangChain, CrewAI)
- claude-code (Claude Code, AI-assisted development, Cursor, Windsurf)
- wordpress (WordPress, WooCommerce, Gutenberg, themes, plugins)
- devops (Docker, CI/CD, servers, monitoring, self-hosting, Kubernetes)
- n8n-automation (N8N, workflow automation, Make, Zapier)
- ai-news (Model releases, AI industry news, product launches)
- business (Freelancing, consulting, pricing, client management)

If none fits well, suggest a new short slug.

Title: {title}
First 500 chars of content: {content_preview}

Respond with ONLY the category slug, nothing else."""


def categorize_content(title: str, content: str) -> str:
    """Determine the best category for content. Returns a category slug."""
    client = openai.OpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY)

    prompt = CATEGORIZE_PROMPT.format(
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
        # Validate it's a known category or a reasonable slug
        if slug in CATEGORIES or (len(slug) <= 30 and slug.replace("-", "").isalnum()):
            return slug
        logger.warning("Unexpected category slug: %s, defaulting to ai-news", slug)
        return "ai-news"
    except Exception as exc:
        logger.error("Categorization failed: %s", exc)
        return "ai-news"
