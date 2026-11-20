"""Temporary probe round 2."""
import requests, re, json
from xml.etree import ElementTree as ET
UA = "FC-Harvest/1.0 (parliamentary monitoring tool)"
API = "https://committees-api.parliament.uk/api"

def get(url, params=None, accept="application/json"):
    r = requests.get(url, params=params, headers={"User-Agent": UA, "Accept": accept}, timeout=20)
    print(f"\n### {r.status_code} {r.headers.get('content-type','')} {r.url}")
    return r

r = get(f"{API}/PublicationType")
for t in r.json(): print("PUBTYPE", t.get("id"), t.get("name"))

r = get(f"{API}/Publications", {"CommitteeId": 365, "Take": 8, "SortOrder": "PublicationDateDescending"})
print(r.text[:300])
if r.ok:
    for p in r.json().get("items", []):
        print("PUB", p.get("id"), p.get("publicationStartDate"), (p.get("type") or {}).get("name"), "|", p.get("description"),
              "| biz:", [b.get("title") for b in p.get("businesses") or []], "| keys:", sorted(p.keys()))
    print(json.dumps(r.json()["items"][0], indent=1)[:3000])

r = get(f"{API}/CommitteeBusiness", {"CommitteeId": 365, "Take": 5, "SortOrder": "DateOpenedNewest"})
print(r.text[:200])
if r.ok:
    for b in r.json().get("items", []): print("BIZ", b.get("id"), b.get("openDate"), b.get("title"))

r = get(f"{API}/Events", {"CommitteeId": 365, "Take": 3, "StartDateFrom": "2026-11-01"})
print(r.text[:1500])

for q in ["site:committees.parliament.uk/committee/365",
          'site:committees.parliament.uk "Close AI safety gaps"',
          "site:committees.parliament.uk news"]:
    r = get("https://news.google.com/rss/search", {"q": q, "hl": "en-GB", "gl": "GB", "ceid": "GB:en"}, accept="application/rss+xml")
    try:
        root = ET.fromstring(r.content)
        for it in root.iter("item"):
            print("GN", it.findtext("pubDate"), "|", it.findtext("title"), "|", it.findtext("link")[:120], "|", (it.find("source").attrib if it.find("source") is not None else ""))
    except Exception as e:
        print("parse fail", e, r.text[:300])

r = get("https://www.bing.com/news/search", {"q": "site:committees.parliament.uk", "format": "rss"}, accept="application/rss+xml")
print(r.text[:1500])
