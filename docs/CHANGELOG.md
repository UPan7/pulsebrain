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
