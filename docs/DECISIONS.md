# Decisions (ADR log)

Architecture-level decisions and their rationale. One entry per decision — do not retrofit answers into commit messages or code comments.

**Format:**
```
## ADR-NNN: <title> (YYYY-MM-DD)
**Status:** Accepted | Superseded by ADR-XXX | Deprecated
**Context:** What forced the decision
**Decision:** What we chose
**Consequences:** Downstream effects (good and bad)
**Alternatives considered:** What we rejected and why
```

**Update cadence:** add an ADR whenever a design choice would surprise a future reader who only has the code. If a later decision overrules an earlier one, set the old one to "Superseded" and cross-link — do not delete history.

---

## ADR-001: No database (2026-04-19)

**Status:** Accepted

**Context:** Need persistent storage for (a) the knowledge base, (b) deduplication state, (c) per-user config, (d) approval queue, (e) rejection audit. The product markets itself as "Markdown files on your server, no SaaS, no subscription." Adding a database service conflicts with the one-container deploy and breaks the backup-by-tar and edit-in-Obsidian stories.

**Decision:** Use the filesystem for everything:
- **Markdown** for the knowledge base (`knowledge/{chat_id}/{category}/{yyyy}/{mm}/*.md`)
- **JSON** for transactional state (`processed.json`, `pending.json`) — cheap, atomic via `.tmp` + `os.replace`
- **YAML** for user-editable config (`profile.yaml`, `channels.yml`, `categories.yml`) — human-editable in Obsidian / any editor
- **JSONL** for append-only logs (`rejected_log.jsonl`) — line-at-a-time appends are atomic at the OS level

