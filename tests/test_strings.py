"""Tests for src.strings — minimal i18n catalog + t() helper."""

from __future__ import annotations

import pytest


# ── Basic lookups ────────────────────────────────────────────────────────


def test_t_returns_english_by_default():
    from src.strings import t
    text = t("welcome_returning")
    assert "PulseBrain" in text
    assert "ready" in text  # English is the default now


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


def test_language_native_names_cover_all_supported_langs():
    """Every language in SUPPORTED_LANGS has a native-name entry."""
    from src.strings import LANGUAGE_NATIVE_NAMES, SUPPORTED_LANGS
    for lang in SUPPORTED_LANGS:
        assert lang in LANGUAGE_NATIVE_NAMES
        assert LANGUAGE_NATIVE_NAMES[lang]  # non-empty


def test_language_flags_cover_all_supported_langs():
    from src.strings import LANGUAGE_FLAGS, SUPPORTED_LANGS
    for lang in SUPPORTED_LANGS:
        assert lang in LANGUAGE_FLAGS
        assert LANGUAGE_FLAGS[lang]


# ── Fallbacks ─────────────────────────────────────────────────────────────


def test_t_falls_back_to_en_when_key_missing_in_target_lang():
    """If the target lang is missing a key, return the English value."""
    from src.strings import STRINGS, t

    # Inject a fake key that exists only in English
    original = dict(STRINGS["en"])
    STRINGS["en"]["__test_only_en__"] = "english only"
    try:
        # Request in de — should fall through to en, not the key
        assert t("__test_only_en__", "de") == "english only"
        # Request in ru — same fallback
        assert t("__test_only_en__", "ru") == "english only"
    finally:
        STRINGS["en"] = original


def test_t_falls_back_to_key_itself_when_missing_everywhere():
    """A typoed key surfaces loudly instead of rendering empty."""
    from src.strings import t
    assert t("__no_such_key__") == "__no_such_key__"
    assert t("__no_such_key__", "en") == "__no_such_key__"


def test_t_unknown_language_falls_back_to_en():
    from src.strings import t
    # A truly fake language code — falls through to en via the missing-table path
    text = t("welcome_returning", "xx")
    assert "ready" in text  # English fallback


def test_t_missing_placeholder_returns_template_unformatted():
    """A missing {name} doesn't crash — returns the raw template."""
    from src.strings import t
    # Deliberately forget the name kwarg
    text = t("language_changed", "en")
    assert "{name}" in text  # unformatted, not a KeyError


# ── Parity check: every language covers the English key set ─────────────


def test_every_language_covers_english_keys():
    """English is the authoritative source — every other language must
    cover its full key set (missing keys fall back to en, but we want
    the catalog to be complete so users never see English when they
    asked for something else).
    """
    from src.strings import STRINGS, SUPPORTED_LANGS

    en_keys = set(STRINGS["en"].keys())
    for lang in SUPPORTED_LANGS:
        if lang == "en":
            continue
        lang_keys = set(STRINGS.get(lang, {}).keys())
        missing = en_keys - lang_keys
        assert not missing, f"{lang!r} is missing keys: {sorted(missing)}"


def test_no_language_has_extra_keys_beyond_english():
    """If a non-English catalog defines keys that English doesn't,
    that's a typo or forgotten cleanup — flag it loudly.
    """
    from src.strings import STRINGS, SUPPORTED_LANGS

    en_keys = set(STRINGS["en"].keys())
    for lang in SUPPORTED_LANGS:
        if lang == "en":
            continue
        lang_keys = set(STRINGS.get(lang, {}).keys())
        extra = lang_keys - en_keys
        assert not extra, f"{lang!r} has keys not in EN: {sorted(extra)}"


# ── Translation invariants (Phase 7.2) ───────────────────────────────────


def _extract_placeholders(template: str) -> set[str]:
    """Pull out the {name}-style placeholders from a format-string template."""
    import re
    # Match {word} but ignore doubled braces {{ }} (escaped literal braces)
    return set(re.findall(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})", template))


def test_all_templates_preserve_english_placeholders():
    """Every translation must keep the exact set of {placeholders} the
    English template has. Missing or renamed placeholders would break
    the .format() call at runtime.
    """
    from src.strings import STRINGS, SUPPORTED_LANGS

    en = STRINGS["en"]
    for key, en_template in en.items():
        expected = _extract_placeholders(en_template)
        for lang in SUPPORTED_LANGS:
            if lang == "en":
                continue
            lang_template = STRINGS.get(lang, {}).get(key)
            if lang_template is None:
                continue  # covered by the key-coverage test
            actual = _extract_placeholders(lang_template)
            assert actual == expected, (
                f"{lang}:{key} placeholder mismatch — "
                f"expected {sorted(expected)}, got {sorted(actual)}"
            )


def test_all_templates_format_with_dummy_args():
    """Every template must .format() cleanly when given values for
    every placeholder in the English version. Catches stray { or } that
    Python's format machinery would choke on.
    """
    from src.strings import STRINGS, SUPPORTED_LANGS

    en = STRINGS["en"]
    for key, en_template in en.items():
        placeholders = _extract_placeholders(en_template)
        dummy_args = {name: f"<{name}>" for name in placeholders}
        for lang in SUPPORTED_LANGS:
            template = STRINGS.get(lang, {}).get(key)
            if template is None:
                continue
            try:
                template.format(**dummy_args)
            except (KeyError, IndexError, ValueError) as exc:
                raise AssertionError(
                    f"{lang}:{key} failed to .format() with {dummy_args!r}: {exc}"
                )


def test_t_fallback_chain_lang_to_en_to_key():
    """Missing key in zh should fall through to English, not ru."""
    from src.strings import STRINGS, t

    # Inject a fake English-only key
    STRINGS["en"]["__chain_test__"] = "english chain value"
    try:
        # Request from Chinese — should land on English, not 'ru' or key
        assert t("__chain_test__", "zh") == "english chain value"
        # Request from Russian — same fallback
        assert t("__chain_test__", "ru") == "english chain value"
    finally:
        STRINGS["en"].pop("__chain_test__", None)


# ── Key coverage for Phase 5 surfaces ────────────────────────────────────


@pytest.mark.parametrize("key", [
    "welcome_returning",
    "welcome_first_run",
    "help_text",
    "language_menu_prompt",
    "language_changed",
    "wizard_lang_prompt",
    "wizard_lang_saved",
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
    "round_digest_body",
])
def test_phase_5_keys_defined_in_english(key):
    """Regression: every Phase 5 / 6 key lives in the English catalog."""
    from src.strings import STRINGS
    assert key in STRINGS["en"], f"EN missing: {key}"
