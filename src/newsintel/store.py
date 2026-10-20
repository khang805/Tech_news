"""Storage backend chooser. Supabase when SUPABASE_URL and SUPABASE_SERVICE_KEY are set (GitHub Actions).
Otherwise a local JSON file in data/ (offline tests and local runs)."""
import os
from pathlib import Path

from .config import DATA_DIR
from .models import parse_utc, to_utc_iso
from .storage import load_db, save_db
from .supabase_store import StoreError, SupabaseStore  # noqa: F401  (StoreError re-exported)


class LocalStore:
    kind = "local"

    def __init__(self, path: Path = DATA_DIR / "articles.json"):
        self.path = path
        self.db = load_db(path)

    def load_articles(self) -> list[dict]:
        return list(self.db["articles"])

    def load_seen(self) -> list[dict]:
        return list(self.db["seen_ids"])

    def persist(self, changed: list[dict], new_seen_ids: list[str], now, article_cutoff, seen_cutoff,
                last_run_iso: str | None = None) -> int:
        by_id = {a["id"]: a for a in self.db["articles"]}
        for a in changed:
            by_id[a["id"]] = a
        kept = [a for a in by_id.values() if parse_utc(a["published_utc"]) >= article_cutoff]
        pruned = len(by_id) - len(kept)
        self.db["articles"] = kept

        known = {s["id"] for s in self.db["seen_ids"]}
        stamp = to_utc_iso(now)
        for article_id in new_seen_ids:
            if article_id not in known:
                self.db["seen_ids"].append({"id": article_id, "added_utc": stamp})
                known.add(article_id)
        self.db["seen_ids"] = [s for s in self.db["seen_ids"] if parse_utc(s["added_utc"]) >= seen_cutoff]

        if last_run_iso:
            self.db["last_run_utc"] = last_run_iso
        save_db(self.path, self.db)
        return pruned


def get_store(local_path: Path | None = None):
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if url and key:
        return SupabaseStore(url, key)
    return LocalStore(local_path or DATA_DIR / "articles.json")
