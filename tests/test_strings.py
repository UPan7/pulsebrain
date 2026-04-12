"""Tests for src.strings — minimal i18n catalog + t() helper."""

from __future__ import annotations

import pytest


# ── Basic lookups ────────────────────────────────────────────────────────


def test_t_returns_russian_by_default():
    from src.strings import t
    text = t("welcome_returning")
    assert "PulseBrain" in text
    assert "готов" in text  # Russian


def test_t_returns_explicit_russian():
    from src.strings import t
    text = t("welcome_returning", "ru")
    assert "готов" in text


def test_t_returns_english_when_requested():
    from src.strings import t
    text = t("welcome_returning", "en")
    assert "ready" in text
    assert "готов" not in text


def test_t_formats_placeholders():
    from src.strings import t
    text = t("language_changed", "en", name="English")
    assert "English" in text
    assert "{name}" not in text


def test_t_ru_placeholder():
    from src.strings import t
    text = t("language_changed", "ru", name="Русский")
    assert "Русский" in text


# ── Fallbacks ─────────────────────────────────────────────────────────────


def test_t_falls_back_to_ru_when_key_missing_in_en():
    """If en is missing a key, return the ru value (not an empty string)."""
    from src.strings import STRINGS, t

    # Inject a fake key that exists only in ru
    original = dict(STRINGS["ru"])
    STRINGS["ru"]["__test_only_ru__"] = "только русский"
    try:
        assert t("__test_only_ru__", "en") == "только русский"
    finally:
        STRINGS["ru"] = original


def test_t_falls_back_to_key_itself_when_missing_everywhere():
    """A typoed key surfaces loudly instead of rendering empty."""
    from src.strings import t
    assert t("__no_such_key__") == "__no_such_key__"
    assert t("__no_such_key__", "en") == "__no_such_key__"


def test_t_unknown_language_falls_back_to_ru():
    from src.strings import t
    # 'de' is unsupported — falls through to ru via the missing-table path
    text = t("welcome_returning", "de")
    assert "готов" in text


def test_t_missing_placeholder_returns_template_unformatted():
    """A missing {name} doesn't crash — returns the raw template."""
    from src.strings import t
    # Deliberately forget the name kwarg
    text = t("language_changed", "ru")
    assert "{name}" in text  # unformatted, not a KeyError


# ── Parity check: every ru key exists in en ──────────────────────────────


def test_every_ru_key_has_en_counterpart():
    """Keep EN in lockstep with RU for the Phase 5 surfaces.

    If this starts being painful (en lagging ru), relax it to a
    warning. For now, keep it strict since the catalog is small.
    """
    from src.strings import STRINGS

    ru_keys = set(STRINGS["ru"].keys())
    en_keys = set(STRINGS["en"].keys())
    missing = ru_keys - en_keys
    assert not missing, f"EN is missing keys: {missing}"


def test_every_en_key_has_ru_counterpart():
    from src.strings import STRINGS

    ru_keys = set(STRINGS["ru"].keys())
    en_keys = set(STRINGS["en"].keys())
    extra = en_keys - ru_keys
    assert not extra, f"EN has keys not in RU: {extra}"


# ── Key coverage for Phase 5 surfaces ────────────────────────────────────


@pytest.mark.parametrize("key", [
    "welcome_returning",
    "welcome_first_run",
    "help_text",
    "language_menu_prompt",
    "language_changed",
    "wizard_lang_prompt",
    "wizard_welcome_body",
    "wizard_persona_prompt",
    "wizard_learning_prompt",
    "wizard_stack_prompt",
    "wizard_notinterested_prompt",
    "wizard_categories_prompt",
    "wizard_channels_prompt",
    "wizard_done",
    "cancel_confirmed",
    "onboarding_confirm_rerun",
])
def test_phase_5_keys_defined_in_both_languages(key):
    from src.strings import STRINGS
    assert key in STRINGS["ru"], f"RU missing: {key}"
    assert key in STRINGS["en"], f"EN missing: {key}"
