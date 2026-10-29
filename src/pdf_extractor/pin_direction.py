"""Pin direction (electrical type) read from the datasheet's own pin-table rows.

The symbol layout places pins by role (inputs left; supplies, outputs, grounds
right — the SnapEDA guideline the QC re-check grades against). Most pins get no
role from their name alone (VOUTL, IOUTP1, SDO, VINR, AIN1 ...), so they all fell
to the left. The datasheet states the direction outright, in one of two forms:

* a type column after the name and pin number(s): ``XTAL1 13 18 10 I``,
  ``18 PVDD P PLL Supply Voltage (1.8 V).``
* a description whose first phrase names it: ``7 SDO Serial Data Output``,
  ``10 IOUTP4 DAC4 Current Output, Positive Side.``

Only a pin-table row shape is read — the pin's name next to pin number(s) — so
prose and pinout drawings ("TXA 7 30 INTA") yield nothing. Unclear wording yields
nothing too; the name classifier still applies downstream.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Tuple

# Type-column codes (TI "I/O", ADI "Type"). Value: (electrical_type, role).
# A role is only given where the code alone fixes it (ground). A power code
# ("P") says nothing about supply vs ground, so the caller lets the name decide.
_TYPE_CODES: Dict[str, Tuple[str, Optional[str]]] = {
    "I": ("input", None), "DI": ("input", None), "AI": ("input", None),
    "O": ("output", None), "DO": ("output", None), "AO": ("output", None),
    "I/O": ("bidirectional", None), "IO": ("bidirectional", None),
    "DIO": ("bidirectional", None), "AIO": ("bidirectional", None),
    "B": ("bidirectional", None),
    "OD": ("open_collector", None),
    "P": ("power_in", None), "PWR": ("power_in", None),
    "S": ("power_in", None),
    "G": ("power_in", "ground"), "GND": ("power_in", "ground"),
}
_NUMBERISH = re.compile(r"^[\d,–—\-]+$")
_POWER_DOWN = re.compile(r"power[\s-]*(down|up|good|on|off|save|saving|enable)", re.I)


def _strip(token: str) -> str:
    return token.strip(",;:()")


def _fold(text: str) -> str:
    """Upper-case with every dash/minus variant as ASCII "-" (printed "VA–")."""
    return re.sub("[‐-―−﹘﹣－]", "-", str(text or "")).upper()


def _name_in(token: str, name: str) -> bool:
    """True if ``token`` is the name, or a comma group that lists it (CDA,CDB)."""
    token, name = _fold(_strip(token)), _fold(name)
    return token == name or name in [t for t in re.split(r"[,/]", token) if t]


def _numbers_in(tokens: Iterable[str]) -> List[int]:
    return [int(n) for t in tokens for n in re.findall(r"\d+", t)]


def description_direction(text: str) -> Optional[Tuple[str, Optional[str]]]:
    """(electrical_type, role) from a description's first phrase, or None."""
    # First phrase: up to a sentence stop (not a decimal point, "1.8 V"), ";"
    # or "(". "Output enable" / "input enable" name a control, not a direction.
    clause = re.split(r"\.(?=\s|$)|[;(]", text, maxsplit=1)[0].lower()
    clause = re.sub(r"\b(output|input)[\s-]*enable", "enable", clause)
    if not clause.strip():
        return None
    if "adjust" in clause:
        return "passive", None   # full-scale/gain adjust terminals (FSADJ)
    if "ground" in clause:
        return "power_in", "ground"
    if "ldo" in clause or "regulator" in clause:
        return "power_out", "supply"
    if re.search(r"\b(supply|power)\s+output", clause):
        return "power_out", "supply"   # "Clock Power Supply Output" (CLDO)
    if "supply" in clause or (re.search(r"\bpower\b", clause) and not _POWER_DOWN.search(clause)):
        return "power_in", "supply"
    has_in = re.search(r"\binputs?\b", clause) is not None
    has_out = re.search(r"\boutputs?\b", clause) is not None
    if re.search(r"\binputs?\s*/\s*outputs?\b", clause) or (has_in and has_out):
        return "bidirectional", None
    if has_out:
        return "output", None
    if has_in:
        # "Mute Control Input", "Zero Crossing Enable Input", "Chip Select
        # Input": a control input, grouped with the controls at the upper left.
        if re.search(r"\b(control|enable|select)\b", clause):
            return "input", "control"
        return "input", None
    return None


