"""Dual-inline through-hole package-body template (DIP / PDIP / CDIP).

Unlike the surface-mount gull-wing families, DIP leads are straight blades that
pass DOWN THROUGH the board, so this geometry extends BELOW the seating plane:
the assembly's bounding-box zmin is negative (~ -3.0mm), by design. The moulded
body sits ABOVE the board on its standoff, spanning Z = A1 .. A. Lead columns are
separated along X (lead-span E axis); pins run along Y at pitch e. Pin numbering
is the same counter-clockwise dual-row scheme as the gull-wing template.
"""
from __future__ import annotations

from typing import List, Tuple

import cadquery as cq

from ..spec import Body3DSpec
from .base import PackageTemplate

# Default lead-blade thickness (JEDEC symbol c) when the datasheet omits it.
DEFAULT_LEAD_THICKNESS = 0.25
# How far a through-hole lead protrudes below the seating plane (Z=0), in mm.
LEAD_LENGTH_BELOW_BOARD = 3.0
# JEDEC-ish fallbacks when the spec leaves a value at 0 / absent.
DEFAULT_BODY_HEIGHT_A = 4.0
DEFAULT_STANDOFF_A1 = 0.38
DEFAULT_PITCH_E = 2.54
DEFAULT_LEAD_WIDTH_B = 0.46

_BODY_COLOR = cq.Color(0.15, 0.15, 0.17)
_LEAD_COLOR = cq.Color(0.75, 0.75, 0.78)


def _lead_y_positions(n_side: int, pitch: float) -> List[float]:
    """Y coordinates for one column, centred on the origin, top -> bottom."""
    return [((n_side - 1) / 2.0 - i) * pitch for i in range(n_side)]


def _pin_numbering(left: int, right: int, pitch: float) -> List[Tuple[int, float, str]]:
    """Counter-clockwise dual-row numbering.

    Pin 1 is top of the left column; numbers run down the left column, then up
    the right column. Returns (pin_number, y, side) with side in {"L","R"}.
    """
    order: List[Tuple[int, float, str]] = []
    pin = 1
    # Left column: top -> bottom.
    for y in _lead_y_positions(left, pitch):
        order.append((pin, y, "L"))
        pin += 1
    # Right column: bottom -> top.
    for y in reversed(_lead_y_positions(right, pitch)):
        order.append((pin, y, "R"))
        pin += 1
    return order


class DIPTemplate(PackageTemplate):
    lead_style = "through_hole"

    def build(self, spec: Body3DSpec) -> cq.Assembly:
        A = spec.body_height_A or DEFAULT_BODY_HEIGHT_A
        A1 = spec.standoff_A1 or DEFAULT_STANDOFF_A1
        A2 = max(A - A1, 0.05)          # moulded body thickness
        E = spec.lead_span_E
        E1 = spec.body_width_E1
        D = spec.body_length_D
        b = spec.lead_width_b or DEFAULT_LEAD_WIDTH_B
        e = spec.lead_pitch_e or DEFAULT_PITCH_E
        c = DEFAULT_LEAD_THICKNESS

        asm = cq.Assembly()

        body = (
            cq.Workplane("XY")
            .box(E1, D, A2)
            .translate((0, 0, A1 + A2 / 2.0))
        )
        asm.add(body, name="Body", color=_BODY_COLOR)

        left, right = spec.pins_per_side[0], spec.pins_per_side[1]
        for pin, y, side in _pin_numbering(left, right, e):
            s = -1.0 if side == "L" else 1.0
            lead = self._dip_lead(s, y, E, b, c, A1, A2)
            asm.add(lead, name=f"Lead_{pin}", color=_LEAD_COLOR)

        return asm

    @staticmethod
    def _dip_lead(
        s: float, y: float, E: float, b: float, c: float, A1: float, A2: float,
    ) -> cq.Workplane:
        """One straight DIP lead: a vertical blade from the body side down through
        the board to a tip at Z = -LEAD_LENGTH_BELOW_BOARD."""
        x = s * (E / 2.0)
        top_z = A1 + A2 / 2.0                 # lead exits the body mid-height
        bottom_z = -LEAD_LENGTH_BELOW_BOARD
        height = top_z - bottom_z
        return (
            cq.Workplane("XY")
            .box(c, b, height)
            .translate((x, y, bottom_z + height / 2.0))
        )
