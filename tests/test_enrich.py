from datetime import datetime, timezone

from newsintel import enrich
from newsintel.enrich import enrich_articles
from newsintel.impact import AIUnavailable
from newsintel.models import Article

NOW = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
CFG = {"max_items_per_run": 50, "enrich_batch_size": 2, "pause_seconds": 0}


def make(i, text="Source sentence one. Sentence two follows here.", status="full"):
    return Article(id=f"id{i}", title=f"Story {i}", link=f"https://x.com/{i}", source_name="Src",
                   category="NVIDIA", source_priority=3, published_utc=NOW.isoformat(timespec="seconds"),
                   first_seen_utc=NOW.isoformat(timespec="seconds"), overview=text, explanation="",
                   content_status=status)


def test_gemini_sets_impact_line_and_paragraph(monkeypatch):
    arts = [make(0), make(1)]
    reply = {"items": [
        {"id": "a0", "impact": "high", "summary": "Company launches a model that runs faster and is free to use. It was released this week.", "basis": "text"},
        {"id": "a1", "impact": "Medium", "summary": "A partner was announced, according to the headline only, with no further details available.", "basis": "headline"},
    ]}
    monkeypatch.setattr(enrich, "ask_json", lambda prompt, cfg: reply)
    counts = enrich_articles(arts, CFG, sleep=lambda _: None)
    assert counts == {"summaries": 2, "impact": 2}
    assert arts[0].impact_level == "High" and arts[0].impact_source == "ai"
    assert arts[0].overview == "Company launches a model that runs faster and is free to use. It was released this week."
    assert arts[0].explanation == ""
    assert arts[0].summary_source == "ai"
    assert arts[1].impact_level == "Medium" and arts[1].summary_source == "headline"


def test_invalid_or_missing_answers_keep_source_text(monkeypatch):
    arts = [make(0, text="Original feed text stays."), make(1)]
    reply = {"items": [{"id": "a0", "impact": "Huge", "summary": "short"}]}
    monkeypatch.setattr(enrich, "ask_json", lambda prompt, cfg: reply)
    counts = enrich_articles(arts, CFG, sleep=lambda _: None)
    assert counts == {"summaries": 0, "impact": 0}
    assert arts[0].overview == "Original feed text stays." and arts[0].summary_source == "source"
    assert arts[0].impact_source == "rules"


def test_ai_down_leaves_everything_as_before(monkeypatch):
    def down(prompt, cfg):
        raise AIUnavailable("offline")
    monkeypatch.setattr(enrich, "ask_json", down)
    arts = [make(0)]
    assert enrich_articles(arts, CFG, sleep=lambda _: None) == {"summaries": 0, "impact": 0}
    assert arts[0].summary_source == "source"


def test_headline_only_story_is_sent_with_empty_text(monkeypatch):
    seen = {}

    def capture(prompt, cfg):
        seen["prompt"] = prompt
        return {"items": []}
    monkeypatch.setattr(enrich, "ask_json", capture)
    enrich_articles([make(0, text="Limited source content: only the title and link are available.",
                          status="insufficient")], CFG, sleep=lambda _: None)
    assert '"text": ""' in seen["prompt"]
