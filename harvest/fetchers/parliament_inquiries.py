"""
Committee Inquiries (all committees) — newly opened inquiries and other committee
business, from the official Committees API (/api/CommitteeBusiness).

This replaced an HTML scrape of committees.parliament.uk/inquiries/, which now
serves a Cloudflare challenge (HTTP 403) to automated clients.
"""

from .parliament_committees_api import _fetch_new_business


def fetch(source_cfg: dict) -> list[dict]:
    return _fetch_new_business(committee_id=None, take=int(source_cfg.get("count", 50)))
