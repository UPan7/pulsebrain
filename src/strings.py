"""i18n string catalog + t() helper — World 10 language support.

Scope: all user-facing strings in the bot — commands, buttons, errors,
wizard prompts, notifications. The catalog is the single source of
truth; callers render via t(key, lang, **fmt).

Supported languages (World 10 set):

    en (English — default)     es (Spanish)
    de (German)                it (Italian)
    fr (French)                pt (Portuguese)
    zh (Chinese, simplified)   ja (Japanese)
    ru (Russian)               ar (Arabic)

Usage:

    from src.strings import t
    await update.message.reply_text(t("welcome_returning", "en"))
    await update.message.reply_text(t("language_changed", "de", name="Deutsch"))

Fallback chain: requested lang → English → key itself. A typoed or
missing key surfaces loudly as its own string (e.g. "no_such_key")
instead of silently rendering empty.
"""

from __future__ import annotations

from typing import Any

# Canonical tuple of supported language codes. Imported by profile,
# onboarding, and telegram_bot so the whitelist lives in one place.
# Order matters for UI rendering (the /language picker renders in
# this order as 2×5 flag buttons).
SUPPORTED_LANGS: tuple[str, ...] = (
    "en", "de", "fr", "es", "it",
    "pt", "zh", "ja", "ru", "ar",
)

_DEFAULT_LANG = "en"

# Native names for the language picker. These don't need per-locale
# translations — "Deutsch" is "Deutsch" in every language. Kept as a
# flat dict instead of per-catalog entries to avoid 10×10 duplication.
LANGUAGE_NATIVE_NAMES: dict[str, str] = {
    "en": "English",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "it": "Italiano",
    "pt": "Português",
    "zh": "中文",
    "ja": "日本語",
    "ru": "Русский",
    "ar": "العربية",
}

# Emoji flags for the 2×5 picker keyboard. Flag-then-native-name is
# the standard inline-button layout.
LANGUAGE_FLAGS: dict[str, str] = {
    "en": "🇬🇧",
    "de": "🇩🇪",
    "fr": "🇫🇷",
    "es": "🇪🇸",
    "it": "🇮🇹",
    "pt": "🇵🇹",
    "zh": "🇨🇳",
    "ja": "🇯🇵",
    "ru": "🇷🇺",
    "ar": "🇸🇦",
}


