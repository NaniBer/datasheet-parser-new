"""Helpers for identifying package features that are not electrical pins."""

from __future__ import annotations

import re


NON_PIN_FEATURE_PATTERNS = (
    r"\bexposed\s+thermal\s+pad\b",
    r"\bthermal\s+pad\b",
    r"\bexposed\s+pad\b",
    r"\bcenter\s+thermal\s+pad\b",
    r"\bcenter\s+pad\b",
    r"\bdie\s+pad\b",
)


def is_non_pin_feature_name(name: str) -> bool:
    """
    Return True when a pin label clearly refers to a package feature rather
    than an electrical pin.

    We keep this intentionally conservative to avoid hiding real pins.
    """
    if not name:
        return False

    normalized = re.sub(r"\s+", " ", str(name).strip().lower())
    compact = re.sub(r"[^a-z0-9]", "", normalized).upper()

    if compact in {"EP", "EPAD"}:
        return True

    if normalized == "pad":
        return True

    for pattern in NON_PIN_FEATURE_PATTERNS:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            return True

    return False
