"""Rule-based pin table parsing for clean datasheet tables.

This parser is intentionally conservative. It is used before the LLM so that
well-structured pin tables can be extracted deterministically, while the LLM
remains a fallback for ambiguous diagrams or messy mixed-content pages.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

try:
    from ..models.pin_data import Pin, PinData, PackageInfo
    from ..models.pin_classifier import detect_active_low, description_marks_active_low
    from .part_number_hint import (
        infer_part_number_hint,
        family_from_page_designators,
        package_designator_from_part_number,
        TI_DESIGNATOR_FAMILIES,
    )
    from ..utils.package_detector import PackageDetector
except ImportError:  # pragma: no cover - compatibility for top-level imports
    from src.models.pin_data import Pin, PinData, PackageInfo
    from src.models.pin_classifier import detect_active_low, description_marks_active_low
    from src.pdf_extractor.part_number_hint import (
        infer_part_number_hint,
        family_from_page_designators,
        package_designator_from_part_number,
        TI_DESIGNATOR_FAMILIES,
    )
    from src.utils.package_detector import PackageDetector

from .non_pin_features import is_non_pin_feature_name


_HEADER_STOPWORDS = {
    "PIN",
    "PIN NO",
    "PIN NUMBER",
    "NO",
    "NO.",
    "NUMBER",
    "NAME",
    "FUNCTION",
    "DESCRIPTION",
    "I/O",
    "IO",
    "TYPE",
    "VALUE",
    "PARAMETER",
    "PARAMETERS",
}

_KNOWN_PIN_LABELS = {
    "GND",
    "VCC",
    "VDD",
    "VSS",
    "PGND",
    "AGND",
    "DGND",
    "OE",
    "MR",
    "CLR",
    "SER",
    "SRCLK",
    "RCLK",
    "SCK",
    "MOSI",
    "MISO",
    "SDA",
    "SCL",
    "RESET",
    "CLK",
    "CS",
    "NC",
    "TRIG",
    "OUT",
    "CTRL",
    "THRES",
    "DISCH",
    "VIN",
    "VOUT",
    "FB",
    "VOS",
    "PG",
    "SW",
    "FSYNC",
    "REGOUT",
    "CPOUT",
    "AUX_DA",
    "AUX_CL",
    "AD0",
    "SDO",
    "SDI",
    "CLKIN",
    "VLOGIC",
    "RESV",
    "RESERVED",
}


@dataclass
class ParsedPinTableCandidate:
    """A parsed pin table candidate with a confidence score."""

    page_number: int
    score: int
    pin_data: PinData


def _normalize_cell_text(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\r", " ").replace("\n", " ").split()).strip()


def _normalize_table(table: List) -> List[List[str]]:
    rows: List[List[str]] = []
    for row in table or []:
        normalized_row = [_normalize_cell_text(cell) for cell in row]
        if any(normalized_row):
            rows.append(normalized_row)
    return rows


def _table_text(table: List[List[str]]) -> str:
    return " ".join(" ".join(cell for cell in row if cell).lower() for row in table)


def _column_blobs(table: List[List[str]], max_rows: int = 4) -> List[str]:
    max_cols = max((len(row) for row in table), default=0)
    blobs: List[str] = []
    for col_idx in range(max_cols):
        parts: List[str] = []
        for row in table[:max_rows]:
            if col_idx < len(row):
                text = _normalize_cell_text(row[col_idx])
                if text:
                    parts.append(text)
        blobs.append(" ".join(parts).lower())
    return blobs


_SPACED_RANGE_RE = re.compile(r"(\d+)\s*[-–—]\s*(\d+)")


def _extract_pin_numbers(text: str) -> List[int]:
    normalized = _normalize_cell_text(text)
    if not normalized:
        return []
    # Close up spaced ranges ("44 - 48", "44 – 48") so the split below keeps
    # them whole instead of reading only the endpoints.
    normalized = _SPACED_RANGE_RE.sub(r"\1-\2", normalized)

    numbers: List[int] = []
    for chunk in re.split(r"[,\s]+", normalized):
        chunk = chunk.strip()
        if not chunk:
            continue

        range_match = re.fullmatch(r"(\d+)-(\d+)", chunk)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            if start <= end:
                numbers.extend(range(start, end + 1))
            else:
                numbers.extend(range(end, start + 1))
            continue

        # Plain decimal digits (ASCII or full-width) that int() accepts.
        if chunk.isdecimal():
            numbers.append(int(chunk))
            continue

        # Enclosed / decorated numerals where each character is a whole pin
        # number: circled digits number pins as "①②" = pins 1 and 2
        # (not the number 12), and "⑩" = 10. Guard against non-decimal
        # strings like "3.3" by requiring EVERY character to be an integer
        # numeral. This is the case that used to crash int() (ValueError on
        # '①②') because those characters are isdigit() but not
        # isdecimal().
        enclosed = _enclosed_numerals(chunk)
        if enclosed:
            numbers.extend(enclosed)

    return numbers


def _enclosed_numerals(chunk: str) -> List[int]:
    """Return the pin numbers for a chunk of enclosed/decorated numerals
    (e.g. circled "①②" -> [1, 2]), or [] when any character is not a
    plausible integer numeral."""
    values: List[int] = []
    for ch in chunk:
        value = unicodedata.numeric(ch, None)
        if value is None or value != int(value) or not (1 <= int(value) <= 300):
            return []
        values.append(int(value))
    return values


def _looks_like_pin_label(text: str) -> bool:
    normalized = _normalize_cell_text(text)
    if not normalized or is_non_pin_feature_name(normalized):
        return False

    upper = normalized.upper()
    if upper in _HEADER_STOPWORDS:
        return False

    # Voltage-rail names keep their sign ("V+", "V–", "VS-"); the compact
    # form below would strip it and leave a bare "V" that matches nothing.
    if re.fullmatch(r"V[A-Z]{0,2}\d?\s*[+\-−–]", upper):
        return True

    compact = re.sub(r"[^A-Z0-9/']+", "", upper)
    if not compact:
        return False

    compact_core = compact.strip("/")

    if compact in _KNOWN_PIN_LABELS or compact_core in _KNOWN_PIN_LABELS:
        return True

    if re.fullmatch(r"[A-Z]\d{1,2}", compact_core):
        return True

    if re.fullmatch(r"[A-Z]{2,6}\d{0,2}", compact_core):
        return True

    if "/" in normalized:
        parts = [
            re.sub(r"[^A-Z0-9']+", "", part.upper())
            for part in re.split(r"\s*/\s*", normalized)
            if part.strip()
        ]
        if len(parts) == 1 and parts[0] in _KNOWN_PIN_LABELS:
            return True
        if len(parts) >= 2 and all(
            part and len(part) <= 8 and re.fullmatch(r"[A-Z0-9']+", part)
            for part in parts
        ):
            return True

    return False


def _extract_pin_name(row: List[str]) -> str:
    for cell in row:
        if _looks_like_pin_label(cell):
            return _normalize_cell_text(cell)
    return ""


def _extract_function(pin_name: str) -> Optional[str]:
    upper = _normalize_cell_text(pin_name).upper()
    if not upper:
        return None

    rail = re.sub(r"[−–]", "-", upper).replace(" ", "")
    if re.fullmatch(r"V[A-Z]{0,2}\d?\+", rail):
        return "power"
    if re.fullmatch(r"V[A-Z]{0,2}\d?-", rail):
        return "ground"

    if upper in {"GND", "VSS", "AGND", "DGND", "PGND"}:
        return "ground"
    if upper in {"VCC", "VDD", "AVCC", "VLOGIC", "VIN", "VOUT", "REGOUT", "CPOUT"}:
        return "power"
    if upper in {"EN", "OE", "MR", "CLR", "RESET", "FSYNC", "CS"}:
        return "control"
    if upper in {"SDA", "SDI", "FB", "AD0", "CLKIN", "AUX_DA", "AUX_CL", "THRES", "DISCH"}:
        return "input"
    if upper in {"SDO", "OUT", "PG", "SW", "CLK", "SCL", "SCK", "MOSI", "MISO", "TRIG"}:
        return "output"
    if upper in {"NC", "RESV", "RESERVED"}:
        return "none"
    return None


def _infer_family(
    text_content: str, pin_count: int, part_number: Optional[str] = None
) -> Optional[str]:
    """Package family named in the page text, or None.

    Evidence, in order: an explicit family name ("SOIC"), then a TI
    mechanical designator header ("DSC PACKAGE" -> WSON). Never guesses
    from pin count: an invented family (e.g. "SOIC-9" for the TPS63060
    VSON) passes pin validation and renders wrong geometry. With no
    evidence the deterministic parser yields no candidate and the LLM
    path, whose output is validation-gated, takes over.
    """
    detector = PackageDetector()
    detected = detector._detect_from_text(text_content or "")  # pylint: disable=protected-access
    if detected:
        return detected
    return family_from_page_designators(text_content or "", part_number)


def _build_pin_data(
    page_number: int,
    pin_map: Dict[int, Pin],
    text_content: str,
    part_number: Optional[str],
    score_bonus: int = 0,
    family: Optional[str] = None,
) -> Optional[ParsedPinTableCandidate]:
    if not pin_map:
        return None

    pins = [pin_map[number] for number in sorted(pin_map)]
    if len(pins) < 4:
        return None

    family = family or _infer_family(text_content, len(pins), part_number)
    if not family:
        return None
    package_type = f"{family}-{len(pins)}"
    component_name = part_number or infer_part_number_hint(text_content) or "Unknown"

    pin_data = PinData(
        component_name=component_name,
        package=PackageInfo(
            type=package_type,
            pin_count=len(pins),
            width=0.0,
            height=0.0,
            pitch=None,
            thickness=None,
        ),
        pins=pins,
        selected_package_index=0,
        selected_package_type=package_type,
        selection_reason=(
            f"Deterministic table parser selected the pin table on page {page_number}"
        ),
        extraction_method="Table",
    )

    score = len(pins) * 10 + score_bonus
    return ParsedPinTableCandidate(page_number=page_number, score=score, pin_data=pin_data)


# Package family names as they appear in multi-package pin-table headers
# ("NAME | LCCC | SOIC, SOT23-8, VSSOP, CDIP, PDIP, SO, TSSOP | ...").
# Longer names precede their substrings so alternation matches whole tokens.
_FAMILY_HEADER_RE = re.compile(
    r"\b(?:LCCC|PLCC|TSSOP|VSSOP|SSOP|MSOP|SOIC|SOT-?23(?:-\d+)?|SOP|SO|"
    r"CDIP|PDIP|DIP|CFP|QFN|WSON|SON|DFN)\b"
)


def _package_pin_column(table: List[List[str]], family: Optional[str]) -> Optional[int]:
    """Column holding pin numbers for the target family, or None.

    Multi-package datasheets (e.g. LM358) print one pin-number column per
    package group. Taking numbers from the first numeric cell then reads the
    wrong package's numbering — the LCCC column alone yields 20 pins for an
    8-pin part. When a header row names families in two or more columns and
    exactly one matches the inferred family, pin numbers must come from that
    column only.
    """
    if not family:
        return None
    fam = re.sub(r"[^A-Z0-9]", "", family.upper())
    if not fam:
        return None

    for row in table[:4]:
        family_columns: Dict[int, List[str]] = {}
        for idx, cell in enumerate(row):
            tokens = [
                re.sub(r"[^A-Z0-9]", "", token)
                for token in _FAMILY_HEADER_RE.findall((cell or "").upper())
            ]
            if tokens:
                family_columns[idx] = tokens

        if len(family_columns) < 2:
            continue

        matches = [
            idx
            for idx, tokens in family_columns.items()
            if any(
                token == fam or token.startswith(fam) or token.endswith(fam)
                for token in tokens
            )
        ]
        if len(matches) == 1:
            return matches[0]

    return None


# Device-name tokens in table headers ("MCP3204" / "MCP3208").
_DEVICE_TOKEN_RE = re.compile(r"[A-Z]{2,}[0-9]{2,}[A-Z0-9]*")


def _part_number_pin_column(
    table: List[List[str]], part_number: Optional[str]
) -> Optional[int]:
    """Column holding pin numbers for the target device, or None.

    Shared-family datasheets (MCP3204/3208) print one pin-number column per
    device, headed by the device name rather than a package family. When a
    header row names devices in two or more columns and the part number
    matches exactly one, pin numbers must come from that column only.
    """
    if not part_number:
        return None
    pn = re.sub(r"[^A-Z0-9]", "", part_number.upper())
    if not pn:
        return None

    for row in table[:4]:
        device_columns: Dict[int, set] = {}
        for idx, cell in enumerate(row):
            for token in _DEVICE_TOKEN_RE.findall((cell or "").upper()):
                if len(token) >= 5:
                    device_columns.setdefault(idx, set()).add(token)

        if len(device_columns) < 2:
            continue

        matches = [
            idx
            for idx, tokens in device_columns.items()
            if any(pn.startswith(token) for token in tokens)
        ]
        if len(matches) == 1:
            return matches[0]

    return None


# TI per-package number column header: "PFB NO.", "RHB NO.", "D PIN NO.".
_DESIGNATOR_COLUMN_RE = re.compile(r"([A-Z]{1,4})\s+(?:PIN\s+)?NO\.?")


def _designator_pin_column(
    table: List[List[str]], part_number: Optional[str]
) -> Optional[int]:
    """Column holding pin numbers for the part's TI package designator, or None.

    TI tables print one number column per package, headed by the designator
    ("PFB NO. | FN NO. | RHB NO."). The orderable part number carries the
    same designator (TL16C2550PFBR -> PFB), so exactly one column matches.
    """
    designator = package_designator_from_part_number(part_number)
    if not designator:
        return None
    for row in table[:4]:
        columns: Dict[int, str] = {}
        for idx, cell in enumerate(row):
            match = _DESIGNATOR_COLUMN_RE.fullmatch((cell or "").upper().strip())
            if match:
                columns[idx] = match.group(1)
        if len(columns) < 2:
            continue
        matches = [idx for idx, token in columns.items() if token == designator]
        if len(matches) == 1:
            return matches[0]
    return None


# A name range inside one cell: "D0-D4", "D0–D4", "AIN1 to AIN6", "P7:P0".
_NAME_RANGE_RE = re.compile(
    r"([A-Z][A-Z_]*?)(\d+)\s*(?:-|–|—|TO|:)\s*([A-Z][A-Z_]*?)?(\d+)", re.IGNORECASE
)
_NUMBER_ITEM_RE = re.compile(r"(\d+)(?:\s*[-–—]\s*(\d+))?")


def _cell_items(raw) -> List[str]:
    """Comma/line-separated items of a raw cell ("CTSA,\\nCTSB" -> 2 items)."""
    return [item for item in re.split(r"\s*[,\n]\s*", str(raw or "").strip()) if item]


def _expand_name_item(item: str) -> Optional[List[str]]:
    match = _NAME_RANGE_RE.fullmatch(item)
    if match:
        prefix, start, other_prefix, end = match.groups()
        if other_prefix and other_prefix.upper() != prefix.upper():
            return None
        step = 1 if int(end) >= int(start) else -1
        return [f"{prefix}{n}" for n in range(int(start), int(end) + step, step)]
    if _looks_like_pin_label(item):
        return [_normalize_cell_text(item)]
    return None


def _expand_number_item(item: str) -> Optional[List[int]]:
    match = _NUMBER_ITEM_RE.fullmatch(item)
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else start
    step = 1 if end >= start else -1
    return list(range(start, end + step, step))


def _pair_grouped_cell(raw_names, raw_numbers) -> Optional[List[Tuple[int, str]]]:
    """Pair a grouped row's names with its numbers, or None when ambiguous.

    "CTSA, CTSB | 38, 23" and "D0-D4 / D5-D7 | 44 - 48 / 1 - 3" list names
    and numbers item for item, so they pair in printed order. Pairing only
    happens when both cells split into the same number of items AND each
    name item covers exactly as many pins as its number item. A range label
    against a scattered list ("GPO0 to GPO3 | 5, 6, 41, 42") does not line
    up, and its order is genuinely unreliable (ADV7180: pin 5 is GPO1), so
    it is left for the drawing-based repair.
    """
    name_items = _cell_items(raw_names)
    number_items = _cell_items(raw_numbers)
    if len(name_items) != len(number_items):
        return None
    names: List[str] = []
    numbers: List[int] = []
    for name_item, number_item in zip(name_items, number_items):
        expanded_names = _expand_name_item(name_item)
        expanded_numbers = _expand_number_item(number_item)
        if not expanded_names or not expanded_numbers:
            return None
        if len(expanded_names) != len(expanded_numbers):
            return None
        names.extend(expanded_names)
        numbers.extend(expanded_numbers)
    if len(numbers) < 2 or len(set(numbers)) != len(numbers):
        return None
    return list(zip(numbers, names))


def grouped_row_pairs(raw_row: List) -> List[Tuple[int, str]]:
    """Every (pin number, name) pairing a grouped table row states outright.

    Uses the same line-up rule as the parser (_pair_grouped_cell), trying each
    number cell against each other cell, so "D0-D4 / D5-D7 | 44 - 48 / 1 - 3"
    yields (46, "D2") and nothing for a range against a scattered list.
    """
    pairs: List[Tuple[int, str]] = []
    for number_idx, number_cell in enumerate(raw_row):
        if not number_cell or not _extract_pin_numbers(str(number_cell)):
            continue
        for name_idx, name_cell in enumerate(raw_row):
            if name_idx == number_idx or not name_cell:
                continue
            pairs.extend(_pair_grouped_cell(name_cell, number_cell) or [])
    return pairs


def _has_multiple_package_columns(table: List[List[str]]) -> bool:
    """True when a header row names packages/devices in two or more columns.

    Such tables carry one pin-number column per package (STM32's
    "BGA100 | LQFP48 | LQFP64 | LQFP100"); reading the first numeric cell
    per row mixes numbering schemes into garbage.
    """
    for row in table[:4]:
        columns = set()
        for idx, cell in enumerate(row):
            text = (cell or "").upper()
            if _FAMILY_HEADER_RE.search(text):
                columns.add(idx)
                continue
            for token in _DEVICE_TOKEN_RE.findall(text):
                if len(token) >= 5:
                    columns.add(idx)
                    break
        if len(columns) >= 2:
            return True
    return False


def _variant_column_index(table: List[List[str]], part_number: Optional[str]) -> Optional[int]:
    if not part_number:
        return None

    target_tokens = [token for token in re.findall(r"[A-Z0-9]+", part_number.upper()) if len(token) >= 3]
    if not target_tokens:
        return None

    blobs = _column_blobs(table, max_rows=4)
    best_index = None
    best_score = 0

    for idx, blob in enumerate(blobs):
        score = sum(1 for token in target_tokens if token in blob.upper())
        if score > best_score:
            best_score = score
            best_index = idx

    if best_score == 0:
        return None

    if best_index > 0:
        return best_index - 1

    return best_index


def _pair_grouped_row(
    raw_table: Optional[List[List]],
    row_index: int,
    number_column: Optional[int],
    pin_count: int,
) -> Optional[List[Tuple[int, str]]]:
    """Per-pin names for a grouped row, from its raw (line-preserving) cells.

    Tries each non-number cell as the name cell; see _pair_grouped_cell for
    when a pairing is trusted. None keeps the row's single-label behaviour.
    """
    if raw_table is None or number_column is None or pin_count < 2:
        return None
    raw_row = raw_table[row_index]
    if number_column >= len(raw_row):
        return None
    for idx, raw_cell in enumerate(raw_row):
        if idx == number_column or not raw_cell:
            continue
        pairs = _pair_grouped_cell(raw_cell, raw_row[number_column])
        if pairs and len(pairs) == pin_count:
            return pairs
    return None


def _parse_table_rows(
    table: List[List[str]],
    page_number: int,
    text_content: str,
    part_number: Optional[str],
    raw_table: Optional[List[List]] = None,
) -> Optional[ParsedPinTableCandidate]:
    variant_column = _variant_column_index(table, part_number)
    family = _infer_family(text_content, 0, part_number)
    package_pin_column = _package_pin_column(table, family)
    if package_pin_column is None:
        package_pin_column = _part_number_pin_column(table, part_number)
    designator_family = None
    if package_pin_column is None:
        package_pin_column = _designator_pin_column(table, part_number)
        if package_pin_column is not None:
            # The header and the part number name the same package designator,
            # which is better family evidence than a page listing several
            # packages ("TQFP (PFB) ... PLCC (FN) ... QFN (RHB)").
            designator_family = TI_DESIGNATOR_FAMILIES.get(
                package_designator_from_part_number(part_number)
            )
    if package_pin_column is None and _has_multiple_package_columns(table):
        # Multi-package table with no resolvable column (STM32's
        # BGA100/LQFP48/LQFP64/LQFP100): reading the first numeric cell
        # per row would mix numbering schemes. Yield no candidate and let
        # the validation-gated LLM path handle the document.
        return None
    pin_candidates: Dict[int, List[Pin]] = {}

    for row_index, row in enumerate(table):
        if not any(row):
            continue

        pin_numbers: List[int] = []
        number_column: Optional[int] = None
        if package_pin_column is not None:
            if package_pin_column < len(row):
                pin_numbers = _extract_pin_numbers(row[package_pin_column])
                number_column = package_pin_column
        else:
            for idx, cell in enumerate(row):
                cell_numbers = _extract_pin_numbers(cell)
                if cell_numbers:
                    pin_numbers = cell_numbers
                    number_column = idx
                    break

        if not pin_numbers:
            continue

        active_low_row = description_marks_active_low(" ".join(cell for cell in row if cell))
        grouped = _pair_grouped_row(raw_table, row_index, number_column, len(pin_numbers))
        if grouped:
            for number, name in grouped:
                pin_candidates.setdefault(number, []).append(
                    Pin(
                        number=number,
                        name=name,
                        function=_extract_function(name),
                        active_low=detect_active_low(name) or active_low_row,
                    )
                )
            continue

        # Fused "NAME NO." columns ("L2 10") hide the label: strip the
        # row's own pin numbers (standalone tokens only) before matching.
        number_strings = {str(n) for n in pin_numbers}
        stripped_row = [
            " ".join(tok for tok in cell.split() if tok not in number_strings)
            for cell in row
        ]
        pin_name = _extract_pin_name(stripped_row) or _extract_pin_name(row)
        if not pin_name:
            continue

        # Thermal/exposed pads without a pin number are already skipped above.
        # If is_non_pin_feature_name matches here, pin_numbers is guaranteed non-empty,
        # meaning the datasheet explicitly numbered this pad (e.g. QFN EP = pin 25).
        # Treat it as a real electrical pin — do not skip.

        function = _extract_function(pin_name)
        # Active-low: a printed marker on the name (overbar/slash/#/_N), or an
        # explicit "(active low)" anywhere in this pin's row (the description
        # cell), which survives extraction when the overbar is lost. Convention
        # alone (a bare "CS"/"RESET") is never enough — see pin_classifier.
        active_low = detect_active_low(pin_name) or active_low_row
        for number in pin_numbers:
            pin_candidates.setdefault(number, []).append(
                Pin(number=number, name=pin_name, function=function, active_low=active_low)
            )

    pin_map: Dict[int, Pin] = {}
    choose_last = bool(part_number and re.search(r"6050\b", part_number.upper()))
    for number, candidates in pin_candidates.items():
        if not candidates:
            continue
        pin_map[number] = candidates[-1] if choose_last and len(candidates) > 1 else candidates[0]

    return _build_pin_data(
        page_number=page_number,
        pin_map=pin_map,
        text_content=text_content,
        part_number=part_number,
        score_bonus=5 if variant_column is not None else 0,
        family=designator_family,
    )


def _raw_rows(table: List) -> List[List]:
    """Non-empty rows with cells kept raw (line breaks intact), aligned with
    _normalize_table's rows."""
    return [
        list(row)
        for row in table or []
        if any(_normalize_cell_text(cell) for cell in row)
    ]


