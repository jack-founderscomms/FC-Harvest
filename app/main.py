"""
FC-Harvest web dashboard — FastAPI.

Routes:
  GET /              — main dashboard
  GET /api/items     — JSON items
  GET /api/health    — per-source health status
  POST /api/harvest  — trigger harvest in background
  GET /api/runs      — recent run history
  GET /api/sources   — source list + keywords
"""

import logging
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, Query, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from harvest import db as database
from harvest.runner import load_config, run_harvest
from harvest.scheduler import start_scheduler

logger = logging.getLogger(__name__)

app = FastAPI(title="FC-Harvest", version="1.0")

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

_scheduler = None


@app.on_event("startup")
def on_startup():
    global _scheduler
    database.init_db()
    try:
        _scheduler = start_scheduler()
    except Exception as e:
        logger.error("Could not start scheduler: %s", e)


@app.on_event("shutdown")
def on_shutdown():
    if _scheduler:
        _scheduler.shutdown(wait=False)


# ── HTML Dashboard ─────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    source: list[str] = Query(default=[]),
    keywords_only: bool = Query(default=False),
    limit: int = Query(default=200, le=1000),
    offset: int = Query(default=0),
):
    database.init_db()
    config = load_config()
    all_source_ids = _get_all_source_ids(config)
    label_map = _build_label_map(config)

    with database.get_db() as conn:
        items = database.get_items(
            conn,
            source_ids=source if source else None,
            keyword_filter=keywords_only,
            limit=limit,
            offset=offset,
        )
        recent_runs = database.get_recent_runs(conn, limit=5)
        source_health = database.get_source_health(conn)

    grouped: dict[str, list] = defaultdict(list)
    for item in items:
        grouped[item["source_id"]].append(item)

    ordered_groups = []
    seen_sources = set(grouped.keys())
    for sid in all_source_ids:
        if sid in seen_sources:
            ordered_groups.append({
                "source_id": sid,
                "label": label_map.get(sid, sid),
                "items": grouped[sid],
                "health": source_health.get(sid),
            })

    # Count keyword-matched items across all sources
    kw_counts: dict[str, int] = defaultdict(int)
    for item in items:
        for kw in (item.get("matched_kws") or []):
            kw_counts[kw] += 1
    top_keywords = sorted(kw_counts.items(), key=lambda x: -x[1])[:15]

    # Sources with errors (for health panel — include even if they have no items)
    errored_sources = []
    for sid in all_source_ids:
        h = source_health.get(sid)
        if h and h.get("status") == "error":
            errored_sources.append({
                "source_id": sid,
                "label": label_map.get(sid, sid),
                "message": h.get("message", ""),
                "checked_at": (h.get("checked_at") or "")[:16].replace("T", " "),
            })

    return templates.TemplateResponse("index.html", {
        "request": request,
        "groups": ordered_groups,
        "all_source_ids": all_source_ids,
        "label_map": label_map,
        "selected_sources": source,
        "keywords_only": keywords_only,
        "limit": limit,
        "offset": offset,
        "total_items": len(items),
        "recent_runs": recent_runs,
        "source_health": source_health,
        "errored_sources": errored_sources,
        "top_keywords": top_keywords,
        "keywords": config.get("keywords", []),
    })


# ── JSON API ───────────────────────────────────────────────────────────────

@app.get("/api/items")
def api_items(
    source: list[str] = Query(default=[]),
    keywords_only: bool = Query(default=False),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0),
):
    database.init_db()
    with database.get_db() as conn:
        items = database.get_items(
            conn,
            source_ids=source if source else None,
            keyword_filter=keywords_only,
            limit=limit,
            offset=offset,
        )
    return {"items": items, "count": len(items)}


@app.get("/api/health")
def api_health():
    database.init_db()
    with database.get_db() as conn:
        health = database.get_source_health(conn)
    return {"sources": health}


@app.post("/api/harvest")
def api_trigger_harvest(background_tasks: BackgroundTasks):
    background_tasks.add_task(_run_harvest_bg)
    return {"status": "harvest started"}


def _run_harvest_bg():
    try:
        result = run_harvest()
        logger.info("Manual harvest result: new=%d errors=%d", result["new_items"], len(result["errors"]))
    except Exception as e:
        logger.error("Manual harvest error: %s", e, exc_info=True)


@app.get("/api/runs")
def api_runs():
    database.init_db()
    with database.get_db() as conn:
        runs = database.get_recent_runs(conn, limit=20)
    return {"runs": runs}


@app.get("/api/sources")
def api_sources():
    config = load_config()
    return {
        "sources": _build_label_map(config),
        "keywords": config.get("keywords", []),
    }


# ── Helpers ────────────────────────────────────────────────────────────────

def _get_all_source_ids(config: dict) -> list[str]:
    return [src["id"] for group in config.get("sources", {}).values() for src in group]


def _build_label_map(config: dict) -> dict[str, str]:
    return {
        src["id"]: src.get("label", src["id"])
        for group in config.get("sources", {}).values()
        for src in group
    }
