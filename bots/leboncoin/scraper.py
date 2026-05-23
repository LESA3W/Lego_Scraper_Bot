"""LeBonCoin scraper with persistent Playwright browser + auto-CAPTCHA solver.

LeBonCoin has no public API and ships an aggressive Datadome challenge. We
keep one Chromium instance alive across cycles, solve the slider CAPTCHA on
demand, and parse listings out of the embedded ``__NEXT_DATA__`` JSON blob.

The ``pyautogui`` import is Windows-only (used to minimize the visible browser
window). On other platforms the minimize step is silently skipped.
"""

import json
import random
import re
import time
from typing import Dict, List, Optional

try:
    import pyautogui
    _PYAUTOGUI_AVAILABLE = True
except Exception:
    _PYAUTOGUI_AVAILABLE = False

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright


CAPTCHA_MARKER = "On s'assure"


class LeBonCoinBrowser:
    """Persistent Chromium session for LeBonCoin scraping."""

    def __init__(self) -> None:
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_initialized = False
        self.captcha_solved = False

    def minimize_window(self) -> None:
        """Minimize the browser window (Windows only). No-op elsewhere."""
        if not _PYAUTOGUI_AVAILABLE:
            return
        try:
            time.sleep(0.5)
            pyautogui.hotkey("win", "down")
            time.sleep(0.5)
        except Exception as e:
            print(f"[WARN] Could not minimize browser window: {e}")

    def auto_accept_cookies(self) -> bool:
        cookie_selectors = [
            "button:has-text('Accepter')",
            "button:has-text('Tout accepter')",
            "[data-qa-id='cookies-accept-all']",
        ]
        for selector in cookie_selectors:
            try:
                button = self.page.locator(selector).first
                if button.is_visible(timeout=3000):
                    button.click()
                    time.sleep(1)
                    return True
            except Exception:
                continue
        return True

    def auto_solve_slider_captcha(self) -> bool:
        """Solve the Datadome slider CAPTCHA. Falls back to manual wait if not found."""
        try:
            time.sleep(2)
            if CAPTCHA_MARKER not in self.page.content() and "DataDome" not in self.page.content():
                return True

            print("[INFO] CAPTCHA detected, attempting to solve")
            iframe_selector = (
                "iframe[src*='captcha'], iframe[src*='datadome'], iframe[title*='DataDome']"
            )

            try:
                self.page.wait_for_selector(iframe_selector, timeout=5000)
                iframe_element = self.page.frame_locator(iframe_selector).first

                slider_selectors = [
                    "[class*='slider']",
                    "[class*='captcha-puzzle']",
                    "div[role='slider']",
                    "button[aria-label*='slide']",
                    "[id*='slider']",
                    ".slide-button",
                ]

                for selector in slider_selectors:
                    try:
                        slider = iframe_element.locator(selector).first
                        if not slider.is_visible(timeout=2000):
                            continue

                        box = slider.bounding_box()
                        if not box:
                            continue

                        start_x = box["x"] + 10
                        start_y = box["y"] + box["height"] / 2
                        end_x = start_x + 280

                        self.page.mouse.move(start_x, start_y)
                        time.sleep(random.uniform(0.1, 0.3))
                        self.page.mouse.down()
                        time.sleep(random.uniform(0.05, 0.15))

                        steps = 25
                        for i in range(steps):
                            progress = (i + 1) / steps
                            eased = progress * progress * (3 - 2 * progress)
                            current_x = start_x + (end_x - start_x) * eased
                            jitter_y = random.uniform(-2, 2)
                            self.page.mouse.move(current_x, start_y + jitter_y)
                            time.sleep(random.uniform(0.015, 0.035))

                        self.page.mouse.up()
                        time.sleep(4)

                        if CAPTCHA_MARKER not in self.page.content():
                            print("[INFO] CAPTCHA solved")
                            self.captcha_solved = True
                        return True
                    except Exception:
                        continue

                print("[WARN] Slider not found, waiting 10s for manual resolution")
                time.sleep(10)
                return True

            except Exception as e:
                print(f"[WARN] Could not access CAPTCHA iframe: {e}; waiting 10s")
                time.sleep(10)
                return True

        except Exception as e:
            print(f"[ERROR] CAPTCHA solving error: {e}")
            return True

    def init(self) -> bool:
        """Launch the persistent browser. Returns False on failure."""
        if self.is_initialized:
            return True

        try:
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ],
            )
            self.context = self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                locale="fr-FR",
                timezone_id="Europe/Paris",
                geolocation={"latitude": 48.8566, "longitude": 2.3522},
            )
            self.context.add_init_script(
                """
                Object.defineProperty(navigator, 'webdriver', {get: () => false});
                window.chrome = {runtime: {}};
                """
            )
            self.page = self.context.new_page()
            self.page.goto("https://www.leboncoin.fr", wait_until="load", timeout=30000)

            self.minimize_window()
            time.sleep(1)
            self.auto_accept_cookies()
            time.sleep(1)
            self.auto_solve_slider_captcha()

            self.is_initialized = True
            print("[INFO] LeBonCoin browser ready")
            return True

        except Exception as e:
            print(f"[ERROR] Browser init failed: {e}")
            return False

    def fetch_item_details(self, item_url: str) -> Optional[Dict]:
        """Load a single ad page and extract seller/condition/description."""
        try:
            self.page.goto(item_url, wait_until="load", timeout=20000)
            time.sleep(3)

            if CAPTCHA_MARKER in self.page.content():
                self.auto_solve_slider_captcha()
                time.sleep(2)

            next_data_match = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                self.page.content(),
                re.DOTALL,
            )
            if not next_data_match:
                return None

            json_data = json.loads(next_data_match.group(1))
            page_props = json_data.get("props", {}).get("pageProps", {})

            ad_data = None
            if "ad" in page_props:
                ad_data = page_props["ad"]
            elif "adView" in page_props:
                ad_data = page_props["adView"]
            elif "searchData" in page_props:
                ads = page_props["searchData"].get("ads", [])
                if ads:
                    ad_data = ads[0]

            if not ad_data:
                return None

            description = ad_data.get("body", "") or ad_data.get("description", "")

            seller_url: Optional[str] = None
            owner = ad_data.get("owner", {})
            user_id = owner.get("user_id")
            store_id = owner.get("store_id")
            if user_id:
                seller_url = f"https://www.leboncoin.fr/profile/{user_id}/offers"
            elif store_id:
                seller_url = f"https://www.leboncoin.fr/profile/{store_id}/offers"

            seller_rating: Optional[float] = None
            seller_reviews: Optional[int] = None

            attributes = ad_data.get("attributes", [])
            for attr in attributes:
                key = attr.get("key", "")
                value = attr.get("value", "")
                if key == "rating_score":
                    try:
                        seller_rating = round(float(value) * 5, 1)
                    except Exception:
                        pass
                elif key == "rating_count":
                    try:
                        seller_reviews = int(value)
                    except Exception:
                        pass

            if seller_rating is None or seller_reviews is None:
                rating_data = owner.get("rating", {})
                if rating_data:
                    if seller_rating is None and rating_data.get("rate"):
                        try:
                            seller_rating = round(float(rating_data["rate"]) * 5, 1)
                        except Exception:
                            pass
                    if seller_reviews is None and rating_data.get("count") is not None:
                        seller_reviews = rating_data["count"]

            # LBC condition values are stored as keys; map them back to human strings.
            # Strings stay French because they're matched against the French config.
            condition = "N/A"
            condition_map = {
                "etatneuf": "État neuf",
                "tresbonetat": "Très bon état",
                "bonetat": "Bon état",
                "etatsatisfaisant": "État satisfaisant",
            }
            for attr in attributes:
                if attr.get("key") == "condition":
                    raw_value = attr.get("value", "")
                    condition = condition_map.get(raw_value, raw_value.title())
                    break

            return {
                "seller_url": seller_url,
                "seller_rating": seller_rating,
                "seller_reviews": seller_reviews,
                "condition": condition,
                "description": description,
            }

        except Exception as e:
            print(f"[ERROR] Could not fetch item details: {e}")
            return None

    def fetch_items(self, search_text: str, page_num: int = 1, limit: int = 35) -> List[Dict]:
        """Fetch a search results page; fetches per-ad details only when needed."""
        if not self.is_initialized:
            print("[ERROR] Browser not initialized")
            return []

        items: List[Dict] = []

        try:
            search_url = (
                "https://www.leboncoin.fr/recherche"
                f"?category=41&text={search_text.replace(' ', '%20')}"
                f"&shippable=1&item_condition=1&sort=time&order=desc&page={page_num}"
            )
            self.page.goto(search_url, wait_until="load", timeout=30000)
            time.sleep(3)

            if CAPTCHA_MARKER in self.page.content():
                self.auto_solve_slider_captcha()
                time.sleep(2)

            for _ in range(3):
                self.page.evaluate("window.scrollBy(0, window.innerHeight / 3)")
                time.sleep(0.5)
            time.sleep(2)

            next_data_match = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                self.page.content(),
                re.DOTALL,
            )
            if not next_data_match:
                print("[WARN] No __NEXT_DATA__ found on search page")
                return items

            json_data = json.loads(next_data_match.group(1))
            ads = (
                json_data.get("props", {})
                .get("pageProps", {})
                .get("searchData", {})
                .get("ads", [])
            )

            for ad in ads[:limit]:
                try:
                    item_id = str(ad.get("list_id", ""))
                    title = ad.get("subject", "")
                    lego_ids_in_title = set(re.findall(r"\b\d{4,7}\b", title))
                    description = ad.get("body", "") or ad.get("description", "")

                    # Only burn a per-ad page load when there's no chance of matching from the search payload.
                    if not lego_ids_in_title and not description:
                        url = ad.get("url", f"https://www.leboncoin.fr/{item_id}.htm")
                        details = self.fetch_item_details(url)
                        if details:
                            description = details.get("description", "")

                    price_data = ad.get("price", [0])
                    price = float(price_data[0]) if isinstance(price_data, list) and price_data else 0.0

                    images = ad.get("images", {}).get("urls", [])
                    image_url = images[0] if images else ""

                    location = ad.get("location", {})
                    owner = ad.get("owner", {})

                    items.append({
                        "id": item_id,
                        "title": title,
                        "description": description,
                        "price": price,
                        "condition": "N/A",
                        "city": location.get("city", "N/A"),
                        "region": location.get("region_name", "N/A"),
                        "seller_name": owner.get("name", "Unknown"),
                        "seller_type": owner.get("type", ""),
                        "seller_rating": None,
                        "seller_reviews": None,
                        "seller_url": None,
                        "url": ad.get("url", f"https://www.leboncoin.fr/{item_id}.htm"),
                        "image": image_url,
                        "published_date": ad.get("index_date", ""),
                    })

                except Exception as e:
                    print(f"[WARN] Could not parse ad: {e}")
                    continue

        except Exception as e:
            print(f"[ERROR] Search fetch failed: {e}")

        return items

    def close(self) -> None:
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        self.is_initialized = False


_browser_instance: Optional[LeBonCoinBrowser] = None


def get_browser() -> LeBonCoinBrowser:
    global _browser_instance
    if _browser_instance is None:
        _browser_instance = LeBonCoinBrowser()
    return _browser_instance
