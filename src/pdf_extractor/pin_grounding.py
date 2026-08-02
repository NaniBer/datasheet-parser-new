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
