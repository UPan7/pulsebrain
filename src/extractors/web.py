"""Web article content extraction via trafilatura."""

from __future__ import annotations

import logging

import trafilatura

logger = logging.getLogger(__name__)


def extract_web_article(url: str) -> dict[str, str | None] | None:
    """Download and extract clean text + metadata from a web article.

    Returns dict with keys: title, author, date, text, source_url, sitename.
    Returns None on failure.
    """
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            logger.warning("Failed to download %s", url)
            return None

        text = trafilatura.extract(
            downloaded,
            output_format="txt",
            include_comments=False,
            include_tables=True,
        )

        metadata = trafilatura.extract_metadata(downloaded)

        if not text or len(text) < 100:
            logger.warning("Extracted text too short for %s", url)
            return None

        return {
            "title": metadata.title if metadata else url,
            "author": metadata.author if metadata else "Unknown",
            "date": metadata.date if metadata else None,
            "text": text,
            "source_url": url,
            "sitename": metadata.sitename if metadata else None,
        }
    except Exception as exc:
        logger.error("Article extraction failed for %s: %s", url, exc)
        return None
