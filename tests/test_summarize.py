"""Tests for src.summarize — LLM call retries, JSON parsing, question answering."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import openai
import pytest


def _make_client(*responses):
    """Build a mock OpenAI client whose chat.completions.create cycles through *responses*."""
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
    return openai.APIError(message=msg, request=MagicMock(), body=None)


# ── summarize_content ──────────────────────────────────────────────────────


def test_summarize_returns_parsed_dict_on_success(tmp_knowledge_dir, chat_id, sample_summary_dict):
    from src.summarize import summarize_content

    client = _make_client(json.dumps(sample_summary_dict))
    with patch("src.summarize.openai.OpenAI", return_value=client):
        result = summarize_content(chat_id, "content", "Title", "Channel", "youtube_video")

    assert result == sample_summary_dict
    assert client.chat.completions.create.call_count == 1


def test_summarize_truncates_content_over_100k(tmp_knowledge_dir, chat_id, sample_summary_dict):
    from src.summarize import summarize_content

    client = _make_client(json.dumps(sample_summary_dict))
    long_content = "x" * 150_000
    with patch("src.summarize.openai.OpenAI", return_value=client):
        summarize_content(chat_id, long_content, "Title", "Channel", "youtube_video")

    sent_prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "[... content truncated ...]" in sent_prompt
    assert 100_000 <= sent_prompt.count("x") < 101_000


def test_summarize_retries_on_json_decode_error_then_succeeds(tmp_knowledge_dir, chat_id, sample_summary_dict):
    from src.summarize import summarize_content

    client = _make_client("not valid json", json.dumps(sample_summary_dict))
    with patch("src.summarize.openai.OpenAI", return_value=client):
        result = summarize_content(chat_id, "c", "T", "S", "youtube_video")

    assert result == sample_summary_dict
    assert client.chat.completions.create.call_count == 2


def test_summarize_returns_none_after_two_json_decode_errors(tmp_knowledge_dir, chat_id):
    from src.summarize import summarize_content

    client = _make_client("garbage 1", "garbage 2")
    with patch("src.summarize.openai.OpenAI", return_value=client):
        result = summarize_content(chat_id, "c", "T", "S", "youtube_video")

    assert result is None
    assert client.chat.completions.create.call_count == 2


def test_summarize_retries_on_api_error_then_succeeds(tmp_knowledge_dir, chat_id, sample_summary_dict):
    from src.summarize import summarize_content

    client = _make_client(_api_error("rate limit"), json.dumps(sample_summary_dict))
    with patch("src.summarize.openai.OpenAI", return_value=client):
        result = summarize_content(chat_id, "c", "T", "S", "youtube_video")

    assert result == sample_summary_dict
    assert client.chat.completions.create.call_count == 2


def test_summarize_returns_none_after_two_api_errors(tmp_knowledge_dir, chat_id):
    from src.summarize import summarize_content

    client = _make_client(_api_error("e1"), _api_error("e2"))
    with patch("src.summarize.openai.OpenAI", return_value=client):
        result = summarize_content(chat_id, "c", "T", "S", "youtube_video")

    assert result is None
    assert client.chat.completions.create.call_count == 2


def test_summarize_returns_none_on_unexpected_exception(tmp_knowledge_dir, chat_id):
    from src.summarize import summarize_content

    client = _make_client(RuntimeError("unexpected"))
    with patch("src.summarize.openai.OpenAI", return_value=client):
        result = summarize_content(chat_id, "c", "T", "S", "youtube_video")

    assert result is None
    assert client.chat.completions.create.call_count == 1


def test_summarize_includes_metadata_in_prompt(tmp_knowledge_dir, chat_id, sample_summary_dict):
    from src.summarize import summarize_content

    client = _make_client(json.dumps(sample_summary_dict))
    with patch("src.summarize.openai.OpenAI", return_value=client):
        summarize_content(
            chat_id,
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
    from src.summarize import SUMMARIZE_PROMPT

    assert "suggested_category" not in SUMMARIZE_PROMPT
    assert '"ai-agents"' not in SUMMARIZE_PROMPT


def test_summarize_uses_unknown_when_date_missing(tmp_knowledge_dir, chat_id, sample_summary_dict):
    from src.summarize import summarize_content

    client = _make_client(json.dumps(sample_summary_dict))
    with patch("src.summarize.openai.OpenAI", return_value=client):
        summarize_content(chat_id, "c", "T", "S", "youtube_video", date=None)

    prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "unknown" in prompt


def test_summarize_prompt_enforces_humanizer_voice():
    from src.summarize import SUMMARIZE_PROMPT

    assert "WRITING VOICE" in SUMMARIZE_PROMPT
    assert "Full sentences" in SUMMARIZE_PROMPT
    assert "Active voice" in SUMMARIZE_PROMPT
    assert "BANNED phrases" in SUMMARIZE_PROMPT
    assert "LENGTH BUDGET" in SUMMARIZE_PROMPT
    assert "2 minutes" in SUMMARIZE_PROMPT
    assert "500 words" in SUMMARIZE_PROMPT


def test_summarize_prompt_has_anchor_rubric():
    from src.summarize import SUMMARIZE_PROMPT

    assert "RELEVANCE SCORING" in SUMMARIZE_PROMPT
    assert "10 =" in SUMMARIZE_PROMPT
    assert "8 =" in SUMMARIZE_PROMPT
    assert "6 =" in SUMMARIZE_PROMPT
    assert "4 =" in SUMMARIZE_PROMPT
    assert "2 =" in SUMMARIZE_PROMPT
    assert "actively_learning" in SUMMARIZE_PROMPT
    assert "known_stack" in SUMMARIZE_PROMPT
    assert "not_interested_in" in SUMMARIZE_PROMPT


def test_summarize_prompt_has_no_literal_relevance_default():
    from src.summarize import SUMMARIZE_PROMPT

    assert '"relevance_score": 8' not in SUMMARIZE_PROMPT
    assert '"relevance_score": <1-10>' in SUMMARIZE_PROMPT


# ── answer_question ────────────────────────────────────────────────────────


def test_answer_question_builds_context_from_sources(tmp_knowledge_dir, chat_id):
    from src.profile import init_profile, save_profile
    from src.summarize import answer_question

    init_profile(chat_id)
    save_profile(chat_id, {"language": "ru", "persona": "test"})

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
        result = answer_question(chat_id, "What is alpha?", sources)

    assert result == "Ответ на русском"
    user_prompt = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "First Source" in user_prompt
    assert "channel-a" in user_prompt
    assert "alpha content" in user_prompt
    assert "Second Source" in user_prompt
    assert "What is alpha?" in user_prompt


def test_answer_question_handles_missing_source_fields(tmp_knowledge_dir, chat_id):
    from src.summarize import answer_question

    client = _make_client("ok")
    sources = [{"extracted_text": "lonely text"}]
    with patch("src.summarize.openai.OpenAI", return_value=client):
        result = answer_question(chat_id, "Q", sources)

    assert result == "ok"
    user_prompt = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert "Source 1" in user_prompt
    assert "?" in user_prompt
    assert "lonely text" in user_prompt


def test_answer_question_returns_none_on_api_error(tmp_knowledge_dir, chat_id):
    from src.summarize import answer_question

    client = _make_client(_api_error("down"))
    with patch("src.summarize.openai.OpenAI", return_value=client):
        result = answer_question(chat_id, "Q", [{"title": "T", "extracted_text": "x"}])

    assert result is None


# ── Profile-driven language + user context injection ──────────────────────


def test_summarize_injects_user_context_block(tmp_knowledge_dir, chat_id, sample_summary_dict):
    from src.profile import init_profile, save_profile
    from src.summarize import summarize_content

    init_profile(chat_id)
    save_profile(chat_id, {
        "language": "ru",
        "persona": "Senior DevOps at small agency",
        "known_stack": ["docker", "n8n"],
        "actively_learning": ["AI agents"],
    })

    client = _make_client(json.dumps(sample_summary_dict))
    with patch("src.summarize.openai.OpenAI", return_value=client):
        summarize_content(chat_id, "content", "T", "S", "youtube_video")

    prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "USER CONTEXT" in prompt
    assert "Senior DevOps at small agency" in prompt
    assert "docker" in prompt
    assert "AI agents" in prompt


def test_summarize_uses_profile_language_ru(tmp_knowledge_dir, chat_id, sample_summary_dict):
    from src.profile import init_profile, save_profile
    from src.summarize import summarize_content

    init_profile(chat_id)
    save_profile(chat_id, {"language": "ru", "persona": "X"})

    client = _make_client(json.dumps(sample_summary_dict))
    with patch("src.summarize.openai.OpenAI", return_value=client):
        summarize_content(chat_id, "content", "T", "S", "youtube_video")

    prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "Write in Russian" in prompt
    assert "Write in English" not in prompt


def test_summarize_uses_profile_language_en(tmp_knowledge_dir, chat_id, sample_summary_dict):
    from src.profile import init_profile, save_profile
    from src.summarize import summarize_content

    init_profile(chat_id)
    save_profile(chat_id, {"language": "en", "persona": "X"})

    client = _make_client(json.dumps(sample_summary_dict))
    with patch("src.summarize.openai.OpenAI", return_value=client):
        summarize_content(chat_id, "content", "T", "S", "youtube_video")

    prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "Write in English" in prompt
    assert "Write in Russian" not in prompt


def test_summarize_defaults_to_en_when_profile_missing(tmp_knowledge_dir, chat_id, sample_summary_dict):
    from src.profile import init_profile
    from src.summarize import summarize_content

    init_profile(chat_id)

    client = _make_client(json.dumps(sample_summary_dict))
    with patch("src.summarize.openai.OpenAI", return_value=client):
        summarize_content(chat_id, "content", "T", "S", "youtube_video")

    prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "Write in English" in prompt
    assert "USER CONTEXT" in prompt


def test_summarize_survives_profile_exception(tmp_knowledge_dir, chat_id, sample_summary_dict):
    from src.summarize import summarize_content

    client = _make_client(json.dumps(sample_summary_dict))
    with (
        patch("src.summarize.openai.OpenAI", return_value=client),
        patch("src.profile.build_relevance_context", side_effect=RuntimeError("boom")),
    ):
        result = summarize_content(chat_id, "content", "T", "S", "youtube_video")

    assert result == sample_summary_dict


def test_language_directives_cover_all_supported_langs():
    from src.strings import SUPPORTED_LANGS
    from src.summarize import LANGUAGE_DIRECTIVES

    for code in SUPPORTED_LANGS:
        assert code in LANGUAGE_DIRECTIVES, f"LANGUAGE_DIRECTIVES missing: {code}"
        assert LANGUAGE_DIRECTIVES[code]


@pytest.mark.parametrize("lang,expected_phrase", [
    ("de", "Write in German"),
    ("fr", "Write in French"),
    ("es", "Write in Spanish"),
    ("it", "Write in Italian"),
    ("pt", "Write in Portuguese"),
    ("zh", "Write in Simplified Chinese"),
    ("ja", "Write in Japanese"),
    ("ar", "Write in Arabic"),
])
def test_summarize_injects_language_directive_for_new_langs(
    tmp_knowledge_dir, chat_id, sample_summary_dict, lang, expected_phrase,
):
    from src.profile import init_profile, save_profile
    from src.summarize import summarize_content

    init_profile(chat_id)
    save_profile(chat_id, {"language": lang, "persona": "test"})

    client = _make_client(json.dumps(sample_summary_dict))
    with patch("src.summarize.openai.OpenAI", return_value=client):
        summarize_content(chat_id, "content", "T", "S", "youtube_video")

    prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert expected_phrase in prompt
