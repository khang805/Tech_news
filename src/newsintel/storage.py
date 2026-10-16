"""JSON storage: atomic writes, pruning old items, and recovery from a corrupted file."""
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path

from .models import parse_utc, to_utc_iso

log = logging.getLogger(__name__)
SCHEMA_VERSION = 1
SEEN_RETENTION_DAYS = 180
RUN_HISTORY_LIMIT = 30


def empty_db() -> dict:
    return {"schema_version": SCHEMA_VERSION, "last_run_utc": None, "articles": [], "seen_ids": [], "run_history": []}


def load_db(path: Path) -> dict:
    if not path.exists():
        return empty_db()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("top-level JSON is not an object")
    except (OSError, ValueError) as exc:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = path.with_name(f"articles.corrupt-{stamp}.json")
        path.rename(backup)
        log.error("articles.json could not be read (%s); moved to %s and starting fresh", exc, backup.name)
        return empty_db()
    db = empty_db()
    db.update({k: v for k, v in data.items() if k in db})
    return db


def save_db(path: Path, db: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)  # atomic on the same filesystem


def seen_set(db: dict) -> set[str]:
    return {s["id"] for s in db["seen_ids"]}


def mark_seen(db: dict, ids, now: datetime) -> None:
    known = seen_set(db)
    stamp = to_utc_iso(now)
    for article_id in ids:
        if article_id not in known:
            db["seen_ids"].append({"id": article_id, "added_utc": stamp})
            known.add(article_id)


def prune(db: dict, now: datetime, retention_days: int) -> int:
    """Remove articles older than retention_days. Their ids stay in seen_ids for 180 days."""
    cutoff = now - timedelta(days=retention_days)
    kept, removed = [], []
    for art in db["articles"]:
        (removed if parse_utc(art["published_utc"]) < cutoff else kept).append(art)
    db["articles"] = kept
    mark_seen(db, [a["id"] for a in removed], now)
    seen_cutoff = now - timedelta(days=SEEN_RETENTION_DAYS)
    db["seen_ids"] = [s for s in db["seen_ids"] if parse_utc(s["added_utc"]) >= seen_cutoff]
    return len(removed)


def record_run(db: dict, summary: dict, now: datetime) -> None:
    db["last_run_utc"] = to_utc_iso(now)
    db["run_history"] = (db["run_history"] + [summary])[-RUN_HISTORY_LIMIT:]
