from datetime import datetime, timedelta, timezone

from newsintel.dedupe import dedupe_batch
from newsintel.models import Article
from newsintel.text_utils import article_id

NOW = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)


def make(title, link, source, priority, hours_ago=1):
    pub = NOW - timedelta(hours=hours_ago)
    return Article(id=article_id(link), title=title, link=link, source_name=source, category="X",
                   source_priority=priority, published_utc=pub.isoformat(timespec="seconds"),
                   first_seen_utc=NOW.isoformat(timespec="seconds"))


def test_same_link_kept_once_and_higher_priority_wins():
    a = make("Model released", "https://x.com/a?utm_source=rss", "Low Src", 3)
    b = make("Model released", "https://x.com/a", "High Src", 4)
    new, dupes = dedupe_batch([a, b], [], set(), NOW)
    assert len(new) == 1 and dupes == 1
    assert new[0].source_name == "High Src"


def test_similar_titles_in_batch_keep_higher_priority_source():
    a = make("OpenAI releases new reasoning model", "https://a.com/1", "Low Blog", 2)
    b = make("OpenAI releases new reasoning model.", "https://b.com/1", "Big Blog", 5)
    new, _ = dedupe_batch([a, b], [], set(), NOW)
    assert len(new) == 1
    assert new[0].source_name == "Big Blog"
    assert new[0].also_reported_by == ["Low Blog"]


def test_similar_title_matches_stored_article():
    stored_art = make("DeepSeek releases open model", "https://s.com/1", "Stored Src", 3, hours_ago=5)
    cand = make("DeepSeek releases open model", "https://n.com/9", "New Src", 4)
    new, dupes = dedupe_batch([cand], [stored_art], set(), NOW)
    assert new == [] and dupes == 1
    assert "New Src" in stored_art.also_reported_by


def test_different_titles_are_kept():
    a = make("Kubernetes 1.40 released", "https://k.io/1", "K", 4)
    b = make("Cloudflare launches new WAF rules", "https://c.io/1", "C", 3)
    new, _ = dedupe_batch([a, b], [], set(), NOW)
    assert len(new) == 2


def test_seen_ids_block_reinsertion():
    a = make("Old item", "https://o.io/1", "O", 3)
    new, dupes = dedupe_batch([a], [], {a.id}, NOW)
    assert new == [] and dupes == 1
