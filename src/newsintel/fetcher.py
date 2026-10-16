"""Fetch RSS/Atom feeds and turn each entry into a RawItem."""
import calendar
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import feedparser

from .http_client import FetchError, get_with_retries
from .text_utils import collapse_ws

log = logging.getLogger(__name__)


@dataclass
class RawItem:
    feed: dict
    title: str
    link: str
    summary_html: str
    published: datetime
    date_is_estimated: bool


def _entry_date(entry, now: datetime):
    struct = entry.get("published_parsed") or entry.get("updated_parsed")
    if struct:
        try:
            return datetime.fromtimestamp(calendar.timegm(struct), tz=timezone.utc), False
        except (TypeError, ValueError, OverflowError):
            pass
    return now, True  # no usable date in the feed: use fetch time and mark it


def parse_feed(content: bytes, feed: dict, max_items: int, now: datetime) -> list[RawItem]:
    parsed = feedparser.parse(content)
    if parsed.bozo and not parsed.entries:
        exc_name = type(getattr(parsed, "bozo_exception", None)).__name__
        raise FetchError("invalid_xml", f"feed is not valid RSS/Atom ({exc_name})")
    items = []
    for entry in parsed.entries[:max_items]:
        title = collapse_ws(entry.get("title", ""))
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        summary = entry.get("summary") or entry.get("description") or ""
        if not summary and entry.get("content"):
            summary = entry["content"][0].get("value", "")
        published, estimated = _entry_date(entry, now)
        items.append(RawItem(feed, title, link, summary, published, estimated))
    if not items:
        raise FetchError("empty_feed", "feed returned no usable entries")
    return items


def fetch_feed(feed: dict, session, settings: dict, now: datetime, content: bytes | None = None) -> list[RawItem]:
    """Download (or use `content`, for offline fixtures) and parse one feed."""
    if content is None:
        content = get_with_retries(session, feed["url"], settings).content
    return parse_feed(content, feed, settings["max_items_per_feed"], now)
