"""Fill-only pin-name classifier (Slice A.2).

Maps a pin NAME to (electrical_type, role, active_low) using the extraction
output contract's vocabulary. Deliberately conservative: only high-confidence
name patterns resolve to a concrete value; anything ambiguous returns None so it
stays "unspecified"/"other" downstream — it never guesses.

active_low is NAME-MARKER only (trailing #, leading /, _N suffix, overbar).
Convention-only inversion (e.g. OE, RESET without a printed marker) is
intentionally NOT inferred.

Consumed fill-only in ComponentRecord.from_pin_data: it only fills fields the
LLM/datasheet left empty and never overrides an existing value.
"""
import re
from typing import Optional, Tuple

_OVERBAR = ("̅", "̄")  # combining overline / macron
_SUPPLY = ("VCC", "VDD", "AVCC", "AVDD", "VDDA", "VBAT", "VDDIO")
_GROUND = ("GND", "VSS", "AGND", "DGND", "VSSA")


def _compact(name: str) -> str:
    """Uppercase, unify minus signs, drop punctuation except + and -."""
    n = (name or "").upper().replace("–", "-").replace("−", "-")
    return re.sub(r"[^A-Z0-9+\-]", "", n)


def detect_active_low(name: str) -> bool:
    """Conservative active-low: explicit printed markers only."""
    if not name:
        return False
    n = name.strip()
    return (
        n.endswith("#")
        or n.startswith("/")
        or n.upper().endswith("_N")
        or any(ch in n for ch in _OVERBAR)
    )


def _family(compact: str, families) -> bool:
    """True if compact is a family token, optionally with a trailing index."""
    for f in families:
        if compact == f:
            return True
        if compact.startswith(f) and compact[len(f):].isdigit():
            return True
    return False


def classify_pin_name(name: str) -> Tuple[Optional[str], Optional[str], bool]:
    """Return (electrical_type, role, active_low); None where ambiguous."""
    active_low = detect_active_low(name)
    c = _compact(name)
    if not c:
        return None, None, active_low

    if c in {"NC", "DNC", "NOCONNECT", "RESERVED", "DNU"}:
        return "no_connect", "nc", active_low
    if c in {"EP", "EPAD", "PAD", "THERMAL", "THERMALPAD", "EXPOSEDPAD"}:
        return "passive", "thermal", active_low
    if _family(c, _SUPPLY) or c == "V+":
        return "power_in", "supply", active_low
    if _family(c, _GROUND) or c == "V-":
        return "power_in", "ground", active_low
    if re.match(r"^N?(RST|RESET|MR|SRCLR)(\d|[_/#].*)?$", c):
        return "input", "reset", active_low
    if "XTAL" in c or "OSC" in c:
        if "OUT" in c or c.endswith("2"):
            return "output", "oscillator", active_low
        return "input", "oscillator", active_low
    if re.search(r"(SRCLK|RCLK|SCLK|CLK)", c):
        return "input", "clock", active_low
    if re.match(r"^EN(ABLE)?(\d|[_/#].*)?$", c):
        return "input", "enable", active_low
    if re.match(r"^(OE|CE|CS|WE|RD|WR)(\d|[_/#].*)?$", c):
        return "input", "control", active_low
    if c.startswith("Q"):
        return "output", "data", active_low
    if re.match(r"^(OUT|DOUT|DO)(\d|[_/].*)?$", c):
        return "output", "output", active_low
    if re.match(r"^(DIN|SER|DATA)(\d|[_/].*)?$", c):
        return "input", "data", active_low
    if re.match(r"^A\d+$", c):
        return "input", "address", active_low
    if re.match(r"^D\d+$", c):
        return "input", "data", active_low
    if re.match(r"^P[A-Z]\d+", c):
        return "bidirectional", "io", active_low

    return None, None, active_low  # ambiguous -> stay unspecified/other (no guess)
