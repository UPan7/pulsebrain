# Changelog

Reverse-chronological. Most recent on top. One entry per meaningful change — commit-level churn goes in git, not here.

**Format:**
```
## YYYY-MM-DD — <headline>
**What:** changed / added / removed
**Why:** motivation
**Impact:** files touched, breaking changes, migrations, test coverage notes
```

**Update cadence:** append on any change that would matter to a teammate returning after a month away. Skip for typos, formatting, and comment-only commits.

---

## 2026-05-21 — SaaS conversion: self-serve signup, subscriptions, quotas

**What:** Turned the friends-only bot into a sellable hosted SaaS (lean MVP).
- Dynamic user registry ([src/registry.py](../src/registry.py), `data/users/registry.json`) replaces the static `TELEGRAM_CHAT_IDS` allowlist; that env var now only seeds admins. `/start` self-registers any non-blocked chat.
- Subscription billing ([src/billing.py](../src/billing.py), `plans.yml`): trial / basic / pro / lifetime plans with per-user `subscription.yaml` + `usage.json`. Channel and monthly-item quotas enforced; the pipeline gates every item on `quota_check()` before incurring cost.
- Telegram Stars payment flow — `/subscribe` (recurring Star invoice links) and `/billing`, plus `PreCheckoutQuery` / `SuccessfulPayment` handlers.
- Expired users keep read-only access (`/search`, `/recent`, `/get`); `/add`, `/run`, link drops and Q&A require an active plan.

**Why:** The product is being commercialized — strangers must be able to sign up and pay without operator action, and managed LLM/proxy costs must be bounded per user.

**Impact:** New: [src/registry.py](../src/registry.py), [src/billing.py](../src/billing.py), [plans.yml](../plans.yml), [tests/test_registry.py](../tests/test_registry.py), [tests/test_billing.py](../tests/test_billing.py), [tests/test_billing_flow.py](../tests/test_billing_flow.py). Modified: [src/config.py](../src/config.py), [src/pipeline.py](../src/pipeline.py), [src/scheduler.py](../src/scheduler.py), [src/telegram_bot.py](../src/telegram_bot.py), [src/main.py](../src/main.py), [src/migration.py](../src/migration.py), [src/strings.py](../src/strings.py) (26 billing keys ×10 languages), [tests/conftest.py](../tests/conftest.py), [docker-compose.yml](../docker-compose.yml), [.env.example](../.env.example). Test suite 579 → 622, coverage 89.7%.

**Breaking changes:** Authorization no longer keyed on the env allowlist. Existing allowlisted users are grandfathered (marker-guarded migration → unlimited `lifetime` plan), so deployed instances keep working. See [ADR-007](DECISIONS.md#adr-007-dynamic-user-registry-replaces-the-static-allowlist-2026-05-21), [ADR-008](DECISIONS.md#adr-008-subscription-billing-in-jsonyaml-paid-via-telegram-stars-2026-05-21).

**Migration:** Idempotent, marker-guarded (`.migrated_billing_v1`). Runs automatically on first boot.

---

## 2026-04-19 — Per-user category isolation (drop shared defaults)

**What:** Removed `_DEFAULT_CATEGORIES` from [src/config.py](../src/config.py). `load_categories(chat_id)` now returns only the user's own `categories.yml` (empty dict if none). In [src/categorize.py](../src/categorize.py), the LLM-fallback path no longer hardcodes `ai-news` — a second LLM call generates a fresh slug + description from the content; on double-failure it falls back to a per-user `uncategorized` slug that lives only in that user's file.

**Why:** A newly-onboarded friend saw category lists that included `ai-news` and other slugs they never picked — the hardcoded defaults were leaking across tenants, breaking the "every user is isolated" rule.

**Impact:** [src/config.py](../src/config.py), [src/categorize.py](../src/categorize.py), [src/onboarding_presets.py](../src/onboarding_presets.py) docstring, [CLAUDE.md](../CLAUDE.md) state-files table, [tests/test_config.py](../tests/test_config.py), [tests/test_categorize.py](../tests/test_categorize.py), [tests/test_multi_user.py](../tests/test_multi_user.py). No migration of existing users' files — their explicit picks stay untouched.

**Breaking changes:** Any user who was implicitly relying on a hardcoded default (e.g. `ai-news`) being present without having picked it will no longer see it. See [ADR-006](DECISIONS.md#adr-006).

---

## 2026-04-19 — Initial documentation bootstrap

**What:** Added full documentation skeleton.

**Why:** Prior to today, documentation was limited to a short [CLAUDE.md](../CLAUDE.md) and a user-facing [README.md](../README.md). An agent opening the repo had no fast way to orient — no module map, no architecture diagrams, no ADRs. This bootstrap fills the gap.

**Impact:**
- Expanded [CLAUDE.md](../CLAUDE.md) from 47 lines to full project guide (stack, architecture rules, modules table, key files, Telegram commands, error handling, testing methodology, state files schema, docs update protocol, links).
- Created [docs/system-context/MODULE_MAP.md](system-context/MODULE_MAP.md) — top-level tree, per-module file listings, cross-module edges, state file schemas.
- Created [docs/system-context/SYSTEM_CONSTRAINTS.md](system-context/SYSTEM_CONSTRAINTS.md) — 12 non-negotiable rules (no DB, multi-tenant chat_id, atomic writes, allowlist, no crashes, canonical content IDs, strings.t(), secrets via env, proxy RO, validated LLM output, migration no-merge, category path-safety).
- Created [docs/system-context/TECH_CONTEXT.md](system-context/TECH_CONTEXT.md) — per-library rationale + gotchas for Python 3.11, python-telegram-bot, APScheduler, OpenAI SDK (via OpenRouter), youtube-transcript-api, feedparser, trafilatura, PyYAML, requests, python-slugify, pytest stack, Docker, Hetzner, proxy-cheap.
- Created [docs/ARCHITECTURE.md](ARCHITECTURE.md) — Mermaid diagrams for system overview, user-drop-link path, scheduler path, multi-tenant isolation, deployment topology, failure/recovery matrix.
- Created [docs/DECISIONS.md](DECISIONS.md) — 5 ADRs:
  - ADR-001 No database (Markdown + JSON + YAML)
  - ADR-002 Single container for bot + scheduler
  - ADR-003 Multi-tenant via `chat_id` threading
  - ADR-004 Rotating residential proxies for YouTube transcripts
  - ADR-005 Pending queue before disk commit
- Created this file (`CHANGELOG.md`).

**Files touched:** 7 (1 updated, 6 new). No code changes — documentation only.

**Breaking changes:** None.

**Migration:** None.

**Skipped by design:**
- `docs/system-context/DATABASE_SCHEMA.md` — no database (see ADR-001). State file schemas live in MODULE_MAP instead.
- `docs/SPEC.md` — no GUI product; Telegram commands + `t()` string keys are the interface and are documented in CLAUDE.md / MODULE_MAP.
- `docs/TESTING.md` — testing strategy fits inside CLAUDE.md without warranting a separate file.
