from datetime import datetime, timedelta, timezone

from newsintel.storage import empty_db, load_db, mark_seen, prune, save_db, seen_set

NOW = datetime(2026, 10, 13, 12, tzinfo=timezone.utc)


def art(article_id, days_old):
    return {"id": article_id, "published_utc": (NOW - timedelta(days=days_old)).isoformat(timespec="seconds")}


def test_missing_file_gives_empty_db(tmp_path):
    db = load_db(tmp_path / "articles.json")
    assert db["articles"] == [] and db["seen_ids"] == []


def test_save_and_load_round_trip(tmp_path):
    path = tmp_path / "articles.json"
    db = empty_db()
    db["articles"].append(art("a", 1))
    save_db(path, db)
    assert load_db(path)["articles"][0]["id"] == "a"


def test_prune_removes_old_articles_but_remembers_their_ids():
    db = empty_db()
    db["articles"] = [art("new", 1), art("old", 100)]
    assert prune(db, NOW, retention_days=90) == 1
    assert [a["id"] for a in db["articles"]] == ["new"]
    assert "old" in seen_set(db)


def test_corrupt_file_is_moved_aside_not_discarded(tmp_path):
    path = tmp_path / "articles.json"
    path.write_text("{not json", encoding="utf-8")
    db = load_db(path)
    assert db["articles"] == []
    backups = list(tmp_path.glob("articles.corrupt-*.json"))
    assert len(backups) == 1 and not path.exists()


def test_seen_ids_expire_after_180_days():
    db = empty_db()
    db["seen_ids"] = [{"id": "ancient", "added_utc": (NOW - timedelta(days=200)).isoformat(timespec="seconds")}]
    prune(db, NOW, 90)
    assert "ancient" not in seen_set(db)


def test_mark_seen_has_no_duplicates():
    db = empty_db()
    mark_seen(db, ["x", "x"], NOW)
    mark_seen(db, ["x"], NOW)
    assert len(db["seen_ids"]) == 1
