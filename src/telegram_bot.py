"""All Telegram bot handlers: commands, link drops, inline keyboards.

Multi-tenant: every handler extracts ``chat_id`` from the update and
passes it explicitly to every downstream module. The allowlist is a
list of ``chat_id``s from the ``TELEGRAM_CHAT_IDS`` env var, not a
single global. Messages from unknown chats are silently dropped with
a warning log line.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from pathlib import Path
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
    TELEGRAM_CHAT_IDS,
    add_category,
    load_categories,
    load_channels,
    save_channels,
)
from src.extractors.youtube import get_recent_video_ids, resolve_channel_id
from src.onboarding import (
    CALLBACK_STEPS,
    OPTIONAL_STEPS,
    STEPS,
    apply_draft,
    new_draft,
    next_step,
    parse_multiline,
    step_key,
)
from src.onboarding_presets import PRESET_CATEGORIES, PRESET_CHANNELS
from src.pending import (
    commit_pending,
    get_pending,
    list_pending,
    read_rejected_log,
    reject_pending,
    update_pending_category,
)
from src.pipeline import process_web_article, process_youtube_video
from src.profile import get_language, profile_exists
from src.router import SourceType, detect_source_type
from src.storage import (
    find_entry_by_id,
    get_entries_in_category,
    get_recent_entries,
    get_source_text_path,
    get_stats,
    read_entry_markdown,
    search_for_question,
    search_knowledge,
)
from src.strings import t
from src.summarize import answer_question

logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(r"https?://\S+")
_TELEGRAM_MSG_LIMIT = 4096


def _truncate_message(text: str, limit: int = _TELEGRAM_MSG_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _split_long_message(text: str, limit: int = _TELEGRAM_MSG_LIMIT - 20) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        split_at = remaining.rfind("\n\n", 0, limit)
        if split_at == -1:
            split_at = remaining.rfind("\n", 0, limit)
        if split_at == -1 or split_at == 0:
            split_at = limit
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


_SOURCE_ICONS: dict[str, str] = {
    "youtube_video": "📺",
    "web_article": "📰",
}


def _render_pending_message(chat_id: int, entry: dict[str, Any]) -> str:
    lang = get_language(chat_id)
    icon = _SOURCE_ICONS.get(entry.get("source_type", ""), "📄")
    title = entry.get("title", "?")
    date = entry.get("date_str") or "?"

    if entry.get("source_type") == "youtube_video":
        source_line = f"by {entry.get('source_name', '?')} | {date}"
    else:
        source_line = f"{entry.get('sitename') or entry.get('source_name', '?')} | {date}"

    bullets = "\n".join(f"• {b}" for b in entry.get("summary_bullets", []))
    topics_str = " ".join(f"#{tp}" for tp in entry.get("topics", []))

    cat_marker = t("pending_new_cat_marker", lang) if entry.get("is_new_category") else ""
    cat_line = (
        f"📂 {t('pending_category_label', lang)}: "
        f"{entry.get('category', '?')}{cat_marker}"
    )

    source_url = entry.get("source_url", "")
    url_line = f"🔗 {source_url}\n" if source_url else ""

    return (
        f"{icon} {title}\n"
        f"{source_line}\n"
        f"{url_line}\n"
        f"📋 {t('pending_summary_label', lang)}:\n{bullets}\n\n"
        f"{cat_line}\n"
        f"🏷 {topics_str}\n"
        f"📊 {t('pending_relevance_label', lang)}: "
        f"{entry.get('relevance', '?')}/10\n"
        f"{t('pending_awaiting_label', lang)}"
    )


def _pending_keyboard(chat_id: int, pending_id: str) -> InlineKeyboardMarkup:
    lang = get_language(chat_id)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("pending_btn_save", lang),
                                 callback_data=f"psave:{pending_id}"),
            InlineKeyboardButton(t("pending_btn_reject", lang),
                                 callback_data=f"pskip:{pending_id}"),
        ],
        [
            InlineKeyboardButton(t("pending_btn_category", lang),
                                 callback_data=f"pcat:{pending_id}"),
        ],
    ])


def _pending_category_keyboard(chat_id: int, pending_id: str) -> InlineKeyboardMarkup:
    lang = get_language(chat_id)
    categories = load_categories(chat_id)
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for slug in categories:
        row.append(InlineKeyboardButton(slug, callback_data=f"psetc:{pending_id}:{slug}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton(t("pending_btn_new_category", lang),
                             callback_data=f"psetc:{pending_id}:__new__"),
    ])
    return InlineKeyboardMarkup(buttons)


# ── Security: allowlist filter ──────────────────────────────────────────────

def _authorized(update: Update) -> bool:
    """Only respond to chat_ids present in TELEGRAM_CHAT_IDS."""
    chat_id = update.effective_chat.id if update.effective_chat else 0
    if chat_id not in TELEGRAM_CHAT_IDS:
        logger.warning("Unauthorized access attempt from chat_id=%s", chat_id)
        return False
    return True


def _chat_id(update: Update) -> int:
    """Extract chat_id from the update. Caller should have passed _authorized first."""
    return update.effective_chat.id if update.effective_chat else 0


# ── Command handlers ─────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    chat_id = _chat_id(update)
    if not profile_exists(chat_id):
        await _start_wizard(update, context)
        return
    await update.message.reply_text(t("welcome_returning", get_language(chat_id)))


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    chat_id = _chat_id(update)
    await update.message.reply_text(t("help_text", get_language(chat_id)))


async def cmd_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    chat_id = _chat_id(update)
    await update.message.reply_text(
        t("language_menu_prompt", get_language(chat_id)),
        reply_markup=_language_keyboard(),
    )


async def cmd_onboarding(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    chat_id = _chat_id(update)
    if profile_exists(chat_id):
        lang = get_language(chat_id)
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton(t("onboarding_rerun_yes", lang), callback_data="onb:rerun:yes"),
            InlineKeyboardButton(t("onboarding_rerun_no", lang), callback_data="onb:rerun:no"),
        ]])
        await update.message.reply_text(
            t("onboarding_confirm_rerun", lang),
            reply_markup=kb,
        )
        return
    await _start_wizard(update, context)


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    chat_id = _chat_id(update)
    lang = get_language(chat_id)
    flow_keys = ("pending_channel", "waiting_new_category",
                 "onboarding_step", "onboarding_draft")
    wiped = False
    for key in flow_keys:
        if context.user_data.pop(key, None) is not None:
            wiped = True
    if wiped:
        await update.message.reply_text(t("cancel_confirmed", lang))
    else:
        await update.message.reply_text(t("cancel_nothing_to_cancel", lang))


# ── Onboarding wizard helpers ───────────────────────────────────────────────


def _build_language_grid(callback_prefix: str) -> InlineKeyboardMarkup:
    from src.strings import LANGUAGE_FLAGS, LANGUAGE_NATIVE_NAMES, SUPPORTED_LANGS

    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for code in SUPPORTED_LANGS:
        label = f"{LANGUAGE_FLAGS[code]} {LANGUAGE_NATIVE_NAMES[code]}"
        row.append(InlineKeyboardButton(label, callback_data=f"{callback_prefix}:{code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def _language_keyboard() -> InlineKeyboardMarkup:
    return _build_language_grid("lang")


def _wizard_lang_keyboard() -> InlineKeyboardMarkup:
    return _build_language_grid("onb:lang")


def _wizard_skip_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(t("wizard_skip_button", lang), callback_data="onb:skip"),
    ]])


def _wizard_start_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(t("wizard_start_button", lang), callback_data="onb:next"),
    ]])


def _wizard_category_keyboard(draft: dict[str, Any], lang: str) -> InlineKeyboardMarkup:
    selected = draft.get("selected_categories", {})
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for slug in PRESET_CATEGORIES:
        mark = "✓ " if slug in selected else ""
        row.append(InlineKeyboardButton(
            f"{mark}{slug}",
            callback_data=f"onb:cat:{slug}",
        ))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(
        t("wizard_done_button", lang),
        callback_data="onb:done",
    )])
    return InlineKeyboardMarkup(rows)


def _wizard_channel_keyboard(draft: dict[str, Any], lang: str) -> InlineKeyboardMarkup:
    selected_ids = {ch.get("id") for ch in draft.get("selected_channels", [])}
    rows: list[list[InlineKeyboardButton]] = []
    for idx, ch in enumerate(PRESET_CHANNELS):
        mark = "✓ " if ch.get("id") in selected_ids else ""
        label = f"{mark}{ch.get('name', '?')} ({ch.get('category', '?')})"
        rows.append([InlineKeyboardButton(label, callback_data=f"onb:ch:{idx}")])
    rows.append([InlineKeyboardButton(
        t("wizard_done_button", lang),
        callback_data="onb:done",
    )])
    return InlineKeyboardMarkup(rows)


async def _start_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from src.strings import SUPPORTED_LANGS

    context.user_data["onboarding_step"] = 0
    draft = new_draft()

    hint = ""
    user = getattr(update, "effective_user", None)
    if user is not None:
        hint = (getattr(user, "language_code", "") or "").split("-")[0].lower()
    if hint in SUPPORTED_LANGS:
        draft["language"] = hint
    else:
        draft["language"] = "en"

    context.user_data["onboarding_draft"] = draft

    intro_lang = draft["language"]
    text = (
        t("welcome_first_run", intro_lang)
        + "\n\n"
        + t("wizard_lang_prompt", intro_lang)
    )
    await update.message.reply_text(text, reply_markup=_wizard_lang_keyboard())


async def _send_wizard_step(send, *, step_index: int, draft: dict[str, Any]) -> None:
    key = step_key(step_index)
    if key is None:
        return
    lang = draft.get("language", "en")

    if key == "welcome":
        await send(t("wizard_welcome_body", lang), reply_markup=_wizard_start_keyboard(lang))
    elif key == "persona":
        await send(t("wizard_persona_prompt", lang))
    elif key == "learning":
        await send(t("wizard_learning_prompt", lang))
    elif key == "stack":
        await send(t("wizard_stack_prompt", lang))
    elif key == "notinterested":
        await send(t("wizard_notinterested_prompt", lang), reply_markup=_wizard_skip_keyboard(lang))
    elif key == "categories":
        await send(t("wizard_categories_prompt", lang), reply_markup=_wizard_category_keyboard(draft, lang))
    elif key == "channels":
        if not PRESET_CHANNELS:
            await send(t("wizard_channels_empty", lang))
            return
        await send(t("wizard_channels_prompt", lang), reply_markup=_wizard_channel_keyboard(draft, lang))
    elif key == "done":
        await send(t("wizard_done", lang))


async def _advance_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE, send) -> None:
    chat_id = _chat_id(update)
    step_index = context.user_data.get("onboarding_step", 0)
    draft = context.user_data.get("onboarding_draft") or new_draft()

    new_index = next_step(step_index)
    context.user_data["onboarding_step"] = new_index

    key = step_key(new_index)

    if key == "channels" and not PRESET_CHANNELS:
        await _send_wizard_step(send, step_index=new_index, draft=draft)
        new_index = next_step(new_index)
        context.user_data["onboarding_step"] = new_index
        key = step_key(new_index)

    if key == "done":
        try:
            apply_draft(chat_id, draft)
        except Exception as exc:
            logger.error("Failed to apply onboarding draft: %s", exc)
        await _send_wizard_step(send, step_index=new_index, draft=draft)
        context.user_data.pop("onboarding_step", None)
        context.user_data.pop("onboarding_draft", None)
        return

    await _send_wizard_step(send, step_index=new_index, draft=draft)


async def _handle_onboarding_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    chat_id = _chat_id(update)
    query = update.callback_query

    if data.startswith("onb:rerun:"):
        choice = data.split(":", 2)[2]
        if choice == "no":
            await query.edit_message_text(t("onboarding_kept_existing", get_language(chat_id)))
            return
        await query.edit_message_reply_markup(reply_markup=None)

        class _ShimUpdate:
            def __init__(self, q, orig):
                self.message = q.message
                self.effective_chat = orig.effective_chat
                self.effective_user = orig.effective_user
        await _start_wizard(_ShimUpdate(query, update), context)
        return

    if context.user_data.get("onboarding_step") is None:
        await query.edit_message_reply_markup(reply_markup=None)
        return

    draft = context.user_data.get("onboarding_draft") or new_draft()

    if data.startswith("onb:lang:"):
        from src.strings import SUPPORTED_LANGS
        code = data.split(":", 2)[2]
        if code not in SUPPORTED_LANGS:
            return
        draft["language"] = code
        context.user_data["onboarding_draft"] = draft
        await query.edit_message_text(t("wizard_lang_saved", code))
        await _advance_wizard(update, context, query.message.reply_text)
        return

    if data == "onb:skip":
        current_key = step_key(context.user_data["onboarding_step"])
        if current_key in OPTIONAL_STEPS:
            await query.edit_message_reply_markup(reply_markup=None)
            await _advance_wizard(update, context, query.message.reply_text)
        return

    if data == "onb:next":
        await query.edit_message_reply_markup(reply_markup=None)
        await _advance_wizard(update, context, query.message.reply_text)
        return

    if data.startswith("onb:cat:"):
        slug = data.split(":", 2)[2]
        if slug not in PRESET_CATEGORIES:
            return
        selected = draft.setdefault("selected_categories", {})
        if slug in selected:
            del selected[slug]
        else:
            selected[slug] = PRESET_CATEGORIES[slug]
        context.user_data["onboarding_draft"] = draft
        await query.edit_message_reply_markup(
            reply_markup=_wizard_category_keyboard(draft, draft.get("language", "en"))
        )
        return

    if data.startswith("onb:ch:"):
        try:
            idx = int(data.split(":", 2)[2])
        except ValueError:
            return
        if not (0 <= idx < len(PRESET_CHANNELS)):
            return
        channel = PRESET_CHANNELS[idx]
        selected = draft.setdefault("selected_channels", [])
        existing_ids = {ch.get("id") for ch in selected}
        if channel.get("id") in existing_ids:
            draft["selected_channels"] = [
                ch for ch in selected if ch.get("id") != channel.get("id")
            ]
        else:
            selected.append(channel)
        context.user_data["onboarding_draft"] = draft
        await query.edit_message_reply_markup(
            reply_markup=_wizard_channel_keyboard(draft, draft.get("language", "en"))
        )
        return

    if data == "onb:done":
        await query.edit_message_reply_markup(reply_markup=None)
        await _advance_wizard(update, context, query.message.reply_text)
        return


async def _handle_wizard_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    step_index = context.user_data.get("onboarding_step", 0)
    draft = context.user_data.get("onboarding_draft") or new_draft()
    key = step_key(step_index)

    if key == "persona":
        draft["persona"] = text.strip()
    elif key == "learning":
        draft["actively_learning"] = parse_multiline(text)
    elif key == "stack":
        items = parse_multiline(text)
        draft["known_stack"] = items
        draft["already_comfortable_with"] = list(items)
    elif key == "notinterested":
        draft["not_interested_in"] = parse_multiline(text)
    else:
        return

    context.user_data["onboarding_draft"] = draft
    await _advance_wizard(update, context, update.message.reply_text)


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    chat_id = _chat_id(update)
    lang = get_language(chat_id)
    channels = load_channels(chat_id)
    if not channels:
        await update.message.reply_text(t("list_empty", lang))
        return

    lines = [t("list_header", lang)]
    for ch in channels:
        status = "✅" if ch.get("enabled", True) else "⏸"
        lines.append(f"{status} {ch['name']} — {ch.get('category', '?')}")

    await update.message.reply_text("\n".join(lines))


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    chat_id = _chat_id(update)
    lang = get_language(chat_id)
    args = context.args or []
    if not args:
        await update.message.reply_text(t("add_usage", lang))
        return

    url = args[0]
    category = args[1] if len(args) > 1 else None

    await update.message.reply_text(t("add_resolving", lang))

    channel_id, channel_name = resolve_channel_id(url)
    if not channel_id:
        await update.message.reply_text(t("add_resolve_failed", lang))
        return

    channels = load_channels(chat_id)
    for ch in channels:
        if ch["id"] == channel_id:
            await update.message.reply_text(
                t("add_already_tracked", lang, name=channel_name)
            )
            return

    if category:
        channels.append({
            "name": channel_name,
            "id": channel_id,
            "category": category,
            "enabled": True,
        })
        save_channels(chat_id, channels)
        await update.message.reply_text(
            t("add_added_to_category", lang, name=channel_name, category=category)
        )
    else:
        context.user_data["pending_channel"] = {
            "name": channel_name,
            "id": channel_id,
        }
        keyboard = _category_keyboard(chat_id, "add_channel")
        await update.message.reply_text(
            t("add_pick_category", lang, name=channel_name),
            reply_markup=keyboard,
        )


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    chat_id = _chat_id(update)
    lang = get_language(chat_id)
    args = context.args or []
    if not args:
        await update.message.reply_text(t("remove_usage", lang))
        return

    name_query = " ".join(args).lower()
    channels = load_channels(chat_id)
    found = False
    for ch in channels:
        if ch["name"].lower() == name_query or name_query in ch["name"].lower():
            ch["enabled"] = False
            found = True
            save_channels(chat_id, channels)
            await update.message.reply_text(
                t("remove_disabled", lang, name=ch["name"])
            )
            break

    if not found:
        await update.message.reply_text(
            t("remove_not_found", lang, name=name_query)
        )


async def cmd_categories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    chat_id = _chat_id(update)
    lang = get_language(chat_id)
    stats = get_stats(chat_id)
    health = stats.get("category_health", {})

    if not health:
        await update.message.reply_text(t("categories_empty", lang))
        return

    lines = [t("categories_header", lang)]
    for cat in stats["by_category"]:
        info = health.get(cat, {})
        count = info.get("count", 0)
        last_entry = info.get("last_entry") or "?"
        avg = info.get("avg_relevance", 0)
        stale = info.get("stale", False)

        marker = "⚠" if stale else "✅"
        suffix = t("categories_stale_marker", lang) if stale else ""
        count_str = t("categories_entry_count", lang, count=count)
        lines.append(
            f"{marker} {cat} ({count_str}){suffix}\n"
            + t("categories_item_line", lang, avg=avg, last=last_entry)
        )

    await update.message.reply_text("\n".join(lines))


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    chat_id = _chat_id(update)
    lang = get_language(chat_id)
    args = context.args or []
    if not args:
        await update.message.reply_text(t("search_usage", lang))
        return

    query = " ".join(args)
    results = search_knowledge(chat_id, query)

    if not results:
        await update.message.reply_text(t("search_nothing", lang, query=query))
        return

    lines = [t("search_found_header", lang, count=len(results), query=query)]
    for i, r in enumerate(results[:5], 1):
        type_icon = "📺" if r.get("type") == "youtube_video" else "📰"
        url_line = f"   🔗 {r['source_url']}" if r.get("source_url") else ""
        lines.append(
            f"{i}. {type_icon} {r.get('title', '?')}\n"
            f"   {r.get('source', '?')} | {r.get('date', '?')} | "
            f"{r.get('category', '?')} | ⭐ {r.get('relevance', '?')}/10"
            + (f"\n{url_line}" if url_line else "")
        )
        if r.get("summary_preview"):
            lines.append(f"   {r['summary_preview'][:100]}")
        lines.append("")

    lines.append(t("recent_get_hint", lang))

    await update.message.reply_text("\n".join(lines))


async def cmd_recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    chat_id = _chat_id(update)
    lang = get_language(chat_id)
    args = context.args or []
    count = int(args[0]) if args and args[0].isdigit() else 5

    entries = get_recent_entries(chat_id, count)
    if not entries:
        await update.message.reply_text(t("recent_empty", lang))
        return

    lines = [t("recent_header", lang, count=len(entries))]
    for e in entries:
        type_icon = "📺" if e.get("type") == "youtube_video" else "📰"
        url_line = f"   🔗 {e['source_url']}" if e.get("source_url") else ""
        lines.append(
            f"{type_icon} {e.get('title', '?')}\n"
            f"   {e.get('source', '?')} | {e.get('date', '?')} | {e.get('category', '?')}"
            + (f"\n{url_line}" if url_line else "")
        )
    lines.append("")
    lines.append(t("recent_get_hint", lang))

    await update.message.reply_text("\n".join(lines))


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    chat_id = _chat_id(update)
    lang = get_language(chat_id)
    stats = get_stats(chat_id)
    channels = load_channels(chat_id)
    active = sum(1 for ch in channels if ch.get("enabled", True))

    await update.message.reply_text(
        "🤖 PulseBrain Status\n\n"
        + t(
            "status_body",
            lang,
            total=stats["total"],
            videos=stats["videos"],
            articles=stats["articles"],
            active=active,
            all=len(channels),
            avg=stats["avg_relevance"],
            this_week=stats["this_week"],
        )
    )


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    chat_id = _chat_id(update)
    stats = get_stats(chat_id)

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
    """Force a pipeline run for this user's enabled channels."""
    if not _authorized(update):
        return
    chat_id = _chat_id(update)
    lang = get_language(chat_id)
    await update.message.reply_text(t("run_starting", lang))

    from src.scheduler import run_channel_check

    results = await run_channel_check(chat_id, app=context.application)
    if results:
        await update.message.reply_text(t("run_processed", lang, count=results))
    else:
        await update.message.reply_text(t("run_nothing", lang))


