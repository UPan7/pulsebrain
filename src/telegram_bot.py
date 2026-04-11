"""All Telegram bot handlers: commands, link drops, inline keyboards."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    add_category,
    load_categories,
    load_channels,
    save_channels,
)
from src.extractors.youtube import get_recent_video_ids, resolve_channel_id
from src.pipeline import process_web_article, process_youtube_video
from src.router import SourceType, detect_source_type
from src.storage import get_recent_entries, get_stats, move_entry, search_for_question, search_knowledge
from src.summarize import answer_question

logger = logging.getLogger(__name__)

# URL regex for detecting links in messages
URL_PATTERN = re.compile(r"https?://\S+")

# Telegram message size limit
_TELEGRAM_MSG_LIMIT = 4096


def _truncate_message(text: str, limit: int = _TELEGRAM_MSG_LIMIT) -> str:
    """Truncate message text to fit Telegram's message size limit."""
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


# ── Security: chat ID filter ────────────────────────────────────────────────

def _authorized(update: Update) -> bool:
    """Only respond to the configured chat ID."""
    chat_id = update.effective_chat.id if update.effective_chat else 0
    if chat_id != TELEGRAM_CHAT_ID:
        logger.warning("Unauthorized access attempt from chat_id=%s", chat_id)
        return False
    return True


# ── Command handlers ─────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    await update.message.reply_text(
        "👋 PulseBrain запущен!\n\n"
        "Отправь мне ссылку на YouTube видео, статью или канал — "
        "я обработаю и сохраню в базу знаний.\n\n"
        "Используй /help для списка команд."
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    await update.message.reply_text(
        "📖 Команды:\n\n"
        "/add <url> [category] — Добавить YouTube канал в мониторинг\n"
        "/remove <name> — Отключить канал\n"
        "/list — Все отслеживаемые каналы\n"
        "/categories — Категории с количеством записей\n"
        "/search <запрос> — Поиск по базе знаний\n"
        "/recent [N] — Последние N записей (по умолч. 5)\n"
        "/status — Состояние бота\n"
        "/run — Запустить проверку каналов\n"
        "/stats — Подробная статистика\n"
        "/help — Эта справка\n\n"
        "Или просто отправь ссылку — бот определит тип и обработает!\n"
        "Или задай вопрос текстом — бот ответит по базе знаний."
    )


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    channels = load_channels()
    if not channels:
        await update.message.reply_text("📡 Нет отслеживаемых каналов.")
        return

    lines = ["📡 Отслеживаемые каналы:\n"]
    for ch in channels:
        status = "✅" if ch.get("enabled", True) else "⏸"
        lines.append(f"{status} {ch['name']} — {ch.get('category', '?')}")

    await update.message.reply_text("\n".join(lines))


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("Использование: /add <youtube_url> [category]")
        return

    url = args[0]
    category = args[1] if len(args) > 1 else None

    await update.message.reply_text("⏳ Определяю канал...")

    channel_id, channel_name = resolve_channel_id(url)
    if not channel_id:
        await update.message.reply_text("⚠️ Не удалось определить канал по ссылке.")
        return

    # Check if already exists
    channels = load_channels()
    for ch in channels:
        if ch["id"] == channel_id:
            await update.message.reply_text(f"Канал {channel_name} уже отслеживается.")
            return

    if category:
        # Add directly
        channels.append({
            "name": channel_name,
            "id": channel_id,
            "category": category,
            "enabled": True,
        })
        save_channels(channels)
        await update.message.reply_text(
            f"✅ Канал {channel_name} добавлен в категорию {category}."
        )
    else:
        # Ask for category via inline keyboard
        context.user_data["pending_channel"] = {
            "name": channel_name,
            "id": channel_id,
        }
        keyboard = _category_keyboard("add_channel")
        await update.message.reply_text(
            f"📡 Канал: {channel_name}\n"
            "Выбери категорию:",
            reply_markup=keyboard,
        )


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("Использование: /remove <channel_name>")
        return

    name_query = " ".join(args).lower()
    channels = load_channels()
    found = False
    for ch in channels:
        if ch["name"].lower() == name_query or name_query in ch["name"].lower():
            ch["enabled"] = False
            found = True
            save_channels(channels)
            await update.message.reply_text(f"⏸ Канал {ch['name']} отключён.")
            break

    if not found:
        await update.message.reply_text(f"Канал '{name_query}' не найден.")