def _shared_header_rows(table: List[List[str]], next_table: List[List[str]]) -> int:
    """Number of leading rows two tables share verbatim (a repeated header)."""
    count = 0
    for row, next_row in zip(table[:3], next_table[:3]):
        if row != next_row:
            break
        count += 1
    return count


def _pin_numbers(candidate: ParsedPinTableCandidate) -> set:
    return {int(pin.number) for pin in candidate.pin_data.pins}


def parse_pin_data_from_tables(
    content,
    part_number: Optional[str] = None,
) -> Optional[PinData]:
    """
    Attempt to extract PinData directly from structured pin tables.

    This is a conservative, rule-based parser used before the LLM. It works
    well for clean pin tables with explicit row data and will return None when
    the table structure looks ambiguous enough that the LLM should take over.
    """
    if not getattr(content, "tables", None):
        return None

    candidates: List[ParsedPinTableCandidate] = []
    text_content = getattr(content, "text_content", "") or ""

    def parse(page_number, normalized_table, raw_table):
        return _parse_table_rows(
            normalized_table,
            page_number=page_number,
            text_content=text_content,
            part_number=part_number,
            raw_table=raw_table,
        )

    parsed = []
    for page_number, table in content.tables:
        normalized_table = _normalize_table(table)
        if len(normalized_table) < 3:
            continue
        raw_table = _raw_rows(table)
        candidate = parse(page_number, normalized_table, raw_table)
        parsed.append((page_number, normalized_table, raw_table, candidate))
        if candidate:
            candidates.append(candidate)

    # A pin table continued onto the next page (TL16C2550: A0..RESET on p4,
    # RIA..XTAL2 on p5) is one table: merge it so neither half is chosen alone.
    merged = None
    for (page, norm, raw, cand), (next_page, next_norm, next_raw, next_cand) in zip(
        parsed, parsed[1:]
    ):
        if merged is None or merged[0] != page:
            merged = (page, norm, raw, cand)
        header_rows = _shared_header_rows(norm, next_norm)
        if (
            next_page == page + 1
            and header_rows
            and merged[3] is not None
            and next_cand is not None
            and not (_pin_numbers(merged[3]) & _pin_numbers(next_cand))
        ):
            merged_norm = merged[1] + next_norm[header_rows:]
            merged_raw = merged[2] + next_raw[header_rows:]
            merged_cand = parse(merged[0], merged_norm, merged_raw)
            if merged_cand:
                candidates.append(merged_cand)
            merged = (next_page, merged_norm, merged_raw, merged_cand)
        else:
            merged = None

    if not candidates:
        return None

    best_candidate = max(
        candidates,
        key=lambda candidate: (candidate.score, len(candidate.pin_data.pins), -candidate.page_number),
    )

    return best_candidate.pin_data
