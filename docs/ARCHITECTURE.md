# Architecture

High-level diagrams of PulseBrain. Text-and-diagrams — code references go to [system-context/MODULE_MAP.md](system-context/MODULE_MAP.md); rules go to [system-context/SYSTEM_CONSTRAINTS.md](system-context/SYSTEM_CONSTRAINTS.md).

## System overview

```mermaid
flowchart LR
    user(["User (Telegram)"])
    tg[["Telegram Bot API"]]
    bot["pulsebrain container<br/>(python 3.11-slim, ARM64)"]

    subgraph ext[External services]
        yt[["YouTube RSS + oEmbed"]]
        ytt[["youtube-transcript-api<br/>via rotating residential proxy"]]
        web[["Arbitrary web URLs<br/>(trafilatura)"]]
        or[["OpenRouter<br/>openai/gpt-5.4-nano"]]
    end

    subgraph vol[Docker volumes on host]
        km[/"knowledge/{chat_id}/*.md"/]
        ds[/"data/users/{chat_id}/*.json,yaml"/]
        pc[/"proxy-credentials (:ro)"/]
    end

    user <-->|long-poll| tg
    tg <--> bot

    bot -->|RSS / oEmbed / scrape| yt
    bot -->|transcript fetch| ytt
    bot -->|article fetch| web
    bot -->|chat.completions| or

    bot <--> km
    bot <--> ds
    bot -->|read-only| pc
```

**Deploy target:** Hetzner CAX21 (ARM64, 4 vCPU, 8 GB RAM). One container. No DB.

## Request paths

There are two ways a new entry lands in the knowledge base. Both funnel through [src/pipeline.py](../src/pipeline.py).

