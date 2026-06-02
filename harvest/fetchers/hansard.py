"""
Hansard fetcher — recent debates from the official Hansard API.
Docs/Swagger: https://hansard-api.parliament.uk/swagger/docs/v1
Base URL: https://hansard-api.parliament.uk

No auth required. Returns JSON. Official, stable. Open Parliament Licence v3.0.

We fetch recent debate sittings for a given house, then list section titles.
"""

import re
from datetime import date, timedelta, timezone, datetime
from .base import polite_get

API_BASE = "https://hansard-api.parliament.uk"


def fetch(source_cfg: dict) -> list[dict]:
    house = source_cfg.get("house", "Commons")

    # Fetch recent sittings (last 7 days)
    since = (date.today() - timedelta(days=7)).isoformat()
    today = date.today().isoformat()

    sittings_url = f"{API_BASE}/overview/{house.lower()}/sittings.json"
    params = {"startDate": since, "endDate": today}

    try:
        resp = polite_get(sittings_url, params=params, accept_json=True)
        data = resp.json()
    except Exception:
        # Try alternate endpoint structure
        return _fetch_via_search(house)

    items = []
    sittings = data if isinstance(data, list) else data.get("sittings", [])

    for sitting in sittings:
        sitting_date = (sitting.get("date") or sitting.get("SittingDate") or "")[:10]
        sections = sitting.get("sections", sitting.get("debateSections", []))

        for section in sections:
            title = (section.get("title") or section.get("Title") or "").strip()
            if not title or len(title) < 4:
                continue

            section_id = section.get("id") or section.get("externalId") or ""
            url = _build_url(house.lower(), sitting_date, section_id)

            items.append({
                "item_id": f"hansard_{house}_{sitting_date}_{section_id or title[:30]}",
                "title": title,
                "url": url,
                "published_at": _date_to_iso(sitting_date),
                "summary": (section.get("summary") or ""),
                "matched_kws": [],
            })

    return items if items else _fetch_via_search(house)


def _fetch_via_search(house: str) -> list[dict]:
    """Fallback: use the search endpoint."""
    since = (date.today() - timedelta(days=7)).isoformat()
    url = f"{API_BASE}/search/debates.json"
    params = {
        "house": house,
        "startDate": since,
        "take": 50,
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
        sitting_date = (r.get("sittingDate") or r.get("date") or "")[:10]
        section_id = r.get("id") or r.get("externalId") or ""
        items.append({
            "item_id": f"hansard_{house}_{sitting_date}_{section_id}",
            "title": title,
            "url": _build_url(house.lower(), sitting_date, section_id),
            "published_at": _date_to_iso(sitting_date),
            "summary": (r.get("summary") or ""),
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
        return datetime.strptime(d[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc).isoformat()
    except ValueError:
        return d
