"""Tests for src.categorize — per-user slug validation, LLM fallback."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _mock_response(text: str):
    choice = MagicMock()
    choice.message.content = text
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _mock_client(*responses, exceptions=None):
    """Build a mock OpenAI client that returns the given responses in order.

    Pass `exceptions=[True, False, ...]` to make specific calls raise instead
    of returning a response. Aligned with `responses` by index.
    """
    client = MagicMock()
    if exceptions is None:
        client.chat.completions.create.side_effect = list(responses)
    else:
        effects = []
        for i, resp in enumerate(responses):
            if i < len(exceptions) and exceptions[i]:
                effects.append(Exception("api error"))
            else:
                effects.append(resp)
        client.chat.completions.create.side_effect = effects
    return client


def _seed(chat_id: int, mapping: dict[str, str]) -> None:
    import yaml
    from src.config import ensure_user_dirs, user_categories_file

    ensure_user_dirs(chat_id)
    user_categories_file(chat_id).write_text(yaml.dump(mapping), encoding="utf-8")


def test_categorize_returns_existing_category(tmp_knowledge_dir, chat_id):
    """Known slug returned by LLM → (slug, False)."""
    from src.categorize import categorize_content

    _seed(chat_id, {"ai-agents": "AI Agents"})
    client = _mock_client(_mock_response("ai-agents"))
    with patch("src.categorize.openai.OpenAI", return_value=client):
        slug, is_new = categorize_content(chat_id, "AI Agents Tutorial", "content here")

    assert slug == "ai-agents"
    assert is_new is False


def test_categorize_returns_new_valid_slug(tmp_knowledge_dir, chat_id):
    """Unknown but valid slug → (slug, True)."""
    from src.categorize import categorize_content
    from src.config import ensure_user_dirs

    ensure_user_dirs(chat_id)
    client = _mock_client(_mock_response("machine-learning"))
    with patch("src.categorize.openai.OpenAI", return_value=client):
        slug, is_new = categorize_content(chat_id, "ML Tutorial", "content")

    assert slug == "machine-learning"
    assert is_new is True


def test_categorize_long_slug_triggers_fresh_generation(tmp_knowledge_dir, chat_id):
    """Malformed slug → second LLM call generates a fresh one → (new_slug, True)."""
    from src.categorize import categorize_content
    from src.config import ensure_user_dirs

    ensure_user_dirs(chat_id)
    client = _mock_client(
        _mock_response("a" * 50),
        _mock_response('{"slug": "robotics", "description": "Robotics & Automation"}'),
    )
    with patch("src.categorize.openai.OpenAI", return_value=client):
        slug, is_new = categorize_content(chat_id, "Title", "content")

    assert slug == "robotics"
    assert is_new is True


def test_categorize_non_alnum_slug_triggers_fresh_generation(tmp_knowledge_dir, chat_id):
    """Slug with special chars → fresh-generation kicks in."""
    from src.categorize import categorize_content
    from src.config import ensure_user_dirs

    ensure_user_dirs(chat_id)
    client = _mock_client(
        _mock_response("cat/../hack"),
        _mock_response('{"slug": "security-research", "description": "Sec Research"}'),
    )
    with patch("src.categorize.openai.OpenAI", return_value=client):
        slug, is_new = categorize_content(chat_id, "Title", "content")

    assert slug == "security-research"
    assert is_new is True


def test_categorize_api_error_then_fresh_generation(tmp_knowledge_dir, chat_id):
    """Primary call raises → second call generates a fresh slug."""
    from src.categorize import categorize_content
    from src.config import ensure_user_dirs

    ensure_user_dirs(chat_id)
    client = _mock_client(
        _mock_response(""),  # placeholder, replaced by exception below
        _mock_response('{"slug": "devops", "description": "DevOps"}'),
        exceptions=[True, False],
    )
    with patch("src.categorize.openai.OpenAI", return_value=client):
        slug, is_new = categorize_content(chat_id, "Title", "content")

    assert slug == "devops"
    assert is_new is True


def test_categorize_both_calls_fail_falls_back_to_uncategorized(tmp_knowledge_dir, chat_id):
    """Primary call raises, fresh-generation also fails → per-user 'uncategorized'."""
    from src.categorize import categorize_content
    from src.config import ensure_user_dirs

    ensure_user_dirs(chat_id)
    client = MagicMock()
    client.chat.completions.create.side_effect = Exception("API down")
    with patch("src.categorize.openai.OpenAI", return_value=client):
        slug, is_new = categorize_content(chat_id, "Title", "content")

    assert slug == "uncategorized"
    assert is_new is True  # user doesn't have it yet → new


def test_categorize_fresh_generation_auto_merged_into_existing(tmp_knowledge_dir, chat_id):
    """Fresh slug that's near-duplicate of an existing category is merged, not re-added."""
    from src.categorize import categorize_content

    _seed(chat_id, {"robotics": "Robotics"})
    client = _mock_client(
        _mock_response("!!!garbage!!!"),
        _mock_response('{"slug": "robotic", "description": "Robotic"}'),
    )
    with patch("src.categorize.openai.OpenAI", return_value=client):
        slug, is_new = categorize_content(chat_id, "Title", "content")

    assert slug == "robotics"
    assert is_new is False


