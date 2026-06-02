"""
Written Statements — UK Parliament OData API.
Endpoint: https://oralquestionsandstatements.parliament.uk/api/writtenstatements
Docs: https://developer.parliament.uk/

API is official, no auth required.
Returns JSON with OData envelope.

RELIABILITY: This is a stable, documented Parliament API. Low brittleness.
"""

from datetime import datetime, timedelta, timezone
from .base import polite_get

API_BASE = "https://oralquestionsandstatements.parliament.uk/api/writtenstatements"


def fetch(source_cfg: dict) -> list[dict]:
    house = source_cfg.get("house", "Commons")
    # Fetch statements from the last 7 days to catch any missed by the last run
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    params = {
        "house": house,
        "date_from": since,
        "take": 50,
        "skip": 0,
    }

    resp = polite_get(API_BASE, params=params, accept_json=True)
    data = resp.json()

    # OData response may use 'value' key or top-level list
    results = data if isinstance(data, list) else data.get("value", data.get("results", []))

    items = []
    for r in results:
        statement_id = str(r.get("id", "")) or r.get("UIN", "")
        made_when = r.get("dateMade") or r.get("date") or ""
        title = (r.get("title") or r.get("Title") or "Written Statement").strip()
        minister = r.get("answeringBodyName") or r.get("AnsweringBodyName") or ""
        if minister:
            title = f"{title} — {minister}"

        url = _build_url(r)
        summary = (r.get("text") or r.get("Text") or "")
        if summary:
            import re
            summary = re.sub(r"<[^>]+>", " ", summary).strip()[:500]

        item = {
            "item_id": f"ws_{house}_{statement_id}",
            "title": title,
            "url": url,
            "published_at": _normalise_date(made_when),
            "summary": summary,
            "matched_kws": [],
        }
        if item["title"] and statement_id:
            items.append(item)
    return items


def _build_url(r: dict) -> str:
    sid = r.get("id") or r.get("UIN", "")
    if sid:
        return f"https://questions-statements.parliament.uk/written-statements/detail/{sid}"
    return "https://questions-statements.parliament.uk/written-statements"


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
