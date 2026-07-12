"""
Text-based package dimension extraction (no vision API, no table of contents).

Many datasheets carry their mechanical dimensions as real text in the PDF:

- Modern TI outlines ("PACKAGE OUTLINE" pages) annotate values directly on the
  vector drawing: "14X 0.65" (pitch), "16X 0.30 / 0.17" (lead width),
  "1.2 MAX" (height), min/max pairs anchored to "NOTE 3"/"NOTE 4".
- Prose-style datasheets (e.g. FTDI) state dimensions in a sentence:
  "nominally 5.30mm x 10.20mm body (7.80mm x 10.20mm including pins).
   The pins are on a 0.65 mm pitch."

Pages are found by scanning every page's *content* — never PDF bookmarks or a
table of contents, since many datasheets have neither.

All parsers return flat dicts compatible with
PcbFootprintBuilder._apply_extracted_dims():
    {"package_type": ..., "unit": "mm", "e": pitch, "E": body width,
     "D": body length, "b": lead width, "L": lead length, "A": height}
"""

import re
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF

from .part_number_hint import package_designator_from_part_number

# Standard lead pitches (mm) — used both for parsing hints and plausibility.
STANDARD_PITCHES = (0.35, 0.4, 0.5, 0.65, 0.8, 1.0, 1.27, 1.778, 2.0, 2.54)
PITCH_TOLERANCE = 0.03

# Content signatures that mark a page as a mechanical drawing page.
_PAGE_SIGNATURES = (
    "PACKAGE OUTLINE",
    "PACKAGE DIMENSIONS",
    "MECHANICAL DATA",
    "MECHANICAL DIMENSIONS",
)

_FLOAT = r"\d+\.\d+"


def _floats(s: str) -> List[float]:
    return [float(x) for x in re.findall(_FLOAT, s)]


def find_dimension_pages(doc: "fitz.Document") -> List[int]:
    """
    Return 0-indexed pages that look like mechanical drawing pages.

    Scans the text content of every page; does NOT use doc.get_toc() or
    bookmarks — datasheets without a table of contents must work identically.
    """
    pages = []
    for i in range(len(doc)):
        text = doc[i].get_text()
        upper = text.upper()
        if any(sig in upper for sig in _PAGE_SIGNATURES):
            # Skip pure board-layout / stencil pages (no package outline).
            if "BOARD LAYOUT" in upper or "STENCIL DESIGN" in upper:
                continue
            pages.append(i)
        elif re.search(r"mm\s*(x|×)\s*\d+\.\d+\s*mm", text) and "pitch" in text.lower():
            pages.append(i)
    return pages


# TI mechanical drawing code, e.g. "DW0016A": designator + 4 digits + rev.
_DRAWING_CODE = re.compile(r"\b([A-Z]{1,4})\d{4}[A-Z]?\b")


def drawing_code_prefixes(text: str) -> set:
    """Designator prefixes of TI drawing codes on a page (DW0016A -> DW)."""
    return {m.group(1) for m in _DRAWING_CODE.finditer(text)}


def page_matches_designator(text: str, designator: Optional[str]) -> bool:
    """
    False only when the page carries drawing codes and none match the
    designator. Pages without codes (non-TI datasheets) always pass, and
    no designator means no filtering — this can only *exclude* a wrong
    variant, never invent a match.
    """
    if not designator:
        return True
    prefixes = drawing_code_prefixes(text)
    return not prefixes or designator in prefixes


def page_package_name(text: str) -> str:
    """Best-effort package family/name from a drawing page's text."""
    # TI style: "TSSOP - 1.2 mm max height"
    m = re.search(r"\b([A-Z]{2,6})\s*-\s*[\d.]+\s*mm max height", text)
    if m:
        return m.group(1)
    # Generic: "SSOP-28 Package Dimensions"
    m = re.search(r"\b([A-Z]{2,6}-\d+)\s+Package Dimensions", text, re.IGNORECASE)
    if m:
        return m.group(1)
    return ""


