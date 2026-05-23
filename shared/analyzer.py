"""Listing analyzer with priority-based filter chain.

Same logic for LeBonCoin and Vinted; platform-specific behavior is selected
via the ``platform`` argument ("leboncoin" or "vinted").
"""

import re
from typing import Optional, Tuple

from shared.filters import is_text_valid


def analyze_item(
    item: dict,
    legos: dict,
    config: dict,
    platform: str,
) -> Tuple[Optional[dict], Optional[str]]:
    """Run an item through the configured filter chain.

    Args:
        item: Parsed listing payload (id, title, price, condition, etc.).
        legos: Reference Lego DB keyed by set id, with ``price_ref`` and ``name``.
        config: Full app config (filters + platform sections).
        platform: ``"leboncoin"`` or ``"vinted"``.

    Returns:
        (decision_dict, None) when accepted, (None, "filter_name") when rejected.
    """
    filters = config["filters"]
    platform_filters = filters.get(platform, {})

    filter_priority = filters.get(
        "priority",
        ["state", "lego_id", "banned_words", "discount"],
    )

    title = item.get("title", "").lower()
    description = item.get("description", "").lower()
    text = f"{title} {description}"
    price = item.get("price")
    condition = item.get("condition", "N/A") if platform == "leboncoin" else item.get("condition")

    if price is None:
        return None, "missing_price"

    found_ids = set(re.findall(r"\b\d{4,7}\b", text))
    valid_ids = found_ids.intersection(legos.keys()) if found_ids else set()
    seller_rating = item.get("seller_rating")
    seller_reviews = item.get("seller_reviews")

    for filter_name in filter_priority:

        if filter_name == "state":
            if not platform_filters.get("state", {}).get("enabled", False):
                continue
            allowed_states = set(platform_filters.get("allowed_states", []))
            if condition not in allowed_states:
                return None, "state"

        elif filter_name == "lego_id":
            if not filters.get("lego_id", {}).get("enabled", True):
                continue
            if not found_ids:
                return None, "lego_id_not_found"
            if not valid_ids:
                return None, "lego_id_not_in_database"

        elif filter_name == "banned_words":
            if not filters.get("banned_words", {}).get("enabled", True):
                continue
            if not is_text_valid(text):
                return None, "banned_words"

        elif filter_name == "seller":
            seller_cfg = platform_filters.get("seller", {})
            if not seller_cfg.get("enabled", False):
                continue
            min_rating = seller_cfg.get("min_rating", 0)
            min_reviews = seller_cfg.get("min_reviews", 0)
            if seller_rating is not None and seller_reviews is not None:
                if seller_rating < min_rating or seller_reviews < min_reviews:
                    return None, "seller"

        elif filter_name == "discount":
            discount_cfg = filters.get("discount")
            if not discount_cfg or not discount_cfg.get("enabled", False):
                continue
            if not valid_ids:
                return None, "lego_id_not_in_database"

            min_discount = discount_cfg.get("min", 0)
            max_discount = discount_cfg.get("max", 100)

            for lego_id in valid_ids:
                lego = legos[lego_id]
                price_ref = lego["price_ref"]
                discount = round(100 - (price / price_ref * 100))

                if min_discount <= discount <= max_discount:
                    return {
                        "lego_id": lego_id,
                        "lego_name": lego["name"],
                        "price_ref": price_ref,
                        "price": price,
                        "discount": discount,
                        "original_link": lego.get("original-link"),
                    }, None

            return None, "discount"

    if valid_ids:
        lego_id = next(iter(valid_ids))
        lego = legos[lego_id]
        price_ref = lego["price_ref"]
        discount = round(100 - (price / price_ref * 100))
        return {
            "lego_id": lego_id,
            "lego_name": lego["name"],
            "price_ref": price_ref,
            "price": price,
            "discount": discount,
            "original_link": lego.get("original-link"),
        }, None

    return None, "lego_id_not_in_database"
