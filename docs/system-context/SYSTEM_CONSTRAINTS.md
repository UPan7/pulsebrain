# System Constraints

> Iron rules for PulseBrain. If a change violates one of these, it needs an ADR in [../DECISIONS.md](../DECISIONS.md) before merge.
>
> **Update cadence:** add a constraint when the same bug class bites twice, or when a decision in DECISIONS.md promotes a design choice to an invariant. Remove a constraint only via superseding ADR.

---

## Constraint 1: No database

**Rule:** State lives on the filesystem — Markdown for knowledge, JSON for transactional state (processed, pending), YAML for user-edited config (profile, channels, categories). No SQLite, no Postgres, no ORM.

**Why:** The product promises "Markdown files on your server, no SaaS, no subscription." A DB would break the backup story (rsync a folder), the offline-edit story (open any entry in Obsidian), and the portability story (tar the folder, move to a new host).

**Enforcement:** Code review — any `import sqlite3` / `sqlalchemy` / `psycopg` fails review. No DB lib in [requirements.txt](../../requirements.txt).

**Violation example:** "Let's add a lightweight SQLite for fast search." No — keyword search over ≤ 10 k Markdown files is fine; a vector store for semantic search is a separate roadmap item and needs its own ADR.

---

## Constraint 2: Multi-tenant via `chat_id` threading

**Rule:** Every function that touches per-user state takes `chat_id: int` as its first argument. No module-level globals for the current user. No "active session" singleton.

**Why:** A single container serves N allowed users. One shared cache means one user sees another user's summaries or relevance gating — a privacy break.

