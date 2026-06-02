"""
GOV.UK Search API fetcher.
API docs: https://github.com/alphagov/search-api/blob/main/docs/search-api.md
Base URL: https://www.gov.uk/api/search.json

No auth required. Official API, stable.

Valid filter fields: filter_organisations, filter_document_type, filter_world_locations, etc.
NOTE: filter_content_purpose_supergroup is NOT a valid parameter — use filter_document_type.

Useful document types: news_story, press_release, guidance, consultation, policy_paper,
speech, written_statement, government_response, statistical_data_set, transparency
"""

from .base import polite_get

GOVUK_API_URL = "https://www.gov.uk/api/search.json"
GOVUK_BASE = "https://www.gov.uk"


def fetch(source_cfg: dict) -> list[dict]:
    """
    Fetch items from GOV.UK Search API for a single source config entry.
    Returns list of normalised item dicts.
    """
    params = _build_params(source_cfg["params"])
    resp = polite_get(GOVUK_API_URL, params=params, accept_json=True)
    data = resp.json()

    items = []
    for result in data.get("results", []):
        link = result.get("link", "")
        item = {
            "item_id": link,
            "title": result.get("title", "").strip(),
            "url": GOVUK_BASE + link if link.startswith("/") else link,
            "published_at": result.get("public_timestamp"),
            "summary": (result.get("description") or "").strip(),
            "matched_kws": [],
        }
        if item["title"]:
            items.append(item)
    return items


def _build_params(cfg_params: dict) -> dict:
    params: dict[str, object] = {}
    for key, value in cfg_params.items():
        if isinstance(value, list):
            params[key] = value
        else:
            params[key] = value
    return params
