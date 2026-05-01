"""Entry point: start Telegram bot + scheduler (multi-tenant)."""

from __future__ import annotations

from src.config import (
    ADMIN_CHAT_ID,
    DATA_DIR,
    KNOWLEDGE_DIR,
    OPENROUTER_API_KEY,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_IDS,
    chat_label,
    ensure_user_dirs,
    logger,
    prune_category_state,
)


def _validate_config() -> None:
    """Ensure required environment variables are set."""
    missing: list[str] = []
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not TELEGRAM_CHAT_IDS:
        missing.append("TELEGRAM_CHAT_IDS (or legacy TELEGRAM_CHAT_ID)")
    if not OPENROUTER_API_KEY:
        missing.append("OPENROUTER_API_KEY")
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}"
        )


def _ensure_directories() -> None:
    """Create knowledge/ and data/ directories if they don't exist."""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    """Start the bot."""
    logger.info("Starting PulseBrain (multi-tenant)...")

    _validate_config()
    _ensure_directories()

    from src.migration import migrate_legacy_to_admin
    from src.pending import init_pending, prune_pending_state
    from src.profile import init_profile, prune_profile_state
    from src.scheduler import setup_scheduler
    from src.storage import init_processed, prune_storage_state
    from src.telegram_bot import create_bot_application

    migrate_legacy_to_admin(ADMIN_CHAT_ID)

    pruned = (
        prune_category_state(TELEGRAM_CHAT_IDS)
        + prune_storage_state(TELEGRAM_CHAT_IDS)
        + prune_pending_state(TELEGRAM_CHAT_IDS)
        + prune_profile_state(TELEGRAM_CHAT_IDS)
    )
    if pruned:
        logger.info("Pruned %d stale per-user registry entries", pruned)

    logger.info(
        "Allowed users (%d): %s",
        len(TELEGRAM_CHAT_IDS),
        ", ".join(
            f"{chat_label(cid)} [{cid}]"
            + (" (admin)" if cid == ADMIN_CHAT_ID else "")
            for cid in TELEGRAM_CHAT_IDS
        ),
    )
    for chat_id in TELEGRAM_CHAT_IDS:
        ensure_user_dirs(chat_id)
        init_processed(chat_id)
        init_pending(chat_id)
        init_profile(chat_id)

    # Scheduler is configured here but started only after the event loop is running
    scheduler_holder: list = []

    async def post_init(application) -> None:
        scheduler = setup_scheduler(application)
        scheduler.start()
        scheduler_holder.append(scheduler)
        logger.info("Scheduler started.")

    app = create_bot_application(post_init=post_init)

    logger.info("Bot is running. Waiting for messages...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
