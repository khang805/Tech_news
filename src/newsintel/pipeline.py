"""One collection run: fetch, process, dedupe, label impact with free AI, alert, digest, save."""
import json
import logging
from datetime import timedelta
from pathlib import Path

from .article_page import PageFetcher
from .config import DATA_DIR, DOCS_DIR, LOG_FILE, load_feeds, load_settings
from .dedupe import dedupe_batch
from .digest import PERIODS, build_alert, build_digest, build_overflow, period_pool
from .emailer import load_email_config, send_email
from .fetcher import fetch_feed
from .formatter import build_article
from .http_client import FetchError, make_session
from .enrich import enrich_articles
from .impact import ai_configured, select_important
from .logging_setup import setup_logging
from .models import Article, to_utc_iso, utcnow
from .site import build_site
from .storage import SEEN_RETENTION_DAYS, load_db, mark_seen, seen_set
from .store import StoreError, get_store
from .text_utils import clean_html

log = logging.getLogger("newsintel")
LEGACY_FILE = DATA_DIR / "articles.json"


def run(opts) -> int:
    setup_logging(LOG_FILE, opts.verbose)
    settings = load_settings()
    ai_cfg = settings["ai"]
    feeds = load_feeds()
    if opts.feed:
        feeds = [f for f in feeds if f["name"] == opts.feed]
        if not feeds:
            log.error("no enabled feed named %r in config/feeds.yaml", opts.feed)
            return 1

    ai_on = bool(ai_cfg.get("enabled", True)) and not opts.no_ai and ai_configured()
    if not ai_on:
        log.info("AI off (no GEMINI_API_KEY/GROQ_API_KEY, or --no-ai): using rule-based impact levels")

    now = utcnow()
    no_send = opts.dry_run or opts.no_email
    cfg = load_email_config(settings)
    log.info("email setup: SMTP_USERNAME %s, SMTP_PASSWORD %s, recipients %d",
             "set" if cfg["username"] else "MISSING", "set" if cfg["password"] else "MISSING",
             len(cfg["recipients"]))
    if opts.test_email:
        text = "This is a test from News Intel. If you can read this, email is working."
        ok = send_email(cfg, f"{settings['email']['subject_prefix']} test email", text, f"<p>{text}</p>",
                        dry_run=opts.dry_run)
        log.info("test email %s", "sent" if ok else "NOT sent (see messages above)")
        return 0 if ok else 1

    # Load stored data (Supabase in GitHub Actions, local JSON otherwise).
    try:
        store = get_store()
        articles_in = store.load_articles()
        seen_in = store.load_seen()
    except (StoreError, OSError) as exc:
        log.error("could not read storage: %s", exc)
        return 1

    # One-time migration: the first Supabase run imports the old data/articles.json, if it exists.
    migrated = False
    if store.kind == "supabase" and not articles_in and LEGACY_FILE.exists():
        legacy = load_db(LEGACY_FILE)
        articles_in, seen_in = legacy["articles"], legacy["seen_ids"]
        migrated = True
        log.info("migrating %d articles from %s into %s", len(articles_in), LEGACY_FILE.name, store.kind)

    # After migration every article counts as changed, so all of them are written to the database.
    snapshot = {} if migrated else {a["id"]: json.dumps(a, sort_keys=True) for a in articles_in}
    db = {"articles": list(articles_in), "seen_ids": list(seen_in)}
    session = make_session(settings)
    fixture_bytes = Path(opts.fixture).read_bytes() if opts.fixture else None

    # 1. Fetch every enabled feed. One failing feed never stops the run.
    feeds_ok, feeds_failed, raw_items = [], [], []
    for feed in feeds:
        try:
            items = fetch_feed(feed, session, settings, now, content=fixture_bytes)
        except FetchError as exc:
            feeds_failed.append((feed["name"], exc.kind))
            log.warning("feed failed, skipping: %s (%s)", feed["name"], exc)
            continue
        except Exception as exc:
            feeds_failed.append((feed["name"], type(exc).__name__))
            log.exception("unexpected error in feed %s, skipping", feed["name"])
            continue
        feeds_ok.append(feed["name"])
        raw_items.extend(items)
        log.info("feed ok: %s (%d items)", feed["name"], len(items))
    log.info("feeds: %d ok, %d failed", len(feeds_ok), len(feeds_failed))

    # 2. Ignore items older than the fetch window (unless testing with --ignore-age).
    if not opts.ignore_age:
        max_age = now - timedelta(days=settings["max_article_age_days"])
        raw_items = [i for i in raw_items if i.published >= max_age]

    # 3. Build articles. Full-page text is used only when it is longer than the feed text.
    pages = PageFetcher(session, settings)
    candidates = []
    for item in raw_items:
        text = clean_html(item.summary_html)
        if item.feed.get("fetch_full_text") and item.link:
            page_text = pages.fetch_text(item.link)
            if len(page_text) > len(text):
                text = page_text
        candidates.append(build_article(item, settings, now, text))

    # 4. Remove duplicates against stored articles and within this batch.
    stored = [Article.from_dict(d) for d in db["articles"]]
    new, duplicates = dedupe_batch(
        candidates, stored, seen_set(db), now,
        threshold=settings["title_similarity_threshold"],
        window_days=settings["dedupe_window_days"],
    )
    log.info("new articles: %d, duplicates removed: %d", len(new), duplicates)
    all_articles = stored + new

    # 5. Gemini labels impact and writes one line + one paragraph per new story. Source text is the fallback.
    if ai_on and new:
        enrich_articles(new, ai_cfg)

    # 6. Breaking alerts for new High-impact articles (off by default).
    high = sorted([a for a in new if a.impact_level == "High"], key=lambda a: -a.importance_score)
    alerts_on = bool(settings.get("breaking_alerts", False))
    limit = settings["max_alerts_per_run"] if alerts_on else 0
    for art in (high[:limit] if alerts_on else []):
        subj, text, html = build_alert(art, settings)
        if send_email(cfg, subj, text, html, dry_run=no_send):
            art.alerted = True
    overflow = high[limit:] if alerts_on else []
    if overflow:
        subj, text, html = build_overflow(len(overflow), settings)
        send_email(cfg, subj, text, html, dry_run=no_send)
        for art in overflow:
            art.alerted = True

    # 7. Digest: day = newest important unsent stories; week/month = AI picks the important ones.
    digest_sent = False
    if opts.digest:
        period = opts.period
        pool = period_pool(all_articles, now, period)
        n = settings["period_top_n"][period]
        if period == "day":
            selected = sorted(pool, key=lambda a: -a.importance_score)[:n]
            note = "ranked by importance score"
        else:
            selected, method = select_important(pool, n, PERIODS[period][0].lower(), ai_cfg,
                                                fallback_only=not ai_on)
            note = "chosen by free AI model" if method == "AI" else "ranked by importance score"
        stats = {"feeds_ok": len(feeds_ok), "feeds_failed": feeds_failed, "new": len(new),
                 "duplicates": duplicates, "high": len(high)}
        subj, text, html = build_digest(selected, stats, settings, now, period, note)
        digest_sent = send_email(cfg, subj, text, html, dry_run=no_send)
        if digest_sent and period == "day":
            for art in selected:
                art.digested = True

    # 8. Save. Only new or changed articles are written, which keeps database traffic small.
    db["articles"] = [a.to_dict() for a in all_articles]
    mark_seen(db, [a.id for a in new], now)
    changed = [a for a in db["articles"] if snapshot.get(a["id"]) != json.dumps(a, sort_keys=True)]
    seen_to_write = [s["id"] for s in db["seen_ids"]] if migrated else [a.id for a in new]
    article_cutoff = now - timedelta(days=settings["retention_days"])
    seen_cutoff = now - timedelta(days=SEEN_RETENTION_DAYS)

    summary = {"run_utc": to_utc_iso(now), "storage": store.kind, "ai": ai_on, "feeds_ok": len(feeds_ok),
               "feeds_failed": len(feeds_failed), "new": len(new), "duplicates": duplicates,
               "high": len(high), "changed": len(changed), "digest": opts.period if opts.digest else None,
               "digest_sent": digest_sent}

    if opts.dry_run:
        log.info("dry run: nothing was written")
    else:
        try:
            pruned = store.persist(changed, seen_to_write, now, article_cutoff, seen_cutoff,
                                   last_run_iso=to_utc_iso(now))
            summary["pruned"] = pruned
            build_site(DOCS_DIR, settings)
        except (StoreError, OSError) as exc:
            log.error("could not save data: %s", exc)
            return 1

    log.info("run complete: %s", summary)
    if opts.digest and not no_send and not digest_sent:
        log.error("DIGEST EMAIL WAS NOT SENT. Read the email lines above: missing secrets or an SMTP error.")
        return 1
    return 0 if (feeds_ok or not feeds) else 1
