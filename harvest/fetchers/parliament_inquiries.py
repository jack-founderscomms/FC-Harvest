"""
Committee Inquiries — HTML scrape of committees.parliament.uk/inquiries/

FRAGILITY NOTE: This is an HTML scrape — no official API exists for this page.
The page uses server-rendered HTML. Structure may change after Parliament website
redesigns. Mark as 'scrape' in monitoring.

We use requests + BeautifulSoup. No JavaScript rendering needed (content is SSR).
"""

from bs4 import BeautifulSoup
from datetime import datetime, timezone
from .base import polite_get


def fetch(source_cfg: dict) -> list[dict]:
    url = source_cfg.get("url", "https://committees.parliament.uk/inquiries/")
    resp = polite_get(url)
    soup = BeautifulSoup(resp.text, "lxml")

    items = []

    # The inquiries page lists inquiry cards. Each card has a heading link and metadata.
    # Selector targets the inquiry list items — adjust if site structure changes.
    cards = soup.select("li.list-item, article.inquiry-card, div.inquiry-item, .results-list li")
    if not cards:
        # Broader fallback: any <li> or <article> containing an <a> with /inquiries/ in href
        cards = [
            tag for tag in soup.find_all(["li", "article"])
            if tag.find("a", href=lambda h: h and "/inquiries/" in h)
        ]

    for card in cards:
        link_tag = card.find("a", href=True)
        if not link_tag:
            continue

        href = link_tag["href"]
        if not href.startswith("http"):
            href = "https://committees.parliament.uk" + href

        title = link_tag.get_text(strip=True)
        if not title or "/inquiries/" not in href:
            continue

        # Try to extract a date from card text
        published_at = _extract_date(card)

        # Stable ID: the URL path
        item_id = href.split("?")[0].rstrip("/")

        # Summary: any paragraph text in card
        summary_tag = card.find("p")
        summary = summary_tag.get_text(strip=True)[:500] if summary_tag else ""

        items.append({
            "item_id": item_id,
            "title": title,
            "url": href,
            "published_at": published_at,
            "summary": summary,
            "matched_kws": [],
        })

    return items


def _extract_date(card) -> str | None:
    """Look for a date string in the card's text."""
    import re
    text = card.get_text(" ", strip=True)
    # Match patterns like "12 June 2025" or "2025-06-12"
    m = re.search(r"\b(\d{1,2}\s+\w+\s+\d{4})\b", text)
    if m:
        try:
            dt = datetime.strptime(m.group(1), "%d %B %Y")
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    m2 = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if m2:
        try:
            dt = datetime.strptime(m2.group(1), "%Y-%m-%d")
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    return None
