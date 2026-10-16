"""Text cleaning and link normalization. This module only cleans and selects source text; it never writes new words."""
import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

TRACKING_PARAMS = {"fbclid", "gclid", "ref", "ref_src"}
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def clean_html(raw: str) -> str:
    """Remove tags, scripts and styles, keeping only visible text."""
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return collapse_ws(soup.get_text(" "))


def split_sentences(text: str) -> list[str]:
    text = collapse_ws(text)
    if not text:
        return []
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def word_count(text: str) -> int:
    return len(text.split())


def trim(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def normalize_link(url: str) -> str:
    """Lowercase host, drop www., trailing slash, fragment and tracking parameters."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/")
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in TRACKING_PARAMS
    ]
    return urlunsplit(((parts.scheme or "https").lower(), host, path, urlencode(sorted(query)), ""))


def article_id(link: str) -> str:
    return hashlib.sha256(normalize_link(link).encode("utf-8")).hexdigest()


def normalize_title(title: str) -> str:
    return collapse_ws(re.sub(r"[^a-z0-9 ]+", " ", (title or "").lower()))
