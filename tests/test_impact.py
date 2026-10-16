from datetime import datetime, timedelta, timezone

from newsintel import impact
from newsintel.digest import period_pool
from newsintel.impact import AIUnavailable, classify_articles, select_important
from newsintel.models import Article

NOW = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)
AI_CFG = {"gemini_model": "m", "groq_model": "m", "batch_size": 2, "max_items_per_run": 10,
          "max_selection_candidates": 50, "pause_seconds": 0}


def make(i, score=50, hours_ago=2, digested=False, level="Low"):
    pub = NOW - timedelta(hours=hours_ago)
    return Article(id=f"id{i}", title=f"Story {i}", link=f"https://x.com/{i}", source_name="S",
                   category="AI Agents", source_priority=3,
                   published_utc=pub.isoformat(timespec="seconds"),
                   first_seen_utc=NOW.isoformat(timespec="seconds"),
                   importance_score=score, importance_level="Low", impact_level=level,
                   overview="Some overview text.", digested=digested)


def test_classify_uses_ai_labels_and_ignores_unknown_ids(monkeypatch):
    arts = [make(0), make(1), make(2)]
    replies = [
        {"items": [{"id": "a0", "impact": "high"}, {"id": "a1", "impact": "Medium"}]},
        {"items": [{"id": "a0", "impact": "Huge"}, {"id": "zzz", "impact": "High"}]},
    ]
    monkeypatch.setattr(impact, "ask_json", lambda prompt, cfg: replies.pop(0))
    labelled = classify_articles(arts, AI_CFG, sleep=lambda _: None)
    assert labelled == 2
    assert arts[0].impact_level == "High" and arts[0].impact_source == "ai"
    assert arts[1].impact_level == "Medium"
    assert arts[2].impact_source == "rules"  # invalid reply: rule-based level kept


def test_classify_falls_back_when_ai_unavailable(monkeypatch):
    def down(prompt, cfg):
        raise AIUnavailable("no keys")
    monkeypatch.setattr(impact, "ask_json", down)
    arts = [make(0, level="Medium")]
    assert classify_articles(arts, AI_CFG, sleep=lambda _: None) == 0
    assert arts[0].impact_level == "Medium"


def test_select_important_uses_ai_choice(monkeypatch):
    pool = [make(i, score=50 + i) for i in range(6)]
    monkeypatch.setattr(impact, "ask_json", lambda prompt, cfg: {"selected": ["a0", "a5"]})
    picked, method = select_important(pool, 2, "weekly", AI_CFG)
    assert method == "AI"
    assert {a.id for a in picked} == {"id0", "id5"}


def test_select_important_falls_back_to_score(monkeypatch):
    def down(prompt, cfg):
        raise AIUnavailable("offline")
    monkeypatch.setattr(impact, "ask_json", down)
    pool = [make(i, score=i * 10) for i in range(6)]
    picked, method = select_important(pool, 2, "weekly", AI_CFG)
    assert method == "score"
    assert [a.id for a in picked] == ["id5", "id4"]


def test_select_important_without_ai_is_score_only():
    pool = [make(i, score=i) for i in range(4)]
    picked, method = select_important(pool, 2, "monthly", AI_CFG, fallback_only=True)
    assert method == "score" and len(picked) == 2


def test_period_pool_day_skips_digested_week_keeps_them():
    arts = [make(1, hours_ago=2, digested=True), make(2, hours_ago=2), make(3, hours_ago=100)]
    assert [a.id for a in period_pool(arts, NOW, "day")] == ["id2"]
    assert {a.id for a in period_pool(arts, NOW, "week")} == {"id1", "id2", "id3"}
    assert {a.id for a in period_pool(arts, NOW, "month")} == {"id1", "id2", "id3"}


def test_week_excludes_older_than_seven_days():
    old = make(9, hours_ago=24 * 10)
    assert old.id not in {a.id for a in period_pool([old], NOW, "week")}
    assert old.id in {a.id for a in period_pool([old], NOW, "month")}
