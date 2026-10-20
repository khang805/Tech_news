"""Supabase storage through its built-in REST API (plain HTTPS, no extra packages).
Writes use the SERVICE key (secret, GitHub Actions only). The website reads with the ANON key (public, read-only by RLS)."""
import requests

from .models import to_utc_iso

PAGE = 1000


class StoreError(Exception):
    pass


class SupabaseStore:
    kind = "supabase"

    def __init__(self, url: str, service_key: str, session=None, timeout: int = 60):
        self.base = url.rstrip("/") + "/rest/v1"
        self.headers = {"apikey": service_key, "Authorization": f"Bearer {service_key}"}
        self.session = session or requests.Session()
        self.timeout = timeout

    def _check(self, resp, action: str) -> None:
        if resp.status_code >= 300:
            raise StoreError(f"{action} failed: HTTP {resp.status_code} {resp.text[:200]}")

    def _read_all(self, table: str, select: str, order: str | None = None) -> list[dict]:
        rows, offset = [], 0
        while True:
            params = {"select": select}
            if order:
                params["order"] = order
            headers = {**self.headers, "Range-Unit": "items", "Range": f"{offset}-{offset + PAGE - 1}"}
            resp = self.session.get(f"{self.base}/{table}", params=params, headers=headers, timeout=self.timeout)
            self._check(resp, f"read {table}")
            batch = resp.json()
            rows.extend(batch)
            if len(batch) < PAGE:
                return rows
            offset += PAGE

    def load_articles(self) -> list[dict]:
        return [row["data"] for row in self._read_all("articles", "data", order="published_utc.desc")]

    def load_seen(self) -> list[dict]:
        return self._read_all("seen_ids", "id,added_utc")

    def _upsert(self, table: str, rows: list[dict], on_conflict: str, batch_size: int = 500,
                ignore_duplicates: bool = False) -> None:
        prefer = "resolution=ignore-duplicates" if ignore_duplicates else "resolution=merge-duplicates"
        headers = {**self.headers, "Content-Type": "application/json", "Prefer": prefer}
        for start in range(0, len(rows), batch_size):
            resp = self.session.post(f"{self.base}/{table}", params={"on_conflict": on_conflict},
                                     json=rows[start:start + batch_size], headers=headers, timeout=self.timeout)
            self._check(resp, f"write {table}")

    def upsert_articles(self, articles: list[dict]) -> None:
        rows = [{"id": a["id"], "published_utc": a["published_utc"], "data": a} for a in articles]
        self._upsert("articles", rows, "id", batch_size=100)

    def add_seen(self, ids: list[str], now_iso: str) -> None:
        self._upsert("seen_ids", [{"id": i, "added_utc": now_iso} for i in ids], "id", ignore_duplicates=True)

    def set_meta(self, key: str, value) -> None:
        self._upsert("meta", [{"key": key, "value": value}], "key")

    def _delete_older(self, table: str, column: str, cutoff_iso: str) -> int:
        headers = {**self.headers, "Prefer": "return=representation"}
        resp = self.session.delete(f"{self.base}/{table}", params={column: f"lt.{cutoff_iso}"},
                                   headers=headers, timeout=self.timeout)
        self._check(resp, f"prune {table}")
        return len(resp.json()) if resp.content else 0

    def persist(self, changed: list[dict], new_seen_ids: list[str], now, article_cutoff, seen_cutoff,
                last_run_iso: str | None = None) -> int:
        """Write changed articles, remember new IDs, delete old rows. Returns the number of articles deleted."""
        self.upsert_articles(changed)
        self.add_seen(new_seen_ids, to_utc_iso(now))
        pruned = self._delete_older("articles", "published_utc", to_utc_iso(article_cutoff))
        self._delete_older("seen_ids", "added_utc", to_utc_iso(seen_cutoff))
        if last_run_iso:
            self.set_meta("last_run_utc", last_run_iso)
        return pruned
