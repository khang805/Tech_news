"""Free AI helpers. The AI only labels impact (High/Medium/Low) and picks important items.
It never writes summaries, so overviews and explanations still come only from the source text.
Order: Google Gemini (free tier) -> Groq (free tier) -> rule-based fallback."""
import json
import logging
import os
import re
import time

import requests

from .models import Article, parse_utc

log = logging.getLogger(__name__)
LEVELS = ("High", "Medium", "Low")

CLASSIFY_PROMPT = (
    "You label tech news by impact. Use ONLY the title, source and summary given. Do not add facts.\n"
    "- High: major model or product launch, new chip or platform, large funding or acquisition, "
    "major security incident, or a significant policy change for AI or cloud.\n"
    "- Medium: notable update, new feature, partnership, or smaller funding round.\n"
    "- Low: minor update, opinion, tutorial, or routine news.\n"
    'Return JSON only in this form: {"items":[{"id":"a0","impact":"High"}]} and include every id.\n'
    "Items:\n"
)

SELECT_PROMPT = (
    "Choose the {N} most important items for a {PERIOD} tech briefing. Use ONLY the given text. "
    "Prefer major model, chip, cloud and funding news, and spread picks across categories. "
    "Return JSON only in this form: {\"selected\":[\"a3\",\"a10\"]}.\n"
    "Items:\n"
)


class AIUnavailable(Exception):
    pass


def ai_configured() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GROQ_API_KEY"))


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    return re.sub(r"\s*```$", "", text)


def _post_gemini(prompt: str, ai_cfg: dict) -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise AIUnavailable("no GEMINI_API_KEY")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{ai_cfg['gemini_model']}:generateContent"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.1},
    }
    resp = requests.post(url, headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                         json=body, timeout=60)
    if resp.status_code != 200:
        raise AIUnavailable(f"HTTP {resp.status_code}")
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


def _post_groq(prompt: str, ai_cfg: dict) -> str:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise AIUnavailable("no GROQ_API_KEY")
    body = {
        "model": ai_cfg["groq_model"],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = requests.post("https://api.groq.com/openai/v1/chat/completions",
                         headers={"Authorization": f"Bearer {key}"}, json=body, timeout=60)
    if resp.status_code != 200:
        raise AIUnavailable(f"HTTP {resp.status_code}")
    return resp.json()["choices"][0]["message"]["content"]


PROVIDERS = (("Gemini", _post_gemini), ("Groq", _post_groq))


def ask_json(prompt: str, ai_cfg: dict) -> dict:
    """Ask the first working free provider for a JSON object. Raises AIUnavailable if none work."""
    errors = []
    for name, call in PROVIDERS:
        try:
            data = json.loads(_strip_fences(call(prompt, ai_cfg)))
            if not isinstance(data, dict):
                raise ValueError("reply is not a JSON object")
            return data
        except AIUnavailable as exc:
            errors.append(f"{name}: {exc}")
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError) as exc:
            errors.append(f"{name}: {type(exc).__name__}")
    raise AIUnavailable("; ".join(errors))


def _as_list(value) -> list:
    return value if isinstance(value, list) else []


def classify_articles(articles: list[Article], ai_cfg: dict, sleep=time.sleep) -> int:
    """Set impact_level (and impact_source='ai') on articles. Failures keep the rule-based level."""
    targets = articles[: ai_cfg["max_items_per_run"]]
    labelled = 0
    size = ai_cfg["batch_size"]
    for start in range(0, len(targets), size):
        chunk = targets[start:start + size]
        items = [{"id": f"a{i}", "title": a.title, "source": a.source_name,
                  "category": a.category, "summary": a.overview[:300]} for i, a in enumerate(chunk)]
        try:
            data = ask_json(CLASSIFY_PROMPT + json.dumps(items, ensure_ascii=False), ai_cfg)
        except AIUnavailable as exc:
            log.warning("AI impact labels unavailable, keeping rule-based levels (%s)", exc)
            break
        labels = {str(x.get("id")): str(x.get("impact", "")).strip().capitalize()
                  for x in _as_list(data.get("items")) if isinstance(x, dict)}
        for i, art in enumerate(chunk):
            level = labels.get(f"a{i}")
            if level in LEVELS:
                art.impact_level = level
                art.impact_source = "ai"
                labelled += 1
        sleep(ai_cfg["pause_seconds"])
    log.info("AI labelled impact for %d of %d new articles", labelled, len(targets))
    return labelled


def select_important(pool: list[Article], n: int, period_label: str, ai_cfg: dict,
                     fallback_only: bool = False) -> tuple[list[Article], str]:
    """Pick the n most important articles. Returns (articles, method) where method is 'AI' or 'score'."""
    ranked = sorted(pool, key=lambda a: (-a.importance_score, -parse_utc(a.published_utc).timestamp()))
    if len(ranked) <= n:
        return ranked, "score"
    if fallback_only:
        return ranked[:n], "score"
    candidates = ranked[: ai_cfg["max_selection_candidates"]]
    items = [{"id": f"a{i}", "title": a.title, "source": a.source_name, "category": a.category,
              "impact": a.impact_level, "summary": a.overview[:200]} for i, a in enumerate(candidates)]
    prompt = SELECT_PROMPT.replace("{N}", str(n)).replace("{PERIOD}", period_label) + json.dumps(items, ensure_ascii=False)
    try:
        data = ask_json(prompt, ai_cfg)
    except AIUnavailable as exc:
        log.warning("AI selection unavailable, ranking by score instead (%s)", exc)
        return ranked[:n], "score"
    index = {f"a{i}": a for i, a in enumerate(candidates)}
    picked: list[Article] = []
    for cid in _as_list(data.get("selected")):
        art = index.get(str(cid))
        if art and art.id not in {p.id for p in picked}:
            picked.append(art)
    if not picked:
        return ranked[:n], "score"
    picked = sorted(picked[:n], key=lambda a: -a.importance_score)
    return picked, "AI"
