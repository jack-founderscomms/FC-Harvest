"""Shared HTTP session with polite defaults."""

import time
import requests

# Single shared session reused across fetchers
_session: requests.Session | None = None

HEADERS = {
    "User-Agent": "FC-Harvest/1.0 (parliamentary monitoring tool; contact jack@founderscomms.co)",
    "Accept": "application/json, application/xml, text/html",
}

REQUEST_TIMEOUT = 20  # seconds
RATE_LIMIT_DELAY = 1.0  # seconds between requests to same host


def get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(HEADERS)
    return _session


def polite_get(url: str, params: dict | None = None, accept_json: bool = False) -> requests.Response:
    """GET with timeout, and a brief pause to be polite."""
    session = get_session()
    headers = {"Accept": "application/json"} if accept_json else {}
    time.sleep(RATE_LIMIT_DELAY)
    resp = session.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp
