"""Quad gull-wing package-body template (QFP / TQFP / LQFP ...).

Four-sided generalization of the dual-row gull-wing template. Leads emerge from
all four faces of the moulded body and sit on the seating plane (Z=0). Body
spans Z = A1 .. A. Left/right lead columns are separated along X (E axis) with
pins running along Y; top/bottom rows are separated along Y (D axis) with pins
running along X -- the same gull-wing foot->riser->shoulder profile rotated 90.

Y-axis span choice: the E axis is fully specified (lead span E, body width E1),
so its per-side lead overhang is (E - E1) / 2. The datasheet gives D as the
overall Y extent (tip-to-tip), matching the validator, so the top/bottom foot
tips sit at +/- D/2 and the Y bounding box equals D. The Y-direction body edge
is derived by subtracting the same overhang: D1 = D - (E - E1). Equivalently the
Y span is D1 + (E - E1), i.e. body length plus the identical E-axis overhang. For
a square QFP (D == E) this yields a square body and a Y span equal to E.
"""
from __future__ import annotations

from typing import List, Tuple

import cadquery as cq

from ..spec import Body3DSpec
from .base import PackageTemplate

# Default lead-frame thickness (JEDEC symbol c) when the datasheet omits it.
DEFAULT_LEAD_THICKNESS = 0.20

_BODY_COLOR = cq.Color(0.15, 0.15, 0.17)
_LEAD_COLOR = cq.Color(0.75, 0.75, 0.78)


def _lead_line_positions(n_side: int, pitch: float) -> List[float]:
    """Along-side coordinates for one row/column, centred on the origin.

    Ordered most-positive -> most-negative (top -> bottom for a column running
    along Y, right -> left for a row running along X).
    """
    return [((n_side - 1) / 2.0 - i) * pitch for i in range(n_side)]


def _pin_numbering(
    pins_per_side: List[int], pitch: float
) -> List[Tuple[int, str, float]]:
    """Counter-clockwise QFP numbering.

    ``pins_per_side`` is ``[left, right, top, bottom]``. Pin 1 is the top of the
    LEFT side; numbers run DOWN the left side, ALONG the bottom (left -> right),
    UP the right side, then ACROSS the top (right -> left). Returns
    ``(pin_number, side, along_coord)`` with side in {"L", "R", "T", "B"} and
    ``along_coord`` the position on the side's varying axis (Y for L/R, X for
    T/B).
    """
    left, right, top, bottom = pins_per_side
    order: List[Tuple[int, str, float]] = []
    pin = 1

    # Left column: top -> bottom (Y descending).
    for y in _lead_line_positions(left, pitch):
        order.append((pin, "L", y))
        pin += 1
    # Bottom row: left -> right (X ascending).
    for x in reversed(_lead_line_positions(bottom, pitch)):
        order.append((pin, "B", x))
        pin += 1
    # Right column: bottom -> top (Y ascending).
    for y in reversed(_lead_line_positions(right, pitch)):
        order.append((pin, "R", y))
        pin += 1
    # Top row: right -> left (X descending).
    for x in _lead_line_positions(top, pitch):
        order.append((pin, "T", x))
        pin += 1

    return order


class QuadGullwingTemplate(PackageTemplate):
    lead_style = "quad_gullwing"

    def build(self, spec: Body3DSpec) -> cq.Assembly:
        A = spec.body_height_A
        A1 = spec.standoff_A1
        A2 = max(A - A1, 0.05)          # moulded body thickness
        E = spec.lead_span_E
        E1 = spec.body_width_E1
        D = spec.body_length_D
        b = spec.lead_width_b
        L = spec.lead_foot_L
        e = spec.lead_pitch_e
        c = DEFAULT_LEAD_THICKNESS

        # Same per-side lead overhang on both axes; derive the Y body edge (D1)
        # so the Y-side leads reuse the E-axis overhang and the Y span equals D.
        overhang = (E - E1)
        D1 = max(D - overhang, 0.05)

        asm = cq.Assembly()

        body = (
            cq.Workplane("XY")
            .box(E1, D1, A2)
            .translate((0, 0, A1 + A2 / 2.0))
        )
        asm.add(body, name="Body", color=_BODY_COLOR)

        for pin, side, along in _pin_numbering(spec.pins_per_side, e):
            if side in ("L", "R"):
                s = -1.0 if side == "L" else 1.0
                lead = self._gullwing_lead("x", s, along, E, E1, L, b, c, A1, A2)
            else:
                s = -1.0 if side == "B" else 1.0
                lead = self._gullwing_lead("y", s, along, D, D1, L, b, c, A1, A2)
            asm.add(lead, name=f"Lead_{pin}", color=_LEAD_COLOR)

        return asm

    @staticmethod
    def _gullwing_lead(
        axis: str, s: float, u: float, span: float, body_dim: float, L: float,
        b: float, c: float, A1: float, A2: float,
    ) -> cq.Workplane:
        """One gull-wing lead: shoulder (at body) -> riser -> foot (on board).

        ``axis`` is the direction the lead extends: "x" for left/right columns,
        "y" for top/bottom rows. ``s`` is the side sign (-1/+1), ``u`` the fixed
        perpendicular coordinate (Y for x-axis leads, X for y-axis leads).
        ``span`` is the tip-to-tip extent along ``axis`` and ``body_dim`` the
        body edge along ``axis``.
        """
        knee = s * (span / 2.0 - L)
        body_edge = s * (body_dim / 2.0)
        shoulder_z = A1 + A2 * 0.5           # lead exits the body mid-height

        def place(along_len: float, z_h: float, along_c: float, z_c: float):
            if axis == "x":
                box = cq.Workplane("XY").box(along_len, b, z_h)
                return box.translate((along_c, u, z_c))
            box = cq.Workplane("XY").box(b, along_len, z_h)
            return box.translate((u, along_c, z_c))

        # Foot: flat on the seating plane, from the knee out to the tip.
        lead = place(L, c, s * (span / 2.0 - L / 2.0), c / 2.0)

        # Riser: vertical run at the knee, from the foot up to shoulder height.
        riser_h = shoulder_z - c
        if riser_h > 0:
            lead = lead.union(place(c, riser_h, knee, c + riser_h / 2.0))

        # Shoulder: horizontal from the body side out to the knee.
        shoulder_len = abs(knee - body_edge)
        if shoulder_len > 1e-6:
            lead = lead.union(
                place(shoulder_len, c, (knee + body_edge) / 2.0, shoulder_z)
            )

        return lead
