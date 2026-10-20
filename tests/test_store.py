from datetime import datetime, timedelta, timezone

import pytest

from newsintel.store import LocalStore, get_store
from newsintel.supabase_store import StoreError, SupabaseStore

NOW = datetime(2026, 10, 19, 12, tzinfo=timezone.utc)


class FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else []
        self.content = b"x" if body else b""
        self.text = str(body)

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def _next(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)

    def get(self, url, **kwargs):
        return self._next("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self._next("POST", url, **kwargs)

    def delete(self, url, **kwargs):
        return self._next("DELETE", url, **kwargs)


def test_supabase_reads_all_pages():
    full = [{"data": {"id": str(i)}} for i in range(1000)]
    rest = [{"data": {"id": "x"}}] * 3
    session = FakeSession([FakeResp(206, full), FakeResp(206, rest)])
    store = SupabaseStore("https://proj.supabase.co", "service-key", session=session)
    assert len(store.load_articles()) == 1003
    assert session.calls[1][2]["headers"]["Range"] == "1000-1999"


def test_supabase_upsert_merges_on_id():
    session = FakeSession([FakeResp(201, [])])
    store = SupabaseStore("https://proj.supabase.co", "service-key", session=session)
    store.upsert_articles([{"id": "a1", "published_utc": "2026-10-19T00:00:00+00:00", "title": "T"}])
    method, url, kwargs = session.calls[0]
    assert method == "POST" and url.endswith("/rest/v1/articles")
    assert kwargs["params"] == {"on_conflict": "id"}
    assert kwargs["headers"]["Prefer"] == "resolution=merge-duplicates"


def test_supabase_error_is_raised_not_silent():
    store = SupabaseStore("https://proj.supabase.co", "k", session=FakeSession([FakeResp(401, {"message": "bad key"})]))
    with pytest.raises(StoreError):
        store.load_articles()


def test_local_store_persists_and_prunes(tmp_path):
    path = tmp_path / "articles.json"
    store = LocalStore(path)
    old = {"id": "old", "published_utc": (NOW - timedelta(days=60)).isoformat(timespec="seconds")}
    fresh = {"id": "new", "published_utc": (NOW - timedelta(days=1)).isoformat(timespec="seconds")}
    pruned = store.persist([old, fresh], ["old", "new"], NOW, NOW - timedelta(days=30), NOW - timedelta(days=180))
    assert pruned == 1
    assert [a["id"] for a in LocalStore(path).load_articles()] == ["new"]
    assert {s["id"] for s in LocalStore(path).load_seen()} == {"old", "new"}


def test_get_store_falls_back_to_local_without_keys(monkeypatch, tmp_path):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    assert get_store(tmp_path / "a.json").kind == "local"
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "k")
    assert get_store(tmp_path / "a.json").kind == "supabase"
