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
    # Lettered "Dimension Limits" tables (Microchip/Atmel packaging pages).
    "COMMON DIMENSIONS",
    "DIMENSION LIMITS",
    "PACKAGING INFORMATION",
)

# Headings/markers that identify a lettered dimension-limits TABLE (as opposed
# to a graphical TI outline). Used to gate parse_dimension_table.
_TABLE_SIGNATURES = ("COMMON DIMENSIONS", "DIMENSION LIMITS", "PACKAGING INFORMATION")

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

        # c = lead/frame thickness: a bare "c" label anchored to a thin
        # MIN/MAX pair on the two preceding lines (JEDEC thickness ~0.1-0.3mm).
        if line == "c" and i >= 2:
            pair = _floats(" ".join(lines[i - 2:i]))
            if len(pair) == 2 and all(0.05 <= p <= 0.60 for p in pair):
                dims["c"] = (pair[0] + pair[1]) / 2.0

        # D2/E2 = exposed thermal pad (QFN/DFN): the two floats that follow
        # an "exposed pad" / "thermal pad" heading are its D2 then E2 sizes.
        if re.search(r"(exposed|thermal)\s+pad", line, re.IGNORECASE):
            following = _floats(" ".join(lines[i + 1:i + 3]))
            if len(following) >= 2:
                if 0 < following[0] < 60.0:
                    dims["D2"] = following[0]
                if 0 < following[1] < 60.0:
                    dims["E2"] = following[1]

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


# JEDEC symbols that can appear as standalone tokens in a lettered table. Used
# only to decide table orientation (which side of a symbol its values sit on).
_TABLE_SYMBOLS = {
    "A", "A1", "A2", "A3", "b", "b1", "c", "c1",
    "D", "D1", "D2", "E", "E1", "E2", "e", "L", "L1",
}


def _pure_float(s: str) -> bool:
    return re.fullmatch(_FLOAT, s) is not None


def _float_run(lines: List[str], i: int, step: int) -> List[float]:
    """Contiguous run of pure-float lines starting adjacent to i in `step` dir."""
    run: List[float] = []
    j = i + step
    while 0 <= j < len(lines) and _pure_float(lines[j]):
        run.append(float(lines[j]))
        j += step
    return run


def _table_orientation(lines: List[str]) -> int:
    """+1 if a symbol's values FOLLOW it, -1 if they PRECEDE it (majority vote).

    Lettered tables are laid out consistently: either "values then symbol"
    (Microchip/Atmel, e.g. 0.05 / 0.15 / A1) or "symbol then values" (ST, e.g.
    A / 0.500 / 0.550 / 0.600). Reading the wrong side grabs a neighbouring
    symbol's numbers, so orientation is decided once for the whole table.
    """
    before = after = 0
    for i, line in enumerate(lines):
        if line not in _TABLE_SYMBOLS:
            continue
        if i > 0 and _pure_float(lines[i - 1]):
            before += 1
        if i + 1 < len(lines) and _pure_float(lines[i + 1]):
            after += 1
    return 1 if after > before else -1


def _drop_inch_duplicates(vals: List[float]) -> List[float]:
    """Drop values that are the inch equivalent (mm/25.4) of another value.

    Dual-unit tables print each dimension twice (mm and inch). Mixing the two
    corrupts any min/max/mean, so a value x is dropped when some other value in
    the run is ~25.4x (its millimetre counterpart)."""
    keep = [
        x for x in vals
        if not (x > 0 and any(
            v != x and abs(25.4 * x - v) <= max(0.03, 0.04 * v) for v in vals
        ))
    ]
    return keep or vals


# Combined tokens some tables print for a shared min/max (e.g. Atmel TQFP's
# "D/E" span and "D1/E1" body): the one run of values applies to BOTH keys.
_COMBINED_SYMBOLS = {"D/E": ("D", "E"), "D1/E1": ("D1", "E1")}


