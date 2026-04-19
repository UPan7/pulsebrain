"""LLM summarization of content via OpenRouter."""

from __future__ import annotations

import json
import logging
from typing import Any

import openai

from src.config import (
    LLM_MODEL,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_SEMAPHORE,
)

logger = logging.getLogger(__name__)


_client_cache: openai.OpenAI | None = None


def _client() -> openai.OpenAI:
    """Lazy-cached OpenAI client — reuses the httpx session across calls."""
    global _client_cache
    if _client_cache is None:
        _client_cache = openai.OpenAI(
            base_url=OPENROUTER_BASE_URL, api_key=OPENROUTER_API_KEY
        )
    return _client_cache

# Language directive injected into SUMMARIZE_PROMPT. Determines what
# language the bullets / notes / insights / action_items are written in.
# Read from the user profile at summarize time (src.profile.load_profile).
# Must cover every code in src.strings.SUPPORTED_LANGS.
LANGUAGE_DIRECTIVES: dict[str, str] = {
    "en": (
        "Write in English, dense but conversational, like a smart colleague "
        "explaining what they just watched."
    ),
    "de": (
        "Write in German (Deutsch), dense but conversational, like a smart "
        "colleague explaining what they just watched."
    ),
    "fr": (
        "Write in French (français), dense but conversational, like a smart "
        "colleague explaining what they just watched."
    ),
    "es": (
        "Write in Spanish (español), dense but conversational, like a smart "
        "colleague explaining what they just watched."
    ),
    "it": (
        "Write in Italian (italiano), dense but conversational, like a smart "
        "colleague explaining what they just watched."
    ),
    "pt": (
        "Write in Portuguese (português), dense but conversational, like a "
        "smart colleague explaining what they just watched."
    ),
    "zh": (
        "Write in Simplified Chinese (简体中文), dense but conversational, "
        "like a smart colleague explaining what they just watched."
    ),
    "ja": (
        "Write in Japanese (日本語), dense but conversational, like a smart "
        "colleague explaining what they just watched."
    ),
    "ru": (
        "Write in Russian, dense but conversational, like a smart colleague "
        "explaining what they just watched."
    ),
    "ar": (
        "Write in Arabic (العربية), dense but conversational, like a smart "
        "colleague explaining what they just watched."
    ),
}


# Length budgets by transcript/article word count. The model picks the
# base mode from word_count, then may collapse to "short" when it scores
# relevance ≤ 4 (low-signal content stays tight regardless of length).
# `deep_dive` is a new optional section with 3-4 technical subsections —
# emitted only by long/xlong modes. Calibrated on the real corpus where
# 3-hour Dave Ebbelaar builds came back at 380 words of narrative, which
# users flagged as too sparse.
_LENGTH_BUDGETS: dict[str, dict[str, object]] = {
    "short":  {"bullets": "3-5", "notes": "200-300", "paragraphs": "2-3", "insights": "2-3", "actions": "2-3", "deep_dive": False, "dd_count": "0", "dd_words": "0"},
    "medium": {"bullets": "5-7", "notes": "400-500", "paragraphs": "3",   "insights": "3-5", "actions": "3-5", "deep_dive": False, "dd_count": "0", "dd_words": "0"},
    "long":   {"bullets": "6-8", "notes": "500-700", "paragraphs": "3-4", "insights": "4-6", "actions": "4-6", "deep_dive": True,  "dd_count": "3",   "dd_words": "100-150"},
    "xlong":  {"bullets": "7-9", "notes": "600-900", "paragraphs": "4",   "insights": "5-7", "actions": "5-7", "deep_dive": True,  "dd_count": "4",   "dd_words": "100-150"},
}

_MODE_ORDER: list[str] = ["short", "medium", "long", "xlong"]


def _pick_mode(word_count: int) -> str:
    """Map transcript/article word count to a base length mode."""
    if word_count < 1500:
        return "short"
    if word_count < 3500:
        return "medium"
    if word_count < 7000:
        return "long"
    return "xlong"


def _render_budget_block(mode: str) -> str:
    """Return the LENGTH BUDGET prompt fragment for *mode*."""
    b = _LENGTH_BUDGETS[mode]
    if b["deep_dive"]:
        dd_line = (
            f"- deep_dive: REQUIRED. {b['dd_count']} subsections, each "
            f"{{heading, body}}. Body is {b['dd_words']} words of technical "
            "detail — commands, names, versions, numbers, gotchas. Not a "
            "re-list of bullets; different concrete material."
        )
    else:
        dd_line = '- deep_dive: null (short/medium content does not need it).'
    return (
        f"LENGTH MODE: {mode}\n"
        f"- summary_bullets: {b['bullets']} bullets, each ONE full sentence, "
        "12-25 words. Open with the single most surprising or practical "
        "takeaway — the hook.\n"
        f"- detailed_notes: {b['paragraphs']} paragraphs, {b['notes']} words "
        "total. NARRATIVE prose, not a re-list of the bullets. Tell the "
        "story: what problem, what answer, what catch.\n"
        f"- key_insights: {b['insights']} \"aha\" moments, each 10-20 words. "
        "Non-obvious claims the user wouldn't know without watching.\n"
        f"- action_items: {b['actions']} concrete next steps, each 8-20 "
        "words. NO generic \"try X\", \"consider Y\" — instead \"deploy X "
        "in docker-compose\", \"replace Y with Z in the N8N workflow\".\n"
        f"{dd_line}\n"
        "- topics: 3-6 short kebab-case slugs."
    )


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

LENGTH BUDGET — scales with content length (≈{content_words} words of
source). A 10-minute clip should not get the same budget as a 3-hour
masterclass. Use the mode below. Over/undershoot by a bullet or 50 words
is fine; inverting the mode is not.

{length_budget_block}

RELEVANCE OVERRIDE — after you score relevance (see rubric below):
- If relevance ≤ 4 → COLLAPSE to the short-mode budget regardless of
  what word_count said. Low-signal content stays tight; the user will
  skip it anyway. Set deep_dive to null.
- Otherwise → use the mode above.

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

OUTPUT FORMAT (valid JSON only, no markdown fences, no commentary).
Score relevance FIRST so it can drive your length choices:
{{
  "relevance_score": <1-10>,
  "topics": ["...", "..."],
  "summary_bullets": ["...", "..."],
  "detailed_notes": "...",
  "deep_dive": [{{"heading": "...", "body": "..."}}, ...] or null,
  "key_insights": ["...", "..."],
  "action_items": ["...", "..."]
}}

CONTENT:
{content}"""


def summarize_content(
    chat_id: int,
    content: str,
    title: str,
    source_name: str,
    source_type: str,
    date: str | None = None,
) -> dict[str, Any] | None:
    """Send content to LLM via OpenRouter and get structured summary back.

    Category inference is intentionally NOT done here — see
    :func:`src.categorize.categorize_content`. Keeping the two LLM calls
    separate avoids the summarize prompt copying its example value
    verbatim (which used to force every entry into 'ai-agents').

    Language and relevance scoring are driven by ``chat_id``'s profile
    — the summary output is written in their configured language and
    the LLM sees a USER CONTEXT block listing stack / learning goals /
    rejected topics so it can anchor the relevance rubric to that user.
    """
    client = _client()

    # Pick length mode from the ORIGINAL word count, before truncation,
    # so a 3-hour talk still gets an xlong budget even though we chop
    # its transcript for the prompt. Mode drives budget inlined below.
    content_words = len(content.split())
    length_mode = _pick_mode(content_words)
    length_budget_block = _render_budget_block(length_mode)

    # Truncate content to ~100k chars to stay within context limits
    max_content_len = 100_000
    if len(content) > max_content_len:
        content = content[:max_content_len] + "\n\n[... content truncated ...]"

    # Build the USER CONTEXT block + pick the language directive from
    # the caller's profile. A genuine failure (parse error, disk error)
    # is logged loudly with chat_id so it doesn't silently degrade the
    # user's language / persona context across every summary. Language
    # at least always comes from get_language(), which is bulletproof.
    from src.profile import build_relevance_context, format_relevance_context, get_language

    try:
        ctx = build_relevance_context(chat_id)
    except Exception as exc:
        logger.error(
            "Failed to build relevance context for chat_id=%s: %s — "
            "falling back to language-only context",
            chat_id, exc,
        )
        ctx = {"language": get_language(chat_id)}

    user_context_block = format_relevance_context(ctx)
    language = ctx.get("language", "en")
    language_directive = LANGUAGE_DIRECTIVES.get(
        language, LANGUAGE_DIRECTIVES["en"]
    )

    prompt = SUMMARIZE_PROMPT.format(
        user_context=user_context_block,
        language_directive=language_directive,
        length_budget_block=length_budget_block,
        content_words=content_words,
        title=title,
        source_name=source_name,
        source_type=source_type,
        date=date or "unknown",
        content=content,
    )

    for attempt in range(2):
        try:
            with OPENROUTER_SEMAPHORE:
                response = client.chat.completions.create(
                    model=LLM_MODEL,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}],
                )
            raw = response.choices[0].message.content.strip()
            parsed = json.loads(raw)
            # Tag the picked mode on the response so downstream code can
            # persist it for analytics / debugging. Model doesn't need
            # to emit this itself.
            parsed.setdefault("length_mode", length_mode)
            return parsed
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
{language_directive}"""

QUESTION_USER_PROMPT = """\
Context from knowledge base:
---
{context}
---

User question: {question}"""


def answer_question(chat_id: int, question: str, sources: list[dict[str, str]]) -> str | None:
    """Answer a free-form question using ``chat_id``'s knowledge base sources.

    The answer is written in the caller's configured profile language.
    """
    from src.profile import get_language

    lang = get_language(chat_id)
    language_directive = LANGUAGE_DIRECTIVES.get(lang, LANGUAGE_DIRECTIVES["en"])
    system_prompt = QUESTION_SYSTEM_PROMPT.format(language_directive=language_directive)

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
        with OPENROUTER_SEMAPHORE:
            response = client.chat.completions.create(
                model=LLM_MODEL,
                max_tokens=2048,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        logger.error("Question answering failed: %s", exc)
        return None
