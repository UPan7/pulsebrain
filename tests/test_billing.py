"""Tests for src.billing — plans, subscriptions, usage metering, quotas."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch


# ── Plan catalog ────────────────────────────────────────────────────────────

def test_load_plans_has_core_plans():
    from src.billing import load_plans

    plans = load_plans()
    for key in ("trial", "basic", "pro", "lifetime"):
        assert key in plans


def test_get_plan_falls_back_to_trial_for_unknown():
    from src.billing import get_plan

    assert get_plan("does-not-exist") == get_plan("trial")


def test_purchasable_plans_sorted_by_price():
    from src.billing import purchasable_plans

    plans = purchasable_plans()
    keys = [k for k, _ in plans]
    assert "trial" not in keys and "lifetime" not in keys  # not purchasable
    prices = [p["price_xtr"] for _, p in plans]
    assert prices == sorted(prices)


# ── Subscription lifecycle ──────────────────────────────────────────────────

def test_start_trial(tmp_knowledge_dir, chat_id):
    from src.billing import is_active, start_trial, subscription_status

    sub = start_trial(chat_id)
    assert sub["plan"] == "trial"
    assert subscription_status(chat_id) == "active"
    assert is_active(chat_id) is True


def test_subscription_status_none_when_no_file(tmp_knowledge_dir, chat_id):
    from src.billing import subscription_status

    assert subscription_status(chat_id) == "none"


def test_subscription_status_expired_from_past_date(tmp_knowledge_dir, chat_id):
    """A past expiry reads as expired even when stored status is 'active'."""
    from src.billing import save_subscription, subscription_status

    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    save_subscription(chat_id, {"plan": "basic", "status": "active", "expires_at": past})
    assert subscription_status(chat_id) == "expired"


def test_activate_paid_sets_active(tmp_knowledge_dir, chat_id):
    from src.billing import activate_paid, current_plan, subscription_status

    activate_paid(chat_id, "basic", charge_id="ch_1", period_days=30)
    assert subscription_status(chat_id) == "active"
    assert current_plan(chat_id)["max_channels"] == 10  # basic plan, plans.yml


def test_activate_paid_renewal_extends_expiry(tmp_knowledge_dir, chat_id):
    from src.billing import activate_paid

    first = activate_paid(chat_id, "basic", charge_id="ch_1", period_days=30)
    second = activate_paid(chat_id, "basic", charge_id="ch_2", period_days=30)
    assert datetime.fromisoformat(second["expires_at"]) > datetime.fromisoformat(first["expires_at"])
    assert second["telegram_charge_id"] == "ch_2"


def test_activate_paid_with_explicit_expiry(tmp_knowledge_dir, chat_id):
    from src.billing import activate_paid

    when = datetime.now(timezone.utc) + timedelta(days=99)
    sub = activate_paid(chat_id, "pro", charge_id="c", expires_at=when)
    assert sub["expires_at"] == when.isoformat()


def test_grandfather_never_expires(tmp_knowledge_dir, chat_id):
    from src.billing import grandfather, is_active, subscription_status

    grandfather(chat_id)
    assert subscription_status(chat_id) == "active"
    assert is_active(chat_id) is True


def test_cancel_keeps_access_until_expiry(tmp_knowledge_dir, chat_id):
    from src.billing import activate_paid, cancel_subscription, is_active

    activate_paid(chat_id, "basic", charge_id="c", period_days=30)
    cancel_subscription(chat_id)
    # Cancelled, but the paid window has not lapsed yet.
    assert is_active(chat_id) is True


# ── Quotas + usage metering ─────────────────────────────────────────────────

def test_quota_check_blocks_without_subscription(tmp_knowledge_dir, chat_id):
    from src.billing import quota_check

    allowed, reason = quota_check(chat_id)
    assert allowed is False
    assert reason == "quota_expired"


def test_quota_check_allows_within_limit(tmp_knowledge_dir, chat_id):
    from src.billing import quota_check, start_trial

    start_trial(chat_id)
    allowed, reason = quota_check(chat_id)
    assert allowed is True and reason == ""


def test_quota_check_blocks_when_items_exceeded(tmp_knowledge_dir, chat_id):
    from src.billing import get_plan, quota_check, record_usage, start_trial

    start_trial(chat_id)
    for _ in range(get_plan("trial")["max_items_per_period"]):
        record_usage(chat_id, source="add")
    allowed, reason = quota_check(chat_id)
    assert allowed is False and reason == "quota_items_exceeded"


def test_channel_quota_check(tmp_knowledge_dir, chat_id):
    from src.billing import channel_quota_check, get_plan, start_trial

    start_trial(chat_id)
    limit = get_plan("trial")["max_channels"]
    assert channel_quota_check(chat_id, limit - 1)[0] is True
    assert channel_quota_check(chat_id, limit)[0] is False


def test_record_usage_increments(tmp_knowledge_dir, chat_id):
    from src.billing import load_usage, record_usage

    record_usage(chat_id, source="add")
    record_usage(chat_id, source="scheduler")
    usage = load_usage(chat_id)
    assert usage["items_processed"] == 2
    assert usage["by_source"] == {"add": 1, "scheduler": 1}


def test_monthly_rollover_resets_counter(tmp_knowledge_dir, chat_id):
    import src.billing as billing

    billing.record_usage(chat_id, source="add")
    # Force the stored period to the distant past, then read again.
    with billing._usage_lock_for(chat_id):
        billing._usage_caches[chat_id]["period"] = "2000-01"
    usage = billing.load_usage(chat_id)
    assert usage["period"] == billing._current_period()
    assert usage["items_processed"] == 0


def test_usage_summary(tmp_knowledge_dir, chat_id):
    from src.billing import record_usage, start_trial, usage_summary

    start_trial(chat_id)
    record_usage(chat_id, source="add")
    summary = usage_summary(chat_id)
    assert summary["plan"] == "trial"
    assert summary["status"] == "active"
    assert summary["items_used"] == 1


# ── Multi-tenant isolation ──────────────────────────────────────────────────

def test_quota_isolation_between_users(tmp_knowledge_dir, chat_id, other_chat_id):
    from src.billing import get_plan, quota_check, record_usage, start_trial

    start_trial(chat_id)
    start_trial(other_chat_id)
    for _ in range(get_plan("trial")["max_items_per_period"]):
        record_usage(chat_id, source="add")
    # chat_id exhausted; other_chat_id untouched.
    assert quota_check(chat_id)[0] is False
    assert quota_check(other_chat_id)[0] is True


def test_expiry_isolation_between_users(tmp_knowledge_dir, chat_id, other_chat_id):
    from src.billing import is_active, save_subscription, start_trial

    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    save_subscription(chat_id, {"plan": "basic", "status": "active", "expires_at": past})
    start_trial(other_chat_id)
    assert is_active(chat_id) is False
    assert is_active(other_chat_id) is True


def test_prune_billing_state(tmp_knowledge_dir, chat_id, other_chat_id):
    import src.billing as billing

    billing.start_trial(chat_id)
    billing.start_trial(other_chat_id)
    billing.load_usage(chat_id)
    pruned = billing.prune_billing_state([chat_id])
    assert pruned > 0
    assert other_chat_id not in billing._subscription_caches


# ── Pipeline integration (real quota gate + metering) ───────────────────────

def test_pipeline_quota_gate_blocks_without_subscription(tmp_knowledge_dir, chat_id, monkeypatch):
    """The pre-flight gate returns an error and skips all extraction/LLM."""
    import src.pipeline as pipeline
    from src.billing import quota_check, record_usage

    # conftest stubs these permissive — restore the real functions here.
    monkeypatch.setattr(pipeline, "quota_check", quota_check)
    monkeypatch.setattr(pipeline, "record_usage", record_usage)

    with patch("src.pipeline.get_video_metadata") as mock_meta:
        result = pipeline.process_youtube_video(chat_id, "https://www.youtube.com/watch?v=x")

    assert "error" in result
    mock_meta.assert_not_called()  # blocked before any cost was incurred


def test_pipeline_records_usage_on_success(tmp_knowledge_dir, chat_id, monkeypatch):
    import src.pipeline as pipeline
    from src.billing import load_usage, quota_check, record_usage, start_trial

    start_trial(chat_id)
    monkeypatch.setattr(pipeline, "quota_check", quota_check)
    monkeypatch.setattr(pipeline, "record_usage", record_usage)

    with (
        patch("src.pipeline.get_video_metadata",
              return_value={"title": "T", "channel": "C", "upload_date": None}),
        patch("src.pipeline.get_transcript", return_value="transcript body"),
        patch("src.pipeline.summarize_content", return_value={
            "summary_bullets": ["a"], "detailed_notes": "n", "key_insights": [],
            "action_items": [], "topics": [], "relevance_score": 7, "length_mode": "short",
        }),
        patch("src.pipeline.categorize_content", return_value=("ai-news", False)),
    ):
        result = pipeline.process_youtube_video(
            chat_id, "https://www.youtube.com/watch?v=ok123", source="scheduler",
        )

    assert "error" not in result
    usage = load_usage(chat_id)
    assert usage["items_processed"] == 1
    assert usage["by_source"]["scheduler"] == 1


# ── Billing migration (grandfathering) ──────────────────────────────────────

def test_grandfather_allowlisted_users(tmp_knowledge_dir, chat_id, other_chat_id):
    from src.billing import load_subscription, subscription_status
    from src.migration import grandfather_allowlisted_users
    from src.registry import is_registered

    assert grandfather_allowlisted_users([chat_id, other_chat_id]) is True
    for cid in (chat_id, other_chat_id):
        assert is_registered(cid)
        assert subscription_status(cid) == "active"
        assert load_subscription(cid)["plan"] == "lifetime"
    # Marker-guarded — a second call is a no-op.
    assert grandfather_allowlisted_users([chat_id]) is False


def test_grandfather_does_not_clobber_existing_subscription(tmp_knowledge_dir, chat_id):
    from src.billing import activate_paid, load_subscription
    from src.migration import grandfather_allowlisted_users

    activate_paid(chat_id, "basic", charge_id="ch", period_days=30)
    grandfather_allowlisted_users([chat_id])
    # An existing paid subscription must survive, not be overwritten.
    assert load_subscription(chat_id)["plan"] == "basic"
