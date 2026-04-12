"""Tests for src.extractors.youtube — retry backoff, metadata."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_get_transcript_succeeds_first_try():
    """Transcript returned on first attempt — no retries."""
    from src.extractors.youtube import get_transcript

    mock_snippet = MagicMock()
    mock_snippet.text = "hello world"
    mock_transcript = [mock_snippet]

    with patch("src.extractors.youtube.YouTubeTranscriptApi") as MockApi:
        instance = MockApi.return_value
        instance.fetch.return_value = mock_transcript

        result = get_transcript("test_vid", languages=["en"])
        assert result == "hello world"
        assert instance.fetch.call_count == 1


def test_get_transcript_retries_with_backoff():
    """Fails 2x, succeeds 3rd. Verify time.sleep called with backoff delays."""
    from src.extractors.youtube import get_transcript

    mock_snippet = MagicMock()
    mock_snippet.text = "success"

    with (
        patch("src.extractors.youtube.YouTubeTranscriptApi") as MockApi,
        patch("src.extractors.youtube.time.sleep") as mock_sleep,
    ):
        instance = MockApi.return_value
        instance.fetch.side_effect = [
            Exception("fail1"),
            Exception("fail2"),
            [mock_snippet],
        ]

        result = get_transcript("test_vid", languages=["en"])
        assert result == "success"
        assert instance.fetch.call_count == 3
        # Backoff: sleep(1) after 1st fail, sleep(2) after 2nd fail
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)


def test_get_transcript_none_after_all_retries():
    """All 3 attempts fail → returns None."""
    from src.extractors.youtube import get_transcript

    with (
        patch("src.extractors.youtube.YouTubeTranscriptApi") as MockApi,
        patch("src.extractors.youtube.time.sleep"),
    ):
        instance = MockApi.return_value
        instance.fetch.side_effect = Exception("always fails")

        result = get_transcript("test_vid", languages=["en"])
        assert result is None
        assert instance.fetch.call_count == 3


def test_get_video_metadata_success():
    """oEmbed returns title + channel."""
    from src.extractors.youtube import get_video_metadata

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "title": "Test Video",
        "author_name": "TestChannel",
    }

    with patch("src.extractors.youtube.requests.get", return_value=mock_resp):
        meta = get_video_metadata("abc123")
        assert meta["title"] == "Test Video"
        assert meta["channel"] == "TestChannel"


def test_get_video_metadata_failure():
    """HTTP error → fallback dict with None values."""
    from src.extractors.youtube import get_video_metadata

    with patch("src.extractors.youtube.requests.get", side_effect=Exception("network")):
        meta = get_video_metadata("abc123")
        assert meta["title"] is None
        assert meta["channel"] is None


# ── Proxy helpers ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_proxy_cache():
    """Clear the module-level _proxy_lines cache between tests."""
    import src.extractors.youtube as yt
    yt._proxy_lines = []
    yield
    yt._proxy_lines = []


def test_load_proxy_lines_caches_after_first_read(tmp_path):
    import src.extractors.youtube as yt

    creds = tmp_path / "proxy-credentials"
    creds.write_text("user:pass@host:8080\n", encoding="utf-8")

    with patch.object(yt, "PROXY_CREDENTIALS_FILE", creds):
        first = yt._load_proxy_lines()
        second = yt._load_proxy_lines()

    assert first == ["user:pass@host:8080"]
    assert second is first  # cached, same list object


def test_load_proxy_lines_handles_missing_file(tmp_path):
    import src.extractors.youtube as yt

    missing = tmp_path / "no-creds"
    with patch.object(yt, "PROXY_CREDENTIALS_FILE", missing):
        result = yt._load_proxy_lines()

    assert result == []


def test_make_proxy_config_returns_none_when_no_creds(tmp_path):
    import src.extractors.youtube as yt

    with patch.object(yt, "PROXY_CREDENTIALS_FILE", tmp_path / "missing"):
        assert yt._make_proxy_config() is None


def test_make_proxy_config_returns_config_when_creds_available(tmp_path):
    import src.extractors.youtube as yt

    creds = tmp_path / "proxy-credentials"
    creds.write_text("u:p@h:1\n", encoding="utf-8")
    with patch.object(yt, "PROXY_CREDENTIALS_FILE", creds):
        cfg = yt._make_proxy_config()

    assert cfg is not None


def test_get_random_proxy_dict_returns_none_when_no_creds(tmp_path):
    import src.extractors.youtube as yt

    with patch.object(yt, "PROXY_CREDENTIALS_FILE", tmp_path / "missing"):
        assert yt._get_random_proxy_dict() is None


def test_get_random_proxy_dict_returns_dict_when_creds_available(tmp_path):
    import src.extractors.youtube as yt

    creds = tmp_path / "proxy-credentials"
    creds.write_text("u:p@h:1\n", encoding="utf-8")
    with patch.object(yt, "PROXY_CREDENTIALS_FILE", creds):
        result = yt._get_random_proxy_dict()

    assert result == {"http": "http://u:p@h:1", "https": "http://u:p@h:1"}


# ── resolve_channel_id ─────────────────────────────────────────────────────


def _mock_html_response(html: str):
    resp = MagicMock()
    resp.text = html
    return resp


def test_resolve_channel_id_external_id_regex():
    from src.extractors.youtube import resolve_channel_id

    html = '<meta><script>"externalId":"UCabcdef123","author":"My Channel"</script>'
    with patch("src.extractors.youtube.requests.get", return_value=_mock_html_response(html)):
        cid, name = resolve_channel_id("https://youtube.com/@my")

    assert cid == "UCabcdef123"
    assert name == "My Channel"


def test_resolve_channel_id_channel_id_param_fallback():
    from src.extractors.youtube import resolve_channel_id

    html = 'channel_id=UCfallback00000000000000 - <title>Fallback Channel - YouTube</title>'
    with patch("src.extractors.youtube.requests.get", return_value=_mock_html_response(html)):
        cid, name = resolve_channel_id("https://youtube.com/@fb")

    assert cid == "UCfallback00000000000000"
    assert name == "Fallback Channel"


def test_resolve_channel_id_channelId_json_fallback():
    from src.extractors.youtube import resolve_channel_id

    html = '"channelId":"UCjsonjsonjsonjsonjsonjs"'
    with patch("src.extractors.youtube.requests.get", return_value=_mock_html_response(html)):
        cid, _ = resolve_channel_id("https://youtube.com/@js")

    assert cid == "UCjsonjsonjsonjsonjsonjs"


def test_resolve_channel_id_normalizes_handle_url():
    """A bare 'youtube.com/foo' URL is rewritten to 'youtube.com/@foo' before fetching."""
    from src.extractors.youtube import resolve_channel_id

    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        return _mock_html_response('"externalId":"UCxx00000000000000000000"')

    with patch("src.extractors.youtube.requests.get", side_effect=fake_get):
        resolve_channel_id("https://youtube.com/fireship")

    assert "@fireship" in captured["url"]


def test_resolve_channel_id_returns_none_on_no_match():
    from src.extractors.youtube import resolve_channel_id

    with patch("src.extractors.youtube.requests.get", return_value=_mock_html_response("<html></html>")):
        cid, name = resolve_channel_id("https://youtube.com/@x")

    assert cid is None
    assert name is None


def test_resolve_channel_id_returns_none_on_network_error():
    from src.extractors.youtube import resolve_channel_id

    with patch("src.extractors.youtube.requests.get", side_effect=Exception("net")):
        cid, name = resolve_channel_id("https://youtube.com/@x")

    assert cid is None
    assert name is None


# ── get_recent_video_ids (RSS) ─────────────────────────────────────────────


def test_get_recent_video_ids_returns_video_ids():
    from src.extractors.youtube import get_recent_video_ids

    fake_feed = MagicMock()
    fake_feed.entries = [
        {"yt_videoid": "vid1"},
        {"yt_videoid": "vid2"},
        {"yt_videoid": "vid3"},
    ]
    with patch("src.extractors.youtube.feedparser.parse", return_value=fake_feed):
        ids = get_recent_video_ids("UCx", count=3)

    assert ids == ["vid1", "vid2", "vid3"]


def test_get_recent_video_ids_returns_empty_on_exception():
    from src.extractors.youtube import get_recent_video_ids

    with patch("src.extractors.youtube.feedparser.parse", side_effect=Exception("rss")):
        assert get_recent_video_ids("UCx") == []


def test_get_recent_video_ids_skips_entries_without_id():
    from src.extractors.youtube import get_recent_video_ids

    fake_feed = MagicMock()
    fake_feed.entries = [
        {"yt_videoid": "vid1"},
        {},  # missing
        {"yt_videoid": "vid2"},
    ]
    with patch("src.extractors.youtube.feedparser.parse", return_value=fake_feed):
        ids = get_recent_video_ids("UCx", count=10)

    assert ids == ["vid1", "vid2"]
