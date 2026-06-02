"""
Hansard fetcher — recent debates from hansard.parliament.uk.

The Hansard website exposes an internal search API used by its own frontend.
We use the /api/writtenAnswers/search and /api/debates/search endpoints.

RELIABILITY: These are undocumented internal APIs. Medium brittleness — they work
but may change without notice. We try the search endpoint first, then fall back
to the RSS feed at hansard.parliament.uk/rss/{house}/debates.rss.

API base: https://hansard.parliament.uk/api
RSS fallback: https://hansard.parliament.uk/rss/{house}/debates.rss
"""

import re
import feedparser
from datetime import date, timedelta, timezone, datetime
from .base import polite_get

API_BASE = "https://hansard.parliament.uk/api"


def fetch(source_cfg: dict) -> list[dict]:
    house = source_cfg.get("house", "Commons")
    house_lower = house.lower()

    # Try 1: search API for recent debates
    items = _fetch_via_search_api(house, house_lower)
    if items:
        return items

    # Try 2: RSS feed
    items = _fetch_via_rss(house_lower)
    if items:
        return items

    # Try 3: debates listing page scrape
    return _fetch_via_scrape(house_lower)


def _fetch_via_search_api(house: str, house_lower: str) -> list[dict]:
    since = (date.today() - timedelta(days=7)).isoformat()
    url = f"{API_BASE}/debates/search"
    params = {
        "house": house,
        "startDate": since,
        "take": 50,
        "skip": 0,
        "orderBy": "SittingDateDesc",
    }
    try:
        resp = polite_get(url, params=params, accept_json=True)
        data = resp.json()
    except Exception:
        return []

    results = data if isinstance(data, list) else data.get("results", data.get("searchResults", []))
    items = []
    for r in results:
        title = (r.get("title") or r.get("debateTitle") or "").strip()
        if not title:
            continue
        section_id = r.get("id") or r.get("externalId") or ""
        sitting_date = (r.get("sittingDate") or r.get("date") or "")[:10]
        items.append({
            "item_id": f"hansard_{house}_{sitting_date}_{section_id}",
            "title": title,
            "url": _build_url(house_lower, sitting_date, section_id),
            "published_at": _date_to_iso(sitting_date),
            "summary": (r.get("summary") or ""),
            "matched_kws": [],
        })
    return items


def _fetch_via_rss(house_lower: str) -> list[dict]:
    # Try several known RSS URL patterns
    rss_candidates = [
        f"https://hansard.parliament.uk/rss/{house_lower}/debates.rss",
        f"https://hansard.parliament.uk/{house_lower}/debates.rss",
        f"https://hansard.parliament.uk/rss/debates/{house_lower}.rss",
    ]
    for url in rss_candidates:
        try:
            resp = polite_get(url)
            if resp.status_code != 200:
                continue
            feed = feedparser.parse(resp.text)
            if not feed.entries:
                continue
            items = []
            for entry in feed.entries:
                item_id = entry.get("id") or entry.get("link", "")
                items.append({
                    "item_id": item_id,
                    "title": entry.get("title", "").strip(),
                    "url": entry.get("link", ""),
                    "published_at": _parse_feed_date(entry),
                    "summary": _get_summary(entry),
                    "matched_kws": [],
                })
            return [i for i in items if i["title"]]
        except Exception:
            continue
    return []


def _fetch_via_scrape(house_lower: str) -> list[dict]:
    from bs4 import BeautifulSoup
    url = f"https://hansard.parliament.uk/{house_lower}"
    try:
        resp = polite_get(url)
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    items = []
    for a in soup.select("a[href*='/debates/']")[:50]:
        href = a["href"]
        title = a.get_text(strip=True)
        if not title or len(title) < 5:
            continue
        full_url = f"https://hansard.parliament.uk{href}" if href.startswith("/") else href
        items.append({
            "item_id": href,
            "title": title,
            "url": full_url,
            "published_at": None,
            "summary": "",
            "matched_kws": [],
        })
    return items


def _build_url(house_lower: str, sitting_date: str, section_id: str) -> str:
    if section_id:
        return f"https://hansard.parliament.uk/{house_lower}/{sitting_date}/debates/{section_id}"
    return f"https://hansard.parliament.uk/{house_lower}/{sitting_date}"


def _date_to_iso(d: str) -> str | None:
    if not d:
        return None
    try:
        return datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return d


def _parse_feed_date(entry) -> str | None:
    from email.utils import parsedate_to_datetime
    for field in ("published", "updated"):
        raw = entry.get(field)
        if raw:
            try:
                return parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
            except Exception:
                pass
    return None


def _get_summary(entry) -> str:
    for field in ("summary", "content"):
        val = entry.get(field)
        if isinstance(val, list) and val:
            val = val[0].get("value", "")
        if val:
            return re.sub(r"<[^>]+>", " ", str(val)).strip()[:500]
    return ""
