# PulseBrain

Self-hosted Telegram bot that builds a personal knowledge base from YouTube channels and web articles.

<!-- TODO: add Telegram conversation screenshot -->

Tech moves too fast. New tools, models, and releases drop weekly. This bot watches your favorite YouTube channels, reads the articles you'd never get to, and builds a searchable knowledge base — so you stay current without the FOMO. No SaaS, no subscriptions, Markdown files on your server.

## Features

- **YouTube channel monitoring** — periodic checks via RSS + YouTube API, configurable interval
- **Drop-a-link processing** — paste any YouTube video or web article URL in Telegram; bot processes it immediately
- **Bring your own LLM** — works with any OpenRouter model; defaults to gpt-5.4-nano (relevance score, bullets, insights, action items)
- **Approval queue** — staged entries with inline keyboard (approve / reject / re-categorize)
- **Full-text search** — `/search` across all knowledge entries, jump to any entry with `/get`
- **Structured Markdown output** — category/year/month folder hierarchy, lossless `.source.txt` sibling
- **Single authorized user** — bot ignores everyone except your `TELEGRAM_CHAT_ID`
- **No database** — Markdown files are the knowledge base

## Quick Start

1. **Clone and configure**
   ```bash
   git clone https://github.com/youruser/pulse-bot.git
   cd pulse-bot
   cp .env.example .env
   # Edit .env — fill in TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, OPENROUTER_API_KEY
   ```

