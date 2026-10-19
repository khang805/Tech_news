from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

from newsintel.fetcher import parse_feed
from newsintel.http_client import FetchError, get_with_retries

FIXTURE = Path(__file__).parent / "fixtures" / "sample_feed.xml"
NOW = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
FEED = {"name": "Sample", "url": "https://example.com/feed", "category": "", "source_priority": 4}
SETTINGS = {"request_timeout_seconds": 5, "max_retries": 2, "backoff_seconds": 2, "user_agent": "test"}


class FakeResp:
    def __init__(self, status, content=b""):
        self.status_code = status
        self.content = content


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, url, timeout=None):
        self.calls += 1
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_parse_fixture_returns_items():
    items = parse_feed(FIXTURE.read_bytes(), FEED, 30, NOW)
    assert len(items) == 4
    assert items[0].title.startswith("Example Lab")
    assert all(i.link.startswith("https://") for i in items)


def test_missing_date_is_marked_estimated():
    items = parse_feed(FIXTURE.read_bytes(), FEED, 30, NOW)
    assert items[-1].date_is_estimated is True
    assert items[0].date_is_estimated is False


def test_invalid_xml_raises_recoverable_error():
    with pytest.raises(FetchError) as exc:
        parse_feed(b"<html><body>not a feed</body>", FEED, 30, NOW)
    assert exc.value.kind == "invalid_xml"


def test_retries_then_succeeds():
    session = FakeSession([FakeResp(500), FakeResp(200, b"ok")])
    resp = get_with_retries(session, "https://x", SETTINGS, sleep=lambda _: None)
    assert resp.content == b"ok"
    assert session.calls == 2


def test_404_is_not_retried():
    session = FakeSession([FakeResp(404)])
    with pytest.raises(FetchError) as exc:
        get_with_retries(session, "https://x", SETTINGS, sleep=lambda _: None)
    assert exc.value.kind == "http_404"
    assert session.calls == 1


def test_timeouts_exhaust_retries():
    session = FakeSession([requests.Timeout(), requests.Timeout(), requests.Timeout()])
    with pytest.raises(FetchError) as exc:
        get_with_retries(session, "https://x", SETTINGS, sleep=lambda _: None)
    assert exc.value.kind == "timeout"
    assert session.calls == 3

def test_server_error_waits_longer_than_normal_retries():
    waits = []
    session = FakeSession([FakeResp(503), FakeResp(200, b"ok")])
    get_with_retries(session, "https://x", SETTINGS | {"server_error_backoff_seconds": 10}, sleep=waits.append)
    assert waits == [10]

def test_pacing_spaces_requests_to_the_same_site():
    waits = []
    now = [0.0]

    def clock():
        return now[0]

    def sleep(seconds):
        waits.append(seconds)
        now[0] += seconds

    settings = SETTINGS | {"host_min_interval_seconds": {"news.google.com": 3}}
    session = FakeSession([FakeResp(200, b"a"), FakeResp(200, b"b")])
    get_with_retries(session, "https://news.google.com/rss/x", settings, sleep=sleep, clock=clock)
    get_with_retries(session, "https://news.google.com/rss/y", settings, sleep=sleep, clock=clock)
    assert waits == [3]