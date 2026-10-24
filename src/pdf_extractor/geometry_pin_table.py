"""Geometry-based reader for "collapsed" pin tables.

Some datasheets (e.g. ADI AD9106) print the pin table as ``Pin No. | Mnemonic |
Description`` but PDF table detection collapses each whole column into a single
cell (``"1\\n2\\n...\\n32"``), which the row-based deterministic parser cannot
read. Here we recover rows from glyph geometry instead: pin numbers and mnemonics
that share a y-coordinate belong to the same pin. The overbar overline font
(``ZWAdobeF``) is dropped from names -- it is the active-low bar, flagged
separately -- so ``C̄S̄`` reads as ``CS``.

Used only as a fallback when the row-based parser finds nothing, so it never
disturbs datasheets that already parse cleanly.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

_OVERLINE_FONT = "ZWAdobeF"
_MNEMONIC_HEADERS = ("Mnemonic", "Signal", "Name", "Symbol")
_RIGHT_HEADERS = ("Description", "Function", "Type", "Direction", "I/O")
# A pin-number column header distinguishes a PIN table from a register/bit table
# (which use "Bit"/"Addr"/"Address" and must be ignored).
_PIN_NUM_HEADERS = ("Pin", "No.", "No", "Number", "Terminal", "Ball", "Pad")
_ROW_DY = 4.0  # pt; number and name on the same printed row


def _clean_chars_in(page, x0: float, x1: float, y_top: float) -> List[dict]:
    """Non-overline glyphs within an x-band, below the header y."""
    return [
        c for c in (page.chars or [])
        if _OVERLINE_FONT not in (c.get("fontname") or "")
        and x0 <= c["x0"] < x1
        and c["top"] > y_top
        and c.get("text", "").strip()
    ]


def _name_at(chars: List[dict], y: float) -> str:
    row = sorted(
        (c for c in chars if abs((c["top"] + c["bottom"]) / 2 - y) < _ROW_DY),
        key=lambda c: c["x0"],
    )
    # join in x-order, inserting a space only on a real gap
    text, prev = "", None
    for c in row:
        if prev is not None and c["x0"] - prev["x1"] > 0.3 * (prev["bottom"] - prev["top"]):
            text += " "
        text += c["text"]
        prev = c
    return text.strip()


def _page_pairs(page) -> List[Tuple[int, str]]:
    words = page.extract_words()
    header = {w["text"]: w for w in words}
    mnem = next((header[h] for h in _MNEMONIC_HEADERS if h in header), None)
    if mnem is None:
        return []
    # Must have a pin-number header to the LEFT of the mnemonic column, else this
    # is a register/bit table, not a pin table.
    if not any(h in header and header[h]["x0"] < mnem["x0"] for h in _PIN_NUM_HEADERS):
        return []
    right = next((header[h] for h in _RIGHT_HEADERS if h in header and header[h]["x0"] > mnem["x0"]), None)
    mx0 = mnem["x0"]
    nx1 = mx0 - 2.0                       # pin-number column: left of the mnemonic
    dx0 = (right["x0"] - 3.0) if right else (mx0 + 200.0)
    hy = mnem["bottom"]

    name_chars = _clean_chars_in(page, mx0 - 2.0, dx0, hy)
    pairs: List[Tuple[int, str]] = []
    for w in words:
        if w["x0"] >= nx1 or w["top"] <= hy or not w["text"].strip().isdigit():
            continue
        y = (w["top"] + w["bottom"]) / 2
        name = _name_at(name_chars, y)
        if _looks_like_pin_name(name):
            pairs.append((int(w["text"]), name))
    return pairs


def _looks_like_pin_name(name: str) -> bool:
    """A real mnemonic: has a letter, is short, and is not a table-of-contents
    leader (``Register Map ...... 13``) or prose."""
    if not name or len(name) > 20 or ".." in name:
        return False
    return bool(re.search(r"[A-Za-z]", name)) and " " not in name.strip()


def extract_geometry_pin_table(pages) -> Optional[List[Tuple[int, str]]]:
    """Merge pin (number, name) pairs across the given pdfplumber pages.

    Returns a sorted unique list only when it looks like a real pin table: at
    least 4 pins and a gap-free 1..N numbering. Otherwise None, so the caller
    falls back to the LLM.
    """
    merged: dict = {}
    for page in pages:
        try:
            text = page.extract_text() or ""
        except Exception:  # pragma: no cover
            continue
        if not any(h in text for h in _MNEMONIC_HEADERS):
            continue
        for num, name in _page_pairs(page):
            merged.setdefault(num, name)  # first page wins on duplicates

    if len(merged) < 4:
        return None
    numbers = sorted(merged)
    if numbers != list(range(1, len(numbers) + 1)):
        return None  # not a clean 1..N sequence -> don't trust it
    return [(n, merged[n]) for n in numbers]
