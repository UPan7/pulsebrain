# Pulse Bot

Personal knowledge aggregation bot managed via Telegram. Monitors YouTube channels on schedule and processes manually dropped links (YouTube videos, blog posts, articles).

## Stack

- Python 3.11+, type hints everywhere
- Telegram bot via python-telegram-bot
- YouTube transcripts via youtube-transcript-api
- Web articles via trafilatura
- Summarization via Claude API (claude-sonnet-4-20250514)
- Scheduling via APScheduler
- Storage: Markdown files in knowledge/ volume
- Docker on Hetzner CAX21 (ARM64)

## Key Architecture Decisions

- No database — Markdown files are the knowledge base
- Single container — bot + scheduler in one process
- channels.yml is the only writable config (modified via Telegram)
- processed.json tracks duplicates (key: `yt:{video_id}` or `web:{sha256(url)}`)
- All user-facing messages in Russian
- Bot only responds to configured TELEGRAM_CHAT_ID

## Running

```bash
cp .env.example .env  # Fill in API keys
docker compose build
docker compose up -d
```

## Development

```bash
pip install -r requirements.txt
python -m src.main
```

## File Naming

`knowledge/{category}/{year}/{month}/{source-slug}_{title-slug}_{date}.md`

## Error Handling

Never crash on single failure. Log, notify via Telegram, continue.