async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    chat_id = _chat_id(update)
    lang = get_language(chat_id)
    entries = list_pending(chat_id)
    if not entries:
        await update.message.reply_text(t("pending_queue_empty", lang))
        return

    await update.message.reply_text(
        t("pending_queue_header", lang, count=len(entries))
    )
    for entry in entries[:10]:
        await update.message.reply_text(
            _truncate_message(_render_pending_message(chat_id, entry)),
            reply_markup=_pending_keyboard(chat_id, entry["id"]),
        )


_REJECT_REASON_KEYS: dict[str, str] = {
    "low_relevance": "reject_reason_low_relevance",
    "manual": "reject_reason_manual",
}


async def cmd_rejected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    chat_id = _chat_id(update)
    lang = get_language(chat_id)
    args = context.args or []
    try:
        limit = int(args[0]) if args else 10
    except ValueError:
        limit = 10
    limit = max(1, min(limit, 50))

    records = read_rejected_log(chat_id, limit)
    if not records:
        await update.message.reply_text(t("rejected_empty", lang))
        return

    lines = [t("rejected_header", lang, count=len(records))]
    rel_label = t("pending_relevance_label", lang).lower()
    for rec in records:
        icon = _SOURCE_ICONS.get(rec.get("source_type", ""), "📄")
        title = rec.get("title", "?")
        source = rec.get("source_name", "?")
        score = rec.get("relevance", "?")
        reason_key = rec.get("reason", "manual")
        reason_catalog_key = _REJECT_REASON_KEYS.get(reason_key)
        reason = t(reason_catalog_key, lang) if reason_catalog_key else reason_key
        lines.append(
            f"{icon} {title}\n"
            f"    {rel_label} {score}/10 · {source} · {reason}"
        )

    await update.message.reply_text(_truncate_message("\n".join(lines)))