def parse_dimension_table(text: str) -> Dict[str, float]:
    """Parse the footprint dimension set from a lettered dimension table.

    Microchip/Atmel/ST-style "Dimension Limits" / "COMMON DIMENSIONS" tables
    print each JEDEC symbol with its MIN/NOM/MAX values on adjacent lines. This
    reads the vertical profile (overall height A, standoff A1, body thickness
    A2) that the graphical TI-outline parser cannot see (their labels live in
    the drawing, not the text layer), and — additively — the planar footprint
    set: lead pitch e, lead width b, lead foot L, body length D, and overall
    span / body width E / E1.

    Robust to the two real-world variations: table orientation (values before
    vs after the symbol, decided once for the whole table) and dual mm/inch
    units (the inch column is detected and dropped). Only trusted inside a
    lettered-table context so stray "A"/"A1" tokens elsewhere cannot be mistaken
    for dimensions.
    """
    up = text.upper()
    has_table = ("SYMBOL" in up and "MIN" in up and "MAX" in up) or any(
        sig in up for sig in _TABLE_SIGNATURES
    )
    if not has_table:
        return {}

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    step = _table_orientation(lines)
    dims: Dict[str, float] = {}
    # Per-symbol plausibility. Vertical profile: A = overall height, A1 =
    # standoff, A2 = body. A1 is capped tight (SMD standoffs are <=~0.25mm); a
    # larger value is a misread of the height column, not a standoff. Planar
    # footprint set: e = lead pitch, b = lead width, L = lead foot (all lead
    # features, same values-vs-symbol layout as A1); D/E/E1/D1 = body extents.
    bounds = {
        "A": (0.3, 6.0), "A1": (0.0, 0.35), "A2": (0.2, 6.0),
        "e": (0.3, 3.0), "b": (0.1, 1.6), "L": (0.2, 1.5),
        "D": (1.0, 60.0), "D1": (1.0, 60.0),
        "E": (1.0, 60.0), "E1": (1.0, 60.0),
    }
    for i, line in enumerate(lines):
        # A combined "D/E"/"D1/E1" token feeds its one run to both keys.
        keys = _COMBINED_SYMBOLS.get(line, (line,)) if line in bounds \
            or line in _COMBINED_SYMBOLS else None
        if keys is None:
            continue
        run = _drop_inch_duplicates(_float_run(lines, i, step))
        # Pitch is often a lone annotation ("0.80 TYP.") rather than a pure-float
        # MIN/NOM/MAX trio, so _float_run comes up empty; read the float out of
        # the single adjacent (orientation-side) line instead.
        if line == "e" and not run and 0 <= i + step < len(lines):
            run = _floats(lines[i + step])
        for key in keys:
            lo, hi = bounds[key]
            in_band = [v for v in run if lo <= v <= hi]
            if in_band:
                dims.setdefault(key, sum(in_band) / len(in_band))

    # Pitch is quantised: snap to a standard value when close, matching the
    # STANDARD_PITCHES/PITCH_TOLERANCE convention used by plausible_dims. This
    # also selects the NOM pitch cleanly (a lone TYP value snaps to itself).
    if "e" in dims:
        for p in STANDARD_PITCHES:
            if abs(dims["e"] - p) <= PITCH_TOLERANCE:
                dims["e"] = p
                break

    # Ordering sanity: standoff < body thickness <= overall height. A misread
    # that violates the physical stack-up is dropped rather than shipped.
    a, a1, a2 = dims.get("A"), dims.get("A1"), dims.get("A2")
    if a is not None and a1 is not None and a1 >= a:
        dims.pop("A1", None)
    if a is not None and a2 is not None and a2 > a + 0.05:
        dims.pop("A2", None)
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

    # A1 = standoff (seating plane to body underside): a small positive gap.
    a1 = dims.get("A1")
    if a1 is not None and not 0.0 <= a1 <= 0.35:
        return False

    # A2 = moulded body thickness: positive, and no taller than overall A.
    a2 = dims.get("A2")
    if a2 is not None:
        if not 0.2 <= a2 <= 6.0:
            return False
        if a is not None and a2 > a + 0.05:
            return False

    for key in ("D", "E", "E1"):
        v = dims.get(key)
        if v is not None and not 1.0 <= v <= 60.0:
            return False

    # Body width (E1 or E) must exceed lead width.
    body = dims.get("E1") or dims.get("E")
    if body is not None and b is not None and body <= b:
        return False

    # c = lead/frame thickness (JEDEC): a thin sheet, ~0.05-0.60mm.
    c = dims.get("c")
    if c is not None and not 0.05 <= c <= 0.60:
        return False

    # D2/E2 = exposed thermal pad (QFN/DFN): positive and smaller than the
    # body it sits inside (D along the D axis, E1/E along the E axis).
    d2 = dims.get("D2")
    if d2 is not None:
        if d2 <= 0:
            return False
        d_body = dims.get("D")
        if d_body is not None and d2 >= d_body:
            return False

    e2 = dims.get("E2")
    if e2 is not None:
        if e2 <= 0:
            return False
        e_body = dims.get("E1") or dims.get("E")
        if e_body is not None and e2 >= e_body:
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

        # Supplement the vertical profile (standoff A1, body A2, and height A
        # when missing) from a lettered dimension table on the same page. The
        # graphical parser reads the X/Y footprint but not the Z standoff.
        for key, val in parse_dimension_table(text).items():
            dims.setdefault(key, val)

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