async def cmd_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    stats = get_stats()
    categories = load_categories()
    lines = ["📂 Категории:\n"]
    for cat, count in stats["by_category"].items():
        name = categories.get(cat, cat)
        lines.append(f"• {cat}: {count} записей — {name}")

    if not stats["by_category"]:
        lines.append("Пока нет записей.")

    await update.message.reply_text("\n".join(lines))


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("Использование: /search <запрос>")
        return

    query = " ".join(args)
    results = search_knowledge(query)

    if not results:
        await update.message.reply_text(f'🔍 По запросу "{query}" ничего не найдено.')
        return

    lines = [f'🔍 Найдено {len(results)} результатов по "{query}":\n']
    for i, r in enumerate(results[:5], 1):
        type_icon = "📺" if r.get("type") == "youtube_video" else "📰"
        lines.append(
            f"{i}. {type_icon} {r.get('title', '?')}\n"
            f"   {r.get('source', '?')} | {r.get('date', '?')} | "
            f"{r.get('category', '?')} | ⭐ {r.get('relevance', '?')}/10"
        )
        if r.get("summary_preview"):
            lines.append(f"   {r['summary_preview'][:100]}")
        lines.append("")

    await update.message.reply_text("\n".join(lines))


async def cmd_recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    args = context.args or []
    count = int(args[0]) if args and args[0].isdigit() else 5

    entries = get_recent_entries(count)
    if not entries:
        await update.message.reply_text("📋 Пока нет записей.")
        return

    lines = [f"📋 Последние {len(entries)} записей:\n"]
    for e in entries:
        type_icon = "📺" if e.get("type") == "youtube_video" else "📰"
        lines.append(
            f"{type_icon} {e.get('title', '?')}\n"
            f"   {e.get('source', '?')} | {e.get('date', '?')} | {e.get('category', '?')}"
        )

    await update.message.reply_text("\n".join(lines))


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    stats = get_stats()
    channels = load_channels()
    active = sum(1 for ch in channels if ch.get("enabled", True))

    await update.message.reply_text(
        "🤖 PulseBrain Status\n\n"
        f"📁 Записей: {stats['total']}\n"
        f"📺 Видео: {stats['videos']}\n"
        f"📰 Статей: {stats['articles']}\n"
        f"📡 Каналов: {active}/{len(channels)}\n"
        f"📊 Средняя релевантность: {stats['avg_relevance']}/10\n"
        f"📅 За эту неделю: {stats['this_week']}\n"
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    stats = get_stats()

    lines = [
        "📊 Knowledge Base Stats\n",
        f"📁 Total entries: {stats['total']}",
        f"📺 YouTube videos: {stats['videos']}",
        f"📰 Web articles: {stats['articles']}",
        "",
        "By category:",
    ]
    for cat, count in stats["by_category"].items():
        lines.append(f"• {cat}: {count} entries")

    lines.append(f"\nThis week: {stats['this_week']} new entries")
    lines.append(f"Avg relevance: {stats['avg_relevance']}/10")

    if stats["top_sources"]:
        lines.append("\nTop sources:")
        for name, count in stats["top_sources"]:
            lines.append(f"• {name}: {count} entries")

    await update.message.reply_text("\n".join(lines))


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Force a pipeline run for all enabled channels."""
    if not _authorized(update):
        return
    await update.message.reply_text("🔄 Запускаю проверку каналов...")

    from src.scheduler import run_channel_check

    results = await run_channel_check()
    if results:
        await update.message.reply_text(f"✅ Обработано {results} новых видео.")
    else:
        await update.message.reply_text("✅ Новых видео не найдено.")


# ── Link drop handler ────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle any message — detect URLs and process them."""
    if not _authorized(update):
        return

    text = update.message.text or ""

    # Check if we're waiting for a new category name
    waiting_action = context.user_data.pop("waiting_new_category", None)
    if waiting_action:
        await _handle_new_category_input(update, context, text.strip(), waiting_action)
        return

    urls = URL_PATTERN.findall(text)

    if not urls:
        # No URLs — treat as a free-form question to the knowledge base
        await _handle_question(update, context, text)
        return

    for url in urls:
        source_type = detect_source_type(url)

        if source_type == SourceType.YOUTUBE_VIDEO:
            await _handle_youtube_video(update, context, url)
        elif source_type == SourceType.YOUTUBE_CHANNEL:
            await _handle_youtube_channel(update, context, url)
        else:
            await _handle_web_article(update, context, url)


async def _handle_youtube_video(
    update: Update, context: ContextTypes.DEFAULT_TYPE, url: str
) -> None:
    msg = await update.message.reply_text("⏳ Обрабатываю видео...")

    result = await asyncio.to_thread(process_youtube_video, url)
    if not result:
        await msg.edit_text("⚠️ Произошла неизвестная ошибка.")
        return

    if "error" in result:
        await msg.edit_text(f"⚠️ {result['error']}")
        return

    topics_str = " ".join(f"#{t}" for t in result.get("topics", []))
    bullets = "\n".join(f"• {b}" for b in result.get("summary_bullets", []))
    rel_path = os.path.relpath(result["file_path"], start="/app")

    cat_line = f"📂 Категория: {result['category']}"
    if result.get("is_new_category"):
        cat_line += " 🆕 (новая!)"

    text = (
        f"📺 {result['title']}\n"
        f"by {result['channel']} | {result.get('date', '?')}\n\n"
        f"📋 Саммари:\n{bullets}\n\n"
        f"{cat_line}\n"
        f"🏷 {topics_str}\n"
        f"📊 Релевантность: {result['relevance']}/10\n"
        f"💾 Сохранено: {rel_path}"
    )

    # Store result for potential category change
    context.user_data["last_result"] = result

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ OK", callback_data="cat_ok"),
            InlineKeyboardButton("🔄 Изменить", callback_data="cat_change"),
        ]
    ])
    await msg.edit_text(_truncate_message(text), reply_markup=keyboard)


