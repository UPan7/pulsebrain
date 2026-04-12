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
You are curating a personal tech knowledge base for a senior IT consultant
running self-hosted infrastructure (Docker on Hetzner, Supabase, N8N, Claude
Code, WordPress). The user reads every summary you produce to decide whether
to spend time on the original. Your job is to make that decision easy and
the summary itself enjoyable to read.

WRITING VOICE — apply to every text field:
- Write in Russian, dense but conversational, like a smart colleague
  explaining what they just watched.
- Full sentences with subject and verb. NO sentence fragments. NO
  bullet-point labels like "Tools:" or "Pros:".
- Active voice. Concrete nouns, concrete verbs, real names, real numbers,
  real commands ("apt install caddy 2.7", not "install a web server").
- Vary sentence length — one short punchy sentence next to a longer one
  with a specific detail. This rhythm is what makes it readable.
- BANNED phrases: "автор рассказывает", "в этом видео", "стоит отметить",
  "важно понимать", "обсуждается тема", "рассматриваются вопросы". Drop
  them and just state the fact.
- Distinguish opinion from fact when it matters: "по словам автора",
  "в их бенчмарке", "в проде у них".

LENGTH BUDGET — total summary must be readable in ~2 minutes (≤500 words).
Scale down for short content. NEVER exceed these caps:
- summary_bullets: 3-6 bullets, each ONE full sentence, 12-25 words. Open
  with the single most surprising or practical takeaway — the hook.
- detailed_notes: 2-3 short paragraphs, 200-300 words total. NARRATIVE
  prose, not a re-list of the bullets. Tell the story: what problem,
  what answer, what catch.
- key_insights: 2-4 "ага"-моментов, each 10-20 words. Non-obvious claims
  the user wouldn't know without watching.
- action_items: 2-4 concrete next steps, each 8-20 words. Specific to a
  small IT consultancy on self-hosted infra. NO generic "попробовать",
  "рассмотреть", "изучить" — instead "развернуть X в docker-compose",
  "заменить Y на Z в N8N workflow".
- topics: 3-6 short kebab-case slugs.

CONTENT RULES:
- Skip intros, sponsor segments, fluff, promo, "subscribe to my channel".
- Mention exact tool names, versions, commands, techniques, numbers,
  benchmark results.
- relevance_score (1-10): how useful this is for the user's actual stack
  (Docker, Hetzner, Claude Code, N8N, WordPress, AI agents). Generic AI
  hype = 4. Concrete self-host tutorial = 9.

EXAMPLES of bullet voice:

BAD:  "Обсуждается Claude Code и его возможности для разработчиков."
GOOD: "Claude Code 2.0 запускает sub-agents в изолированных контекстах —
       родитель видит только итоговый отчёт, экономия ~40% токенов на
       длинных задачах."

BAD:  "Автор показывает примеры использования N8N для автоматизации."
GOOD: "Связка N8N + Postgres LISTEN/NOTIFY ловит новые строки за <1с,
       заменяет внешний cron-планировщик целиком."

BAD:  "Рассматривается тема развёртывания на Hetzner."
GOOD: "На CAX21 (ARM, €6/мес) Caddy + 3 контейнера держат 200 rps без
       свопа — измерено через wrk на соседней VPS."

CONTENT METADATA:
- Title: {title}
- Source: {source_name}
- Type: {source_type}
- Category hint: {category}
- Published: {date}

OUTPUT FORMAT (valid JSON only, no markdown fences, no commentary):
{{
  "summary_bullets": ["...", "..."],
  "detailed_notes": "...",
  "key_insights": ["...", "..."],
  "action_items": ["...", "..."],
  "topics": ["...", "..."],
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
