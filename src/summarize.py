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

# Language directive injected into SUMMARIZE_PROMPT. Determines what
# language the bullets / notes / insights / action_items are written in.
# Read from the user profile at summarize time (src.profile.load_profile).
LANGUAGE_DIRECTIVES: dict[str, str] = {
    "ru": (
        "Write in Russian, dense but conversational, like a smart colleague "
        "explaining what they just watched."
    ),
    "en": (
        "Write in English, dense but conversational, like a smart colleague "
        "explaining what they just watched."
    ),
}


SUMMARIZE_PROMPT = """\
You are curating a personal tech knowledge base. The user reads every
summary you produce to decide whether to spend time on the original.
Your job is to make that decision easy and the summary itself enjoyable
to read.

{user_context}

WRITING VOICE — apply to every text field:
- {language_directive}
- Full sentences with subject and verb. NO sentence fragments. NO
  bullet-point labels like "Tools:" or "Pros:".
- Active voice. Concrete nouns, concrete verbs, real names, real numbers,
  real commands ("apt install caddy 2.7", not "install a web server").
- Vary sentence length — one short punchy sentence next to a longer one
  with a specific detail. This rhythm is what makes it readable.
- BANNED phrases: "the author says", "in this video", "it's worth noting",
  "it's important to understand", "the topic is discussed", "the question
  is considered" and their equivalents in any language. Drop them and
  just state the fact.
- Distinguish opinion from fact when it matters: "per the author",
  "in their benchmark", "in their production setup".

LENGTH BUDGET — total summary must be readable in ~2 minutes (≤500 words).
Scale down for short content. NEVER exceed these caps:
- summary_bullets: 3-6 bullets, each ONE full sentence, 12-25 words. Open
  with the single most surprising or practical takeaway — the hook.
- detailed_notes: 2-3 short paragraphs, 200-300 words total. NARRATIVE
  prose, not a re-list of the bullets. Tell the story: what problem,
  what answer, what catch.
- key_insights: 2-4 "aha" moments, each 10-20 words. Non-obvious claims
  the user wouldn't know without watching.
- action_items: 2-4 concrete next steps, each 8-20 words. NO generic
  "try X", "consider Y", "study Z" — instead "deploy X in docker-compose",
  "replace Y with Z in the N8N workflow".
- topics: 3-6 short kebab-case slugs.

CONTENT RULES:
- Skip intros, sponsor segments, fluff, promo, "subscribe to my channel".
- Mention exact tool names, versions, commands, techniques, numbers,
  benchmark results.

RELEVANCE SCORING (1-10) — be honest, not polite. Anchor against the
USER CONTEXT block above, not a generic rubric:

  10 = "I needed exactly this. Block the afternoon." A concrete
       technique/command/benchmark in the user's actively_learning list,
       fits their known_stack, and they don't already know it.
   8 = Solid and practical. Worth the watch. Touches known_stack with
       new detail or a better approach than what they currently use.
   6 = Interesting, some new info, but mostly known territory. Skip
       unless it's a slow day.
   4 = Mostly recap / news / hype. Generic listicle. Sponsored content.
       Beginner crash course on a topic already in
       already_comfortable_with.
   2 = Explicitly in not_interested_in. Wrong audience entirely.
   1 = Pure noise.

Downrank aggressively: "5 AI tools you must use", "I used Claude for
30 days", news recap digests, beginner tutorials on basics the user
already has. Uprank concrete architecture deep-dives, production
post-mortems, cost/perf numbers, obscure gotchas.

CONTENT METADATA:
- Title: {title}
- Source: {source_name}
- Type: {source_type}
- Published: {date}

OUTPUT FORMAT (valid JSON only, no markdown fences, no commentary):
{{
  "summary_bullets": ["...", "..."],
  "detailed_notes": "...",
  "key_insights": ["...", "..."],
  "action_items": ["...", "..."],
  "topics": ["...", "..."],
  "relevance_score": <1-10>
}}

CONTENT:
{content}"""


def summarize_content(
    content: str,
    title: str,
    source_name: str,
    source_type: str,
    date: str | None = None,
) -> dict[str, Any] | None:
    """Send content to LLM via OpenRouter and get structured summary back.

    Category inference is intentionally NOT done here — see
    src/categorize.py:categorize_content. Keeping the two LLM calls
    separate avoids the summarize prompt copying its example value
    verbatim (which used to force every entry into 'ai-agents').

    Language and relevance scoring are driven by the user profile
    (src.profile) — the summary output is written in profile.language
    and the LLM sees a USER CONTEXT block listing stack / learning
    goals / rejected topics so it can anchor the relevance rubric.
    """
    client = _client()

    # Truncate content to ~100k chars to stay within context limits
    max_content_len = 100_000
    if len(content) > max_content_len:
        content = content[:max_content_len] + "\n\n[... content truncated ...]"

    # Build the USER CONTEXT block + pick the language directive from
    # the current profile. Both are best-effort — a missing profile
    # falls through to neutral defaults so the summarizer still works.
    from src.profile import build_relevance_context, format_relevance_context

    try:
        ctx = build_relevance_context()
    except Exception as exc:
        logger.warning("Failed to build relevance context: %s", exc)
        ctx = {"language": "ru"}

    user_context_block = format_relevance_context(ctx)
    language = ctx.get("language", "ru")
    language_directive = LANGUAGE_DIRECTIVES.get(
        language, LANGUAGE_DIRECTIVES["ru"]
    )

    prompt = SUMMARIZE_PROMPT.format(
        user_context=user_context_block,
        language_directive=language_directive,
        title=title,
        source_name=source_name,
        source_type=source_type,
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
