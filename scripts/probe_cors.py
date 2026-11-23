import requests
O = {"Origin": "https://htmlpreview.github.io", "User-Agent": "Mozilla/5.0"}
API = "https://committees-api.parliament.uk/api"
for url in [f"{API}/Committees?CommitteeStatus=Current&Take=500",
            f"{API}/Publications?CommitteeId=365&Take=2&SortOrder=PublicationDateDescending",
            f"{API}/CommitteeBusiness?CommitteeId=365&Take=2&SortOrder=DateOpenedNewest",
            f"{API}/Committees/365/Events?StartDateFrom=2026-11-16&Take=3",
            f"{API}/Committees?house=Commons&currentCommitteesOnly=true",
            "https://news.google.com/rss/search?q=site:committees.parliament.uk/committee/365&hl=en-GB&gl=GB&ceid=GB:en",
            "https://raw.githubusercontent.com/jack-founderscomms/FC-Harvest/main/README.md"]:
    try:
        r = requests.get(url, headers=O, timeout=60)
        print(r.status_code, "ACAO=", r.headers.get("access-control-allow-origin"), url)
        if "Events" in url or "currentCommitteesOnly" in url:
            j = r.json(); items = j.get("items", j) if isinstance(j, dict) else j
            print("  total:", j.get("totalResults") if isinstance(j, dict) else len(j), "| n:", len(items))
            if "Events" in url and items: 
                e = items[0]; print("  keys:", sorted(e.keys())); print("  ", {k: e.get(k) for k in ("id","name","startDate","eventType","location")})
                for a in (e.get("activities") or [])[:2]: print("  act:", {k: a.get(k) for k in a if k in ("title","startDate","attendees","businesses")})
    except Exception as ex:
        print("EXC", url, ex)
