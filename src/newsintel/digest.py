"""Digest and alert emails. Two groups: High Impact, and Medium & Low Impact. Each story = one line + one paragraph."""
import html as h
from datetime import timedelta
from zoneinfo import ZoneInfo

from .models import Article, parse_utc

PERIODS = {"day": ("Daily", 1), "week": ("Weekly", 7), "month": ("Monthly", 30)}
HIGH_GROUP = "High Impact"
OTHER_GROUP = "Medium & Low Impact"


def period_pool(articles: list[Article], now, period: str) -> list[Article]:
    """Day digests use stories not yet sent. Week and month digests look at everything in the window."""
    _, days = PERIODS[period]
    cutoff = now - timedelta(days=days)
    recent = [a for a in articles if parse_utc(a.published_utc) >= cutoff]
    if period == "day":
        return [a for a in recent if not a.digested]
    return recent


def group_of(a: Article) -> str:
    return HIGH_GROUP if a.impact_level == "High" else OTHER_GROUP


def _local(iso: str, tz_name: str) -> str:
    return parse_utc(iso).astimezone(ZoneInfo(tz_name)).strftime("%d %b %Y, %H:%M %Z")


def _meta(a: Article, tz: str) -> str:
    est = " (date estimated)" if a.date_is_estimated else ""
    label = "AI" if a.impact_source == "ai" else "rules"
    return (f"{a.category} | {a.source_name} | {_local(a.published_utc, tz)}{est} | "
            f"Impact: {a.impact_level} (by {label})")


def _story_text(n: int, a: Article, tz: str) -> str:
    lines = [f"{n}. {a.title}", "   " + _meta(a, tz), "", "   " + a.overview]
    if a.explanation:
        lines += ["", "   " + a.explanation]
    lines += ["", "   Read more: " + a.link]
    return "\n".join(lines)


def _story_html(n: int, a: Article, tz: str) -> str:
    body = f"<p style='margin:0 0 8px;font-weight:bold'>{h.escape(a.overview)}</p>"
    if a.explanation:
        body += f"<p style='margin:0 0 8px'>{h.escape(a.explanation)}</p>"
    return (
        '<div style="margin:0 0 18px;padding:14px;border:1px solid #e3e6eb;border-radius:8px">'
        f'<h3 style="margin:0 0 4px;font-size:17px">{n}. {h.escape(a.title)}</h3>'
        f'<div style="font-size:12px;color:#666;margin-bottom:8px">{h.escape(_meta(a, tz))}</div>'
        f"{body}"
        f'<a href="{h.escape(a.link, quote=True)}">Read more</a>'
        "</div>"
    )


def _wrap(body: str) -> str:
    return ('<html><body style="font-family:Arial,sans-serif;max-width:720px;margin:auto;color:#1d1d1f">'
            f"{body}</body></html>")


def build_digest(selected: list[Article], stats: dict, settings: dict, now, period: str, note: str):
    tz = settings["timezone_display"]
    prefix = settings["email"]["subject_prefix"]
    label, days = PERIODS[period]
    day = now.astimezone(ZoneInfo(tz)).strftime("%d %b %Y")
    status = (f"New this run: {stats['new']} | High impact (new): {stats['high']} | "
              f"Feeds OK: {stats['feeds_ok']} | Feeds failed: {len(stats['feeds_failed'])}")
    if not selected:
        subject = f"{prefix} {label} digest: no new stories - {day}"
        msg = f"No stories were found for the last {days} day(s).\n{status}"
        return subject, msg + "\n", _wrap("<p>" + h.escape(msg).replace("\n", "<br>") + "</p>")

    high_n = sum(1 for a in selected if group_of(a) == HIGH_GROUP)
    subject = f"{prefix} {label} digest: {len(selected)} stories ({high_n} high impact) - {day}"
    title = f"{label} tech intelligence - {day}"
    groups = {HIGH_GROUP: [], OTHER_GROUP: []}
    for a in selected:
        groups[group_of(a)].append(a)

    text_parts = [title, status, f"Selection: {note}", ""]
    html_parts = [f"<h2>{h.escape(title)}</h2>",
                  f"<p style='font-size:13px;color:#555'>{h.escape(status)}<br>Selection: {h.escape(note)}</p>"]
    n = 0
    for name in (HIGH_GROUP, OTHER_GROUP):
        items = groups[name]
        if not items:
            continue
        text_parts += [f"===== {name} ({len(items)}) =====", ""]
        html_parts.append(f"<h2 style='font-size:18px;border-bottom:2px solid #1d2b44'>{h.escape(name)} ({len(items)})</h2>")
        for a in items:
            n += 1
            text_parts += [_story_text(n, a, tz), ""]
            html_parts.append(_story_html(n, a, tz))
    if stats["feeds_failed"]:
        failed = ", ".join(f"{name} ({kind})" for name, kind in stats["feeds_failed"])
        text_parts.append(f"Feeds that failed: {failed}")
        html_parts.append(f"<p style='font-size:12px;color:#a00'>Feeds that failed: {h.escape(failed)}</p>")
    return subject, "\n".join(text_parts), _wrap("".join(html_parts))


def build_alert(a: Article, settings: dict):
    tz = settings["timezone_display"]
    prefix = settings["email"]["subject_prefix"]
    subject = f"{prefix} HIGH IMPACT: {a.title}"
    text = "HIGH IMPACT ALERT\n\n" + _story_text(1, a, tz)
    return subject, text, _wrap(_story_html(1, a, tz))


def build_overflow(count: int, settings: dict):
    prefix = settings["email"]["subject_prefix"]
    msg = (f"{count} more high-impact stories were found in this run. They are on the website "
           "and will appear in the next digest.")
    return f"{prefix} {count} more high-impact stories", msg, _wrap(f"<p>{h.escape(msg)}</p>")
