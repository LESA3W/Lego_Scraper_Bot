"""Text-based filtering: detect banned French keywords in Lego listings.

The keywords stay in French because the source listings (LeBonCoin, Vinted FR)
are written in French. Translating them would break the filter.
"""

from typing import List, Optional


BANNED_WORDS = [
    # Completeness issues
    "incomplet",
    "manque",
    "manquant",
    "manquante",
    "manquantes",
    "pièce manquante",
    "pieces manquantes",
    "pièces manquantes",
    "il manque",
    "sans notice",
    "notice seule",

    # Packaging issues
    "boite vide",
    "boîte vide",
    "boite abimée",
    "boîte abimée",
    "sans boite",
    "sans boîte",

    # Unwanted listing types
    "lot",
    "lots",
    "vrac",
    "en vrac",
    "custom",
    "customs",
    "moc",
    "figurine seule",
    "figurine uniquement",
    "minifig seule",
    "minifig uniquement",
    "que la figurine",
    "seulement figurine",

    # Damaged condition
    "abîmé",
    "abimé",
    "abîmée",
    "abimée",
    "cassé",
    "cassée",
    "endommagé",
    "endommagée",
    "défectueux",
    "défectueuse",

    # Other suspect phrases
    "pour pièces",
    "pour pieces",
    "à compléter",
    "a compléter",
    "incomplet mais",
]


POSITIVE_KEYWORDS = [
    "neuf",
    "jamais ouvert",
    "scellé",
    "scelle",
    "complet",
    "toutes les pièces",
    "toutes pieces",
    "notice incluse",
    "boite d'origine",
    "boîte d'origine",
    "état neuf",
]


def is_text_valid(text: str, custom_banned: Optional[List[str]] = None) -> bool:
    """Return True if no banned word appears in the text."""
    text = text.lower().strip()

    banned_list = BANNED_WORDS.copy()
    if custom_banned:
        banned_list.extend(custom_banned)

    for word in banned_list:
        if word in text:
            return False

    return True


def get_positive_score(text: str) -> int:
    """Count how many positive keywords appear in the text."""
    text = text.lower().strip()
    return sum(1 for keyword in POSITIVE_KEYWORDS if keyword in text)


def analyze_text_quality(text: str) -> dict:
    """Return a quality assessment dict: valid, positive_score, banned_found, confidence."""
    text = text.lower().strip()
    banned_found = [word for word in BANNED_WORDS if word in text]
    positive_score = get_positive_score(text)

    if banned_found:
        confidence = "low"
    elif positive_score >= 2:
        confidence = "high"
    elif positive_score >= 1:
        confidence = "medium"
    else:
        confidence = "medium"

    return {
        "valid": len(banned_found) == 0,
        "positive_score": positive_score,
        "banned_found": banned_found,
        "confidence": confidence,
    }


def extract_concerns(text: str) -> List[str]:
    """Return human-readable reasons the listing was flagged."""
    text = text.lower().strip()
    return [f"Banned word: '{word}'" for word in BANNED_WORDS if word in text]
