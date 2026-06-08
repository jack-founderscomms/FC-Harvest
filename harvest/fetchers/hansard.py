"""
Hansard fetcher — recent debates from two official Hansard APIs.

Primary:   https://hansard-api.parliament.uk  (Swagger: /swagger/docs/v1)
Secondary: https://api.parliament.uk/historic-hansard  (Swagger: /api)

No auth required. Returns JSON. Official, stable. Open Parliament Licence v3.0.

Fetch order:
  1. hansard-api sittings endpoint (newest, most structured)
  2. api.parliament.uk sittings search (broader coverage)
  3. hansard-api search/debates fallback
  4. api.parliament.uk contributions search (last resort)
"""

from datetime import date, timedelta, timezone, datetime
from .base import polite_get

API_BASE = "https://hansard-api.parliament.uk"
HIST_API_BASE = "https://api.parliament.uk/historic-hansard"


def fetch(source_cfg: dict) -> list[dict]:
    house = source_cfg.get("house", "Commons")
    since = (date.today() - timedelta(days=7)).isoformat()
    today = date.today().isoformat()

    items = _fetch_sittings(house, since, today)
    if items:
        return items

    items = _fetch_hist_sittings(house, since, today)
    if items:
        return items

    items = _fetch_via_search(house, since)
    if items:
        return items

    return _fetch_hist_contributions(house, since, today)


def _fetch_sittings(house: str, since: str, today: str) -> list[dict]:
    url = f"{API_BASE}/overview/{house.lower()}/sittings.json"
    try:
        resp = polite_get(url, params={"startDate": since, "endDate": today}, accept_json=True)
        data = resp.json()
    except Exception:
        return []

    sittings = data if isinstance(data, list) else data.get("sittings", [])
    items = []
    for sitting in sittings:
        sitting_date = (sitting.get("date") or sitting.get("SittingDate") or "")[:10]
        for section in (sitting.get("sections") or sitting.get("debateSections") or []):
            title = (section.get("title") or section.get("Title") or "").strip()
            if not title or len(title) < 4:
                continue
            section_id = section.get("id") or section.get("externalId") or ""
            items.append(_make_item(house, sitting_date, section_id, title,
                                    section.get("summary") or ""))
    return items


def _fetch_hist_sittings(house: str, since: str, today: str) -> list[dict]:
    """api.parliament.uk/historic-hansard sittings search."""
    url = f"{HIST_API_BASE}/sittings/search.json"
    try:
        resp = polite_get(url, params={
            "start_date": since, "end_date": today, "house": house.lower()
        }, accept_json=True)
        data = resp.json()
    except Exception:
        return []

    sittings = data if isinstance(data, list) else data.get("sittings", data.get("results", []))
    items = []
    for sitting in sittings:
        sitting_date = (sitting.get("date") or sitting.get("sitting_date") or "")[:10]
        sections = sitting.get("sections") or sitting.get("debates") or sitting.get("contributions") or []
        if sections:
            for sec in sections:
                title = (sec.get("title") or sec.get("heading") or sec.get("slug") or "").replace("-", " ").strip()
                if not title or len(title) < 4:
                    continue
                items.append(_make_item(house, sitting_date,
                                        sec.get("id") or sec.get("slug") or "", title,
                                        sec.get("summary") or sec.get("extract") or ""))
        else:
            title = (sitting.get("title") or sitting.get("heading") or "").strip()
            if title and len(title) >= 4:
                items.append(_make_item(house, sitting_date,
                                        sitting.get("id") or sitting.get("slug") or "", title, ""))
    return items


def _fetch_via_search(house: str, since: str) -> list[dict]:
    """Fallback: hansard-api search/debates endpoint."""
    url = f"{API_BASE}/search/debates.json"
    try:
        resp = polite_get(url, params={
            "house": house, "startDate": since, "take": 50, "orderBy": "SittingDateDesc"
        }, accept_json=True)
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
        items.append(_make_item(house, sitting_date, section_id, title, r.get("summary") or ""))
    return items


def _fetch_hist_contributions(house: str, since: str, today: str) -> list[dict]:
    """Last resort: api.parliament.uk/historic-hansard contributions search."""
    url = f"{HIST_API_BASE}/contributions/search.json"
    try:
        resp = polite_get(url, params={
            "start_date": since, "end_date": today, "house": house.lower()
        }, accept_json=True)
        data = resp.json()
    except Exception:
        return []

    results = data if isinstance(data, list) else data.get("contributions", data.get("results", []))
    items = []
    for r in results:
        title = (r.get("title") or r.get("debate_title") or r.get("heading") or "").strip()
        if not title:
            continue
        sitting_date = (r.get("date") or r.get("sitting_date") or "")[:10]
        rid = r.get("id") or r.get("slug") or ""
        items.append(_make_item(house, sitting_date, rid, title, r.get("text") or r.get("extract") or ""))
    return items


def _make_item(house: str, sitting_date: str, section_id: str, title: str, summary: str) -> dict:
    return {
        "item_id": f"hansard_{house}_{sitting_date}_{section_id or title[:30]}",
        "title": title,
        "url": _build_url(house.lower(), sitting_date, section_id),
        "published_at": _date_to_iso(sitting_date),
        "summary": summary,
        "matched_kws": [],
    }


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
