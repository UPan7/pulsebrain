# PulseBrain

## What this is

Self-hosted Telegram bot that builds a personal, multi-tenant knowledge base by monitoring YouTube channels on a schedule and processing user-dropped links (YouTube videos + web articles). One container, one bot, many allowed users; each user has an isolated data tree. UI is multilingual (RU / EN / DE / FR / ES / IT / PT / ZH / JA / AR) — picked per-user via the onboarding wizard.

## Stack

- **Language:** Python 3.11+, type hints everywhere (`from __future__ import annotations`)
- **Telegram:** `python-telegram-bot >=21` (async)
- **Scheduler:** APScheduler (`AsyncIOScheduler` + `IntervalTrigger`)
- **YouTube:** `youtube-transcript-api` (transcripts) + oEmbed API (metadata) + HTML scrape (channel-ID resolve) + `feedparser` (RSS listing)
- **Web articles:** `trafilatura`
- **LLM:** OpenAI SDK → OpenRouter (`openai/gpt-5.4-nano`) for both summarization and category inference
- **Proxies:** rotating residential (proxy-cheap.com) via file-backed credentials, random pick per request
- **Storage:** Markdown files + `.source.txt` siblings in `knowledge/{chat_id}/…`; state in JSON / YAML under `data/users/{chat_id}/`
- **Tests:** pytest + pytest-asyncio + pytest-cov; 85 % coverage gate
- **Deploy:** Docker (Python 3.11-slim) on Hetzner CAX21 (ARM64); CI via GitHub Actions → SSH + SCP

## Architecture rules (non-negotiable)