2. **Add your channels** (or let the bot's onboarding wizard do it)
   ```bash
   # Edit channels.yml — see Configuration section below
   ```

3. **Build and run**
   ```bash
   docker compose build
   docker compose up -d
   ```

4. **Start the bot in Telegram** — send `/start` to run the onboarding wizard

5. **Drop a link** — paste any YouTube or article URL in the chat to process it immediately

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Onboarding wizard (first run) or welcome message |
| `/help` | Show all commands |
| `/add <url> [category]` | Add a YouTube channel to monitor |
| `/remove` | Pause or remove a tracked channel |
| `/list` | Show all tracked channels with enabled/paused status |
| `/categories` | Show categories with entry counts, last date, avg relevance |
| `/search <query>` | Full-text search across knowledge base (returns entry IDs) |
| `/recent [count]` | List most recent entries (default: 5) |
| `/get [entry_id]` | Browse entries by category picker or jump to specific entry |
| `/status` | Quick stats: total entries, active channels, this week's count |
| `/stats` | Detailed stats: entries by category, top sources, weekly summary |
| `/pending` | List staged entries awaiting approval (inline keyboard) |
| `/rejected [count]` | Show auto-rejected entries with rejection reason |
| `/run` | Force immediate pipeline run for all enabled channels |
| `/language` | Switch UI language without re-running wizard |
| `/onboarding` | Re-run the setup wizard |
| `/cancel` | Cancel any in-progress wizard step |

## How It Works

```
Telegram
   │
   ├─ /add <channel-url>  ──► Channel stored in channels.yml
   │
   ├─ Drop link  ──────────► router.py detects type
   │                              │
   └─ Scheduler (APScheduler) ───►│
                                  ▼
                         extractors/
                         ├── youtube.py  ── oEmbed metadata
                         │                  RSS feed → video IDs
                         │                  youtube-transcript-api + proxy
                         └── web.py  ─────── trafilatura
                                  │
                                  ▼
                         pipeline.py
                         ├── summarize.py  ── OpenRouter LLM
                         │                   relevance score, bullets,
                         │                   insights, action items
                         └── categorize.py ── category inference
                                  │
                                  ▼
                         pending.py  ──────── Telegram approval queue
                                  │          (approve / reject / re-cat)
                                  ▼
                         storage.py  ──────── Write Markdown + .source.txt
                                              Update search index
```

## Knowledge Base Structure

Files are stored under `knowledge/` with the path:
`{category}/{year}/{month}/{source-slug}_{title-slug}_{date}.md`

```
knowledge/
├── ai-agents/
│   └── 2025/
│       └── 04/
│           ├── cole-medin_multi-agent-patterns_2025-04-13.md
│           └── cole-medin_multi-agent-patterns_2025-04-13.source.txt
├── devops/
│   └── 2025/
│       └── 04/
│           └── networkchuck_docker-in-2025_2025-04-10.md
└── ai-news/
    └── ...
```

Each `.source.txt` contains the raw transcript or article body for corpus use or `/get` downloads.

**Entry format:**

```markdown
# Exploring Agentic AI Patterns

- **Source:** https://youtube.com/watch?v=...
- **Type:** youtube_video
- **Channel:** Cole Medin
- **Date:** 2025-04-13
- **Category:** ai-agents
- **Relevance:** 8/10
- **Topics:** multi-agent, orchestration, tool-use

## Summary

• Bullet point 1
• Bullet point 2

## Detailed Notes

...

## Key Insights

- Insight 1

## Action Items

- [ ] Action 1
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Yes | Your numeric Telegram chat ID |
| `OPENROUTER_API_KEY` | Yes | API key from openrouter.ai |
| `CHECK_INTERVAL_MINUTES` | No | Scheduler interval in minutes (default: 30) |
| `MIN_RELEVANCE_THRESHOLD` | No | Auto-reject below this score 1–10 (default: 4) |
| `TRANSCRIPT_LANGUAGES` | No | YouTube transcript language priority, comma-separated (default: `en,de,ru`) |
| `LOG_LEVEL` | No | Python logging level (default: `INFO`) |

### Proxies (required for transcripts)

YouTube aggressively rate-limits `youtube-transcript-api` on data-center IPs. Without rotating residential proxies, transcript fetching will fail within hours.

The bot reads credentials from `proxy-credentials` — one entry per line, format `user:pass@host:port`:

```
user1:pass1@gate.proxy-cheap.com:31112
user2:pass2@gate.proxy-cheap.com:31113
```

A random entry is picked per request. The file is mounted read-only in Docker:

```yaml
# docker-compose.yml
volumes:
  - ./proxy-credentials:/app/proxy-credentials:ro
```

**Tested provider:** [proxy-cheap.com](https://proxy-cheap.com) rotating residential plan. Any HTTP/HTTPS proxy that supports `user:pass@host:port` format works.

If `proxy-credentials` is missing or empty, the bot falls back to direct requests (expect bans on VPS IPs).

### channels.yml

```yaml
channels:
  - name: "Cole Medin"
    id: "UCmHzpwaNEMgz2Do3IfJbXzg"
    category: "ai-agents"
    enabled: true

  - name: "Fireship"
    id: "UCsBjURrPoezykLs9EqgamOA"
    category: "ai-news"
    enabled: true
```

Fields: `name`, `id` (YouTube channel ID), `category` (slug), `enabled` (bool). Optionally add `min_relevance` per channel to override the global threshold.

The bot manages this file via `/add` and `/remove` commands — editing manually is fine too.

### Default Categories

| Slug | Label |
|------|-------|
| `ai-agents` | AI Agents & Multi-Agent |
| `claude-code` | Claude Code & AI Dev |
| `devops` | DevOps & Infrastructure |
| `n8n-automation` | N8N & Automation |
| `ai-news` | AI News & Releases |
| `wordpress` | WordPress & WooCommerce |
| `business` | Business & Freelancing |

Custom categories can be created via the bot's category picker.

## Deployment

Single Docker container. Volumes persist knowledge and data between restarts.

```yaml
# docker-compose.yml (excerpt)
volumes:
  - ./knowledge:/app/knowledge   # Markdown knowledge base
  - ./data:/app/data             # processed.json, pending, profile, rejected log
  - ./channels.yml:/app/channels.yml
```

Target: Hetzner CAX21 (ARM64, 4 vCPU, 8GB RAM). The Python 3.11-slim image builds multi-arch clean.

## Development

```bash
pip install -r requirements.txt
python -m src.main
```

Tests require 85% coverage:

```bash
pytest --cov=src tests/
```

## Roadmap

**Phase 2 (planned):**
- RSS blog monitoring — same pipeline, no YouTube-specific steps
- PDF ingestion — drop a PDF in Telegram, get a summarized entry
- RAG layer — vector search over the knowledge base for semantic queries
- Karpathy-style wiki compilation — periodic LLM pass that synthesizes entries into structured topic pages

## Contributing

PRs welcome. Keep the no-database constraint and the single-container architecture.

Run tests before submitting: `pytest --cov=src tests/ --cov-fail-under=85`

## License

MIT
