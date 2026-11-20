"""
Parliamentary Committees — one source per committee, combining:

  1. News articles   — the committee's press releases on committees.parliament.uk
                       (e.g. "Close AI safety gaps ... MPs urge"), found via Google News.
  2. Publications    — reports, government responses and correspondence, from the
                       official Committees API.
  3. New inquiries   — inquiries / committee business opened recently, from the API.

Why news comes via Google News: the Committees API has no news endpoint, and
committees.parliament.uk serves a Cloudflare challenge ("Just a moment...") to
automated clients such as GitHub Actions runners, so its pages and RSS cannot be
fetched directly. See parliament_committee_news.py.

Committees API docs: https://committees-api.parliament.uk/index.html
No auth required. Official, stable.

Config keys (all optional except id/label/type):
  committee_id   — pin the API committee ID (recommended; see the committee's URL,
                   e.g. committees.parliament.uk/committee/365/... → 365)
  search_name    — fallback lookup by name if committee_id is not set
  house          — "Commons" | "Lords" | "Joint" (used with search_name)
  include        — subset of [news, publications, inquiries]; default all three
  news_days      — how far back to look for news articles (default 30)
  publication_types — list of publication type names to keep
                   (default: Report, Special Report, Government Response, Correspondence)
"""

import logging
import re
from datetime import datetime, timezone

from .base import polite_get
from . import parliament_committee_news

logger = logging.getLogger(__name__)

API_BASE = "https://committees-api.parliament.uk/api"
SITE_BASE = "https://committees.parliament.uk"

# From GET /api/PublicationType
PUBLICATION_TYPE_IDS = {
    "report": 1,
    "government response": 2,
    "correspondence": 3,
    "minutes and decisions": 4,
    "agendas and papers": 5,
    "formal minutes": 6,
    "special report": 12,
    "engagement document": 13,
    "other document": 15,
}
DEFAULT_PUBLICATION_TYPES = ["Report", "Special Report", "Government Response", "Correspondence"]
DEFAULT_INCLUDE = ["news", "publications", "inquiries"]

# The Committees API is often slow (>20s per call)
API_TIMEOUT = 60
API_RETRIES = 1

# Cache of the current-committee list, fetched once per process
_committees_cache: list[dict] | None = None


def fetch(source_cfg: dict) -> list[dict]:
    committee = resolve_committee(source_cfg)
    committee_id = committee["id"]
    include = source_cfg.get("include") or DEFAULT_INCLUDE

    items: list[dict] = []
    failures: list[str] = []

    parts = {
        "news": lambda: parliament_committee_news.fetch_for_committee(
            committee_id, days=int(source_cfg.get("news_days", 30))
        ),
        "publications": lambda: _fetch_publications(
            committee_id, source_cfg.get("publication_types") or DEFAULT_PUBLICATION_TYPES
        ),
        "inquiries": lambda: _fetch_new_business(committee_id),
    }
    for part in include:
        fn = parts.get(part)
        if not fn:
            failures.append(f"unknown include '{part}'")
            continue
        try:
            items.extend(fn())
        except Exception as exc:  # isolate each part — one failing shouldn't hide the others
            logger.warning("Committee %s: %s failed: %s", committee_id, part, exc)
            failures.append(f"{part}: {exc}")

    if failures and not items:
        raise RuntimeError(f"All committee feeds failed for {committee['name']}: " + "; ".join(failures))
    return items


# ── Committee lookup ─────────────────────────────────────────────────────────

def resolve_committee(source_cfg: dict) -> dict:
    """Return {'id', 'name', 'house'} for the configured committee."""
    if source_cfg.get("committee_id"):
        cid = int(source_cfg["committee_id"])
        return {"id": cid, "name": source_cfg.get("label", str(cid)), "house": source_cfg.get("house", "")}

    search_name = source_cfg.get("search_name")
    if not search_name:
        raise ValueError("Committee source needs either committee_id or search_name")
    house = source_cfg.get("house", "Commons")
    found = _find_committee(search_name, house)
    if not found:
        raise ValueError(
            f"Committee not found: '{search_name}' ({house}). "
            "Set committee_id in config.yaml — it's the number in the committee's URL."
        )
    return found


def _norm(name: str) -> str:
    name = name.lower().replace("&", "and")
    name = re.sub(r"\(.*?\)", " ", name)
    name = re.sub(r"\b(the|committee)\b", " ", name)
    return re.sub(r"[^a-z0-9]+", " ", name).strip()