# ── Entry detail / file access (/get command) ───────────────────────────────

def _strip_frontmatter(md_content: str) -> str:
    marker = md_content.find("\n## ")
    if marker == -1:
        return md_content
    return md_content[marker + 1:]


def _render_entry_detail(chat_id: int, entry: dict[str, Any], body: str) -> str:
    lang = get_language(chat_id)
    icon = _SOURCE_ICONS.get(entry.get("type", ""), "📄")
    lines = [
        f"{icon} {entry.get('title', '?')}",
        "",
        f"🔗 {entry.get('source_url', '?')}",
        f"📂 {t('pending_category_label', lang)}: {entry.get('category', '?')}",
        f"📅 {entry.get('date', '?')} · "
        f"⭐ {entry.get('relevance', '?')}/10",
    ]
    topics = entry.get("topics", "")
    if topics:
        lines.append(f"🏷 {topics}")
    lines.append("")
    lines.append(body)
    return "\n".join(lines)


def _entry_files_keyboard(chat_id: int, entry_data_id: str) -> InlineKeyboardMarkup:
    lang = get_language(chat_id)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                t("entry_btn_md_file", lang),
                callback_data=f"entfile:md:{entry_data_id}",
            ),
            InlineKeyboardButton(
                t("entry_btn_raw_file", lang),
                callback_data=f"entfile:raw:{entry_data_id}",
            ),
        ]
    ])


