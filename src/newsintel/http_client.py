"""HTTP session with a User-Agent, timeouts, and retries with exponential backoff."""
import logging
import time

import requests

log = logging.getLogger(__name__)


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
    return session


def get_with_retries(session, url: str, settings: dict, sleep=time.sleep):
    """Return the response for HTTP 200. Retries timeouts, network errors, 429 and 5xx. Other 4xx fail at once."""
    timeout = settings["request_timeout_seconds"]
    retries = settings["max_retries"]
    backoff = settings["backoff_seconds"]
    last_error = None
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, timeout=timeout)
        except requests.Timeout:
            last_error = FetchError("timeout", f"timed out after {timeout}s")
        except requests.RequestException as exc:
            last_error = FetchError("network", type(exc).__name__)
        else:
            if resp.status_code == 200:
                return resp
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = FetchError(f"http_{resp.status_code}", f"HTTP {resp.status_code}")
            else:
                raise FetchError(f"http_{resp.status_code}", f"HTTP {resp.status_code}")
        if attempt < retries:
            delay = backoff * (2 ** attempt)
            log.warning("attempt %d for %s failed (%s); retrying in %ss", attempt + 1, url, last_error.kind, delay)
            sleep(delay)
    raise last_error
