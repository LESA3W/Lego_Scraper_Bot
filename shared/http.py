"""Lightweight HTTP helper with retry and rate-limit handling."""

import time
import requests


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Connection": "keep-alive",
}


def safe_get(url, timeout=20, retries=2):
    """GET with basic error handling and 429 backoff."""
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)

            if r.status_code == 429:
                time.sleep(60)
                continue

            r.raise_for_status()
            return r

        except Exception:
            if attempt == retries:
                return None
            time.sleep(3)

    return None
