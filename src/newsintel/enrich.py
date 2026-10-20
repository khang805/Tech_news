"""Gemini (free tier) writes one summary paragraph for each new story, and labels its impact.
One request covers a batch of stories, which keeps the number of free-tier requests low.
The model is told to use only the text it is given. A story with only a headline gets a one-sentence
summary that restates the headline, so it does not invent details."""
import json
import logging
import time

from .impact import LEVELS, AIUnavailable, _as_list, ask_json
from .models import Article
from .text_utils import collapse_ws

log = logging.getLogger(__name__)
MIN_SUMMARY = 40
MAX_SUMMARY = 1200

ENRICH_PROMPT = (
    "You write summaries for a tech news digest. For each item, use ONLY the title, source and text given.\n"
    "Return these fields for each item:\n"
    "- impact: High (major model or product launch, new chip or platform, large funding or acquisition, "
    "major security incident, significant AI or cloud policy change), Medium (notable update, new feature, "
    "partnership, smaller funding round), or Low (minor update, opinion, tutorial, routine news).\n"
    "- summary: exactly one paragraph of 3 to 5 sentences that covers every important point in the text: "
    "what happened, who is involved, key numbers, dates and details, and why it matters if the text says so. "
    "The reader should not need to open the article.\n"
    "- basis: \"text\" if the text field contains details, or \"headline\" if the text is empty.\n"
    "Rules: never add facts, numbers, names, dates, quotes or opinions that are not in the input. "
    "If basis is \"headline\", write one sentence that restates the title neutrally, with no added details.\n"
    'Return JSON only, in this form: {"items":[{"id":"a0","impact":"High","summary":"...","basis":"text"}]}, '
    "with every id included.\n"
    "Items:\n"
)


def _source_text(a: Article) -> str:
    if a.content_status == "insufficient":
        return ""
    return collapse_ws(f"{a.overview} {a.explanation}")


def enrich_articles(articles: list[Article], ai_cfg: dict, sleep=time.sleep) -> dict:
    """Set impact, the one-paragraph summary (stored in overview) and summary_source on new articles.
    If a batch fails, its stories keep the source text and rule-based impact."""
    size = int(ai_cfg.get("enrich_batch_size", 8))
    targets = articles[: ai_cfg["max_items_per_run"]]
    counts = {"summaries": 0, "impact": 0}
    for start in range(0, len(targets), size):
        chunk = targets[start:start + size]
        items = [{"id": f"a{i}", "title": a.title, "source": a.source_name, "category": a.category,
                  "text": _source_text(a)} for i, a in enumerate(chunk)]
        try:
            data = ask_json(ENRICH_PROMPT + json.dumps(items, ensure_ascii=False), ai_cfg)
        except AIUnavailable as exc:
            log.warning("AI enrichment unavailable; remaining stories keep source text and rule-based impact (%s)", exc)
            break
        rows = {str(x.get("id")): x for x in _as_list(data.get("items")) if isinstance(x, dict)}
        for i, art in enumerate(chunk):
            row = rows.get(f"a{i}")
            if not row:
                continue
            level = str(row.get("impact", "")).strip().capitalize()
            if level in LEVELS:
                art.impact_level = level
                art.impact_source = "ai"
                counts["impact"] += 1
            text = collapse_ws(str(row.get("summary", "")))
            if MIN_SUMMARY <= len(text) <= MAX_SUMMARY:
                art.overview = text          # the single paragraph shown for the story
                art.explanation = ""
                headline_only = str(row.get("basis", "")).strip().lower() == "headline"
                art.summary_source = "headline" if headline_only else "ai"
                counts["summaries"] += 1
        sleep(ai_cfg["pause_seconds"])
    log.info("AI labelled impact for %d and wrote %d summaries, from %d new stories",
             counts["impact"], counts["summaries"], len(targets))
    return counts