def _categories_browse_keyboard(by_category: dict[str, int]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for slug, count in by_category.items():
        row.append(
            InlineKeyboardButton(
                f"{slug} ({count})",
                callback_data=f"getcat:{slug}",
            )
        )
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(rows)


def _entries_browse_keyboard(entries: list[dict[str, str]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for entry in entries:
        title = entry.get("title", "?") or "?"
        label = (title[:57] + "…") if len(title) > 60 else title
        rows.append(
            [
                InlineKeyboardButton(
                    label,
                    callback_data=f"getent:{entry['id']}",
                )
            ]
        )
    return InlineKeyboardMarkup(rows)


async def _send_categories_list(chat_id: int, update: Update, lang: str) -> None:
    stats = get_stats(chat_id)
    by_category = stats.get("by_category") or {}
    if not by_category:
        await update.message.reply_text(t("get_empty_base", lang))
        return
    await update.message.reply_text(
        t("get_pick_category", lang),
        reply_markup=_categories_browse_keyboard(by_category),
    )


async def _send_entry_detail(chat_id: int, send_reply: Any, entry: dict[str, str], lang: str) -> None:
    try:
        raw_md = await asyncio.to_thread(read_entry_markdown, entry["path"])
    except OSError as exc:
        logger.warning("Failed to read %s: %s", entry["path"], exc)
        await send_reply(t("get_read_failed", lang))
        return

    body = _strip_frontmatter(raw_md).strip()
    text = _render_entry_detail(chat_id, entry, body)

    keyboard = _entry_files_keyboard(chat_id, entry["id"])

    chunks = _split_long_message(text)
    total = len(chunks)
    for index, chunk in enumerate(chunks):
        prefix = f"({index + 1}/{total}) " if total > 1 else ""
        is_last = index == total - 1
        await send_reply(
            prefix + chunk,
            reply_markup=keyboard if is_last else None,
            disable_web_page_preview=True,
        )


async def cmd_get(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    chat_id = _chat_id(update)
    lang = get_language(chat_id)
    args = context.args or []
    if not args:
        await _send_categories_list(chat_id, update, lang)
        return

    wanted_id = args[0].strip().lower()
    entry = find_entry_by_id(chat_id, wanted_id)
    if entry is None:
        await update.message.reply_text(t("get_not_found", lang, entry_id=wanted_id))
        return

    await _send_entry_detail(chat_id, update.message.reply_text, entry, lang)


# ── Link drop handler ────────────────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    chat_id = _chat_id(update)

    text = update.message.text or ""

    if context.user_data.get("onboarding_step") is not None:
        current_key = step_key(context.user_data["onboarding_step"])
        if current_key is not None and current_key not in CALLBACK_STEPS:
            await _handle_wizard_text(update, context, text)
            return

    waiting_action = context.user_data.pop("waiting_new_category", None)
    if waiting_action:
        await _handle_new_category_input(update, context, text.strip(), waiting_action)
        return

    urls = URL_PATTERN.findall(text)

    if not urls:
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


async def _handle_youtube_video(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str) -> None:
    chat_id = _chat_id(update)
    lang = get_language(chat_id)
    msg = await update.message.reply_text(t("processing_video", lang))

    result = await asyncio.to_thread(process_youtube_video, chat_id, url)
    if not result:
        await msg.edit_text(t("processing_unknown_error", lang))
        return

    if "error" in result:
        await msg.edit_text(f"⚠️ {result['error']}")
        return

    pending_id = result["pending_id"]
    entry = get_pending(chat_id, pending_id)
    if entry is None:
        await msg.edit_text(t("pending_record_gone", lang))
        return

    await msg.edit_text(
        _truncate_message(_render_pending_message(chat_id, entry)),
        reply_markup=_pending_keyboard(chat_id, pending_id),
    )


async def _handle_youtube_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str) -> None:
    chat_id = _chat_id(update)
    lang = get_language(chat_id)
    msg = await update.message.reply_text(t("add_resolving", lang))

    channel_id, channel_name = resolve_channel_id(url)
    if not channel_id:
        await msg.edit_text(t("add_resolve_failed", lang))
        return

    channels = load_channels(chat_id)
    for ch in channels:
        if ch["id"] == channel_id:
            await msg.edit_text(t("add_already_tracked", lang, name=channel_name))
            return

    context.user_data["pending_channel"] = {
        "name": channel_name,
        "id": channel_id,
    }

    keyboard = _category_keyboard(chat_id, "add_channel")
    await msg.edit_text(
        t("channel_add_pick_category", lang, name=channel_name),
        reply_markup=keyboard,
    )


async def _handle_web_article(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str) -> None:
    chat_id = _chat_id(update)
    lang = get_language(chat_id)
    msg = await update.message.reply_text(t("processing_article", lang))

    result = await asyncio.to_thread(process_web_article, chat_id, url)
    if not result:
        await msg.edit_text(t("processing_unknown_error", lang))
        return

    if "error" in result:
        await msg.edit_text(f"⚠️ {result['error']}")
        return

    pending_id = result["pending_id"]
    entry = get_pending(chat_id, pending_id)
    if entry is None:
        await msg.edit_text(t("pending_record_gone", lang))
        return

    await msg.edit_text(
        _truncate_message(_render_pending_message(chat_id, entry)),
        reply_markup=_pending_keyboard(chat_id, pending_id),
    )


# ── Question handler ──────────────────────────────────────────────────────────

async def _handle_question(update: Update, context: ContextTypes.DEFAULT_TYPE, question: str) -> None:
    chat_id = _chat_id(update)
    lang = get_language(chat_id)
    msg = await update.message.reply_text(t("qa_searching", lang))

    sources = search_for_question(chat_id, question, max_files=5)

    if not sources:
        await msg.edit_text(t("qa_nothing", lang))
        return

    answer = answer_question(chat_id, question, sources)

    if not answer:
        await msg.edit_text(t("qa_failed", lang))
        return

    source_lines: list[str] = []
    for i, src in enumerate(sources, 1):
        type_icon = "📺" if src.get("type") == "youtube_video" else "📰"
        title = src.get("title", "?")
        source_name = src.get("source", src.get("sitename", "?"))
        date = src.get("date", "?")
        source_lines.append(f"{i}. {type_icon} {title} — {source_name}, {date}")

    text_body = (
        f"{t('qa_answer_header', lang, count=len(sources))}\n\n"
        f"{answer}\n\n"
        f"{t('qa_sources_header', lang)}\n" + "\n".join(source_lines)
    )

    await msg.edit_text(_truncate_message(text_body))


# ── New category input handler ───────────────────────────────────────────────

async def _handle_new_category_input(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, action: str) -> None:
    chat_id = _chat_id(update)
    lang = get_language(chat_id)
    parts = text.split(maxsplit=1)
    slug = parts[0].lower().strip()
    description = parts[1].strip() if len(parts) > 1 else slug.replace("-", " ").title()

    clean_slug = re.sub(r"[^a-z0-9-]", "", slug)
    if not clean_slug or len(clean_slug) > 30:
        await update.message.reply_text(t("new_cat_invalid_slug", lang))
        context.user_data["waiting_new_category"] = action
        return

    add_category(chat_id, clean_slug, description)

    if action == "add_channel":
        pending = context.user_data.get("pending_channel")
        if not pending:
            await update.message.reply_text(
                t("new_cat_created_lost", lang, slug=clean_slug)
            )
            return
        channels = load_channels(chat_id)
        channels.append({
            "name": pending["name"],
            "id": pending["id"],
            "category": clean_slug,
            "enabled": True,
        })
        save_channels(chat_id, channels)
        context.user_data.pop("pending_channel", None)
        await update.message.reply_text(
            t(
                "new_cat_created_channel_added",
                lang,
                slug=clean_slug,
                name=pending["name"],
            ),
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        t("new_cat_btn_yes", lang),
                        callback_data=f"fetch_recent:{pending['id']}:{clean_slug}",
                    ),
                    InlineKeyboardButton(
                        t("new_cat_btn_no", lang),
                        callback_data="fetch_skip",
                    ),
                ]
            ]),
        )
    elif action.startswith("pending:"):
        pending_id = action.split(":", 1)[1]
        if not update_pending_category(chat_id, pending_id, clean_slug, is_new_category=True):
            await update.message.reply_text(
                t("new_cat_created_no_record", lang, slug=clean_slug)
            )
            return
        entry = get_pending(chat_id, pending_id)
        await update.message.reply_text(
            _truncate_message(_render_pending_message(chat_id, entry)),
            reply_markup=_pending_keyboard(chat_id, pending_id),
        )


