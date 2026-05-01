# Tech Context

> Per-technology reference: what we use, why, where, conventions, and gotchas that bit us.
>
> **Update cadence:** update when adding / removing / upgrading a library, or when a new gotcha is discovered. A version bump alone does not need an update unless the API surface changed.

## Related documents

- [MODULE_MAP.md](MODULE_MAP.md) — module layout referenced below
- [SYSTEM_CONSTRAINTS.md](SYSTEM_CONSTRAINTS.md) — enforced rules
- [../DECISIONS.md](../DECISIONS.md) — why each stack choice

---

## Python 3.11+

**Version pin:** `python:3.11-slim` in [Dockerfile](../../Dockerfile).

**Why chosen:** Type hints with `from __future__ import annotations` work without quoting forward refs; `asyncio` performance; wide library support for the deps we use.

**Where used:** Everywhere.

**Conventions:**
- `from __future__ import annotations` at the top of every `src/` module.
- Full type hints on function signatures — `dict[str, Any]`, `list[str]`, `int | None`, no legacy `Dict`/`List`.
- Prefer `pathlib.Path` over `os.path`.
- Prefer `datetime.now(timezone.utc)` over naive `datetime.now()`.

**Gotchas:**
- 3.11 slim base image is ARM64-clean — required for Hetzner CAX21.
- `typing.Any` in YAML-loaded dicts: be explicit about `dict[str, Any]` to keep mypy/pyright happy.

---

## python-telegram-bot (>= 21)

**Version pin:** `python-telegram-bot>=21.0` in [requirements.txt](../../requirements.txt).

**Why chosen:** Async-first API matches APScheduler's `AsyncIOScheduler`. Mature inline-keyboard + callback-data support. Long-polling "just works" — no webhook plumbing.

**Where used:** [src/telegram_bot.py](../../src/telegram_bot.py), startup in [src/main.py](../../src/main.py), outbound notifications from [src/scheduler.py](../../src/scheduler.py).

