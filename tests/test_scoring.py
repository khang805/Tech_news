from datetime import datetime, timedelta, timezone

from newsintel.scoring import categorize, score_article

NOW = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)


def test_source_priority_points_and_old_article():
    score, level, reasons = score_article("Plain title", "", 5, NOW - timedelta(days=5), NOW, [], 70)
    assert score == 25
    assert "source priority 5" in reasons
    assert level == "Low"


def test_release_keywords_add_points():
    score, _, reasons = score_article("Lab releases model v2", "Now open source", 1,
                                      NOW - timedelta(days=5), NOW, [], 70)
    assert score == 5 + 30  # priority 5 + release, version, open-source
    assert "release keyword: release" in reasons


def test_funding_keywords_add_points():
    score, _, reasons = score_article("Startup raises Series A", "", 1, NOW - timedelta(days=5), NOW, [], 70)
    assert score == 5 + 20  # priority 5 + funding, series-a
    assert "funding keyword: funding" in reasons


def test_security_text_scores_on_release_words_only():
    score, level, _ = score_article("Critical CVE-2026-1234 vulnerability patched", "", 5,
                                    NOW - timedelta(hours=1), NOW, [], 70)
    assert score == 25 + 20  # priority + recency; security words are no longer a scoring category
    assert level == "Medium"


def test_entity_points_and_score_cap():
    score, level, _ = score_article(
        "OpenAI launches v2 release, open source, announces general availability GA with funding raised",
        "", 5, NOW - timedelta(hours=1), NOW, ["OpenAI"], 70)
    assert score == 100
    assert level == "High"


def test_level_thresholds():
    _, low, _ = score_article("Plain", "", 3, NOW - timedelta(days=5), NOW, [], 70)
    _, medium, _ = score_article("Plain", "", 5, NOW - timedelta(hours=1), NOW, [], 70)
    assert low == "Low"
    assert medium == "Medium"


def test_categorize_prefers_feed_category_then_keywords():
    rules = {"High Performance Computing": ["supercomputer"], "NVIDIA": ["nvidia"]}
    assert categorize("Anything", "", "Feed Category", rules, "General") == "Feed Category"
    assert categorize("New NVIDIA chip", "", "", rules, "General") == "NVIDIA"
    assert categorize("Nothing matches", "", "", rules, "General") == "General"