def _all_current_committees() -> list[dict]:
    global _committees_cache
    if _committees_cache is None:
        resp = polite_get(
            f"{API_BASE}/Committees",
            params={"CommitteeStatus": "Current", "Take": 500},
            accept_json=True, timeout=API_TIMEOUT, retries=API_RETRIES,
        )
        _committees_cache = resp.json().get("items", [])
    return _committees_cache


def _find_committee(search_name: str, house: str) -> dict | None:
    target = _norm(search_name)
    candidates = [
        c for c in _all_current_committees()
        if not house or (c.get("house") or "").lower() == house.lower()
    ]

    def ranked(pred):
        # Prefer full committees over sub-committees
        hits = [c for c in candidates if pred(_norm(c.get("name") or ""))]
        hits.sort(key=lambda c: c.get("parentCommittee") is not None)
        return hits

    for pred in (
        lambda n: n == target,
        lambda n: n.startswith(target),
        lambda n: target in n,
    ):
        hits = ranked(pred)
        if hits:
            c = hits[0]
            return {"id": c["id"], "name": c.get("name", ""), "house": c.get("house", "")}
    return None


# ── Publications ─────────────────────────────────────────────────────────────

def _fetch_publications(committee_id: int, type_names: list[str]) -> list[dict]:
    type_ids = [PUBLICATION_TYPE_IDS[t.lower()] for t in type_names if t.lower() in PUBLICATION_TYPE_IDS]
    params = {
        "CommitteeId": committee_id,
        "SortOrder": "PublicationDateDescending",
        "Take": 30,
    }
    if type_ids:
        params["PublicationTypeIds"] = type_ids  # requests repeats the key per value
    resp = polite_get(f"{API_BASE}/Publications", params=params, accept_json=True,
                      timeout=API_TIMEOUT, retries=API_RETRIES)

    items = []
    for p in resp.json().get("items", []):
        pub_id = p.get("id")
        title = (p.get("description") or "").strip()
        if not pub_id or not title:
            continue
        type_name = (p.get("type") or {}).get("name", "Publication")
        inquiries = [b.get("title") for b in (p.get("businesses") or []) if b.get("title")]
        summary = type_name
        if inquiries:
            summary += " · Inquiry: " + "; ".join(inquiries)
        items.append({
            "item_id": f"pub_{pub_id}",
            "title": title,
            "url": _publication_url(p),
            "published_at": _normalise_date(p.get("publicationStartDate")),
            "summary": summary[:500],
            "matched_kws": [],
        })
    return items


def _publication_url(p: dict) -> str:
    pub_id = p["id"]
    # Reports usually have an HTML version on publications.parliament.uk — nicer than the PDF
    if p.get("additionalContentUrl"):
        return p["additionalContentUrl"]
    for doc in p.get("documents") or []:
        doc_id = doc.get("documentId") or doc.get("id")
        if doc_id:
            return f"{SITE_BASE}/publications/{pub_id}/documents/{doc_id}/default/"
    return f"{SITE_BASE}/publications/{pub_id}/"


# ── New inquiries / committee business ───────────────────────────────────────

def _fetch_new_business(committee_id: int | None = None, take: int = 10) -> list[dict]:
    params = {"SortOrder": "DateOpenedNewest", "Take": take}
    if committee_id:
        params["CommitteeId"] = committee_id
    resp = polite_get(f"{API_BASE}/CommitteeBusiness", params=params, accept_json=True,
                      timeout=API_TIMEOUT, retries=API_RETRIES)

    items = []
    for b in resp.json().get("items", []):
        biz_id = b.get("id")
        title = (b.get("title") or "").strip()
        if not biz_id or not title:
            continue
        btype = (b.get("type") or {}).get("name", "Inquiry")
        label = "New inquiry" if (b.get("type") or {}).get("isInquiry") else f"New {btype.lower()}"
        summary_bits = [btype]
        for sp in b.get("openSubmissionPeriods") or []:
            if sp.get("endDate"):
                summary_bits.append(f"Evidence deadline {sp['endDate'][:10]}")
                break
        items.append({
            "item_id": f"business_{biz_id}",
            "title": f"{label}: {title}",
            "url": f"{SITE_BASE}/work/{biz_id}/",
            "published_at": _normalise_date(b.get("openDate")),
            "summary": " · ".join(summary_bits),
            "matched_kws": [],
        })
    return items


def _normalise_date(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()
