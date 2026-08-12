"""Gull-wing package-body template (SOIC / SOP / SSOP / TSSOP / QFP ...).

Milestone 1 covers dual-row gull-wing families. Leads sit on the seating plane
(Z=0) and rise to the moulded body, which spans Z = A1 .. A. Lead columns are
separated along X (lead-span E axis); pins run along Y at pitch e.
"""
from __future__ import annotations

import logging
from typing import List, Tuple

import cadquery as cq

from ..spec import Body3DSpec
from .base import PackageTemplate

logger = logging.getLogger(__name__)

# Default lead-frame thickness (JEDEC symbol c) when the datasheet omits it.
DEFAULT_LEAD_THICKNESS = 0.20

# Detail-feature sizes (mm). Each is applied fail-open: if the OCCT op raises,
# the plain geometry is kept, so a detail failure never breaks a build. Radii are
# clamped against the local geometry so they stay well inside validator
# tolerances (span +/-0.15, length +/-0.10, height +/-0.05).
BODY_CHAMFER = 0.20          # top/bottom moulded-body bevel
PIN1_DIMPLE_R = 0.30         # pin-1 index dimple radius
PIN1_DIMPLE_DEPTH = 0.15     # pin-1 index dimple depth
LEAD_FILLET = 0.08           # gull-wing bend radius

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


class GullwingTemplate(PackageTemplate):
    lead_style = "gullwing"

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

        asm = cq.Assembly()

        body = self._build_body(E1, D, A2, A1)
        asm.add(body, name="Body", color=_BODY_COLOR)

        left, right = spec.pins_per_side[0], spec.pins_per_side[1]
        for pin, y, side in _pin_numbering(left, right, e):
            s = -1.0 if side == "L" else 1.0
            lead = self._gullwing_lead(s, y, E, E1, L, b, c, A1, A2)
            asm.add(lead, name=f"Lead_{pin}", color=_LEAD_COLOR)

        return asm

    @staticmethod
    def _build_body(E1: float, D: float, A2: float, A1: float) -> cq.Workplane:
        """Moulded body: a box with top/bottom perimeter chamfers and a pin-1
        index dimple. Each detail is fail-open (falls back to the plain box).

        Built centred at Z=0 (top at +A2/2), then lifted onto the standoff A1.
        Chamfers cut the top/bottom rim inward, so the base stays E1 x D and the
        top stays at +A2/2 -- overall span/length/height are preserved.
        """
        body = cq.Workplane("XY").box(E1, D, A2)

        # Top + bottom perimeter chamfer (the classic SOIC moulded bevel).
        chamfer = min(BODY_CHAMFER, 0.4 * A2, 0.2 * min(E1, D))
        if chamfer > 0.01:
            try:
                body = body.edges(">Z").chamfer(chamfer).edges("<Z").chamfer(chamfer)
            except Exception:  # OCCT edge-op failure -> keep the plain box
                logger.debug("body chamfer skipped", exc_info=True)
                body = cq.Workplane("XY").box(E1, D, A2)

        # Pin-1 index dimple on the top face, near the pin-1 corner (x<0, y>0),
        # kept clear of the chamfered rim so it lands on the flat top.
        r_d = min(PIN1_DIMPLE_R, 0.15 * min(E1, D))
        depth = min(PIN1_DIMPLE_DEPTH, 0.3 * A2)
        if r_d > 0.05 and depth > 0.02:
            try:
                margin = chamfer + r_d + 0.20
                px = -(E1 / 2.0 - margin)
                py = D / 2.0 - margin
                dimple = (
                    cq.Workplane("XY")
                    .cylinder(depth, r_d)
                    .translate((px, py, A2 / 2.0 - depth / 2.0))
                )
                body = body.cut(dimple)
            except Exception:
                logger.debug("pin-1 dimple skipped", exc_info=True)

        return body.translate((0, 0, A1 + A2 / 2.0))

    @staticmethod
    def _gullwing_lead(
        s: float, y: float, E: float, E1: float, L: float, b: float,
        c: float, A1: float, A2: float,
    ) -> cq.Workplane:
        """One gull-wing lead: shoulder (at body) -> riser -> foot (on board)."""
        tip = s * (E / 2.0)
        knee = s * (E / 2.0 - L)
        body_edge = s * (E1 / 2.0)
        shoulder_z = A1 + A2 * 0.5           # lead exits the body mid-height

        # Foot: flat on the seating plane, from knee out to the tip.
        foot = (
            cq.Workplane("XY")
            .box(L, b, c)
            .translate((s * (E / 2.0 - L / 2.0), y, c / 2.0))
        )
        lead = foot

        # Riser: vertical run at the knee, from the foot up to shoulder height.
        riser_h = shoulder_z - c
        if riser_h > 0:
            riser = (
                cq.Workplane("XY")
                .box(c, b, riser_h)
                .translate((knee, y, c + riser_h / 2.0))
            )
            lead = lead.union(riser)

        # Shoulder: horizontal from the body side out to the knee.
        shoulder_len = abs(knee - body_edge)
        if shoulder_len > 1e-6:
            shoulder = (
                cq.Workplane("XY")
                .box(shoulder_len, b, c)
                .translate(((knee + body_edge) / 2.0, y, shoulder_z))
            )
            lead = lead.union(shoulder)

        # Round the gull-wing profile: fillet the edges running along Y (the two
        # bends, the foot tip and the shoulder root). Fail-open -> sharp lead.
        radius = min(LEAD_FILLET, 0.4 * c, 0.3 * b)
        if radius > 0.01:
            try:
                lead = lead.edges("|Y").fillet(radius)
            except Exception:  # OCCT fillet failure -> keep the sharp union
                logger.debug("lead fillet skipped", exc_info=True)

        return lead
