"""
Commons/Lords Votes (Divisions) fetcher.

Commons: https://commonsvotes-api.parliament.uk/swagger/docs/v1
  GET /data/Divisions.json/search?queryParameters.startDate=YYYY-MM-DD&queryParameters.take=N

Lords: https://lordsvotes-api.parliament.uk
  GET /data/Divisions/search?queryParameters.startDate=YYYY-MM-DD&queryParameters.take=N

No auth required. Official, stable.
"""

from datetime import date, timedelta, timezone, datetime
from .base import polite_get

COMMONS_API = "https://commonsvotes-api.parliament.uk"
LORDS_API   = "https://lordsvotes-api.parliament.uk"


def fetch(source_cfg: dict) -> list[dict]:
    house = source_cfg.get("house", "Commons")
    since = (date.today() - timedelta(days=14)).isoformat()
    return _fetch_commons(since) if house == "Commons" else _fetch_lords(since)


def _fetch_commons(since: str) -> list[dict]:
    params = {
        "queryParameters.startDate": since,
        "queryParameters.take": 25,
        "queryParameters.skip": 0,
    }
    try:
        resp = polite_get(f"{COMMONS_API}/data/Divisions.json/search", params=params, accept_json=True)
        data = resp.json()
    except Exception:
        return []

    items = data if isinstance(data, list) else data.get("items", data.get("value", []))
    return [
        {
            "item_id": f"votes_commons_{d.get('DivisionId') or d.get('divisionId', '')}",
            "title": (d.get("Title") or d.get("title") or "").strip(),
            "url": _commons_url(d.get("DivisionId") or d.get("divisionId")),
            "published_at": _normalise_date(d.get("Date") or d.get("date") or ""),
            "summary": f"Ayes: {d.get('AyeCount', '?')} · Noes: {d.get('NoCount', d.get('NoeCount', '?'))}",
            "matched_kws": [],
        }
        for d in items if (d.get("Title") or d.get("title"))
    ]


def _fetch_lords(since: str) -> list[dict]:
    params = {
        "queryParameters.startDate": since,
        "queryParameters.take": 25,
        "queryParameters.skip": 0,
    }
    try:
        resp = polite_get(f"{LORDS_API}/data/Divisions/search", params=params, accept_json=True)
        data = resp.json()
    except Exception:
        return []

    items = data if isinstance(data, list) else data.get("items", data.get("value", []))
    return [
        {
            "item_id": f"votes_lords_{d.get('DivisionId') or d.get('divisionId', '')}",
            "title": (d.get("Title") or d.get("title") or d.get("DivisionTitle") or "").strip(),
            "url": _lords_url(d.get("DivisionId") or d.get("divisionId")),
            "published_at": _normalise_date(d.get("Date") or d.get("date") or ""),
            "summary": f"Contents: {d.get('ContentCount', '?')} · Not-Contents: {d.get('NotContentCount', '?')}",
            "matched_kws": [],
        }
        for d in items if (d.get("Title") or d.get("title") or d.get("DivisionTitle"))
    ]


def _commons_url(did) -> str:
    return f"https://votes.parliament.uk/Votes/Commons/Division/{did}" if did else "https://votes.parliament.uk"


def _lords_url(did) -> str:
    return f"https://votes.parliament.uk/Votes/Lords/Division/{did}" if did else "https://votes.parliament.uk"


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
