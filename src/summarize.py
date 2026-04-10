"""Claude API summarization of content."""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL

logger = logging.getLogger(__name__)

SUMMARIZE_PROMPT = """\
You are a tech knowledge curator for a senior IT consultant and DevOps engineer
who works with WordPress, AI agents, Claude Code, N8N, and self-hosted infrastructure.

Analyze this content and produce a structured summary.

RULES:
- Write in Russian
- Be specific: mention exact tool names, versions, commands, techniques
- Focus on practical, actionable information
- Skip intros, sponsor segments, fluff, and promotional content
- "Action Items" should be specific to someone running a small IT consultancy
  with self-hosted infrastructure (Docker, Hetzner, Supabase, N8N)

CONTENT METADATA:
- Title: {title}
- Source: {source_name}
- Type: {source_type}
- Category hint: {category}
- Published: {date}

OUTPUT FORMAT (valid JSON only, no markdown fences):
{{
  "summary_bullets": ["bullet 1", "bullet 2", "..."],
  "detailed_notes": "2-3 paragraphs in Russian",
  "key_insights": ["insight 1", "insight 2"],
  "action_items": ["action 1", "action 2"],
  "topics": ["topic-tag-1", "topic-tag-2"],
  "relevance_score": 8,
  "suggested_category": "ai-agents"
}}

CONTENT:
{content}"""


def summarize_content(
    content: str,
    title: str,
    source_name: str,
    source_type: str,
    category: str = "auto-detect",
    date: str | None = None,
) -> dict[str, Any] | None:
    """Send content to Claude API and get structured summary back."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Truncate content to ~100k chars to stay within context limits
    max_content_len = 100_000
    if len(content) > max_content_len:
        content = content[:max_content_len] + "\n\n[... content truncated ...]"

    prompt = SUMMARIZE_PROMPT.format(
        title=title,
        source_name=source_name,
        source_type=source_type,
        category=category,
        date=date or "unknown",
        content=content,
    )

    for attempt in range(2):
        try:
            message = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("JSON parse error on attempt %d: %s", attempt + 1, exc)
            if attempt == 0:
                continue
            return None
        except anthropic.APIError as exc:
            logger.error("Claude API error on attempt %d: %s", attempt + 1, exc)
            if attempt == 0:
                import time
                time.sleep(5)
                continue
            return None
        except Exception as exc:
            logger.error("Unexpected error in summarize: %s", exc)
            return None

    return None
