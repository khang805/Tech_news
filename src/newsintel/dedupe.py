"""Duplicate detection: same normalized link, or a near-identical title within a recent window."""
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from .models import Article, parse_utc
from .text_utils import normalize_title


def is_similar_title(a: str, b: str, threshold: float) -> bool:
    return SequenceMatcher(None, normalize_title(a), normalize_title(b)).ratio() >= threshold


def _add_source(article: Article, source: str) -> None:
    if source != article.source_name and source not in article.also_reported_by:
        article.also_reported_by.append(source)


def dedupe_batch(candidates: list[Article], stored: list[Article], seen_ids: set[str],
                 now: datetime, threshold: float = 0.9, window_days: int = 7) -> tuple[list[Article], int]:
    """Return (new_articles, duplicate_count). Higher-priority sources win; others are recorded in also_reported_by."""
    by_id = {a.id: a for a in stored}
    seen = set(seen_ids) | set(by_id)
    window_start = now - timedelta(days=window_days)
    recent = [a for a in stored if parse_utc(a.published_utc) >= window_start]
    kept: list[Article] = []
    duplicates = 0

    for cand in sorted(candidates, key=lambda a: (-a.source_priority, a.published_utc)):
        if cand.id in seen:
            if cand.id in by_id:
                _add_source(by_id[cand.id], cand.source_name)
            duplicates += 1
            continue
        match = next((a for a in recent if is_similar_title(cand.title, a.title, threshold)), None)
        if match is None:
            match = next((k for k in kept if is_similar_title(cand.title, k.title, threshold)), None)
        if match is not None:
            _add_source(match, cand.source_name)
            seen.add(cand.id)
            duplicates += 1
            continue
        seen.add(cand.id)
        kept.append(cand)
    return kept, duplicates
