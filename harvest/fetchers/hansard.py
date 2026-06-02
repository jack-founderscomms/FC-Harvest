"""
Hansard API fetcher.
Base URL: https://hansard.parliament.uk/api/

Undocumented but publicly used by the Hansard website itself.
Fetches previous day's debate titles.

RELIABILITY: Not formally documented — may change. Medium brittleness.
We fetch the sittings index for a given date/house.
"""

from datetime import date, timedelta, timezone, datetime
from .base import polite_get

API_BASE = "https://hansard.parliament.uk/api"


def fetch(source_cfg: dict) -> list[dict]:
    house = source_cfg.get("house", "Commons")
    # Yesterday's debates (the most recently complete day)
    target_date = (date.today() - timedelta(days=1)).isoformat()

    url = f"{API_BASE}/sittings/{house}/{target_date}"
    try:
        resp = polite_get(url, accept_json=True)
        data = resp.json()
    except Exception:
        # Try the 'overview' endpoint as fallback
        url = f"{API_BASE}/overview/{house}"
        resp = polite_get(url, accept_json=True)
        data = resp.json()

    items = []
    sittings = data if isinstance(data, list) else data.get("sittings", [data] if data else [])

    for sitting in sittings:
        sitting_date = sitting.get("date", target_date)
        sections = sitting.get("sections", sitting.get("debates", []))
        for section in sections:
            title = (section.get("title") or section.get("Title") or "").strip()
            section_id = section.get("id") or section.get("externalId") or ""
            if not title:
                continue
            url_path = _build_url(house, sitting_date, section_id)
            item = {
                "item_id": f"hansard_{house}_{sitting_date}_{section_id}",
                "title": title,
                "url": url_path,
                "published_at": _date_to_iso(sitting_date),
                "summary": section.get("summary") or "",
                "matched_kws": [],
            }
            items.append(item)
    return items


def _build_url(house: str, sitting_date: str, section_id: str) -> str:
    house_path = "commons" if house.lower() == "commons" else "lords"
    if section_id:
        return f"https://hansard.parliament.uk/{house_path}/{sitting_date}/debates/{section_id}"
    return f"https://hansard.parliament.uk/{house_path}/{sitting_date}"


def _date_to_iso(d: str) -> str:
    try:
        return datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return d
