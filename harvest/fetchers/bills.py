"""
Bills fetcher — UK Parliament Bills API.
Docs: https://bills-api.parliament.uk/index.html
Base: https://bills-api.parliament.uk/api/v1

No auth required. Returns JSON. Official, stable.
"""

from datetime import date, timedelta, timezone, datetime
from .base import polite_get

API_BASE = "https://bills-api.parliament.uk/api/v1"


def fetch(source_cfg: dict) -> list[dict]:
    house = source_cfg.get("house", "Commons")
    since = (date.today() - timedelta(days=30)).isoformat()

    params = {
        "lastUpdatedFrom": since,
        "currentHouse": house,
        "sortOrder": "DateUpdatedDescending",
        "take": 25,
        "skip": 0,
    }
    try:
        resp = polite_get(f"{API_BASE}/Bills", params=params, accept_json=True)
        data = resp.json()
    except Exception:
        return []

    items_raw = data if isinstance(data, list) else data.get("items", [])
    items = []
    for b in items_raw:
        bill_id = str(b.get("billId") or b.get("id") or "")
        title = (b.get("shortTitle") or b.get("longTitle") or "").strip()
        if not title:
            continue
        stage = ""
        cs = b.get("currentStage")
        if isinstance(cs, dict):
            stage = cs.get("description") or cs.get("name") or ""
        elif isinstance(cs, str):
            stage = cs

        items.append({
            "item_id": f"bills_{house}_{bill_id}",
            "title": title,
            "url": f"https://bills.parliament.uk/bills/{bill_id}" if bill_id else "https://bills.parliament.uk",
            "published_at": _normalise_date(b.get("lastUpdate") or b.get("dateIntroduced") or ""),
            "summary": f"Stage: {stage}" if stage else "",
            "matched_kws": [],
        })
    return items


def _normalise_date(raw: str) -> str | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(raw[:19].rstrip("Z"), fmt.rstrip("Z"))
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return raw
