"""Shared scan loop for both bots.

Each bot supplies its own ``fetch_items`` callable (page -> list of dicts).
Optionally, a ``enrich_item`` callable can fetch per-listing details (used by
LeBonCoin to load condition + seller rating from each ad page).
"""

import json
import random
import time
from pathlib import Path
from typing import Callable, Optional

import yaml

from shared.analyzer import analyze_item
from shared.logger import log, success, warning, error, info
from shared.notifier import send_accepted_alert, send_rejected_alert


def load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def polite_sleep(base_seconds: int, jitter_seconds: int) -> None:
    delay = base_seconds + random.randint(0, max(0, jitter_seconds))
    time.sleep(delay)


def init_stats() -> dict:
    return {
        "total_scanned": 0,
        "total_sent": 0,
        "rejected_by_filter": {},
        "price_drops_detected": 0,
        "last_run": None,
        "runtime_stats": {"cycles": 0, "deep_scans": 0, "errors": 0},
    }


def update_stats(stats: dict, rejected_by: Optional[str] = None, sent: bool = False) -> None:
    stats["total_scanned"] += 1
    if sent:
        stats["total_sent"] += 1
    if rejected_by:
        stats["rejected_by_filter"][rejected_by] = (
            stats["rejected_by_filter"].get(rejected_by, 0) + 1
        )


def run_loop(
    *,
    platform: str,
    config_path: Path,
    legos_path: Path,
    seen_path: Path,
    stats_path: Path,
    fetch_items: Callable[[str, int], list],
    enrich_item: Optional[Callable[[dict], None]] = None,
    on_start: Optional[Callable[[], None]] = None,
    on_shutdown: Optional[Callable[[], None]] = None,
) -> None:
    """Run the polite-polling scan loop for one platform.

    Args:
        platform: ``"leboncoin"`` or ``"vinted"``; selects config section + notifier styling.
        config_path: Path to the bot's ``config.yaml``.
        legos_path: Path to the reference Lego DB.
        seen_path: Where to persist per-listing last-seen prices.
        stats_path: Where to persist cycle counters.
        fetch_items: ``(search_text, page_num) -> list[dict]`` for this platform.
        enrich_item: Optional in-place mutator that loads extra fields (seller, condition).
        on_start: Optional setup hook (e.g. open browser).
        on_shutdown: Optional teardown hook (e.g. close browser).
    """
    config = load_yaml(config_path)
    legos = load_json(legos_path)
    seen = load_json(seen_path)
    stats = load_json(stats_path) or init_stats()

    seen.setdefault(platform, {})
    if isinstance(seen[platform], list):
        warning("Migrating seen.json from list -> dict (price-aware)")
        seen[platform] = {}
        save_json(seen_path, seen)

    base_delay = int(config["global"]["loop_delay"])
    jitter = int(config["global"].get("jitter", 0))
    backoff_start = int(config["global"].get("backoff_start", 30))
    backoff_max = int(config["global"].get("backoff_max", 600))
    backoff = backoff_start

    platform_cfg = config[platform]
    deep_every = int(platform_cfg.get("deep_scan_every", 10))
    deep_jitter = int(platform_cfg.get("deep_scan_jitter", 0))
    deep_pages = platform_cfg.get("deep_pages", [2, 3])

    cycle_count = 0
    next_deep_scan = deep_every + random.randint(-deep_jitter, deep_jitter)

    log(f"Lego Scraper [{platform}] started")
    log(f"Filter priority: {' -> '.join(config['filters']['priority'])}")

    if on_start:
        on_start()

    try:
        while True:
            try:
                if not platform_cfg.get("enabled", True):
                    polite_sleep(base_delay, jitter)
                    continue

                cycle_count += 1
                stats["runtime_stats"]["cycles"] += 1
                do_deep_scan = cycle_count >= next_deep_scan

                pages_to_scan = [1]
                if do_deep_scan:
                    pages_to_scan += list(deep_pages)
                    stats["runtime_stats"]["deep_scans"] += 1
                    log(f"DEEP SCAN #{stats['runtime_stats']['deep_scans']} - Cycle #{cycle_count}")
                    log(f"Pages to scan: {pages_to_scan}")
                    next_deep_scan = (
                        cycle_count + deep_every + random.randint(-deep_jitter, deep_jitter)
                    )
                else:
                    log(f"NORMAL SCAN - Cycle #{cycle_count}")
                    log(f"Next deep scan in {next_deep_scan - cycle_count} cycles")

                for page in pages_to_scan:
                    items = fetch_items(platform_cfg["search_text"], page)
                    if not isinstance(items, list):
                        warning("fetch_items did not return a list - skipping")
                        continue

                    log(f"Fetched {len(items)} items from page {page}")

                    for item in items:
                        if not isinstance(item, dict):
                            continue

                        item_id = item.get("id")
                        price = item.get("price")
                        title = item.get("title", "N/A")

                        if not item_id or price is None:
                            continue

                        last_seen_price = seen[platform].get(item_id)
                        if last_seen_price is not None and price >= last_seen_price:
                            continue

                        if last_seen_price is not None and price < last_seen_price:
                            stats["price_drops_detected"] += 1
                            log(
                                f"PRICE DROP #{stats['price_drops_detected']} -> "
                                f"{item_id}: {last_seen_price} EUR -> {price} EUR"
                            )

                        if enrich_item:
                            enrich_item(item)

                        decision, rejected_by = analyze_item(item, legos, config, platform)
                        update_stats(stats, rejected_by=rejected_by, sent=(decision is not None))

                        if decision:
                            success(f"ACCEPTED [{item_id}] {title[:50]}... -> {price} EUR")
                            send_accepted_alert(
                                webhook_url=platform_cfg["webhook"],
                                item=item,
                                decision=decision,
                                platform=platform,
                            )
                        else:
                            rejected_cfg = platform_cfg.get("rejected_items", {})
                            if rejected_cfg.get("log_console", True):
                                log(f"REJECTED [{item_id}] {title[:50]}... | reason: {rejected_by}")
                            if rejected_cfg.get("send_discord", True):
                                send_rejected_alert(
                                    webhook_url=platform_cfg["webhook_reject"],
                                    item=item,
                                    rejected_by=rejected_by,
                                    platform=platform,
                                )

                        seen[platform][item_id] = price
                        save_json(seen_path, seen)

                stats["last_run"] = time.strftime("%Y-%m-%d %H:%M:%S")
                save_json(stats_path, stats)

                backoff = backoff_start

                if cycle_count % 10 == 0:
                    info(
                        f"STATS CHECKPOINT (cycle {cycle_count}) | "
                        f"scanned={stats['total_scanned']} sent={stats['total_sent']} "
                        f"drops={stats['price_drops_detected']} "
                        f"rejections={stats['rejected_by_filter']}"
                    )

            except Exception as e:
                error(f"Cycle error: {e}")
                import traceback
                traceback.print_exc()
                stats["runtime_stats"]["errors"] += 1
                warning(f"Backoff: sleeping {backoff}s (error #{stats['runtime_stats']['errors']})")
                time.sleep(backoff)
                backoff = min(backoff * 2, backoff_max)
                continue

            polite_sleep(base_delay, jitter)

    finally:
        if on_shutdown:
            on_shutdown()