def _is_to(token: str) -> bool:
    return token.lower() == "to"


def _take_numbers(tokens: List[str], k: int) -> Tuple[List[int], int]:
    """Pin-number cells from ``k``: "40, 16", "44-48", "5 to 10, 15, 16"."""
    numbers: List[int] = []
    while k < len(tokens):
        tok = _strip(tokens[k])
        if tok and _NUMBERISH.match(tok):
            numbers.extend(_numbers_in([tok]))
            k += 1
        elif (_is_to(tokens[k]) and numbers and k + 1 < len(tokens)
              and _NUMBERISH.match(_strip(tokens[k + 1]) or "x")):
            hi = _numbers_in([tokens[k + 1]])
            if hi:
                numbers.extend(range(numbers[-1] + 1, hi[0] + 1))
            k += 2
        else:
            break
    return numbers, k


_RANGE_ITEM = re.compile(r"^([A-Z]+)(\d+)\s+TO\s+([A-Z]+)?(\d+)$")


def _take_names(tokens: List[str], k: int) -> Tuple[List[str], int]:
    """A name cell from ``k``: one name, or a group the row lists together —
    "CDA, CDB", "GPO0 to GPO3", "P7 to P2, P1, P0" — expanded to its names.
    A group only continues across a trailing comma or a "to"."""
    if k >= len(tokens):
        return [], k
    group = [tokens[k]]
    k += 1
    while k < len(tokens):
        if _is_to(tokens[k]) and k + 1 < len(tokens):
            group += [tokens[k], tokens[k + 1]]
            k += 2
        elif (group[-1].endswith(",") and re.search(r"[A-Z]", tokens[k])
              and not re.search(r"[a-z]", tokens[k])
              and _strip(tokens[k]).upper() not in _TYPE_CODES):
            group.append(tokens[k])
            k += 1
        else:
            break
    names: List[str] = []
    for item in re.split(r"\s*,\s*", _fold(" ".join(group))):
        item = item.strip()
        m = _RANGE_ITEM.match(item)
        if m and (m.group(3) in (None, m.group(1))):
            a, b = int(m.group(2)), int(m.group(4))
            step = 1 if b >= a else -1
            names.extend(f"{m.group(1)}{n}" for n in range(a, b + step, step))
        elif item:
            names.extend(t for t in re.split(r"[/]", _strip(item)) if t)
            names.append(_strip(item))
    return names, k


def _row_direction(tokens: List[str], name: str, number: int):
    """(rank, (etype, role)) when the line is a pin-table row for this pin.

    rank: 0 = type code on a row stating this pin number, 1 = description on such
    a row, 2/3 = the same on a row for another package's number (the signal's
    direction does not depend on the package). None if not a row for the pin.
    A row may list a group of signals ("5, 6, 41, 42 GPO0 to GPO3 O ..."): one
    direction for all of them, so no name has to be paired with a number.
    """
    parts = _row_parts(tokens, name, number)
    if parts is None:
        return None
    own, rest = parts
    if rest and _strip(rest[0]).upper() in _TYPE_CODES:
        return (0 if own else 2), _TYPE_CODES[_strip(rest[0]).upper()]
    if len(rest) >= 2:
        found = description_direction(" ".join(rest))
        if found:
            return (1 if own else 3), found
    return None


def _row_parts(tokens: List[str], name: str, number: int):
    """(own_number, remaining tokens) when the line is a pin-table row naming
    ``name`` (number(s) then name, or name then number column(s)); else None."""
    if not tokens:
        return None
    target = _fold(name)
    if _NUMBERISH.match(_strip(tokens[0])) and _strip(tokens[0]):
        # "10 IOUTP4 ..." / "5 to 10, 15, 16 P7 to P2, P1, P0 O ...":
        # number(s) first, then the name (group).
        numbers, i = _take_numbers(tokens, 0)
        names, j = _take_names(tokens, i)
    else:
        # "XTAL1 13 18 10 I ..." / "CDA, CDB 40, 16 ...": the name (group),
        # then one number column per package.
        names, i = _take_names(tokens, 0)
        numbers, j = _take_numbers(tokens, i)
        if j == i:
            return None
    if target not in names:
        return None
    return number in numbers, tokens[j:]


