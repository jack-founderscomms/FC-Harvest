"""Temporary probe: discover which committee news endpoints respond from CI."""
import json, requests, re

UA_TOOL = "FC-Harvest/1.0 (parliamentary monitoring tool)"
UA_BROWSER = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/124.0 Safari/537.36")
API = "https://committees-api.parliament.uk/api"
SITE = "https://committees.parliament.uk"

def hit(url, ua=UA_TOOL, accept="application/json", n=700, params=None):
    try:
        r = requests.get(url, params=params, headers={"User-Agent": ua, "Accept": accept}, timeout=20)
        print(f"\n### {r.status_code} {r.headers.get('content-type','')} {r.url}")
        print(r.text[:n].replace("\n", " "))
        return r
    except Exception as e:
        print(f"\n### EXC {url}: {e}")

# swagger paths
r = hit("https://committees-api.parliament.uk/swagger/v1/swagger.json", n=0)
if r is not None and r.ok:
    try:
        sw = r.json()
        for p, ops in sw.get("paths", {}).items():
            for m, op in ops.items():
                params = [x.get("name") for x in op.get("parameters", [])]
                print("PATH", m.upper(), p, params)
    except Exception as e:
        print("swagger parse fail", e)

hit(f"{API}/Committees/365")
r = hit(f"{API}/Committees", params={"CommitteeStatus": "Current", "Take": 400}, n=0)
if r is not None and r.ok:
    d = r.json()
    print("totalResults", d.get("totalResults"))
    for c in d.get("items", []):
        print("COMMITTEE", c.get("id"), "|", c.get("name"), "|", c.get("house"), "|", (c.get("category") or {}).get("name"))
hit(f"{API}/Publications", params={"CommitteeId": 365, "Take": 3}, n=2500)
for guess in ["NewsArticles", "News", "Committees/365/News", "NewsArticle"]:
    hit(f"{API}/{guess}", params={"CommitteeId": 365, "Take": 3}, n=1500)
hit(f"{API}/CommitteeBusiness", params={"CommitteeId": 365, "Take": 2}, n=1200)

slug = "business-innovation-science-and-trade-committee"
for ua in (UA_TOOL, UA_BROWSER):
    print("\n======== UA:", ua[:30])
    for path in [f"/committee/365/{slug}/news/", f"/committee/365/{slug}/news/rss/",
                 f"/committee/365/news/rss/", f"/committee/365/rss/", "/rss/committee/365/news",
                 f"/committee/365/{slug}/news/219006/close-ai-safety-gaps-to-secure-britains-400-billion-ai-growth-opportunity-mps-urge/"]:
        r = hit(SITE + path, ua=ua, accept="text/html,application/xhtml+xml,application/rss+xml,*/*", n=300)
        if r is not None and r.ok and "html" in r.headers.get("content-type", ""):
            links = sorted(set(re.findall(r'href="([^"]*(?:rss|feed|news/\d+)[^"]*)"', r.text)))[:25]
            print("LINKS", links)
            print("SNIP", re.sub(r"\s+", " ", r.text[r.text.find("<main"):][:3000]))
