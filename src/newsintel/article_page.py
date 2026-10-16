"""Optional full-page text extraction. Checks robots.txt, caps size, and rate-limits each website."""
import logging
import time
from urllib import robotparser
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from .text_utils import collapse_ws

log = logging.getLogger(__name__)


def extract_article_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "aside", "form"]):
        tag.decompose()
    container = soup.find("article") or soup.find("main") or soup.body or soup
    paragraphs = [p.get_text(" ", strip=True) for p in container.find_all("p")]
    paragraphs = [p for p in paragraphs if len(p.split()) >= 5]
    text = " ".join(paragraphs) if paragraphs else container.get_text(" ")
    return collapse_ws(text)


class PageFetcher:
    def __init__(self, session, settings: dict, sleep=time.sleep, clock=time.monotonic):
        self.session = session
        self.timeout = settings["request_timeout_seconds"]
        self.max_bytes = settings["max_page_bytes"]
        self.rate_limit = settings["page_rate_limit_seconds"]
        self.user_agent = settings["user_agent"]
        self.sleep = sleep
        self.clock = clock
        self._robots: dict[str, robotparser.RobotFileParser] = {}
        self._last_hit: dict[str, float] = {}

    def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        host = parts.netloc
        if host not in self._robots:
            rp = robotparser.RobotFileParser()
            try:
                resp = self.session.get(f"{parts.scheme}://{host}/robots.txt", timeout=self.timeout)
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                elif resp.status_code in (401, 403):
                    rp.disallow_all = True
                else:
                    rp.allow_all = True
            except requests.RequestException:
                rp.disallow_all = True  # if robots.txt cannot be read, do not fetch the page
            self._robots[host] = rp
        return self._robots[host].can_fetch(self.user_agent, url)

    def fetch_text(self, url: str) -> str:
        """Return extracted article text, or "" if the page is blocked, missing, or unreadable."""
        try:
            if not self._allowed(url):
                log.info("robots.txt does not allow %s; using feed text only", url)
                return ""
            host = urlsplit(url).netloc
            elapsed = self.clock() - self._last_hit.get(host, float("-inf"))
            if elapsed < self.rate_limit:
                self.sleep(self.rate_limit - elapsed)
            self._last_hit[host] = self.clock()
            resp = self.session.get(url, timeout=self.timeout, stream=True)
            if resp.status_code != 200:
                log.info("article page returned HTTP %s: %s", resp.status_code, url)
                return ""
            chunks, total = [], 0
            for chunk in resp.iter_content(chunk_size=65536):
                chunks.append(chunk)
                total += len(chunk)
                if total >= self.max_bytes:
                    break
            html = b"".join(chunks)[: self.max_bytes].decode(resp.encoding or "utf-8", errors="replace")
            return extract_article_text(html)
        except Exception as exc:  # a broken page must never stop the run
            log.warning("could not read article page %s (%s)", url, type(exc).__name__)
            return ""
