"""
Fetch parliamentary committee activity into docs/committees.json for the dashboard.

Why this runs as a scheduled job rather than in the browser like the rest of
docs/index.html:
  • committees-api.parliament.uk sends no CORS headers, so browsers block the page
    from reading it;
  • the Committees API has no news endpoint, and committees.parliament.uk shows
    automated clients a Cloudflare challenge, so news articles come from Google
    News, which browsers also block (no CORS).
The page loads this JSON from raw.githubusercontent.com, which does allow it.

Per committee it collects:
  • committee news   — press releases on committees.parliament.uk (via Google News)
  • reports, special reports, government responses and correspondence (API)
  • newly opened inquiries / committee business (API)
  • upcoming and recent hearings / meetings (API)

The committee list is read from COMMITTEE_SOURCES in docs/index.html
(the `committeeId:` values), so committees are configured in one place.

Run: python scripts/fetch_committees.py
"""

import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "docs" / "index.html"
OUT = ROOT / "docs" / "committees.json"

API = "https://committees-api.parliament.uk/api"
SITE = "https://committees.parliament.uk"
GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
HEADERS = {"User-Agent": "FC-Harvest/1.0 (parliamentary monitoring tool)"}
NEWS_DAYS = 30
API_TIMEOUT = 60  # the Committees API is often slow

# GET /api/PublicationType: 1 Report, 2 Government Response, 3 Correspondence, 12 Special Report
PUBLICATION_TYPES = {1: "committee report", 12: "committee report",
                     2: "government_response", 3: "committee correspondence"}

_session = requests.Session()
_session.headers.update(HEADERS)


def get(url, params=None, timeout=API_TIMEOUT, retries=2):
    """GET with a polite pause; retries timeouts and 429 (rate limited) with backoff."""
    for attempt in range(retries + 1):
        time.sleep(1 if attempt == 0 else 15 * attempt)
        try:
            r = _session.get(url, params=params, timeout=timeout)
        except requests.Timeout:
            if attempt == retries:
                raise
            continue
        if r.status_code == 429 and attempt < retries:
            continue
        r.raise_for_status()
        return r


def committee_ids():
    html = PAGE.read_text(encoding="utf-8")
    block = re.search(r"const COMMITTEE_SOURCES\s*=\s*\[(.*?)\];", html, re.S)
    if not block:
        sys.exit("COMMITTEE_SOURCES not found in docs/index.html")
    return sorted({int(x) for x in re.findall(r"committeeId\s*:\s*(\d+)", block.group(1))})


def iso(raw):
    """API dates are UK local time without an offset; keep them as-is (the page treats them as local)."""
    return (raw or "")[:19]


# ── News (Google News) ───────────────────────────────────────────────────────

_SUFFIX = re.compile(r"\s+-\s+UK Parliament\s*$")
_LISTING = re.compile(r"\s-\s.*\b(Committees?|Sub-Committee)\s*$")  # "X Committee - Publications - Committees"
_GENERIC = {"written evidence", "oral evidence", "faqs", "all former committee members",
            "publications", "news", "events", "membership", "role", "contact us"}


def fetch_news(cid):
    r = get(GOOGLE_NEWS_RSS, timeout=30, params={
        "q": f"site:committees.parliament.uk/committee/{cid} when:{NEWS_DAYS}d",
        "hl": "en-GB", "gl": "GB", "ceid": "GB:en"})
    items, seen = [], set()
    for it in ET.fromstring(r.content).iter("item"):
        title = _SUFFIX.sub("", (it.findtext("title") or "").strip()).strip()
        if not title or title.lower() in _GENERIC or _LISTING.search(title) or title.lower() in seen:
            continue
        seen.add(title.lower())
        try:
            published = parsedate_to_datetime(it.findtext("pubDate")).astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            published = ""
        guid = (it.findtext("guid") or it.findtext("link") or title).strip()
        items.append({"item_id": f"cmt_news_{cid}_{guid[-40:]}", "title": title,
                      "url": (it.findtext("link") or "").strip(), "published_at": published,
                      "summary": "", "doc_type": "committee news"})
    return items


# ── Publications ─────────────────────────────────────────────────────────────

