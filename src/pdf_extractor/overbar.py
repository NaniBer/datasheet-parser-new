"""Recover active-low pin names printed with an overbar.

Datasheets (ADI, TI, ...) draw the active-low overbar with a zero-width Adobe
overline font (``ZWAdobeF``): a glyph pair -- an overline *start* cap ("A") and
an overline *end* cap ("E") -- X-aligned with the pin name on the same text
line. ``pdfplumber``/``pymupdf`` flatten this into stray characters
(``CS`` -> ``CSEE``, ``TRIGGER`` -> ``ATRIGGER E``), destroying the signal, so a
pin like AD9106's T̄R̄Ī̄ḠḠ̄Ē̄R̄ -- whose only active-low marking is the overbar, with
no "(active low)" prose -- is otherwise lost.

We read the overbar back from the glyphs' font + geometry (the overline's x-span
over the name on the same line). This is explicit printed evidence, not a guess
from a bare name, so it stays within the "never infer from convention" rule.
"""
from __future__ import annotations

import re
from typing import Set

_OVERLINE_FONT = "ZWAdobeF"  # the subset prefix varies, e.g. "LXBUYC+ZWAdobeF"
_MAX_OVERBAR_WIDTH = 60.0     # pt; a single pin name's overbar is short -- guards
                              # against a wide inline list collapsing into one span
_SAME_LINE_DY = 9.0           # pt; name glyphs sit on the overline's text line


def _norm(text: str) -> str:
    return re.sub(r"[^A-Z0-9/+]", "", (text or "").upper())


def overbarred_names(page) -> Set[str]:
    """Return the normalized pin names on a pdfplumber ``page`` that carry a
    ZWAdobeF overbar. Empty set when the page uses no overline font (the common
    case) or on any extraction error -- callers treat it as "no extra signal"."""
    try:
        chars = page.chars or []
    except Exception:  # pragma: no cover - defensive against odd page objects
        return set()

    overline = [c for c in chars if _OVERLINE_FONT in (c.get("fontname") or "")]
    if not overline:
        return set()
    normal = [c for c in chars if _OVERLINE_FONT not in (c.get("fontname") or "")]

    # The start/end caps are emitted twice each; dedupe by (text, x, line).
    seen, caps = set(), []
    for c in overline:
        key = (c.get("text"), round(c["x0"]), round(c["top"]))
        if key in seen:
            continue
        seen.add(key)
        caps.append(c)

    starts = [c for c in caps if c.get("text") == "A"]
    ends = [c for c in caps if c.get("text") == "E"]

    names: Set[str] = set()
    used_ends = set()
    for start in sorted(starts, key=lambda c: (c["top"], c["x0"])):
        # nearest end cap to the right, on the same overline, within one pin width
        candidates = [
            e for e in ends
            if id(e) not in used_ends
            and 0.5 < e["x0"] - start["x0"] <= _MAX_OVERBAR_WIDTH
            and abs(e["top"] - start["top"]) <= 8.0
        ]
        if not candidates:
            continue
        end = min(candidates, key=lambda e: e["x0"] - start["x0"])
        used_ends.add(id(end))

        overline_y = (start["top"] + end["top"]) / 2.0
        glyphs = sorted(
            (
                c for c in normal
                if start["x0"] - 0.5 <= (c["x0"] + c["x1"]) / 2.0 <= end["x0"] + 0.5
                and abs(c["top"] - overline_y) <= _SAME_LINE_DY
            ),
            key=lambda c: c["x0"],
        )
        name = _norm("".join(c.get("text", "") for c in glyphs))
        if 2 <= len(name) <= 24:
            names.add(name)
    return names


def matches_overbarred(pin_name: str, overbar_names: Set[str]) -> bool:
    """True if ``pin_name`` corresponds to one of the overbarred names.

    Tolerates the common extractor truncation (e.g. the LLM returning "TRIG" for
    "TRIGGER"): an exact normalized match, or a prefix match when both names are
    at least 4 chars (so "TRIG" matches "TRIGGER" but "CS" never matches "CSA").
    """
    pin = _norm(pin_name)
    if not pin:
        return False
    for ob in overbar_names:
        if pin == ob:
            return True
        if min(len(pin), len(ob)) >= 4 and (pin.startswith(ob) or ob.startswith(pin)):
            return True
    return False
