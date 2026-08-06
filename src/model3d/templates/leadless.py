"""Leadless package-body template (QFN / DFN / WSON / SON ...).

Flush bottom-terminal families with no protruding gull-wing leads. The moulded
body sits on the seating plane (standoff A1 is ~0 for leadless) and spans
Z = A1 .. A. Terminals are small metallized lands on the UNDERSIDE of the body
at its edges: each land's bottom face lies on the seating plane (Z=0) and its
outer face aligns with a body edge.

DFN / SON / WSON are dual-row: terminal rows are separated along X (the
lead-span E axis) and pins run along Y at pitch e. QFN is four-sided. Sidedness
is driven by spec.pins_per_side = [left, right, top, bottom]; a side with count
0 gets no terminals. Numbering is counter-clockwise (JEDEC): pin 1 at the top of
the left column, down the left column, along the bottom (left -> right), up the
right column, then across the top (right -> left).
"""
from __future__ import annotations

from typing import List, Tuple

import cadquery as cq

from ..spec import Body3DSpec
from .base import PackageTemplate

# Default land (foot) length when the datasheet omits JEDEC symbol L.
DEFAULT_LAND_LENGTH = 0.40
# Default terminal (land) thickness in Z.
DEFAULT_TERMINAL_THICKNESS = 0.20

_BODY_COLOR = cq.Color(0.15, 0.15, 0.17)
_LEAD_COLOR = cq.Color(0.75, 0.75, 0.78)


def _lead_positions(n_side: int, pitch: float) -> List[float]:
    """Coordinates for one side's terminals, centred on the origin, first -> last."""
    return [((n_side - 1) / 2.0 - i) * pitch for i in range(n_side)]


def _pin_numbering(
    pins_per_side: List[int], pitch: float
) -> List[Tuple[int, float, str]]:
    """Counter-clockwise leadless numbering.

    pins_per_side is [left, right, top, bottom]. Returns (pin_number, coord,
    side) with side in {"L","R","T","B"}. coord is the along-side position: Y for
    left/right sides, X for top/bottom sides.
    """
    left, right, top, bottom = pins_per_side
    order: List[Tuple[int, float, str]] = []
    pin = 1
    # Left column: top -> bottom.
    for y in _lead_positions(left, pitch):
        order.append((pin, y, "L"))
        pin += 1
    # Bottom row: left -> right.
    for x in reversed(_lead_positions(bottom, pitch)):
        order.append((pin, x, "B"))
        pin += 1
    # Right column: bottom -> top.
    for y in reversed(_lead_positions(right, pitch)):
        order.append((pin, y, "R"))
        pin += 1
    # Top row: right -> left.
    for x in _lead_positions(top, pitch):
        order.append((pin, x, "T"))
        pin += 1
    return order


class LeadlessTemplate(PackageTemplate):
    lead_style = "leadless"

    def build(self, spec: Body3DSpec) -> cq.Assembly:
        A = spec.body_height_A
        A1 = spec.standoff_A1
        A2 = max(A - A1, 0.05)          # moulded body thickness
        E1 = spec.body_width_E1
        D = spec.body_length_D
        b = spec.lead_width_b
        L = spec.lead_foot_L or DEFAULT_LAND_LENGTH
        e = spec.lead_pitch_e
        t = DEFAULT_TERMINAL_THICKNESS

        asm = cq.Assembly()

        body = (
            cq.Workplane("XY")
            .box(E1, D, A2)
            .translate((0, 0, A1 + A2 / 2.0))
        )
        asm.add(body, name="Body", color=_BODY_COLOR)

        # Exposed thermal pad (D2 x E2) on the underside centre, bottom at Z=0,
        # when the extractor captured it. E2 runs along X, D2 along Y (matching
        # the E/D body axes). Skipped entirely when dims are absent.
        if spec.exposed_pad is not None:
            d2, e2 = spec.exposed_pad
            if d2 > 0 and e2 > 0:
                epad = (
                    cq.Workplane("XY")
                    .box(e2, d2, t)
                    .translate((0, 0, t / 2.0))
                )
                asm.add(epad, name="ExposedPad", color=_LEAD_COLOR)

        for pin, coord, side in _pin_numbering(spec.pins_per_side, e):
            lead = self._terminal(side, coord, E1, D, L, b, t)
            asm.add(lead, name=f"Lead_{pin}", color=_LEAD_COLOR)

        return asm

    @staticmethod
    def _terminal(
        side: str, coord: float, E1: float, D: float, L: float, b: float, t: float,
    ) -> cq.Workplane:
        """One flush bottom land: outer face on the body edge, bottom face at Z=0."""
        if side in ("L", "R"):
            s = -1.0 if side == "L" else 1.0
            # Land length L runs along X (inward from the body edge); width b in Y.
            x = s * (E1 / 2.0 - L / 2.0)
            return (
                cq.Workplane("XY")
                .box(L, b, t)
                .translate((x, coord, t / 2.0))
            )
        # Top / bottom rows: land length L runs along Y; width b in X.
        s = -1.0 if side == "B" else 1.0
        y = s * (D / 2.0 - L / 2.0)
        return (
            cq.Workplane("XY")
            .box(b, L, t)
            .translate((coord, y, t / 2.0))
        )
