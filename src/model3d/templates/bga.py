"""BGA / LGA grid-array package-body template.

Grid-array families place their terminals as a near-square 2-D grid of solder
balls (BGA) on the package UNDERSIDE, not as perimeter rows -- so the
spec.pins_per_side split is meaningless here and is ignored. Instead the grid is
derived from pin_count and the ball pitch e:

    cols = ceil(sqrt(pin_count)),  rows = ceil(pin_count / cols)

and pin_count balls are placed row-major, centred on the origin, so a
depopulated array (e.g. 63 balls in an 8x8 grid) still emits exactly pin_count
balls.

Geometry (shared coordinate contract: mm, +Z up, seating plane at Z=0, origin at
component centre): each solder ball is a sphere whose lowest point touches the
seating plane (ball centre at Z = ball_radius). The moulded body is a box
E1 (X) x D (Y) x A2 (Z) sitting above the balls, where A2 = A - A1 - ball_height
and the body underside is at Z = A1 + ball_height, so overall height is A.
"""
from __future__ import annotations

import math

import cadquery as cq

from ..spec import Body3DSpec
from .base import PackageTemplate

# Fallbacks so a build never divides by zero on missing dims.
DEFAULT_PITCH = 0.80
DEFAULT_HEIGHT = 1.00

_BODY_COLOR = cq.Color(0.15, 0.15, 0.17)
_BALL_COLOR = cq.Color(0.72, 0.72, 0.75)


def _grid_positions(pin_count: int, pitch: float):
    """Row-major (x, y) ball centres for a near-square grid centred on origin.

    Yields exactly pin_count positions filling cols = ceil(sqrt(pin_count))
    columns per row, top row first; a partly filled last row (depopulated grid)
    still yields pin_count positions.
    """
    cols = max(math.ceil(math.sqrt(pin_count)), 1)
    rows = max(math.ceil(pin_count / cols), 1)
    x0 = (cols - 1) / 2.0
    y0 = (rows - 1) / 2.0
    for i in range(pin_count):
        row, col = divmod(i, cols)
        x = (col - x0) * pitch
        y = (y0 - row) * pitch      # top row first (highest +Y)
        yield x, y


class BgaTemplate(PackageTemplate):
    lead_style = "bga"

    def build(self, spec: Body3DSpec) -> cq.Assembly:
        e = spec.lead_pitch_e or DEFAULT_PITCH
        A = spec.body_height_A or DEFAULT_HEIGHT
        A1 = spec.standoff_A1
        E1 = spec.body_width_E1 or (e * 4.0)
        D = spec.body_length_D or (e * 4.0)

        ball_d = spec.lead_width_b or (0.6 * e)
        ball_r = ball_d / 2.0
        ball_height = ball_d

        # Moulded body sits above the balls; body underside at A1 + ball_height.
        body_bottom = A1 + ball_height
        A2 = max(A - body_bottom, 0.05)

        asm = cq.Assembly()

        body = (
            cq.Workplane("XY")
            .box(E1, D, A2)
            .translate((0, 0, body_bottom + A2 / 2.0))
        )
        asm.add(body, name="Body", color=_BODY_COLOR)

        for pin, (x, y) in enumerate(_grid_positions(spec.pin_count, e), start=1):
            ball = (
                cq.Workplane("XY")
                .sphere(ball_r)
                .translate((x, y, ball_r))
            )
            asm.add(ball, name=f"Lead_{pin}", color=_BALL_COLOR)

        return asm
