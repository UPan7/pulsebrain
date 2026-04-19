# Module Map

> One-stop orientation for PulseBrain. File list per module + one-line description + cross-module edges + architecture rules per module.
>
> **How to use:** find the relevant module below, read "Entry points" and "Architecture rules", then locate specific files in the per-directory listing. Usually 2–4 file Reads are enough to act.
>
> **Update cadence:** update when adding or removing a `.py` file, changing an architectural rule for a module, or introducing a cross-module dependency. Do NOT update for trivial renames, comment changes, or tests.

## Related documents

- [SYSTEM_CONSTRAINTS.md](SYSTEM_CONSTRAINTS.md) — global non-negotiable rules
- [TECH_CONTEXT.md](TECH_CONTEXT.md) — stack & gotchas per library
- [../ARCHITECTURE.md](../ARCHITECTURE.md) — Mermaid diagrams of data flow
- [../DECISIONS.md](../DECISIONS.md) — ADR log
- [../../CLAUDE.md](../../CLAUDE.md) — project root guide

---

## Top-level layout

```
pulse-bot/
├── src/                          # All application code
│   ├── main.py                     # Entry point — config validate, migrate, start bot + scheduler
│   ├── config.py                   # Env parsing, per-user path helpers, categories & channels I/O, logger
│   ├── router.py                   # URL → source-type classification + video-ID extraction
│   ├── pipeline.py                 # Shared extract→summarize→categorize→stage flow
│   ├── scheduler.py                # APScheduler periodic RSS check per user
│   ├── summarize.py                # OpenRouter LLM summary + question-answering
│   ├── categorize.py               # OpenRouter LLM category inference + fuzzy-merge
│   ├── storage.py                  # Markdown writer, processed.json dedup, _index.md, search, stats
│   ├── pending.py                  # Approval queue (stage / commit / reject) + rejected log
│   ├── profile.py                  # Per-user persona YAML + relevance-context builder
│   ├── migration.py                # One-shot legacy → admin-namespace migrator
│   ├── telegram_bot.py             # All Telegram command handlers + inline keyboards
│   ├── onboarding.py               # Onboarding wizard state machine (pure logic)
│   ├── onboarding_presets.py       # Starter categories + empty starter-channel list
│   ├── strings.py                  # t() + SUPPORTED_LANGS — 10-language UI strings
│   └── extractors/
│       ├── youtube.py                # Transcript via proxied youtube-transcript-api, oEmbed, channel scrape, RSS IDs
│       └── web.py                    # Trafilatura download + clean extract
├── tests/                         # pytest suite (≥ 85 % coverage gate)
├── data/                          # Per-user runtime state (volume — created on first boot)
│   └── users/{chat_id}/           #   profile.yaml, channels.yml, categories.yml, processed.json, pending.json, rejected_log.jsonl
├── knowledge/                     # Per-user Markdown knowledge base (volume)
│   └── {chat_id}/_index.md        #   {category}/{YYYY}/{MM}/*.md + *.source.txt
├── docs/                          # Docs (this file lives here)
├── .github/workflows/deploy.yml   # CI/CD: push → scp → ssh → docker compose rebuild
├── .env.example                   # Config surface (env vars)
├── channels.yml                   # Legacy / bootstrap seed file (root); active channels are per-user under data/
├── proxy-1945686-credentials      # Proxy credentials file (gitignored in real deploys; mounted :ro)
├── Dockerfile                     # python:3.11-slim, single stage
├── docker-compose.yml             # One service, four volumes
├── requirements.txt               # Runtime + test deps
├── pyproject.toml                 # pytest + coverage config (85 % gate)
├── CLAUDE.md                      # Root guide for agents / humans
└── README.md                      # End-user quick-start
```

---

## src/ — core application

**What it is:** every runtime module. Flat layout with a single `extractors/` subpackage. Multi-tenant throughout.

**Entry point:** [main.py](../../src/main.py) — `python -m src.main`.