### Path A — user drops a link

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant T as Telegram
    participant B as telegram_bot.py
    participant R as router.py
    participant P as pipeline.py
    participant E as extractors/*
    participant S as summarize.py
    participant C as categorize.py
    participant PN as pending.py
    participant ST as storage.py
    participant OR as OpenRouter

    U->>T: paste URL
    T->>B: message update
    B->>B: allowlist check (chat_id)
    B->>R: detect_source_type(url)
    R-->>B: "youtube_video" | "web_article"
    B->>P: process_youtube_video(chat_id, url) <br/>OR process_web_article(chat_id, url)
    P->>ST: is_processed(chat_id, content_id)
    ST-->>P: false
    P->>E: get_transcript(video_id) OR extract_web_article(url)
    E-->>P: text (or None → error path)
    P->>S: summarize_content(chat_id, ...)
    S->>OR: chat.completions (with USER CONTEXT)
    OR-->>S: JSON (bullets, notes, relevance, ...)
    S-->>P: dict (or None → error path)
    P->>C: categorize_content(chat_id, title, content)
    C->>OR: chat.completions (pick slug)
    OR-->>C: slug
    C-->>P: (slug, is_new_category)
    P->>PN: stage_pending(chat_id, ..., raw_text)
    PN-->>P: pending_id
    P->>ST: mark_processed(chat_id, content_id, "pending")
    P-->>B: result dict
    B->>T: reply with summary + approve/reject keyboard
    T->>U: notification
    U->>T: tap Approve
    T->>B: callback_query
    B->>PN: commit_pending(chat_id, pending_id)
    PN->>ST: save_entry(...) + mark_processed(..., "ok")
    ST-->>PN: written path
    PN-->>B: Path
    B->>T: "Saved to knowledge base"
```

### Path B — scheduler tick

```mermaid
sequenceDiagram
    autonumber
    participant AP as APScheduler
    participant SC as scheduler.py
    participant CF as config.load_channels
    participant F as feedparser (YouTube RSS)
    participant P as pipeline.py
    participant PN as pending.py
    participant TG as Telegram app.bot
    participant U as User

    AP->>SC: scheduled_check() every CHECK_INTERVAL_MINUTES
    loop for each chat_id in TELEGRAM_CHAT_IDS
        SC->>CF: load_channels(chat_id)
        CF-->>SC: [channels...]
        par for each enabled channel (asyncio.gather)
            SC->>F: fetch_channel_videos(channel_id)
            F-->>SC: [videos...]
        end
        loop for each (channel, video)
            SC->>SC: is_processed? → skip
            SC->>P: process_youtube_video(chat_id, url, category, upload_date)
            P-->>SC: result with relevance
            alt relevance < min_relevance
                SC->>PN: reject_pending(pending_id, reason="low_relevance")
            else
                SC->>TG: send_notification(chat_id, result)<br/>(approve/reject keyboard)
                TG->>U: push notification
            end
        end
        SC->>TG: round digest (only if processed+rejected+failed > 0)
    end
```

## Multi-tenant isolation

```mermaid
flowchart TB
    subgraph TG[Telegram Bot API]
        inbox([inbound updates])
    end

    bot["bot.run_polling<br/>(single process)"]

    subgraph routing[Routing layer]
        allow{allowlist<br/>check}
    end

    subgraph u1[chat_id = 123]
        d1[/"data/users/123/<br/>processed.json, pending.json,<br/>profile.yaml, channels.yml,<br/>categories.yml, rejected_log.jsonl"/]
        k1[/"knowledge/123/<br/>{category}/{yyyy}/{mm}/*.md + *.source.txt"/]
        c1["in-memory caches keyed on 123<br/>(_processed_caches, _pending_caches,<br/>_profile_caches, _entry_caches)"]
    end

    subgraph u2[chat_id = 456]
        d2[/"data/users/456/..."/]
        k2[/"knowledge/456/..."/]
        c2["in-memory caches keyed on 456"]
    end

    subgraph u3[chat_id = 789]
        d3[/"data/users/789/..."/]
        k3[/"knowledge/789/..."/]
        c3["in-memory caches keyed on 789"]
    end

    inbox --> bot
    bot --> allow
    allow -- chat_id in TELEGRAM_CHAT_IDS --> u1
    allow -- chat_id in TELEGRAM_CHAT_IDS --> u2
    allow -- chat_id in TELEGRAM_CHAT_IDS --> u3
    allow -. chat_id NOT in list .- X[drop silently]
```

**Isolation invariants (enforced by [Constraint 2](system-context/SYSTEM_CONSTRAINTS.md#constraint-2-multi-tenant-via-chat_id-threading)):**
- Every persistent file lives under `data/users/{chat_id}/` or `knowledge/{chat_id}/`. Nothing shared on disk.
- Every in-memory cache is `dict[int, ...]` keyed on `chat_id`.
- Each `chat_id` has its own `threading.Lock` for per-file atomic writes.
- The scheduler iterates users serially (not in parallel) so one user's LLM calls don't starve another's.

## Auth & authorization model

- **Single gate:** `TELEGRAM_CHAT_IDS` env var. Parsed at boot by `_parse_chat_entries` in [src/config.py:38](../src/config.py#L38). Supports `id` or `id:Label` per entry, comma-separated.
- **Admin is first entry.** `ADMIN_CHAT_ID = TELEGRAM_CHAT_IDS[0]`. The only special power is receiving migration artifacts on first boot.
- **Every command handler runs allowlist check** before doing any work (see [Constraint 4](system-context/SYSTEM_CONSTRAINTS.md#constraint-4-authorized-users-only-telegram_chat_ids-allowlist)).
- **No OAuth, no API keys per user, no roles.** The allowlist is the whole model.

## Deployment topology

```mermaid
flowchart LR
    dev["Developer<br/>(local)"]
    gh[["GitHub<br/>main branch"]]
    cd[["GitHub Actions<br/>.github/workflows/deploy.yml"]]
    hz["Hetzner CAX21<br/>91.99.143.15<br/>/root/pulsebrain/"]

    subgraph container[pulsebrain container]
        app["python -m src.main<br/>(bot + scheduler)"]
    end

    subgraph host[Host filesystem]
        env[/".env"/]
        knowledge[/"knowledge/"/]
        data[/"data/"/]
        chy[/"channels.yml"/]
        proxy[/"proxy-credentials"/]
    end

    dev -- git push main --> gh
    gh --> cd
    cd -- scp --> hz
    cd -- ssh docker compose build --no-cache && up -d --> hz
    hz --> container
    container <--> env
    container <--> knowledge
    container <--> data
    container <--> chy
    container <-- :ro --> proxy
```

**Deploy cadence:** continuous — every merge to `main` ships. Rollback is `git revert` + push; there is no separate release artifact.

**State lives on the host**, not in the image. `docker compose up -d` after a fresh pull just replaces the binary; user knowledge + state survive.

## Failure & recovery

The scheduler is the long-running component. Each failure mode has a defined recovery:

| Failure | Detection | Recovery |
|---|---|---|
| Container crashes | `restart: unless-stopped` | Docker restarts it. State survives (host volumes) |
| Bot process hangs | No health check — symptom is a user reporting silence | `docker compose restart` on the host |
| OpenRouter API outage | `openai.APIError` caught, item marked `error` | Scheduler continues with next item; user sees localized error next run |
| YouTube transcript fetch blocked | 3 retries exhausted, `get_transcript` returns None | Item dropped from this run; next scheduler tick retries |
| Host reboot | systemd + docker daemon auto-start | Container comes back; volumes intact |
| Lost proxy credentials | `_load_proxy_lines` returns `[]`; warning logged | Direct requests used; expect high failure rate — operator rotates creds file on host |

See [Constraint 5](system-context/SYSTEM_CONSTRAINTS.md#constraint-5-no-crashes-on-single-item-failure) for the "never crash" rule.
