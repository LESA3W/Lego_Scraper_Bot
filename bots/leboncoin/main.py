"""LeBonCoin bot entry point."""

from pathlib import Path

from shared.runner import run_loop
from bots.leboncoin.scraper import get_browser


BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent.parent

CONFIG_PATH = BASE_DIR / "config.yaml"
LEGOS_PATH = REPO_ROOT / "data" / "legos.json"
SEEN_PATH = BASE_DIR / "seen.json"
STATS_PATH = BASE_DIR / "stats.json"


def main() -> None:
    browser = get_browser()

    def fetch_items(search_text: str, page_num: int) -> list:
        return browser.fetch_items(search_text, page_num=page_num)

    def enrich_item(item: dict) -> None:
        details = browser.fetch_item_details(item.get("url", ""))
        if not details:
            return
        item["seller_url"] = details.get("seller_url")
        item["condition"] = details.get("condition", "N/A")
        item["seller_rating"] = details.get("seller_rating")
        item["seller_reviews"] = details.get("seller_reviews")
        if details.get("description"):
            item["description"] = details["description"]

    def on_start() -> None:
        if not browser.init():
            raise RuntimeError("Failed to initialize LeBonCoin browser")

    def on_shutdown() -> None:
        if browser.is_initialized:
            browser.close()

    run_loop(
        platform="leboncoin",
        config_path=CONFIG_PATH,
        legos_path=LEGOS_PATH,
        seen_path=SEEN_PATH,
        stats_path=STATS_PATH,
        fetch_items=fetch_items,
        enrich_item=enrich_item,
        on_start=on_start,
        on_shutdown=on_shutdown,
    )


if __name__ == "__main__":
    main()
