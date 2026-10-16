"""Builds Article records. The one-line overview and the paragraph only use text copied from the source."""
from datetime import datetime

from .fetcher import RawItem
from .models import Article, to_utc_iso
from .scoring import categorize, score_article
from .text_utils import article_id, split_sentences, trim, word_count

INSUFFICIENT_OVERVIEW = "Limited source content: only the title and link are available."
PARAGRAPH_SENTENCES = 6


def build_text_fields(source_text: str) -> dict:
    """overview = one line (the first source sentence); explanation = one paragraph (the next sentences)."""
    words = word_count(source_text)
    if words < 15:
        return {"overview": INSUFFICIENT_OVERVIEW, "explanation": "", "content_status": "insufficient"}
    sentences = split_sentences(source_text)
    one_line = trim(sentences[0], 220)
    paragraph = " ".join(sentences[1:1 + PARAGRAPH_SENTENCES]).strip()
    if not paragraph:
        paragraph = "The source text has no further detail beyond the line above."
    status = "full" if words >= 60 else "partial"
    return {"overview": one_line, "explanation": paragraph, "content_status": status}


def build_article(item: RawItem, settings: dict, now: datetime, source_text: str) -> Article:
    feed = item.feed
    priority = int(feed.get("source_priority", 3))
    category = categorize(item.title, source_text, feed.get("category") or "",
                          settings["category_keywords"], settings["default_category"])
    score, level, reasons = score_article(
        item.title, source_text, priority, item.published, now,
        settings["major_entities"], settings["high_importance_threshold"],
    )
    article = Article(
        id=article_id(item.link),
        title=item.title,
        link=item.link,
        source_name=feed["name"],
        category=category,
        source_priority=priority,
        published_utc=to_utc_iso(item.published),
        first_seen_utc=to_utc_iso(now),
        importance_score=score,
        importance_level=level,
        importance_reasons=reasons,
        impact_level=level,
        impact_source="rules",
        date_is_estimated=item.date_is_estimated,
        **build_text_fields(source_text),
    )
    article.relevance = (
        f"Rule-based score {score} ({level}). Reasons: {'; '.join(reasons) or 'none'}. Category: {category}."
    )
    return article
