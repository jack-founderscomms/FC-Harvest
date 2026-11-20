"""
Parliamentary Committee news articles (press releases on committees.parliament.uk).

committees.parliament.uk has no news API and serves a Cloudflare challenge to
automated clients (including GitHub Actions), so neither the news pages nor any
site RSS can be fetched directly. Google News indexes these articles, so we query
its RSS search restricted to the committee's section of the site:

    site:committees.parliament.uk/committee/{id} when:{days}d

Google News also indexes the committee's listing pages ("... - Publications -
Committees - UK Parliament", "Written evidence", etc.); those are filtered out.

Links are Google News redirect URLs — they open the original committee article
in a browser.

RELIABILITY: Medium. Depends on Google News indexing; articles usually appear
within hours of publication.

Can be used standalone (type: parliament_committee_news, with committee_id) but is
normally called from parliament_committees_api as the "news" part of a committee source.
"""

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

from .base import polite_get

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"

_SUFFIX = re.compile(r"\s+-\s+UK Parliament\s*$")
# Listing / navigation pages, e.g. "X Committee - Correspondence - Committees"
_LISTING = re.compile(r"\s-\s.*\b(Committees?|Sub-Committee)\s*$")
_GENERIC_TITLES = {
    "written evidence", "oral evidence", "faqs", "all former committee members",
    "publications", "news", "events", "membership", "role", "contact us",
}


def fetch(source_cfg: dict) -> list[dict]:
    if not source_cfg.get("committee_id"):
        raise ValueError("parliament_committee_news needs committee_id")
    return fetch_for_committee(int(source_cfg["committee_id"]), days=int(source_cfg.get("news_days", 30)))


def fetch_for_committee(committee_id: int, days: int = 30) -> list[dict]:
    query = f"site:committees.parliament.uk/committee/{committee_id} when:{days}d"
    resp = polite_get(
        GOOGLE_NEWS_RSS,
        params={"q": query, "hl": "en-GB", "gl": "GB", "ceid": "GB:en"},
    )
    return parse_feed(resp.content)


def parse_feed(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    items = []
    seen_titles = set()
    for it in root.iter("item"):
        raw_title = (it.findtext("title") or "").strip()
        title = _SUFFIX.sub("", raw_title).strip()
        if not title or _is_listing(title) or title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())

        link = (it.findtext("link") or "").strip()
        guid = (it.findtext("guid") or link).strip()
        items.append({
            "item_id": f"news_{guid}",
            "title": title,
            "url": link,
            "published_at": _parse_date(it.findtext("pubDate")),
            "summary": "Committee news",
            "matched_kws": [],
        })
    return items


def _is_listing(title: str) -> bool:
    return title.lower() in _GENERIC_TITLES or bool(_LISTING.search(title))


def _parse_date(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None
