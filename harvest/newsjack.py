"""
Newsjack client configuration.

Loads/saves newsjack.yaml (client roster + skill settings) and matches
harvested items to each client's watch keywords so the dashboards can show
per-client newsjack opportunities.
"""

import re
import yaml
from datetime import datetime, timedelta, timezone
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent / "newsjack.yaml"

DEFAULT_SETTINGS = {
    "max_age_days": 7,
    "max_items_per_client": 15,
    "tone": "",
    "output_format": "",
}


def load_newsjack() -> dict:
    if not CONFIG_PATH.exists():
        return {"settings": dict(DEFAULT_SETTINGS), "clients": []}
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f) or {}
    settings = dict(DEFAULT_SETTINGS)
    settings.update(cfg.get("settings") or {})
    clients = [_normalise_client(c) for c in (cfg.get("clients") or [])]
    return {"settings": settings, "clients": clients}


def save_newsjack(cfg: dict):
    header = (
        "# FC-Harvest — Newsjack skill configuration\n"
        "# Edit by hand or via the dashboard 'Newsjack clients' panel\n"
        "# (dashboard saves rewrite this file).\n"
        "# The skill can also fetch config + live matches from GET /api/newsjack\n"
    )
    body = yaml.safe_dump(
        {"settings": cfg.get("settings", {}), "clients": cfg.get("clients", [])},
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    CONFIG_PATH.write_text(header + body, encoding="utf-8")


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "client"


def upsert_client(data: dict) -> dict:
    """Create or update a client. Returns the saved client dict.

    Raises ValueError on invalid input.
    """
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("Client name is required")

    client = _normalise_client({
        "id": (data.get("id") or "").strip() or slugify(name),
        "name": name,
        "sector": (data.get("sector") or "").strip(),
        "enabled": bool(data.get("enabled", True)),
        "keywords": data.get("keywords") or [],
        "spokespeople": data.get("spokespeople") or [],
        "notes": (data.get("notes") or "").strip(),
    })

    cfg = load_newsjack()
    clients = cfg["clients"]
    for i, existing in enumerate(clients):
        if existing["id"] == client["id"]:
            clients[i] = client
            break
    else:
        clients.append(client)
    save_newsjack(cfg)
    return client


def delete_client(client_id: str) -> bool:
    cfg = load_newsjack()
    before = len(cfg["clients"])
    cfg["clients"] = [c for c in cfg["clients"] if c["id"] != client_id]
    if len(cfg["clients"]) == before:
        return False
    save_newsjack(cfg)
    return True


def match_items_to_clients(items: list[dict], cfg: dict) -> dict[str, list[dict]]:
    """Return {client_id: [matched items]} for enabled clients.

    An item matches when any client keyword appears (word-boundary,
    case-insensitive) in its title or summary, and the item is younger than
    settings.max_age_days. Each returned item carries the client keywords it
    hit under 'client_kws'.
    """
    settings = cfg.get("settings", {})
    max_age_days = int(settings.get("max_age_days") or DEFAULT_SETTINGS["max_age_days"])
    per_client_cap = int(
        settings.get("max_items_per_client") or DEFAULT_SETTINGS["max_items_per_client"]
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    fresh = [i for i in items if _is_fresh(i, cutoff)]

    matches: dict[str, list[dict]] = {}
    for client in cfg.get("clients", []):
        if not client.get("enabled"):
            continue
        patterns = [
            (kw, re.compile(r"\b" + re.escape(kw) + r"\b", re.IGNORECASE))
            for kw in client.get("keywords", [])
        ]
        if not patterns:
            matches[client["id"]] = []
            continue
        hits = []
        for item in fresh:
            text = " ".join(filter(None, [item.get("title", ""), item.get("summary", "")]))
            hit_kws = [kw for kw, pat in patterns if pat.search(text)]
            if hit_kws:
                hits.append({**item, "client_kws": hit_kws})
            if len(hits) >= per_client_cap:
                break
        matches[client["id"]] = hits
    return matches


def _normalise_client(c: dict) -> dict:
    spokespeople = []
    for sp in c.get("spokespeople") or []:
        if isinstance(sp, str):
            sp = {"name": sp}
        spokespeople.append({
            "name": (sp.get("name") or "").strip(),
            "title": (sp.get("title") or "").strip(),
            "expertise": (sp.get("expertise") or "").strip(),
        })
    keywords = [str(k).strip() for k in (c.get("keywords") or []) if str(k).strip()]
    return {
        "id": c.get("id") or slugify(c.get("name", "")),
        "name": c.get("name", ""),
        "sector": c.get("sector", "") or "",
        "enabled": bool(c.get("enabled", True)),
        "keywords": keywords,
        "spokespeople": spokespeople,
        "notes": c.get("notes", "") or "",
    }


def _is_fresh(item: dict, cutoff: datetime) -> bool:
    ts = item.get("published_at") or item.get("fetched_at")
    if not ts:
        return False
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= cutoff
