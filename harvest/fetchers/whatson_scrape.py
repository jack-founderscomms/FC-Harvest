"""
What's On in Parliament — official What's On API.
Docs/Swagger: https://whatson-api.parliament.uk/swagger/ui/index
Base URL: https://whatson-api.parliament.uk

No auth required. Returns JSON. Official, stable.

Falls back to HTML scrape of whatson.parliament.uk if the API returns no results.
"""

from datetime import date, timedelta, timezone, datetime
from .base import polite_get

API_BASE = "https://whatson-api.parliament.uk/api"


def fetch(source_cfg: dict) -> list[dict]:
    items = _fetch_via_api()
    if items:
        return items
    return _fetch_via_scrape(source_cfg.get("url", "https://whatson.parliament.uk"))


def _fetch_via_api() -> list[dict]:
    since = date.today().isoformat()
    until = (date.today() + timedelta(days=14)).isoformat()

    # Try events endpoint
    for endpoint in ("events", "Events", "calendar", "Calendar"):
        url = f"{API_BASE}/{endpoint}"
        params = {"startDate": since, "endDate": until, "take": 50}
        try:
            resp = polite_get(url, params=params, accept_json=True)
            if resp.status_code != 200:
                continue
            data = resp.json()
            results = data if isinstance(data, list) else data.get("results", data.get("items", []))
            if not results:
                continue
            return _parse_api_events(results)
        except Exception:
            continue
    return []


def _parse_api_events(results: list) -> list[dict]:
    items = []
    for r in results:
        title = (r.get("title") or r.get("Title") or r.get("name") or r.get("Name") or "").strip()
        if not title:
            continue

        event_id = str(r.get("id") or r.get("Id") or title[:40])
        event_date = r.get("startDate") or r.get("date") or r.get("StartDate") or ""
        url = r.get("url") or r.get("Url") or r.get("link") or ""

        items.append({
            "item_id": f"whatson_{event_id}",
            "title": title,
            "url": url,
            "published_at": _normalise_date(event_date),
            "summary": (r.get("description") or r.get("Description") or "")[:500],
            "matched_kws": [],
        })
    return items


def _fetch_via_scrape(url: str) -> list[dict]:
    import re
    from bs4 import BeautifulSoup
    try:
        resp = polite_get(url)
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    items = []

    for a in soup.find_all("a", href=True):
        title = a.get_text(strip=True)
        if not title or len(title) < 6:
            continue
        href = a["href"]
        if not href.startswith("http"):
            href = "https://whatson.parliament.uk" + href

        parent_text = (a.parent.get_text(" ", strip=True) if a.parent else "")
        published_at = _extract_date_from_text(parent_text)

        items.append({
            "item_id": href.split("?")[0].rstrip("/"),
            "title": title,
            "url": href,
            "published_at": published_at,
            "summary": "",
            "matched_kws": [],
        })

    # Dedupe by item_id
    seen = set()
    unique = []
    for it in items:
        if it["item_id"] not in seen:
            seen.add(it["item_id"])
            unique.append(it)
    return unique[:50]


def _extract_date_from_text(text: str) -> str | None:
    import re
    m = re.search(r"\b(\d{1,2}\s+\w+\s+\d{4})\b", text)
    if m:
        try:
            dt = datetime.strptime(m.group(1), "%d %B %Y")
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    return None


def _normalise_date(raw: str) -> str | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(raw[:19], fmt)
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return raw
