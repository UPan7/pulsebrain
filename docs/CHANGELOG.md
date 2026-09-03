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

## 2026-09-03 — Transient failures are retried instead of blacklisted forever

**What:** Failures are now classified permanent vs transient at the extractor boundary and retried on a bounded schedule. `is_processed` changed meaning from "a record exists" to "this is blocked right now"; `has_processed_record` preserves the old existence check. `processed.json` records for `status="failed"` gained `failure_kind`, `error_code`, `attempts` and `retry_after`. Pipeline error results gained `error_code` (the stable `t()` key) and `failure_kind`. Two new env vars: `MAX_TRANSIENT_ATTEMPTS` (default 5) and `RETRY_BACKOFF_HOURS` (default `1,6,24,168`).

**Why:** A week-long residential-proxy outage permanently blacklisted four videos. `is_processed` tested key membership only, so the `failed` records written by `e55e7ca` blocked content as hard as `ok` — even though the failure was pure infrastructure. `e55e7ca` was right to stop infinite retries; it just could not tell a dead proxy from a captionless video, because `get_transcript` collapsed every exception into `None`.

**Impact:** [src/config.py](../src/config.py), [src/storage.py](../src/storage.py), [src/extractors/youtube.py](../src/extractors/youtube.py), [src/extractors/web.py](../src/extractors/web.py), [src/pipeline.py](../src/pipeline.py), [src/scheduler.py](../src/scheduler.py), [src/telegram_bot.py](../src/telegram_bot.py), [.env.example](../.env.example), [requirements.txt](../requirements.txt). Tests added across `test_config`, `test_storage`, `test_multi_user`, `test_extractors`, `test_extractors_web`, `test_pipeline`, `test_scheduler`, `test_telegram_bot` — 606 passing, coverage 91.9 %. `youtube-transcript-api` pinned to `>=1.2,<2` because the classifier depends on the exception taxonomy. Zero new user-facing strings and no new commands.

**Migration:** **None, by design.** Existing `failed` records carry no `failure_kind`, and retry eligibility is a whitelist requiring `failure_kind == "transient"` — so every historical failure stays blocked. `skipped`, `pending`, `ok` and `rejected` keep blocking exactly as before.

**Also fixed:** the back-catalog suppression in `_mark_remaining_channel_videos_skipped` used `is_processed` as an existence check. Under the new semantics it would have read a cooled-down transient failure as unseen and overwritten it with `skipped` — silently making the blip permanent and defeating the whole feature. See [ADR-007](DECISIONS.md#adr-007).

**Documentation correction:** [CLAUDE.md](../CLAUDE.md) claimed the 85 % coverage gate is CI-enforced. It is not — `deploy.yml` is the only workflow and it runs scp + `docker compose build`, never `pytest`. The gate is local-only.

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
