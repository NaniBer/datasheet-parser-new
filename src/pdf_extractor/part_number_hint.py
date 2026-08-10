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


# Package/case labels are NOT part numbers. On a pin-configuration page these
# (e.g. "DFN-6", "SOIC-8", "TO-92", "SOT-23", "QFN-32") can out-score the real
# part number in the token ranking, so a datasheet whose ordered part number is
# absent from the extracted text would otherwise be identified by its package.
_PKG_LABEL_FAMILIES = (
    "HVSSOP", "VSSOP", "TSSOP", "HTSSOP", "WLCSP", "LQFP", "TQFP", "PDIP",
    "CDIP", "WSON", "D2PAK", "SSOP", "QSOP", "MSOP", "SOIC", "LCCC", "PLCC",
    "DPAK", "MELF", "TSOP", "SOD", "SMA", "SMB", "SMC", "QFN", "DFN", "QFP",
    "BGA", "LGA", "SON", "SOP", "SOT", "DIP", "TO", "DO", "SC", "SO",
)
_PKG_LABEL_RE = re.compile(
    r"^(?:" + "|".join(_PKG_LABEL_FAMILIES) + r")-?\d{1,4}[A-Z]{0,3}$"
)


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

    # A bare package/case label (DFN-6, SOIC-8, TO-92, QFN-32) is never a part
    # number — reject so it can't be mistaken for one.
    if _PKG_LABEL_RE.match(token):
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

    The filename is a tie-breaker, not an override. A single plausible token
    derived from the source filename wins when it is *corroborated* by the
    document text (it occurs at least once in the extracted content) — that is
    strong, mutually-confirming evidence.

    When that filename token appears NOWHERE in the text, it must not override
    a strong in-document identifier: a token that clears the score thresholds
    used below (``best_score >= 3.0`` and separated from the runner-up by at
    least 0.5) is preferred instead. This makes the result independent of the
    filename, so byte-identical files under different names resolve to the same
    part number. The uncorroborated filename token is used only as a last
    resort, when no in-document identifier is strong enough to trust.

    The score-based ranking decides directly when the filename yields zero or
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
        # by the uppercase-only TOKEN_PATTERN. Underscores become spaces:
        # `_` is a \w character, so a stem like "9_BQ25570" has no word
        # boundary before the part token and it would otherwise never match
        # (or worse, only a fragment after a later hyphen would).
        for token in _tokenize(source_stem.upper().replace("_", " ")):
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

    ranked = sorted(
        ((token, _score_token(token, stats)) for token in stats),
        key=lambda item: item[1],
        reverse=True,
    )

    if not ranked:
        return None

    # A single filename token is a tie-breaker, not an override.
    if len(filename_candidates) == 1:
        filename_token = filename_candidates[0]

        # Corroborated by the document text -> strong, keep it.
        if stats[filename_token]["text_hits"] > 0:
            return filename_token

        # Uncorroborated: the filename claims a part that appears nowhere in the
        # text. Prefer a strong in-document identifier if one clears the score
        # thresholds, so the result stays independent of the filename. Only the
        # tokens that actually occur in the text are eligible here.
        in_doc_ranked = [
            (token, score) for token, score in ranked if stats[token]["text_hits"] > 0
        ]
        if in_doc_ranked:
            best_token, best_score = in_doc_ranked[0]
            second_score = in_doc_ranked[1][1] if len(in_doc_ranked) > 1 else 0.0
            if best_score >= 3.0 and (not second_score or (best_score - second_score) >= 0.5):
                return best_token

        # No trustworthy in-document identifier -> fall back to the filename
        # token rather than making a brittle guess.
        return filename_token

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
    "D", "DW", "DB", "DBQ", "DBV", "DCK", "DCN", "DCT", "DDC", "DGK",
    "DGV", "DRC", "DRL", "DSC", "DSG",
    "N", "NE", "NS", "P", "PS", "PW", "PWP",
    "RGE", "RGR", "RGT", "RGY", "RGZ", "RHA", "RHB", "RHL", "RTE", "RUM",
}

# Designator -> package family (only families with supported geometry;
# unsupported ones like DCK/SC-70 are deliberately absent so extraction
# stays fail-closed for them).
TI_DESIGNATOR_FAMILIES = {
    "D": "SOIC", "DW": "SOIC", "NS": "SOIC", "PS": "SOIC",
    "DB": "SSOP", "DBQ": "SSOP",
    # PWP is PowerPAD HTSSOP: TSSOP body/grid with an exposed pad.
    "PW": "TSSOP", "PWP": "TSSOP", "DGV": "TSSOP",
    "DGK": "MSOP",
    "DBV": "SOT23", "DCN": "SOT23", "DDC": "SOT23",
    "DSC": "WSON", "DSG": "WSON", "DRC": "WSON",
    "RGE": "QFN", "RGR": "QFN", "RGT": "QFN", "RGY": "QFN", "RGZ": "QFN",
    "RHA": "QFN", "RHB": "QFN", "RHL": "QFN", "RTE": "QFN", "RUM": "QFN",
    "N": "PDIP", "NE": "PDIP", "P": "PDIP",
}

# "DSC PACKAGE (TOP VIEW)" or "D, DW, N, NS, OR PW PACKAGE (TOP VIEW)".
# Whitespace is optional throughout: the content extractor squeezes spaces,
# so the same headers arrive as "DSCPACKAGE" / "D,DW,N,NS,ORPWPACKAGE".
_DESIGNATOR_HEADER = re.compile(
    r"\b((?:[A-Z]{1,3}\s*,\s*(?:OR\s*)?)*[A-Z]{1,3})\s*PACKAGE\b"
)


def family_from_page_designators(
    text: str, part_number: Optional[str] = None
) -> Optional[str]:
    """
    Package family named by TI mechanical designators in a page header.

    A single known designator names the family directly ("DSC PACKAGE" ->
    WSON). Headers listing several designators are ambiguous and resolve
    only through the part number's own designator; otherwise None — this
    never guesses.
    """
    designators: set = set()
    for match in _DESIGNATOR_HEADER.finditer(text or ""):
        tokens = re.split(r"[,\s]+", match.group(1))
        for t in tokens:
            if t.startswith("OR") and t[2:] in TI_DESIGNATOR_FAMILIES:
                t = t[2:]  # "ORPW" from a space-squeezed ", OR PW"
            if t != "OR" and t in TI_DESIGNATOR_FAMILIES:
                designators.add(t)

    if not designators:
        return None
    if len(designators) == 1:
        return TI_DESIGNATOR_FAMILIES[next(iter(designators))]

    pn_designator = package_designator_from_part_number(part_number)
    if pn_designator in designators:
        return TI_DESIGNATOR_FAMILIES[pn_designator]
    return None

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
