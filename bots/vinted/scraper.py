"""Vinted scraper: hybrid Playwright (one-time token) + pure HTTP.

Vinted's public API is reachable with a short-lived bearer token. We launch
Playwright once at startup to grab the token + session cookie, cache them to
disk, and from then on all listing fetches are plain ``requests`` calls.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests


API_URL = "https://www.vinted.fr/api/v2/catalog/items"
TOKEN_FILE = Path(__file__).resolve().parent / "vinted_token.json"

_CACHED_TOKEN: Optional[str] = None
_SESSION_COOKIE: Optional[str] = None


def _save_token(token: str, session: str) -> None:
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump({"token": token, "session": session, "timestamp": time.time()}, f)


def _test_token(token: str, session: Optional[str]) -> bool:
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    cookies = {"_vinted_fr_session": session} if session else {}
    try:
        r = requests.get(
            API_URL,
            headers=headers,
            cookies=cookies,
            params={"search_text": "test", "per_page": 1, "page": 1},
            timeout=10,
        )
        return r.status_code == 200
    except Exception:
        return False


def init_session() -> bool:
    """Load a cached token or generate a fresh one via Playwright."""
    global _CACHED_TOKEN, _SESSION_COOKIE

    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            _CACHED_TOKEN = data.get("token")
            _SESSION_COOKIE = data.get("session")
            if _CACHED_TOKEN and _test_token(_CACHED_TOKEN, _SESSION_COOKIE):
                print("[INFO] Vinted token loaded from cache")
                return True
            print("[WARN] Cached Vinted token expired, regenerating")
        except Exception as e:
            print(f"[WARN] Could not load cached Vinted token: {e}")

    print("[INFO] Bootstrapping Vinted session with Playwright")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] Playwright is not installed. Run: pip install playwright && playwright install chromium")
        return False

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                locale="fr-FR",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            page.goto("https://www.vinted.fr", timeout=30000)
            page.wait_for_timeout(5000)

            cookies = context.cookies()
            cookie_dict = {c["name"]: c["value"] for c in cookies}
            _SESSION_COOKIE = cookie_dict.get("_vinted_fr_session")

            token = page.evaluate(
                """() => {
                    return localStorage.getItem('auth_token')
                        || localStorage.getItem('access_token')
                        || (window.VINTED && window.VINTED.auth && window.VINTED.auth.token);
                }"""
            )
            if not token:
                token = cookie_dict.get("access_token_web")

            browser.close()

            if token and _SESSION_COOKIE:
                _CACHED_TOKEN = token
                _save_token(token, _SESSION_COOKIE)
                print(f"[INFO] Vinted token acquired: {token[:20]}...")
                return True

            print("[ERROR] Could not extract Vinted token")
            return False

    except Exception as e:
        print(f"[ERROR] Playwright bootstrap failed: {e}")
        return False


def fetch_items(search_text: str, page: int = 1, limit: int = 20) -> List[Dict]:
    """Fetch a page of Vinted listings matching ``search_text``."""
    global _CACHED_TOKEN, _SESSION_COOKIE

    if not _CACHED_TOKEN and not init_session():
        print("[ERROR] No Vinted token available")
        return []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Accept-Language": "fr-FR,fr;q=0.9",
        "Authorization": f"Bearer {_CACHED_TOKEN}",
        "Referer": "https://www.vinted.fr/",
    }
    cookies = {"anonymous-locale": "fr"}
    if _SESSION_COOKIE:
        cookies["_vinted_fr_session"] = _SESSION_COOKIE

    params = {
        "search_text": search_text,
        "per_page": limit,
        "page": page,
        "order": "newest_first",
    }

    try:
        time.sleep(1.5)
        response = requests.get(API_URL, headers=headers, cookies=cookies, params=params, timeout=20)

        if response.status_code in (401, 403):
            print("[WARN] Vinted token expired, refreshing")
            _CACHED_TOKEN = None
            if TOKEN_FILE.exists():
                TOKEN_FILE.unlink()
            return fetch_items(search_text, page, limit)

        if response.status_code == 429:
            print("[WARN] Vinted rate limit, sleeping 5s")
            time.sleep(5)
            return fetch_items(search_text, page, limit)

        response.raise_for_status()
        data = response.json()

    except Exception as e:
        print(f"[ERROR] Vinted fetch failed: {e}")
        return []

    status_map = {
        "Neuf avec étiquette": "new_with_tags",
        "Neuf sans étiquette": "new_without_tags",
        "Très bon état": "very_good",
        "Bon état": "good",
        "Satisfaisant": "satisfactory",
    }

    items: List[Dict] = []
    for x in data.get("items", []):
        try:
            user = x.get("user", {})
            condition = status_map.get(x.get("status", ""), "unknown")
            items.append({
                "id": str(x["id"]),
                "title": x.get("title", ""),
                "description": x.get("description", ""),
                "price": float(x["price"]["amount"]),
                "condition": condition,
                "seller_name": user.get("login"),
                "seller_rating": user.get("feedback_reputation"),
                "seller_reviews": user.get("feedback_count"),
                "seller_url": (
                    f"https://www.vinted.fr/member/{user.get('id')}"
                    if user.get("id") else None
                ),
                "url": x.get("url"),
                "image": (x.get("photos") or [{}])[0].get("url", ""),
            })
        except Exception as e:
            print(f"[WARN] Could not parse Vinted item: {e}")
            continue

    return items
