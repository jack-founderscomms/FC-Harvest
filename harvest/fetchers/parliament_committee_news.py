"""
Parliamentary Committee news fetcher.

After the 2024 general election all committees were reconstituted with new IDs,
so hardcoded RSS URLs break. This fetcher dynamically discovers the committee ID
by scraping the committees listing page, then fetches the RSS feed for that committee.

Discovery is cached in-process so it only runs once per harvest.

RELIABILITY: Medium. Discovery depends on the committee listing page structure.
RSS feeds themselves are official once the ID is found.
"""

import re
import feedparser
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from .base import polite_get

COMMITTEES_BASE = "https://committees.parliament.uk"

# Cache: (search_name, house) → committee_id
_id_cache: dict[tuple[str, str], str | None] = {}


def fetch(source_cfg: dict) -> list[dict]:
    search_name = source_cfg["search_name"]
    house = source_cfg.get("house", "Commons")

    committee_id = _discover_committee_id(search_name, house)
    if not committee_id:
        raise ValueError(
            f"Could not find committee ID for '{search_name}' ({house}). "
            "Check committees.parliament.uk for the current committee name/URL."
        )

    rss_url = f"{COMMITTEES_BASE}/committee/{committee_id}/news/rss/"
    resp = polite_get(rss_url)

    if resp.status_code == 404:
        # Some committees use a slightly different RSS path
        rss_url = f"{COMMITTEES_BASE}/committee/{committee_id}/rss/"
        resp = polite_get(rss_url)

    feed = feedparser.parse(resp.text)
    items = []
    for entry in feed.entries:
        item_id = entry.get("id") or entry.get("link", "")
        published_at = _parse_date(entry)
        summary = _get_summary(entry)
        item = {
            "item_id": item_id,
            "title": entry.get("title", "").strip(),
            "url": entry.get("link", ""),
            "published_at": published_at,
            "summary": summary,
            "matched_kws": [],
        }
        if item["title"] and item["item_id"]:
            items.append(item)
    return items


def _discover_committee_id(search_name: str, house: str) -> str | None:
    cache_key = (search_name.lower(), house.lower())
    if cache_key in _id_cache:
        return _id_cache[cache_key]

    # Fetch the committees listing page
    url = f"{COMMITTEES_BASE}/committees/all/"
    try:
        resp = polite_get(url)
    except Exception:
        _id_cache[cache_key] = None
        return None

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(resp.text, "lxml")

    # Look for links like /committee/123/some-committee-name
    pattern = re.compile(r"/committee/(\d+)/[^/\"']+")
    name_lower = search_name.lower()

    found_id = None
    for a in soup.find_all("a", href=pattern):
        href = a["href"]
        link_text = a.get_text(strip=True).lower()
        # Match by search name and optionally by house
        if name_lower in link_text or name_lower in href.lower():
            # Check house context if possible
            parent_text = (a.parent.get_text(" ", strip=True) if a.parent else "").lower()
            if house.lower() == "lords" and "lords" not in parent_text and "lords" not in href.lower():
                continue
            if house.lower() == "commons" and "lords" in parent_text:
                continue
            m = pattern.search(href)
            if m:
                found_id = m.group(1)
                break

    _id_cache[cache_key] = found_id
    return found_id


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
            return re.sub(r"<[^>]+>", " ", str(val)).strip()[:500]
    return ""
