"""
Harvest runner — iterates all configured sources, fetches, filters, stores.
Failures on individual sources are recorded in source_health and reported
in the dashboard, but never stop the rest of the harvest.
"""

import logging
import yaml
from pathlib import Path

from . import db as database
from .filters import match_keywords
from .fetchers import (
    govuk,
    parliament_rss,
    parliament_written_statements,
    hansard,
    parliament_inquiries,
    parliament_committee_news,
    parliament_committees_api,
    whatson_scrape,
)

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

FETCHER_MAP = {
    "govuk_api": govuk,
    "parliament_rss": parliament_rss,
    "parliament_committee_news": parliament_committee_news,
    "parliament_committees_api": parliament_committees_api,
    "parliament_written_statements_api": parliament_written_statements,
    "hansard_api": hansard,
    "parliament_inquiries_scrape": parliament_inquiries,
    "whatson_scrape": whatson_scrape,
}


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _flatten_keywords(config: dict) -> list[str]:
    """Return a deduplicated flat keyword list from keyword_categories (or legacy keywords)."""
    cats = config.get("keyword_categories")
    if cats:
        seen: set[str] = set()
        result: list[str] = []
        for kws in cats.values():
            for kw in kws:
                if kw not in seen:
                    seen.add(kw)
                    result.append(kw)
        return result
    return config.get("keywords", [])


def run_harvest(config: dict | None = None) -> dict:
    """
    Run a full harvest. Individual source failures are isolated — they are
    recorded in source_health and included in the return value, but the
    harvest always continues to the next source.
    Returns: {new_items, errors: [{source_id, message}], run_id}
    """
    if config is None:
        config = load_config()

    keywords = _flatten_keywords(config)
    sources_cfg = config.get("sources", {})

    database.init_db()

    errors: list[dict] = []
    total_new = 0

    with database.get_db() as conn:
        run_id = database.log_run_start(conn)

    all_sources: list[dict] = []
    for group_name, group_sources in sources_cfg.items():
        for src in group_sources:
            src = dict(src)
            src["_group"] = group_name
            all_sources.append(src)

    for src in all_sources:
        source_id = src.get("id", src.get("label", "unknown"))
        source_type = src.get("type")
        fetcher = FETCHER_MAP.get(source_type)

        if not fetcher:
            msg = f"Unknown fetcher type '{source_type}'"
            errors.append({"source_id": source_id, "message": msg})
            with database.get_db() as conn:
                database.record_source_health(conn, source_id, "error", msg)
            continue

        try:
            logger.info("Fetching %s (%s)...", source_id, source_type)
            raw_items = fetcher.fetch(src)
            logger.info("  → %d items fetched", len(raw_items))
        except Exception as exc:
            msg = _friendly_error(exc)
            errors.append({"source_id": source_id, "message": msg})
            logger.error("Error fetching '%s': %s", source_id, exc, exc_info=True)
            with database.get_db() as conn:
                database.record_source_health(conn, source_id, "error", msg)
            continue  # always continue to next source

        new_count = 0
        with database.get_db() as conn:
            for item in raw_items:
                item["matched_kws"] = match_keywords(item, keywords)
                is_new = database.upsert_item(conn, source_id, item)
                if is_new:
                    new_count += 1

            status = "ok" if raw_items else "warning"
            health_msg = "" if raw_items else "Fetched successfully but returned 0 items"
            database.record_source_health(conn, source_id, status, health_msg, len(raw_items))

        logger.info("  → %d new items stored", new_count)
        total_new += new_count

    error_strings = [f"{e['source_id']}: {e['message']}" for e in errors]
    with database.get_db() as conn:
        database.log_run_finish(conn, run_id, total_new, error_strings)

    summary = {"new_items": total_new, "errors": errors, "run_id": run_id}
    logger.info("Harvest complete. New items: %d, Errors: %d", total_new, len(errors))
    return summary


def _friendly_error(exc: Exception) -> str:
    """Turn a raw exception into a short human-readable status message."""
    msg = str(exc)
    if "403" in msg:
        return "403 Forbidden — server is blocking this IP/user-agent"
    if "404" in msg:
        return "404 Not Found — URL has changed or been removed"
    if "422" in msg:
        return "422 Unprocessable — API rejected a query parameter"
    if "NameResolutionError" in msg or "Name or service not known" in msg:
        return "DNS failure — domain does not exist or is unreachable"
    if "ConnectionError" in msg or "Max retries" in msg:
        return "Connection failed — server unreachable"
    if "Timeout" in msg or "timed out" in msg.lower():
        return "Request timed out"
    if "Could not find committee" in msg:
        return msg  # already friendly from committee fetcher
    return msg[:120]
