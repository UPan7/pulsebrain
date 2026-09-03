"""Web article content extraction via trafilatura."""

from __future__ import annotations

import logging

import trafilatura

logger = logging.getLogger(__name__)


def extract_web_article(
    url: str,
    *,
    failure_out: dict[str, str] | None = None,
) -> dict[str, str | None] | None:
    """Download and extract clean text + metadata from a web article.

    Returns dict with keys: title, author, date, text, source_url, sitename.
    Returns None on failure.

    *failure_out*, when supplied, receives ``{"kind": ..., "code": ...}``
    classifying the failure as ``"permanent"`` or ``"transient"``. See
    :func:`src.extractors.youtube.get_transcript` for the rationale behind
    the out-parameter.
    """
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            # trafilatura collapses timeouts, DNS failures, proxy errors and
            # HTTP errors into a bare None. The dominant cause is network, so
            # classify transient; a hard 404 costs a bounded handful of
            # pointless retries. Telling them apart would mean switching to
            # fetch_response() for the status code, which changes the call
            # shape every existing test patches.
            logger.warning("Failed to download %s", url)
            if failure_out is not None:
                failure_out.update(kind="transient", code="DownloadFailed")
            return None

        text = trafilatura.extract(
            downloaded,
            output_format="txt",
            include_comments=False,
            include_tables=True,
        )

        metadata = trafilatura.extract_metadata(downloaded)

        if not text or len(text) < 100:
            # Paywall, JS-only app, or an index page. Re-fetching in six
            # hours yields the same bytes — permanent.
            logger.warning("Extracted text too short for %s", url)
            if failure_out is not None:
                failure_out.update(kind="permanent", code="TextTooShort")
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
        if failure_out is not None:
            failure_out.update(kind="transient", code=type(exc).__name__)
        return None
