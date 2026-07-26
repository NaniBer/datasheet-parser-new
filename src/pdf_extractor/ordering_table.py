"""
Ground the ordered package variant in the datasheet's own ordering table.

The order-code -> package mapping is *printed* in every proper datasheet, in a
section headed "Ordering Information" / "Package Option Addendum" / "Ordering
Guide" / "Orderable Part Number". Reading that table per-document is
vendor-agnostic: we look up the ordered part number's row instead of memorizing
every vendor's suffix scheme (an endless treadmill). This mirrors
``text_dimensions.py``, which grounds mechanical dimensions in the drawing page
rather than hardcoding them -- the document is the source of truth.

Everything here is grounded in the document text and fails closed. No ordering
section, no parseable row, or no matching row -> ``None``, and the caller keeps
its existing behaviour (this can only *improve* variant selection, never break
it).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover - fitz is a hard dep elsewhere
    fitz = None


# Section headings that introduce an ordering / package-option table. Kept
# high-precision on purpose: a false section is worse than a missing one.
_SECTION_HEADINGS = (
    "PACKAGE OPTION ADDENDUM",
    "ORDERING INFORMATION",
    "ORDERING GUIDE",
    "ORDERABLE PART NUMBER",
    "ORDERABLE DEVICE",
    "PART ORDERING INFORMATION",
    "DEVICE ORDERING INFORMATION",
)

# Known package family tokens, longest / most-specific first because Python's
# ``re`` alternation is leftmost-first (not leftmost-longest). Dashes are made
# optional so "SOT-23" and "SOT23" both match.
_FAMILY_TOKENS = (
    "HVSSOP", "VSSOP", "HTSSOP", "TSSOP", "QSOP", "SSOP", "MSOP",
    "SOIC", "SOP",
    "WSON", "VSON", "USON", "SON",
    "WQFN", "VQFN", "UQFN", "TQFN", "QFN", "TQFP", "LQFP", "MQFP", "QFP",
    "TDFN", "UDFN", "WDFN", "DFN",
    "PDIP", "CDIP", "SDIP", "DIP",
    "PLCC", "LCCC", "LCC",
    "WLCSP", "DSBGA", "TFBGA", "FBGA", "BGA", "LGA",
    "SOT-223", "SOT-143", "SOT-363", "SOT-89", "SOT-23", "SOT",
    "TO-220", "TO-263", "TO-252", "TO-247", "TO-264", "TO-100", "TO-92",
    "D2PAK", "DPAK", "MLF", "MLP", "SIP", "ZIP",
)

_FAMILY_ALT = "|".join(t.replace("-", r"\-?") for t in _FAMILY_TOKENS)
_FAMILY_RE = re.compile(r"(?<![A-Z0-9])(" + _FAMILY_ALT + r")(?![A-Z0-9])", re.IGNORECASE)

# Minimum length of the shorter of (part-number token, target) for a prefix
# match to count -- avoids spurious hits on a short common stem.
_MIN_PREFIX_LEN = 6
# Plausible pin/lead counts for a component footprint.
_MIN_PINS, _MAX_PINS = 2, 500


@dataclass
class OrderingMatch:
    """One ordering-table row matched to the target part number."""

    orderable: str
    package: Optional[str]
    pin_count: Optional[int]
    exact: bool
    reason: str


def _normalize(value: str) -> str:
    """Uppercase and strip everything but letters/digits (separator-agnostic)."""
    return re.sub(r"[^A-Z0-9]+", "", (value or "").upper())


def full_pdf_text(path: str) -> str:
    """Concatenated text of every page (the ordering table is often not on a
    detected pinout page, so we scan the whole document, like
    ``text_dimensions.find_dimension_pages``)."""
    if fitz is None:  # pragma: no cover
        return ""
    doc = fitz.open(path)
    try:
        return "\n".join(doc[i].get_text() for i in range(len(doc)))
    finally:
        doc.close()


def _section_start(text: str) -> int:
    """Index of the first ordering-section heading, or 0 if none is present."""
    upper = text.upper()
    positions = [upper.find(h) for h in _SECTION_HEADINGS]
    positions = [p for p in positions if p >= 0]
    return min(positions) if positions else 0


# A standalone "package cell" as extracted from a real ordering table, where
# PyMuPDF puts each column on its own line. The parens hold either a drawing
# code ("SOIC (DW) | 16") or the pin count ("PDIP (16)"); pins may also follow
# a pipe. Anchored to the whole line so it can't fire on prose.
_PACKAGE_CELL_RE = re.compile(
    r"^(" + _FAMILY_ALT + r")\b\s*(?:\(([^)]*)\))?\s*(?:[|｜]\s*(\d{1,3}))?\s*$",
    re.IGNORECASE,
)


def _package_cell(line: str) -> Optional[tuple]:
    """Parse a standalone package cell -> (family, pin_count|None), or None."""
    m = _PACKAGE_CELL_RE.match(line.strip())
    if not m:
        return None
    family = m.group(1).upper()
    pins = None
    if m.group(3):  # after a pipe: "SOIC (DW) | 16"
        pins = _in_range(m.group(3))
    elif m.group(2) and m.group(2).strip().isdigit():  # in parens: "PDIP (16)"
        pins = _in_range(m.group(2).strip())
    return family, pins


def _inline_package(line: str, part_token: str) -> Optional[tuple]:
    """Package named on the same line as the part number (single-line vendor
    rows, e.g. "PIC16F871-I/L  Industrial  44-Lead PLCC")."""
    # Ignore the part-number token itself so its letters can't be mistaken for
    # a family.
    scan = line.replace(part_token, " ")
    fam = _FAMILY_RE.search(scan)
    if not fam:
        return None
    return fam.group(1).upper(), _pin_count_from_line(scan, fam)


def _pin_count_from_line(line: str, family_match: re.Match) -> Optional[int]:
    """Pin/lead count stated explicitly on a single-line row, or None.

    Only the unambiguous forms are trusted (fail closed on the rest):
      "44-Lead", "8 Pin"        -> count before an explicit LEAD/PIN word
      "SOIC-8", "SOIC (8)"      -> count immediately after the family token
      "8-SOIC", "20 QFN"        -> count immediately before the family token
    """
    fam = re.escape(family_match.group(1))

    m = re.search(r"\b(\d{1,3})\s*-?\s*(?:LEAD|LEADS|PIN|PINS)\b", line, re.IGNORECASE)
    if m:
        return _in_range(m.group(1))

    m = re.search(fam + r"\s*[-(（]\s*(\d{1,3})\b", line, re.IGNORECASE)
    if m:
        return _in_range(m.group(1))

    m = re.search(r"\b(\d{1,3})\s*-?\s*" + fam + r"\b", line, re.IGNORECASE)
    if m:
        return _in_range(m.group(1))

    return None


def _in_range(digits: str) -> Optional[int]:
    try:
        n = int(digits)
    except ValueError:
        return None
    return n if _MIN_PINS <= n <= _MAX_PINS else None


def _pn_relation(token_norm: str, target_norm: str) -> Optional[bool]:
    """Return True (exact), False (prefix), or None (no match) for a normalized
    part-number token against the normalized target."""
    if not token_norm or not target_norm:
        return None
    if token_norm == target_norm:
        return True
    shorter, longer = sorted((token_norm, target_norm), key=len)
    if len(shorter) >= _MIN_PREFIX_LEN and longer.startswith(shorter):
        return False
    return None


def find_ordering_match(text: str, part_number: Optional[str]) -> Optional[OrderingMatch]:
    """
    Look up ``part_number`` in the datasheet's ordering table and return the
    package / pin count printed on its row.

    Real ordering tables extract as one column-cell per line, so a row is:
    an orderable part-number line, then the package named either on the same
    line (single-line vendor rows) or in a standalone "package cell" a few
    lines below ("SOIC (DW) | 16"). A candidate row is one whose part-number
    line matches the target (exact, or a >=6-char prefix relationship) and for
    which a package can be found within the row. When an ordering-section
    heading is present we only scan from there, which sharply cuts false
    positives.

    The best match wins: exact part-number match over prefix, then the longest
    matching token, then a row that also carries a pin count.
    """
    if not part_number or not text:
        return None

    target = _normalize(part_number)
    if len(target) < _MIN_PREFIX_LEN:
        return None

    lines = [ln.strip() for ln in text[_section_start(text):].splitlines()]

    best: Optional[OrderingMatch] = None
    best_key = ()
    for k, line in enumerate(lines):
        if not line:
            continue

        # Does this line carry the ordered part number? Try the whole line
        # (a bare orderable cell) and each whitespace token.
        token, relation = None, None
        for candidate in [line, *line.split()]:
            rel = _pn_relation(_normalize(candidate), target)
            if rel is not None:
                token, relation = candidate, rel
                if rel:  # exact beats a prefix token on the same line
                    break
        if relation is None:
            continue

        # Package on the same line, else the first package cell within the row.
        found = _inline_package(line, token)
        if not found:
            for j in range(k + 1, min(k + 7, len(lines))):
                cell = _package_cell(lines[j])
                if cell:
                    found = cell
                    # Some addenda split the row further ("SOIC" / "D" / "8"):
                    # if the cell carried no pin count, the Pins column is the
                    # first bare integer just below it.
                    if cell[1] is None:
                        for p in range(j + 1, min(j + 4, len(lines))):
                            if re.fullmatch(r"\d{1,3}", lines[p]) and _in_range(lines[p]):
                                found = (cell[0], _in_range(lines[p]))
                                break
                    break
        if not found:
            continue

        package, pins = found
        reason = (
            f"Ordering table row {token!r} "
            f"({'exact' if relation else 'prefix'} match) -> "
            f"{package}" + (f", {pins} pins" if pins else "")
        )
        # Rank: exact > prefix, then longer token, then has-pin-count.
        key = (1 if relation else 0, len(_normalize(token)), 1 if pins else 0)
        if key > best_key:
            best_key = key
            best = OrderingMatch(
                orderable=token,
                package=package,
                pin_count=pins,
                exact=relation,
                reason=reason,
            )

    return best


# --------------------------------------------------------------------------- #
# LLM-grounded fallback: when the deterministic parser above can't read a
# vendor's ordering-table layout, ask the model the one narrow question
# ("which package does this order code map to?") and verify its answer against
# the document text before trusting it. This is what lets the lookup work
# across vendors instead of only the layouts we hand-coded.
# --------------------------------------------------------------------------- #

_LLM_REGION_CHARS = 6000


def _ordering_region(text: str) -> str:
    """Best window of text to hand the model: from the ordering-section
    heading when present, else the document tail where addenda usually live."""
    start = _section_start(text)
    if start:
        return text[start:start + _LLM_REGION_CHARS]
    return text[-_LLM_REGION_CHARS:] if len(text) > _LLM_REGION_CHARS else text


def _family_from_text(value: str) -> Optional[str]:
    """First known package-family token in a string (uppercased), or None."""
    if not value:
        return None
    m = _FAMILY_RE.search(value)
    return m.group(1).upper() if m else None


def _parse_json_object(raw: str) -> Optional[dict]:
    """Pull the first JSON object out of a model reply (which may be fenced)."""
    if not raw:
        return None
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    import json

    try:
        obj = json.loads(raw[start:end + 1])
    except (ValueError, TypeError):
        return None
    return obj if isinstance(obj, dict) else None


def _build_ordering_prompt(region: str, part_number: str) -> list:
    return [
        {
            "role": "system",
            "content": (
                "You read the ordering / package-option table of an electronic "
                "component datasheet and map ONE orderable part number to the "
                "package printed on its row. Use ONLY information present in the "
                "provided text. If the order code is not listed, say so. Never "
                "guess from outside knowledge."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Order code: {part_number}\n\n"
                f"Ordering table text:\n{region}\n\n"
                "Return STRICT JSON only, no prose:\n"
                '{"found": true|false, '
                '"package": "<package family exactly as written, e.g. SOIC, '
                'TSSOP, QFN, SOT-23, TO-263, or empty>", '
                '"pin_count": <integer or null>}\n'
                "found=false if the order code is not in the text."
            ),
        },
    ]


def find_ordering_match_llm(
    text: str,
    part_number: Optional[str],
    model: str = "llama-3",
    verbose: bool = False,
) -> Optional[OrderingMatch]:
    """
    LLM-grounded ordering-table lookup, used only when the deterministic
    :func:`find_ordering_match` returns None.

    The model's answer is trusted only after grounding: the package family it
    reports must actually appear in the ordering-table text. Anything it
    invents (a package not in the document) is rejected -> None, so the caller
    keeps its prior behaviour. Any API/parse failure also returns None.
    """
    if not part_number or not text:
        return None

    region = _ordering_region(text)
    if not region.strip():
        return None

    try:
        from ..chat_bot import get_completion_from_messages
    except ImportError:  # pragma: no cover
        from src.chat_bot import get_completion_from_messages

    try:
        raw = get_completion_from_messages(
            _build_ordering_prompt(region, part_number), model=model, temperature=0
        )
    except Exception as exc:  # never let the fallback break the pipeline
        if verbose:
            print(f"  Ordering-table LLM fallback skipped: {exc}")
        return None

    data = _parse_json_object(raw)
    if not data or not data.get("found"):
        return None

    # Ground the package: the string the model returned must actually appear in
    # the ordering text (defeats hallucination). We accept it whether it names a
    # known family ("SOIC") or a vendor spelling we don't catalog ("SO20",
    # "Powerdip"), as long as it is printed in the document.
    region_norm = _normalize(region)
    pkg_raw = str(data.get("package") or "").strip()
    pkg_norm = _normalize(pkg_raw)
    family = _family_from_text(pkg_raw)
    grounded = (len(pkg_norm) >= 3 and pkg_norm in region_norm) or (
        family is not None and _normalize(family) in region_norm
    )
    if not pkg_raw or not grounded:
        return None
    # Prefer a catalogued family label for downstream matching; else keep the
    # vendor spelling as-is.
    package = family or pkg_raw

    # Ground the pin count too: trust it only if it is plausible and printed.
    pins = None
    raw_pins = data.get("pin_count")
    if isinstance(raw_pins, (int, str)):
        candidate = _in_range(str(raw_pins).strip()) if str(raw_pins).strip().isdigit() else None
        if candidate and str(candidate) in re.sub(r"[^0-9]", " ", region):
            pins = candidate

    exact = _normalize(part_number) in region_norm
    return OrderingMatch(
        orderable=part_number,
        package=package,
        pin_count=pins,
        exact=exact,
        reason=(
            f"LLM-grounded ordering table -> {package}"
            + (f", {pins} pins" if pins else "")
        ),
    )
