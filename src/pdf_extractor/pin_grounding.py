"""Pin-number grounding against parsed datasheet pin-table rows.

The LLM extractor sometimes reads a pin table correctly and then fabricates
extra pins to inflate the package - e.g. it reads a real 10-pin table (pins
1-10) and appends fake pins numbered 11-20, all named "NC". Those fabricated
pins evade the existing name-grounding check because "NC" genuinely appears
in the datasheet text somewhere. This module catches them by grounding pin
NUMBERS against the numbers that actually appear in the datasheet's own parsed
pin-table rows (built deterministically, reusing the same table-parsing
helpers used elsewhere in the pipeline).

Safety is deliberately biased hard toward NEVER dropping a real pin:

  * We only ever drop a pin that is BOTH a no-connect (NC/DNC) AND whose
    number appears in no parsed table. Real signal pins (PA0, VTT, ...) are
    never dropped even if the table extraction missed their number - so a
    noisy or incomplete index (register bit-field tables, multi-package pin
    tables where the parser only captured one variant's column) can at worst
    cause us to MISS a fabrication, never to wrongly drop a real pin.
  * An empty index (diagram-only datasheets with no parseable table) is a
    no-op.
  * A package whose pins are entirely ungrounded is skipped - the index most
    likely came from an unrelated table, not fabrication.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set

try:
    from .deterministic_table_parser import (
        _extract_pin_name,
        _extract_pin_numbers,
        _normalize_table,
    )
except ImportError:  # pragma: no cover - compatibility for top-level imports
    from src.pdf_extractor.deterministic_table_parser import (
        _extract_pin_name,
        _extract_pin_numbers,
        _normalize_table,
    )


_NO_CONNECT_NAMES = {"NC", "DNC", "NCDNC", "NOCONNECT", "NOCONNECTION"}


# ---------------------------------------------------------------------------
# Provenance / corroboration (Task 1: stop & trace hallucinations)
#
# The number-grounding above only ever drops fabricated NC pins. This section
# answers a different, broader question for every pin: "is the (number, name)
# pairing actually evidenced in the datasheet?" — and records that evidence on
# the pin. It is deliberately split into three tiers so the abstention gate can
# be tuned from measured data instead of a guess:
#
#   grounded    - the pin's number AND name appear together on one source line
#                 or table row (the shape a real pin table / connection diagram
#                 takes). Strongest evidence.
#   weak        - the name (or all its word-segments) appears somewhere in the
#                 source, but not co-located with the pin number. Generic names
#                 (V+, GND, IN) land here on a hallucinated pinout because they
#                 occur in prose everywhere — which is exactly why "appears
#                 anywhere" is too weak to trust on its own.
#   unsupported - the name appears nowhere in the source. Almost certainly
#                 invented (or the source page was never captured).
#   nc          - a no-connect pin; low signal, excluded from corroboration.
# ---------------------------------------------------------------------------


def _normalize(text) -> str:
    """Uppercase, strip every non-alphanumeric char (mirrors the validator)."""
    return re.sub(r"[^A-Za-z0-9]", "", str(text or "")).upper()


def _name_segments(name: str) -> List[str]:
    """Word-segments of a pin name, each normalized, length >= 2."""
    segments = [_normalize(seg) for seg in re.split(r"[^A-Za-z0-9]+", str(name or ""))]
    return [seg for seg in segments if len(seg) >= 2]


def _source_lines(content) -> List[tuple]:
    """(page_number, raw_line, normalized_line) for every text line and table row.

    Page is tracked from the "--- Page N ---" markers content_extractor emits;
    table rows carry their own page number.
    """
    lines: List[tuple] = []
    text = getattr(content, "text_content", "") or ""
    current_page = None
    page_marker = re.compile(r"---\s*Page\s+(\d+)")
    for raw in text.split("\n"):
        marker = page_marker.search(raw)
        if marker:
            current_page = int(marker.group(1))
            continue
        if raw.strip():
            lines.append((current_page, raw, _normalize(raw)))

    for page_number, table in getattr(content, "tables", None) or []:
        for row in table or []:
            joined = " ".join(str(cell) for cell in row if cell)
            if joined.strip():
                lines.append((page_number, joined, _normalize(joined)))

    return lines


def _line_has_number(raw_line: str, number: int) -> bool:
    """True if the pin number appears as a standalone token on the line."""
    return re.search(rf"(?<!\d){number}(?!\d)", raw_line) is not None


def _grade_pin(number, name, lines: List[tuple]):
    """Return (status, source_page, evidence) for one pin against the source."""
    if _is_no_connect(name):
        return "nc", None, None

    segments = _name_segments(name)
    raw_name = str(name or "").strip()
    if not segments and len(raw_name) < 2:
        # Single-char names (+, -, K) carry too little signal to judge.
        return "weak", None, None

    def name_on_line(raw_line: str, norm_line: str) -> bool:
        if segments:  # multi-char words: match segments in the punctuation-stripped line
            return all(seg in norm_line for seg in segments)
        # Short symbolic names (V+, V-, IN+): match the token literally on the raw line
        return raw_name in raw_line

    name_appears_anywhere = False
    for page, raw, norm in lines:
        if name_on_line(raw, norm):
            name_appears_anywhere = True
            if number is not None and _line_has_number(raw, int(number)):
                return "grounded", page, raw.strip()[:160]

    return ("weak", None, None) if name_appears_anywhere else ("unsupported", None, None)


def _pins_of(pin_data):
    """Yield the (mutable) pin objects to assess, across both PinData shapes."""
    packages = getattr(pin_data, "packages", None)
    if packages:
        for package in packages:
            if isinstance(package, dict):
                for pin in package.get("pins") or []:
                    yield pin
    pins = getattr(pin_data, "pins", None)
    if pins:
        for pin in pins:
            yield pin


def _pin_get(pin, key):
    return pin.get(key) if isinstance(pin, dict) else getattr(pin, key, None)


def _pin_set(pin, key, value):
    if isinstance(pin, dict):
        pin[key] = value
    else:
        setattr(pin, key, value)


def pin_number_coverage(pin_data, content) -> float:
    """Fraction of the extracted pins whose NUMBER appears as a standalone token
    anywhere in the source (text or table rows).

    This distinguishes a pinout invented from prose (the source contains no pin
    numbers at all -> ~0.0) from a real but graphical/discrete pinout whose
    package drawing does carry the numbers (-> high). It is deliberately about
    the *numbers*, not the names: a diode drawing may only print "1 2" beside
    the leads, which grounds by number even when the names don't ground by text.
    Returns 1.0 when there are no pins to judge (no evidence of invention).
    """
    lines = _source_lines(content)
    pins = list(_pins_of(pin_data))
    numbers = []
    for pin in pins:
        n = _pin_get(pin, "number")
        try:
            numbers.append(int(n))
        except (TypeError, ValueError):
            continue
    if not numbers:
        return 1.0
    present = sum(
        1 for n in numbers if any(_line_has_number(raw, n) for _p, raw, _norm in lines)
    )
    return present / len(numbers)


def assess_pin_grounding(pin_data, content) -> Dict[str, int]:
    """Tag every pin with its provenance and return a status tally.

    Populates each pin's ``grounding`` / ``source_page`` / ``source_evidence``
    in place, and returns counts like ``{"grounded": 6, "weak": 1,
    "unsupported": 1, "nc": 0, "total": 8}``. Pure instrumentation — no pin is
    added, dropped, or renamed. The abstention gate reads this tally.
    """
    lines = _source_lines(content)
    tally = {"grounded": 0, "weak": 0, "unsupported": 0, "nc": 0, "total": 0}

    for pin in _pins_of(pin_data):
        number = _pin_get(pin, "number")
        name = _pin_get(pin, "name")
        status, page, evidence = _grade_pin(number, name, lines)
        _pin_set(pin, "grounding", status)
        _pin_set(pin, "source_page", page)
        _pin_set(pin, "source_evidence", evidence)
        tally[status] += 1
        tally["total"] += 1

    return tally


def _is_no_connect(name) -> bool:
    """True for a no-connect pin label (NC / DNC / N.C. / "no connect")."""
    if not name:
        return False
    compact = re.sub(r"[^A-Z]", "", str(name).upper())
    return compact in _NO_CONNECT_NAMES


def build_pin_number_index(tables) -> Dict[int, Set[str]]:
    """Map pin_number -> set of UPPERCASE names the datasheet's table rows print.

    Built deterministically from `tables` (the `content.tables` shape:
    `List[Tuple[int, List[List[str]]]]`) by reusing the same
    deterministic_table_parser helpers used elsewhere. Per row, the numbers are
    taken from the first cell that yields any (mirroring how the deterministic
    table parser locates the pin-number column) and the name from
    `_extract_pin_name`. A number with no resolvable name still maps to an
    (empty) entry so the number counts as "present".

    This scans every table, so the index may include non-pin numbers (e.g. from
    spec tables). That is intentional and safe: `drop_ungrounded_pins` only ever
    drops no-connect pins, so a spurious number in the index can only cause a
    fabrication to be missed, never a real pin to be dropped.

    Returns {} when no numbers are found anywhere in `tables`.
    """
    index: Dict[int, Set[str]] = {}

    for _page_number, table in tables or []:
        normalized_table = _normalize_table(table)
        for row in normalized_table:
            pin_numbers: List[int] = []
            for cell in row:
                cell_numbers = _extract_pin_numbers(cell)
                if cell_numbers:
                    pin_numbers = cell_numbers
                    break

            if not pin_numbers:
                continue

            pin_name = _extract_pin_name(row)
            normalized_name = pin_name.upper()

            for number in pin_numbers:
                entry = index.setdefault(number, set())
                if normalized_name:
                    entry.add(normalized_name)

    return index


_TRAILING_COUNT_RE = re.compile(r"-\d+$")


def _resuffix_type(type_str: Optional[str], new_count: int) -> Optional[str]:
    """Replace a trailing "-<digits>" suffix on a package type string with the
    new pin count. Types without a numeric suffix (e.g. "SOIC") are returned
    unchanged."""
    if not type_str:
        return type_str
    if _TRAILING_COUNT_RE.search(type_str):
        return _TRAILING_COUNT_RE.sub(f"-{new_count}", type_str)
    return type_str


def _is_droppable(number, name, index: Dict[int, Set[str]]) -> bool:
    """A pin is droppable only when it is a no-connect AND its number appears
    in no parsed table row. Real signal pins are never droppable."""
    return _is_no_connect(name) and number not in index


def _drop_from_dict_package(package: dict, index: Dict[int, Set[str]]) -> int:
    """Drop fabricated no-connect pins from a single multi-package dict in
    place. Returns the number of pins dropped."""
    pins = package.get("pins")
    if not pins:
        return 0

    # If no pin number is grounded, the index came from a different table than
    # this package's pins - do not touch it.
    if not any(pin.get("number") in index for pin in pins):
        return 0

    kept = [pin for pin in pins if not _is_droppable(pin.get("number"), pin.get("name"), index)]
    dropped = len(pins) - len(kept)
    if dropped == 0:
        return 0

    package["pins"] = kept
    package["pin_count"] = len(kept)
    package["type"] = _resuffix_type(package.get("type"), len(kept))
    return dropped


def _grounded_pin_list(pins: List, index: Dict[int, Set[str]]):
    """Returns the trimmed pin list and drop count for a legacy `Pin` dataclass
    list, or (None, 0) when nothing should change."""
    if not pins:
        return None, 0

    if not any(pin.number in index for pin in pins):
        return None, 0

    kept = [pin for pin in pins if not _is_droppable(pin.number, pin.name, index)]
    dropped = len(pins) - len(kept)
    if dropped == 0:
        return None, 0

    return kept, dropped


def drop_ungrounded_pins(pin_data, index: Dict[int, Set[str]]) -> int:
    """Remove fabricated no-connect pins whose NUMBER is absent from `index`.

    Mutates `pin_data` in place; returns the number of pins dropped (0 if
    none). Handles both `PinData` shapes: the new multi-package
    `pin_data.packages` (list of dicts), and the legacy single-package
    `pin_data.package` / `pin_data.pins` (dataclasses).

    Safety guards (see module docstring for the rationale):
      - Empty `index` -> do nothing.
      - Only no-connect pins are ever dropped; a real signal pin is never
        removed, no matter how noisy the index is.
      - A package whose pins are entirely ungrounded is skipped.
    """
    if not index:
        return 0

    total_dropped = 0

    packages = getattr(pin_data, "packages", None)
    if packages:
        for package in packages:
            if not isinstance(package, dict):
                continue
            total_dropped += _drop_from_dict_package(package, index)

    pins = getattr(pin_data, "pins", None)
    if pins:
        kept, dropped = _grounded_pin_list(pins, index)
        if kept is not None:
            pin_data.pins = kept
            package_info = getattr(pin_data, "package", None)
            if package_info is not None:
                package_info.pin_count = len(kept)
                package_info.type = _resuffix_type(
                    getattr(package_info, "type", None), len(kept)
                )
            total_dropped += dropped

    return total_dropped