**Consequences:**
- (+) Backups are `tar czf pulsebrain-YYYY-MM-DD.tgz data/ knowledge/`.
- (+) Users can edit profile / channels / entries directly with any editor; the bot re-reads on next access.
- (+) No migrations. No connection pools. No "is the DB up?" health check.
- (+) Deploy image is tiny — python-slim + pip deps. Nothing else.
- (−) Keyword search is O(files) — fine up to low thousands of entries; will need an index (see ADR-005 / future vector store) past ~10 k.
- (−) No transactions across files. Mitigated by: per-user locks, atomic writes, idempotent operations (e.g. content IDs are canonical).
- (−) Concurrent writes require explicit `threading.Lock` per file — enforced by [SYSTEM_CONSTRAINTS.md Constraint 3](system-context/SYSTEM_CONSTRAINTS.md#constraint-3-atomic-writes-for-all-persistent-state).

**Alternatives considered:**
- **SQLite** — embedded, single-file, cheap. Rejected: breaks the "edit in Obsidian" story; still needs a schema migration tool as the product evolves; adds one more thing to back up correctly.
- **Postgres** — would enable better search and real concurrency. Rejected: conflicts with one-container deploy, needs a managed service or second container, adds operational complexity disproportionate to current scale (single-user or small friend group).
- **Hybrid — Markdown for content, SQLite for index** — rejected for now; the 85 % test coverage already mocks filesystem happily and the search volume doesn't justify the complexity. Revisit if entry count goes past 5 k.

---

## ADR-002: Single container for bot + scheduler (2026-04-19)

**Status:** Accepted

**Context:** The bot handles interactive Telegram commands; the scheduler periodically polls YouTube RSS feeds. These could run in separate containers (bot / worker split), which is the standard Celery-style layout.

**Decision:** Both run in a single Python process inside one container. APScheduler's `AsyncIOScheduler` is started from the Telegram bot's `post_init` hook, sharing the same event loop.

**Consequences:**
- (+) One image, one `docker compose up`, one set of logs, one set of volumes. Fits a €7/mo VPS with no operational overhead.
- (+) No IPC needed — scheduler calls `telegram_bot.send_notification(app, …)` directly via the shared `app` reference.
- (+) Startup ordering is explicit: config → migration → per-user init → scheduler → `run_polling`.
- (−) Scheduler and bot share a process — a hang in one blocks the other. Mitigated by: both being async (long-running I/O doesn't block); `asyncio.to_thread` for the CPU-bound extract/summarize call chain.
- (−) Horizontal scaling means running multiple copies, which would double-process every RSS item. Not a current requirement — allowlist-gated single-tenant-ish product.

**Alternatives considered:**
- **Bot container + worker container + Redis broker** — the Celery pattern. Rejected: overkill for a personal-knowledge tool processing ≤ 100 videos/day; Redis adds a second volume to back up; IPC complicates error propagation.
- **systemd timer instead of APScheduler** — would require the scheduler to be a separate process anyway. Rejected for the same in-process reasons + APScheduler gives us clean test ergonomics.

---

## ADR-003: Multi-tenant via `chat_id` threading (2026-04-19)

**Status:** Accepted. Supersedes the original single-user design implicit in pre-Phase-5 commits.

**Context:** Original bot design was single-tenant: one `TELEGRAM_CHAT_ID` env var, state at the root of `data/` and `knowledge/`. User wanted to share the deployment with friends (a small group) without spinning up one container per person and without the operational cost of an actual SaaS.

**Decision:** Make the bot multi-tenant by:
1. Accepting a comma-separated `TELEGRAM_CHAT_IDS` env (with optional `id:Label` labels); first entry is admin.
2. Namespacing every persistent file under `data/users/{chat_id}/` and `knowledge/{chat_id}/`.
3. Passing `chat_id: int` as the first argument of every function that touches per-user state.
4. Keying every in-memory cache and `threading.Lock` by `chat_id`.
5. Migrating legacy single-user data into the admin's namespace on first boot, guarded by a `.migrated_v1` marker ([src/migration.py](../src/migration.py)).

**Consequences:**
- (+) One deploy serves a small trusted group. No per-user infrastructure.
- (+) Per-user LLM context → per-user relevance gating. A user interested in `claude-code` sees different scores than a user interested in `wordpress`.
- (+) Migration from single-user was automated and idempotent — no manual operator steps.
- (−) Every module's API signature grew `chat_id` — larger surface area, slightly more verbose. Mitigated by: strict convention (always first arg), lint-visible at every call site.
- (−) Large files like `telegram_bot.py` (1511 LOC) and `strings.py` (2727 LOC) became necessary. Splitting `strings.py` per-language (or moving to gettext / .po files) is a future refactor tracked but not urgent.

**Alternatives considered:**
- **One container per user** — clean isolation. Rejected: operationally painful (N sets of proxies, env files, compose services); wasteful at 1-5 users.
- **True multi-tenant with a DB** — the SaaS pattern. Rejected: conflicts with ADR-001 and the whole product positioning.
- **Shared state with `user_id` columns** — would need a DB; same conflict.

---

## ADR-004: Rotating residential proxies for YouTube transcripts (2026-04-19)

**Status:** Accepted

**Context:** `youtube-transcript-api` is a scraper — it talks to the caption endpoint that YouTube exposes to the web player. YouTube aggressively blocks data-center IPs; a bare VPS run produces ~100 % failure rate within hours. The bot is deployed on Hetzner VPSes, which are blocked.

**Decision:** Read credentials from a file (`proxy-credentials`, one `user:pass@host:port` per line) mounted read-only in the container. Per-request random line pick. Fall back to direct requests if file missing. Retry 3× with exponential backoff (`1s, 2s, 4s`) — each retry picks a fresh random line.

**Consequences:**
- (+) Transcript success rate is ~95 % in practice (residential proxies themselves fail 5–10 % — retries absorb it).
- (+) Adding / rotating proxies is a `vi proxy-credentials` on the host; no rebuild needed.
- (+) `:ro` mount means no code path can overwrite credentials — small but nonzero defense against bugs.
- (+) Any provider speaking `user:pass@host:port` is a drop-in replacement — proxy-cheap.com is tested but not a hard dependency.
- (−) Proxies cost money (~$5/mo for residential rotating). Small but real recurring cost.
- (−) Residential IPs can have high latency (500ms–2s per transcript fetch); amortized fine at scheduler cadence of 30 min.

**Alternatives considered:**
- **YouTube Data API v3** — official caption endpoint requires OAuth per user + quota. Rejected: wildly disproportionate complexity and cost (quota forces batching + paid tier at any real scale).
- **Whisper on the audio stream** — download audio, locally transcribe. Rejected: 10-20× more compute per video; ARM64 GPU-free hosts can't keep up with scheduler cadence.
- **No proxies, just retry** — tested, fails persistently on VPS.

---

## ADR-005: Pending queue before disk commit (2026-04-19)

**Status:** Accepted

**Context:** After summarize + categorize run, the entry *could* be written straight to `knowledge/{chat_id}/…/*.md`. But LLM relevance scoring is noisy (false positives on hype content, false negatives on dense videos) and users want the last say before committing to their knowledge base.

**Decision:** Introduce a staging layer in [src/pending.py](../src/pending.py). After summarize + categorize, the pipeline calls `stage_pending(...)` which:
1. Inlines the full summary payload + lossless raw text into `data/users/{chat_id}/pending.json`.
2. Marks `processed.json[content_id] = "pending"` so the scheduler doesn't re-stage.
3. Tells Telegram to send an approve/reject keyboard.

The user's tap drives:
- **Approve** → `commit_pending` writes the `.md` + `.source.txt`, marks `status="ok"`, drops from pending.
- **Reject** → `reject_pending` appends to `rejected_log.jsonl` with reason, marks `status="rejected"`, drops from pending.

Scheduler has an additional auto-reject path: entries below `min_relevance` never hit the user's inbox — they're rejected with `reason="low_relevance"`, audit-logged, never written to Markdown.

**Consequences:**
- (+) User sees the bot's judgment before it hits their knowledge base. A noisy week's digest can be triaged in under a minute via `/pending`.
- (+) `rejected_log.jsonl` is the signal for eventually tuning the relevance prompt — every rejection with reason is a data point.
- (+) `.source.txt` is inlined in `pending.json` and carried forward only on approve, so rejected content leaves no disk footprint beyond a log line.
- (+) The auto-reject gate gives users the "quiet bot" option — set `min_relevance: 7` on a noisy channel to only see real signal.
- (−) `pending.json` can grow if the user ignores notifications. No auto-eviction. In practice, `/pending` and `/rejected` give enough visibility that this stays small.
- (−) The shape of `pending.json` is tightly coupled to the shape of `save_entry` args — schema changes need migration (none yet, but the risk is real).

**Alternatives considered:**
- **Straight-to-disk, delete on reject** — atomic but messy (write then unlink cycles; editor-open files can't be unlinked on Windows; index re-regeneration churn).
- **In-memory staging only** — survives only until process restart; `docker compose restart` would lose pending items.
- **Approve-by-default, reject with explicit command** — too noisy; would require an eviction path and leave clutter.

---

## ADR-006: Categories are per-user, no shared defaults (2026-04-19)

**Status:** Accepted

**Context:** `load_categories(chat_id)` used to merge a hardcoded `_DEFAULT_CATEGORIES` dict (7 slugs, incl. `ai-news`) over the user's own `categories.yml`. A friend who finished onboarding then saw categories they never picked in `/categories` and pending entries. This broke [Architecture rule 3](../CLAUDE.md#architecture-rules-non-negotiable) ("Per-user isolation is total"): every tenant was inheriting the same 7 slugs. Compounding this, [src/categorize.py](../src/categorize.py) hardcoded `ai-news` as the fallback slug whenever the LLM returned something malformed or the API raised — which surfaced the leaked slug even in users who never picked it.

**Decision:**
- Delete `_DEFAULT_CATEGORIES` entirely from [src/config.py](../src/config.py).
- `load_categories(chat_id)` returns exactly the user's `categories.yml` (or `{}` if no file yet). The starter menu lives in [src/onboarding_presets.py](../src/onboarding_presets.py) `PRESET_CATEGORIES` and is only shown during the wizard — what the user toggles is what goes into their file.
- When the LLM returns an unparseable slug or the first call raises, [src/categorize.py](../src/categorize.py) makes a second, focused LLM call asking for `{"slug": "...", "description": "..."}` derived from the content — still per-user. Only if both calls fail do we fall back to a per-user `uncategorized` slug; on approval it's written to *that* user's file via the existing `is_new_category` flow.
- No migration of existing `categories.yml` files. Users keep their explicit picks. Anything they implicitly relied on is re-added organically by the LLM on next matching content.

**Consequences:**
- (+) Two users with zero overlap in their onboarding picks now have zero overlap in their category lists — enforces tenant isolation at the data layer, not just the file layer.
- (+) No more "mystery" slugs appearing in a user's `/categories`.
- (+) The fallback for a garbled LLM reply stays content-relevant (a generated slug) instead of forcing everything into one bucket.
- (−) A brand-new user who hasn't finished onboarding has an empty categories dict. The LLM prompt handles this ("suggest a new short slug") but it means the very first entry for such a user always goes into a freshly-generated or `uncategorized` slug. Acceptable — onboarding runs before any `/add`.
- (−) Any existing user whose admin-era bot had silently accumulated `ai-news`-tagged entries without them explicitly picking it will see that slug disappear from *new* suggestions. Existing files under `knowledge/{chat_id}/ai-news/` are untouched.

**Alternatives considered:**
- **Keep defaults as onboarding seeds, drop the merge at runtime** — half-measure; still requires two parallel category sets and doesn't simplify.
- **Migrate each existing `categories.yml` to bake in the old defaults on first start** — preserves behavior but defeats the point of the fix for long-lived users.
- **Retry the primary LLM prompt instead of a dedicated fresh-category call** — simpler but less targeted; the second prompt is specifically shaped for slug generation.

---

## ADR-007: Failures are classified permanent vs transient, with bounded retries (2026-09-03)

**Status:** Accepted

**Context:** A residential-proxy outage lasted a week. Every transcript fetch failed with `ProxyError`, and commit `e55e7ca` ("Mark failed videos as processed so scheduler stops retrying them") faithfully recorded each one as `status="failed"`. Because `is_processed` tested key membership only — `return content_id in cache` — a `failed` record blocked content exactly as hard as `ok`. Four videos were permanently blacklisted over an infrastructure problem that fixed itself the moment the proxy came back.

`e55e7ca`'s intent was correct: without it the scheduler re-attempted an unprocessable video every 30 minutes forever. The flaw was that it could not tell "this video has no captions" from "our proxy is down" — because `get_transcript` collapsed every exception into `None`, so by the time the pipeline saw the failure the reason was already gone.

**Decision:**
- Classify at the extractor boundary, where the exception is still in hand. [src/extractors/youtube.py](../src/extractors/youtube.py) enumerates `_PERMANENT_TRANSCRIPT_ERRORS` and treats everything else as transient; [src/extractors/web.py](../src/extractors/web.py) mirrors it.
- Propagate the reason through a caller-owned `failure_out` dict, leaving the `str | None` return contract untouched.
- Give pipeline error results a machine-readable `error_code` (the `t()` key) and a `failure_kind`, so nothing downstream ever parses a localized string.
- `is_processed` now means "is this blocked *now*", with `now` injected for testability. `has_processed_record` keeps the old existence semantics for back-catalog suppression.
- Retry eligibility is a whitelist: `status == "failed"` **and** `failure_kind == "transient"` **and** `attempts < MAX_TRANSIENT_ATTEMPTS` **and** the cooldown has elapsed. Cooldowns come from `RETRY_BACKOFF_HOURS` (default `1,6,24,168` — a horizon of ~8 days, chosen to outlast the observed 7-day outage).
- No new retry machinery. The scheduler's existing per-cycle gate is the retry mechanism; the cooldown is expressed purely as data in the record that gate already reads.

**Consequences:**
- (+) Transient outages self-heal with no operator action. A proxy blip costs a delay, not the content.
- (+) `e55e7ca`'s guarantee survives intact — retries are bounded by the attempt cap, and a permanent failure is not retried even once.
- (+) An OpenRouter blip no longer blacklists a video either; `pipeline_err_summarize_failed` was the second-largest source of the same bug.
- (+) Zero new user-facing strings, zero new commands, no migration, no new state file. `/run` already serves as the manual trigger once a cooldown elapses.
- (+) Permanent errors short-circuit the in-call retry loop, saving two proxy requests and 3 s of sleep per captionless video.
- (−) The retry horizon is capped by the RSS window: `fetch_channel_videos` sees only a channel's newest 10 entries, so a video that ages out before its cooldown expires is never retried. The ladder must be sized against posting frequency.
- (−) `is_processed` is now time-dependent, so tests must inject `now` rather than assume a static answer.
- (−) Legacy `failed` records stay blocked forever. Deliberate, and the explicit user decision — production data was not to be touched.
- (−) `failure_out` is a mutable out-parameter, a mild code smell, accepted for the reasons under Alternatives.

**Alternatives considered:**
- **Change `get_transcript`'s return type to a tuple/NamedTuple** — cleanest API, but breaks 14 `patch(..., return_value=…)` sites across `test_pipeline.py` and `test_integration.py`, including tests guarding the behaviour being changed.
- **Add a parallel `get_transcript_result()`** — worse: existing `patch("src.pipeline.get_transcript")` calls become inert, so a test would make a real network call instead of failing loudly.
- **Module-level "last error" global** — races under the scheduler's `asyncio.gather` → `asyncio.to_thread` fan-out across users.
- **Branch on `CouldNotRetrieveTranscript`** — `RequestBlocked` descends from it, so this would classify a dead proxy as permanent and reproduce the exact bug.
- **Parse the localized error string** — rejected outright; the prose is rendered in ten languages.
- **A `/retry` command** — every command costs 10 translations, and `/run` already covers the manual case.
- **Migrate production `processed.json` to unblock the four stuck videos** — user declined touching production data.

---

## ADR template (copy for new entries)

```markdown
## ADR-NNN: <short title> (YYYY-MM-DD)

**Status:** Accepted | Superseded by ADR-XXX | Deprecated

**Context:** <what forced the decision — constraint, incident, or conscious choice>

**Decision:** <what we're doing, concrete enough to verify in code>

**Consequences:**
- (+) <good effect>
- (−) <cost or risk, with mitigation>

**Alternatives considered:**
- **<option>** — <why rejected>
```
