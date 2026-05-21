"""Entry point: start Telegram bot + scheduler (multi-tenant SaaS)."""

from __future__ import annotations

from src.config import (
    ADMIN_CHAT_ID,
    DATA_DIR,
    KNOWLEDGE_DIR,
    OPENROUTER_API_KEY,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_IDS,
    TELEGRAM_CHAT_LABELS,
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
        missing.append("TELEGRAM_CHAT_IDS (admin seed; or legacy TELEGRAM_CHAT_ID)")
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
    logger.info("Starting PulseBrain (multi-tenant SaaS)...")

    _validate_config()
    _ensure_directories()

    from src.billing import prune_billing_state
    from src.migration import grandfather_allowlisted_users, migrate_legacy_to_admin
    from src.pending import init_pending, prune_pending_state
    from src.profile import init_profile, prune_profile_state
    from src.registry import all_user_ids, get_user, init_registry, seed_admins
    from src.scheduler import setup_scheduler
    from src.storage import init_processed, prune_storage_state
    from src.telegram_bot import create_bot_application

    # Dynamic registry replaces the static allowlist. The env var
    # TELEGRAM_CHAT_IDS now only seeds admin accounts.
    init_registry()
    seed_admins(TELEGRAM_CHAT_IDS, TELEGRAM_CHAT_LABELS)

    # One-shot, marker-guarded migrations (idempotent across restarts).
    migrate_legacy_to_admin(ADMIN_CHAT_ID)
    grandfather_allowlisted_users(TELEGRAM_CHAT_IDS)

    user_ids = all_user_ids()

    pruned = (
        prune_category_state(user_ids)
        + prune_storage_state(user_ids)
        + prune_pending_state(user_ids)
        + prune_profile_state(user_ids)
        + prune_billing_state(user_ids)
    )
    if pruned:
        logger.info("Pruned %d stale per-user registry entries", pruned)

    logger.info(
        "Registered users (%d): %s",
        len(user_ids),
        ", ".join(
            f"{(get_user(cid) or {}).get('label') or cid} [{cid}]"
            + (" (admin)" if (get_user(cid) or {}).get("role") == "admin" else "")
            for cid in user_ids
        ),
    )
    for chat_id in user_ids:
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
