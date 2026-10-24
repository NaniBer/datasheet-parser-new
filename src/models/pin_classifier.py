"""Fill-only pin-name classifier (Slice A.2).

Maps a pin NAME to (electrical_type, role, active_low) using the extraction
output contract's vocabulary. Deliberately conservative: only high-confidence
name patterns resolve to a concrete value; anything ambiguous returns None so it
stays "unspecified"/"other" downstream — it never guesses.

active_low is NAME-MARKER only (trailing # or *, leading /, leading/trailing ~,
_N suffix, combining overbar). Convention-only inversion (e.g. OE, RESET without
a printed marker) is intentionally NOT inferred.

Consumed fill-only in ComponentRecord.from_pin_data: it only fills fields the
LLM/datasheet left empty and never overrides an existing value.
"""
import re
from typing import Optional, Tuple

_OVERBAR = ("̅", "̄")  # combining overline / macron
_SUPPLY = ("VCC", "VDD", "AVCC", "AVDD", "VDDA", "VBAT", "VDDIO")
_GROUND = ("GND", "VSS", "AGND", "DGND", "VSSA")
_ACTIVE_LOW_DESC = re.compile(r"active[\s_-]*low", re.IGNORECASE)


def description_marks_active_low(text) -> bool:
    """True if a pin's description/function text explicitly says "(active low)"
    / "active-low".

    This is the one active-low signal that survives PDF text extraction when the
    printed overbar is lost (e.g. TI "chip-select input (active low)" arriving as
    a bare name "CS" with no marker). It is explicit printed evidence, not a
    convention guess, so flagging from it stays within the "never infer" rule.
    """
    if not text:
        return False
    return bool(_ACTIVE_LOW_DESC.search(str(text)))


def _compact(name: str) -> str:
    """Uppercase, unify minus signs, drop punctuation except + and -."""
    n = (name or "").upper().replace("–", "-").replace("−", "-")
    return re.sub(r"[^A-Z0-9+\-]", "", n)


def detect_active_low(name: str) -> bool:
    """Conservative active-low: explicit printed markers only.

    Recognised markers are the notations a datasheet prints on an active-low
    pin name:
      - trailing ``#`` or ``*``           (``CS#``, ``RESET*``)
      - leading ``/`` or leading/trailing ``~``  (``/CS``, ``~CS``, ``CS~``)
      - ``_N``/``_n`` suffix               (``RESET_N``)
      - a combining overbar/macron on any character (``W̅E̅``)

    Convention-only inversion (``OE``, ``RESET`` with no printed marker) is
    deliberately NOT inferred — a bare name whose overbar was lost in
    extraction stays active-high here (that is an upstream extraction gap,
    not a classifier gap).
    """
    if not name:
        return False
    n = name.strip()
    return (
        n.endswith("#")
        or n.endswith("*")
        or n.startswith("/")
        or n.startswith("~")
        or n.endswith("~")
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
    # Supply rails: VCC/VDD families (opt. analog/digital prefix + suffix such as
    # VDDIO/AVDD/DVDD), positive rails V+/VA+/VD+, plus the legacy family list.
    if (
        _family(c, _SUPPLY)
        or re.match(r"^[AD]?V(DD|CC)[A-Z0-9]*$", c)
        or re.match(r"^A?V[A-Z]*\+$", c)
        or c == "V+"
    ):
        return "power_in", "supply", active_low
    # Grounds / negative rails: GND families with channel suffix (AGNDR/AGNDL),
    # VSS families, and negative rails V-/VA-/VD-.
    if (
        _family(c, _GROUND)
        or re.match(r"^[ADP]?GND[A-Z0-9]*$", c)
        or re.match(r"^VSS[A-Z0-9]*$", c)  # require the V: bare "SS" is SPI slave-select, not ground
        or re.match(r"^A?V[A-Z]*-$", c)
        or c == "V-"
    ):
        return "power_in", "ground", active_low
    # Regulator / LDO outputs the part sources (CLDO, DLDO1, AVDD_LDO): power_out.
    if re.match(r"^[A-Z]{0,4}LDO\d*$", c):
        return "power_out", "supply", active_low
    # Adjust/set and sense pins (FSADJ, VADJ, CAL_SENSE, ISENSE): high-impedance
    # analog terminals, not driven signals -> passive/analog.
    if "ADJ" in c or "SENSE" in c:
        return "passive", "analog", active_low
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
    # SD/MMC/SDIO data lines (DAT0..DAT3, CD/DAT3) and command line drive both
    # ways -> bidirectional. CLK on these buses stays input (handled above).
    if re.match(r"^(CD)?DAT\d+$", c) or c == "CMD":
        return "bidirectional", "data", active_low
    if re.match(r"^A\d+$", c):
        return "input", "address", active_low
    if re.match(r"^D\d+$", c):
        return "input", "data", active_low
    if re.match(r"^P[A-Z]\d+", c):
        return "bidirectional", "io", active_low

    return None, None, active_low  # ambiguous -> stay unspecified/other (no guess)
