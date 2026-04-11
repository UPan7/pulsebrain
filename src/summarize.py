"""LLM summarization of content via OpenRouter."""

from __future__ import annotations

import json
import logging
from typing import Any

import openai

from src.config import LLM_MODEL, OPENROUTER_API_KEY, OPENROUTER_BASE_URL

logger = logging.getLogger(__name__)


def _client() -> openai.OpenAI:
    return openai.OpenAI(base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY)

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
    """Send content to LLM via OpenRouter and get structured summary back."""
    client = _client()

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
            response = client.chat.completions.create(
                model=LLM_MODEL,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.choices[0].message.content.strip()
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("JSON parse error on attempt %d: %s", attempt + 1, exc)
            if attempt == 0:
                continue
            return None
        except openai.APIError as exc:
            logger.error("OpenRouter API error on attempt %d: %s", attempt + 1, exc)
            if attempt == 0:
                continue
            return None
        except Exception as exc:
            logger.error("Unexpected error in summarize: %s", exc)
            return None

    return None


# ── Question answering ───────────────────────────────────────────────────────

QUESTION_SYSTEM_PROMPT = """\
You are a knowledge assistant. Answer the user's question based ONLY \
on the provided sources from their personal knowledge base. \
If the sources don't contain relevant information, say so honestly.
Always cite which source each insight comes from.
Answer in Russian."""

QUESTION_USER_PROMPT = """\
Context from knowledge base:
---
{context}
---

User question: {question}"""


def answer_question(question: str, sources: list[dict[str, str]]) -> str | None:
    """Answer a free-form question using knowledge base sources."""
    client = _client()

    # Build context block from sources
    context_parts: list[str] = []
    for i, src in enumerate(sources, 1):
        source_label = src.get("source", src.get("title", f"Source {i}"))
        date = src.get("date", "?")
        context_parts.append(
            f"[Source {i}: {src.get('title', '?')} — {source_label}, {date}]\n"
            f"{src.get('extracted_text', '')}"
        )

    context = "\n\n---\n\n".join(context_parts)

    user_prompt = QUESTION_USER_PROMPT.format(context=context, question=question)

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            max_tokens=2048,
            messages=[
                {"role": "system", "content": QUESTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.error("Question answering failed: %s", exc)
        return None
