"""Per-user knowledge base + processed tracking.

Each allowed ``chat_id`` owns an isolated tree:

    knowledge/{chat_id}/_index.md
    knowledge/{chat_id}/{category}/{year}/{month}/*.md
    knowledge/{chat_id}/{category}/{year}/{month}/*.source.txt

Deduplication state (``processed.json``) is likewise per-user, so two
chat_ids that encounter the same YouTube video each get their own
summary. All caches and locks are partitioned by chat_id.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time as _time
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from slugify import slugify

from src.config import KNOWLEDGE_DIR, user_knowledge_dir, user_processed_file

logger = logging.getLogger(__name__)


# ── Processed tracking (per-user cache + lock registry) ────────────────────

_processed_caches: dict[int, dict[str, Any]] = {}
_processed_locks: dict[int, threading.Lock] = {}
_processed_meta_lock = threading.Lock()


def _processed_lock_for(chat_id: int) -> threading.Lock:
    with _processed_meta_lock:
        lock = _processed_locks.get(chat_id)
        if lock is None:
            lock = threading.Lock()
            _processed_locks[chat_id] = lock
        return lock


def _load_processed_from_disk(chat_id: int) -> dict[str, Any]:
    """Read a user's processed.json from disk (internal helper)."""
    path = user_processed_file(chat_id)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _flush_processed(chat_id: int) -> None:
    """Atomically write this user's cache to disk (caller holds lock)."""
    path = user_processed_file(chat_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(_processed_caches[chat_id], f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def init_processed(chat_id: int) -> None:
    """Load a user's processed.json into memory. Call once per chat_id at startup."""
    with _processed_lock_for(chat_id):
        _processed_caches[chat_id] = _load_processed_from_disk(chat_id)


def is_processed(chat_id: int, content_id: str) -> bool:
    """True if ``content_id`` has already been processed for ``chat_id``."""
    with _processed_lock_for(chat_id):
        cache = _processed_caches.get(chat_id)
        if cache is None:
            return content_id in _load_processed_from_disk(chat_id)
        return content_id in cache


def mark_processed(chat_id: int, content_id: str, status: str = "ok") -> None:
    """Mark ``content_id`` as processed for ``chat_id`` and flush atomically."""
    with _processed_lock_for(chat_id):
        cache = _processed_caches.get(chat_id)
        if cache is None:
            cache = _load_processed_from_disk(chat_id)
            _processed_caches[chat_id] = cache
        cache[content_id] = {
            "status": status,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
        _flush_processed(chat_id)


def make_content_id(source_type: str, identifier: str) -> str:
    """Create a content ID: ``yt:{video_id}`` or ``web:{sha256(url)}``.

    The same content maps to the same ID across users — uniqueness is
    enforced per-user via the per-user :func:`is_processed` lookup.
    """
    if source_type == "youtube_video":
        return f"yt:{identifier}"
    return f"web:{hashlib.sha256(identifier.encode()).hexdigest()[:16]}"


# ── File naming ──────────────────────────────────────────────────────────────

def _build_file_path(
    chat_id: int,
    category: str,
    source_slug: str,
    title: str,
    date_str: str | None,
) -> Path:
    """Build the path under this user's knowledge dir."""
    if date_str:
        try:
            dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        except ValueError:
            dt = datetime.now(timezone.utc)
    else:
        dt = datetime.now(timezone.utc)

    year = str(dt.year)
    month = f"{dt.month:02d}"

    title_slug = slugify(title, max_length=60)
    src_slug = slugify(source_slug, max_length=30)
    date_part = dt.strftime("%Y-%m-%d")
    filename = f"{src_slug}_{title_slug}_{date_part}.md"

    if len(filename) > 100:
        filename = filename[:96] + ".md"

    return user_knowledge_dir(chat_id) / category / year / month / filename


# ── Save markdown ────────────────────────────────────────────────────────────

def _validate_category(category: str) -> None:
    """Reject category slugs that could cause path traversal."""
    if ".." in category or "/" in category or "\\" in category:
        raise ValueError(f"Invalid category slug: {category!r}")


def save_entry(
    chat_id: int,
    title: str,
    source_url: str,
    source_type: str,
    source_name: str,
    date_str: str | None,
    category: str,
    relevance: int,
    topics: list[str],
    summary_bullets: list[str],
    detailed_notes: str,
    key_insights: list[str],
    action_items: list[str],
    author: str | None = None,
    sitename: str | None = None,
    raw_text: str | None = None,
    deep_dive: list[dict[str, str]] | None = None,
    update_index: bool = True,
) -> Path:
    """Save a knowledge entry for ``chat_id`` as a .md file and update their index.

    If *raw_text* is provided (the original transcript or article body),
    it is written verbatim to a sibling ``{stem}.source.txt`` — the
    lossless source — alongside the .md summary.

    *deep_dive* is an optional list of ``{"heading": str, "body": str}``
    dicts. When present and non-empty, a ``## Deep Dive`` section is
    rendered between Detailed Notes and Key Insights. Entries saved
    before this feature (or from short/medium summaries) pass ``None``
    and simply omit the section — no migration needed.
    """
    _validate_category(category)
    file_path = _build_file_path(chat_id, category, source_name, title, date_str)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [f"# {title}", ""]

    lines.append(f"- **Source:** {source_url}")
    lines.append(f"- **Type:** {source_type}")

    if source_type == "youtube_video":
        lines.append(f"- **Channel:** {source_name}")
    else:
        if sitename:
            lines.append(f"- **Site:** {sitename}")
        if author and author != "Unknown":
            lines.append(f"- **Author:** {author}")

    lines.append(f"- **Date:** {date_str or 'unknown'}")
    lines.append(f"- **Category:** {category}")
    lines.append(f"- **Relevance:** {relevance}/10")
    lines.append(f"- **Topics:** {', '.join(topics)}")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    for bullet in summary_bullets:
        lines.append(f"\u2022 {bullet}")
    lines.append("")

    lines.append("## Detailed Notes")
    lines.append("")
    lines.append(detailed_notes)
    lines.append("")

    if deep_dive:
        lines.append("## Deep Dive")
        lines.append("")
        for section in deep_dive:
            heading = (section.get("heading") or "").strip()
            body = (section.get("body") or "").strip()
            if not heading and not body:
                continue
            if heading:
                lines.append(f"### {heading}")
                lines.append("")
            if body:
                lines.append(body)
                lines.append("")

    lines.append("## Key Insights")
    lines.append("")
    for insight in key_insights:
        lines.append(f"- {insight}")
    lines.append("")

    lines.append("## Action Items")
    lines.append("")
    for item in action_items:
        lines.append(f"- [ ] {item}")
    lines.append("")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info("Saved entry (chat_id=%s): %s", chat_id, file_path)

    if raw_text:
        source_path = _source_sibling_path(file_path)
        try:
            with open(source_path, "w", encoding="utf-8") as f:
                f.write(raw_text)
            logger.info("Saved source text: %s", source_path)
        except OSError as exc:
            logger.warning("Failed to write source sibling for %s: %s",
                           file_path, exc)

    _invalidate_entry_cache(chat_id)

    if update_index:
        _update_index(chat_id)

    return file_path


def _source_sibling_path(md_path: Path) -> Path:
    """Path of the .source.txt sibling for a given .md file."""
    return md_path.with_name(md_path.stem + ".source.txt")


def get_source_text_path(md_path: str | Path) -> Path:
    """Return the .source.txt sibling path for a .md file.

    The sibling may or may not exist on disk; callers should check
    ``.exists()`` before reading.
    """
    return _source_sibling_path(Path(md_path))


# ── Stable entry IDs ─────────────────────────────────────────────────────────

def entry_id(chat_id: int, md_path: str | Path) -> str:
    """Short stable hex ID for a knowledge-base entry, derived from its
    path relative to this user's ``knowledge/{chat_id}/`` root.

    Used by the Telegram ``/get`` command, search/recent output, and the
    file-download callbacks to reference an entry without embedding its
    full absolute path in ``callback_data`` (capped at 64 bytes).
    """
    p = Path(md_path)
    root = user_knowledge_dir(chat_id)
    try:
        rel = p.relative_to(root)
    except ValueError:
        rel = Path(p.name)
    return hashlib.sha256(str(rel).encode("utf-8")).hexdigest()[:8]


def find_entry_by_id(chat_id: int, wanted_id: str) -> dict[str, str] | None:
    """Look up a cached entry by its :func:`entry_id` value.

    Returns the same dict shape as :func:`_parse_entry_metadata` (with the
    added ``"id"`` key populated), or None if no entry matches.
    """
    if not wanted_id:
        return None
    for entry in _get_all_entries(chat_id):
        if entry.get("id") == wanted_id:
            return entry
    return None


def read_entry_markdown(path: str | Path) -> str:
    """Read the full markdown contents of an entry from disk."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ── Move entry between categories ────────────────────────────────────────────

def move_entry(chat_id: int, old_path: str, new_category: str) -> str | None:
    """Move a .md file to a new category directory under this user's tree.

    Returns the new path or None if the source is missing.
    """
    old = Path(old_path)
    if not old.exists():
        logger.warning("Cannot move — file not found: %s", old_path)
        return None

    root = user_knowledge_dir(chat_id)
    try:
        parts = old.relative_to(root).parts  # (old_cat, year, month, file)
    except ValueError:
        parts = ()

    if len(parts) >= 4:
        new_path = root / new_category / parts[1] / parts[2] / parts[3]
    else:
        new_path = root / new_category / old.name

    new_path.parent.mkdir(parents=True, exist_ok=True)

    content = old.read_text(encoding="utf-8")
    import re
    content = re.sub(
        r"^- \*\*Category:\*\* .+$",
        f"- **Category:** {new_category}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    new_path.write_text(content, encoding="utf-8")

    old_source = _source_sibling_path(old)
    if old_source.exists():
        new_source = _source_sibling_path(new_path)
        old_source.rename(new_source)
        logger.info("Moved source sibling: %s -> %s", old_source, new_source)

    old.unlink()
    logger.info("Moved entry (chat_id=%s): %s -> %s", chat_id, old_path, new_path)
    _invalidate_entry_cache(chat_id)
    _update_index(chat_id)
    return str(new_path)


# ── Index ────────────────────────────────────────────────────────────────────

def _update_index(chat_id: int) -> None:
    """Regenerate _index.md from all .md files in this user's knowledge tree."""
    root = user_knowledge_dir(chat_id)
    root.mkdir(parents=True, exist_ok=True)
    index_path = root / "_index.md"

    entries: list[dict[str, str]] = []
    for md_file in root.rglob("*.md"):
        if md_file.name == "_index.md":
            continue
        info = _parse_entry_metadata(chat_id, md_file)
        if info:
            entries.append(info)

    entries.sort(key=lambda e: e.get("date", ""), reverse=True)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    video_count = sum(1 for e in entries if e.get("type") == "youtube_video")
    article_count = sum(1 for e in entries if e.get("type") == "web_article")

    lines = [
        "# Knowledge Base Index",
        "",
        f"Last updated: {now}  ",
        f"Total entries: {len(entries)} ({video_count} videos, {article_count} articles)",
        "",
        "## Recent (last 7 days)",
        "",
        "| Date | Type | Source | Title | Category | Rel. | File |",
        "|------|------|--------|-------|----------|------|------|",
    ]

    week_ago = (datetime.now(timezone.utc).replace(hour=0, minute=0, second=0) -
                timedelta(days=7)).strftime("%Y-%m-%d")

    for entry in entries:
        if entry.get("date", "") >= week_ago:
            type_icon = "\U0001f4fa" if entry.get("type") == "youtube_video" else "\U0001f4f0"
            rel_path = os.path.relpath(entry["path"], root)
            lines.append(
                f"| {entry.get('date', '')} "
                f"| {type_icon} "
                f"| {entry.get('source', '')} "
                f"| {entry.get('title', '')} "
                f"| {entry.get('category', '')} "
                f"| {entry.get('relevance', '')} "
                f"| [\u2192]({rel_path}) |"
            )

    lines.append("")
    lines.append("## By Category")
    lines.append("")

    by_cat: dict[str, list[dict[str, str]]] = {}
    for entry in entries:
        cat = entry.get("category", "uncategorized")
        by_cat.setdefault(cat, []).append(entry)

    for cat in sorted(by_cat.keys()):
        cat_entries = by_cat[cat]
        lines.append(f"### {cat} ({len(cat_entries)} entries)")
        lines.append("")
        lines.append("| Date | Type | Source | Title | Rel. | File |")
        lines.append("|------|------|--------|-------|------|------|")
        for entry in cat_entries[:20]:
            type_icon = "\U0001f4fa" if entry.get("type") == "youtube_video" else "\U0001f4f0"
            rel_path = os.path.relpath(entry["path"], root)
            lines.append(
                f"| {entry.get('date', '')} "
                f"| {type_icon} "
                f"| {entry.get('source', '')} "
                f"| {entry.get('title', '')} "
                f"| {entry.get('relevance', '')} "
                f"| [\u2192]({rel_path}) |"
            )
        lines.append("")

    with open(index_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _parse_entry_metadata(chat_id: int, md_file: Path) -> dict[str, str] | None:
    """Parse YAML-like metadata from the top of a .md file."""
    try:
        with open(md_file, "r", encoding="utf-8") as f:
            content = f.read(2000)
    except OSError:
        return None

    info: dict[str, str] = {
        "path": str(md_file),
        "id": entry_id(chat_id, md_file),
    }

    for line in content.split("\n"):
        if line.startswith("# ") and "title" not in info:
            info["title"] = line[2:].strip()
        elif line.startswith("- **Source:**"):
            info["source_url"] = line.split(":**", 1)[1].strip()
        elif line.startswith("- **Type:**"):
            info["type"] = line.split(":**", 1)[1].strip()
        elif line.startswith("- **Channel:**"):
            info["source"] = line.split(":**", 1)[1].strip()
        elif line.startswith("- **Site:**"):
            info["source"] = line.split(":**", 1)[1].strip()
        elif line.startswith("- **Date:**"):
            info["date"] = line.split(":**", 1)[1].strip()
        elif line.startswith("- **Category:**"):
            info["category"] = line.split(":**", 1)[1].strip()
        elif line.startswith("- **Relevance:**"):
            info["relevance"] = line.split(":**", 1)[1].strip().replace("/10", "")
        elif line.startswith("- **Topics:**"):
            raw = line.split(":**", 1)[1].strip()
            info["topics"] = ", ".join(
                t.strip() for t in raw.split(",") if t.strip()
            )

    if "title" not in info:
        return None
    return info


# ── Entry cache (TTL-based, per-user) ───────────────────────────────────────

_entry_caches: dict[int, tuple[list[dict[str, str]], float]] = {}
_entry_cache_locks: dict[int, threading.Lock] = {}
_entry_cache_meta_lock = threading.Lock()
_ENTRY_CACHE_TTL: float = 60.0  # seconds


def _entry_cache_lock_for(chat_id: int) -> threading.Lock:
    with _entry_cache_meta_lock:
        lock = _entry_cache_locks.get(chat_id)
        if lock is None:
            lock = threading.Lock()
            _entry_cache_locks[chat_id] = lock
        return lock


def _get_all_entries(chat_id: int) -> list[dict[str, str]]:
    """Return all parsed entries for ``chat_id``, using cache if still valid."""
    with _entry_cache_lock_for(chat_id):
        now = _time.monotonic()
        cached = _entry_caches.get(chat_id)
        if cached is not None:
            entries_cached, cached_at = cached
            if (now - cached_at) < _ENTRY_CACHE_TTL:
                return entries_cached

        root = user_knowledge_dir(chat_id)
        entries: list[dict[str, str]] = []
        if root.exists():
            for md_file in root.rglob("*.md"):
                if md_file.name == "_index.md":
                    continue
                info = _parse_entry_metadata(chat_id, md_file)
                if info:
                    entries.append(info)

        _entry_caches[chat_id] = (entries, now)
        return entries


def _invalidate_entry_cache(chat_id: int) -> None:
    """Reset this user's entry cache so next access re-scans."""
    with _entry_cache_lock_for(chat_id):
        _entry_caches.pop(chat_id, None)


def prune_storage_state(valid_ids: Iterable[int]) -> int:
    """Drop processed + entry caches and locks for chat_ids outside ``valid_ids``.

    Called at startup to bound memory after the allowlist changes. Returns
    total number of cache/lock slots pruned.
    """
    keep = set(valid_ids)
    pruned = 0
    with _processed_meta_lock:
        for cid in [c for c in _processed_caches if c not in keep]:
            _processed_caches.pop(cid, None)
            pruned += 1
        for cid in [c for c in _processed_locks if c not in keep]:
            del _processed_locks[cid]
            pruned += 1
    with _entry_cache_meta_lock:
        for cid in [c for c in _entry_caches if c not in keep]:
            _entry_caches.pop(cid, None)
            pruned += 1
        for cid in [c for c in _entry_cache_locks if c not in keep]:
            del _entry_cache_locks[cid]
            pruned += 1
    return pruned


# ── Search ───────────────────────────────────────────────────────────────────

def search_knowledge(chat_id: int, query: str, max_results: int = 10) -> list[dict[str, str]]:
    """Search ``chat_id``'s knowledge base by keyword matching."""
    query_lower = query.lower()
    results: list[tuple[int, dict[str, str]]] = []
    root = user_knowledge_dir(chat_id)
    if not root.exists():
        return []

    for md_file in root.rglob("*.md"):
        if md_file.name == "_index.md":
            continue

        try:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            continue

        score = 0
        content_lower = content.lower()

        for word in query_lower.split():
            first_line = content.split("\n", 1)[0].lower()
            if word in first_line:
                score += 10
            if word in content_lower:
                score += content_lower.count(word)

        if score > 0:
            info = _parse_entry_metadata(chat_id, md_file)
            if info:
                summary_start = content.find("## Summary")
                if summary_start != -1:
                    summary_section = content[summary_start:summary_start + 500]
                    summary_lines = [
                        line.strip()
                        for line in summary_section.split("\n")
                        if line.strip().startswith("\u2022")
                    ][:2]
                    info["summary_preview"] = "\n".join(summary_lines)
                results.append((score, info))

    results.sort(key=lambda x: x[0], reverse=True)
    return [r[1] for r in results[:max_results]]


def get_recent_entries(chat_id: int, count: int = 5) -> list[dict[str, str]]:
    """Get the most recently added entries for ``chat_id``."""
    entries = list(_get_all_entries(chat_id))
    entries.sort(key=lambda e: e.get("date", ""), reverse=True)
    return entries[:count]


def get_entries_in_category(chat_id: int, slug: str, limit: int = 20) -> list[dict[str, str]]:
    """Return up to *limit* entries in the given category for ``chat_id``."""
    entries = [e for e in _get_all_entries(chat_id) if e.get("category") == slug]
    entries.sort(key=lambda e: e.get("date", ""), reverse=True)
    return entries[:limit]


def search_for_question(chat_id: int, query: str, max_files: int = 5) -> list[dict[str, str]]:
    """Find relevant entries in ``chat_id``'s knowledge base for a free-form question."""
    query_lower = query.lower()
    scored: list[tuple[float, Path]] = []
    root = user_knowledge_dir(chat_id)
    if not root.exists():
        return []

    for md_file in root.rglob("*.md"):
        if md_file.name == "_index.md":
            continue

        try:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            continue

        content_lower = content.lower()
        keyword_score = 0
        for word in query_lower.split():
            first_line = content.split("\n", 1)[0].lower()
            if word in first_line:
                keyword_score += 10
            keyword_score += content_lower.count(word)

        if keyword_score == 0:
            continue

        info = _parse_entry_metadata(chat_id, md_file)
        if not info:
            continue

        recency_bonus = 1.0
        entry_date = info.get("date", "")
        if entry_date:
            try:
                days_ago = (datetime.now(timezone.utc) -
                            datetime.strptime(entry_date[:10], "%Y-%m-%d").replace(
                                tzinfo=timezone.utc)).days
                if days_ago < 30:
                    recency_bonus = 1.0 + (30 - days_ago) / 30.0
            except ValueError:
                pass

        rel_bonus = 1.0
        try:
            rel_bonus = 1.0 + int(info.get("relevance", "5").strip()) / 10.0
        except ValueError:
            pass

        final_score = keyword_score * recency_bonus * rel_bonus
        scored.append((final_score, md_file))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_files = [path for _, path in scored[:max_files]]

    results: list[dict[str, str]] = []
    total_chars = 0
    max_total_chars = 40_000

    for md_file in top_files:
        try:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            continue

        info = _parse_entry_metadata(chat_id, md_file) or {}
        extracted = _extract_sections(content, compact=(total_chars > max_total_chars // 2))

        info["extracted_text"] = extracted
        results.append(info)
        total_chars += len(extracted)

    if total_chars > max_total_chars:
        for entry in results:
            path = entry.get("path", "")
            if not path:
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                entry["extracted_text"] = _extract_sections(content, compact=True)
            except OSError:
                pass

    return results


def _extract_sections(content: str, compact: bool = False) -> str:
    """Extract Summary + Key Insights + Detailed Notes from a .md file."""
    sections: list[str] = []

    for section_name in ["## Summary", "## Key Insights", "## Detailed Notes"]:
        if compact and section_name != "## Summary":
            break
        start = content.find(section_name)
        if start == -1:
            continue
        next_heading = content.find("\n## ", start + len(section_name))
        if next_heading == -1:
            section_text = content[start:]
        else:
            section_text = content[start:next_heading]
        sections.append(section_text.strip())

    return "\n\n".join(sections) if sections else content[:1000]


def get_stats(chat_id: int) -> dict[str, Any]:
    """Collect knowledge base statistics for ``chat_id``."""
    entries = list(_get_all_entries(chat_id))

    total = len(entries)
    videos = sum(1 for e in entries if e.get("type") == "youtube_video")
    articles = sum(1 for e in entries if e.get("type") == "web_article")

    by_category: dict[str, int] = {}
    by_source: dict[str, int] = {}
    relevance_scores: list[int] = []

    cat_health: dict[str, dict[str, Any]] = {}

    week_ago = (datetime.now(timezone.utc) -
                timedelta(days=7)).strftime("%Y-%m-%d")
    month_ago = (datetime.now(timezone.utc) -
                 timedelta(days=30)).strftime("%Y-%m-%d")
    this_week = 0

    for e in entries:
        cat = e.get("category", "uncategorized")
        by_category[cat] = by_category.get(cat, 0) + 1

        source = e.get("source", "unknown")
        by_source[source] = by_source.get(source, 0) + 1

        try:
            rel = int(e.get("relevance", "0").strip())
            relevance_scores.append(rel)
        except ValueError:
            rel = None

        if e.get("date", "") >= week_ago:
            this_week += 1

        bucket = cat_health.setdefault(cat, {
            "count": 0, "last_entry": "", "rel_sum": 0, "rel_n": 0,
        })
        bucket["count"] += 1
        entry_date = e.get("date", "")
        if entry_date > bucket["last_entry"]:
            bucket["last_entry"] = entry_date
        if rel is not None:
            bucket["rel_sum"] += rel
            bucket["rel_n"] += 1

    avg_relevance = (
        round(sum(relevance_scores) / len(relevance_scores), 1)
        if relevance_scores
        else 0
    )

    top_sources = sorted(by_source.items(), key=lambda x: x[1], reverse=True)[:5]

    category_health: dict[str, dict[str, Any]] = {}
    for cat, bucket in cat_health.items():
        avg = (round(bucket["rel_sum"] / bucket["rel_n"], 1)
               if bucket["rel_n"] else 0)
        category_health[cat] = {
            "count": bucket["count"],
            "last_entry": bucket["last_entry"] or None,
            "avg_relevance": avg,
            "stale": bool(bucket["last_entry"]) and bucket["last_entry"] < month_ago,
        }

    return {
        "total": total,
        "videos": videos,
        "articles": articles,
        "by_category": dict(sorted(by_category.items(), key=lambda x: x[1], reverse=True)),
        "category_health": category_health,
        "this_week": this_week,
        "avg_relevance": avg_relevance,
        "top_sources": top_sources,
    }