_TYPE_HEADER = re.compile(r"^(I/O|IO|TYPE|PIN TYPE|DIR(ECTION)?)(\s*\(\d+\))?$", re.I)
_DESC_HEADER = re.compile(r"^(DESCRIPTION|FUNCTION)(\s*\(\d+\))?$", re.I)


def table_directions(tables) -> Dict[str, Tuple[str, Optional[str]]]:
    """{folded pin name: (etype, role)} from tables with an I/O / TYPE column
    (or, lacking one, a DESCRIPTION column). Grouped name cells ("CDA, CDB",
    "D0-D4") give every listed signal the row's direction."""
    from .deterministic_table_parser import _cell_items, _expand_name_item

    out: Dict[str, Tuple[str, Optional[str]]] = {}
    for _page, table in tables or []:
        rows = [[str(c or "").strip() for c in (r or [])] for r in (table or [])]
        type_col = desc_col = None
        start = 0
        for h, row in enumerate(rows[:3]):
            for c, cell in enumerate(row):
                flat = " ".join(cell.split())
                if type_col is None and _TYPE_HEADER.match(flat):
                    type_col, start = c, h + 1
                if desc_col is None and _DESC_HEADER.match(flat):
                    desc_col, start = c, max(start, h + 1)
        if type_col is None and desc_col is None:
            continue
        name_cols = range(0, min(c for c in (type_col, desc_col) if c is not None))

        def direction(type_text: str, desc_text: str):
            found = _TYPE_CODES.get(_strip(type_text).upper()) if type_text else None
            if found is None and desc_text:
                found = description_direction(desc_text)
            return found

        for row in rows[start:]:
            cell = lambda c: row[c] if c is not None and c < len(row) else ""
            for c in name_cols:
                if c >= len(row) or not re.search(r"[A-Za-z]", row[c]):
                    continue
                # A name cell may wrap a group ("CTSA,\nCTSB"); a cell holding
                # several separate entries is a collapsed column (whole table
                # in one row) and pairs line-by-line only when the type /
                # description cell has exactly as many lines.
                entries = re.split(r"(?<!,)\s*\n\s*", row[c].strip())
                if len(entries) == 1:
                    pairs = [(entries[0], direction(cell(type_col), cell(desc_col)))]
                else:
                    t_lines = cell(type_col).split("\n") if type_col is not None else []
                    d_lines = cell(desc_col).split("\n") if desc_col is not None else []
                    if len(t_lines) == 1 and t_lines[0].strip():
                        # One type for the whole cell ("D0-D4 / D5-D7 | I/O").
                        found = direction(t_lines[0], "")
                        pairs = [(e, found) for e in entries]
                    elif len(t_lines) == len(entries):
                        pairs = [(e, direction(t, "")) for e, t in zip(entries, t_lines)]
                    elif len(d_lines) == len(entries):
                        pairs = [(e, direction("", d)) for e, d in zip(entries, d_lines)]
                    else:
                        continue
                for entry, found in pairs:
                    if found is None:
                        continue
                    for item in _cell_items(entry):
                        for name in _expand_name_item(item) or []:
                            out.setdefault(_fold(name), found)
    return out


def read_pin_direction(name: str, number: int, lines: Iterable[str]):
    """(electrical_type, role) for one pin from the best pin-table row, or None."""
    if not name or number is None:
        return None
    best = None
    for line in lines:
        hit = _row_direction(line.split(), name, int(number))
        if hit and (best is None or hit[0] < best[0]):
            best = hit
            if best[0] == 0:
                break
    return best[1] if best else None


