"""
What's On in Parliament — scraper for whatson.parliament.uk.

No reliable RSS/API URL has been found. Falls back to HTML scraping.
FRAGILITY NOTE: Medium — the page is SSR but layout may change.
"""

import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from .base import polite_get

BASE_URL = "https://whatson.parliament.uk"


def fetch(source_cfg: dict) -> list[dict]:
    url = source_cfg.get("url", BASE_URL)
    resp = polite_get(url)
    soup = BeautifulSoup(resp.text, "lxml")

    items = []

    # Try multiple selector strategies — the page layout may vary
    cards = (
        soup.select("article")
        or soup.select(".event-item, .event-card, li.event")
        or [li for li in soup.find_all("li") if li.find("a", href=True) and li.find("time")]
    )

    for card in cards:
        link_tag = card.find("a", href=True)
        if not link_tag:
            continue

        title = link_tag.get_text(strip=True)
        if not title or len(title) < 4:
            continue

        href = link_tag["href"]
        if not href.startswith("http"):
            href = BASE_URL + href

        published_at = _extract_date(card)
        summary_tag = card.find("p")
        summary = summary_tag.get_text(strip=True)[:500] if summary_tag else ""

        items.append({
            "item_id": href.split("?")[0].rstrip("/"),
            "title": title,
            "url": href,
            "published_at": published_at,
            "summary": summary,
            "matched_kws": [],
        })

    return items


def _extract_date(card) -> str | None:
    time_tag = card.find("time")
    if time_tag:
        dt_attr = time_tag.get("datetime", "")
        if dt_attr:
            try:
                return datetime.fromisoformat(dt_attr).replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass

    text = card.get_text(" ", strip=True)
    m = re.search(r"\b(\d{1,2}\s+\w+\s+\d{4})\b", text)
    if m:
        try:
            dt = datetime.strptime(m.group(1), "%d %B %Y")
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    return None
