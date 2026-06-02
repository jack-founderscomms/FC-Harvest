"""
GOV.UK Search API fetcher.
Docs: https://docs.publishing.service.gov.uk/repos/search-api/using-the-search-api.html
Base: https://www.gov.uk/api/search.json   (no auth, official, stable)

Valid filter params:
  filter_organisations             — org slug, e.g. "department-for-science-innovation-and-technology"
  filter_content_store_document_type — e.g. news_story, press_release, guidance, consultation,
                                       policy_paper, speech, written_statement, government_response
  order                            — "-public_timestamp" (newest first)
  count                            — max results (up to 1500)

NOTE: filter_content_purpose_supergroup and filter_document_type are NOT valid — they cause 422.
"""

from .base import polite_get

GOVUK_API_URL = "https://www.gov.uk/api/search.json"
GOVUK_BASE = "https://www.gov.uk"


def fetch(source_cfg: dict) -> list[dict]:
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
        params[key] = value
    return params