async def _handle_youtube_channel(
    update: Update, context: ContextTypes.DEFAULT_TYPE, url: str
) -> None:
    msg = await update.message.reply_text("⏳ Определяю канал...")

    channel_id, channel_name = resolve_channel_id(url)
    if not channel_id:
        await msg.edit_text("⚠️ Не удалось определить канал по ссылке.")
        return

    # Check if already monitored
    channels = load_channels()
    for ch in channels:
        if ch["id"] == channel_id:
            await msg.edit_text(f"📡 Канал {channel_name} уже отслеживается.")
            return

    context.user_data["pending_channel"] = {
        "name": channel_name,
        "id": channel_id,
    }

    keyboard = _category_keyboard("add_channel")
    await msg.edit_text(
        f"📡 Канал: {channel_name}\n"
        "Добавить в мониторинг?\n\n"
        "Выбери категорию:",
        reply_markup=keyboard,
    )


async def _handle_web_article(
    update: Update, context: ContextTypes.DEFAULT_TYPE, url: str
) -> None:
    msg = await update.message.reply_text("⏳ Читаю статью...")

    result = await asyncio.to_thread(process_web_article, url)
    if not result:
        await msg.edit_text("⚠️ Произошла неизвестная ошибка.")
        return

    if "error" in result:
        await msg.edit_text(f"⚠️ {result['error']}")
        return

    topics_str = " ".join(f"#{t}" for t in result.get("topics", []))
    bullets = "\n".join(f"• {b}" for b in result.get("summary_bullets", []))
    rel_path = os.path.relpath(result["file_path"], start="/app")

    source_line = result.get("sitename") or result.get("source_name", "")
    date_line = result.get("date", "?")

    cat_line = f"📂 Категория: {result['category']}"
    if result.get("is_new_category"):
        cat_line += " 🆕 (новая!)"

    text = (
        f"📰 {result['title']}\n"
        f"{source_line} | {date_line}\n\n"
        f"📋 Саммари:\n{bullets}\n\n"
        f"{cat_line}\n"
        f"🏷 {topics_str}\n"
        f"📊 Релевантность: {result['relevance']}/10\n"
        f"💾 Сохранено: {rel_path}"
    )

    context.user_data["last_result"] = result

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ OK", callback_data="cat_ok"),
            InlineKeyboardButton("🔄 Изменить", callback_data="cat_change"),
        ]
    ])
    await msg.edit_text(_truncate_message(text), reply_markup=keyboard)


# ── Question handler ──────────────────────────────────────────────────────────

