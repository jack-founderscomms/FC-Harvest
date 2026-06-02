"""
Parliamentary Committees — official Committees API.
Docs/Swagger: https://committees-api.parliament.uk/index.html
Base URL: https://committees-api.parliament.uk/api

No auth required. Returns JSON. Official, stable.

We fetch:
  1. The committee ID for the configured committee name via /api/Committees
  2. Recent news/publications via /api/Committees/{id}/NewsArticles (or similar)

Committee IDs are cached in-process to avoid repeated discovery calls.
"""

import re
from datetime import datetime, timezone
from .base import polite_get

API_BASE = "https://committees-api.parliament.uk/api"

# Cache: normalised search name → committee id
_committee_id_cache: dict[str, int | None] = {}


def fetch(source_cfg: dict) -> list[dict]:
    search_name = source_cfg["search_name"]
    house = source_cfg.get("house", "Commons")

    committee_id = _find_committee_id(search_name, house)
    if not committee_id:
        raise ValueError(
            f"Committee not found: '{search_name}' ({house}). "
            "Check https://committees-api.parliament.uk/index.html for current committee names."
        )

    # Fetch news articles for this committee
    news_url = f"{API_BASE}/Committees/{committee_id}/NewsArticles"
    try:
        resp = polite_get(news_url, params={"take": 30, "skip": 0}, accept_json=True)
        data = resp.json()
    except Exception:
        # Fallback: try publications endpoint
        pub_url = f"{API_BASE}/Committees/{committee_id}/Publications"
        resp = polite_get(pub_url, params={"take": 30, "skip": 0}, accept_json=True)
        data = resp.json()

    results = data if isinstance(data, list) else data.get("items", data.get("results", []))

    items = []
    for r in results:
        title = (r.get("title") or r.get("Title") or "").strip()
        if not title:
            continue

        item_id = str(r.get("id") or r.get("Id") or "")
        url = r.get("url") or r.get("Url") or r.get("link") or ""
        if not url and item_id:
            url = f"https://committees.parliament.uk/committee/{committee_id}/news/{item_id}"

        pub_date = r.get("publishedDate") or r.get("PublishedDate") or r.get("date") or ""

        items.append({
            "item_id": f"committee_{committee_id}_{item_id or title[:40]}",
            "title": title,
            "url": url,
            "published_at": _normalise_date(pub_date),
            "summary": (r.get("summary") or r.get("Summary") or "")[:500],
            "matched_kws": [],
        })
    return items


def _find_committee_id(search_name: str, house: str) -> int | None:
    cache_key = f"{search_name.lower()}|{house.lower()}"
    if cache_key in _committee_id_cache:
        return _committee_id_cache[cache_key]

    # Fetch all committees
    url = f"{API_BASE}/Committees"
    params = {"house": house, "currentCommitteesOnly": "true"}
    try:
        resp = polite_get(url, params=params, accept_json=True)
        data = resp.json()
    except Exception:
        _committee_id_cache[cache_key] = None
        return None

    committees = data if isinstance(data, list) else data.get("items", data.get("value", []))

    name_lower = search_name.lower()
    found_id = None

    for c in committees:
        c_name = (c.get("name") or c.get("Name") or "").lower()
        c_house = (c.get("house") or c.get("House") or "").lower()

        if name_lower not in c_name:
            continue
        if house.lower() not in c_house and c_house:
            continue

        found_id = c.get("id") or c.get("Id")
        break

    # If exact match failed, try partial substring match
    if not found_id:
        name_words = set(name_lower.split())
        best, best_score = None, 0
        for c in committees:
            c_name = (c.get("name") or c.get("Name") or "").lower()
            c_house = (c.get("house") or c.get("House") or "").lower()
            if house.lower() not in c_house and c_house:
                continue
            score = sum(1 for w in name_words if w in c_name)
            if score > best_score:
                best_score = score
                best = c.get("id") or c.get("Id")
        if best_score >= 2:
            found_id = best

    _committee_id_cache[cache_key] = found_id
    return found_id


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
