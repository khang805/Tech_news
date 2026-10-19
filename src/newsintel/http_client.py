"""HTTP session with a User-Agent, per-site pacing, timeouts, and retries with backoff.

Pacing: some sites (Google News) block bursts of requests. For those hosts we keep a minimum gap
between requests (host_min_interval_seconds in settings.yaml).
Retries: timeouts and network errors retry quickly. Server errors (5xx) and rate limits (429) wait
longer, and honour a Retry-After header if the server sends one."""
import logging
import time
from urllib.parse import urlsplit

import requests

log = logging.getLogger(__name__)
MAX_RETRY_AFTER = 120  # never wait longer than this because of a Retry-After header


class FetchError(Exception):
    """A recoverable problem with one feed or page. `kind` is a short label for the run report."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def make_session(settings: dict) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": settings["user_agent"],
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.5",
    })
    session.newsintel_last_request = {}  # host -> time of the last request, used for pacing
    return session


def _min_interval(url: str, settings: dict) -> float:
    host = urlsplit(url).netloc.lower()
    for domain, seconds in (settings.get("host_min_interval_seconds") or {}).items():
        if host == domain or host.endswith("." + domain):
            return float(seconds)
    return 0.0


def _pace(session, url: str, settings: dict, sleep, clock) -> None:
    gap = _min_interval(url, settings)
    if gap <= 0:
        return
    book = getattr(session, "newsintel_last_request", None)
    if book is None:
        book = {}
        session.newsintel_last_request = book
    host = urlsplit(url).netloc.lower()
    elapsed = clock() - book.get(host, float("-inf"))
    if elapsed < gap:
        sleep(gap - elapsed)
    book[host] = clock()


def _retry_after(resp) -> float | None:
    headers = getattr(resp, "headers", None) or {}
    try:
        return min(float(headers.get("Retry-After")), MAX_RETRY_AFTER)
    except (TypeError, ValueError):
        return None


def get_with_retries(session, url: str, settings: dict, sleep=time.sleep, clock=time.monotonic):
    """Return the response for HTTP 200. Other 4xx errors fail at once."""
    timeout = settings["request_timeout_seconds"]
    retries = settings["max_retries"]
    backoff = settings["backoff_seconds"]
    server_backoff = settings.get("server_error_backoff_seconds", 10)
    last_error = None
    for attempt in range(retries + 1):
        _pace(session, url, settings, sleep, clock)
        try:
            resp = session.get(url, timeout=timeout)
        except requests.Timeout:
            last_error = FetchError("timeout", f"timed out after {timeout}s")
            wait = backoff * (2 ** attempt)
        except requests.RequestException as exc:
            last_error = FetchError("network", type(exc).__name__)
            wait = backoff * (2 ** attempt)
        else:
            if resp.status_code == 200:
                return resp
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = FetchError(f"http_{resp.status_code}", f"HTTP {resp.status_code}")
                wait = max(server_backoff * (2 ** attempt), _retry_after(resp) or 0)
            else:
                raise FetchError(f"http_{resp.status_code}", f"HTTP {resp.status_code}")
        if attempt < retries:
            log.warning("attempt %d for %s failed (%s); retrying in %.0fs", attempt + 1, url, last_error.kind, wait)
            sleep(wait)
    raise last_error