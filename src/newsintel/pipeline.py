"""One collection run: fetch, process, dedupe, label impact with free AI, alert, digest, archive."""
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
from .impact import ai_configured, classify_articles, select_important
from .logging_setup import setup_logging
from .models import Article, to_utc_iso, utcnow
from .site import build_site
from .storage import load_db, mark_seen, prune, record_run, save_db, seen_set
from .text_utils import clean_html

log = logging.getLogger("newsintel")


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
    db_path = DATA_DIR / "articles.json"
    db = load_db(db_path)
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

    # 5. Free AI labels impact (High/Medium/Low) for new articles. Rule-based levels are the fallback.
    if ai_on and new:
        classify_articles(new, ai_cfg)

    # 6. Breaking alerts for new High-impact articles (capped; extras get one summary email).
    cfg = load_email_config(settings)
    high = sorted([a for a in new if a.impact_level == "High"], key=lambda a: -a.importance_score)
    limit = settings["max_alerts_per_run"]
    for art in high[:limit]:
        subj, text, html = build_alert(art, settings)
        if send_email(cfg, subj, text, html, dry_run=no_send):
            art.alerted = True
    overflow = high[limit:]
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

    # 8. Save: update articles, remember new ids, prune, record the run.
    db["articles"] = [a.to_dict() for a in all_articles]
    mark_seen(db, [a.id for a in new], now)
    removed = prune(db, now, settings["retention_days"])
    summary = {"run_utc": to_utc_iso(now), "ai": ai_on, "feeds_ok": len(feeds_ok),
               "feeds_failed": len(feeds_failed), "new": len(new), "duplicates": duplicates,
               "high": len(high), "digest": opts.period if opts.digest else None,
               "digest_sent": digest_sent, "pruned": removed}
    record_run(db, summary, now)

    if opts.dry_run:
        log.info("dry run: nothing was written")
    else:
        try:
            save_db(db_path, db)
            build_site(db["articles"], DOCS_DIR, to_utc_iso(now), settings)
        except OSError as exc:
            log.error("could not write storage: %s", exc)
            return 1

    log.info("run complete: %s", summary)
    return 0 if (feeds_ok or not feeds) else 1
