"""Tests for the Telegram Stars payment flow + self-serve registration."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _precheckout_update(chat_id: int, payload: str):
    update = MagicMock()
    update.effective_chat.id = chat_id
    query = MagicMock()
    query.invoice_payload = payload
    query.from_user.id = chat_id
    query.answer = AsyncMock()
    update.pre_checkout_query = query
    return update


def _payment_update(chat_id: int, *, payload: str, charge_id: str = "ch_test"):
    update = MagicMock()
    update.effective_chat.id = chat_id
    sp = MagicMock()
    sp.invoice_payload = payload
    sp.telegram_payment_charge_id = charge_id
    sp.subscription_expiration_date = None
    sp.is_recurring = True
    update.message.successful_payment = sp
    update.message.reply_text = AsyncMock()
    return update


# ── Pre-checkout ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_precheckout_accepts_valid_payload(tmp_knowledge_dir, chat_id):
    from src.telegram_bot import precheckout_handler

    update = _precheckout_update(chat_id, payload=f"plan:basic:{chat_id}")
    await precheckout_handler(update, MagicMock())
    update.pre_checkout_query.answer.assert_called_once()
    assert update.pre_checkout_query.answer.call_args.kwargs["ok"] is True


@pytest.mark.asyncio
async def test_precheckout_rejects_bad_payload(tmp_knowledge_dir, chat_id):
    from src.telegram_bot import precheckout_handler

    update = _precheckout_update(chat_id, payload="garbage")
    await precheckout_handler(update, MagicMock())
    assert update.pre_checkout_query.answer.call_args.kwargs["ok"] is False


@pytest.mark.asyncio
async def test_precheckout_rejects_unknown_plan(tmp_knowledge_dir, chat_id):
    from src.telegram_bot import precheckout_handler

    update = _precheckout_update(chat_id, payload=f"plan:nonexistent:{chat_id}")
    await precheckout_handler(update, MagicMock())
    assert update.pre_checkout_query.answer.call_args.kwargs["ok"] is False


# ── Successful payment ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_successful_payment_activates_plan(tmp_knowledge_dir, chat_id):
    import src.telegram_bot as bot
    from src.billing import load_subscription, subscription_status

    update = _payment_update(chat_id, payload=f"plan:basic:{chat_id}", charge_id="ch_42")
    await bot.on_successful_payment(update, MagicMock())

    assert subscription_status(chat_id) == "active"
    sub = load_subscription(chat_id)
    assert sub["plan"] == "basic"
    assert sub["telegram_charge_id"] == "ch_42"
    update.message.reply_text.assert_called_once()


@pytest.mark.asyncio
async def test_recurring_payment_extends_expiry(tmp_knowledge_dir, chat_id):
    import src.telegram_bot as bot
    from src.billing import load_subscription

    await bot.on_successful_payment(
        _payment_update(chat_id, payload=f"plan:basic:{chat_id}", charge_id="ch_1"), MagicMock())
    first = load_subscription(chat_id)["expires_at"]
    await bot.on_successful_payment(
        _payment_update(chat_id, payload=f"plan:basic:{chat_id}", charge_id="ch_2"), MagicMock())
    second = load_subscription(chat_id)["expires_at"]
    assert datetime.fromisoformat(second) > datetime.fromisoformat(first)


@pytest.mark.asyncio
async def test_successful_payment_ignores_malformed_payload(tmp_knowledge_dir, chat_id):
    import src.telegram_bot as bot
    from src.billing import subscription_status

    update = _payment_update(chat_id, payload="not-a-plan")
    await bot.on_successful_payment(update, MagicMock())
    assert subscription_status(chat_id) == "none"  # nothing activated


# ── /subscribe + /billing ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cmd_subscribe_sends_invoice_buttons(tmp_knowledge_dir, chat_id):
    import src.telegram_bot as bot

    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.bot.create_invoice_link = AsyncMock(return_value="https://t.me/invoice")

    await bot.cmd_subscribe(update, ctx)

    ctx.bot.create_invoice_link.assert_awaited()
    update.message.reply_text.assert_called_once()
    assert update.message.reply_text.call_args.kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_cmd_billing_shows_plan_status(tmp_knowledge_dir, chat_id):
    import src.telegram_bot as bot
    from src.billing import start_trial

    start_trial(chat_id)
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message.reply_text = AsyncMock()

    await bot.cmd_billing(update, MagicMock())

    text = update.message.reply_text.call_args[0][0]
    assert "Trial" in text


# ── Self-serve registration via /start ──────────────────────────────────────

@pytest.mark.asyncio
async def test_cmd_start_self_registers_new_user(tmp_knowledge_dir, chat_id, monkeypatch):
    import src.registry as registry
    import src.telegram_bot as bot
    from src.billing import subscription_status

    # Real is_registered so the new-user branch actually runs.
    monkeypatch.setattr(bot, "is_registered", registry.is_registered)

    update = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_user = MagicMock()
    update.effective_user.username = "newbie"
    update.effective_user.language_code = "en"
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.user_data = {}

    await bot.cmd_start(update, ctx)

    assert registry.is_registered(chat_id) is True
    assert subscription_status(chat_id) == "active"  # trial started


# ── requires_active gate ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_requires_active_blocks_expired_user(tmp_knowledge_dir, chat_id, monkeypatch):
    """An expired user calling /add gets the upsell, not the handler body."""
    import src.telegram_bot as bot

    monkeypatch.setattr(bot, "is_registered", lambda c: True)
    monkeypatch.setattr(bot, "is_active", lambda c: False)

    update = MagicMock()
    update.effective_chat.id = chat_id
    update.message.reply_text = AsyncMock()
    ctx = MagicMock()
    ctx.args = ["https://www.youtube.com/@channel"]

    with patch("src.telegram_bot.resolve_channel_id") as mock_resolve:
        await bot.cmd_add(update, ctx)

    mock_resolve.assert_not_called()  # handler body never ran
    update.message.reply_text.assert_called_once()
