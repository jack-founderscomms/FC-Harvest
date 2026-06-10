"""
Oral Questions fetcher.
API: https://oralquestionsandmotions-api.parliament.uk/swagger/ui/index
Base: https://oralquestionsandmotions-api.parliament.uk/api

Fetches oral questions for the next 7 days and last 7 days.
No auth required. Official, stable.
"""

from datetime import date, timedelta, timezone, datetime
from .base import polite_get

API_BASE = "https://oralquestionsandmotions-api.parliament.uk/api"


def fetch(source_cfg: dict) -> list[dict]:
    items = []
    seen = set()
    today = date.today()

    for offset in range(-7, 8):
        target = (today + timedelta(days=offset)).isoformat()
        for item in _fetch_for_date(target):
            if item["item_id"] not in seen:
                seen.add(item["item_id"])
                items.append(item)

    return items


def _fetch_for_date(target_date: str) -> list[dict]:
    try:
        resp = polite_get(f"{API_BASE}/oralquestions/list",
                          params={"date": target_date}, accept_json=True)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []

    rows = data if isinstance(data, list) else (
        data.get("Response") or data.get("results") or data.get("value") or []
    )
    items = []
    for q in rows:
        qid = str(q.get("Id") or q.get("id") or "")
        text = (q.get("QuestionText") or q.get("questionText") or q.get("Text") or "").strip()
        if not text:
            continue
        body = (q.get("AnsweringBodyName") or q.get("answeringBodyName") or "").strip()
        member = (q.get("AskingMemberName") or q.get("askingMemberName") or "").strip()
        answer_date = (q.get("OralAnswerDate") or q.get("oralAnswerDate") or target_date)[:10]

        items.append({
            "item_id": f"oraq_{qid or (target_date + '_' + text[:20])}",
            "title": f"[{body}] {text}" if body else text,
            "url": "https://questions-statements.parliament.uk/oral-questions",
            "published_at": _normalise_date(answer_date),
            "summary": f"Asked by {member}" if member else "",
            "matched_kws": [],
        })
    return items


def _normalise_date(raw: str) -> str | None:
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw[:10], "%Y-%m-%d")
            return dt.replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return raw
