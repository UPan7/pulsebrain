"""Save .md files, update _index.md, search knowledge base, track processed items."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time as _time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from slugify import slugify

from src.config import DATA_DIR, KNOWLEDGE_DIR, PROCESSED_FILE

logger = logging.getLogger(__name__)


# ── Processed tracking (in-memory with Lock) ────────────────────────────────

_processed_lock = threading.Lock()
_processed_cache: dict[str, Any] | None = None


def _load_processed_from_disk() -> dict[str, Any]:
    """Read processed.json from disk (internal helper)."""
    if not PROCESSED_FILE.exists():
        return {}
    try:
        with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _flush_processed() -> None:
    """Atomically write _processed_cache to disk (caller must hold lock)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path = PROCESSED_FILE.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(_processed_cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, PROCESSED_FILE)


def init_processed() -> None:
    """Load processed.json into memory. Call once at startup."""
    global _processed_cache
    with _processed_lock:
        _processed_cache = _load_processed_from_disk()


def is_processed(content_id: str) -> bool:
    """Check if a content ID has already been processed (in-memory)."""
    with _processed_lock:
        if _processed_cache is None:
            return content_id in _load_processed_from_disk()
        return content_id in _processed_cache


def mark_processed(content_id: str, status: str = "ok") -> None:
    """Mark a content ID as processed and flush to disk atomically."""
    global _processed_cache
    with _processed_lock:
        if _processed_cache is None:
            _processed_cache = _load_processed_from_disk()
        _processed_cache[content_id] = {
            "status": status,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }
        _flush_processed()


def make_content_id(source_type: str, identifier: str) -> str:
    """Create a content ID: yt:{video_id} or web:{sha256(url)}."""
    if source_type == "youtube_video":
        return f"yt:{identifier}"
    return f"web:{hashlib.sha256(identifier.encode()).hexdigest()[:16]}"


# ── File naming ──────────────────────────────────────────────────────────────

def _build_file_path(
    category: str,
    source_slug: str,
    title: str,
    date_str: str | None,
) -> Path:
    """Build: knowledge/{category}/{year}/{month}/{source}_{title}_{date}.md"""
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

    # Ensure max 100 chars for filename
    if len(filename) > 100:
        filename = filename[:96] + ".md"

    return KNOWLEDGE_DIR / category / year / month / filename


# ── Save markdown ────────────────────────────────────────────────────────────

def _validate_category(category: str) -> None:
    """Reject category slugs that could cause path traversal."""
    if ".." in category or "/" in category or "\\" in category:
        raise ValueError(f"Invalid category slug: {category!r}")


def save_entry(
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
    update_index: bool = True,
) -> Path:
    """Save a knowledge entry as a .md file and update the index."""
    _validate_category(category)
    file_path = _build_file_path(category, source_name, title, date_str)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Build markdown content
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

    logger.info("Saved entry: %s", file_path)

    _invalidate_entry_cache()

    if update_index:
        _update_index()

    return file_path


# ── Move entry between categories ────────────────────────────────────────────

def move_entry(old_path: str, new_category: str) -> str | None:
    """Move a .md file to a new category directory. Returns new path or None."""
    old = Path(old_path)
    if not old.exists():
        logger.warning("Cannot move — file not found: %s", old_path)
        return None

    # Build new path: knowledge/{new_category}/{year}/{month}/{filename}
    # Extract year/month from old path structure
    parts = old.relative_to(KNOWLEDGE_DIR).parts  # (old_cat, year, month, file)
    if len(parts) >= 4:
        new_path = KNOWLEDGE_DIR / new_category / parts[1] / parts[2] / parts[3]
    else:
        new_path = KNOWLEDGE_DIR / new_category / old.name

    new_path.parent.mkdir(parents=True, exist_ok=True)

    # Update category inside the file content
    content = old.read_text(encoding="utf-8")
    import re
    content = re.sub(r"^- \*\*Category:\*\* .+$", f"- **Category:** {new_category}", content, count=1, flags=re.MULTILINE)
    new_path.write_text(content, encoding="utf-8")

    old.unlink()
    logger.info("Moved entry: %s -> %s", old_path, new_path)
    _invalidate_entry_cache()
    _update_index()
    return str(new_path)


# ── Index ────────────────────────────────────────────────────────────────────

def _update_index() -> None:
    """Regenerate _index.md from all .md files in knowledge/."""
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    index_path = KNOWLEDGE_DIR / "_index.md"

    entries: list[dict[str, str]] = []
    for md_file in KNOWLEDGE_DIR.rglob("*.md"):
        if md_file.name == "_index.md":
            continue
        info = _parse_entry_metadata(md_file)
        if info:
            entries.append(info)

    # Sort by date descending
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
            rel_path = os.path.relpath(entry["path"], KNOWLEDGE_DIR)
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

    # Group by category
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
        for entry in cat_entries[:20]:  # Limit to avoid huge index
            type_icon = "\U0001f4fa" if entry.get("type") == "youtube_video" else "\U0001f4f0"
            rel_path = os.path.relpath(entry["path"], KNOWLEDGE_DIR)
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


def _parse_entry_metadata(md_file: Path) -> dict[str, str] | None:
    """Parse YAML-like metadata from the top of a .md file."""
    try:
        with open(md_file, "r", encoding="utf-8") as f:
            content = f.read(2000)  # Only read top portion
    except OSError:
        return None

    info: dict[str, str] = {"path": str(md_file)}

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

    if "title" not in info:
        return None
    return info


