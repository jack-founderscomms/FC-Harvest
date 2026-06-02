"""
Written Statements — UK Parliament API.
Endpoint: https://questions-statements-api.parliament.uk/api/WrittenStatements
(Previously oralquestionsandstatements.parliament.uk — that domain no longer exists.)

Official API, no auth required. Returns JSON.
RELIABILITY: Official Parliament API. Low brittleness.
"""

import re
from datetime import datetime, timedelta, timezone
from .base import polite_get

API_BASE = "https://questions-statements-api.parliament.uk/api/WrittenStatements"


def fetch(source_cfg: dict) -> list[dict]:
    house = source_cfg.get("house", "Commons")
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    params = {
        "house": house,
        "dateFrom": since,
        "take": 50,
        "skip": 0,
    }

    resp = polite_get(API_BASE, params=params, accept_json=True)
    data = resp.json()

    results = data if isinstance(data, list) else data.get("results", data.get("value", []))

    items = []
    for r in results:
        statement_id = str(r.get("id") or r.get("uin") or r.get("UIN") or "")
        if not statement_id:
            continue

        title = (r.get("title") or r.get("Title") or "Written Statement").strip()
        body_name = r.get("answeringBodyName") or r.get("AnsweringBodyName") or ""
        if body_name:
            title = f"{title} — {body_name}"

        made_when = r.get("dateMade") or r.get("date") or r.get("DateMade") or ""

        raw_text = r.get("text") or r.get("Text") or ""
        summary = re.sub(r"<[^>]+>", " ", raw_text).strip()[:500] if raw_text else ""

        items.append({
            "item_id": f"ws_{house}_{statement_id}",
            "title": title,
            "url": f"https://questions-statements.parliament.uk/written-statements/detail/{statement_id}",
            "published_at": _normalise_date(made_when),
            "summary": summary,
            "matched_kws": [],
        })
    return items


def _normalise_date(raw: str) -> str | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            dt = datetime.strptime(raw[:26].rstrip("Z"), fmt.rstrip("Z"))
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return raw
