"""The Article record and small UTC time helpers."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone


@dataclass
class Article:
    id: str
    title: str
    link: str
    source_name: str
    category: str
    source_priority: int
    published_utc: str
    first_seen_utc: str
    importance_score: int = 0
    importance_level: str = "Low"          # rule-based level (0-100 score thresholds)
    importance_reasons: list[str] = field(default_factory=list)
    impact_level: str = "Low"              # final impact: High / Medium / Low (AI-rated when available)
    impact_source: str = "rules"           # "ai" or "rules"
    overview: str = ""
    explanation: str = ""
    relevance: str = ""
    content_status: str = "insufficient"
    date_is_estimated: bool = False
    alerted: bool = False
    digested: bool = False
    also_reported_by: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Article":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in names})


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_utc_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_utc(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