# ── Entry cache (TTL-based) ──────────────────────────────────────────────────

_entry_cache: list[dict[str, str]] | None = None
_entry_cache_time: float = 0.0
_ENTRY_CACHE_TTL: float = 60.0  # seconds


def _get_all_entries() -> list[dict[str, str]]:
    """Return all parsed entries, using cache if still valid."""
    global _entry_cache, _entry_cache_time
    now = _time.monotonic()
    if _entry_cache is not None and (now - _entry_cache_time) < _ENTRY_CACHE_TTL:
        return _entry_cache

    entries: list[dict[str, str]] = []
    for md_file in KNOWLEDGE_DIR.rglob("*.md"):
        if md_file.name == "_index.md":
            continue
        info = _parse_entry_metadata(md_file)
        if info:
            entries.append(info)

    _entry_cache = entries
    _entry_cache_time = now
    return entries


def _invalidate_entry_cache() -> None:
    """Reset entry cache so next access re-scans."""
    global _entry_cache, _entry_cache_time
    _entry_cache = None
    _entry_cache_time = 0.0


# ── Search ───────────────────────────────────────────────────────────────────

def search_knowledge(query: str, max_results: int = 10) -> list[dict[str, str]]:
    """Search knowledge base by keyword matching in titles and content."""
    query_lower = query.lower()
    results: list[tuple[int, dict[str, str]]] = []

    for md_file in KNOWLEDGE_DIR.rglob("*.md"):
        if md_file.name == "_index.md":
            continue

        try:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            continue

        score = 0
        content_lower = content.lower()

        # Score based on matches
        for word in query_lower.split():
            # Title match (first line) is worth more
            first_line = content.split("\n", 1)[0].lower()
            if word in first_line:
                score += 10
            if word in content_lower:
                score += content_lower.count(word)

        if score > 0:
            info = _parse_entry_metadata(md_file)
            if info:
                # Extract first few summary bullets
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


def get_recent_entries(count: int = 5) -> list[dict[str, str]]:
    """Get the most recently added entries."""
    entries = list(_get_all_entries())
    entries.sort(key=lambda e: e.get("date", ""), reverse=True)
    return entries[:count]


def search_for_question(query: str, max_files: int = 5) -> list[dict[str, str]]:
    """Find relevant entries for a free-form question.

    Returns up to *max_files* results, each containing extracted sections
    (Summary, Key Insights, Detailed Notes) trimmed to fit context limits.

    Ranking: keyword score * recency bonus * relevance score.
    """
    query_lower = query.lower()
    scored: list[tuple[float, Path]] = []

    for md_file in KNOWLEDGE_DIR.rglob("*.md"):
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

        # Parse metadata for bonus multipliers
        info = _parse_entry_metadata(md_file)
        if not info:
            continue

        # Recency bonus: entries from last 30 days get up to 2x
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

        # Relevance score bonus
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
    max_total_chars = 40_000  # ~10K tokens

    for md_file in top_files:
        try:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            continue

        info = _parse_entry_metadata(md_file) or {}
        extracted = _extract_sections(content, compact=(total_chars > max_total_chars // 2))

        info["extracted_text"] = extracted
        results.append(info)
        total_chars += len(extracted)

    # If total context is way too large, re-extract with summary-only
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
    """Extract Summary + Key Insights + Detailed Notes from a .md file.

    If *compact* is True, only extract Summary (for token budget).
    """
    sections: list[str] = []

    for section_name in ["## Summary", "## Key Insights", "## Detailed Notes"]:
        if compact and section_name != "## Summary":
            break
        start = content.find(section_name)
        if start == -1:
            continue
        # Find the next ## heading or end of file
        next_heading = content.find("\n## ", start + len(section_name))
        if next_heading == -1:
            section_text = content[start:]
        else:
            section_text = content[start:next_heading]
        sections.append(section_text.strip())

    return "\n\n".join(sections) if sections else content[:1000]


def get_stats() -> dict[str, Any]:
    """Collect knowledge base statistics."""
    entries = list(_get_all_entries())

    total = len(entries)
    videos = sum(1 for e in entries if e.get("type") == "youtube_video")
    articles = sum(1 for e in entries if e.get("type") == "web_article")

    by_category: dict[str, int] = {}
    by_source: dict[str, int] = {}
    relevance_scores: list[int] = []

    week_ago = (datetime.now(timezone.utc) -
                timedelta(days=7)).strftime("%Y-%m-%d")
    this_week = 0

    for e in entries:
        cat = e.get("category", "uncategorized")
        by_category[cat] = by_category.get(cat, 0) + 1

        source = e.get("source", "unknown")
        by_source[source] = by_source.get(source, 0) + 1

        try:
            relevance_scores.append(int(e.get("relevance", "0").strip()))
        except ValueError:
            pass

        if e.get("date", "") >= week_ago:
            this_week += 1

    avg_relevance = (
        round(sum(relevance_scores) / len(relevance_scores), 1)
        if relevance_scores
        else 0
    )

    top_sources = sorted(by_source.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "total": total,
        "videos": videos,
        "articles": articles,
        "by_category": dict(sorted(by_category.items(), key=lambda x: x[1], reverse=True)),
        "this_week": this_week,
        "avg_relevance": avg_relevance,
        "top_sources": top_sources,
    }