def parse_ti_outline(text: str, pin_count: int) -> Dict[str, float]:
    """
    Parse a TI-style "PACKAGE OUTLINE" page where dimension values are
    annotated on the drawing itself (no lettered table).

    Heuristics are keyed to the pin count N:
      - "(N-2)X <v>"          -> e  (pitch; N-2 gaps across both rows)
      - "NX <hi>" + "<lo>"    -> b  (lead width min/max, midpoint)
      - "<v> MAX"             -> A  (package height)
      - "<hi>" + "<lo> TYP"   -> E  (span including leads, midpoint)
      - pair before "NOTE 3"  -> D  (body length; TI note 3 = mold flash)
      - pair before "NOTE 4"  -> E1 (body width; TI note 4 = interlead flash)
      - pair in 0.3-1.5mm before "(x) TYP" -> L (lead length)

    A parse is cross-checked against the row span annotation "2X <span>"
    which must equal e * (N/2 - 1); on mismatch the pitch is dropped.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    dims: Dict[str, float] = {}

    for i, line in enumerate(lines):
        m = re.match(rf"^{pin_count - 2}X\s+({_FLOAT})$", line)
        if m:
            dims["e"] = float(m.group(1))

        m = re.match(rf"^{pin_count}X\s+({_FLOAT})$", line)
        if m and i + 1 < len(lines) and re.match(rf"^{_FLOAT}$", lines[i + 1]):
            dims["b"] = (float(m.group(1)) + float(lines[i + 1])) / 2.0

        m = re.match(r"^(\d+(?:\.\d+)?)\s+MAX$", line)
        if m and 0.3 <= float(m.group(1)) <= 6.0:
            dims["A"] = float(m.group(1))

        m = re.match(rf"^({_FLOAT})\s+TYP$", line)
        if m and i > 0 and re.match(rf"^{_FLOAT}$", lines[i - 1]):
            dims["E"] = (float(m.group(1)) + float(lines[i - 1])) / 2.0

        if line.startswith("NOTE") and i >= 2:
            pair = _floats(" ".join(lines[i - 2:i]))
            if len(pair) >= 2:
                mid = (pair[-1] + pair[-2]) / 2.0
                if "3" in line:
                    dims["D"] = mid
                elif "4" in line:
                    dims["E1"] = mid

        if re.match(rf"^\({_FLOAT}\)\s*TYP$", line) and i >= 2:
            pair = _floats(" ".join(lines[i - 2:i]))
            if len(pair) == 2 and all(0.3 <= p <= 1.5 for p in pair):
                dims["L"] = (pair[0] + pair[1]) / 2.0

    # Cross-check pitch against the row span annotation ("2X 4.55").
    if "e" in dims:
        m = re.search(rf"\b2X\s+({_FLOAT})", text)
        if m:
            expected_span = dims["e"] * (pin_count // 2 - 1)
            if abs(float(m.group(1)) - expected_span) > 0.06:
                del dims["e"]

    return dims


def parse_prose(text: str) -> Dict[str, float]:
    """
    Parse prose-style dimensions, e.g. FTDI:
    "nominally 5.30mm x 10.20mm body (7.80mm x 10.20mm including pins).
     The pins are on a 0.65 mm pitch."
    """
    dims: Dict[str, float] = {}

    m = re.search(
        rf"({_FLOAT})\s*mm\s*(?:x|×)\s*({_FLOAT})\s*mm\s*body", text, re.IGNORECASE
    )
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        # Body width is the smaller axis, body length the larger.
        dims["E1"], dims["D"] = min(a, b), max(a, b)

    m = re.search(
        rf"\(({_FLOAT})\s*mm\s*(?:x|×)\s*({_FLOAT})\s*mm\s+including\s+pins",
        text,
        re.IGNORECASE,
    )
    if m:
        a, b = float(m.group(1)), float(m.group(2))
        dims["E"] = min(a, b)

    m = re.search(rf"on\s+a\s+({_FLOAT})\s*mm\s+pitch", text, re.IGNORECASE)
    if m:
        dims["e"] = float(m.group(1))

    return dims


def plausible_dims(dims: Dict[str, Any]) -> bool:
    """
    Sanity gate for extracted dimensions (any source — text or vision).

    Rejects results whose values cannot belong to a real IC package, which
    catches vision-model failures that assign real numbers to wrong labels.
    """
    e = dims.get("e")
    if e is not None:
        if not any(abs(e - p) <= PITCH_TOLERANCE for p in STANDARD_PITCHES):
            return False

    b = dims.get("b")
    if b is not None:
        if not 0.1 <= b <= 1.6:
            return False
        if e is not None and b >= e:
            return False

    a = dims.get("A")
    if a is not None and not 0.3 <= a <= 6.0:
        return False

    for key in ("D", "E", "E1"):
        v = dims.get(key)
        if v is not None and not 1.0 <= v <= 60.0:
            return False

    # Body width (E1 or E) must exceed lead width.
    body = dims.get("E1") or dims.get("E")
    if body is not None and b is not None and body <= b:
        return False

    return True


def extract_text_dimensions(
    doc: "fitz.Document",
    target_package_type: Optional[str] = None,
    part_number: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Extract dimensions from PDF text only (no API calls, no table of contents).

    Args:
        doc: Open fitz document.
        target_package_type: e.g. "TSSOP-16" or "SOIC-16". Used to derive the
            pin count for TI-outline heuristics and to pick the right drawing
            when a datasheet documents several package variants.
        part_number: Orderable part number (e.g. "SN74HC595DWR"). Its package
            designator suffix disambiguates same-family variants the family
            check cannot (narrow "D" vs wide "DW" SOIC).

    Returns:
        Flat dims dict (same shape as DimensionExtractor.extract), or None.
    """
    pin_count = None
    family = ""
    if target_package_type:
        m = re.search(r"\d+", target_package_type)
        if m:
            pin_count = int(m.group())
        family = re.sub(r"[^A-Z]", "", target_package_type.upper().split("-")[0])

    designator = package_designator_from_part_number(part_number)

    best: Optional[Dict[str, Any]] = None
    for page_no in find_dimension_pages(doc):
        text = doc[page_no].get_text()
        if not page_matches_designator(text, designator):
            continue
        page_pkg = page_package_name(text)

        # When we know the target family, skip drawings of other variants.
        if family and page_pkg:
            page_family = re.sub(r"[^A-Z]", "", page_pkg.split("-")[0])
            if page_family != family:
                continue

        dims: Dict[str, float] = {}
        if pin_count:
            dims = parse_ti_outline(text, pin_count)
        if not dims:
            dims = parse_prose(text)

        if not dims or not plausible_dims(dims):
            continue

        result: Dict[str, Any] = {
            "package_type": page_pkg or (target_package_type or ""),
            "unit": "mm",
        }
        result.update(dims)

        # Prefer the result with the most extracted values.
        if best is None or len(result) > len(best):
            best = result

    return best
