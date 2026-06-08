"""
Parliament RSS feed fetcher.
Used for: committee news, What's On in Parliament.
feedparser handles Atom and RSS 2.0 transparently.

RELIABILITY: RSS feeds are official but occasionally go stale or return 404
when committees are restructured. Flag if status != 200.
"""

try:
    import feedparser
except ImportError:
    feedparser = None  # type: ignore
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from .base import polite_get


def fetch(source_cfg: dict) -> list[dict]:
    if feedparser is None:
        raise ImportError("feedparser is not available (requires sgmllib, removed in Python 3.11)")
    url = source_cfg["url"]
    resp = polite_get(url)
    feed = feedparser.parse(resp.text)

    items = []
    for entry in feed.entries:
        item_id = entry.get("id") or entry.get("link", "")
        published_at = _parse_date(entry)
        item = {
            "item_id": item_id,
            "title": entry.get("title", "").strip(),
            "url": entry.get("link", ""),
            "published_at": published_at,
            "summary": _get_summary(entry),
            "matched_kws": [],
        }
        if item["title"] and item["item_id"]:
            items.append(item)
    return items


def _parse_date(entry) -> str | None:
    for field in ("published", "updated"):
        raw = entry.get(field)
        if raw:
            try:
                return parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
            except Exception:
                pass
        parsed = entry.get(f"{field}_parsed")
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc).isoformat()
            except Exception:
                pass
    return None


def _get_summary(entry) -> str:
    for field in ("summary", "content"):
        val = entry.get(field)
        if isinstance(val, list) and val:
            val = val[0].get("value", "")
        if val:
            # Strip any HTML tags
            import re
            return re.sub(r"<[^>]+>", " ", str(val)).strip()[:500]
    return ""