### Architecture rules (applies to every module in `src/`)

1. **First argument of every public function is `chat_id: int`** when the function touches per-user state. Return types never carry cross-user data.
2. **No globals for user state.** Per-user caches (`_*_caches`) are dicts keyed by `chat_id`, guarded by per-user locks (`_*_locks`).
3. **Atomic writes use `threading.Lock` + `.tmp` → `os.replace`.** Never partial JSON/YAML on disk.
4. **Errors never propagate past a handler / scheduler iteration.** Log, localize-and-notify, continue.
5. **User-visible text comes from `src.strings.t(key, lang, **kwargs)`.** Lang resolved from `src.profile.get_language(chat_id)`.

### Files (flat)

| File | Role |
|---|---|
| [`main.py`](../../src/main.py) | `main()` — validate env, ensure dirs, run migration once, per-user init for each allowed chat_id, schedule via `post_init`, `app.run_polling(drop_pending_updates=True)` |
| [`config.py`](../../src/config.py) | Parses `TELEGRAM_CHAT_IDS` (supports `id:Name`), exports path helpers `user_dir / user_profile_file / user_channels_file / user_categories_file / user_processed_file / user_pending_file / user_rejected_log_file / user_knowledge_dir`, owns `load_categories` / `add_category` / `load_channels` / `save_channels` with per-user locks, configures `logger` |
| [`router.py`](../../src/router.py) | `SourceType` constants; `detect_source_type(url)` for youtube_video / youtube_channel / web_article; `extract_video_id(url)` handles `youtu.be/X` and `?v=X` |
| [`pipeline.py`](../../src/pipeline.py) | Shared `_process_content()` — dedup check → extract (YouTube or web) → summarize → categorize → `stage_pending` → `mark_processed(status="pending")`. Public API: `process_youtube_video`, `process_web_article` |
| [`scheduler.py`](../../src/scheduler.py) | `fetch_channel_videos(channel_id)` RSS parse; `run_channel_check(chat_id, app)` iterates all enabled channels, processes new videos, auto-rejects < `min_relevance`, sends per-item notification + end-of-run digest (only on non-zero activity); `setup_scheduler(app)` registers one `IntervalTrigger` job that loops all allowed users |
| [`summarize.py`](../../src/summarize.py) | `summarize_content(chat_id, content, title, source_name, source_type, date)` — builds `LANGUAGE_DIRECTIVES[lang]` + user-context block from profile, calls OpenRouter, parses JSON, retries once on malformed output. `answer_question(chat_id, question, sources)` for `/search` follow-ups |
| [`categorize.py`](../../src/categorize.py) | `categorize_content(chat_id, title, content)` — LLM picks a slug; `_auto_merge()` pure fuzzy-match against existing categories at 0.75 threshold (catches `ai-agent`→`ai-agents`); falls back to `ai-news` on malformed slug or exception |
| [`storage.py`](../../src/storage.py) | `init_processed(chat_id)` / `is_processed` / `mark_processed` / `make_content_id(source_type, identifier)`. `save_entry(...)` writes Markdown + `.source.txt` sibling. `_update_index(chat_id)` regenerates `_index.md`. `move_entry` re-categorizes. `search_knowledge`, `search_for_question`, `get_recent_entries`, `get_entries_in_category`, `get_stats`, `entry_id`, `find_entry_by_id`, `read_entry_markdown`, `get_source_text_path`. TTL entry cache (60 s) per user |
| [`pending.py`](../../src/pending.py) | `init_pending` / `stage_pending` / `get_pending` / `list_pending` / `update_pending_category` / `commit_pending` (→ `save_entry` → `mark_processed(status="ok")`) / `reject_pending(reason)` (→ `_append_rejected_log` → `mark_processed(status="rejected")`). `read_rejected_log` for `/rejected` command |
| [`profile.py`](../../src/profile.py) | `init_profile` / `load_profile` (safe — falls through to defaults) / `save_profile` / `profile_exists` / `get_language`. `build_relevance_context(chat_id)` merges profile + top-categories + top-topics + recent-avg + rejected titles for summarize prompt. `format_relevance_context` flattens to a prompt-ready string |
| [`migration.py`](../../src/migration.py) | `migrate_legacy_to_admin(admin_chat_id)` — idempotent via `data/.migrated_v1` marker. Moves flat legacy files (`data/processed.json`, `channels.yml`, `knowledge/{category}/…`) into `data/users/{admin}/` + `knowledge/{admin}/`. Skips when admin namespace already has content (no silent merge) |
| [`telegram_bot.py`](../../src/telegram_bot.py) | 17 command handlers registered in `create_bot_application()` at line 1489. User-auth decorator, inline-keyboard callbacks for approve/reject/category-edit, `send_notification(app, chat_id, result)` called from scheduler |
| [`onboarding.py`](../../src/onboarding.py) | `STEPS = [lang, welcome, persona, learning, stack, notinterested, categories, channels, done]`. `CALLBACK_STEPS` vs text steps. `new_draft()`, `step_key(i)`, `next_step(i)`, `parse_multiline(text)`, `apply_draft(chat_id, draft)` writes profile + categories + channels |
| [`onboarding_presets.py`](../../src/onboarding_presets.py) | `PRESET_CATEGORIES` dict (10 slugs — superset of `config._DEFAULT_CATEGORIES`), `PRESET_CHANNELS = []` (wizard skips channel step when empty) |
| [`strings.py`](../../src/strings.py) | `t(key, lang, **kwargs)` single lookup with fallback chain → `en`. `SUPPORTED_LANGS = ["en","de","fr","es","it","pt","zh","ja","ru","ar"]`. Large (2727 LOC) because every template has 10 translations |

