"""Vinted bot entry point."""

from pathlib import Path

from shared.runner import run_loop
from bots.vinted import scraper


BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent.parent

CONFIG_PATH = BASE_DIR / "config.yaml"
LEGOS_PATH = REPO_ROOT / "data" / "legos.json"
SEEN_PATH = BASE_DIR / "seen.json"
STATS_PATH = BASE_DIR / "stats.json"


def main() -> None:
    run_loop(
        platform="vinted",
        config_path=CONFIG_PATH,
        legos_path=LEGOS_PATH,
        seen_path=SEEN_PATH,
        stats_path=STATS_PATH,
        fetch_items=scraper.fetch_items,
    )


if __name__ == "__main__":
    main()
