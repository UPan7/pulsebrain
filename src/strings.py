"""Minimal i18n string catalog for Phase 5 surfaces.

Scope: only the strings touched by the onboarding wizard, /language,
/start, /help, /cancel. Pre-existing Russian strings elsewhere in the
codebase stay hardcoded and get migrated opportunistically on later
edits — a full refactor of all user-facing strings is explicitly out
of scope.

Usage:

    from src.strings import t
    await update.message.reply_text(t("welcome_returning", "ru"))
    await update.message.reply_text(t("language_changed", "en", name="English"))

Missing keys in a target language fall back to Russian; missing keys
in Russian fall back to the key itself (so a typo surfaces loudly in
the UI instead of silently rendering an empty string).
"""

from __future__ import annotations

from typing import Any

_DEFAULT_LANG = "ru"

# Nested: language → key → template. Every ru key should have an en
# counterpart, but the t() helper tolerates lag.
STRINGS: dict[str, dict[str, str]] = {
    "ru": {
        # ── /start, /help ──
        "welcome_returning": (
            "👋 PulseBrain готов.\n\n"
            "Отправь мне ссылку на YouTube видео, статью или канал — "
            "я обработаю и сохраню в базу знаний.\n\n"
            "Используй /help для списка команд."
        ),
        "welcome_first_run": (
            "👋 Привет! Это твой персональный мозг.\n\n"
            "Давай настроим его под тебя — займёт 3-5 минут. "
            "В любой момент можно прервать командой /cancel."
        ),
        "help_text": (
            "📖 Команды:\n\n"
            "/add <url> [category] — Добавить YouTube канал в мониторинг\n"
            "/remove <name> — Отключить канал\n"
            "/list — Все отслеживаемые каналы\n"
            "/categories — Категории с количеством записей\n"
            "/search <запрос> — Поиск по базе знаний\n"
            "/recent [N] — Последние N записей (по умолч. 5)\n"
            "/pending — Записи на подтверждение\n"
            "/rejected [N] — Последние авто-отклонённые видео\n"
            "/status — Состояние бота\n"
            "/run — Запустить проверку каналов\n"
            "/stats — Подробная статистика\n"
            "/language — Сменить язык интерфейса\n"
            "/onboarding — Перенастроить бота с нуля\n"
            "/cancel — Отменить текущий диалог\n"
            "/help — Эта справка\n\n"
            "Или просто отправь ссылку — бот определит тип и обработает!\n"
            "Или задай вопрос текстом — бот ответит по базе знаний."
        ),

        # ── Language picker ──
        "language_menu_prompt": "Выбери язык интерфейса:",
        "language_changed": "Язык изменён на: {name}",
        "language_name_ru": "Русский",
        "language_name_en": "English",

        # ── Onboarding wizard ──
        "wizard_lang_prompt": "Сначала — выбери язык интерфейса:",
        "wizard_start_button": "▶️ Начать",
        "wizard_skip_button": "⏭ Пропустить",
        "wizard_done_button": "✅ Готово",
        "wizard_welcome_body": (
            "Я буду проводить тебя через несколько вопросов:\n\n"
            "1. Кто ты и чем занимаешься\n"
            "2. Что сейчас изучаешь\n"
            "3. Чем пользуешься в работе\n"
            "4. Чего точно не хочешь видеть\n"
            "5. Стартовые категории и каналы\n\n"
            "В любой момент — /cancel."
        ),
        "wizard_persona_prompt": (
            "Пара предложений о себе: профессия, чем занимаешься, "
            "какой уровень опыта."
        ),
        "wizard_learning_prompt": (
            "Что сейчас активно изучаешь? Каждая тема с новой строки.\n"
            "Например:\n"
            "AI агенты\n"
            "RAG и векторные базы\n"
            "Оптимизация затрат на LLM"
        ),
        "wizard_stack_prompt": (
            "Какими инструментами уже уверенно пользуешься? "
            "По одному в строке."
        ),
        "wizard_notinterested_prompt": (
            "Чего точно не хочешь видеть? Например: крипта, "
            "энтерпрайз-продажи, мобильная разработка. "
            "Можно пропустить."
        ),
        "wizard_categories_prompt": (
            "Стартовые категории. Отметь нужные — остальные не будут "
            "создаваться.\nНажми «Готово» когда закончишь."
        ),
        "wizard_channels_prompt": (
            "Стартовые каналы. Выбери на какие сразу подписать "
            "бота — остальные можно добавить позже через /add."
        ),
        "wizard_channels_empty": (
            "Пресет-каналов пока нет. Добавишь позже через /add."
        ),
        "wizard_done": (
            "✅ Готово!\n\n"
            "Буду следить за каналами каждый час и фильтровать по твоему "
            "профилю. Используй:\n\n"
            "• Кидай ссылки — обработаю любой URL\n"
            "• /pending — очередь на подтверждение\n"
            "• /rejected — что было авто-отклонено\n"
            "• /language — сменить язык\n"
            "• /help — всё остальное"
        ),

        # ── Cancel ──
        "cancel_confirmed": "❌ Отменено. Состояние сброшено.",
        "cancel_nothing_to_cancel": "👌 Нечего отменять.",

        # ── Onboarding re-run confirm ──
        "onboarding_confirm_rerun": (
            "⚠️ Профиль уже настроен. Перезапустить онбординг?\n"
            "Текущий профиль будет перезаписан, но категории и каналы "
            "останутся."
        ),
        "onboarding_rerun_yes": "🔁 Да, перенастроить",
        "onboarding_rerun_no": "🛑 Нет, оставить как есть",
        "onboarding_kept_existing": "👌 Оставил как есть.",
    },
    "en": {
        # ── /start, /help ──
        "welcome_returning": (
            "👋 PulseBrain ready.\n\n"
            "Send me a link to a YouTube video, article or channel — "
            "I'll process it and save it to the knowledge base.\n\n"
            "Use /help for the command list."
        ),
        "welcome_first_run": (
            "👋 Hi! This is your personal brain.\n\n"
            "Let's set it up — takes 3-5 minutes. You can bail at any "
            "time with /cancel."
        ),
        "help_text": (
            "📖 Commands:\n\n"
            "/add <url> [category] — Add a YouTube channel to monitoring\n"
            "/remove <name> — Disable a channel\n"
            "/list — All monitored channels\n"
            "/categories — Categories with entry counts\n"
            "/search <query> — Search the knowledge base\n"
            "/recent [N] — Last N entries (default 5)\n"
            "/pending — Entries awaiting approval\n"
            "/rejected [N] — Recently auto-rejected videos\n"
            "/status — Bot status\n"
            "/run — Force a channel check\n"
            "/stats — Detailed statistics\n"
            "/language — Switch interface language\n"
            "/onboarding — Re-run the setup wizard\n"
            "/cancel — Cancel current dialog\n"
            "/help — This help text\n\n"
            "Or just drop a link — the bot figures out the type.\n"
            "Or ask a question in plain text — the bot answers from the KB."
        ),

        # ── Language picker ──
        "language_menu_prompt": "Pick your interface language:",
        "language_changed": "Language switched to: {name}",
        "language_name_ru": "Русский",
        "language_name_en": "English",

        # ── Onboarding wizard ──
        "wizard_lang_prompt": "First — pick your interface language:",
        "wizard_start_button": "▶️ Start",
        "wizard_skip_button": "⏭ Skip",
        "wizard_done_button": "✅ Done",
        "wizard_welcome_body": (
            "I'll walk you through a few questions:\n\n"
            "1. Who you are and what you do\n"
            "2. What you're currently learning\n"
            "3. What tools you use day-to-day\n"
            "4. What you definitely don't want to see\n"
            "5. Starter categories and channels\n\n"
            "Type /cancel to bail at any time."
        ),
        "wizard_persona_prompt": (
            "A couple sentences about yourself: profession, what you do, "
            "experience level."
        ),
        "wizard_learning_prompt": (
            "What are you actively learning right now? One topic per line.\n"
            "For example:\n"
            "AI agents\n"
            "RAG and vector databases\n"
            "LLM cost optimization"
        ),
        "wizard_stack_prompt": (
            "What tools are you already comfortable with? One per line."
        ),
        "wizard_notinterested_prompt": (
            "What do you definitely not want to see? For example: crypto, "
            "enterprise sales, mobile development. Optional — feel free "
            "to skip."
        ),
        "wizard_categories_prompt": (
            "Starter categories. Tick the ones you want — the rest won't "
            "be created.\nTap Done when you're finished."
        ),
        "wizard_channels_prompt": (
            "Starter channels. Pick which ones to subscribe to now — "
            "others can be added later via /add."
        ),
        "wizard_channels_empty": (
            "No preset channels yet. You can add them later via /add."
        ),
        "wizard_done": (
            "✅ All set!\n\n"
            "I'll check channels every hour and filter by your profile. "
            "Quick reference:\n\n"
            "• Drop any URL — I'll process it\n"
            "• /pending — approval queue\n"
            "• /rejected — what was auto-rejected\n"
            "• /language — switch language\n"
            "• /help — everything else"
        ),

        # ── Cancel ──
        "cancel_confirmed": "❌ Cancelled. State cleared.",
        "cancel_nothing_to_cancel": "👌 Nothing to cancel.",

        # ── Onboarding re-run confirm ──
        "onboarding_confirm_rerun": (
            "⚠️ Profile already set up. Re-run onboarding?\n"
            "Current profile will be overwritten, but categories and "
            "channels will stay."
        ),
        "onboarding_rerun_yes": "🔁 Yes, redo it",
        "onboarding_rerun_no": "🛑 No, keep it",
        "onboarding_kept_existing": "👌 Keeping it as is.",
    },
}


def t(key: str, lang: str = _DEFAULT_LANG, **fmt: Any) -> str:
    """Lookup + format. Falls back to ru when the key is missing in *lang*.

    Falls back to the key itself if missing in both languages — this is
    intentional: a typo or forgotten migration surfaces loudly in the
    UI instead of silently rendering an empty string.
    """
    table = STRINGS.get(lang) or {}
    template = table.get(key) or STRINGS[_DEFAULT_LANG].get(key) or key
    if fmt:
        try:
            return template.format(**fmt)
        except (KeyError, IndexError):
            return template
    return template
