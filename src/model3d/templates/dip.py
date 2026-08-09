"""Dual-inline through-hole package-body template (DIP / PDIP / CDIP).

Unlike the surface-mount gull-wing families, DIP leads are straight blades that
pass DOWN THROUGH the board, so this geometry extends BELOW the seating plane:
the assembly's bounding-box zmin is negative (~ -3.0mm), by design. The moulded
body sits ABOVE the board on its standoff, spanning Z = A1 .. A. Lead columns are
separated along X (lead-span E axis); pins run along Y at pitch e. Pin numbering
is the same counter-clockwise dual-row scheme as the gull-wing template.

Lead form (SPLAY). A real DIP lead does not drop straight from the body wall to
the tip: it exits the moulded body at the body-width (E1) wall, then steps
OUTWARD below the shoulder so the tips seat at the mounting row spacing E (E > E1
for a standard 300-mil DIP). We model that as a shouldered/stepped blade -- an
upper stub at the body-exit width, a short horizontal shoulder, and a lower pin
at the seated row spacing E -- rather than a single straight blade. The lead FEET
(the lowest -Z face the validator reads) still land at +/- E/2 so the through-
hole row spacing matches the spec, while the tip row spacing is now wider than
the body's lead exit -- i.e. the leads genuinely splay outward.

Note on vendor STEP fidelity: some vendor DIP STEP models keep leads in their
manufactured OVER-splayed state (tip spread eB > E) with long drawn leads. We
model the SEATED convention (feet at E, JEDEC lead length L below the board),
which is what the footprint/validator contract expects; the residual difference
to an over-splayed vendor model is a convention difference, not a build error.
"""
from __future__ import annotations

from typing import List, Tuple

import cadquery as cq

from ..spec import Body3DSpec
from .base import PackageTemplate

# Default lead-blade thickness (JEDEC symbol c) when the datasheet omits it.
DEFAULT_LEAD_THICKNESS = 0.25
# How far a through-hole lead protrudes below the seating plane (Z=0), in mm,
# when the datasheet gives no usable lead length L. JEDEC DIP L is ~3.0-3.3mm.
LEAD_LENGTH_BELOW_BOARD = 3.0
# Smallest lead-foot L (mm) we trust as a real through-hole protrusion. Below
# this we treat L as absent/gull-wing-ish and fall back to the default; this
# keeps the protrusion parametric (driven by the datasheet) without letting a
# tiny surface-mount L collapse the leads.
MIN_THROUGH_HOLE_L = 1.5
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


def _protrusion_below_board(spec: Body3DSpec) -> float:
    """How far the lead protrudes below the seating plane (mm), parametric.

    Uses the datasheet lead length L when it is a plausible through-hole value,
    otherwise the JEDEC-ish default. Keeps the Z profile driven by the spec
    rather than a single hard-coded constant.
    """
    L = spec.lead_foot_L or 0.0
    return L if L >= MIN_THROUGH_HOLE_L else LEAD_LENGTH_BELOW_BOARD


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
        below = _protrusion_below_board(spec)

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
            lead = self._dip_lead(s, y, E, E1, b, c, A1, A2, below)
            asm.add(lead, name=f"Lead_{pin}", color=_LEAD_COLOR)

        return asm

    @staticmethod
    def _dip_lead(
        s: float, y: float, E: float, E1: float, b: float, c: float,
        A1: float, A2: float, below: float,
    ) -> cq.Workplane:
        """One shouldered/splayed DIP lead.

        The lead exits the moulded body at the body-width wall (+/- E1/2), steps
        outward across a short shoulder, and drops as a straight pin to the tip
        at the seated row spacing (+/- E/2), Z = -below. Built as the union of an
        upper stub, a horizontal shoulder, and a lower pin so the tip keeps a
        single well-defined bottom (-Z) face at +/- E/2 for the validator.
        """
        tip_x = s * (E / 2.0)
        # Body-exit width: at the body wall, and never wider than the tip so the
        # step is always outward (a genuine splay). Falls back to the tip when
        # the body width is missing (degenerate straight blade).
        exit_half = min(E1 / 2.0, E / 2.0) if E1 and E1 > 0 else E / 2.0
        exit_x = s * exit_half

        top_z = A1 + A2 / 2.0                 # lead exits the body mid-height
        bottom_z = -below
        z_step = min(A1, top_z)               # splay/step just above the board

        # Upper stub: at the body-exit width, from the shoulder up into the body.
        upper_h = max(top_z - z_step, c)
        upper = (
            cq.Workplane("XY")
            .box(c, b, upper_h)
            .translate((exit_x, y, z_step + upper_h / 2.0))
        )
        # Lower pin: at the seated row spacing, from the shoulder down through
        # the board to the tip. This solid owns the lowest (-Z) face.
        lower_h = z_step - bottom_z
        lower = (
            cq.Workplane("XY")
            .box(c, b, lower_h)
            .translate((tip_x, y, bottom_z + lower_h / 2.0))
        )
        # Shoulder: horizontal blade bridging the exit width and the row spacing.
        span = abs(tip_x - exit_x) + c
        shoulder = (
            cq.Workplane("XY")
            .box(span, b, c)
            .translate(((exit_x + tip_x) / 2.0, y, z_step))
        )
        return upper.union(shoulder).union(lower)
