"""Heuristics for inferring a likely part number from datasheet text."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple


_TOKEN_PATTERN = re.compile(r"\b[A-Z0-9][A-Z0-9\-/]{2,}\b")
_PAGE_MARKER_PATTERN = re.compile(r"^---\s*Page\s+(\d+)\s*---\s*$", re.IGNORECASE)

_STOPWORDS = {
    "ABSOLUTE",
    "APPLICATION",
    "APPROVAL",
    "CHARACTERISTICS",
    "CONFIGURATION",
    "CONTENTS",
    "DESIGN",
    "DESCRIPTION",
    "DIMENSIONS",
    "ELECTRICAL",
    "FEATURES",
    "FIGURE",
    "FIGURES",
    "FUNCTIONS",
    "GENERAL",
    "GROUND",
    "PACKAGE",
    "PACKAGES",
    "PIN",
    "PINOUT",
    "PRODUCT",
    "RATINGS",
    "REFERENCE",
    "RECOMMENDED",
    "REV",
    "SECTION",
    "TABLE",
    "TABLES",
    "THERMAL",
    "TYPICAL",
    "VOLTAGE",
    "WWW",
    "HTTP",
}


def _normalize_token(token: str) -> str:
    """Normalize a candidate token into a clean uppercase identifier."""
    cleaned = token.strip(".,;:()[]{}<>\"'")
    cleaned = cleaned.replace(" ", "")
    return cleaned.upper()


def _token_is_plausible(token: str) -> bool:
    """Return True when a token looks like a part number."""
    if not token or token in _STOPWORDS:
        return False

    if len(token) < 4:
        return False

    if not any(ch.isdigit() for ch in token):
        return False

    if re.fullmatch(r"\d+", token):
        return False

    if "/" in token:
        return False

    if token in {"I2C", "SPI", "UART", "USB", "GPIO", "PWM", "ADC", "DAC"}:
        return False

    if token.endswith("X") and any(ch.isdigit() for ch in token[:-1]):
        # Generic family markers like TPS6216X are less useful than exact variants.
        return False

    return True


def _page_blocks(text_content: str) -> Iterable[Tuple[int, str]]:
    """Yield (page_number, page_text) blocks from formatted content."""
    current_page = None
    current_lines = []

    for line in (text_content or "").splitlines():
        marker = _PAGE_MARKER_PATTERN.match(line.strip())
        if marker:
            if current_page is not None and current_lines:
                yield current_page, "\n".join(current_lines).strip()
            current_page = int(marker.group(1))
            current_lines = []
            continue

        if current_page is not None:
            current_lines.append(line)

    if current_page is not None and current_lines:
        yield current_page, "\n".join(current_lines).strip()


def _tokenize(text: str) -> Iterable[str]:
    """Extract plausible identifier tokens from text."""
    for raw_token in _TOKEN_PATTERN.findall(text or ""):
        token = _normalize_token(raw_token)
        if _token_is_plausible(token):
            yield token


def _score_token(token: str, stats: Dict[str, Dict[str, int]]) -> float:
    """Score a candidate token using frequency and location heuristics."""
    entry = stats[token]
    score = entry["text_hits"] * 2.5 + entry["filename_hits"] * 1.5
    score -= min(entry["first_page"], 6) * 0.1

    if entry["text_hits"] > 1:
        score += 0.75

    return score


def infer_part_number_hint(text_content: str, source_name: Optional[str] = None) -> Optional[str]:
    """
    Infer a likely part number from extracted datasheet text.

    When a single plausible token is derived from the source filename it is
    returned unconditionally — the filename is stronger evidence than
    frequently-repeated internal identifiers (e.g. register bit names).
    The score-based ranking is used only when the filename yields zero or
    multiple candidates.
    """
    stats: Dict[str, Dict[str, int]] = {}

    for page_num, page_text in _page_blocks(text_content):
        lines = [line.strip() for line in page_text.splitlines() if line.strip()]
        for line in lines[:20]:
            for token in _tokenize(line):
                entry = stats.setdefault(
                    token,
                    {
                        "text_hits": 0,
                        "filename_hits": 0,
                        "first_page": page_num,
                    },
                )
                entry["text_hits"] += 1
                if page_num < entry["first_page"]:
                    entry["first_page"] = page_num

    if source_name:
        source_stem = Path(source_name).stem
        # Uppercase so mixed-case part numbers (e.g. "ATmega328p") are captured
        # by the uppercase-only TOKEN_PATTERN.
        for token in _tokenize(source_stem.upper()):
            entry = stats.setdefault(
                token,
                {
                    "text_hits": 0,
                    "filename_hits": 0,
                    "first_page": 999,
                },
            )
            entry["filename_hits"] += 1

    if not stats:
        return None

    filename_candidates = [token for token, entry in stats.items() if entry["filename_hits"] > 0]

    # A single filename candidate is strong evidence for the part number.
    # Return it unconditionally — it should not be overridden by frequently-
    # repeated internal identifiers (e.g. register bit names like "ICES1").
    if len(filename_candidates) == 1:
        return filename_candidates[0]

    ranked = sorted(
        ((token, _score_token(token, stats)) for token in stats),
        key=lambda item: item[1],
        reverse=True,
    )

    if not ranked:
        return None

    best_token, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0

    # Avoid making a brittle guess when several part-number-like tokens appear
    # with essentially the same score, which is common in multi-variant family
    # titles like "TPS62160, TPS62161, TPS62162, TPS62163".
    if best_score < 3.0:
        return None

    if second_score and (best_score - second_score) < 0.5:
        return None

    return best_token


# TI-style package designators: the suffix of an orderable part number and
# the prefix of the matching mechanical drawing code on the outline page
# (e.g. SN74HC595DWR -> designator DW -> drawing code DW0016A).
_PACKAGE_DESIGNATORS = {
    "D", "DW", "DB", "DBQ", "DBV", "DCK", "DCT", "DGK", "DGV", "DRL",
    "N", "NE", "NS", "P", "PS", "PW", "RGE", "RGY", "RUM",
}

# Packing / eco options appended after the package designator.
_ORDER_OPTION_SUFFIXES = ("E4", "G4", "R", "T")


def package_designator_from_part_number(part_number: Optional[str]) -> Optional[str]:
    """
    Derive the package designator from an orderable part number suffix.

    "SN74HC595DWR" -> "DW" (wide SOIC), "SN74HC595D" -> "D" (narrow SOIC),
    "SN74HC595PWR" -> "PW" (TSSOP). Returns None when the part number has no
    recognizable designator suffix, so callers fall back to family matching.
    """
    if not part_number:
        return None
    match = re.search(r"\d([A-Z]+)$", part_number.upper().strip())
    if not match:
        return None
    suffix = match.group(1)
    while suffix:
        if suffix in _PACKAGE_DESIGNATORS:
            return suffix
        for option in _ORDER_OPTION_SUFFIXES:
            if suffix.endswith(option) and len(suffix) > len(option):
                suffix = suffix[: -len(option)]
                break
        else:
            return None
    return None