### Primary data sources

- **Telegram Bot API** (via `python-telegram-bot`) — inbound messages + outbound notifications, long-polling
- **YouTube RSS** (`https://www.youtube.com/feeds/videos.xml?channel_id=…`) — no auth, no rate limit
- **YouTube oEmbed** (`https://www.youtube.com/oembed`) — metadata; direct HTTP, no proxy
- **YouTube transcripts** (`youtube-transcript-api`) — via rotating proxy
- **YouTube channel page** (HTML scrape) — `resolve_channel_id()` regex against `externalId` / `channelId`
- **Any web article URL** (via trafilatura) — direct HTTP
- **OpenRouter API** (`https://openrouter.ai/api/v1/chat/completions`) — summarize + categorize + Q&A

### Cross-module edges (high-level)

```
main ──▶ config, migration, storage.init_processed, pending.init_pending,
          profile.init_profile, scheduler.setup_scheduler, telegram_bot.create_bot_application

telegram_bot ──▶ config, pipeline, storage (search/recent/find/stats),
                  pending (list/commit/reject), onboarding, profile,
                  strings, summarize (answer_question)

pipeline ──▶ router, extractors.youtube, extractors.web, summarize,
              categorize, pending (stage_pending), storage (is_processed/mark_processed/make_content_id),
              profile.get_language, strings

scheduler ──▶ pipeline, storage (is_processed/make_content_id), pending (reject_pending),
               profile.get_language, strings, telegram_bot.send_notification (optional)

summarize ──▶ config (LLM_MODEL / OPENROUTER_*), profile.build_relevance_context + format_relevance_context

categorize ──▶ config (LLM_MODEL / OPENROUTER_* / load_categories)

storage ──▶ config (KNOWLEDGE_DIR / user_*_file / user_knowledge_dir)

pending ──▶ config (user_pending_file / user_rejected_log_file),
             storage (_validate_category / mark_processed / save_entry)

profile ──▶ config (user_profile_file); read-only imports storage._get_all_entries
            and pending.read_rejected_log (lazy, inside functions to avoid cycles)

migration ──▶ config (LEGACY_* + user_* helpers + ensure_user_dirs)

onboarding ──▶ config (add_category / load_channels / save_channels),
                profile.save_profile, strings.SUPPORTED_LANGS

extractors.youtube ──▶ config (PROXY_CREDENTIALS_FILE / TRANSCRIPT_LANGUAGES)

extractors.web ──▶ trafilatura only (no internal deps)
```