def apply_pin_directions(pins, source_text: str, tables=None) -> int:
    """Fill each pin's electrical_type (and a datasheet-stated supply/ground
    role) from the pin table: a structured table's I/O / TYPE column first,
    else the pin's row in ``source_text``. Fill-only for the type; returns how
    many pins gained a type."""
    from ..models.pin_classifier import classify_pin_name

    lines = [ln for ln in (source_text or "").split("\n") if ln.strip()]
    by_table = table_directions(tables)
    filled = 0
    for pin in pins or []:
        get = (lambda k: pin.get(k)) if isinstance(pin, dict) else (lambda k: getattr(pin, k, None))

        def put(k, v):
            if isinstance(pin, dict):
                pin[k] = v
            else:
                setattr(pin, k, v)

        found = by_table.get(_fold(get("name") or "")) or read_pin_direction(
            get("name"), get("number"), lines)
        if not found:
            continue
        etype, role = found
        c_type, c_role, _ = classify_pin_name(get("name") or "")
        if etype == "power_in" and role is None:
            # A bare power code ("P"): AGND is a ground, PVDD a supply.
            role = "ground" if c_role == "ground" else "supply"
        if etype == "power_in" and c_type == "power_out":
            etype = "power_out"  # a regulator output the part sources (CLDO)
        if not get("electrical_type"):
            put("electrical_type", etype)
            filled += 1
        elif etype == c_type == "power_out" and get("electrical_type") != "power_out":
            # The datasheet row and the name both say regulator output: that
            # beats an earlier guess (QC AD9106 SCH-05: CLDO came as bidirectional).
            put("electrical_type", etype)
        if role and not get("role"):
            put("role", role)
    return filled


def propagate_channel_siblings(pins) -> int:
    """Fill a pin's missing direction / active-low from its A/B channel twin.

    Dual-channel parts name a signal per channel (RTSA/RTSB, CSA/CSB, TXA/TXB)
    and the datasheet documents them in one grouped row ("RTSA, RTSB ... O",
    "Chip select A/B (active low)"). A run that types only one channel (TL16C2550:
    the B-channel came back with no direction, so RTSB/DTRB sat on the input
    side) leaves the twin unspecified. Only a missing type / role / active-low is
    filled, from a twin that differs by the last letter alone (A<->B) with a
    base of at least two letters; nothing is ever overwritten. Returns the number
    of pins changed.
    """
    def get(p, k):
        return p.get(k) if isinstance(p, dict) else getattr(p, k, None)

    def put(p, k, v):
        if isinstance(p, dict):
            p[k] = v
        else:
            setattr(p, k, v)

    by_name = {}
    for pin in pins or []:
        name = _fold(get(pin, "name") or "")
        by_name.setdefault(name, []).append(pin)
    changed = 0
    for pin in pins or []:
        name = _fold(get(pin, "name") or "")
        if len(name) < 3 or name[-1] not in "AB" or not name[-2].isalpha():
            continue
        twins = by_name.get(name[:-1] + ("B" if name[-1] == "A" else "A"), [])
        if len(twins) != 1:
            continue
        twin, hit = twins[0], False
        for key in ("electrical_type", "role"):
            if not get(pin, key) and get(twin, key):
                put(pin, key, get(twin, key))
                hit = True
        if get(twin, "active_low") and not get(pin, "active_low"):
            put(pin, "active_low", True)
            hit = True
        changed += hit
    return changed


def apply_active_low_from_rows(pins, source_text: str) -> int:
    """Flag a pin active-low when its own pin-table row says so ("32 TRIGGER
    Pattern Trigger Input, Active Low."; "8 CS SPI Port Chip Select, Active Low.").

    The printed overbar is lost in plain text, and ADI's sometimes uses no
    overline font, but the description states it (AD9106 CS/RESET/TRIGGER stayed
    unmarked, QC A5). Only a row stating this pin's own number counts; the flag is
    only ever added. Returns the number of pins newly flagged.
    """
    from ..models.pin_classifier import description_marks_active_low

    lines = [ln.split() for ln in (source_text or "").split("\n") if ln.strip()]
    flagged = 0
    for pin in pins or []:
        get = (lambda k: pin.get(k)) if isinstance(pin, dict) else (lambda k: getattr(pin, k, None))
        if get("active_low") or not get("name") or get("number") is None:
            continue
        for tokens in lines:
            parts = _row_parts(tokens, get("name"), int(get("number")))
            if parts and parts[0] and len(parts[1]) >= 2 and description_marks_active_low(" ".join(parts[1])):
                if isinstance(pin, dict):
                    pin["active_low"] = True
                else:
                    pin.active_low = True
                flagged += 1
                break
    return flagged