1. **No database.** Knowledge lives as Markdown. State lives as JSON (processed, pending) or YAML (profile, channels, categories). If you catch yourself wanting SQL, first write an ADR.
2. **Multi-tenant via `chat_id` threading.** Every handler, pipeline, storage, summarize, and pending call takes `chat_id` as its first argument. No globals, no "current user". See [src/config.py:120](src/config.py#L120) for per-user path helpers.
3. **Per-user isolation is total.** Caches, locks, files, even LLM context. Two users who encounter the same video each get their own summary with their own relevance.
4. **All state writes are atomic.** Thread lock + `.tmp` file + `os.replace`. See [src/storage.py:61](src/storage.py#L61), [src/pending.py:63](src/pending.py#L63), [src/profile.py:99](src/profile.py#L99).
5. **Bot only responds to `TELEGRAM_CHAT_IDS` allowlist.** The first id is the admin; they receive legacy-migration artifacts. Unauthorized messages are silently ignored.
6. **All user-facing strings go through `src.strings.t(key, lang, **kwargs)`.** No bare literals in handlers. Adding a string means adding 10 translations. See [src/strings.py](src/strings.py).
7. **Content IDs are canonical.** `yt:{video_id}` for YouTube, `web:{sha256(url)[:16]}` for articles. Never random UUIDs. See [src/storage.py:100](src/storage.py#L100).
8. **Never crash on single-item failure.** Log + notify user + continue with next item. One user's scheduler error must not break the others. See [src/scheduler.py:196](src/scheduler.py#L196).
9. **LLM output is validated before staging.** Relevance ∈ [1,10], non-empty bullets. See [src/pipeline.py:86](src/pipeline.py#L86).
10. **Proxy credentials are read-only in the container.** Mounted `:ro`. See [docker-compose.yml:12](docker-compose.yml#L12).
11. **Secrets via env vars only.** Never committed; `.env.example` shows the shape.

## Modules

| Name | Path | Purpose | Status |
|---|---|---|---|
| Entry | [src/main.py](src/main.py) | Startup: config validation, per-user init, scheduler wiring, `run_polling()` | stable |
| Config | [src/config.py](src/config.py) | Env parsing, per-user path helpers, categories I/O, channels I/O, logging | stable |
| Router | [src/router.py](src/router.py) | URL → `youtube_video` / `youtube_channel` / `web_article`; `extract_video_id()` | stable |
| Pipeline | [src/pipeline.py](src/pipeline.py) | extract → summarize → categorize → stage (per `chat_id`) | stable |
| Scheduler | [src/scheduler.py](src/scheduler.py) | Periodic RSS check per user; relevance gate; optional notifications + digest | stable |
| YouTube extractor | [src/extractors/youtube.py](src/extractors/youtube.py) | Transcripts via proxy + retry; oEmbed metadata; channel-ID scrape; RSS IDs | stable |
| Web extractor | [src/extractors/web.py](src/extractors/web.py) | Trafilatura download + extract; title/author/date/text | stable |
| Summarize | [src/summarize.py](src/summarize.py) | OpenRouter JSON prompt; bullets, notes, insights, actions, relevance; `answer_question()` | stable |
| Categorize | [src/categorize.py](src/categorize.py) | LLM picks slug; fuzzy merge ≥ 0.75 into existing | stable |
| Storage | [src/storage.py](src/storage.py) | Markdown writer, `_index.md` rebuild, dedup `processed.json`, search, stats, entry IDs | stable |
| Pending | [src/pending.py](src/pending.py) | Approval queue (stage / commit / reject), rejected log, per-user locks | stable |
| Profile | [src/profile.py](src/profile.py) | Per-user YAML; language + persona + learning targets; `build_relevance_context()` | stable |
| Migration | [src/migration.py](src/migration.py) | One-shot legacy → admin-namespace migrator; marker-guarded idempotent | stable |
| Telegram bot | [src/telegram_bot.py](src/telegram_bot.py) | All command handlers, inline keyboards, notification helpers | stable, large (1511 LOC) |
| Onboarding | [src/onboarding.py](src/onboarding.py) | Pure state machine (STEPS, draft, apply) — no Telegram imports | stable |
| Onboarding presets | [src/onboarding_presets.py](src/onboarding_presets.py) | Starter categories + empty channel list | stable |
| Strings | [src/strings.py](src/strings.py) | `t()` + SUPPORTED_LANGS; 10-language templates | stable, large (2727 LOC) |

## Key files

| File | Role |
|---|---|
| [src/main.py](src/main.py) | Orchestrates startup: validate config → ensure dirs → migrate → per-user init → scheduler `post_init` → polling |
| [src/config.py](src/config.py) | Single source of truth for env + paths; adding a new env var starts here |
| [src/pipeline.py](src/pipeline.py) | The shared fetch-summarize-stage flow. Both `/add` and scheduler funnel through here |
| [src/telegram_bot.py](src/telegram_bot.py) | ~17 command handlers + `send_notification()` + inline keyboard callbacks |
| [src/strings.py](src/strings.py) | All UI text. Never hardcode a literal in a handler |
| [src/storage.py](src/storage.py) | Markdown layout, dedup, atomic writes, TTL entry cache (60 s) |
| [src/pending.py](src/pending.py) | The approve-or-reject contract. Entries never hit disk until committed |
| [.env.example](.env.example) | Config surface; copy → `.env` |
| [docker-compose.yml](docker-compose.yml) | Container contract: volumes, proxy mount, logging |
| [channels.yml](channels.yml) | Legacy shape, kept for reference / bootstrap; active channels live under `data/users/{chat_id}/channels.yml` |

## Telegram commands

Registered in [src/telegram_bot.py:1489-1505](src/telegram_bot.py#L1489).

| Command | Purpose |
|---|---|
| `/start` | First-run wizard or welcome |
| `/help` | All commands in user's language |
| `/onboarding` | Re-run the wizard |
| `/language` | Switch UI language without wizard |
| `/add <url> [category]` | Add YouTube channel OR drop a link for immediate processing |
| `/remove` | Pause/remove a tracked channel |
| `/list` | All channels with enabled/paused status |
| `/categories` | Categories + counts + last date + avg relevance |
| `/search <query>` | Keyword search; returns entry IDs |
| `/recent [n]` | Latest n entries (default 5) |
| `/get [id]` | Browse by category picker or fetch a specific entry (incl. `.source.txt`) |
| `/status` | Quick counters |
| `/stats` | Per-category health, top sources, weekly summary |
| `/pending` | Staged entries with approve/reject keyboard |
| `/rejected [n]` | Auto-rejected entries with reason |
| `/run` | Force immediate scheduler cycle for the caller |
| `/cancel` | Abort any in-progress wizard step |

## Commands (shell)

```bash
# Dev loop
pip install -r requirements.txt
python -m src.main

# Tests (85% coverage gate enforced via pyproject.toml)
pytest
pytest tests/test_pipeline.py -k process_youtube_video

# Container
docker compose build
docker compose up -d
docker compose logs -f

# Deploy (CI on push to main, scp → ssh → compose rebuild)
git push origin main
```

## Testing methodology

- **Style:** integration-first with heavy use of fakes for external I/O (LLM, HTTP, Telegram). Pure logic modules (`router`, `categorize._auto_merge`, `onboarding`) have narrow unit tests.
- **Coverage gate:** ≥ 85 % enforced by [pyproject.toml:4](pyproject.toml#L4); CI fails otherwise.
- **Test location:** co-located as `tests/test_<module>.py`; one file per `src/` module + cross-cutting `test_multi_user.py`, `test_integration.py`.
- **Runner:** `pytest` with `asyncio_mode = "auto"`.
- **What to mock:** OpenRouter client, `youtube-transcript-api`, `requests.get`, `feedparser.parse`, Telegram `app.bot.send_message`.
- **What NOT to mock:** filesystem (use `tmp_path`), YAML / JSON parsers, stdlib.
- **Multi-tenant invariant:** every test that touches state must assert isolation — two `chat_id`s, two trees, no cross-contamination. See [tests/test_multi_user.py](tests/test_multi_user.py).

## State files per user

Under `data/users/{chat_id}/`:

| File | Shape | Writer | Reader |
|---|---|---|---|
| `profile.yaml` | language, persona, skill_level, known_stack[], actively_learning[], already_comfortable_with[], not_interested_in[] | onboarding, `/language` | summarize (relevance context) |
| `channels.yml` | `{channels: [{name, id, category, enabled, min_relevance?}]}` | `/add`, `/remove`, wizard | scheduler |
| `categories.yml` | `{slug: description}` (merged over defaults) | `/add`, wizard, auto-add on new-category | categorize, `/categories` |
| `processed.json` | `{content_id: {status: pending|ok|rejected, processed_at}}` | pipeline, pending | dedup checks |
| `pending.json` | `{pending_id: {content_id, title, summary_bullets, …}}` | pipeline (stage), approve/reject | `/pending`, scheduler auto-reject |
| `rejected_log.jsonl` | one JSON record per reject | pending.reject_pending | `/rejected` |

Under `knowledge/{chat_id}/`:

- `_index.md` — regenerated on every write / move
- `{category}/{YYYY}/{MM}/{source-slug}_{title-slug}_{date}.md` — the entry
- `{…}.source.txt` — lossless transcript / article body sibling

## Error handling

Every external call has a defined failure mode. The bot never crashes.

| Scenario | Code location | Outcome |
|---|---|---|
| No transcript after 3 attempts | [src/extractors/youtube.py:71](src/extractors/youtube.py#L71) | Return `None` → pipeline returns `{"error": …}` → caller notifies user in their language |
| oEmbed metadata fails | [src/extractors/youtube.py:87](src/extractors/youtube.py#L87) | Fall through to `{"title": None, …}`; pipeline uses `f"Video {video_id}"` |
| Trafilatura returns < 100 chars | [src/extractors/web.py:33](src/extractors/web.py#L33) | Return `None` → pipeline errors out with `pipeline_err_web_extract_failed` |
| LLM returns malformed JSON | [src/summarize.py:213](src/summarize.py#L213) | Retry once; on second failure return `None` → pipeline aborts the item |
| OpenRouter API error | [src/summarize.py:218](src/summarize.py#L218) | Retry once; on second failure return `None` |
| Category slug outside alnum + dash | [src/categorize.py:88](src/categorize.py#L88) | Default to `ai-news`, log warning |
| Duplicate content | [src/pipeline.py:43](src/pipeline.py#L43) | Return `pipeline_err_*_already_processed` — localized message |
| Telegram send fails in scheduler | [src/scheduler.py:115](src/scheduler.py#L115) | Log warning; scheduler cycle continues |
| Scheduler raises for one user | [src/scheduler.py:196](src/scheduler.py#L196) | Log error; loop continues to next `chat_id` |
| Proxy file missing | [src/extractors/youtube.py:30](src/extractors/youtube.py#L30) | Warn once; fall back to direct requests |
| Round digest delivery fails | [src/scheduler.py:175](src/scheduler.py#L175) | Swallowed — never fail the scheduler for a flaky notification |

## Docs update protocol

**After a structural change:**
1. Update the relevant module doc in [docs/](docs/) — at minimum [MODULE_MAP.md](docs/system-context/MODULE_MAP.md).
2. Update this file if project-level context changed (new module, new env var, new architecture rule).
3. Add an entry to [docs/DECISIONS.md](docs/DECISIONS.md) for any architecture-level decision.
4. Add a one-liner to [docs/CHANGELOG.md](docs/CHANGELOG.md).

**Update cadence:**
- Add / remove a `src/` file → MODULE_MAP.md
- Change an architecture rule or env var → CLAUDE.md + MODULE_MAP.md + SYSTEM_CONSTRAINTS.md
- Choose a new technology → TECH_CONTEXT.md + ADR in DECISIONS.md
- Rename a helper function → skip; docs should not track renames

**Do not update docs for:** trivial refactors, comment changes, test-only additions, string-table additions in a supported language.

## Key project documents

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — Mermaid diagrams: overview, data flow, multi-tenant isolation, deploy topology
- [docs/system-context/MODULE_MAP.md](docs/system-context/MODULE_MAP.md) — **Open this first.** Per-module file listing, entry points, cross-module edges
- [docs/system-context/SYSTEM_CONSTRAINTS.md](docs/system-context/SYSTEM_CONSTRAINTS.md) — Non-negotiable rules with enforcement
- [docs/system-context/TECH_CONTEXT.md](docs/system-context/TECH_CONTEXT.md) — Stack versions, rationale, gotchas
- [docs/DECISIONS.md](docs/DECISIONS.md) — ADR log
- [docs/CHANGELOG.md](docs/CHANGELOG.md) — Reverse-chron change log
- [README.md](README.md) — End-user installation & quick-start