**Conventions:**
- Long-polling with `app.run_polling(drop_pending_updates=True)` — stale messages from downtime are discarded.
- `post_init` hook starts the scheduler so it participates in the same event loop as the bot.
- `callback_data` is capped at **64 bytes** — this is why we use `entry_id = sha256(path)[:8]` (see [src/storage.py:261](../../src/storage.py#L261)).
- Every handler first calls the allowlist check (see [SYSTEM_CONSTRAINTS.md](SYSTEM_CONSTRAINTS.md) Constraint 4).

**Gotchas:**
- `InlineKeyboardButton(callback_data=…)` payload must be ≤ 64 bytes — URLs and long paths won't fit.
- Bot API exposes no message history — tests and error recovery must not rely on looking up old messages.
- `ConversationHandler` was deliberately avoided — the onboarding wizard uses plain `context.user_data["onboarding_step"]` (index into `STEPS`) because ConversationHandler's state routing collides with global command handlers like `/cancel`.

---

## APScheduler (>= 3.10)

**Version pin:** `apscheduler>=3.10.0`.

**Why chosen:** In-process scheduling with `AsyncIOScheduler` — no Celery, no Redis, no external worker. One job, one interval, done.

**Where used:** [src/scheduler.py](../../src/scheduler.py).

**Conventions:**
- Single `IntervalTrigger(minutes=CHECK_INTERVAL_MINUTES)` job. Iterating users happens inside the job (not one job per user) so adding a user doesn't require scheduler restart.
- `id="channel_check"` + `replace_existing=True` makes scheduler setup idempotent.
- Scheduler is started from the Telegram bot's `post_init` so it lives in the same event loop.

**Gotchas:**
- If the job raises, APScheduler logs but keeps the schedule alive. We still wrap each per-user iteration in `try/except` to avoid letting one user's failure swallow the rest — see Constraint 5.
- `AsyncIOScheduler` must be started after the event loop exists; starting it before `app.run_polling()` blows up.

---

## OpenAI SDK → OpenRouter

**Version pin:** `openai>=1.0.0` (the 1.x client; OpenRouter implements the `/v1/chat/completions` endpoint). Model: `openai/gpt-5.4-nano` (constant at [src/config.py:106](../../src/config.py#L106)).

**Why chosen:** OpenRouter lets us swap models without changing code and gives per-token pricing across providers. `openai>=1.x` client speaks its protocol.

**Where used:** [src/summarize.py](../../src/summarize.py) (summary + Q&A), [src/categorize.py](../../src/categorize.py) (category inference).

**Conventions:**
- Base URL override: `openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=…)`.
- JSON-only response: the prompt explicitly says "no markdown fences, no commentary." Parse with `json.loads()`; retry once on `JSONDecodeError`.
- `max_tokens=4096` for summarize, `max_tokens=50` for categorize — the latter returns only a slug.
- Summarize prompt injects a per-user `USER CONTEXT` block built from `profile.build_relevance_context(chat_id)` so relevance scoring is anchored to the caller's interests.

**Gotchas:**
- `openai.APIError` must be caught separately from generic `Exception` — it carries useful request-id info for debugging.
- Model returns valid-shaped JSON 99 % of the time; the retry-once logic handles the 1 % without exploding the bot.
- Cost model: summarize is the expensive call (~4 k completion tokens per video). Keep the content truncation at 100 k chars to avoid runaway bills on long podcasts.

---

## youtube-transcript-api (>= 1.0)

**Version pin:** `youtube-transcript-api>=1.0.0`.

**Why chosen:** No official YouTube API call for captions without OAuth and without quota pain. This library scrapes the caption track that YouTube exposes to the web player.

**Where used:** [src/extractors/youtube.py](../../src/extractors/youtube.py) — `get_transcript()`.

**Conventions:**
- Always pass `languages=TRANSCRIPT_LANGUAGES` (default `en,de,ru`). The API picks the first available caption track — order matters.
- Wrap every call in a 3-attempt retry loop with exponential backoff (`1 s, 2 s, 4 s`). See [src/extractors/youtube.py:71](../../src/extractors/youtube.py#L71).
- Use `GenericProxyConfig(http_url=…, https_url=…)` when `proxy-credentials` is present. Fall back to direct when missing.

**Gotchas:**
- **YouTube blocks data-center IPs aggressively.** A bare VPS run will fail transcript fetches within hours. Residential proxy rotation is non-optional on cloud.
- The library renamed methods in 1.0 — if you see `youtube_transcript_api.YouTubeTranscriptApi.get_transcript(video_id)` in tutorials, that's pre-1.0 API. We use `api = YouTubeTranscriptApi(proxy_config=…)` + `api.fetch(video_id, languages=…)` which is the 1.x shape.
- A video with no captions raises — we catch `Exception` generically because the library throws half a dozen different exception classes.

---

## feedparser (>= 6.0)

**Version pin:** `feedparser>=6.0.0`.

**Why chosen:** YouTube channels expose RSS at `https://www.youtube.com/feeds/videos.xml?channel_id=…` — no API key, no quota. Feedparser handles the (weirdly non-standard) YouTube RSS shape.

**Where used:** [src/extractors/youtube.py](../../src/extractors/youtube.py) (`get_recent_video_ids`), [src/scheduler.py](../../src/scheduler.py) (`fetch_channel_videos`).

**Conventions:**
- Extract `entry.get("yt_videoid", "")` — feedparser normalizes YouTube's `yt:videoId` namespace to that key.
- Fall back to parsing `entry["link"]` for `watch?v=…` if `yt_videoid` is absent.
- Limit to 10 entries per feed — YouTube RSS returns 15 by default, we only need recent.

**Gotchas:**
- YouTube RSS does not rate-limit, but it's cached — newly-uploaded videos may take 5–15 minutes to appear.
- No `published` date precision beyond minutes; use `entry.get("published")` as a fallback when oEmbed's `upload_date` is `None` (which is always — oEmbed doesn't expose it).

---

## trafilatura (>= 2.0)

**Version pin:** `trafilatura>=2.0.0`.

**Why chosen:** Best-in-class article text extraction. Handles boilerplate stripping, sitename detection, paywalls' `noscript` content. Readability-style parsers exist (readability-lxml, newspaper3k) but trafilatura has the best benchmarks and is still maintained.

**Where used:** [src/extractors/web.py](../../src/extractors/web.py).

**Conventions:**
- `trafilatura.fetch_url(url)` downloads. `trafilatura.extract(raw, output_format='txt', include_comments=False, include_tables=True)` extracts body. `trafilatura.extract_metadata(raw)` for title/author/date/sitename.
- Reject articles with `len(text) < 100` — almost always means extraction failed.

**Gotchas:**
- `fetch_url` uses its own HTTP client — does not go through our proxy. This is intentional (articles aren't behind YouTube's IP ban), but don't rely on proxy rotation for articles.
- `metadata.date` comes back in varied shapes (`"2025-04-13"`, `"2025-04-13T10:00:00"`, sometimes `None`); downstream code handles all three.

---

## PyYAML (>= 6.0)

**Version pin:** `pyyaml>=6.0`.

**Why chosen:** Standard for Python YAML. `safe_load` prevents arbitrary-Python execution that the default `yaml.load` allows.

**Where used:** [src/config.py](../../src/config.py) (channels, categories), [src/profile.py](../../src/profile.py), [src/onboarding.py](../../src/onboarding.py).

**Conventions:**
- Always `yaml.safe_load` — never `yaml.load`.
- Always `yaml.dump(..., allow_unicode=True, default_flow_style=False, sort_keys=False)` — we want Cyrillic / CJK readable, block style, and insertion-order preservation.
- Writes go through the `.tmp` + `os.replace` pattern (Constraint 3).

**Gotchas:**
- `safe_load` returns `None` for empty files — every reader must guard: `data = yaml.safe_load(f) or {}`.
- Python 3.11's `yaml.safe_dump` emits `true`/`false` (not `True`/`False`) — our file format is consistent with YAML 1.1.

---

## requests (>= 2.31)

**Version pin:** `requests>=2.31.0`.

**Why chosen:** Simplest HTTP client for the oEmbed endpoint and channel-page scrape. Not worth pulling in httpx for two synchronous calls.

**Where used:** [src/extractors/youtube.py](../../src/extractors/youtube.py) — oEmbed metadata + `resolve_channel_id` HTML scrape.

**Conventions:**
- `timeout=15` on every call — never unbounded.
- Custom `User-Agent` for channel-page scrape to avoid bot-detection heuristics: `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"`.

**Gotchas:**
- `resp.json()` raises on non-JSON responses — always check `resp.status_code == 200` first.

---

## python-slugify (>= 8.0)

**Version pin:** `python-slugify>=8.0.0`.

**Why chosen:** Title slugs need Unicode transliteration (Russian, German, Chinese titles → ASCII slug) + length cap + separator consistency. Rolling our own is error-prone.

**Where used:** [src/storage.py](../../src/storage.py) — `_build_file_path`.

**Conventions:**
- `slugify(title, max_length=60)` for titles, `slugify(source_slug, max_length=30)` for channel / site names.
- Final filename cap at 100 chars (Windows path length ceiling).

**Gotchas:**
- Handles are transliterated to ASCII — `"@cole-medin"` works, `"Коля Медин"` becomes `"kolia-medin"`. Source name lookup still works because we store the human name in entry metadata, not the slug.

---

## pytest + pytest-asyncio + pytest-cov

**Version pins:** `pytest>=8.0.0`, `pytest-asyncio>=0.23.0`, `pytest-cov>=4.0.0`.

**Why chosen:** Industry standard. `pytest-asyncio`'s `asyncio_mode = "auto"` means async tests don't need decorators. `pytest-cov` enforces the 85 % gate.

**Where used:** [tests/](../../tests/), config in [pyproject.toml](../../pyproject.toml).

**Conventions:**
- `tmp_path` fixture for per-user filesystem state — never touch the real `data/` or `knowledge/` directories.
- Mock external I/O (OpenRouter, requests, feedparser, Telegram app) with `unittest.mock.patch` or injected fakes.
- One test file per `src/` module, plus `test_multi_user.py` and `test_integration.py` for cross-cutting.

**Gotchas:**
- `asyncio_mode = "auto"` means every test runs in an event loop — synchronous tests still work but have tiny overhead.
- Coverage `omit` list only excludes `__init__.py`; keep it tight. If a file can't be tested (e.g. `main.py` needing a real event loop), refactor the untested branch out.

---

## Docker + docker compose

**Version pin:** `python:3.11-slim` base. Compose file format `version: '3.8'`.

**Why chosen:** Single-container deploy targets a single small VPS. Compose gives us declarative volumes + restart policy + log rotation without orchestration overhead.

**Where used:** [Dockerfile](../../Dockerfile), [docker-compose.yml](../../docker-compose.yml).

**Conventions:**
- Single service `yt-knowledge-bot` named `pulsebrain`.
- Four volumes: `knowledge/` (RW), `data/` (RW), `channels.yml` (RW — for legacy bootstrap migration), `proxy-credentials` (RO).
- `restart: unless-stopped` — survives host reboots, stops when explicitly stopped.
- JSON-file logs with 10 MB × 3 rotation — Docker default would be unbounded.

**Gotchas:**
- `--no-cache` on rebuild in CD — skipping it caused stale pip layers to mask requirement updates in practice.
- `proxy-credentials` mount is `:ro` (see Constraint 9); mounting it RW is a bug.
- Changing `channels.yml` at the root does not affect already-migrated users — root `channels.yml` is only read on first boot by the migrator.

---

## Hetzner CAX21 (ARM64)

**Why chosen:** €7.29/mo for 4 vCPU + 8 GB RAM; plenty of headroom for a single-user bot processing ≤ 100 videos / day. ARM64 is cheaper than x86 at Hetzner for equivalent specs.

**Where used:** Target host for production deploy. CI SSH's to a hardcoded IP in [.github/workflows/deploy.yml](../../.github/workflows/deploy.yml).

**Conventions:**
- Host path: `/root/pulsebrain/`.
- Deploy via `scp src/ requirements.txt Dockerfile docker-compose.yml` (no `tests/`, no `.env` — those stay local/on-server respectively).
- `.env` and `proxy-credentials` live on the server, never in the repo.

**Gotchas:**
- Python wheels must be ARM64-clean. `trafilatura`, `lxml`, `yaml` — all tested to build on ARM. Avoid packages that ship x86-only wheels.
- SSH key rotation: update `DEPLOY_SSH_KEY` secret in GitHub Actions; don't forget the authorized_keys on the host.

---

## proxy-cheap.com (rotating residential)

**Why chosen:** Cheap (~$5/mo), simple `user:pass@host:port` authentication, residential IPs bypass YouTube's datacenter blocking.

**Where used:** Consumed by [src/extractors/youtube.py](../../src/extractors/youtube.py) via `PROXY_CREDENTIALS_FILE`.

**Conventions:**
- One credential per line. Random line picked per request.
- File mounted `:ro` into the container.
- No retry against the same proxy line — retry picks a fresh random line.

**Gotchas:**
- Residential proxies vary in reliability — expect ~5-10 % request failures even when YouTube is up. The 3-attempt retry in `get_transcript` absorbs this.
- Any provider implementing the same `user:pass@host:port` shape is a drop-in replacement — we are not locked in.
