"""
Written Statements — UK Parliament API.
Docs: https://questions-statements-api.parliament.uk/index.html
Base: https://questions-statements-api.parliament.uk/api

No auth required. Returns JSON. Official, stable.

NOTE: The old domain oralquestionsandstatements.parliament.uk no longer exists.
The current domain is questions-statements-api.parliament.uk
"""

import re
from datetime import datetime, timedelta, timezone
from .base import polite_get

API_BASE = "https://questions-statements-api.parliament.uk/api"


def fetch(source_cfg: dict) -> list[dict]:
    house = source_cfg.get("house", "Commons")
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    # Try the writtenstatements endpoint first, then writtenquestions as fallback
    for path, label in (("writtenstatements", "statement"), ("writtenquestions", "question")):
        url = f"{API_BASE}/{path}"
        params = {
            "house": house,
            "dateFrom": since,
            "take": 50,
            "skip": 0,
        }
        try:
            resp = polite_get(url, params=params, accept_json=True)
            if resp.status_code != 200:
                continue
            data = resp.json()
            results = data if isinstance(data, list) else data.get("results", data.get("value", []))
            if results:
                return _parse_results(results, house, label)
        except Exception:
            continue

    return []


def _parse_results(results: list, house: str, label: str) -> list[dict]:
    items = []
    for r in results:
        statement_id = str(r.get("id") or r.get("uin") or r.get("UIN") or "")
        if not statement_id:
            continue

        title = (r.get("title") or r.get("Title") or f"Written {label.title()}").strip()
        body_name = (
            r.get("answeringBodyName") or r.get("AnsweringBodyName")
            or r.get("department") or r.get("Department") or ""
        )
        if body_name:
            title = f"{title} — {body_name}"

        made_when = (
            r.get("dateMade") or r.get("date") or r.get("DateMade")
            or r.get("dateAsked") or r.get("DateAsked") or ""
        )

        raw_text = r.get("text") or r.get("Text") or r.get("answerText") or ""
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