# ── Inline keyboard callbacks ────────────────────────────────────────────────

def _category_keyboard(chat_id: int, prefix: str) -> InlineKeyboardMarkup:
    lang = get_language(chat_id)
    categories = load_categories(chat_id)
    buttons = []
    row: list[InlineKeyboardButton] = []
    for slug in categories:
        row.append(InlineKeyboardButton(slug, callback_data=f"{prefix}:{slug}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton(
            t("pending_btn_new_category", lang),
            callback_data=f"{prefix}:__new__",
        )
    ])
    return InlineKeyboardMarkup(buttons)


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _authorized(update):
        return
    chat_id = _chat_id(update)
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data = query.data

    if data.startswith("onb:"):
        await _handle_onboarding_callback(update, context, data)
        return

    if data.startswith("lang:"):
        from src.strings import SUPPORTED_LANGS
        code = data.split(":", 1)[1]
        if code not in SUPPORTED_LANGS:
            return
        from src.profile import load_profile, save_profile
        from src.strings import LANGUAGE_NATIVE_NAMES
        profile = load_profile(chat_id)
        profile["language"] = code
        save_profile(chat_id, profile)
        name = LANGUAGE_NATIVE_NAMES[code]
        await query.edit_message_text(t("language_changed", code, name=name))
        return

    lang = get_language(chat_id)
    if data.startswith("psave:"):
        pending_id = data.split(":", 1)[1]
        entry = get_pending(chat_id, pending_id)
        if entry is None:
            await query.edit_message_text(t("pending_record_gone", lang))
            return
        if entry.get("is_new_category"):
            cat = entry["category"]
            add_category(chat_id, cat, cat.replace("-", " ").title())
        file_path = await asyncio.to_thread(commit_pending, chat_id, pending_id)
        if file_path is None:
            await query.edit_message_text(t("pending_save_failed", lang))
            return
        rel_path = os.path.relpath(str(file_path), start="/app")
        await query.edit_message_text(
            _truncate_message(
                _render_pending_message(chat_id, entry)
                + t("pending_saved_suffix", lang, path=rel_path)
            ),
            reply_markup=None,
        )
        return

    if data.startswith("pskip:"):
        pending_id = data.split(":", 1)[1]
        entry = get_pending(chat_id, pending_id)
        if entry is None:
            await query.edit_message_text(t("pending_record_gone", lang))
            return
        reject_pending(chat_id, pending_id)
        await query.edit_message_text(
            _truncate_message(
                _render_pending_message(chat_id, entry)
                + t("pending_rejected_suffix", lang)
            ),
            reply_markup=None,
        )
        return

    if data.startswith("pcat:"):
        pending_id = data.split(":", 1)[1]
        if get_pending(chat_id, pending_id) is None:
            await query.edit_message_text(t("pending_record_gone", lang))
            return
        await query.edit_message_reply_markup(
            reply_markup=_pending_category_keyboard(chat_id, pending_id),
        )
        return

    if data.startswith("psetc:"):
        _, pending_id, slug = data.split(":", 2)
        if slug == "__new__":
            context.user_data["waiting_new_category"] = f"pending:{pending_id}"
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(t("new_cat_prompt", lang))
            return
        if not update_pending_category(chat_id, pending_id, slug):
            await query.edit_message_text(t("pending_record_gone", lang))
            return
        entry = get_pending(chat_id, pending_id)
        await query.edit_message_text(
            _truncate_message(_render_pending_message(chat_id, entry)),
            reply_markup=_pending_keyboard(chat_id, pending_id),
        )
        return

    if data.startswith("add_channel:__new__"):
        context.user_data["waiting_new_category"] = "add_channel"
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(t("new_cat_prompt", lang))
        return

    if data.startswith("add_channel:"):
        category = data.split(":", 1)[1]
        pending = context.user_data.get("pending_channel")
        if not pending:
            await query.message.reply_text(t("channel_data_lost", lang))
            return

        channels = load_channels(chat_id)
        channels.append({
            "name": pending["name"],
            "id": pending["id"],
            "category": category,
            "enabled": True,
        })
        save_channels(chat_id, channels)

        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            t(
                "channel_added_fetch_prompt",
                lang,
                name=pending["name"],
                category=category,
            ),
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(
                        t("new_cat_btn_yes", lang),
                        callback_data=f"fetch_recent:{pending['id']}:{category}",
                    ),
                    InlineKeyboardButton(
                        t("new_cat_btn_no", lang),
                        callback_data="fetch_skip",
                    ),
                ]
            ]),
        )
        context.user_data.pop("pending_channel", None)

    elif data.startswith("fetch_recent:"):
        parts = data.split(":", 2)
        channel_id = parts[1]
        category = parts[2]

        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(t("fetch_starting", lang))

        video_ids = await asyncio.to_thread(get_recent_video_ids, channel_id, 3)
        processed = 0
        for vid in video_ids:
            url = f"https://www.youtube.com/watch?v={vid}"
            result = await asyncio.to_thread(process_youtube_video, chat_id, url, category)
            if result and "error" not in result:
                processed += 1

        await query.message.reply_text(
            t("fetch_processed", lang, done=processed, total=len(video_ids))
        )

    elif data == "fetch_skip":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(t("fetch_skipped", lang))

    elif data.startswith("getcat:"):
        slug = data.split(":", 1)[1]
        entries = get_entries_in_category(chat_id, slug, limit=20)
        if not entries:
            await query.message.reply_text(t("get_category_empty", lang))
            return
        await query.edit_message_text(
            t("get_pick_entry", lang, category=slug, count=len(entries)),
            reply_markup=_entries_browse_keyboard(entries),
        )
        return

    elif data.startswith("getent:"):
        wanted_id = data.split(":", 1)[1]
        entry = find_entry_by_id(chat_id, wanted_id)
        if entry is None:
            await query.message.reply_text(
                t("get_not_found", lang, entry_id=wanted_id)
            )
            return
        await _send_entry_detail(chat_id, query.message.reply_text, entry, lang)
        return

    elif data.startswith("entfile:"):
        parts = data.split(":", 2)
        if len(parts) != 3:
            return
        kind, wanted_id = parts[1], parts[2]
        entry = find_entry_by_id(chat_id, wanted_id)
        if entry is None:
            await query.message.reply_text(
                t("get_not_found", lang, entry_id=wanted_id)
            )
            return

        if kind == "md":
            target_path = Path(entry["path"])
        elif kind == "raw":
            target_path = get_source_text_path(entry["path"])
            if not target_path.exists():
                await query.message.reply_text(t("entry_no_raw_text", lang))
                return
        else:
            return

        try:
            with open(target_path, "rb") as f:
                await query.message.reply_document(
                    document=f,
                    filename=target_path.name,
                    caption=t("entry_file_caption", lang, name=target_path.name),
                )
        except OSError as exc:
            logger.warning("Failed to send %s: %s", target_path, exc)
            await query.message.reply_text(t("get_read_failed", lang))


