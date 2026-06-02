"""
Harvest runner — iterates all configured sources, fetches, filters, stores.
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
    whatson_scrape,
)

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

# Map type strings from config to fetcher modules
FETCHER_MAP = {
    "govuk_api": govuk,
    "parliament_rss": parliament_rss,
    "parliament_committee_news": parliament_committee_news,
    "parliament_written_statements_api": parliament_written_statements,
    "hansard_api": hansard,
    "parliament_inquiries_scrape": parliament_inquiries,
    "whatson_scrape": whatson_scrape,
}


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def run_harvest(config: dict | None = None) -> dict:
    """
    Execute a full harvest across all configured sources.
    Returns a summary dict: {new_items, errors, run_id}.
    """
    if config is None:
        config = load_config()

    keywords = config.get("keywords", [])
    sources_cfg = config.get("sources", {})

    database.init_db()

    errors: list[str] = []
    total_new = 0

    with database.get_db() as conn:
        run_id = database.log_run_start(conn)

    # Collect all source entries as flat list
    all_sources: list[dict] = []
    for group_name, group_sources in sources_cfg.items():
        for src in group_sources:
            src = dict(src)  # copy
            src["_group"] = group_name
            all_sources.append(src)

    for src in all_sources:
        source_id = src.get("id", src.get("label", "unknown"))
        source_type = src.get("type")
        fetcher = FETCHER_MAP.get(source_type)

        if not fetcher:
            errors.append(f"Unknown fetcher type '{source_type}' for source '{source_id}'")
            logger.warning("Unknown fetcher type '%s' for source '%s'", source_type, source_id)
            continue

        try:
            logger.info("Fetching %s (%s)...", source_id, source_type)
            raw_items = fetcher.fetch(src)
            logger.info("  → %d items fetched", len(raw_items))
        except Exception as exc:
            msg = f"Error fetching '{source_id}': {exc}"
            errors.append(msg)
            logger.error(msg, exc_info=True)
            continue

        new_count = 0
        with database.get_db() as conn:
            for item in raw_items:
                item["matched_kws"] = match_keywords(item, keywords)
                is_new = database.upsert_item(conn, source_id, item)
                if is_new:
                    new_count += 1

        logger.info("  → %d new items stored", new_count)
        total_new += new_count

    with database.get_db() as conn:
        database.log_run_finish(conn, run_id, total_new, errors)

    summary = {"new_items": total_new, "errors": errors, "run_id": run_id}
    logger.info("Harvest complete. New items: %d, Errors: %d", total_new, len(errors))
    return summary
