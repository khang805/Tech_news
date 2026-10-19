from datetime import datetime, timezone

from newsintel.digest import build_digest
from newsintel.emailer import load_email_config, parse_recipients, send_email
from newsintel.models import Article

NOW = datetime(2026, 10, 13, 1, tzinfo=timezone.utc)
BASE = {"host": "smtp.example.com", "port": 587, "username": "", "password": "",
        "sender": "", "recipients": ["a@example.com"]}
SETTINGS = {"timezone_display": "Asia/Karachi", "email": {"subject_prefix": "[T]"}}


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def send_message(self, msg):
        FakeSMTP.sent.append((msg["To"], msg["Subject"]))


def test_dry_run_sends_nothing_and_reports_success():
    assert send_email(BASE, "subject", "text", "<p>html</p>", dry_run=True) is True


def test_missing_credentials_skip_without_crashing():
    assert send_email(BASE, "subject", "text", "<p>html</p>") is False


def test_one_message_per_recipient():
    FakeSMTP.sent = []
    cfg = dict(BASE, username="me@example.com", password="app-pass", sender="me@example.com",
               recipients=["a@example.com", "b@example.com", "c@example.com"])
    assert send_email(cfg, "Daily digest", "text", "<p>html</p>", smtp_class=FakeSMTP) is True
    assert [to for to, _ in FakeSMTP.sent] == ["a@example.com", "b@example.com", "c@example.com"]


def test_recipients_from_env_and_settings(monkeypatch):
    monkeypatch.setenv("EMAIL_TO", "x@example.com, y@example.com;z@example.com")
    assert load_email_config(SETTINGS | {"email": {"to": ["old@example.com"]}})["recipients"] == \
        ["x@example.com", "y@example.com", "z@example.com"]
    monkeypatch.delenv("EMAIL_TO")
    assert parse_recipients(["one@example.com", " two@example.com "]) == ["one@example.com", "two@example.com"]


def test_digest_has_two_groups_and_escapes_html():
    high = Article(id="1", title="<script>x</script> & Co", link="https://e.com/?a=1&b=2", source_name="S",
                   category="Frontier AI Labs", source_priority=3, published_utc="2026-10-12T08:00:00+00:00",
                   first_seen_utc="2026-10-13T01:00:00+00:00", importance_score=80, importance_level="High",
                   impact_level="High", impact_source="ai", overview="One line.", explanation="Paragraph.")
    low = Article(id="2", title="Minor update", link="https://e.com/2", source_name="S", category="NVIDIA",
                  source_priority=3, published_utc="2026-10-12T08:00:00+00:00",
                  first_seen_utc="2026-10-13T01:00:00+00:00", impact_level="Low", overview="Small line.")
    stats = {"feeds_ok": 1, "feeds_failed": [], "new": 2, "duplicates": 0, "high": 1}
    subject, text, html = build_digest([high, low], stats, SETTINGS, NOW, "day", "ranked by importance score")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "===== High Impact (1) =====" in text
    assert "===== Medium & Low Impact (1) =====" in text
    assert subject.startswith("[T] Daily digest: 2 stories (1 high impact)")


def test_missing_secret_is_reported_not_silent(caplog):
    caplog.set_level("WARNING")
    assert send_email(BASE, "Daily digest", "t", "<p>h</p>") is False
    assert "not configured" in caplog.text