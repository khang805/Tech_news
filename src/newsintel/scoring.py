"""Rule-based category and importance scoring. Each point is listed in the reasons, so scores are explainable."""
import re
from datetime import datetime, timedelta

RELEASE_SIGNALS = {
    "release": re.compile(r"\brelease[sd]?\b", re.I),
    "launch": re.compile(r"\blaunch(?:es|ed)?\b", re.I),
    "introduces": re.compile(r"\bintroduc(?:es|ing|ed)\b", re.I),
    "open-source": re.compile(r"\bopen[- ]source\b", re.I),
    "version": re.compile(r"\bv\d+(?:\.\d+)*\b", re.I),
    "announces": re.compile(r"\bannounce[sd]?\b", re.I),
    "available now": re.compile(r"\bavailable now\b", re.I),
    "new model": re.compile(r"\bnew model\b", re.I),
    "general availability": re.compile(r"\bgeneral availability\b", re.I),
    "GA": re.compile(r"\bGA\b"),  # case-sensitive on purpose
}
FUNDING_SIGNALS = {
    "funding": re.compile(r"\b(?:raises|raised|funding|series [a-e])\b", re.I),
    "acquisition": re.compile(r"\bacqui(?:res?|red|sition)\b", re.I),
}
FUNDING_SIGNALS = {
    "funding": re.compile(r"\b(?:raises|raised|funding|series [a-e])\b", re.I),
    "acquisition": re.compile(r"\bacqui(?:res?|red|sition)\b", re.I),
}
MAX_PRIORITY_POINTS = 25
MAX_KEYWORD_POINTS = 40
POINTS_PER_KEYWORD = 10
MAX_RECENCY_POINTS = 20
ENTITY_POINTS = 15


def _matches(signals: dict, text: str) -> list[str]:
    return [label for label, rx in signals.items() if rx.search(text)]


def _word_in(term: str, text: str) -> bool:
    return re.search(r"\b" + re.escape(term.lower()) + r"\b", text.lower()) is not None


def categorize(title: str, summary: str, feed_category: str, keyword_map: dict, default: str) -> str:
    if feed_category:
        return feed_category
    text = f"{title} {summary}"
    for category, terms in keyword_map.items():
        if any(_word_in(term, text) for term in terms):
            return category
    return default


def score_article(title: str, summary: str, source_priority: int, published: datetime,
                  now: datetime, entities: list[str], threshold: int) -> tuple[int, str, list[str]]:
    text = f"{title} {summary}"
    reasons: list[str] = []
    points = min(MAX_PRIORITY_POINTS, source_priority * 5)
    reasons.append(f"source priority {source_priority}")

    keyword_hits = [f"release keyword: {x}" for x in _matches(RELEASE_SIGNALS, text)]
    keyword_hits += [f"funding keyword: {x}" for x in _matches(FUNDING_SIGNALS, text)]
    keyword_hits += [f"funding keyword: {x}" for x in _matches(FUNDING_SIGNALS, text)]
    points += min(MAX_KEYWORD_POINTS, POINTS_PER_KEYWORD * len(keyword_hits))
    reasons.extend(keyword_hits)

    age = now - published
    if age <= timedelta(hours=24):
        points += MAX_RECENCY_POINTS
        reasons.append("published in last 24h")
    elif age <= timedelta(hours=48):
        points += MAX_RECENCY_POINTS // 2
        reasons.append("published in last 48h")

    found = [e for e in entities if _word_in(e, title)]
    if found:
        points += ENTITY_POINTS
        reasons.append("major entity in title: " + ", ".join(found[:3]))

    score = min(100, points)
    if score >= threshold:
        level = "High"
    elif score >= 40:
        level = "Medium"
    else:
        level = "Low"
    return score, level, reasons