---

## src/extractors/ — content extraction adapters

**What it is:** thin adapters to external content sources. No business logic, no storage writes. Each extractor returns plain data; the pipeline owns orchestration.

**Primary data source:** external URLs — YouTube (transcripts + metadata) and arbitrary web pages.

### Architecture rules (this module)

1. **Pure adapters.** Never mutate per-user state, never call Telegram, never call `logger.info` about user-visible events.
2. **Return `None` on total failure.** Never raise past the function boundary for expected failures (network, 404, empty article).
3. **Retries live here, not upstream.** YouTube transcripts retry 3× with exponential backoff before giving up; the pipeline assumes the adapter already tried.
4. **Proxies are only used where YouTube blocks VPS IPs.** Transcript + channel-page scrape use proxy; oEmbed and RSS do not (public endpoints, no rate issues observed).
5. **Caching is OK at this layer.** Proxy-credential lines are cached in `_proxy_lines` — cheap and file changes mid-run are not expected.

### Files

| File | Role |
|---|---|
| [`extractors/youtube.py`](../../src/extractors/youtube.py) | `_load_proxy_lines()` reads + caches `proxy-credentials`. `_make_proxy_config()` / `_get_random_proxy_dict()` pick random line per call. `get_transcript(video_id)` — `YouTubeTranscriptApi(proxy_config=…).fetch()` with 3 retries + exp backoff. `get_video_metadata(video_id)` — oEmbed title + channel (upload_date always `None` — oEmbed doesn't expose it). `resolve_channel_id(url)` — normalize handle → scrape externalId regex. `get_recent_video_ids(channel_id, count)` — feedparser RSS |
| [`extractors/web.py`](../../src/extractors/web.py) | `extract_web_article(url)` — `trafilatura.fetch_url` + `.extract(output_format='txt', include_comments=False, include_tables=True)` + `.extract_metadata()`. Rejects articles < 100 chars. Returns `{title, author, date, text, source_url, sitename}` or `None` |

### Cross-module edges

- **Consumes:** `src.config.PROXY_CREDENTIALS_FILE`, `src.config.TRANSCRIPT_LANGUAGES` (youtube only)
- **Publishes to:** `src.pipeline` (the only caller)
- **No internal deps beyond `config`.** Do not import from `storage` / `summarize` / anything else — keep adapters boundary-clean.

---

## tests/ — pytest suite

**What it is:** one test file per `src/` module plus cross-cutting integration tests. Coverage gate ≥ 85 % enforced in `pyproject.toml`.

**Entry point:** `pytest` (reads config from `pyproject.toml`), or `pytest tests/test_<module>.py -k <case>`.

### Architecture rules (this module)

1. **Filesystem is real, external I/O is faked.** Use `tmp_path` fixture for user dirs; mock OpenRouter client, `requests.get`, `feedparser.parse`, Telegram app.
2. **Multi-tenant invariant is a test requirement, not a nice-to-have.** When a test writes user state, it should also assert a second user is unaffected.
3. **Tests are co-located one-per-module.** `test_X.py` ↔ `src/X.py`. Cross-cutting goes into `test_multi_user.py` or `test_integration.py`.
4. **`asyncio_mode = "auto"`** — async tests don't need decorators.
5. **Coverage omits `__init__.py` only.** Every other line is counted.

### Files

| File | Covers |
|---|---|
| [`conftest.py`](../../tests/conftest.py) | Shared fixtures (tmp user dirs, faked config paths, env resets) |
| [`test_main.py`](../../tests/test_main.py) | `_validate_config`, `_ensure_directories`, startup orchestration |
| [`test_config.py`](../../tests/test_config.py) | `_parse_chat_entries` (id, id:Name, mixed, dedup), `load_categories` merge, `add_category` |
| [`test_router.py`](../../tests/test_router.py) | `detect_source_type` + `extract_video_id` across URL shapes |
| [`test_pipeline.py`](../../tests/test_pipeline.py) | `process_youtube_video` + `process_web_article` — happy path, duplicate, transcript-fail, summarize-fail, category passthrough |
| [`test_scheduler.py`](../../tests/test_scheduler.py) | `run_channel_check` — relevance gate, auto-reject, notification, digest only on non-zero, per-channel `min_relevance` |
| [`test_extractors.py`](../../tests/test_extractors.py) | YouTube transcript retries, metadata oEmbed fallback, `resolve_channel_id`, `get_recent_video_ids` |
| [`test_extractors_web.py`](../../tests/test_extractors_web.py) | Trafilatura happy path, short-article rejection, metadata absence |
| [`test_summarize.py`](../../tests/test_summarize.py) | LLM JSON retry, language directive selection, relevance-context injection, `answer_question` |
| [`test_categorize.py`](../../tests/test_categorize.py) | Exact match, `_auto_merge` threshold, new-slug acceptance, malformed-slug fallback to `ai-news` |
| [`test_storage.py`](../../tests/test_storage.py) | Markdown writing, `make_content_id`, dedup cache, `_index.md`, search scoring, `move_entry`, `get_stats` |
| [`test_pending.py`](../../tests/test_pending.py) | Stage → commit (writes `.md`, `.source.txt`, marks `ok`), stage → reject (log + `rejected` status), `read_rejected_log`, `update_pending_category` |
| [`test_profile.py`](../../tests/test_profile.py) | `load_profile` default fill, `save_profile` atomicity, `get_language` normalization, `build_relevance_context` aggregation |
| [`test_migration.py`](../../tests/test_migration.py) | Marker-guard idempotency, knowledge-tree move, admin-namespace conflict skip, fresh-install marker |
| [`test_onboarding.py`](../../tests/test_onboarding.py) | `STEPS` order, `apply_draft` side effects (profile + categories + channels), multilingual language pick |
| [`test_telegram_bot.py`](../../tests/test_telegram_bot.py) | Auth gate (only allowed chat_ids), `/add` URL routing, approve/reject callback, language switch |
| [`test_strings.py`](../../tests/test_strings.py) | `t()` key coverage per lang, fallback to `en`, parametrized substitution |
| [`test_multi_user.py`](../../tests/test_multi_user.py) | Two chat_ids produce two disjoint trees; shared content → two independent summaries |
| [`test_integration.py`](../../tests/test_integration.py) | End-to-end: drop link → notification → approve → `.md` on disk |

### Cross-module edges

- **Consumes:** every `src/` module
- **Publishes:** coverage report (terminal) + pass/fail signal for CI

---

## Root-level state & config

### Files

| File | Role | Writable by |
|---|---|---|
| [`.env.example`](../../.env.example) | Template: `OPENROUTER_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_IDS` (supports `id:Name`), `CHECK_INTERVAL_MINUTES` (default 30), `MIN_RELEVANCE_THRESHOLD` (default 4), `TRANSCRIPT_LANGUAGES` (default `en,de,ru`), `LOG_LEVEL` | operator (manual) |
| [`channels.yml`](../../channels.yml) | Legacy root-level channel list; first boot migrates it to admin's `data/users/{admin}/channels.yml` and stops reading it. Kept for bootstrap seeding on fresh deploys | operator for seed, migrator for move |
| `proxy-1945686-credentials` | Proxy creds, one `user:pass@host:port` per line. Mounted `:ro` into container at `/app/proxy-credentials` | operator, never the bot |
| [`Dockerfile`](../../Dockerfile) | `python:3.11-slim`, copies `requirements.txt` → pip install → `src/` + `channels.yml`; CMD `python -m src.main` | CI |
| [`docker-compose.yml`](../../docker-compose.yml) | Single service `yt-knowledge-bot` (container `pulsebrain`); volumes for `knowledge/`, `data/`, `channels.yml`, `proxy-1945686-credentials:/app/proxy-credentials:ro`; JSON-file logs (10 MB × 3) | operator |
| [`pyproject.toml`](../../pyproject.toml) | `pytest.asyncio_mode = "auto"`; `addopts = "--cov=src --cov-report=term-missing --cov-fail-under=85"`; coverage omits only `__init__.py` | dev |
| [`requirements.txt`](../../requirements.txt) | Runtime: openai≥1.0, python-telegram-bot≥21, apscheduler≥3.10, feedparser≥6.0, pyyaml≥6.0, youtube-transcript-api≥1.0, requests, python-slugify≥8.0, trafilatura≥2.0. Testing: pytest≥8.0, pytest-asyncio, pytest-cov | dev |
| [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml) | On push to `main`: `scp` `src/ requirements.txt Dockerfile docker-compose.yml` to Hetzner (`91.99.143.15`); `ssh` `docker compose build --no-cache && up -d && image prune -f` | CI |

### State files schema (per-user, under `data/users/{chat_id}/`)

```yaml
# profile.yaml
language: en | de | fr | es | it | pt | zh | ja | ru | ar
persona: "free-text short persona string"
skill_level: "free-text (e.g. 'senior backend')"
known_stack: [tag, tag]
already_comfortable_with: [tag]
actively_learning: [tag]
not_interested_in: [tag]
```

```yaml
# channels.yml
channels:
  - name: "Cole Medin"
    id: "UCmHzpwaNEMgz2Do3IfJbXzg"
    category: "ai-agents"
    enabled: true
    min_relevance: 4    # optional per-channel override
```

```yaml
# categories.yml — flat slug → description map, merged over _DEFAULT_CATEGORIES
ai-agents: "AI Agents & Multi-Agent"
custom-slug: "User-added description"
```

```jsonc
// processed.json
{
  "yt:dQw4w9WgXcQ": { "status": "ok",        "processed_at": "2026-04-19T10:12:03+00:00" },
  "yt:abc123":      { "status": "rejected",  "processed_at": "2026-04-19T10:13:45+00:00" },
  "web:a1b2c3d4e5f6…": { "status": "pending","processed_at": "2026-04-19T10:15:00+00:00" }
}
```

```jsonc
// pending.json — keyed by pending_id = sha256(content_id)[:8]
{
  "a1b2c3d4": {
    "id": "a1b2c3d4",
    "content_id": "yt:…",
    "source_url": "…",
    "source_type": "youtube_video" | "web_article",
    "source_name": "…",
    "title": "…",
    "date_str": "YYYY-MM-DD" | null,
    "category": "slug",
    "is_new_category": false,
    "relevance": 1..10,
    "topics": ["…"],
    "summary_bullets": ["…"],
    "detailed_notes": "…",
    "key_insights": ["…"],
    "action_items": ["…"],
    "author": "…" | null,
    "sitename": "…" | null,
    "raw_text": "…" | null,
    "created_at": "iso"
  }
}
```

```jsonc
// rejected_log.jsonl — append-only, newest lines at the bottom
{"ts":"iso","pending_id":"…","title":"…","source_name":"…","source_url":"…","source_type":"…","relevance":4,"reason":"low_relevance" | "manual"}
```

### Knowledge tree schema

```
knowledge/{chat_id}/
├── _index.md                              # regenerated on every save / move
└── {category}/{YYYY}/{MM}/
    ├── {source-slug}_{title-slug}_{date}.md
    └── {source-slug}_{title-slug}_{date}.source.txt   # lossless original
```

`.md` starts with `# {title}` then a metadata list (`- **Source:** …`), then `## Summary`, `## Detailed Notes`, `## Key Insights`, `## Action Items` sections. Parsed back out by `_parse_entry_metadata` at [src/storage.py:430](../../src/storage.py#L430).