async def _handle_question(
    update: Update, context: ContextTypes.DEFAULT_TYPE, question: str
) -> None:
    """Answer a free-form question using the knowledge base."""
    msg = await update.message.reply_text("🔍 Ищу в базе знаний...")

    sources = search_for_question(question, max_files=5)

    if not sources:
        await msg.edit_text(
            "🤷 По этой теме пока ничего не собрано.\n"
            "Попробуй уточнить запрос или скинь мне ссылку на материал по этой теме."
        )
        return

    answer = answer_question(question, sources)

    if not answer:
        await msg.edit_text("⚠️ Не удалось сформировать ответ. Попробуй позже.")
        return

    # Build sources footer
    source_lines: list[str] = []
    for i, src in enumerate(sources, 1):
        type_icon = "📺" if src.get("type") == "youtube_video" else "📰"
        title = src.get("title", "?")
        source_name = src.get("source", src.get("sitename", "?"))
        date = src.get("date", "?")
        source_lines.append(f"{i}. {type_icon} {title} — {source_name}, {date}")

    text = (
        f"🧠 На основе {len(sources)} источников:\n\n"
        f"{answer}\n\n"
        f"📚 Источники:\n" + "\n".join(source_lines)
    )

    await msg.edit_text(_truncate_message(text))


# ── New category input handler ───────────────────────────────────────────────

async def _handle_new_category_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, action: str
) -> None:
    """Process user input for a new category slug."""
    parts = text.split(maxsplit=1)
    slug = parts[0].lower().strip()
    description = parts[1].strip() if len(parts) > 1 else slug.replace("-", " ").title()

    # Validate slug
    clean_slug = re.sub(r"[^a-z0-9-]", "", slug)
    if not clean_slug or len(clean_slug) > 30:
        await update.message.reply_text("⚠️ Некорректный slug. Используй латиницу, цифры и дефис (до 30 символов).")
        context.user_data["waiting_new_category"] = action
        return

    add_category(clean_slug, description)

    if action == "add_channel":
        pending = context.user_data.get("pending_channel")
        if not pending:
            await update.message.reply_text(f"✅ Категория `{clean_slug}` создана, но данные канала потеряны. Попробуй /add ещё раз.")
            return
        channels = load_channels()
        channels.append({
            "name": pending["name"],
            "id": pending["id"],
            "category": clean_slug,
            "enabled": True,
        })
        save_channels(channels)
        context.user_data.pop("pending_channel", None)
        await update.message.reply_text(
            f"✅ Категория `{clean_slug}` создана.\n"
            f"✅ Канал {pending['name']} добавлен.\n\n"
            "Загрузить последние 3 видео?",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Да", callback_data=f"fetch_recent:{pending['id']}:{clean_slug}"),
                    InlineKeyboardButton("❌ Нет", callback_data="fetch_skip"),
                ]
            ]),
        )
    elif action == "recat":
        await update.message.reply_text(
            f"✅ Категория `{clean_slug}` создана и применена.\n"
            "(Файл будет перемещён при следующей обработке)"
        )


# ── Inline keyboard callbacks ────────────────────────────────────────────────