def test_categorize_uncategorized_already_exists_is_not_new(tmp_knowledge_dir, chat_id):
    """If user already has `uncategorized`, safety-net returns is_new=False."""
    from src.categorize import categorize_content

    _seed(chat_id, {"uncategorized": "Uncategorized"})
    client = MagicMock()
    client.chat.completions.create.side_effect = Exception("API down")
    with patch("src.categorize.openai.OpenAI", return_value=client):
        slug, is_new = categorize_content(chat_id, "Title", "content")

    assert slug == "uncategorized"
    assert is_new is False


# ── Auto-merge (pure — no chat_id) ─────────────────────────────────────────


def test_auto_merge_returns_existing_for_near_duplicate():
    from src.categorize import _auto_merge

    existing = {"ai-agents": "AI Agents", "wordpress": "WordPress"}
    assert _auto_merge("ai-agent", existing) == "ai-agents"


def test_auto_merge_returns_none_for_dissimilar_slug():
    from src.categorize import _auto_merge

    existing = {"ai-agents": "AI Agents", "wordpress": "WordPress"}
    assert _auto_merge("robotics", existing) is None


def test_auto_merge_picks_closest_match():
    from src.categorize import _auto_merge

    existing = {
        "ai-agents": "AI Agents",
        "ai-news": "AI News",
        "wordpress": "WP",
    }
    assert _auto_merge("ai-agent", existing) == "ai-agents"


def test_auto_merge_empty_categories_returns_none():
    from src.categorize import _auto_merge

    assert _auto_merge("anything", {}) is None


def test_categorize_llm_near_duplicate_is_auto_merged(tmp_knowledge_dir, chat_id):
    from src.categorize import categorize_content

    _seed(chat_id, {"ai-agents": "AI Agents"})
    client = _mock_client(_mock_response("ai-agent"))
    with patch("src.categorize.openai.OpenAI", return_value=client):
        slug, is_new = categorize_content(chat_id, "AI Agents Tutorial", "some content")

    assert slug == "ai-agents"
    assert is_new is False


def test_categorize_llm_genuinely_new_slug_is_new(tmp_knowledge_dir, chat_id):
    from src.categorize import categorize_content
    from src.config import ensure_user_dirs

    ensure_user_dirs(chat_id)
    client = _mock_client(_mock_response("robotics"))
    with patch("src.categorize.openai.OpenAI", return_value=client):
        slug, is_new = categorize_content(chat_id, "Robot Arms Tutorial", "content")

    assert slug == "robotics"
    assert is_new is True
