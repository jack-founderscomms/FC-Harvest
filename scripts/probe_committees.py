"""Temporary: run the committee fetchers live from CI and print what they return."""
import json, sys, logging, requests
sys.path.insert(0, ".")
logging.basicConfig(level=logging.INFO)
from harvest.runner import load_config, FETCHER_MAP
from harvest.filters import match_keywords

r = requests.get("https://committees-api.parliament.uk/api/Publications",
                 params={"CommitteeId": 365, "Take": 2, "SortOrder": "PublicationDateDescending"}, timeout=20)
for p in r.json()["items"]:
    print("DOCS", p["id"], json.dumps(p.get("documents"))[:800], "| addl:", p.get("additionalContentUrl"))

cfg = load_config()
kws = cfg["keywords"]
for group in ("committees", "inquiries"):
    for src in cfg["sources"][group]:
        try:
            items = FETCHER_MAP[src["type"]].fetch(src)
        except Exception as e:
            print(f"\n=== {src['id']}: ERROR {e}")
            continue
        print(f"\n=== {src['id']}: {len(items)} items")
        for it in sorted(items, key=lambda i: i.get("published_at") or "", reverse=True)[:12]:
            print(f"  {(it['published_at'] or '')[:10]} | {it['title'][:110]} | {it['summary'][:60]} | kw={match_keywords(it, kws)} | {it['url'][:90]}")