def _category_keyboard(prefix: str) -> InlineKeyboardMarkup:
    """Build a grid of category buttons with a '+ Новая' option."""
    categories = load_categories()
    buttons = []
    row: list[InlineKeyboardButton] = []
    for slug in categories:
        row.append(InlineKeyboardButton(slug, callback_data=f"{prefix}:{slug}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("➕ Новая категория", callback_data=f"{prefix}:__new__")])
    return InlineKeyboardMarkup(buttons)


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard button presses."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data = query.data

    if data == "cat_ok":
        # User confirmed category — register if new
        last = context.user_data.get("last_result", {})
        if last.get("is_new_category"):
            cat = last["category"]
            add_category(cat, cat.replace("-", " ").title())
        await query.edit_message_reply_markup(reply_markup=None)

    elif data == "cat_change":
        # Show category selection
        keyboard = _category_keyboard("recat")
        await query.edit_message_reply_markup(reply_markup=keyboard)

    elif data.startswith("add_channel:__new__") or data.startswith("recat:__new__"):
        # User wants to create a new category — ask for slug
        action = "add_channel" if data.startswith("add_channel") else "recat"
        context.user_data["waiting_new_category"] = action
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "✏️ Введи slug новой категории (например: `machine-learning`).\n"
            "Можно через пробел добавить описание:\n"
            "`machine-learning Machine Learning & Deep Learning`"
        )

    elif data.startswith("recat:"):
        new_category = data.split(":", 1)[1]
        last = context.user_data.get("last_result", {})
        old_path = last.get("file_path")
        await query.edit_message_reply_markup(reply_markup=None)
        if old_path:
            new_path = move_entry(old_path, new_category)
            if new_path:
                await query.message.reply_text(f"📂 Категория изменена на: {new_category}\n💾 Файл перемещён.")
            else:
                await query.message.reply_text(f"📂 Категория: {new_category}\n⚠️ Файл не найден для перемещения.")
        else:
            await query.message.reply_text(f"📂 Категория изменена на: {new_category}")

    elif data.startswith("add_channel:"):
        category = data.split(":", 1)[1]
        pending = context.user_data.get("pending_channel")
        if not pending:
            await query.message.reply_text("⚠️ Данные канала потеряны, попробуйте ещё раз.")
            return

        channels = load_channels()
        channels.append({
            "name": pending["name"],
            "id": pending["id"],
            "category": category,
            "enabled": True,
        })
        save_channels(channels)

        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            f"✅ Канал {pending['name']} добавлен в категорию {category}.\n\n"
            "Загрузить последние 3 видео?",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Да", callback_data=f"fetch_recent:{pending['id']}:{category}"),
                    InlineKeyboardButton("❌ Нет", callback_data="fetch_skip"),
                ]
            ]),
        )
        context.user_data.pop("pending_channel", None)

    elif data.startswith("fetch_recent:"):
        parts = data.split(":", 2)
        channel_id = parts[1]
        category = parts[2]

        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("⏳ Загружаю последние видео...")

        video_ids = await asyncio.to_thread(get_recent_video_ids, channel_id, 3)
        processed = 0
        for vid in video_ids:
            url = f"https://www.youtube.com/watch?v={vid}"
            result = await asyncio.to_thread(process_youtube_video, url, category)
            if result and "error" not in result:
                processed += 1

        await query.message.reply_text(f"✅ Обработано {processed} из {len(video_ids)} видео.")

    elif data == "fetch_skip":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("👌 Хорошо, видео не загружены.")


# ── Notification helper ──────────────────────────────────────────────────────

async def send_notification(app: Application, result: dict[str, Any]) -> None:
    """Send a processed entry notification to the configured chat."""
    if result.get("source_type") == "youtube_video":
        topics_str = " ".join(f"#{t}" for t in result.get("topics", []))
        bullets = "\n".join(f"• {b}" for b in result.get("summary_bullets", []))

        text = (
            f"📺 {result.get('channel', '?')}\n"
            f"{result['title']}\n\n"
            f"📋 Саммари:\n{bullets}\n\n"
            f"🏷 {topics_str}\n"
            f"📊 Релевантность: {result.get('relevance', '?')}/10\n"
            f"🔗 {result.get('source_url', '')}"
        )
    else:
        topics_str = " ".join(f"#{t}" for t in result.get("topics", []))
        bullets = "\n".join(f"• {b}" for b in result.get("summary_bullets", []))

        text = (
            f"📰 {result['title']}\n"
            f"{result.get('sitename', result.get('source_name', '?'))}\n\n"
            f"📋 Саммари:\n{bullets}\n\n"
            f"🏷 {topics_str}\n"
            f"📊 Релевантность: {result.get('relevance', '?')}/10\n"
            f"🔗 {result.get('source_url', '')}"
        )

    await app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=_truncate_message(text))


async def send_error_notification(app: Application, title: str, error: str) -> None:
    """Send error notification to the configured chat."""
    await app.bot.send_message(
        chat_id=TELEGRAM_CHAT_ID,
        text=f"⚠️ Ошибка при обработке:\n{title}\n{error}",
    )


# ── Bot setup ────────────────────────────────────────────────────────────────

def create_bot_application(post_init=None) -> Application:
    """Create and configure the Telegram bot application."""
    builder = Application.builder().token(TELEGRAM_BOT_TOKEN)
    if post_init is not None:
        builder = builder.post_init(post_init)
    app = builder.build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("remove", cmd_remove))
    app.add_handler(CommandHandler("categories", cmd_categories))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(CommandHandler("recent", cmd_recent))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("run", cmd_run))

    # Inline keyboard callbacks
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Generic message handler (link detection) — must be last
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app
