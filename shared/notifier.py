"""Discord webhook notifier: builds embeds for accepted and rejected listings.

Emojis are intentional here: this output is rendered inside Discord embeds.
"""

import requests
from datetime import datetime, timezone


VINTED_COLOR = 0x007782
LEBONCOIN_COLOR = 0xF56B2A
REJECTED_COLOR = 0xFF0000


PLATFORM_DEFAULTS = {
    "vinted": {
        "color": VINTED_COLOR,
        "bot_name": "Lego Scraper",
        "reject_bot_name": "Lego Scraper - Rejected",
        "state_map": {
            "new_with_tags": "New With Tags",
            "new_without_tags": "New Without Tags",
            "very_good": "Very Good",
            "good": "Good",
            "satisfactory": "Satisfactory",
            "unknown": "Unknown",
        },
    },
    "leboncoin": {
        "color": LEBONCOIN_COLOR,
        "bot_name": "Lego Scraper",
        "reject_bot_name": "Lego Scraper - Rejected",
        "state_map": None,  # LBC condition strings are already human-readable
    },
}


REJECT_REASONS = {
    "state": "Disallowed condition",
    "lego_id_not_found": "No Lego set ID found in listing",
    "lego_id_not_in_database": "Lego set ID not in reference database",
    "banned_words": "Banned keywords detected",
    "seller": "Seller does not meet criteria",
    "discount": "Discount outside configured range",
    "missing_price": "Missing price",
}


def format_price(price: float) -> str:
    return f"{price:.2f} €"


def _seller_line(item: dict) -> str:
    """Build the seller display line, with rating/reviews when available."""
    seller_name = item.get("seller_name", "Unknown")
    seller_url = item.get("seller_url", "")
    seller_rating = item.get("seller_rating")
    seller_reviews = item.get("seller_reviews")

    parts = [seller_name]
    if seller_rating and seller_reviews:
        parts.append(f"[({seller_rating}/5) | ({seller_reviews})]")
    elif seller_rating:
        parts.append(f"({seller_rating}/5) ⭐")
    elif seller_reviews:
        parts.append(f"⭐ | ({seller_reviews})")

    display = " ".join(parts)
    return f"[{display}]({seller_url})" if seller_url else display


def send_accepted_alert(
    webhook_url: str,
    item: dict,
    decision: dict,
    platform: str,
) -> bool:
    """Post a rich embed for an accepted listing."""
    try:
        defaults = PLATFORM_DEFAULTS[platform]
        state_map = defaults["state_map"]

        lego_id = decision["lego_id"]
        lego_name = decision["lego_name"]
        price = decision["price"]
        price_ref = decision["price_ref"]
        discount = decision["discount"]
        original_link = decision.get("original_link")

        item_id = item.get("id", "N/A")
        url = item.get("url", "")
        image = item.get("image", "")
        raw_condition = item.get("condition", "N/A")
        condition = state_map.get(raw_condition, raw_condition) if state_map else raw_condition

        description_parts = []
        if original_link:
            description_parts.append(f"### [ [ORIGINAL]({original_link}) ]")
        description_parts.append(f"**\U0001f464 {_seller_line(item)}**")

        # LeBonCoin includes city/region; Vinted does not.
        if platform == "leboncoin":
            city = item.get("city", "N/A")
            region = item.get("region", "N/A")
            description_parts.append(f"\U0001f4cd {city} ({region})")

        description = "\n".join(description_parts)

        footer_text = (
            f"\U0001f4c5 {datetime.now().strftime('%d/%m/%y')} | "
            f"\U0001f550 {datetime.now().strftime('%I:%M %p')} | "
            f"{item_id}"
        )

        embed = {
            "title": f"{lego_name} [{lego_id}]",
            "url": url,
            "description": description,
            "color": defaults["color"],
            "fields": [
                {"name": " ", "value": f"**\U0001f4b8 {format_price(price)}**", "inline": True},
                {"name": " ", "value": f"**\U0001f3f7️ {format_price(price_ref)}**", "inline": True},
                {"name": " ", "value": f"**\U0001f4c9 {discount} %**", "inline": True},
                {"name": " ", "value": f"**\U0001f4e6 {condition}**", "inline": True},
            ],
            "footer": {"text": footer_text},
        }

        if image:
            embed["image"] = {"url": image}

        payload = {"username": defaults["bot_name"], "embeds": [embed]}

        r = requests.post(webhook_url, json=payload, timeout=10)
        r.raise_for_status()
        return True

    except Exception as e:
        print(f"[ERROR] Discord notification failed ({platform}): {e}")
        return False


def send_rejected_alert(
    webhook_url: str,
    item: dict,
    rejected_by: str,
    platform: str,
) -> bool:
    """Post a compact embed for a rejected listing (for tuning the filter chain)."""
    try:
        defaults = PLATFORM_DEFAULTS[platform]
        state_map = defaults["state_map"]

        item_id = item.get("id", "N/A")
        title = item.get("title", "(no title)")
        url = item.get("url", "")
        price = item.get("price", 0)
        raw_condition = item.get("condition", "unknown")
        condition = state_map.get(raw_condition, raw_condition) if state_map else raw_condition

        seller_name = item.get("seller_name", "Unknown")
        seller_rating = item.get("seller_rating")
        seller_reviews = item.get("seller_reviews")

        seller_info = f"\U0001f464 {seller_name}"
        if seller_rating is not None and seller_reviews is not None:
            try:
                seller_info += f" | ⭐ {float(seller_rating)}/5 ({int(seller_reviews)})"
            except (ValueError, TypeError):
                pass

        reason = REJECT_REASONS.get(rejected_by, rejected_by)

        description_lines = [seller_info]
        if platform == "leboncoin":
            city = item.get("city", "N/A")
            region = item.get("region", "N/A")
            description_lines.append(f"\U0001f4cd {city}, {region}")
        description_lines.append("")
        description_lines.append(f"**Reason:** {reason}")

        embed = {
            "title": f"\U0001f6ab REJECTED: {title[:100]}",
            "url": url,
            "description": "\n".join(description_lines),
            "color": REJECTED_COLOR,
            "fields": [
                {"name": " ", "value": f"\U0001f4b8 {format_price(price)}", "inline": True},
                {"name": "\U0001f4e6", "value": str(condition), "inline": True},
                {"name": "\U0001f194 Listing ID", "value": str(item_id), "inline": True},
            ],
            "footer": {"text": f"Rejected at {datetime.now().strftime('%H:%M:%S')}"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        payload = {"username": defaults["reject_bot_name"], "embeds": [embed]}

        r = requests.post(webhook_url, json=payload, timeout=10)
        r.raise_for_status()
        return True

    except Exception as e:
        print(f"[ERROR] Rejected notification failed ({platform}): {e}")
        return False
