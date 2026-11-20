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


def polite_get(
    url: str,
    params: dict | None = None,
    accept_json: bool = False,
    timeout: float = REQUEST_TIMEOUT,
    retries: int = 0,
) -> requests.Response:
    """GET with timeout, and a brief pause to be polite. Retries only on timeouts."""
    session = get_session()
    headers = {"Accept": "application/json"} if accept_json else {}
    for attempt in range(retries + 1):
        time.sleep(RATE_LIMIT_DELAY * (attempt + 1))
        try:
            resp = session.get(url, params=params, headers=headers, timeout=timeout)
        except requests.Timeout:
            if attempt == retries:
                raise
            continue
        resp.raise_for_status()
        return resp
