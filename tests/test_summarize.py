"""Tests for src.summarize — LLM call retries, JSON parsing, question answering."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import openai
import pytest


def _make_client(*responses):
    """Build a mock OpenAI client whose chat.completions.create cycles through *responses*.

    Each item is either a raw string (used as the response content) or an Exception
    (raised when consumed).
    """
    client = MagicMock()

    def _side_effect(*args, **kwargs):
        item = next(_iter)
        if isinstance(item, Exception):
            raise item
        choice = MagicMock()
        choice.message.content = item
        resp = MagicMock()
        resp.choices = [choice]
        return resp

    _iter = iter(responses)
    client.chat.completions.create.side_effect = _side_effect
    return client


def _api_error(msg: str = "boom") -> openai.APIError:
    """Construct an openai.APIError without invoking real network code."""
    return openai.APIError(message=msg, request=MagicMock(), body=None)


# ── summarize_content ──────────────────────────────────────────────────────


def test_summarize_returns_parsed_dict_on_success(sample_summary_dict):
    from src.summarize import summarize_content

    client = _make_client(json.dumps(sample_summary_dict))
    with patch("src.summarize.openai.OpenAI", return_value=client):
        result = summarize_content("content", "Title", "Channel", "youtube_video")

    assert result == sample_summary_dict
    assert client.chat.completions.create.call_count == 1


def test_summarize_truncates_content_over_100k(sample_summary_dict):
    """Content >100k chars is truncated and a marker is appended."""
    from src.summarize import summarize_content

    client = _make_client(json.dumps(sample_summary_dict))
    long_content = "x" * 150_000
    with patch("src.summarize.openai.OpenAI", return_value=client):
        summarize_content(long_content, "Title", "Channel", "youtube_video")

    sent_prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "[... content truncated ...]" in sent_prompt
    # 150k of "x" must be cut to 100k; allow for stray "x" chars in boilerplate.
    assert 100_000 <= sent_prompt.count("x") < 101_000


def test_summarize_retries_on_json_decode_error_then_succeeds(sample_summary_dict):
    from src.summarize import summarize_content

    client = _make_client("not valid json", json.dumps(sample_summary_dict))
    with patch("src.summarize.openai.OpenAI", return_value=client):
        result = summarize_content("c", "T", "S", "youtube_video")

    assert result == sample_summary_dict
    assert client.chat.completions.create.call_count == 2


def test_summarize_returns_none_after_two_json_decode_errors():
    from src.summarize import summarize_content

    client = _make_client("garbage 1", "garbage 2")
    with patch("src.summarize.openai.OpenAI", return_value=client):
        result = summarize_content("c", "T", "S", "youtube_video")

    assert result is None
    assert client.chat.completions.create.call_count == 2


def test_summarize_retries_on_api_error_then_succeeds(sample_summary_dict):
    from src.summarize import summarize_content

    client = _make_client(_api_error("rate limit"), json.dumps(sample_summary_dict))
    with patch("src.summarize.openai.OpenAI", return_value=client):
        result = summarize_content("c", "T", "S", "youtube_video")

    assert result == sample_summary_dict
    assert client.chat.completions.create.call_count == 2


def test_summarize_returns_none_after_two_api_errors():
    from src.summarize import summarize_content

    client = _make_client(_api_error("e1"), _api_error("e2"))
    with patch("src.summarize.openai.OpenAI", return_value=client):
        result = summarize_content("c", "T", "S", "youtube_video")

    assert result is None
    assert client.chat.completions.create.call_count == 2


def test_summarize_returns_none_on_unexpected_exception():
    """Generic Exception → None, no retry."""
    from src.summarize import summarize_content

    client = _make_client(RuntimeError("unexpected"))
    with patch("src.summarize.openai.OpenAI", return_value=client):
        result = summarize_content("c", "T", "S", "youtube_video")

    assert result is None
    assert client.chat.completions.create.call_count == 1


def test_summarize_includes_metadata_in_prompt(sample_summary_dict):
    from src.summarize import summarize_content

    client = _make_client(json.dumps(sample_summary_dict))
    with patch("src.summarize.openai.OpenAI", return_value=client):
        summarize_content(
            content="hello",
            title="Title-X",
            source_name="Channel-Y",
            source_type="youtube_video",
            date="2025-06-15",
        )

    prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "Title-X" in prompt
    assert "Channel-Y" in prompt
    assert "youtube_video" in prompt
    assert "2025-06-15" in prompt


def test_summarize_prompt_has_no_suggested_category_example():
    """Regression guard: the 'ai-agents' example in the JSON schema used to
    make every video land in ai-agents because gpt-5.4-nano copied it
    verbatim. suggested_category is now a categorize.py concern.
    """
    from src.summarize import SUMMARIZE_PROMPT

    assert "suggested_category" not in SUMMARIZE_PROMPT
    assert '"ai-agents"' not in SUMMARIZE_PROMPT


def test_summarize_uses_unknown_when_date_missing(sample_summary_dict):
    from src.summarize import summarize_content

    client = _make_client(json.dumps(sample_summary_dict))
    with patch("src.summarize.openai.OpenAI", return_value=client):
        summarize_content("c", "T", "S", "youtube_video", date=None)

    prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "unknown" in prompt


def test_summarize_prompt_enforces_humanizer_voice():
    """The prompt must keep the readability constraints that fix the dry-summary bug."""
    from src.summarize import SUMMARIZE_PROMPT

    # Voice / readability constraints
    assert "WRITING VOICE" in SUMMARIZE_PROMPT
    assert "Full sentences" in SUMMARIZE_PROMPT
    assert "Active voice" in SUMMARIZE_PROMPT
    assert "BANNED phrases" in SUMMARIZE_PROMPT
    # Length budget — must mention the 2-minute target so the LLM has a target
    assert "LENGTH BUDGET" in SUMMARIZE_PROMPT
    assert "2 minutes" in SUMMARIZE_PROMPT
    assert "500 words" in SUMMARIZE_PROMPT
    # Few-shot examples
    assert "BAD:" in SUMMARIZE_PROMPT
    assert "GOOD:" in SUMMARIZE_PROMPT


# ── answer_question ────────────────────────────────────────────────────────


def test_answer_question_builds_context_from_sources():
    from src.summarize import answer_question

    client = _make_client("Ответ на русском")
    sources = [
        {
            "title": "First Source",
            "source": "channel-a",
            "date": "2025-06-01",
            "extracted_text": "alpha content",
        },
        {
            "title": "Second Source",
            "source": "channel-b",
            "date": "2025-06-02",
            "extracted_text": "beta content",
        },
    ]
    with patch("src.summarize.openai.OpenAI", return_value=client):
        result = answer_question("What is alpha?", sources)

    assert result == "Ответ на русском"
    user_prompt = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "First Source" in user_prompt
    assert "channel-a" in user_prompt
    assert "alpha content" in user_prompt
    assert "Second Source" in user_prompt
    assert "What is alpha?" in user_prompt


def test_answer_question_handles_missing_source_fields():
    """Sources without 'source'/'title'/'date' fall back to defaults."""
    from src.summarize import answer_question

    client = _make_client("ok")
    sources = [{"extracted_text": "lonely text"}]
    with patch("src.summarize.openai.OpenAI", return_value=client):
        result = answer_question("Q", sources)

    assert result == "ok"
    user_prompt = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    # Default labels for missing fields
    assert "Source 1" in user_prompt
    assert "?" in user_prompt
    assert "lonely text" in user_prompt


def test_answer_question_returns_none_on_api_error():
    from src.summarize import answer_question

    client = _make_client(_api_error("down"))
    with patch("src.summarize.openai.OpenAI", return_value=client):
        result = answer_question("Q", [{"title": "T", "extracted_text": "x"}])

    assert result is None
