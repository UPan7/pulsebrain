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
            "👋 Hallo! Das ist dein persönliches Gehirn.\n\n"
            "Richten wir es ein — dauert 3-5 Minuten. Du kannst jederzeit "
            "mit /cancel abbrechen."
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
            "👋 Bonjour ! C'est ton cerveau personnel.\n\n"
            "Configurons-le — ça prend 3-5 minutes. Tu peux abandonner à "
            "tout moment avec /cancel."
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
    },
    "es": {
        "welcome_returning": (
            "👋 PulseBrain listo.\n\n"
            "Envíame un enlace a un vídeo de YouTube, artículo o canal — "
            "lo procesaré y guardaré en la base de conocimiento.\n\n"
            "Usa /help para la lista de comandos."
        ),
        "welcome_first_run": (
            "👋 ¡Hola! Este es tu cerebro personal.\n\n"
            "Vamos a configurarlo — toma 3-5 minutos. Puedes abandonar en "
            "cualquier momento con /cancel."
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
    },
    "it": {
        "welcome_returning": (
            "👋 PulseBrain pronto.\n\n"
            "Inviami un link a un video YouTube, articolo o canale — lo "
            "elaborerò e lo salverò nella base di conoscenza.\n\n"
            "Usa /help per la lista dei comandi."
        ),
        "welcome_first_run": (
            "👋 Ciao! Questo è il tuo cervello personale.\n\n"
            "Configuriamolo — ci vogliono 3-5 minuti. Puoi interrompere in "
            "qualsiasi momento con /cancel."
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
    },
    "pt": {
        "welcome_returning": (
            "👋 PulseBrain pronto.\n\n"
            "Envie-me um link para um vídeo do YouTube, artigo ou canal — "
            "vou processá-lo e salvá-lo na base de conhecimento.\n\n"
            "Use /help para a lista de comandos."
        ),
        "welcome_first_run": (
            "👋 Olá! Este é o seu cérebro pessoal.\n\n"
            "Vamos configurá-lo — leva 3-5 minutos. Você pode desistir a "
            "qualquer momento com /cancel."
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
    },
    "zh": {
        "welcome_returning": (
            "👋 PulseBrain 已就绪。\n\n"
            "向我发送 YouTube 视频、文章或频道的链接 — 我将处理并保存到知识库。\n\n"
            "使用 /help 查看命令列表。"
        ),
        "welcome_first_run": (
            "👋 你好！这是你的个人大脑。\n\n"
            "让我们来设置它 — 需要 3-5 分钟。你随时可以用 /cancel 中止。"
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
    },
    "ja": {
        "welcome_returning": (
            "👋 PulseBrain の準備ができました。\n\n"
            "YouTube 動画、記事、チャンネルのリンクを送信してください — "
            "処理してナレッジベースに保存します。\n\n"
            "コマンドリストは /help で確認できます。"
        ),
        "welcome_first_run": (
            "👋 こんにちは！これはあなた専用の脳です。\n\n"
            "セットアップしましょう — 3〜5 分かかります。いつでも /cancel "
            "で中断できます。"
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
    },
    "ar": {
        "welcome_returning": (
            "👋 PulseBrain جاهز.\n\n"
            "أرسل لي رابط فيديو YouTube أو مقال أو قناة — سأعالجه وأحفظه "
            "في قاعدة المعرفة.\n\n"
            "استخدم /help للاطلاع على قائمة الأوامر."
        ),
        "welcome_first_run": (
            "👋 مرحباً! هذا عقلك الشخصي.\n\n"
            "لنقم بإعداده — يستغرق 3-5 دقائق. يمكنك الإلغاء في أي وقت بـ "
            "/cancel."
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
