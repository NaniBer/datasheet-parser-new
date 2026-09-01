"""Functional pin grouping for schematic symbols (spec SYM-04, Slice C.4b).

Turns per-pin functional roles into a ``side -> ordered pin numbers`` layout so a
symbol reads by function. Under the SnapEDA convention (QC S1) every pin sits in
the LEFT or RIGHT column: the right column carries power/outputs/ground/thermal
(VCC upper, outputs middle, GND lower); the left column carries control, inputs,
I/O, data/analog and other. The result is fed through the existing
custom-layout channel in ``pin_layout._layout_custom_pins``; a blank slot is
represented by ``None`` and consumes one grid step without drawing a pin.

Gating lives in ``models.functional_layout_applicable`` (concrete power + ground
and >= 50% concrete roles). Parts below the gate never reach this module and keep
their legacy physical layout byte-for-byte. See docs/extraction-output-contract.md
and the Sub-step 4 decision doc for the design rationale (Decisions A2 and B).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models import normalize_role, role_side
from ..package_types.package_geometry import SCHEMATIC_GRID_MM, _snap_up_even

# Canonical within-side role-block order (Decision A2). Pins are emitted in this
# block order, one blank grid slot between consecutive non-empty blocks, and
# sorted by pin number within a block (pin numbers are incidental to grouping).
BLOCK_ORDER: Dict[str, List[str]] = {
    "left":   ["control", "clock", "reset", "enable", "address",
               "oscillator", "input", "io", "data", "analog", "other"],
    "right":  ["supply", "output", "ground", "thermal"],
    "top":    [],
    "bottom": [],
}

_MIN_BODY_MM = 4 * SCHEMATIC_GRID_MM   # floor so a tiny part still renders a body
_NAME_CHAR_W = 0.6                     # ~char width per font unit (matches label bbox math)
_CENTRE_GAP_SLOTS = 2                  # grid cols kept clear between inside-drawn L/R names


def _num(pin: Dict[str, Any]) -> str:
    return str(pin.get("number"))


def _pin_num_key(n: str) -> int:
    digits = "".join(ch for ch in str(n) if ch.isdigit())
    return int(digits) if digits else 0


def _is_nc(pin: Dict[str, Any]) -> bool:
    """A pin is a no-connect if flagged, or its role resolves to ``nc``."""
    return bool(pin.get("nc")) or normalize_role(pin.get("role")) == "nc"


def functional_side_layout(pins: List[Dict[str, Any]]) -> Dict[str, List[Optional[str]]]:
    """Build ``side -> [pin-number | None]`` (``None`` = one blank grid slot).

    Role-block order per side (Decision A2), one blank between blocks, NC pins
    clustered as a trailing block at the bottom of the LEFT column (SnapEDA keeps
    the right column clean power/outputs/ground), then the shorter of each
    opposing pair is centred by leading blank padding so both sides share one
    grid lattice (Decision B).
    """
    layout: Dict[str, List[Optional[str]]] = {"left": [], "right": [], "top": [], "bottom": []}

    nc_pins = [p for p in pins if _is_nc(p)]
    placed = [p for p in pins if not _is_nc(p)]

    # Bucket placed pins by side -> role.
    buckets: Dict[str, Dict[str, List[Dict[str, Any]]]] = {s: {} for s in layout}
    for p in placed:
        r = normalize_role(p.get("role")) or "other"
        side = role_side(normalize_role(p.get("role")))   # unknown/other -> "left"
        buckets.setdefault(side, {}).setdefault(r, []).append(p)

    # Emit each side in canonical block order, one blank between non-empty blocks.
    for side, order in BLOCK_ORDER.items():
        for role in order:
            block = sorted(buckets[side].get(role, []), key=lambda p: _pin_num_key(_num(p)))
            if not block:
                continue
            if layout[side]:
                layout[side].append(None)
            layout[side].extend(_num(p) for p in block)

    # NC cluster: trailing block, never dropped (V-01 / SYM-11). SnapEDA keeps
    # the right column clean (power/outputs/ground), so NC pins trail at the
    # BOTTOM of the LEFT column instead of top/bottom (now unused).
    if nc_pins:
        target = "left"
        if layout[target]:
            layout[target].append(None)
        layout[target].extend(_num(p) for p in sorted(nc_pins, key=lambda p: _pin_num_key(_num(p))))

    _centre_pair(layout, "left", "right")
    _centre_pair(layout, "top", "bottom")
    return layout


def _centre_pair(layout: Dict[str, List[Optional[str]]], a: str, b: str) -> None:
    """Leading-blank-pad the shorter of two opposing sides (floor-division)."""
    n = max(len(layout[a]), len(layout[b]))
    for side in (a, b):
        pad = (n - len(layout[side])) // 2
        if pad:
            layout[side] = [None] * pad + layout[side]


def size_functional_body(
    layout: Dict[str, List[Optional[str]]],
    pins: List[Dict[str, Any]],
    params,
) -> None:
    """Resize ``params.body_width/height`` from the grouped layout (Decision B).

    Height comes from the taller of left/right (slots incl. blanks); width from
    the wider of the top/bottom pin span and — when names are drawn inside the
    body — the combined left+right name text plus a centre gap. Both are snapped
    to an even grid multiple so the symmetric-about-origin geometry stays on the
    2.54 mm grid. Mutates ``params`` in place (called before the body/labels are
    built from these dims).
    """
    grid = params.pin_pitch                         # 2.54 after grid normalization
    top_margin = params.body_geometry.top_margin

    v = max(len(layout["left"]), len(layout["right"]), 1)
    params.body_height = _snap_up_even((v - 1) * grid + 2 * top_margin)

    h = max(len(layout["top"]), len(layout["bottom"]))
    top_span = (h - 1) * grid + 2 * top_margin if h > 0 else 0.0

    # SnapEDA columns can be tall and narrow; the conformance side heuristic
    # (schematic_extras._pin_side) classifies a pin as top/bottom rather than
    # left/right once its vertical offset from the body centre exceeds its
    # horizontal one. The extreme pin of the tallest column sits at +/-((v-1)/2)*grid
    # vertically, so keep the body at least that wide — the pins then extend a
    # further pin-length beyond the body edge, landing unambiguously on their
    # column side regardless of float noise in the body centre.
    column_floor = (v - 1) * grid

    text_w = 0.0
    if params.pin_geometry.pin_name_offset < 0:     # names drawn INSIDE the body
        name_by_num = {_num(p): str(p.get("name") or "") for p in pins}
        size = params.pin_geometry.pin_name_size

        def side_name_w(side: str) -> float:
            names = [name_by_num.get(n, "") for n in layout[side] if n]
            return max((len(s) for s in names), default=0) * size * _NAME_CHAR_W

        text_w = side_name_w("left") + side_name_w("right") + _CENTRE_GAP_SLOTS * grid

    params.body_width = _snap_up_even(max(top_span, text_w, _MIN_BODY_MM, column_floor))


def apply_functional_layout(pins: List[Dict[str, Any]], params) -> Dict[str, List[Optional[str]]]:
    """Compute the functional layout and resize ``params`` to fit it."""
    layout = functional_side_layout(pins)
    size_functional_body(layout, pins, params)
    return layout
