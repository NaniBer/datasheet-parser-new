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

    The heuristic is intentionally conservative. It prefers repeated tokens from
    the document text and only falls back to the filename when necessary.
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
        for token in _tokenize(source_stem):
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

    ranked = sorted(
        ((token, _score_token(token, stats)) for token in stats),
        key=lambda item: item[1],
        reverse=True,
    )

    if not ranked:
        return None

    best_token, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    filename_candidates = [token for token, entry in stats.items() if entry["filename_hits"] > 0]

    # Avoid making a brittle guess when several part-number-like tokens appear
    # with essentially the same score, which is common in multi-variant family
    # titles like "TPS62160, TPS62161, TPS62162, TPS62163".
    if best_score < 3.0:
        if len(filename_candidates) == 1:
            return filename_candidates[0]
        return None

    if second_score and (best_score - second_score) < 0.5:
        return None

    return best_token