**Enforcement:** Code review. Per-user caches in [src/storage.py:35](../../src/storage.py#L35), [src/pending.py:37](../../src/pending.py#L37), [src/profile.py:48](../../src/profile.py#L48) are all dicts keyed by `chat_id` with per-user locks. `tests/test_multi_user.py` asserts isolation across state mutations.

**Violation example:** `_cache: dict[str, Any] = {}` at module level without a chat_id key. Rewrite as `_caches: dict[int, dict[str, Any]] = {}` plus `_lock_for(chat_id)`.

---

## Constraint 3: Atomic writes for all persistent state

**Rule:** Every write to `processed.json`, `pending.json`, `profile.yaml`, `categories.yml`, `channels.yml`, `rejected_log.jsonl` uses:
1. Acquire the per-user `threading.Lock`.
2. Write the full serialized state to `path.with_suffix(".tmp")`.
3. `os.replace(tmp, path)` — atomic on POSIX and Windows.

**Why:** The bot's async tasks and the scheduler's thread pool may write the same file concurrently. A partial JSON file kills `is_processed` lookups and puts the queue in an unrecoverable state.

**Enforcement:** See `_flush_processed` at [src/storage.py:61](../../src/storage.py#L61), `_flush` at [src/pending.py:63](../../src/pending.py#L63), `_flush` at [src/profile.py:99](../../src/profile.py#L99). New persistent files must follow the same pattern.

**Violation example:** `with open(path, "w") as f: json.dump(cache, f)` — partial writes on crash. Always `.tmp` + `os.replace`.

**Exception:** `rejected_log.jsonl` is append-only — a single `f.write(line + "\n")` is atomic at the OS level for small records. See [src/pending.py:240](../../src/pending.py#L240).

---

## Constraint 4: Authorized users only (`TELEGRAM_CHAT_IDS` allowlist)

**Rule:** The bot responds to messages only from `chat_id`s in the `TELEGRAM_CHAT_IDS` environment variable. Unauthorized messages are silently ignored (no error reply — that would let strangers probe the deployment).

**Why:** This is a single-tenant-per-friend-group product, not a public bot. Making it public adds rate-limiting, quotas, moderation — none of which are built. Allowlist is the only gate.

**Enforcement:** `_authorized(update)` check ([src/telegram_bot.py:182](../../src/telegram_bot.py#L182)) at the top of every handler; unauthorized attempts are logged and silently dropped. `tests/test_telegram_bot.py` verifies unauthorized messages produce no reply.

**Violation example:** "Let's add a paid tier for outside users." Separate fork or separate gate — do not remove the allowlist.

---

## Constraint 5: No crashes on single-item failure

**Rule:** The process must survive:
- A single video with no transcript
- A single article trafilatura can't parse
- A malformed LLM JSON response
- A Telegram `send_message` failure
- One user's scheduler iteration raising

The corresponding user (if any) gets a localized error message; the rest of the work continues.

**Why:** Scheduler runs every 30 minutes across every allowed user. One bad RSS entry or one flaky network call crashing the loop means silently-missing content until someone notices the container died.

**Enforcement:** `try / except Exception` at each well-defined boundary:
- [src/scheduler.py:115](../../src/scheduler.py#L115) — notification failure
- [src/scheduler.py:175](../../src/scheduler.py#L175) — digest failure
- [src/scheduler.py:196](../../src/scheduler.py#L196) — per-user scheduler iteration
- [src/summarize.py:218](../../src/summarize.py#L218) — LLM API error with single retry
- [src/extractors/youtube.py:78](../../src/extractors/youtube.py#L78) — transcript retry loop
- [src/pending.py:261](../../src/pending.py#L261) — rejected-log append swallowed

Tests exercise each failure path (see [tests/test_scheduler.py](../../tests/test_scheduler.py), [tests/test_pipeline.py](../../tests/test_pipeline.py)).

**Violation example:** A bare `assert summary["relevance_score"] >= 1` in the pipeline — one bad LLM response and the scheduler dies. Guard with `summary.get("relevance_score", 5)` or return `{"error": …}` through the localized channel.

---

## Constraint 6: Canonical content IDs

**Rule:** Content IDs are deterministic from the source:
- `yt:{video_id}` for a YouTube video
- `web:{sha256(url)[:16]}` for an article

Never random UUIDs, never DB-assigned auto-increment, never session-specific IDs.

**Why:** Dedup across drops, scheduler re-runs, and re-imports depends on idempotent IDs. A user who drops the same link twice must see "already processed," not get a duplicate entry.

**Enforcement:** `make_content_id` at [src/storage.py:100](../../src/storage.py#L100) is the single factory. All call sites use it.

**Violation example:** Generating IDs based on title — two videos with identical titles would collide. Generating IDs via `uuid4()` — dedup breaks across restarts.

---

## Constraint 7: All UI text goes through `src.strings.t()`

**Rule:** Every user-facing string — Telegram message, button label, error — comes from `t(key, lang, **kwargs)`, where `lang` is `profile.get_language(chat_id)`. No bare string literals in handlers, scheduler, or pipeline error returns.

**Why:** Users pick a language during onboarding from 10 supported locales. A hardcoded English string in one handler breaks the product promise. Translation coverage is also the checksum — tests verify every key exists in every supported lang.

**Enforcement:** [src/strings.py](../../src/strings.py) is the single registry. [tests/test_strings.py](../../tests/test_strings.py) asserts every key resolves in every `SUPPORTED_LANGS` entry.

**Violation example:** `await update.message.reply_text("Video not found.")` — fails the moment a user with `language: ru` triggers it. Must be `t("cmd_get_not_found", lang)`.

---

## Constraint 8: Secrets only via environment variables

**Rule:** `OPENROUTER_API_KEY`, `TELEGRAM_BOT_TOKEN` come from `os.environ`. Never committed, never in CLI flags, never written back to disk.

**Why:** Standard hygiene. `.env` is in `.gitignore`; `.env.example` is the template.

**Enforcement:** `os.environ.get(...)` at the top of [src/config.py:80](../../src/config.py#L80). No fallback to disk file. CI does not persist secrets.

**Violation example:** Caching `OPENROUTER_API_KEY` into a YAML file for "offline runs" — the file ends up in backups and git.

---

## Constraint 9: Proxy credentials are read-only in the container

**Rule:** The `proxy-credentials` file is mounted `:ro` in [docker-compose.yml:12](../../docker-compose.yml#L12). The application reads it via `PROXY_CREDENTIALS_FILE.read_text()` and caches lines in memory. No write path exists in the code.

**Why:** Credentials come from the provider (proxy-cheap.com) and are rotated manually. The bot has no business rewriting them; any write would be a bug or an attack vector.

**Enforcement:** Only `_load_proxy_lines()` at [src/extractors/youtube.py:24](../../src/extractors/youtube.py#L24) reads the file. Compose mount is `:ro`.

**Violation example:** Adding a Telegram command to update proxies in-place. Instead, keep the read-only mount and document how to swap the file on the host.

---

## Constraint 10: LLM output must be validated before staging

**Rule:** The pipeline rejects the entry (returns `{"error": …}`) if `summarize_content` returns `None` — meaning the LLM failed, returned invalid JSON twice, or the response lacked required fields. The entry never reaches `pending.json` with missing summary bullets.

**Why:** A pending entry with empty bullets is a silent failure — the user approves it, writes garbage to Markdown, and the knowledge base decays. Fail fast, localized, and visible.

**Enforcement:** [src/pipeline.py:86](../../src/pipeline.py#L86):
```python
if not summary:
    return {"error": t("pipeline_err_summarize_failed", lang, title=title)}
```
And defaults in stage_kwargs (`summary.get("relevance_score", 5)`) protect against partial success.

**Violation example:** `stage_pending(..., summary_bullets=summary["summary_bullets"])` — KeyError on a malformed response crashes the scheduler. Always `.get(..., default)` at the staging boundary.

---

## Constraint 11: No silent merge across user namespaces during migration

**Rule:** `migrate_legacy_to_admin` must skip the knowledge-tree move if the admin's namespace already has content. See [src/migration.py:104](../../src/migration.py#L104).

**Why:** An operator running the migration twice (e.g. after restoring a partial backup) could merge old legacy entries with new per-user entries and double-count items, corrupt the index, or overwrite freshly-approved content.

**Enforcement:** Check `target.exists() and any(target.iterdir())` before moving. Log a warning and bail. Marker file `data/.migrated_v1` prevents re-runs entirely.

**Violation example:** "Let's make migration additive." No — migration is a one-shot. Use `_safe_move` (refuses to overwrite) + marker, never `shutil.copytree(..., dirs_exist_ok=True)`.

---

## Constraint 12: Path-traversal-safe category slugs

**Rule:** Category slugs never contain `..`, `/`, or `\`. Validated by `_validate_category` at [src/storage.py:145](../../src/storage.py#L145) before any filesystem use.

**Why:** Slugs come from user input (onboarding wizard, `/add … <category>`) and from LLM output. An attacker-controlled slug like `../../../../tmp/evil` would write outside the user's knowledge tree.

**Enforcement:** `_validate_category` is called from `save_entry`, `stage_pending`, and `update_pending_category`. Any new code path writing per-category must route through the same helper.

**Violation example:** Trusting the LLM-returned slug directly in a path join. Always validate first.