def fetch_publications(cid):
    r = get(f"{API}/Publications", params={
        "CommitteeId": cid, "SortOrder": "PublicationDateDescending", "Take": 25,
        "PublicationTypeIds": list(PUBLICATION_TYPES)})
    items = []
    for p in r.json().get("items", []):
        if not p.get("id") or not p.get("description"):
            continue
        ptype = p.get("type") or {}
        inquiries = [b["title"] for b in p.get("businesses") or [] if b.get("title")]
        url = p.get("additionalContentUrl")  # HTML version of reports
        if not url:
            docs = [d.get("documentId") for d in p.get("documents") or [] if d.get("documentId")]
            url = f"{SITE}/publications/{p['id']}/documents/{docs[0]}/default/" if docs else f"{SITE}/publications/{p['id']}/"
        items.append({"item_id": f"cmt_pub_{p['id']}", "title": p["description"].strip(), "url": url,
                      "published_at": iso(p.get("publicationStartDate")),
                      "summary": " · ".join([ptype.get("name", "")] + [f"Inquiry: {t}" for t in inquiries])[:500],
                      "doc_type": PUBLICATION_TYPES.get(ptype.get("id"), "committee publication")})
    return items


# ── Inquiries / committee business ───────────────────────────────────────────

def fetch_inquiries(cid):
    r = get(f"{API}/CommitteeBusiness", params={"CommitteeId": cid, "SortOrder": "DateOpenedNewest", "Take": 10})
    items = []
    for b in r.json().get("items", []):
        if not b.get("id") or not b.get("title"):
            continue
        btype = b.get("type") or {}
        prefix = "New inquiry" if btype.get("isInquiry") else f"New {btype.get('name', 'business').lower()}"
        summary = [btype.get("name", "")]
        for sp in b.get("openSubmissionPeriods") or []:
            if sp.get("endDate"):
                summary.append(f"Call for evidence closes {sp['endDate'][:10]}")
                break
        items.append({"item_id": f"cmt_inq_{b['id']}", "title": f"{prefix}: {b['title'].strip()}",
                      "url": f"{SITE}/work/{b['id']}/", "published_at": iso(b.get("openDate")),
                      "summary": " · ".join(s for s in summary if s), "doc_type": "inquiry"})
    return items


# ── Hearings / meetings ──────────────────────────────────────────────────────

def fetch_events(cid):
    today = date.today()
    r = get(f"{API}/Committees/{cid}/Events", params={
        "StartDateFrom": (today - timedelta(days=7)).isoformat(),
        "StartDateTo": (today + timedelta(days=42)).isoformat(),
        "ExcludeCancelledEvents": "true", "SortAscending": "true", "Take": 20})
    items = []
    for e in r.json().get("items", []):
        if not e.get("id"):
            continue
        etype = (e.get("eventType") or {}).get("name", "Committee meeting")
        if "private" in etype.lower():  # private deliberative meetings — nothing to follow
            continue
        topics = [b.get("title") for b in e.get("committeeBusinesses") or [] if b.get("title")]
        title = e.get("name") or (f"{etype}: {'; '.join(topics)}" if topics else etype)
        summary = [x for x in (e.get("location"), "; ".join(topics) if topics and e.get("name") else "") if x]
        items.append({"item_id": f"cmt_ev_{e['id']}", "title": title.strip(),
                      "url": f"{SITE}/event/{e['id']}/", "published_at": iso(e.get("startDate")),
                      "summary": " · ".join(summary), "doc_type": "committee hearing", "_is_event": True})
    return items


PARTS = {"news": fetch_news, "publications": fetch_publications,
         "inquiries": fetch_inquiries, "events": fetch_events}


def main():
    ids = committee_ids()
    previous = {}
    if OUT.exists():
        try:
            for i in json.loads(OUT.read_text()).get("items", []):
                previous.setdefault((i["committee_id"], i["_part"]), []).append(i)
        except (ValueError, KeyError):
            pass

    items, failed = [], []
    for cid in ids:
        for part, fn in PARTS.items():
            try:
                got = fn(cid)
            except Exception as e:  # keep the last good data for this part rather than dropping it
                got = previous.get((cid, part), [])
                failed.append(f"{cid}/{part}: {str(e)[:120]}")
                print(f"committee {cid} {part}: FAILED ({e}); keeping {len(got)} previous")
            else:
                print(f"committee {cid} {part}: {len(got)}")
            for i in got:
                i["committee_id"], i["_part"] = cid, part
            items.extend(got)

    items.sort(key=lambda i: i["published_at"], reverse=True)
    OUT.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "committee_ids": ids, "failed": failed, "items": items,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(items)} items for {len(ids)} committees ({len(failed)} failures)")
    if len(failed) == len(ids) * len(PARTS):
        sys.exit("everything failed")


if __name__ == "__main__":
    main()