# ── Notification helpers (scheduler → user) ─────────────────────────────────

async def send_notification(app: Application, chat_id: int, result: dict[str, Any]) -> None:
    """Send a staged-entry notification to ``chat_id``."""
    pending_id = result.get("pending_id")
    if not pending_id:
        return
    entry = get_pending(chat_id, pending_id)
    if entry is None:
        return

    await app.bot.send_message(
        chat_id=chat_id,
        text=_truncate_message(_render_pending_message(chat_id, entry)),
        reply_markup=_pending_keyboard(chat_id, pending_id),
    )


async def send_error_notification(app: Application, chat_id: int, title: str, error: str) -> None:
    """Send an error notification to ``chat_id``."""
    await app.bot.send_message(
        chat_id=chat_id,
        text=t("error_notify_body", get_language(chat_id), title=title, error=error),
    )


# ── Bot setup ────────────────────────────────────────────────────────────────

def create_bot_application(post_init=None) -> Application:
    """Create and configure the Telegram bot application."""
    builder = Application.builder().token(TELEGRAM_BOT_TOKEN)
    if post_init is not None:
        builder = builder.post_init(post_init)
    app = builder.build()

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
    app.add_handler(CommandHandler("pending", cmd_pending))
    app.add_handler(CommandHandler("rejected", cmd_rejected))
    app.add_handler(CommandHandler("get", cmd_get))
    app.add_handler(CommandHandler("onboarding", cmd_onboarding))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("language", cmd_language))

    app.add_handler(CallbackQueryHandler(callback_handler))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app
