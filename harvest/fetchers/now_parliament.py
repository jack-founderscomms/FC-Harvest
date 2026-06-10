"""
Live Now fetcher — what's happening in Parliament right now.
API: https://now-api.parliament.uk/index.html
Base: https://now-api.parliament.uk/api

Endpoints:
  GET /api/CommonsBusiness  — current/today's Commons business
  GET /api/LordsBusiness    — current/today's Lords business

No auth required. Official, stable. Data is live / near-real-time.
"""

from datetime import date, timezone, datetime
from .base import polite_get

API_BASE = "https://now-api.parliament.uk/api"


def fetch(source_cfg: dict) -> list[dict]:
    house = source_cfg.get("house", "Commons")
    endpoint = "CommonsBusiness" if house == "Commons" else "LordsBusiness"

    try:
        resp = polite_get(f"{API_BASE}/{endpoint}", accept_json=True)
        data = resp.json()
    except Exception:
        return []

    items = []
    today = date.today().isoformat()

    def add(b: dict):
        title = (b.get("Title") or b.get("title") or
                 b.get("Description") or b.get("description") or "").strip()
        if not title or len(title) < 3:
            return
        bid = str(b.get("Id") or b.get("id") or title[:40])
        items.append({
            "item_id": f"now_{house}_{bid}",
            "title": title,
            "url": "https://www.parliament.uk/business/live/",
            "published_at": datetime.now(timezone.utc).isoformat(),
            "summary": (b.get("Category") or b.get("category") or
                        b.get("SubTitle") or b.get("subtitle") or "").strip(),
            "matched_kws": [],
        })

    businesses = (
        data if isinstance(data, list)
        else (data.get("CurrentAdjournment") or data.get("BusinessItems") or data.get("items") or [])
    )
    for b in businesses:
        add(b)
        for sub in (b.get("BusinessItems") or b.get("items") or []):
            add(sub)

    return items