# Nested: language → key → template. English (en) is the authoritative
# source — every other language must cover the full en key set, and the
# t() helper falls back lang → en → key when a translation lags.
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
            "👋 Привет! Я PulseBrain — твой персональный агрегатор знаний.\n\n"
            "Ты сохраняешь кучу всего «на потом» и никогда не возвращаешься. "
            "Я это чиню:\n"
            "• 📎 Кидай ссылку на YouTube-видео или статью — я делаю саммари "
            "и раскладываю по категориям.\n"
            "• 📡 Подпиши меня на YouTube-каналы — буду следить и присылать "
            "новые видео на твоё одобрение.\n"
            "• 💬 Задавай вопросы обычным текстом — поищу в твоей базе и "
            "отвечу со ссылками на источники.\n"
            "• 📂 Всё остаётся твоим — обычные markdown-файлы, никакого "
            "vendor lock-in.\n\n"
            "Давай потратим 3 минуты на настройку профиля — чтобы я оценивал "
            "релевантность конкретно под тебя. /cancel — выйти в любой момент."
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
            "/get <id> — Полный текст + скачать .md/raw файлы\n"
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

        # ── Scheduler round digest ──
        "round_digest_body": (
            "🔄 Прогон завершён\n\n"
            "Каналов проверено: {channels}\n"
            "Новых в /pending: {processed}\n"
            "Авто-отклонено: {rejected}\n"
            "Ошибок: {failed}\n\n"
            "Следующий через {interval} мин"
        ),

        # ── Wizard language-picker confirmation ──
        "wizard_lang_saved": "✅ Язык сохранён.",

        # ── Onboarding re-run confirm ──
        "onboarding_confirm_rerun": (
            "⚠️ Профиль уже настроен. Перезапустить онбординг?\n"
            "Текущий профиль будет перезаписан, но категории и каналы "
            "останутся."
        ),
        "onboarding_rerun_yes": "🔁 Да, перенастроить",
        "onboarding_rerun_no": "🛑 Нет, оставить как есть",
        "onboarding_kept_existing": "👌 Оставил как есть.",

        # ── Phase 7.3a ──
        "pending_summary_label": "Саммари",
        "pending_category_label": "Категория",
        "pending_new_cat_marker": " 🆕 (новая!)",
        "pending_relevance_label": "Релевантность",
        "pending_awaiting_label": "⏳ Ожидает подтверждения",
        "pending_btn_save": "✅ Сохранить",
        "pending_btn_reject": "❌ Отклонить",
        "pending_btn_category": "🔄 Категория",
        "pending_btn_new_category": "➕ Новая категория",
        "pending_saved_suffix": "\n\n✅ Сохранено: {path}",
        "pending_rejected_suffix": "\n\n❌ Отклонено",
        "pending_record_gone": "⚠️ Запись больше не в очереди.",
        "pending_save_failed": "⚠️ Не удалось сохранить запись.",
        "list_empty": "📡 Нет отслеживаемых каналов.",
        "list_header": "📡 Отслеживаемые каналы:\n",
        "add_usage": "Использование: /add <youtube_url> [category]",
        "add_resolving": "⏳ Определяю канал...",
        "add_resolve_failed": "⚠️ Не удалось определить канал по ссылке.",
        "add_already_tracked": "Канал {name} уже отслеживается.",
        "add_added_to_category": "✅ Канал {name} добавлен в категорию {category}.",
        "add_pick_category": "📡 Канал: {name}\nВыбери категорию:",
        "remove_usage": "Использование: /remove <channel_name>",
        "remove_disabled": "⏸ Канал {name} отключён.",
        "remove_not_found": "Канал '{name}' не найден.",
        "categories_empty": "📂 Пока нет записей.",
        "categories_header": "📂 Категории:\n",
        "categories_stale_marker": " (давно тихо)",
        "categories_entry_count": "{count} записей",
        "categories_item_line": "    ⭐ avg {avg}   📅 последняя: {last}",
        "search_usage": "Использование: /search <запрос>",
        "search_nothing": "🔍 По запросу \"{query}\" ничего не найдено.",
        "search_found_header": "🔍 Найдено {count} результатов по \"{query}\":\n",
        "recent_empty": "📋 Пока нет записей.",
        "recent_header": "📋 Последние {count} записей:\n",
        "status_body": (
            "📁 Записей: {total}\n"
            "📺 Видео: {videos}\n"
            "📰 Статей: {articles}\n"
            "📡 Каналов: {active}/{all}\n"
            "📊 Средняя релевантность: {avg}/10\n"
            "📅 За эту неделю: {this_week}\n"
        ),
        "run_starting": "🔄 Запускаю проверку каналов...",
        "run_processed": "✅ Обработано {count} новых видео.",
        "run_nothing": "✅ Новых видео не найдено.",
        "pending_queue_empty": "📭 Очередь на подтверждение пуста.",
        "pending_queue_header": "⏳ В очереди: {count} (показываю последние 10)",
        "reject_reason_low_relevance": "низкая релевантность",
        "reject_reason_manual": "вручную",
        "rejected_empty": (
            "📭 Лог отклонённых пуст.\n"
            "Ничего не было авто-отклонено — либо порог релевантности "
            "достаточно мягкий, либо новых видео пока не было."
        ),
        "rejected_header": "❌ Последние {count} отклонённых:\n",
        "processing_video": "⏳ Обрабатываю видео...",
        "processing_unknown_error": "⚠️ Произошла неизвестная ошибка.",
        "processing_article": "⏳ Читаю статью...",
        "channel_add_pick_category": (
            "📡 Канал: {name}\n"
            "Добавить в мониторинг?\n\n"
            "Выбери категорию:"
        ),
        "qa_searching": "🔍 Ищу в базе знаний...",
        "qa_nothing": (
            "🤷 По этой теме пока ничего не собрано.\n"
            "Попробуй уточнить запрос или скинь мне ссылку на материал по этой теме."
        ),
        "qa_failed": "⚠️ Не удалось сформировать ответ. Попробуй позже.",
        "qa_answer_header": "🧠 На основе {count} источников:",
        "qa_sources_header": "📚 Источники:",
        "new_cat_invalid_slug": (
            "⚠️ Некорректный slug. Используй латиницу, цифры и дефис "
            "(до 30 символов)."
        ),
        "new_cat_created_lost": (
            "✅ Категория `{slug}` создана, но данные канала потеряны. "
            "Попробуй /add ещё раз."
        ),
        "new_cat_created_channel_added": (
            "✅ Категория `{slug}` создана.\n"
            "✅ Канал {name} добавлен.\n\n"
            "Загрузить последние 3 видео?"
        ),
        "new_cat_created_no_record": (
            "✅ Категория `{slug}` создана, но запись больше не в очереди."
        ),
        "new_cat_prompt": (
            "✏️ Введи slug новой категории (например: `machine-learning`).\n"
            "Можно через пробел добавить описание:"
        ),
        "new_cat_btn_yes": "✅ Да",
        "new_cat_btn_no": "❌ Нет",
        "channel_data_lost": "⚠️ Данные канала потеряны, попробуйте ещё раз.",
        "channel_added_fetch_prompt": (
            "✅ Канал {name} добавлен в категорию {category}.\n\n"
            "Загрузить последние 3 видео?"
        ),
        "fetch_starting": "⏳ Загружаю последние видео...",
        "fetch_processed": "✅ Обработано {done} из {total} видео.",
        "fetch_skipped": "👌 Хорошо, видео не загружены.",
        "error_notify_body": "⚠️ Ошибка при обработке:\n{title}\n{error}",

        # ── Phase 7.3b ──
        "pipeline_err_video_id_extract": "Не удалось извлечь ID видео из ссылки.",
        "pipeline_err_video_already_processed": "Это видео уже обработано.",
        "pipeline_err_transcript_unavailable": "Транскрипт недоступен для: {title}",
        "pipeline_err_article_already_processed": "Эта статья уже обработана.",
        "pipeline_err_web_extract_failed": (
            "Не удалось извлечь контент с этой страницы.\n"
            "Возможно, сайт требует JavaScript или блокирует парсинг."
        ),
        "pipeline_err_unknown_source_type": "Неизвестный тип контента: {source_type}",
        "pipeline_err_summarize_failed": "Не удалось создать саммари для: {title}",

        # ── Phase 7.9 / Phase 8 ──
        "get_usage": (
            "Использование:\n"
            "• /get — браузер по категориям\n"
            "• /get <entry_id> — открыть запись по 8-значному ID"
        ),
        "get_not_found": (
            "⚠️ Запись `{entry_id}` не найдена. Запусти /recent или "
            "/search чтобы увидеть актуальные ID."
        ),
        "get_read_failed": "⚠️ Не удалось прочитать файл записи с диска.",
        "recent_get_hint": "💡 /get — браузер по категориям",
        "get_pick_category": "📂 Выбери категорию:",
        "get_pick_entry": "📁 {category} — записей: {count}. Выбери:",
        "get_empty_base": "📭 База знаний пуста. Кинь мне ссылку — и начнём.",
        "get_category_empty": "📭 В этой категории пока ничего нет.",
        "entry_btn_md_file": "📄 Саммари (.md)",
        "entry_btn_raw_file": "📜 Полный исходник",
        "entry_no_raw_text": "Сырого текста для этой записи нет.",
        "entry_file_caption": "📎 {name}",
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
            "👋 Hi! I'm PulseBrain — your personal knowledge aggregator.\n\n"
            "You save a ton of stuff \"for later\" and never come back to it. "
            "I fix that:\n"
            "• 📎 Drop me a YouTube or article link — I summarize it and file "
            "it by category.\n"
            "• 📡 Subscribe me to YouTube channels — I watch them on schedule "
            "and queue new videos for your review.\n"
            "• 💬 Ask me questions in plain text — I search your knowledge "
            "base and answer with source citations.\n"
            "• 📂 Everything stays yours — plain markdown files, no cloud "
            "lock-in.\n\n"
            "Let's spend 3 minutes setting up your profile so I can score "
            "relevance for what YOU actually care about. /cancel to stop."
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
            "/get <id> — Full text + download the .md/raw files\n"
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

        # ── Scheduler round digest ──
        "round_digest_body": (
            "🔄 Round complete\n\n"
            "Channels checked: {channels}\n"
            "New in /pending: {processed}\n"
            "Auto-rejected: {rejected}\n"
            "Errors: {failed}\n\n"
            "Next in {interval} min"
        ),

        # ── Wizard language-picker confirmation ──
        "wizard_lang_saved": "✅ Language saved.",

        # ── Onboarding re-run confirm ──
        "onboarding_confirm_rerun": (
            "⚠️ Profile already set up. Re-run onboarding?\n"
            "Current profile will be overwritten, but categories and "
            "channels will stay."
        ),
        "onboarding_rerun_yes": "🔁 Yes, redo it",
        "onboarding_rerun_no": "🛑 No, keep it",
        "onboarding_kept_existing": "👌 Keeping it as is.",

        # ── Phase 7.3a: pending / commands / link processing ──
        "pending_summary_label": "Summary",
        "pending_category_label": "Category",
        "pending_new_cat_marker": " 🆕 (new!)",
        "pending_relevance_label": "Relevance",
        "pending_awaiting_label": "⏳ Awaiting approval",
        "pending_btn_save": "✅ Save",
        "pending_btn_reject": "❌ Reject",
        "pending_btn_category": "🔄 Category",
        "pending_btn_new_category": "➕ New category",
        "pending_saved_suffix": "\n\n✅ Saved: {path}",
        "pending_rejected_suffix": "\n\n❌ Rejected",
        "pending_record_gone": "⚠️ Entry no longer in queue.",
        "pending_save_failed": "⚠️ Failed to save entry.",
        "list_empty": "📡 No monitored channels.",
        "list_header": "📡 Monitored channels:\n",
        "add_usage": "Usage: /add <youtube_url> [category]",
        "add_resolving": "⏳ Resolving channel...",
        "add_resolve_failed": "⚠️ Couldn't resolve the channel from that link.",
        "add_already_tracked": "Channel {name} is already being tracked.",
        "add_added_to_category": "✅ Channel {name} added to category {category}.",
        "add_pick_category": "📡 Channel: {name}\nPick a category:",
        "remove_usage": "Usage: /remove <channel_name>",
        "remove_disabled": "⏸ Channel {name} disabled.",
        "remove_not_found": "Channel '{name}' not found.",
        "categories_empty": "📂 No entries yet.",
        "categories_header": "📂 Categories:\n",
        "categories_stale_marker": " (stale)",
        "categories_entry_count": "{count} entries",
        "categories_item_line": "    ⭐ avg {avg}   📅 last: {last}",
        "search_usage": "Usage: /search <query>",
        "search_nothing": "🔍 Nothing found for \"{query}\".",
        "search_found_header": "🔍 Found {count} results for \"{query}\":\n",
        "recent_empty": "📋 No entries yet.",
        "recent_header": "📋 Last {count} entries:\n",
        "status_body": (
            "📁 Entries: {total}\n"
            "📺 Videos: {videos}\n"
            "📰 Articles: {articles}\n"
            "📡 Channels: {active}/{all}\n"
            "📊 Avg relevance: {avg}/10\n"
            "📅 This week: {this_week}\n"
        ),
        "run_starting": "🔄 Running channel check...",
        "run_processed": "✅ Processed {count} new videos.",
        "run_nothing": "✅ No new videos found.",
        "pending_queue_empty": "📭 Approval queue is empty.",
        "pending_queue_header": "⏳ In queue: {count} (showing last 10)",
        "reject_reason_low_relevance": "low relevance",
        "reject_reason_manual": "manual",
        "rejected_empty": (
            "📭 Rejected log is empty.\n"
            "Nothing was auto-rejected — either the relevance threshold "
            "is soft enough, or no new videos arrived yet."
        ),
        "rejected_header": "❌ Last {count} rejected:\n",
        "processing_video": "⏳ Processing video...",
        "processing_unknown_error": "⚠️ Unknown error occurred.",
        "processing_article": "⏳ Reading article...",
        "channel_add_pick_category": (
            "📡 Channel: {name}\n"
            "Add to monitoring?\n\n"
            "Pick a category:"
        ),
        "qa_searching": "🔍 Searching knowledge base...",
        "qa_nothing": (
            "🤷 Nothing collected on this topic yet.\n"
            "Try refining the query or drop me a link on the subject."
        ),
        "qa_failed": "⚠️ Failed to produce an answer. Try later.",
        "qa_answer_header": "🧠 Based on {count} sources:",
        "qa_sources_header": "📚 Sources:",
        "new_cat_invalid_slug": (
            "⚠️ Invalid slug. Use ASCII letters, digits, and dashes "
            "(max 30 chars)."
        ),
        "new_cat_created_lost": (
            "✅ Category `{slug}` created, but channel data was lost. "
            "Try /add again."
        ),
        "new_cat_created_channel_added": (
            "✅ Category `{slug}` created.\n"
            "✅ Channel {name} added.\n\n"
            "Fetch the last 3 videos?"
        ),
        "new_cat_created_no_record": (
            "✅ Category `{slug}` created, but the entry is no longer in "
            "the queue."
        ),
        "new_cat_prompt": (
            "✏️ Enter the slug for the new category "
            "(e.g. `machine-learning`).\n"
            "Optionally add a description after a space:"
        ),
        "new_cat_btn_yes": "✅ Yes",
        "new_cat_btn_no": "❌ No",
        "channel_data_lost": "⚠️ Channel data lost, please try again.",
        "channel_added_fetch_prompt": (
            "✅ Channel {name} added to category {category}.\n\n"
            "Fetch the last 3 videos?"
        ),
        "fetch_starting": "⏳ Fetching latest videos...",
        "fetch_processed": "✅ Processed {done} out of {total} videos.",
        "fetch_skipped": "👌 OK, videos not fetched.",
        "error_notify_body": "⚠️ Error while processing:\n{title}\n{error}",

        # ── Phase 7.3b: pipeline error messages ──
        "pipeline_err_video_id_extract": "Couldn't extract video ID from the link.",
        "pipeline_err_video_already_processed": "This video has already been processed.",
        "pipeline_err_transcript_unavailable": "Transcript unavailable for: {title}",
        "pipeline_err_article_already_processed": "This article has already been processed.",
        "pipeline_err_web_extract_failed": (
            "Couldn't extract content from this page.\n"
            "The site may require JavaScript or block scraping."
        ),
        "pipeline_err_unknown_source_type": "Unknown content type: {source_type}",
        "pipeline_err_summarize_failed": "Couldn't produce a summary for: {title}",

        # ── Phase 7.9 / Phase 8: /get command + browser ──
        "get_usage": (
            "Usage:\n"
            "• /get — browse by category\n"
            "• /get <entry_id> — open a specific entry by its 8-char ID"
        ),
        "get_not_found": (
            "⚠️ Entry `{entry_id}` not found. Run /recent or /search to "
            "see current IDs."
        ),
        "get_read_failed": "⚠️ Failed to read the entry file from disk.",
        "recent_get_hint": "💡 /get — browse by category",
        "get_pick_category": "📂 Pick a category to browse:",
        "get_pick_entry": "📁 {category} — {count} entries. Pick one:",
        "get_empty_base": "📭 Knowledge base is empty. Drop me a link first.",
        "get_category_empty": "📭 No entries in this category yet.",
        "entry_btn_md_file": "📄 Summary (.md)",
        "entry_btn_raw_file": "📜 Full source",
        "entry_no_raw_text": "No raw-text sidecar for this entry.",
        "entry_file_caption": "📎 {name}",
    },
    "de": {
        "welcome_returning": (
            "👋 PulseBrain ist bereit.\n\n"
            "Sende mir einen Link zu einem YouTube-Video, Artikel oder "
            "Kanal — ich verarbeite ihn und speichere ihn in deiner "
            "Wissensdatenbank.\n\n"
            "Nutze /help für die Befehlsliste."
        ),
        "welcome_first_run": (
            "👋 Hallo! Ich bin PulseBrain — dein persönlicher "
            "Wissens-Aggregator.\n\n"
            "Du speicherst vieles „für später\" und kommst nie darauf "
            "zurück. Das behebe ich:\n"
            "• 📎 Schick mir einen YouTube- oder Artikel-Link — ich fasse "
            "ihn zusammen und sortiere ihn ein.\n"
            "• 📡 Abonniere mich zu YouTube-Kanälen — ich überwache sie und "
            "stelle neue Videos zur Freigabe.\n"
            "• 💬 Stelle Fragen im Klartext — ich durchsuche deine "
            "Wissensbasis und antworte mit Quellenangaben.\n"
            "• 📂 Alles bleibt bei dir — einfache Markdown-Dateien, kein "
            "Cloud-Lock-in.\n\n"
            "Nehmen wir uns 3 Minuten für dein Profil, damit ich Relevanz "
            "passend für DICH bewerten kann. /cancel zum Abbrechen."
        ),
        "help_text": (
            "📖 Befehle:\n\n"
            "/add <url> [category] — YouTube-Kanal zur Überwachung hinzufügen\n"
            "/remove <name> — Kanal deaktivieren\n"
            "/list — Alle überwachten Kanäle\n"
            "/categories — Kategorien mit Eintragszahl\n"
            "/search <query> — Wissensdatenbank durchsuchen\n"
            "/recent [N] — Letzte N Einträge (Standard 5)\n"
            "/pending — Einträge warten auf Bestätigung\n"
            "/rejected [N] — Kürzlich auto-abgelehnte Videos\n"
            "/get <id> — Volltext + .md/Rohdatei herunterladen\n"
            "/status — Bot-Status\n"
            "/run — Kanalprüfung erzwingen\n"
            "/stats — Detaillierte Statistik\n"
            "/language — Oberflächensprache wechseln\n"
            "/onboarding — Setup-Assistent erneut starten\n"
            "/cancel — Aktuellen Dialog abbrechen\n"
            "/help — Diese Hilfe\n\n"
            "Oder sende einfach einen Link — der Bot erkennt den Typ.\n"
            "Oder stelle eine Frage als Text — der Bot antwortet aus der "
            "Wissensdatenbank."
        ),
        "language_menu_prompt": "Wähle deine Oberflächensprache:",
        "language_changed": "Sprache gewechselt zu: {name}",
        "wizard_lang_prompt": "Zuerst — wähle deine Oberflächensprache:",
        "wizard_start_button": "▶️ Start",
        "wizard_skip_button": "⏭ Überspringen",
        "wizard_done_button": "✅ Fertig",
        "wizard_welcome_body": (
            "Ich führe dich durch ein paar Fragen:\n\n"
            "1. Wer du bist und was du machst\n"
            "2. Was du gerade lernst\n"
            "3. Welche Tools du täglich benutzt\n"
            "4. Was du definitiv nicht sehen willst\n"
            "5. Starter-Kategorien und -Kanäle\n\n"
            "Tippe /cancel, um jederzeit abzubrechen."
        ),
        "wizard_persona_prompt": (
            "Ein paar Sätze über dich: Beruf, was du machst, Erfahrungslevel."
        ),
        "wizard_learning_prompt": (
            "Was lernst du gerade aktiv? Ein Thema pro Zeile.\n"
            "Zum Beispiel:\n"
            "AI-Agenten\n"
            "RAG und Vektordatenbanken\n"
            "LLM-Kostenoptimierung"
        ),
        "wizard_stack_prompt": (
            "Mit welchen Tools arbeitest du bereits sicher? Eines pro Zeile."
        ),
        "wizard_notinterested_prompt": (
            "Was willst du definitiv nicht sehen? Zum Beispiel: Krypto, "
            "Enterprise-Vertrieb, Mobile-Entwicklung. Optional — du kannst "
            "überspringen."
        ),
        "wizard_categories_prompt": (
            "Starter-Kategorien. Wähle die gewünschten aus — der Rest wird "
            "nicht erstellt.\nTippe Fertig, wenn du fertig bist."
        ),
        "wizard_channels_prompt": (
            "Starter-Kanäle. Wähle, welche du jetzt abonnieren willst — "
            "weitere kannst du später über /add hinzufügen."
        ),
        "wizard_channels_empty": (
            "Noch keine voreingestellten Kanäle. Du kannst sie später über "
            "/add hinzufügen."
        ),
        "wizard_done": (
            "✅ Alles bereit!\n\n"
            "Ich prüfe Kanäle jede Stunde und filtere nach deinem Profil. "
            "Kurzübersicht:\n\n"
            "• Sende eine URL — ich verarbeite sie\n"
            "• /pending — Genehmigungswarteschlange\n"
            "• /rejected — was auto-abgelehnt wurde\n"
            "• /language — Sprache wechseln\n"
            "• /help — alles andere"
        ),
        "cancel_confirmed": "❌ Abgebrochen. Status zurückgesetzt.",
        "cancel_nothing_to_cancel": "👌 Nichts zum Abbrechen.",
        "round_digest_body": (
            "🔄 Lauf abgeschlossen\n\n"
            "Kanäle geprüft: {channels}\n"
            "Neu in /pending: {processed}\n"
            "Auto-abgelehnt: {rejected}\n"
            "Fehler: {failed}\n\n"
            "Nächster in {interval} Min"
        ),
        "wizard_lang_saved": "✅ Sprache gespeichert.",
        "onboarding_confirm_rerun": (
            "⚠️ Profil bereits eingerichtet. Onboarding erneut starten?\n"
            "Aktuelles Profil wird überschrieben, aber Kategorien und "
            "Kanäle bleiben."
        ),
        "onboarding_rerun_yes": "🔁 Ja, neu einrichten",
        "onboarding_rerun_no": "🛑 Nein, so lassen",
        "onboarding_kept_existing": "👌 Alles gelassen.",

        # ── Phase 7.3a ──
        "pending_summary_label": "Zusammenfassung",
        "pending_category_label": "Kategorie",
        "pending_new_cat_marker": " 🆕 (neu!)",
        "pending_relevance_label": "Relevanz",
        "pending_awaiting_label": "⏳ Wartet auf Bestätigung",
        "pending_btn_save": "✅ Speichern",
        "pending_btn_reject": "❌ Ablehnen",
        "pending_btn_category": "🔄 Kategorie",
        "pending_btn_new_category": "➕ Neue Kategorie",
        "pending_saved_suffix": "\n\n✅ Gespeichert: {path}",
        "pending_rejected_suffix": "\n\n❌ Abgelehnt",
        "pending_record_gone": "⚠️ Eintrag nicht mehr in der Warteschlange.",
        "pending_save_failed": "⚠️ Speichern fehlgeschlagen.",
        "list_empty": "📡 Keine überwachten Kanäle.",
        "list_header": "📡 Überwachte Kanäle:\n",
        "add_usage": "Verwendung: /add <youtube_url> [category]",
        "add_resolving": "⏳ Kanal wird aufgelöst...",
        "add_resolve_failed": "⚠️ Konnte den Kanal aus dem Link nicht ermitteln.",
        "add_already_tracked": "Kanal {name} wird bereits überwacht.",
        "add_added_to_category": "✅ Kanal {name} zur Kategorie {category} hinzugefügt.",
        "add_pick_category": "📡 Kanal: {name}\nWähle eine Kategorie:",
        "remove_usage": "Verwendung: /remove <channel_name>",
        "remove_disabled": "⏸ Kanal {name} deaktiviert.",
        "remove_not_found": "Kanal '{name}' nicht gefunden.",
        "categories_empty": "📂 Noch keine Einträge.",
        "categories_header": "📂 Kategorien:\n",
        "categories_stale_marker": " (veraltet)",
        "categories_entry_count": "{count} Einträge",
        "categories_item_line": "    ⭐ Ø {avg}   📅 letzte: {last}",
        "search_usage": "Verwendung: /search <query>",
        "search_nothing": "🔍 Nichts gefunden für \"{query}\".",
        "search_found_header": "🔍 {count} Ergebnisse für \"{query}\":\n",
        "recent_empty": "📋 Noch keine Einträge.",
        "recent_header": "📋 Letzte {count} Einträge:\n",
        "status_body": (
            "📁 Einträge: {total}\n"
            "📺 Videos: {videos}\n"
            "📰 Artikel: {articles}\n"
            "📡 Kanäle: {active}/{all}\n"
            "📊 Ø Relevanz: {avg}/10\n"
            "📅 Diese Woche: {this_week}\n"
        ),
        "run_starting": "🔄 Starte Kanalprüfung...",
        "run_processed": "✅ {count} neue Videos verarbeitet.",
        "run_nothing": "✅ Keine neuen Videos gefunden.",
        "pending_queue_empty": "📭 Bestätigungswarteschlange ist leer.",
        "pending_queue_header": "⏳ In der Warteschlange: {count} (zeige die letzten 10)",
        "reject_reason_low_relevance": "niedrige Relevanz",
        "reject_reason_manual": "manuell",
        "rejected_empty": (
            "📭 Ablehnungsprotokoll ist leer.\n"
            "Nichts wurde automatisch abgelehnt — entweder ist die "
            "Relevanzschwelle mild genug, oder es sind noch keine neuen "
            "Videos eingetroffen."
        ),
        "rejected_header": "❌ Letzte {count} abgelehnte:\n",
        "processing_video": "⏳ Video wird verarbeitet...",
        "processing_unknown_error": "⚠️ Unbekannter Fehler aufgetreten.",
        "processing_article": "⏳ Artikel wird gelesen...",
        "channel_add_pick_category": (
            "📡 Kanal: {name}\n"
            "Zur Überwachung hinzufügen?\n\n"
            "Wähle eine Kategorie:"
        ),
        "qa_searching": "🔍 Durchsuche Wissensdatenbank...",
        "qa_nothing": (
            "🤷 Zu diesem Thema wurde noch nichts gesammelt.\n"
            "Versuche die Anfrage zu präzisieren oder sende mir einen "
            "Link zu diesem Thema."
        ),
        "qa_failed": "⚠️ Antwort konnte nicht erstellt werden. Versuche es später.",
        "qa_answer_header": "🧠 Basierend auf {count} Quellen:",
        "qa_sources_header": "📚 Quellen:",
        "new_cat_invalid_slug": (
            "⚠️ Ungültiger Slug. Verwende ASCII-Buchstaben, Ziffern und "
            "Bindestriche (max. 30 Zeichen)."
        ),
        "new_cat_created_lost": (
            "✅ Kategorie `{slug}` erstellt, aber Kanaldaten verloren. "
            "Versuche /add erneut."
        ),
        "new_cat_created_channel_added": (
            "✅ Kategorie `{slug}` erstellt.\n"
            "✅ Kanal {name} hinzugefügt.\n\n"
            "Die letzten 3 Videos abrufen?"
        ),
        "new_cat_created_no_record": (
            "✅ Kategorie `{slug}` erstellt, aber der Eintrag ist nicht "
            "mehr in der Warteschlange."
        ),
        "new_cat_prompt": (
            "✏️ Gib den Slug der neuen Kategorie ein "
            "(z.B. `machine-learning`).\n"
            "Optional nach einem Leerzeichen eine Beschreibung anhängen:"
        ),
        "new_cat_btn_yes": "✅ Ja",
        "new_cat_btn_no": "❌ Nein",
        "channel_data_lost": "⚠️ Kanaldaten verloren, bitte erneut versuchen.",
        "channel_added_fetch_prompt": (
            "✅ Kanal {name} zur Kategorie {category} hinzugefügt.\n\n"
            "Die letzten 3 Videos abrufen?"
        ),
        "fetch_starting": "⏳ Aktuelle Videos werden abgerufen...",
        "fetch_processed": "✅ {done} von {total} Videos verarbeitet.",
        "fetch_skipped": "👌 OK, Videos werden nicht abgerufen.",
        "error_notify_body": "⚠️ Fehler bei der Verarbeitung:\n{title}\n{error}",

        # ── Phase 7.3b ──
        "pipeline_err_video_id_extract": "Video-ID konnte nicht aus dem Link extrahiert werden.",
        "pipeline_err_video_already_processed": "Dieses Video wurde bereits verarbeitet.",
        "pipeline_err_transcript_unavailable": "Transkript nicht verfügbar für: {title}",
        "pipeline_err_article_already_processed": "Dieser Artikel wurde bereits verarbeitet.",
        "pipeline_err_web_extract_failed": (
            "Inhalt konnte nicht von dieser Seite extrahiert werden.\n"
            "Die Seite benötigt möglicherweise JavaScript oder blockiert das Scraping."
        ),
        "pipeline_err_unknown_source_type": "Unbekannter Inhaltstyp: {source_type}",
        "pipeline_err_summarize_failed": "Zusammenfassung konnte nicht erstellt werden für: {title}",

        # ── Phase 7.9 / Phase 8 ──
        "get_usage": (
            "Verwendung:\n"
            "• /get — nach Kategorie durchsuchen\n"
            "• /get <entry_id> — Eintrag direkt per 8-stelliger ID öffnen"
        ),
        "get_not_found": (
            "⚠️ Eintrag `{entry_id}` nicht gefunden. Nutze /recent oder "
            "/search für aktuelle IDs."
        ),
        "get_read_failed": "⚠️ Konnte die Eintragsdatei nicht von der Festplatte lesen.",
        "recent_get_hint": "💡 /get — nach Kategorie durchsuchen",
        "get_pick_category": "📂 Kategorie zum Durchsuchen wählen:",
        "get_pick_entry": "📁 {category} — {count} Einträge. Wähle einen:",
        "get_empty_base": "📭 Wissensbasis ist leer. Schick mir zuerst einen Link.",
        "get_category_empty": "📭 Noch keine Einträge in dieser Kategorie.",
        "entry_btn_md_file": "📄 Zusammenfassung (.md)",
        "entry_btn_raw_file": "📜 Vollständige Quelle",
        "entry_no_raw_text": "Keine Rohtext-Datei für diesen Eintrag.",
        "entry_file_caption": "📎 {name}",
    },
    "fr": {
        "welcome_returning": (
            "👋 PulseBrain est prêt.\n\n"
            "Envoie-moi un lien vers une vidéo YouTube, un article ou une "
            "chaîne — je le traiterai et le sauvegarderai dans la base de "
            "connaissances.\n\n"
            "Utilise /help pour la liste des commandes."
        ),
        "welcome_first_run": (
            "👋 Salut ! Je suis PulseBrain — ton agrégateur de "
            "connaissances personnel.\n\n"
            "Tu sauvegardes plein de choses « pour plus tard » et tu n'y "
            "reviens jamais. Je règle ça :\n"
            "• 📎 Envoie-moi un lien YouTube ou un article — je le résume "
            "et je le classe par catégorie.\n"
            "• 📡 Abonne-moi à des chaînes YouTube — je les surveille et te "
            "soumets les nouvelles vidéos pour validation.\n"
            "• 💬 Pose-moi des questions en texte libre — je cherche dans "
            "ta base et réponds avec les sources citées.\n"
            "• 📂 Tout reste à toi — de simples fichiers markdown, pas de "
            "lock-in cloud.\n\n"
            "Prenons 3 minutes pour configurer ton profil, que je puisse "
            "évaluer la pertinence pour TOI. /cancel pour arrêter."
        ),
        "help_text": (
            "📖 Commandes :\n\n"
            "/add <url> [category] — Ajouter une chaîne YouTube à surveiller\n"
            "/remove <name> — Désactiver une chaîne\n"
            "/list — Toutes les chaînes surveillées\n"
            "/categories — Catégories avec nombre d'entrées\n"
            "/search <requête> — Rechercher dans la base de connaissances\n"
            "/recent [N] — Les N dernières entrées (défaut 5)\n"
            "/pending — Entrées en attente d'approbation\n"
            "/rejected [N] — Vidéos récemment auto-rejetées\n"
            "/get <id> — Texte complet + télécharger .md/raw\n"
            "/status — État du bot\n"
            "/run — Forcer une vérification des chaînes\n"
            "/stats — Statistiques détaillées\n"
            "/language — Changer la langue de l'interface\n"
            "/onboarding — Relancer l'assistant de configuration\n"
            "/cancel — Annuler le dialogue en cours\n"
            "/help — Cette aide\n\n"
            "Ou envoie simplement un lien — le bot identifiera le type.\n"
            "Ou pose une question en texte brut — le bot répondra depuis "
            "la base."
        ),
        "language_menu_prompt": "Choisis ta langue d'interface :",
        "language_changed": "Langue changée pour : {name}",
        "wizard_lang_prompt": "D'abord — choisis ta langue d'interface :",
        "wizard_start_button": "▶️ Démarrer",
        "wizard_skip_button": "⏭ Passer",
        "wizard_done_button": "✅ Terminé",
        "wizard_welcome_body": (
            "Je vais te guider à travers quelques questions :\n\n"
            "1. Qui tu es et ce que tu fais\n"
            "2. Ce que tu apprends en ce moment\n"
            "3. Les outils que tu utilises au quotidien\n"
            "4. Ce que tu ne veux absolument pas voir\n"
            "5. Catégories et chaînes de départ\n\n"
            "Tape /cancel pour abandonner à tout moment."
        ),
        "wizard_persona_prompt": (
            "Quelques phrases sur toi : profession, ce que tu fais, niveau "
            "d'expérience."
        ),
        "wizard_learning_prompt": (
            "Qu'apprends-tu activement en ce moment ? Un sujet par ligne.\n"
            "Par exemple :\n"
            "Agents IA\n"
            "RAG et bases vectorielles\n"
            "Optimisation des coûts LLM"
        ),
        "wizard_stack_prompt": (
            "Quels outils maîtrises-tu déjà ? Un par ligne."
        ),
        "wizard_notinterested_prompt": (
            "Que ne veux-tu absolument pas voir ? Par exemple : crypto, "
            "ventes entreprise, développement mobile. Optionnel — tu peux "
            "passer."
        ),
        "wizard_categories_prompt": (
            "Catégories de départ. Coche celles que tu veux — les autres "
            "ne seront pas créées.\nAppuie sur Terminé quand c'est bon."
        ),
        "wizard_channels_prompt": (
            "Chaînes de départ. Choisis celles à suivre maintenant — "
            "d'autres peuvent être ajoutées plus tard via /add."
        ),
        "wizard_channels_empty": (
            "Pas encore de chaînes préréglées. Tu peux les ajouter plus "
            "tard via /add."
        ),
        "wizard_done": (
            "✅ C'est prêt !\n\n"
            "Je vérifierai les chaînes toutes les heures et filtrerai "
            "selon ton profil. Référence rapide :\n\n"
            "• Envoie une URL — je la traiterai\n"
            "• /pending — file d'approbation\n"
            "• /rejected — ce qui a été auto-rejeté\n"
            "• /language — changer de langue\n"
            "• /help — tout le reste"
        ),
        "cancel_confirmed": "❌ Annulé. État effacé.",
        "cancel_nothing_to_cancel": "👌 Rien à annuler.",
        "round_digest_body": (
            "🔄 Tour terminé\n\n"
            "Chaînes vérifiées : {channels}\n"
            "Nouveau dans /pending : {processed}\n"
            "Auto-rejeté : {rejected}\n"
            "Erreurs : {failed}\n\n"
            "Suivant dans {interval} min"
        ),
        "wizard_lang_saved": "✅ Langue enregistrée.",
        "onboarding_confirm_rerun": (
            "⚠️ Profil déjà configuré. Relancer l'onboarding ?\n"
            "Le profil actuel sera écrasé, mais les catégories et chaînes "
            "resteront."
        ),
        "onboarding_rerun_yes": "🔁 Oui, refaire",
        "onboarding_rerun_no": "🛑 Non, garder tel quel",
        "onboarding_kept_existing": "👌 Conservé tel quel.",

        # ── Phase 7.3a ──
        "pending_summary_label": "Résumé",
        "pending_category_label": "Catégorie",
        "pending_new_cat_marker": " 🆕 (nouveau !)",
        "pending_relevance_label": "Pertinence",
        "pending_awaiting_label": "⏳ En attente d'approbation",
        "pending_btn_save": "✅ Enregistrer",
        "pending_btn_reject": "❌ Rejeter",
        "pending_btn_category": "🔄 Catégorie",
        "pending_btn_new_category": "➕ Nouvelle catégorie",
        "pending_saved_suffix": "\n\n✅ Enregistré : {path}",
        "pending_rejected_suffix": "\n\n❌ Rejeté",
        "pending_record_gone": "⚠️ Entrée plus dans la file.",
        "pending_save_failed": "⚠️ Échec de l'enregistrement.",
        "list_empty": "📡 Aucune chaîne surveillée.",
        "list_header": "📡 Chaînes surveillées :\n",
        "add_usage": "Utilisation : /add <youtube_url> [category]",
        "add_resolving": "⏳ Résolution de la chaîne...",
        "add_resolve_failed": "⚠️ Impossible d'identifier la chaîne depuis ce lien.",
        "add_already_tracked": "La chaîne {name} est déjà suivie.",
        "add_added_to_category": "✅ Chaîne {name} ajoutée à la catégorie {category}.",
        "add_pick_category": "📡 Chaîne : {name}\nChoisis une catégorie :",
        "remove_usage": "Utilisation : /remove <channel_name>",
        "remove_disabled": "⏸ Chaîne {name} désactivée.",
        "remove_not_found": "Chaîne '{name}' introuvable.",
        "categories_empty": "📂 Pas encore d'entrées.",
        "categories_header": "📂 Catégories :\n",
        "categories_stale_marker": " (obsolète)",
        "categories_entry_count": "{count} entrées",
        "categories_item_line": "    ⭐ moy {avg}   📅 dernière : {last}",
        "search_usage": "Utilisation : /search <requête>",
        "search_nothing": "🔍 Rien trouvé pour \"{query}\".",
        "search_found_header": "🔍 {count} résultats pour \"{query}\" :\n",
        "recent_empty": "📋 Pas encore d'entrées.",
        "recent_header": "📋 {count} dernières entrées :\n",
        "status_body": (
            "📁 Entrées : {total}\n"
            "📺 Vidéos : {videos}\n"
            "📰 Articles : {articles}\n"
            "📡 Chaînes : {active}/{all}\n"
            "📊 Pertinence moy : {avg}/10\n"
            "📅 Cette semaine : {this_week}\n"
        ),
        "run_starting": "🔄 Lancement de la vérification des chaînes...",
        "run_processed": "✅ {count} nouvelles vidéos traitées.",
        "run_nothing": "✅ Aucune nouvelle vidéo trouvée.",
        "pending_queue_empty": "📭 File d'approbation vide.",
        "pending_queue_header": "⏳ En file : {count} (10 dernières affichées)",
        "reject_reason_low_relevance": "pertinence faible",
        "reject_reason_manual": "manuel",
        "rejected_empty": (
            "📭 Journal des rejets vide.\n"
            "Rien n'a été auto-rejeté — soit le seuil de pertinence est "
            "assez souple, soit aucune nouvelle vidéo n'est encore arrivée."
        ),
        "rejected_header": "❌ {count} derniers rejets :\n",
        "processing_video": "⏳ Traitement de la vidéo...",
        "processing_unknown_error": "⚠️ Erreur inconnue.",
        "processing_article": "⏳ Lecture de l'article...",
        "channel_add_pick_category": (
            "📡 Chaîne : {name}\n"
            "Ajouter à la surveillance ?\n\n"
            "Choisis une catégorie :"
        ),
        "qa_searching": "🔍 Recherche dans la base...",
        "qa_nothing": (
            "🤷 Rien de collecté sur ce sujet pour l'instant.\n"
            "Essaie de préciser la requête ou envoie-moi un lien."
        ),
        "qa_failed": "⚠️ Impossible de produire une réponse. Réessaie plus tard.",
        "qa_answer_header": "🧠 D'après {count} sources :",
        "qa_sources_header": "📚 Sources :",
        "new_cat_invalid_slug": (
            "⚠️ Slug invalide. Utilise des lettres ASCII, des chiffres "
            "et des tirets (max 30 caractères)."
        ),
        "new_cat_created_lost": (
            "✅ Catégorie `{slug}` créée, mais les données de la chaîne "
            "sont perdues. Réessaie /add."
        ),
        "new_cat_created_channel_added": (
            "✅ Catégorie `{slug}` créée.\n"
            "✅ Chaîne {name} ajoutée.\n\n"
            "Récupérer les 3 dernières vidéos ?"
        ),
        "new_cat_created_no_record": (
            "✅ Catégorie `{slug}` créée, mais l'entrée n'est plus dans "
            "la file."
        ),
        "new_cat_prompt": (
            "✏️ Entre le slug de la nouvelle catégorie "
            "(ex. `machine-learning`).\n"
            "Tu peux ajouter une description après un espace :"
        ),
        "new_cat_btn_yes": "✅ Oui",
        "new_cat_btn_no": "❌ Non",
        "channel_data_lost": "⚠️ Données de la chaîne perdues, réessaie.",
        "channel_added_fetch_prompt": (
            "✅ Chaîne {name} ajoutée à la catégorie {category}.\n\n"
            "Récupérer les 3 dernières vidéos ?"
        ),
        "fetch_starting": "⏳ Récupération des dernières vidéos...",
        "fetch_processed": "✅ {done} sur {total} vidéos traitées.",
        "fetch_skipped": "👌 OK, les vidéos ne seront pas récupérées.",
        "error_notify_body": "⚠️ Erreur lors du traitement :\n{title}\n{error}",

        # ── Phase 7.3b ──
        "pipeline_err_video_id_extract": "Impossible d'extraire l'ID vidéo depuis le lien.",
        "pipeline_err_video_already_processed": "Cette vidéo a déjà été traitée.",
        "pipeline_err_transcript_unavailable": "Transcription indisponible pour : {title}",
        "pipeline_err_article_already_processed": "Cet article a déjà été traité.",
        "pipeline_err_web_extract_failed": (
            "Impossible d'extraire le contenu de cette page.\n"
            "Le site peut nécessiter JavaScript ou bloquer le scraping."
        ),
        "pipeline_err_unknown_source_type": "Type de contenu inconnu : {source_type}",
        "pipeline_err_summarize_failed": "Impossible de produire un résumé pour : {title}",

        # ── Phase 7.9 / Phase 8 ──
        "get_usage": (
            "Utilisation :\n"
            "• /get — parcourir par catégorie\n"
            "• /get <entry_id> — ouvrir une entrée par son ID à 8 caractères"
        ),
        "get_not_found": (
            "⚠️ Entrée `{entry_id}` introuvable. Lance /recent ou "
            "/search pour voir les IDs actuels."
        ),
        "get_read_failed": "⚠️ Impossible de lire le fichier depuis le disque.",
        "recent_get_hint": "💡 /get — parcourir par catégorie",
        "get_pick_category": "📂 Choisis une catégorie à parcourir :",
        "get_pick_entry": "📁 {category} — {count} entrées. Choisis :",
        "get_empty_base": "📭 Base de connaissances vide. Envoie-moi d'abord un lien.",
        "get_category_empty": "📭 Aucune entrée dans cette catégorie pour l'instant.",
        "entry_btn_md_file": "📄 Résumé (.md)",
        "entry_btn_raw_file": "📜 Source complète",
        "entry_no_raw_text": "Pas de fichier texte brut pour cette entrée.",
        "entry_file_caption": "📎 {name}",
    },
    "es": {
        "welcome_returning": (
            "👋 PulseBrain listo.\n\n"
            "Envíame un enlace a un vídeo de YouTube, artículo o canal — "
            "lo procesaré y guardaré en la base de conocimiento.\n\n"
            "Usa /help para la lista de comandos."
        ),
        "welcome_first_run": (
            "👋 ¡Hola! Soy PulseBrain — tu agregador personal de "
            "conocimiento.\n\n"
            "Guardas un montón de cosas «para después» y nunca vuelves a "
            "ellas. Yo arreglo eso:\n"
            "• 📎 Envíame un enlace de YouTube o un artículo — lo resumo y "
            "lo archivo por categoría.\n"
            "• 📡 Suscríbeme a canales de YouTube — los vigilo y te pongo "
            "los videos nuevos para revisar.\n"
            "• 💬 Pregúntame en texto libre — busco en tu base y respondo "
            "citando las fuentes.\n"
            "• 📂 Todo queda tuyo — archivos markdown simples, sin lock-in "
            "en la nube.\n\n"
            "Tres minutos configurando tu perfil para que yo mida la "
            "relevancia según TÚ. /cancel para salir."
        ),
        "help_text": (
            "📖 Comandos:\n\n"
            "/add <url> [category] — Añadir canal de YouTube a la monitorización\n"
            "/remove <name> — Desactivar un canal\n"
            "/list — Todos los canales monitorizados\n"
            "/categories — Categorías con conteo de entradas\n"
            "/search <consulta> — Buscar en la base de conocimiento\n"
            "/recent [N] — Últimas N entradas (por defecto 5)\n"
            "/pending — Entradas pendientes de aprobación\n"
            "/rejected [N] — Vídeos auto-rechazados recientemente\n"
            "/get <id> — Texto completo + descargar .md/raw\n"
            "/status — Estado del bot\n"
            "/run — Forzar comprobación de canales\n"
            "/stats — Estadísticas detalladas\n"
            "/language — Cambiar idioma de interfaz\n"
            "/onboarding — Reiniciar el asistente de configuración\n"
            "/cancel — Cancelar diálogo actual\n"
            "/help — Esta ayuda\n\n"
            "O simplemente envía un enlace — el bot detectará el tipo.\n"
            "O haz una pregunta en texto plano — el bot responderá desde "
            "la base."
        ),
        "language_menu_prompt": "Elige tu idioma de interfaz:",
        "language_changed": "Idioma cambiado a: {name}",
        "wizard_lang_prompt": "Primero — elige tu idioma de interfaz:",
        "wizard_start_button": "▶️ Empezar",
        "wizard_skip_button": "⏭ Saltar",
        "wizard_done_button": "✅ Listo",
        "wizard_welcome_body": (
            "Te voy a guiar a través de algunas preguntas:\n\n"
            "1. Quién eres y a qué te dedicas\n"
            "2. Qué estás aprendiendo ahora\n"
            "3. Qué herramientas usas a diario\n"
            "4. Qué definitivamente no quieres ver\n"
            "5. Categorías y canales iniciales\n\n"
            "Escribe /cancel para abandonar en cualquier momento."
        ),
        "wizard_persona_prompt": (
            "Un par de frases sobre ti: profesión, a qué te dedicas, "
            "nivel de experiencia."
        ),
        "wizard_learning_prompt": (
            "¿Qué estás aprendiendo activamente ahora? Un tema por línea.\n"
            "Por ejemplo:\n"
            "Agentes IA\n"
            "RAG y bases vectoriales\n"
            "Optimización de costes de LLM"
        ),
        "wizard_stack_prompt": (
            "¿Qué herramientas ya manejas con soltura? Una por línea."
        ),
        "wizard_notinterested_prompt": (
            "¿Qué definitivamente no quieres ver? Por ejemplo: cripto, "
            "ventas empresariales, desarrollo móvil. Opcional — puedes "
            "saltarlo."
        ),
        "wizard_categories_prompt": (
            "Categorías iniciales. Marca las que quieras — el resto no "
            "se creará.\nPulsa Listo cuando hayas terminado."
        ),
        "wizard_channels_prompt": (
            "Canales iniciales. Elige cuáles suscribir ahora — otros se "
            "pueden añadir después con /add."
        ),
        "wizard_channels_empty": (
            "Aún no hay canales preestablecidos. Puedes añadirlos después "
            "con /add."
        ),
        "wizard_done": (
            "✅ ¡Todo listo!\n\n"
            "Comprobaré los canales cada hora y filtraré según tu perfil. "
            "Referencia rápida:\n\n"
            "• Envía una URL — la procesaré\n"
            "• /pending — cola de aprobación\n"
            "• /rejected — lo que fue auto-rechazado\n"
            "• /language — cambiar idioma\n"
            "• /help — todo lo demás"
        ),
        "cancel_confirmed": "❌ Cancelado. Estado borrado.",
        "cancel_nothing_to_cancel": "👌 Nada que cancelar.",
        "round_digest_body": (
            "🔄 Ronda completada\n\n"
            "Canales comprobados: {channels}\n"
            "Nuevos en /pending: {processed}\n"
            "Auto-rechazados: {rejected}\n"
            "Errores: {failed}\n\n"
            "Siguiente en {interval} min"
        ),
        "wizard_lang_saved": "✅ Idioma guardado.",
        "onboarding_confirm_rerun": (
            "⚠️ Perfil ya configurado. ¿Reiniciar el onboarding?\n"
            "El perfil actual se sobrescribirá, pero las categorías y "
            "canales permanecerán."
        ),
        "onboarding_rerun_yes": "🔁 Sí, rehacer",
        "onboarding_rerun_no": "🛑 No, dejarlo así",
        "onboarding_kept_existing": "👌 Lo dejé como está.",

        # ── Phase 7.3a ──
        "pending_summary_label": "Resumen",
        "pending_category_label": "Categoría",
        "pending_new_cat_marker": " 🆕 (¡nueva!)",
        "pending_relevance_label": "Relevancia",
        "pending_awaiting_label": "⏳ Esperando aprobación",
        "pending_btn_save": "✅ Guardar",
        "pending_btn_reject": "❌ Rechazar",
        "pending_btn_category": "🔄 Categoría",
        "pending_btn_new_category": "➕ Nueva categoría",
        "pending_saved_suffix": "\n\n✅ Guardado: {path}",
        "pending_rejected_suffix": "\n\n❌ Rechazado",
        "pending_record_gone": "⚠️ La entrada ya no está en la cola.",
        "pending_save_failed": "⚠️ No se pudo guardar la entrada.",
        "list_empty": "📡 Sin canales monitorizados.",
        "list_header": "📡 Canales monitorizados:\n",
        "add_usage": "Uso: /add <youtube_url> [category]",
        "add_resolving": "⏳ Resolviendo canal...",
        "add_resolve_failed": "⚠️ No se pudo identificar el canal desde ese enlace.",
        "add_already_tracked": "El canal {name} ya está siendo monitorizado.",
        "add_added_to_category": "✅ Canal {name} añadido a la categoría {category}.",
        "add_pick_category": "📡 Canal: {name}\nElige una categoría:",
        "remove_usage": "Uso: /remove <channel_name>",
        "remove_disabled": "⏸ Canal {name} desactivado.",
        "remove_not_found": "Canal '{name}' no encontrado.",
        "categories_empty": "📂 Aún no hay entradas.",
        "categories_header": "📂 Categorías:\n",
        "categories_stale_marker": " (inactiva)",
        "categories_entry_count": "{count} entradas",
        "categories_item_line": "    ⭐ media {avg}   📅 última: {last}",
        "search_usage": "Uso: /search <consulta>",
        "search_nothing": "🔍 Nada encontrado para \"{query}\".",
        "search_found_header": "🔍 Encontrados {count} resultados para \"{query}\":\n",
        "recent_empty": "📋 Aún no hay entradas.",
        "recent_header": "📋 Últimas {count} entradas:\n",
        "status_body": (
            "📁 Entradas: {total}\n"
            "📺 Vídeos: {videos}\n"
            "📰 Artículos: {articles}\n"
            "📡 Canales: {active}/{all}\n"
            "📊 Relevancia media: {avg}/10\n"
            "📅 Esta semana: {this_week}\n"
        ),
        "run_starting": "🔄 Comprobando canales...",
        "run_processed": "✅ Procesados {count} vídeos nuevos.",
        "run_nothing": "✅ No se encontraron vídeos nuevos.",
        "pending_queue_empty": "📭 La cola de aprobación está vacía.",
        "pending_queue_header": "⏳ En cola: {count} (mostrando las últimas 10)",
        "reject_reason_low_relevance": "relevancia baja",
        "reject_reason_manual": "manual",
        "rejected_empty": (
            "📭 Registro de rechazados vacío.\n"
            "Nada fue auto-rechazado — el umbral de relevancia es "
            "suficientemente suave o aún no han llegado vídeos nuevos."
        ),
        "rejected_header": "❌ Últimos {count} rechazados:\n",
        "processing_video": "⏳ Procesando vídeo...",
        "processing_unknown_error": "⚠️ Ocurrió un error desconocido.",
        "processing_article": "⏳ Leyendo artículo...",
        "channel_add_pick_category": (
            "📡 Canal: {name}\n"
            "¿Añadir a la monitorización?\n\n"
            "Elige una categoría:"
        ),
        "qa_searching": "🔍 Buscando en la base de conocimiento...",
        "qa_nothing": (
            "🤷 Nada recopilado sobre este tema todavía.\n"
            "Prueba a afinar la consulta o envíame un enlace sobre el tema."
        ),
        "qa_failed": "⚠️ No se pudo generar una respuesta. Inténtalo luego.",
        "qa_answer_header": "🧠 Basado en {count} fuentes:",
        "qa_sources_header": "📚 Fuentes:",
        "new_cat_invalid_slug": (
            "⚠️ Slug inválido. Usa letras ASCII, dígitos y guiones "
            "(máx 30 caracteres)."
        ),
        "new_cat_created_lost": (
            "✅ Categoría `{slug}` creada, pero los datos del canal se "
            "perdieron. Intenta /add de nuevo."
        ),
        "new_cat_created_channel_added": (
            "✅ Categoría `{slug}` creada.\n"
            "✅ Canal {name} añadido.\n\n"
            "¿Obtener los últimos 3 vídeos?"
        ),
        "new_cat_created_no_record": (
            "✅ Categoría `{slug}` creada, pero la entrada ya no está "
            "en la cola."
        ),
        "new_cat_prompt": (
            "✏️ Introduce el slug de la nueva categoría "
            "(p. ej. `machine-learning`).\n"
            "Opcionalmente añade una descripción tras un espacio:"
        ),
        "new_cat_btn_yes": "✅ Sí",
        "new_cat_btn_no": "❌ No",
        "channel_data_lost": "⚠️ Datos del canal perdidos, inténtalo de nuevo.",
        "channel_added_fetch_prompt": (
            "✅ Canal {name} añadido a la categoría {category}.\n\n"
            "¿Obtener los últimos 3 vídeos?"
        ),
        "fetch_starting": "⏳ Obteniendo últimos vídeos...",
        "fetch_processed": "✅ Procesados {done} de {total} vídeos.",
        "fetch_skipped": "👌 Vale, los vídeos no se obtendrán.",
        "error_notify_body": "⚠️ Error al procesar:\n{title}\n{error}",

        # ── Phase 7.3b ──
        "pipeline_err_video_id_extract": "No se pudo extraer el ID del vídeo desde el enlace.",
        "pipeline_err_video_already_processed": "Este vídeo ya ha sido procesado.",
        "pipeline_err_transcript_unavailable": "Transcripción no disponible para: {title}",
        "pipeline_err_article_already_processed": "Este artículo ya ha sido procesado.",
        "pipeline_err_web_extract_failed": (
            "No se pudo extraer el contenido de esta página.\n"
            "El sitio puede requerir JavaScript o bloquear el scraping."
        ),
        "pipeline_err_unknown_source_type": "Tipo de contenido desconocido: {source_type}",
        "pipeline_err_summarize_failed": "No se pudo generar un resumen para: {title}",

        # ── Phase 7.9 / Phase 8 ──
        "get_usage": (
            "Uso:\n"
            "• /get — explorar por categoría\n"
            "• /get <entry_id> — abrir una entrada por su ID de 8 caracteres"
        ),
        "get_not_found": (
            "⚠️ Entrada `{entry_id}` no encontrada. Ejecuta /recent o "
            "/search para ver los IDs actuales."
        ),
        "get_read_failed": "⚠️ No se pudo leer el archivo de la entrada.",
        "recent_get_hint": "💡 /get — explorar por categoría",
        "get_pick_category": "📂 Elige una categoría para explorar:",
        "get_pick_entry": "📁 {category} — {count} entradas. Elige una:",
        "get_empty_base": "📭 La base de conocimientos está vacía. Envíame un enlace primero.",
        "get_category_empty": "📭 Aún no hay entradas en esta categoría.",
        "entry_btn_md_file": "📄 Resumen (.md)",
        "entry_btn_raw_file": "📜 Fuente completa",
        "entry_no_raw_text": "No hay archivo de texto en bruto para esta entrada.",
        "entry_file_caption": "📎 {name}",
    },
    "it": {
        "welcome_returning": (
            "👋 PulseBrain pronto.\n\n"
            "Inviami un link a un video YouTube, articolo o canale — lo "
            "elaborerò e lo salverò nella base di conoscenza.\n\n"
            "Usa /help per la lista dei comandi."
        ),
        "welcome_first_run": (
            "👋 Ciao! Sono PulseBrain — il tuo aggregatore personale di "
            "conoscenza.\n\n"
            "Salvi un sacco di cose «per dopo» e non ci torni mai. Io "
            "sistemo questo:\n"
            "• 📎 Mandami un link YouTube o un articolo — lo riassumo e "
            "lo archivio per categoria.\n"
            "• 📡 Iscrivimi a canali YouTube — li controllo e ti metto in "
            "coda i nuovi video per la revisione.\n"
            "• 💬 Fammi domande in testo libero — cerco nella tua base e "
            "rispondo citando le fonti.\n"
            "• 📂 Tutto rimane tuo — semplici file markdown, niente lock-in "
            "cloud.\n\n"
            "Tre minuti per configurare il profilo così posso valutare la "
            "rilevanza per TE. /cancel per uscire."
        ),
        "help_text": (
            "📖 Comandi:\n\n"
            "/add <url> [category] — Aggiungi un canale YouTube al monitoraggio\n"
            "/remove <name> — Disabilita un canale\n"
            "/list — Tutti i canali monitorati\n"
            "/categories — Categorie con conteggio voci\n"
            "/search <query> — Cerca nella base di conoscenza\n"
            "/recent [N] — Ultime N voci (default 5)\n"
            "/pending — Voci in attesa di approvazione\n"
            "/rejected [N] — Video auto-rifiutati di recente\n"
            "/get <id> — Testo completo + scarica .md/raw\n"
            "/status — Stato del bot\n"
            "/run — Forza un controllo canali\n"
            "/stats — Statistiche dettagliate\n"
            "/language — Cambia lingua dell'interfaccia\n"
            "/onboarding — Riavvia la procedura guidata\n"
            "/cancel — Annulla dialogo corrente\n"
            "/help — Questa guida\n\n"
            "Oppure invia semplicemente un link — il bot riconoscerà il "
            "tipo.\nOppure fai una domanda in testo semplice — il bot "
            "risponderà dalla base."
        ),
        "language_menu_prompt": "Scegli la lingua dell'interfaccia:",
        "language_changed": "Lingua cambiata in: {name}",
        "wizard_lang_prompt": "Prima — scegli la lingua dell'interfaccia:",
        "wizard_start_button": "▶️ Inizia",
        "wizard_skip_button": "⏭ Salta",
        "wizard_done_button": "✅ Fatto",
        "wizard_welcome_body": (
            "Ti guiderò attraverso alcune domande:\n\n"
            "1. Chi sei e cosa fai\n"
            "2. Cosa stai imparando in questo momento\n"
            "3. Quali strumenti usi ogni giorno\n"
            "4. Cosa non vuoi assolutamente vedere\n"
            "5. Categorie e canali iniziali\n\n"
            "Scrivi /cancel per interrompere in qualsiasi momento."
        ),
        "wizard_persona_prompt": (
            "Un paio di frasi su di te: professione, cosa fai, livello di "
            "esperienza."
        ),
        "wizard_learning_prompt": (
            "Cosa stai imparando attivamente ora? Un argomento per riga.\n"
            "Ad esempio:\n"
            "Agenti IA\n"
            "RAG e database vettoriali\n"
            "Ottimizzazione costi LLM"
        ),
        "wizard_stack_prompt": (
            "Quali strumenti usi già con sicurezza? Uno per riga."
        ),
        "wizard_notinterested_prompt": (
            "Cosa non vuoi assolutamente vedere? Ad esempio: crypto, "
            "vendite enterprise, sviluppo mobile. Opzionale — puoi saltare."
        ),
        "wizard_categories_prompt": (
            "Categorie iniziali. Spunta quelle che vuoi — le altre non "
            "verranno create.\nTocca Fatto quando hai finito."
        ),
        "wizard_channels_prompt": (
            "Canali iniziali. Scegli a quali iscriverti ora — altri "
            "possono essere aggiunti più tardi con /add."
        ),
        "wizard_channels_empty": (
            "Nessun canale preimpostato ancora. Puoi aggiungerli più tardi "
            "con /add."
        ),
        "wizard_done": (
            "✅ Tutto pronto!\n\n"
            "Controllerò i canali ogni ora e filtrerò in base al tuo "
            "profilo. Riferimento rapido:\n\n"
            "• Invia un URL — lo elaborerò\n"
            "• /pending — coda di approvazione\n"
            "• /rejected — cosa è stato auto-rifiutato\n"
            "• /language — cambia lingua\n"
            "• /help — tutto il resto"
        ),
        "cancel_confirmed": "❌ Annullato. Stato cancellato.",
        "cancel_nothing_to_cancel": "👌 Niente da annullare.",
        "round_digest_body": (
            "🔄 Turno completato\n\n"
            "Canali controllati: {channels}\n"
            "Nuovi in /pending: {processed}\n"
            "Auto-rifiutati: {rejected}\n"
            "Errori: {failed}\n\n"
            "Prossimo tra {interval} min"
        ),
        "wizard_lang_saved": "✅ Lingua salvata.",
        "onboarding_confirm_rerun": (
            "⚠️ Profilo già configurato. Riavviare l'onboarding?\n"
            "Il profilo corrente verrà sovrascritto, ma categorie e canali "
            "rimarranno."
        ),
        "onboarding_rerun_yes": "🔁 Sì, rifare",
        "onboarding_rerun_no": "🛑 No, lasciare così",
        "onboarding_kept_existing": "👌 Lasciato così com'è.",

        # ── Phase 7.3a ──
        "pending_summary_label": "Riepilogo",
        "pending_category_label": "Categoria",
        "pending_new_cat_marker": " 🆕 (nuova!)",
        "pending_relevance_label": "Rilevanza",
        "pending_awaiting_label": "⏳ In attesa di approvazione",
        "pending_btn_save": "✅ Salva",
        "pending_btn_reject": "❌ Rifiuta",
        "pending_btn_category": "🔄 Categoria",
        "pending_btn_new_category": "➕ Nuova categoria",
        "pending_saved_suffix": "\n\n✅ Salvato: {path}",
        "pending_rejected_suffix": "\n\n❌ Rifiutato",
        "pending_record_gone": "⚠️ Voce non più in coda.",
        "pending_save_failed": "⚠️ Salvataggio fallito.",
        "list_empty": "📡 Nessun canale monitorato.",
        "list_header": "📡 Canali monitorati:\n",
        "add_usage": "Uso: /add <youtube_url> [category]",
        "add_resolving": "⏳ Risolvo il canale...",
        "add_resolve_failed": "⚠️ Impossibile identificare il canale da quel link.",
        "add_already_tracked": "Il canale {name} è già monitorato.",
        "add_added_to_category": "✅ Canale {name} aggiunto alla categoria {category}.",
        "add_pick_category": "📡 Canale: {name}\nScegli una categoria:",
        "remove_usage": "Uso: /remove <channel_name>",
        "remove_disabled": "⏸ Canale {name} disabilitato.",
        "remove_not_found": "Canale '{name}' non trovato.",
        "categories_empty": "📂 Nessuna voce ancora.",
        "categories_header": "📂 Categorie:\n",
        "categories_stale_marker": " (obsoleta)",
        "categories_entry_count": "{count} voci",
        "categories_item_line": "    ⭐ media {avg}   📅 ultima: {last}",
        "search_usage": "Uso: /search <query>",
        "search_nothing": "🔍 Nulla trovato per \"{query}\".",
        "search_found_header": "🔍 Trovati {count} risultati per \"{query}\":\n",
        "recent_empty": "📋 Nessuna voce ancora.",
        "recent_header": "📋 Ultime {count} voci:\n",
        "status_body": (
            "📁 Voci: {total}\n"
            "📺 Video: {videos}\n"
            "📰 Articoli: {articles}\n"
            "📡 Canali: {active}/{all}\n"
            "📊 Rilevanza media: {avg}/10\n"
            "📅 Questa settimana: {this_week}\n"
        ),
        "run_starting": "🔄 Avvio controllo canali...",
        "run_processed": "✅ Elaborati {count} nuovi video.",
        "run_nothing": "✅ Nessun video nuovo trovato.",
        "pending_queue_empty": "📭 La coda di approvazione è vuota.",
        "pending_queue_header": "⏳ In coda: {count} (mostro le ultime 10)",
        "reject_reason_low_relevance": "bassa rilevanza",
        "reject_reason_manual": "manuale",
        "rejected_empty": (
            "📭 Registro dei rifiutati vuoto.\n"
            "Niente è stato auto-rifiutato — o la soglia di rilevanza è "
            "abbastanza morbida, o non sono ancora arrivati nuovi video."
        ),
        "rejected_header": "❌ Ultimi {count} rifiutati:\n",
        "processing_video": "⏳ Elaboro il video...",
        "processing_unknown_error": "⚠️ Errore sconosciuto.",
        "processing_article": "⏳ Leggo l'articolo...",
        "channel_add_pick_category": (
            "📡 Canale: {name}\n"
            "Aggiungere al monitoraggio?\n\n"
            "Scegli una categoria:"
        ),
        "qa_searching": "🔍 Cerco nella base di conoscenza...",
        "qa_nothing": (
            "🤷 Niente raccolto su questo argomento ancora.\n"
            "Prova a precisare la query o inviami un link sull'argomento."
        ),
        "qa_failed": "⚠️ Impossibile produrre una risposta. Riprova più tardi.",
        "qa_answer_header": "🧠 Basato su {count} fonti:",
        "qa_sources_header": "📚 Fonti:",
        "new_cat_invalid_slug": (
            "⚠️ Slug non valido. Usa lettere ASCII, cifre e trattini "
            "(max 30 caratteri)."
        ),
        "new_cat_created_lost": (
            "✅ Categoria `{slug}` creata, ma i dati del canale sono "
            "andati persi. Riprova /add."
        ),
        "new_cat_created_channel_added": (
            "✅ Categoria `{slug}` creata.\n"
            "✅ Canale {name} aggiunto.\n\n"
            "Recuperare gli ultimi 3 video?"
        ),
        "new_cat_created_no_record": (
            "✅ Categoria `{slug}` creata, ma la voce non è più in coda."
        ),
        "new_cat_prompt": (
            "✏️ Inserisci lo slug della nuova categoria "
            "(es. `machine-learning`).\n"
            "Opzionalmente aggiungi una descrizione dopo uno spazio:"
        ),
        "new_cat_btn_yes": "✅ Sì",
        "new_cat_btn_no": "❌ No",
        "channel_data_lost": "⚠️ Dati del canale persi, riprova.",
        "channel_added_fetch_prompt": (
            "✅ Canale {name} aggiunto alla categoria {category}.\n\n"
            "Recuperare gli ultimi 3 video?"
        ),
        "fetch_starting": "⏳ Recupero gli ultimi video...",
        "fetch_processed": "✅ Elaborati {done} su {total} video.",
        "fetch_skipped": "👌 OK, i video non verranno recuperati.",
        "error_notify_body": "⚠️ Errore durante l'elaborazione:\n{title}\n{error}",

        # ── Phase 7.3b ──
        "pipeline_err_video_id_extract": "Impossibile estrarre l'ID del video dal link.",
        "pipeline_err_video_already_processed": "Questo video è già stato elaborato.",
        "pipeline_err_transcript_unavailable": "Trascrizione non disponibile per: {title}",
        "pipeline_err_article_already_processed": "Questo articolo è già stato elaborato.",
        "pipeline_err_web_extract_failed": (
            "Impossibile estrarre il contenuto da questa pagina.\n"
            "Il sito potrebbe richiedere JavaScript o bloccare lo scraping."
        ),
        "pipeline_err_unknown_source_type": "Tipo di contenuto sconosciuto: {source_type}",
        "pipeline_err_summarize_failed": "Impossibile produrre un riepilogo per: {title}",

        # ── Phase 7.9 / Phase 8 ──
        "get_usage": (
            "Uso:\n"
            "• /get — sfoglia per categoria\n"
            "• /get <entry_id> — apri una voce tramite ID di 8 caratteri"
        ),
        "get_not_found": (
            "⚠️ Voce `{entry_id}` non trovata. Esegui /recent o /search "
            "per vedere gli ID attuali."
        ),
        "get_read_failed": "⚠️ Impossibile leggere il file della voce.",
        "recent_get_hint": "💡 /get — sfoglia per categoria",
        "get_pick_category": "📂 Scegli una categoria da sfogliare:",
        "get_pick_entry": "📁 {category} — {count} voci. Scegline una:",
        "get_empty_base": "📭 La base di conoscenza è vuota. Mandami prima un link.",
        "get_category_empty": "📭 Nessuna voce in questa categoria al momento.",
        "entry_btn_md_file": "📄 Riassunto (.md)",
        "entry_btn_raw_file": "📜 Fonte completa",
        "entry_no_raw_text": "Nessun file di testo grezzo per questa voce.",
        "entry_file_caption": "📎 {name}",
    },
    "pt": {
        "welcome_returning": (
            "👋 PulseBrain pronto.\n\n"
            "Envie-me um link para um vídeo do YouTube, artigo ou canal — "
            "vou processá-lo e salvá-lo na base de conhecimento.\n\n"
            "Use /help para a lista de comandos."
        ),
        "welcome_first_run": (
            "👋 Olá! Sou o PulseBrain — seu agregador pessoal de "
            "conhecimento.\n\n"
            "Você salva um monte de coisas «para depois» e nunca volta. "
            "Eu resolvo isso:\n"
            "• 📎 Mande um link do YouTube ou artigo — eu resumo e arquivo "
            "por categoria.\n"
            "• 📡 Inscreva-me em canais do YouTube — eu monitoro e coloco "
            "vídeos novos na fila de revisão.\n"
            "• 💬 Pergunte em texto livre — busco na sua base e respondo "
            "citando as fontes.\n"
            "• 📂 Tudo continua seu — arquivos markdown simples, sem "
            "lock-in na nuvem.\n\n"
            "Três minutos para configurar o perfil para eu avaliar a "
            "relevância para VOCÊ. /cancel para sair."
        ),
        "help_text": (
            "📖 Comandos:\n\n"
            "/add <url> [category] — Adicionar canal do YouTube ao monitoramento\n"
            "/remove <name> — Desativar um canal\n"
            "/list — Todos os canais monitorados\n"
            "/categories — Categorias com contagem de entradas\n"
            "/search <consulta> — Buscar na base de conhecimento\n"
            "/recent [N] — Últimas N entradas (padrão 5)\n"
            "/pending — Entradas aguardando aprovação\n"
            "/rejected [N] — Vídeos recentemente auto-rejeitados\n"
            "/get <id> — Texto completo + baixar .md/raw\n"
            "/status — Status do bot\n"
            "/run — Forçar verificação de canais\n"
            "/stats — Estatísticas detalhadas\n"
            "/language — Mudar idioma da interface\n"
            "/onboarding — Reiniciar o assistente de configuração\n"
            "/cancel — Cancelar diálogo atual\n"
            "/help — Esta ajuda\n\n"
            "Ou simplesmente envie um link — o bot identificará o tipo.\n"
            "Ou faça uma pergunta em texto puro — o bot responderá da base."
        ),
        "language_menu_prompt": "Escolha seu idioma de interface:",
        "language_changed": "Idioma alterado para: {name}",
        "wizard_lang_prompt": "Primeiro — escolha seu idioma de interface:",
        "wizard_start_button": "▶️ Iniciar",
        "wizard_skip_button": "⏭ Pular",
        "wizard_done_button": "✅ Pronto",
        "wizard_welcome_body": (
            "Vou guiá-lo através de algumas perguntas:\n\n"
            "1. Quem você é e o que faz\n"
            "2. O que você está aprendendo agora\n"
            "3. Quais ferramentas você usa no dia a dia\n"
            "4. O que você definitivamente não quer ver\n"
            "5. Categorias e canais iniciais\n\n"
            "Digite /cancel para desistir a qualquer momento."
        ),
        "wizard_persona_prompt": (
            "Algumas frases sobre você: profissão, o que faz, nível de "
            "experiência."
        ),
        "wizard_learning_prompt": (
            "O que você está aprendendo ativamente agora? Um tópico por linha.\n"
            "Por exemplo:\n"
            "Agentes IA\n"
            "RAG e bancos vetoriais\n"
            "Otimização de custos de LLM"
        ),
        "wizard_stack_prompt": (
            "Quais ferramentas você já domina? Uma por linha."
        ),
        "wizard_notinterested_prompt": (
            "O que você definitivamente não quer ver? Por exemplo: cripto, "
            "vendas enterprise, desenvolvimento móvel. Opcional — pode pular."
        ),
        "wizard_categories_prompt": (
            "Categorias iniciais. Marque as que você quer — o resto não "
            "será criado.\nToque em Pronto quando terminar."
        ),
        "wizard_channels_prompt": (
            "Canais iniciais. Escolha quais inscrever agora — outros podem "
            "ser adicionados depois com /add."
        ),
        "wizard_channels_empty": (
            "Ainda não há canais predefinidos. Você pode adicioná-los "
            "depois com /add."
        ),
        "wizard_done": (
            "✅ Tudo pronto!\n\n"
            "Vou verificar os canais a cada hora e filtrar pelo seu perfil. "
            "Referência rápida:\n\n"
            "• Envie uma URL — vou processá-la\n"
            "• /pending — fila de aprovação\n"
            "• /rejected — o que foi auto-rejeitado\n"
            "• /language — mudar idioma\n"
            "• /help — todo o resto"
        ),
        "cancel_confirmed": "❌ Cancelado. Estado limpo.",
        "cancel_nothing_to_cancel": "👌 Nada para cancelar.",
        "round_digest_body": (
            "🔄 Rodada completa\n\n"
            "Canais verificados: {channels}\n"
            "Novos em /pending: {processed}\n"
            "Auto-rejeitados: {rejected}\n"
            "Erros: {failed}\n\n"
            "Próximo em {interval} min"
        ),
        "wizard_lang_saved": "✅ Idioma salvo.",
        "onboarding_confirm_rerun": (
            "⚠️ Perfil já configurado. Reiniciar o onboarding?\n"
            "O perfil atual será sobrescrito, mas categorias e canais "
            "permanecerão."
        ),
        "onboarding_rerun_yes": "🔁 Sim, refazer",
        "onboarding_rerun_no": "🛑 Não, deixar como está",
        "onboarding_kept_existing": "👌 Deixei como está.",

        # ── Phase 7.3a ──
        "pending_summary_label": "Resumo",
        "pending_category_label": "Categoria",
        "pending_new_cat_marker": " 🆕 (nova!)",
        "pending_relevance_label": "Relevância",
        "pending_awaiting_label": "⏳ Aguardando aprovação",
        "pending_btn_save": "✅ Salvar",
        "pending_btn_reject": "❌ Rejeitar",
        "pending_btn_category": "🔄 Categoria",
        "pending_btn_new_category": "➕ Nova categoria",
        "pending_saved_suffix": "\n\n✅ Salvo: {path}",
        "pending_rejected_suffix": "\n\n❌ Rejeitado",
        "pending_record_gone": "⚠️ Entrada não está mais na fila.",
        "pending_save_failed": "⚠️ Falha ao salvar entrada.",
        "list_empty": "📡 Nenhum canal monitorado.",
        "list_header": "📡 Canais monitorados:\n",
        "add_usage": "Uso: /add <youtube_url> [category]",
        "add_resolving": "⏳ Resolvendo canal...",
        "add_resolve_failed": "⚠️ Não consegui identificar o canal pelo link.",
        "add_already_tracked": "O canal {name} já está sendo monitorado.",
        "add_added_to_category": "✅ Canal {name} adicionado à categoria {category}.",
        "add_pick_category": "📡 Canal: {name}\nEscolha uma categoria:",
        "remove_usage": "Uso: /remove <channel_name>",
        "remove_disabled": "⏸ Canal {name} desativado.",
        "remove_not_found": "Canal '{name}' não encontrado.",
        "categories_empty": "📂 Nenhuma entrada ainda.",
        "categories_header": "📂 Categorias:\n",
        "categories_stale_marker": " (inativa)",
        "categories_entry_count": "{count} entradas",
        "categories_item_line": "    ⭐ média {avg}   📅 última: {last}",
        "search_usage": "Uso: /search <consulta>",
        "search_nothing": "🔍 Nada encontrado para \"{query}\".",
        "search_found_header": "🔍 Encontrados {count} resultados para \"{query}\":\n",
        "recent_empty": "📋 Nenhuma entrada ainda.",
        "recent_header": "📋 Últimas {count} entradas:\n",
        "status_body": (
            "📁 Entradas: {total}\n"
            "📺 Vídeos: {videos}\n"
            "📰 Artigos: {articles}\n"
            "📡 Canais: {active}/{all}\n"
            "📊 Relevância média: {avg}/10\n"
            "📅 Esta semana: {this_week}\n"
        ),
        "run_starting": "🔄 Executando verificação de canais...",
        "run_processed": "✅ Processados {count} vídeos novos.",
        "run_nothing": "✅ Nenhum vídeo novo encontrado.",
        "pending_queue_empty": "📭 Fila de aprovação vazia.",
        "pending_queue_header": "⏳ Na fila: {count} (mostrando as últimas 10)",
        "reject_reason_low_relevance": "relevância baixa",
        "reject_reason_manual": "manual",
        "rejected_empty": (
            "📭 Registro de rejeitados vazio.\n"
            "Nada foi auto-rejeitado — ou o limiar de relevância está "
            "suave o bastante, ou ainda não chegaram vídeos novos."
        ),
        "rejected_header": "❌ Últimos {count} rejeitados:\n",
        "processing_video": "⏳ Processando vídeo...",
        "processing_unknown_error": "⚠️ Erro desconhecido.",
        "processing_article": "⏳ Lendo artigo...",
        "channel_add_pick_category": (
            "📡 Canal: {name}\n"
            "Adicionar ao monitoramento?\n\n"
            "Escolha uma categoria:"
        ),
        "qa_searching": "🔍 Buscando na base de conhecimento...",
        "qa_nothing": (
            "🤷 Nada coletado sobre este tópico ainda.\n"
            "Tente refinar a consulta ou me envie um link sobre o tema."
        ),
        "qa_failed": "⚠️ Falha ao gerar resposta. Tente depois.",
        "qa_answer_header": "🧠 Baseado em {count} fontes:",
        "qa_sources_header": "📚 Fontes:",
        "new_cat_invalid_slug": (
            "⚠️ Slug inválido. Use letras ASCII, dígitos e hífens "
            "(máx 30 caracteres)."
        ),
        "new_cat_created_lost": (
            "✅ Categoria `{slug}` criada, mas os dados do canal foram "
            "perdidos. Tente /add novamente."
        ),
        "new_cat_created_channel_added": (
            "✅ Categoria `{slug}` criada.\n"
            "✅ Canal {name} adicionado.\n\n"
            "Buscar os últimos 3 vídeos?"
        ),
        "new_cat_created_no_record": (
            "✅ Categoria `{slug}` criada, mas a entrada não está mais "
            "na fila."
        ),
        "new_cat_prompt": (
            "✏️ Digite o slug da nova categoria "
            "(ex. `machine-learning`).\n"
            "Opcionalmente adicione uma descrição após um espaço:"
        ),
        "new_cat_btn_yes": "✅ Sim",
        "new_cat_btn_no": "❌ Não",
        "channel_data_lost": "⚠️ Dados do canal perdidos, tente novamente.",
        "channel_added_fetch_prompt": (
            "✅ Canal {name} adicionado à categoria {category}.\n\n"
            "Buscar os últimos 3 vídeos?"
        ),
        "fetch_starting": "⏳ Buscando últimos vídeos...",
        "fetch_processed": "✅ Processados {done} de {total} vídeos.",
        "fetch_skipped": "👌 OK, vídeos não serão buscados.",
        "error_notify_body": "⚠️ Erro ao processar:\n{title}\n{error}",

        # ── Phase 7.3b ──
        "pipeline_err_video_id_extract": "Não foi possível extrair o ID do vídeo do link.",
        "pipeline_err_video_already_processed": "Este vídeo já foi processado.",
        "pipeline_err_transcript_unavailable": "Transcrição indisponível para: {title}",
        "pipeline_err_article_already_processed": "Este artigo já foi processado.",
        "pipeline_err_web_extract_failed": (
            "Não foi possível extrair o conteúdo desta página.\n"
            "O site pode exigir JavaScript ou bloquear scraping."
        ),
        "pipeline_err_unknown_source_type": "Tipo de conteúdo desconhecido: {source_type}",
        "pipeline_err_summarize_failed": "Não foi possível gerar um resumo para: {title}",

        # ── Phase 7.9 / Phase 8 ──
        "get_usage": (
            "Uso:\n"
            "• /get — navegar por categoria\n"
            "• /get <entry_id> — abrir uma entrada pelo ID de 8 caracteres"
        ),
        "get_not_found": (
            "⚠️ Entrada `{entry_id}` não encontrada. Execute /recent ou "
            "/search para ver os IDs atuais."
        ),
        "get_read_failed": "⚠️ Falha ao ler o arquivo da entrada.",
        "recent_get_hint": "💡 /get — navegar por categoria",
        "get_pick_category": "📂 Escolha uma categoria para navegar:",
        "get_pick_entry": "📁 {category} — {count} entradas. Escolha uma:",
        "get_empty_base": "📭 Base de conhecimento vazia. Envie um link primeiro.",
        "get_category_empty": "📭 Ainda não há entradas nesta categoria.",
        "entry_btn_md_file": "📄 Resumo (.md)",
        "entry_btn_raw_file": "📜 Fonte completa",
        "entry_no_raw_text": "Sem arquivo de texto bruto para esta entrada.",
        "entry_file_caption": "📎 {name}",
    },
    "zh": {
        "welcome_returning": (
            "👋 PulseBrain 已就绪。\n\n"
            "向我发送 YouTube 视频、文章或频道的链接 — 我将处理并保存到知识库。\n\n"
            "使用 /help 查看命令列表。"
        ),
        "welcome_first_run": (
            "👋 你好！我是 PulseBrain — 你的个人知识聚合器。\n\n"
            "你经常把很多东西「留着以后看」，但从不回头。我来解决这个问题：\n"
            "• 📎 发我一个 YouTube 视频或文章链接 — 我会总结并按分类归档。\n"
            "• 📡 订阅 YouTube 频道 — 我会定期监控，把新视频排队供你审核。\n"
            "• 💬 用自然语言提问 — 我会在你的知识库里搜索并附上来源回答。\n"
            "• 📂 一切都是你的 — 简单的 markdown 文件，没有云端绑定。\n\n"
            "花 3 分钟设置个人资料，让我根据你来评估相关性。"
            "/cancel 可以随时退出。"
        ),
        "help_text": (
            "📖 命令：\n\n"
            "/add <url> [category] — 添加 YouTube 频道到监控\n"
            "/remove <name> — 禁用频道\n"
            "/list — 所有监控中的频道\n"
            "/categories — 带条目数的分类\n"
            "/search <查询> — 搜索知识库\n"
            "/recent [N] — 最近 N 条（默认 5）\n"
            "/pending — 等待确认的条目\n"
            "/rejected [N] — 最近自动拒绝的视频\n"
            "/get <id> — 完整文本 + 下载 .md/原始文件\n"
            "/status — 机器人状态\n"
            "/run — 强制检查频道\n"
            "/stats — 详细统计\n"
            "/language — 切换界面语言\n"
            "/onboarding — 重新运行设置向导\n"
            "/cancel — 取消当前对话\n"
            "/help — 本帮助\n\n"
            "或者直接发送链接 — 机器人会识别类型。\n"
            "或者用纯文本提问 — 机器人将从知识库作答。"
        ),
        "language_menu_prompt": "选择界面语言：",
        "language_changed": "语言已切换为：{name}",
        "wizard_lang_prompt": "首先 — 选择界面语言：",
        "wizard_start_button": "▶️ 开始",
        "wizard_skip_button": "⏭ 跳过",
        "wizard_done_button": "✅ 完成",
        "wizard_welcome_body": (
            "我将引导你回答几个问题：\n\n"
            "1. 你是谁，做什么的\n"
            "2. 你现在在学什么\n"
            "3. 你日常使用哪些工具\n"
            "4. 你绝对不想看到什么\n"
            "5. 起始分类和频道\n\n"
            "随时输入 /cancel 中止。"
        ),
        "wizard_persona_prompt": (
            "用几句话介绍你自己：职业、做什么、经验水平。"
        ),
        "wizard_learning_prompt": (
            "你现在正在主动学习什么？每行一个主题。\n"
            "例如：\n"
            "AI 代理\n"
            "RAG 和向量数据库\n"
            "LLM 成本优化"
        ),
        "wizard_stack_prompt": (
            "你已经熟练使用哪些工具？每行一个。"
        ),
        "wizard_notinterested_prompt": (
            "你绝对不想看到什么？例如：加密货币、企业销售、移动开发。可选 — 可以跳过。"
        ),
        "wizard_categories_prompt": (
            "起始分类。勾选你想要的 — 其余不会创建。\n完成后点击完成按钮。"
        ),
        "wizard_channels_prompt": (
            "起始频道。选择现在要订阅哪些 — 其余可以稍后通过 /add 添加。"
        ),
        "wizard_channels_empty": (
            "还没有预设频道。你可以稍后通过 /add 添加。"
        ),
        "wizard_done": (
            "✅ 全部就绪！\n\n"
            "我会每小时检查频道并按你的配置文件过滤。速查：\n\n"
            "• 发送任何 URL — 我会处理\n"
            "• /pending — 审批队列\n"
            "• /rejected — 被自动拒绝的内容\n"
            "• /language — 切换语言\n"
            "• /help — 其他所有"
        ),
        "cancel_confirmed": "❌ 已取消。状态已清除。",
        "cancel_nothing_to_cancel": "👌 没有可取消的。",
        "round_digest_body": (
            "🔄 运行完成\n\n"
            "已检查频道：{channels}\n"
            "新增到 /pending：{processed}\n"
            "自动拒绝：{rejected}\n"
            "错误：{failed}\n\n"
            "下次运行：{interval} 分钟后"
        ),
        "wizard_lang_saved": "✅ 语言已保存。",
        "onboarding_confirm_rerun": (
            "⚠️ 配置文件已设置。重新运行引导？\n"
            "当前配置文件将被覆盖，但分类和频道会保留。"
        ),
        "onboarding_rerun_yes": "🔁 是，重新设置",
        "onboarding_rerun_no": "🛑 不，保持原样",
        "onboarding_kept_existing": "👌 保持原样。",

        # ── Phase 7.3a ──
        "pending_summary_label": "摘要",
        "pending_category_label": "分类",
        "pending_new_cat_marker": " 🆕 (新!)",
        "pending_relevance_label": "相关性",
        "pending_awaiting_label": "⏳ 等待确认",
        "pending_btn_save": "✅ 保存",
        "pending_btn_reject": "❌ 拒绝",
        "pending_btn_category": "🔄 分类",
        "pending_btn_new_category": "➕ 新分类",
        "pending_saved_suffix": "\n\n✅ 已保存：{path}",
        "pending_rejected_suffix": "\n\n❌ 已拒绝",
        "pending_record_gone": "⚠️ 条目已不在队列中。",
        "pending_save_failed": "⚠️ 保存失败。",
        "list_empty": "📡 没有监控的频道。",
        "list_header": "📡 监控的频道：\n",
        "add_usage": "用法：/add <youtube_url> [category]",
        "add_resolving": "⏳ 正在解析频道...",
        "add_resolve_failed": "⚠️ 无法从该链接解析频道。",
        "add_already_tracked": "频道 {name} 已在监控中。",
        "add_added_to_category": "✅ 频道 {name} 已添加到分类 {category}。",
        "add_pick_category": "📡 频道：{name}\n选择一个分类：",
        "remove_usage": "用法：/remove <channel_name>",
        "remove_disabled": "⏸ 频道 {name} 已禁用。",
        "remove_not_found": "未找到频道 '{name}'。",
        "categories_empty": "📂 还没有条目。",
        "categories_header": "📂 分类：\n",
        "categories_stale_marker": " (长时间未更新)",
        "categories_entry_count": "{count} 条",
        "categories_item_line": "    ⭐ 均值 {avg}   📅 最新：{last}",
        "search_usage": "用法：/search <查询>",
        "search_nothing": "🔍 没有找到关于 \"{query}\" 的内容。",
        "search_found_header": "🔍 找到 {count} 条关于 \"{query}\" 的结果：\n",
        "recent_empty": "📋 还没有条目。",
        "recent_header": "📋 最近 {count} 条：\n",
        "status_body": (
            "📁 条目：{total}\n"
            "📺 视频：{videos}\n"
            "📰 文章：{articles}\n"
            "📡 频道：{active}/{all}\n"
            "📊 平均相关性：{avg}/10\n"
            "📅 本周：{this_week}\n"
        ),
        "run_starting": "🔄 开始检查频道...",
        "run_processed": "✅ 已处理 {count} 个新视频。",
        "run_nothing": "✅ 未找到新视频。",
        "pending_queue_empty": "📭 审批队列为空。",
        "pending_queue_header": "⏳ 队列中：{count}（显示最近 10 条）",
        "reject_reason_low_relevance": "相关性低",
        "reject_reason_manual": "手动",
        "rejected_empty": (
            "📭 拒绝日志为空。\n"
            "没有自动拒绝任何内容 — 要么相关性阈值足够宽松，要么还没有新视频到来。"
        ),
        "rejected_header": "❌ 最近 {count} 条被拒绝：\n",
        "processing_video": "⏳ 正在处理视频...",
        "processing_unknown_error": "⚠️ 发生未知错误。",
        "processing_article": "⏳ 正在阅读文章...",
        "channel_add_pick_category": (
            "📡 频道：{name}\n"
            "添加到监控？\n\n"
            "选择一个分类："
        ),
        "qa_searching": "🔍 正在搜索知识库...",
        "qa_nothing": (
            "🤷 该主题还没有收集任何内容。\n"
            "试着细化查询，或者把相关链接发给我。"
        ),
        "qa_failed": "⚠️ 无法生成回答。请稍后再试。",
        "qa_answer_header": "🧠 基于 {count} 个来源：",
        "qa_sources_header": "📚 来源：",
        "new_cat_invalid_slug": (
            "⚠️ 无效的 slug。请使用 ASCII 字母、数字和连字符"
            "（最多 30 字符）。"
        ),
        "new_cat_created_lost": (
            "✅ 分类 `{slug}` 已创建，但频道数据丢失。请重新 /add。"
        ),
        "new_cat_created_channel_added": (
            "✅ 分类 `{slug}` 已创建。\n"
            "✅ 频道 {name} 已添加。\n\n"
            "获取最近 3 个视频？"
        ),
        "new_cat_created_no_record": (
            "✅ 分类 `{slug}` 已创建，但条目已不在队列中。"
        ),
        "new_cat_prompt": (
            "✏️ 输入新分类的 slug（例如：`machine-learning`）。\n"
            "可选：在空格后加上描述："
        ),
        "new_cat_btn_yes": "✅ 是",
        "new_cat_btn_no": "❌ 否",
        "channel_data_lost": "⚠️ 频道数据丢失，请重试。",
        "channel_added_fetch_prompt": (
            "✅ 频道 {name} 已添加到分类 {category}。\n\n"
            "获取最近 3 个视频？"
        ),
        "fetch_starting": "⏳ 正在获取最新视频...",
        "fetch_processed": "✅ 已处理 {done}/{total} 个视频。",
        "fetch_skipped": "👌 好，视频不会获取。",
        "error_notify_body": "⚠️ 处理时出错：\n{title}\n{error}",

        # ── Phase 7.3b ──
        "pipeline_err_video_id_extract": "无法从链接中提取视频 ID。",
        "pipeline_err_video_already_processed": "该视频已经处理过。",
        "pipeline_err_transcript_unavailable": "无法获取字幕：{title}",
        "pipeline_err_article_already_processed": "该文章已经处理过。",
        "pipeline_err_web_extract_failed": (
            "无法从此页面提取内容。\n"
            "网站可能需要 JavaScript 或屏蔽了抓取。"
        ),
        "pipeline_err_unknown_source_type": "未知的内容类型：{source_type}",
        "pipeline_err_summarize_failed": "无法为以下内容生成摘要：{title}",

        # ── Phase 7.9 / Phase 8 ──
        "get_usage": (
            "用法：\n"
            "• /get — 按分类浏览\n"
            "• /get <entry_id> — 通过 8 位 ID 打开特定条目"
        ),
        "get_not_found": (
            "⚠️ 找不到条目 `{entry_id}`。运行 /recent 或 /search 查看当前 ID。"
        ),
        "get_read_failed": "⚠️ 无法从磁盘读取条目文件。",
        "recent_get_hint": "💡 /get — 按分类浏览",
        "get_pick_category": "📂 选择要浏览的分类：",
        "get_pick_entry": "📁 {category} — {count} 条。选择一项：",
        "get_empty_base": "📭 知识库为空。请先发我一条链接。",
        "get_category_empty": "📭 这个分类暂时还没有条目。",
        "entry_btn_md_file": "📄 摘要 (.md)",
        "entry_btn_raw_file": "📜 完整来源",
        "entry_no_raw_text": "该条目没有原始文本文件。",
        "entry_file_caption": "📎 {name}",
    },
    "ja": {
        "welcome_returning": (
            "👋 PulseBrain の準備ができました。\n\n"
            "YouTube 動画、記事、チャンネルのリンクを送信してください — "
            "処理してナレッジベースに保存します。\n\n"
            "コマンドリストは /help で確認できます。"
        ),
        "welcome_first_run": (
            "👋 こんにちは！ PulseBrain です — あなた専用の"
            "ナレッジ・アグリゲーター。\n\n"
            "たくさんのものを「後で読もう」と保存して、結局戻ってこない"
            "ですよね。それを直します：\n"
            "• 📎 YouTube リンクや記事を送ってください — 要約してカテゴリーに"
            "振り分けます。\n"
            "• 📡 YouTube チャンネルを登録してください — 定期的にチェックして、"
            "新しい動画を承認待ちに入れます。\n"
            "• 💬 自然文で質問してください — ナレッジベースを検索して、"
            "出典付きで答えます。\n"
            "• 📂 すべてあなたのもの — ただの markdown ファイル、クラウド"
            "ロックインはありません。\n\n"
            "3 分ほどでプロフィール設定をしましょう。あなたに合った関連性"
            "評価ができます。/cancel でいつでも中止できます。"
        ),
        "help_text": (
            "📖 コマンド：\n\n"
            "/add <url> [category] — YouTube チャンネルを監視に追加\n"
            "/remove <name> — チャンネルを無効化\n"
            "/list — 監視中のすべてのチャンネル\n"
            "/categories — エントリ数付きカテゴリ\n"
            "/search <クエリ> — ナレッジベースを検索\n"
            "/recent [N] — 最新 N 件（既定 5）\n"
            "/pending — 承認待ちのエントリ\n"
            "/rejected [N] — 最近自動却下された動画\n"
            "/get <id> — 全文 + .md / 生テキストのダウンロード\n"
            "/status — ボットの状態\n"
            "/run — チャンネルチェックを強制実行\n"
            "/stats — 詳細統計\n"
            "/language — インターフェース言語を切り替え\n"
            "/onboarding — セットアップウィザードを再実行\n"
            "/cancel — 現在の対話をキャンセル\n"
            "/help — このヘルプ\n\n"
            "あるいはリンクをそのまま送信 — ボットがタイプを認識します。\n"
            "あるいはテキストで質問 — ボットがナレッジベースから答えます。"
        ),
        "language_menu_prompt": "インターフェース言語を選択：",
        "language_changed": "言語を変更しました：{name}",
        "wizard_lang_prompt": "まず — インターフェース言語を選択：",
        "wizard_start_button": "▶️ 開始",
        "wizard_skip_button": "⏭ スキップ",
        "wizard_done_button": "✅ 完了",
        "wizard_welcome_body": (
            "いくつかの質問にお答えいただきます：\n\n"
            "1. あなたは誰で何をしていますか\n"
            "2. 今何を学んでいますか\n"
            "3. 日常的に使っているツール\n"
            "4. 絶対に見たくないもの\n"
            "5. 初期カテゴリとチャンネル\n\n"
            "いつでも /cancel で中断できます。"
        ),
        "wizard_persona_prompt": (
            "あなたについて一言：職業、仕事内容、経験レベル。"
        ),
        "wizard_learning_prompt": (
            "今何を積極的に学んでいますか？1 行に 1 トピック。\n"
            "例：\n"
            "AI エージェント\n"
            "RAG とベクトル DB\n"
            "LLM のコスト最適化"
        ),
        "wizard_stack_prompt": (
            "すでに使いこなしているツールは？1 行に 1 つ。"
        ),
        "wizard_notinterested_prompt": (
            "絶対に見たくないものは？例：暗号通貨、エンタープライズ営業、"
            "モバイル開発。任意 — スキップ可。"
        ),
        "wizard_categories_prompt": (
            "初期カテゴリ。欲しいものをチェック — それ以外は作成されません。\n"
            "終わったら完了ボタンをタップ。"
        ),
        "wizard_channels_prompt": (
            "初期チャンネル。今購読するものを選択 — 他は後から /add で追加できます。"
        ),
        "wizard_channels_empty": (
            "プリセットチャンネルはまだありません。後から /add で追加できます。"
        ),
        "wizard_done": (
            "✅ 準備完了！\n\n"
            "1 時間ごとにチャンネルをチェックし、プロフィールでフィルタリング"
            "します。クイックリファレンス：\n\n"
            "• URL を送信 — 処理します\n"
            "• /pending — 承認キュー\n"
            "• /rejected — 自動却下された内容\n"
            "• /language — 言語切り替え\n"
            "• /help — その他すべて"
        ),
        "cancel_confirmed": "❌ キャンセルしました。状態をクリア。",
        "cancel_nothing_to_cancel": "👌 キャンセルするものはありません。",
        "round_digest_body": (
            "🔄 実行完了\n\n"
            "チェック済みチャンネル：{channels}\n"
            "/pending に新規：{processed}\n"
            "自動却下：{rejected}\n"
            "エラー：{failed}\n\n"
            "次回：{interval} 分後"
        ),
        "wizard_lang_saved": "✅ 言語を保存しました。",
        "onboarding_confirm_rerun": (
            "⚠️ プロフィールはすでに設定済みです。オンボーディングを再実行しますか？\n"
            "現在のプロフィールは上書きされますが、カテゴリとチャンネルは残ります。"
        ),
        "onboarding_rerun_yes": "🔁 はい、やり直す",
        "onboarding_rerun_no": "🛑 いいえ、このまま",
        "onboarding_kept_existing": "👌 そのままにしました。",

        # ── Phase 7.3a ──
        "pending_summary_label": "要約",
        "pending_category_label": "カテゴリ",
        "pending_new_cat_marker": " 🆕 (新規!)",
        "pending_relevance_label": "関連性",
        "pending_awaiting_label": "⏳ 承認待ち",
        "pending_btn_save": "✅ 保存",
        "pending_btn_reject": "❌ 却下",
        "pending_btn_category": "🔄 カテゴリ",
        "pending_btn_new_category": "➕ 新規カテゴリ",
        "pending_saved_suffix": "\n\n✅ 保存しました：{path}",
        "pending_rejected_suffix": "\n\n❌ 却下しました",
        "pending_record_gone": "⚠️ エントリはもうキューにありません。",
        "pending_save_failed": "⚠️ エントリの保存に失敗しました。",
        "list_empty": "📡 監視中のチャンネルはありません。",
        "list_header": "📡 監視中のチャンネル：\n",
        "add_usage": "使用法：/add <youtube_url> [category]",
        "add_resolving": "⏳ チャンネルを解決中...",
        "add_resolve_failed": "⚠️ リンクからチャンネルを特定できませんでした。",
        "add_already_tracked": "チャンネル {name} はすでに追跡中です。",
        "add_added_to_category": "✅ チャンネル {name} をカテゴリ {category} に追加しました。",
        "add_pick_category": "📡 チャンネル：{name}\nカテゴリを選択：",
        "remove_usage": "使用法：/remove <channel_name>",
        "remove_disabled": "⏸ チャンネル {name} を無効化しました。",
        "remove_not_found": "チャンネル '{name}' が見つかりません。",
        "categories_empty": "📂 まだエントリがありません。",
        "categories_header": "📂 カテゴリ：\n",
        "categories_stale_marker": " (停滞中)",
        "categories_entry_count": "{count} 件",
        "categories_item_line": "    ⭐ 平均 {avg}   📅 最新：{last}",
        "search_usage": "使用法：/search <クエリ>",
        "search_nothing": "🔍 \"{query}\" に関する情報は見つかりませんでした。",
        "search_found_header": "🔍 \"{query}\" に関する {count} 件の結果：\n",
        "recent_empty": "📋 まだエントリがありません。",
        "recent_header": "📋 最新 {count} 件：\n",
        "status_body": (
            "📁 エントリ：{total}\n"
            "📺 動画：{videos}\n"
            "📰 記事：{articles}\n"
            "📡 チャンネル：{active}/{all}\n"
            "📊 平均関連性：{avg}/10\n"
            "📅 今週：{this_week}\n"
        ),
        "run_starting": "🔄 チャンネルチェックを実行中...",
        "run_processed": "✅ {count} 件の新しい動画を処理しました。",
        "run_nothing": "✅ 新しい動画はありませんでした。",
        "pending_queue_empty": "📭 承認キューは空です。",
        "pending_queue_header": "⏳ キュー内：{count}（最新 10 件を表示）",
        "reject_reason_low_relevance": "関連性が低い",
        "reject_reason_manual": "手動",
        "rejected_empty": (
            "📭 却下ログは空です。\n"
            "自動却下されたものはありません — 関連性しきい値が十分に緩いか、"
            "まだ新しい動画が来ていないかです。"
        ),
        "rejected_header": "❌ 最新 {count} 件の却下：\n",
        "processing_video": "⏳ 動画を処理中...",
        "processing_unknown_error": "⚠️ 不明なエラーが発生しました。",
        "processing_article": "⏳ 記事を読んでいます...",
        "channel_add_pick_category": (
            "📡 チャンネル：{name}\n"
            "監視に追加しますか？\n\n"
            "カテゴリを選択："
        ),
        "qa_searching": "🔍 ナレッジベースを検索中...",
        "qa_nothing": (
            "🤷 このトピックについてはまだ何も集まっていません。\n"
            "クエリを絞り込むか、関連するリンクを送ってください。"
        ),
        "qa_failed": "⚠️ 回答の生成に失敗しました。後でもう一度試してください。",
        "qa_answer_header": "🧠 {count} 件のソースに基づく：",
        "qa_sources_header": "📚 ソース：",
        "new_cat_invalid_slug": (
            "⚠️ 無効な slug です。ASCII 文字、数字、ハイフンを使用してください"
            "（最大 30 文字）。"
        ),
        "new_cat_created_lost": (
            "✅ カテゴリ `{slug}` を作成しましたが、チャンネルデータが失われました。"
            "/add をもう一度お試しください。"
        ),
        "new_cat_created_channel_added": (
            "✅ カテゴリ `{slug}` を作成しました。\n"
            "✅ チャンネル {name} を追加しました。\n\n"
            "最新の 3 本の動画を取得しますか？"
        ),
        "new_cat_created_no_record": (
            "✅ カテゴリ `{slug}` を作成しましたが、エントリはもうキューにありません。"
        ),
        "new_cat_prompt": (
            "✏️ 新しいカテゴリの slug を入力してください"
            "（例：`machine-learning`）。\n"
            "スペースのあとに説明を追加できます："
        ),
        "new_cat_btn_yes": "✅ はい",
        "new_cat_btn_no": "❌ いいえ",
        "channel_data_lost": "⚠️ チャンネルデータが失われました。もう一度お試しください。",
        "channel_added_fetch_prompt": (
            "✅ チャンネル {name} をカテゴリ {category} に追加しました。\n\n"
            "最新の 3 本の動画を取得しますか？"
        ),
        "fetch_starting": "⏳ 最新の動画を取得中...",
        "fetch_processed": "✅ {done}/{total} 本の動画を処理しました。",
        "fetch_skipped": "👌 OK、動画は取得しません。",
        "error_notify_body": "⚠️ 処理中にエラー：\n{title}\n{error}",

        # ── Phase 7.3b ──
        "pipeline_err_video_id_extract": "リンクから動画 ID を抽出できませんでした。",
        "pipeline_err_video_already_processed": "この動画はすでに処理済みです。",
        "pipeline_err_transcript_unavailable": "トランスクリプトが利用できません：{title}",
        "pipeline_err_article_already_processed": "この記事はすでに処理済みです。",
        "pipeline_err_web_extract_failed": (
            "このページからコンテンツを抽出できませんでした。\n"
            "サイトが JavaScript を必要とするか、スクレイピングをブロックしている可能性があります。"
        ),
        "pipeline_err_unknown_source_type": "不明なコンテンツタイプ：{source_type}",
        "pipeline_err_summarize_failed": "以下の要約を作成できませんでした：{title}",

        # ── Phase 7.9 / Phase 8 ──
        "get_usage": (
            "使用法：\n"
            "• /get — カテゴリで閲覧\n"
            "• /get <entry_id> — 8 文字の ID で特定のエントリを開く"
        ),
        "get_not_found": (
            "⚠️ エントリ `{entry_id}` が見つかりません。"
            "/recent または /search で現在の ID を確認してください。"
        ),
        "get_read_failed": "⚠️ ディスクからエントリファイルを読み込めませんでした。",
        "recent_get_hint": "💡 /get — カテゴリで閲覧",
        "get_pick_category": "📂 閲覧するカテゴリを選択:",
        "get_pick_entry": "📁 {category} — {count} 件。選択してください:",
        "get_empty_base": "📭 ナレッジベースは空です。まずリンクを送ってください。",
        "get_category_empty": "📭 このカテゴリにはまだエントリがありません。",
        "entry_btn_md_file": "📄 要約 (.md)",
        "entry_btn_raw_file": "📜 完全なソース",
        "entry_no_raw_text": "このエントリには生テキストファイルがありません。",
        "entry_file_caption": "📎 {name}",
    },
    "ar": {
        "welcome_returning": (
            "👋 PulseBrain جاهز.\n\n"
            "أرسل لي رابط فيديو YouTube أو مقال أو قناة — سأعالجه وأحفظه "
            "في قاعدة المعرفة.\n\n"
            "استخدم /help للاطلاع على قائمة الأوامر."
        ),
        "welcome_first_run": (
            "👋 مرحباً! أنا PulseBrain — مجمّع المعرفة الشخصي الخاص بك.\n\n"
            "أنت تحفظ الكثير «للاحقاً» ولا تعود إليه أبداً. أنا أحلّ هذه "
            "المشكلة:\n"
            "• 📎 أرسل لي رابط يوتيوب أو مقال — ألخصه وأرتبه في فئات.\n"
            "• 📡 اشترك في قنوات يوتيوب — أراقبها وأضع الفيديوهات الجديدة "
            "في طابور المراجعة.\n"
            "• 💬 اسألني بنص حر — أبحث في قاعدة معرفتك وأجيب مع ذكر "
            "المصادر.\n"
            "• 📂 كل شيء يبقى لك — ملفات markdown بسيطة، بدون قفل سحابي.\n\n"
            "ثلاث دقائق لإعداد ملفك الشخصي حتى أقيس الملاءمة وفقاً لك "
            "أنت. /cancel للإلغاء في أي وقت."
        ),
        "help_text": (
            "📖 الأوامر:\n\n"
            "/add <url> [category] — إضافة قناة YouTube للمراقبة\n"
            "/remove <name> — تعطيل قناة\n"
            "/list — جميع القنوات المراقبة\n"
            "/categories — الفئات مع عدد المدخلات\n"
            "/search <استعلام> — البحث في قاعدة المعرفة\n"
            "/recent [N] — آخر N مدخلات (الافتراضي 5)\n"
            "/pending — المدخلات في انتظار الموافقة\n"
            "/rejected [N] — الفيديوهات المرفوضة تلقائياً مؤخراً\n"
            "/get <id> — النص الكامل + تنزيل ملفات .md/raw\n"
            "/status — حالة البوت\n"
            "/run — فرض فحص القنوات\n"
            "/stats — إحصائيات مفصلة\n"
            "/language — تغيير لغة الواجهة\n"
            "/onboarding — إعادة تشغيل معالج الإعداد\n"
            "/cancel — إلغاء الحوار الحالي\n"
            "/help — هذه المساعدة\n\n"
            "أو أرسل رابطاً فحسب — سيتعرف البوت على النوع.\n"
            "أو اطرح سؤالاً بنص عادي — سيجيب البوت من قاعدة المعرفة."
        ),
        "language_menu_prompt": "اختر لغة الواجهة:",
        "language_changed": "تم تغيير اللغة إلى: {name}",
        "wizard_lang_prompt": "أولاً — اختر لغة الواجهة:",
        "wizard_start_button": "▶️ ابدأ",
        "wizard_skip_button": "⏭ تخطي",
        "wizard_done_button": "✅ تم",
        "wizard_welcome_body": (
            "سأرشدك عبر بضعة أسئلة:\n\n"
            "1. من أنت وماذا تعمل\n"
            "2. ما الذي تتعلمه حالياً\n"
            "3. الأدوات التي تستخدمها يومياً\n"
            "4. ما الذي لا تريد رؤيته بتاتاً\n"
            "5. الفئات والقنوات الابتدائية\n\n"
            "اكتب /cancel للإلغاء في أي وقت."
        ),
        "wizard_persona_prompt": (
            "جملتان عن نفسك: المهنة، ماذا تعمل، مستوى الخبرة."
        ),
        "wizard_learning_prompt": (
            "ما الذي تتعلمه بنشاط الآن؟ موضوع واحد في كل سطر.\n"
            "على سبيل المثال:\n"
            "وكلاء الذكاء الاصطناعي\n"
            "RAG وقواعد البيانات الشعاعية\n"
            "تحسين تكلفة LLM"
        ),
        "wizard_stack_prompt": (
            "ما الأدوات التي تتقنها بالفعل؟ واحدة في كل سطر."
        ),
        "wizard_notinterested_prompt": (
            "ما الذي لا تريد رؤيته بتاتاً؟ على سبيل المثال: العملات المشفرة، "
            "مبيعات المؤسسات، تطوير الموبايل. اختياري — يمكن التخطي."
        ),
        "wizard_categories_prompt": (
            "الفئات الابتدائية. حدد التي تريدها — الباقي لن يُنشأ.\n"
            "اضغط تم عند الانتهاء."
        ),
        "wizard_channels_prompt": (
            "القنوات الابتدائية. اختر أيها ستشترك فيها الآن — يمكن إضافة "
            "غيرها لاحقاً عبر /add."
        ),
        "wizard_channels_empty": (
            "لا توجد قنوات مسبقة بعد. يمكنك إضافتها لاحقاً عبر /add."
        ),
        "wizard_done": (
            "✅ كل شيء جاهز!\n\n"
            "سأفحص القنوات كل ساعة وأفلتر حسب ملفك الشخصي. مرجع سريع:\n\n"
            "• أرسل أي رابط — سأعالجه\n"
            "• /pending — طابور الموافقة\n"
            "• /rejected — ما رُفض تلقائياً\n"
            "• /language — تغيير اللغة\n"
            "• /help — كل شيء آخر"
        ),
        "cancel_confirmed": "❌ تم الإلغاء. تمّت إعادة الحالة.",
        "cancel_nothing_to_cancel": "👌 لا يوجد ما يُلغى.",
        "round_digest_body": (
            "🔄 اكتملت الجولة\n\n"
            "القنوات المفحوصة: {channels}\n"
            "جديد في /pending: {processed}\n"
            "مرفوض تلقائياً: {rejected}\n"
            "الأخطاء: {failed}\n\n"
            "الجولة التالية خلال {interval} دقيقة"
        ),
        "wizard_lang_saved": "✅ تم حفظ اللغة.",
        "onboarding_confirm_rerun": (
            "⚠️ الملف الشخصي مُعد بالفعل. إعادة تشغيل الإعداد؟\n"
            "سيتم استبدال الملف الشخصي الحالي، لكن الفئات والقنوات ستبقى."
        ),
        "onboarding_rerun_yes": "🔁 نعم، أعد",
        "onboarding_rerun_no": "🛑 لا، اتركه",
        "onboarding_kept_existing": "👌 تركته كما هو.",

        # ── Phase 7.3a ──
        "pending_summary_label": "ملخص",
        "pending_category_label": "الفئة",
        "pending_new_cat_marker": " 🆕 (جديدة!)",
        "pending_relevance_label": "الأهمية",
        "pending_awaiting_label": "⏳ في انتظار الموافقة",
        "pending_btn_save": "✅ حفظ",
        "pending_btn_reject": "❌ رفض",
        "pending_btn_category": "🔄 الفئة",
        "pending_btn_new_category": "➕ فئة جديدة",
        "pending_saved_suffix": "\n\n✅ تم الحفظ: {path}",
        "pending_rejected_suffix": "\n\n❌ مرفوض",
        "pending_record_gone": "⚠️ المدخل لم يعد في الطابور.",
        "pending_save_failed": "⚠️ فشل حفظ المدخل.",
        "list_empty": "📡 لا توجد قنوات مراقبة.",
        "list_header": "📡 القنوات المراقبة:\n",
        "add_usage": "الاستخدام: /add <youtube_url> [category]",
        "add_resolving": "⏳ جاري تحديد القناة...",
        "add_resolve_failed": "⚠️ تعذر تحديد القناة من الرابط.",
        "add_already_tracked": "القناة {name} مراقبة بالفعل.",
        "add_added_to_category": "✅ تمت إضافة القناة {name} إلى الفئة {category}.",
        "add_pick_category": "📡 القناة: {name}\nاختر فئة:",
        "remove_usage": "الاستخدام: /remove <channel_name>",
        "remove_disabled": "⏸ تم تعطيل القناة {name}.",
        "remove_not_found": "القناة '{name}' غير موجودة.",
        "categories_empty": "📂 لا توجد مدخلات بعد.",
        "categories_header": "📂 الفئات:\n",
        "categories_stale_marker": " (راكدة)",
        "categories_entry_count": "{count} مدخل",
        "categories_item_line": "    ⭐ متوسط {avg}   📅 الأخير: {last}",
        "search_usage": "الاستخدام: /search <استعلام>",
        "search_nothing": "🔍 لم يُعثر على شيء لـ \"{query}\".",
        "search_found_header": "🔍 {count} نتيجة لـ \"{query}\":\n",
        "recent_empty": "📋 لا توجد مدخلات بعد.",
        "recent_header": "📋 آخر {count} مدخل:\n",
        "status_body": (
            "📁 المدخلات: {total}\n"
            "📺 الفيديوهات: {videos}\n"
            "📰 المقالات: {articles}\n"
            "📡 القنوات: {active}/{all}\n"
            "📊 متوسط الأهمية: {avg}/10\n"
            "📅 هذا الأسبوع: {this_week}\n"
        ),
        "run_starting": "🔄 أبدأ فحص القنوات...",
        "run_processed": "✅ تمت معالجة {count} فيديو جديد.",
        "run_nothing": "✅ لم يُعثر على فيديوهات جديدة.",
        "pending_queue_empty": "📭 طابور الموافقة فارغ.",
        "pending_queue_header": "⏳ في الطابور: {count} (عرض آخر 10)",
        "reject_reason_low_relevance": "أهمية منخفضة",
        "reject_reason_manual": "يدوي",
        "rejected_empty": (
            "📭 سجل المرفوضات فارغ.\n"
            "لم يُرفض شيء تلقائياً — إما أن عتبة الأهمية ناعمة بما يكفي، "
            "أو لم تصل فيديوهات جديدة بعد."
        ),
        "rejected_header": "❌ آخر {count} مرفوض:\n",
        "processing_video": "⏳ جاري معالجة الفيديو...",
        "processing_unknown_error": "⚠️ حدث خطأ غير معروف.",
        "processing_article": "⏳ جاري قراءة المقال...",
        "channel_add_pick_category": (
            "📡 القناة: {name}\n"
            "إضافة إلى المراقبة؟\n\n"
            "اختر فئة:"
        ),
        "qa_searching": "🔍 البحث في قاعدة المعرفة...",
        "qa_nothing": (
            "🤷 لم يُجمع شيء عن هذا الموضوع بعد.\n"
            "جرب تنقيح الاستعلام أو أرسل لي رابطاً حول الموضوع."
        ),
        "qa_failed": "⚠️ تعذر توليد إجابة. حاول لاحقاً.",
        "qa_answer_header": "🧠 بناءً على {count} مصادر:",
        "qa_sources_header": "📚 المصادر:",
        "new_cat_invalid_slug": (
            "⚠️ slug غير صالح. استخدم أحرف ASCII والأرقام والشرطات "
            "(بحد أقصى 30 حرفاً)."
        ),
        "new_cat_created_lost": (
            "✅ تم إنشاء الفئة `{slug}`، لكن فُقدت بيانات القناة. "
            "جرب /add مرة أخرى."
        ),
        "new_cat_created_channel_added": (
            "✅ تم إنشاء الفئة `{slug}`.\n"
            "✅ تمت إضافة القناة {name}.\n\n"
            "جلب آخر 3 فيديوهات؟"
        ),
        "new_cat_created_no_record": (
            "✅ تم إنشاء الفئة `{slug}`، لكن المدخل لم يعد في الطابور."
        ),
        "new_cat_prompt": (
            "✏️ أدخل slug الفئة الجديدة "
            "(مثل: `machine-learning`).\n"
            "اختيارياً: أضف وصفاً بعد مسافة:"
        ),
        "new_cat_btn_yes": "✅ نعم",
        "new_cat_btn_no": "❌ لا",
        "channel_data_lost": "⚠️ فُقدت بيانات القناة، حاول مرة أخرى.",
        "channel_added_fetch_prompt": (
            "✅ تمت إضافة القناة {name} إلى الفئة {category}.\n\n"
            "جلب آخر 3 فيديوهات؟"
        ),
        "fetch_starting": "⏳ جاري جلب أحدث الفيديوهات...",
        "fetch_processed": "✅ تمت معالجة {done} من {total} فيديو.",
        "fetch_skipped": "👌 حسناً، لن يتم جلب الفيديوهات.",
        "error_notify_body": "⚠️ خطأ أثناء المعالجة:\n{title}\n{error}",

        # ── Phase 7.3b ──
        "pipeline_err_video_id_extract": "تعذّر استخراج مُعرِّف الفيديو من الرابط.",
        "pipeline_err_video_already_processed": "تمت معالجة هذا الفيديو سابقاً.",
        "pipeline_err_transcript_unavailable": "النص غير متوفر لـ: {title}",
        "pipeline_err_article_already_processed": "تمت معالجة هذا المقال سابقاً.",
        "pipeline_err_web_extract_failed": (
            "تعذّر استخراج المحتوى من هذه الصفحة.\n"
            "قد يتطلب الموقع JavaScript أو يحظر الجمع."
        ),
        "pipeline_err_unknown_source_type": "نوع محتوى غير معروف: {source_type}",
        "pipeline_err_summarize_failed": "تعذّر توليد ملخص لـ: {title}",

        # ── Phase 7.9 / Phase 8 ──
        "get_usage": (
            "الاستخدام:\n"
            "• /get — التصفح حسب الفئة\n"
            "• /get <entry_id> — فتح مدخل عبر معرّف من 8 أحرف"
        ),
        "get_not_found": (
            "⚠️ المدخل `{entry_id}` غير موجود. شغّل /recent أو /search "
            "لرؤية المعرّفات الحالية."
        ),
        "get_read_failed": "⚠️ فشل قراءة ملف المدخل من القرص.",
        "recent_get_hint": "💡 /get — التصفح حسب الفئة",
        "get_pick_category": "📂 اختر فئة للتصفح:",
        "get_pick_entry": "📁 {category} — {count} مدخل. اختر واحداً:",
        "get_empty_base": "📭 قاعدة المعرفة فارغة. أرسل لي رابطاً أولاً.",
        "get_category_empty": "📭 لا توجد مداخل في هذه الفئة بعد.",
        "entry_btn_md_file": "📄 الملخص (.md)",
        "entry_btn_raw_file": "📜 المصدر الكامل",
        "entry_no_raw_text": "لا يوجد ملف نص خام لهذا المدخل.",
        "entry_file_caption": "📎 {name}",
    },
}


def t(key: str, lang: str = _DEFAULT_LANG, **fmt: Any) -> str:
    """Lookup + format. Fallback chain: *lang* → English → key itself.

    Falling back to the key itself (instead of an empty string) means a
    typo or forgotten migration surfaces loudly in the UI — much easier
    to spot than silent emptiness.
    """
    table = STRINGS.get(lang) or {}
    template = table.get(key) or STRINGS[_DEFAULT_LANG].get(key) or key
    if fmt:
        try:
            return template.format(**fmt)
        except (KeyError, IndexError):
            return template
    return template
