"""Chip 2-terminal package-body template (SMD passives: R / C / L).

Surface-mount two-terminal chip components -- 0201, 0402, 0603, 0805, 1206.
A rectangular moulded/ceramic body spans the seating plane (Z = 0 .. A); two
metallized end caps wrap the body ends along X (the long, body-length D axis).
The end caps are the board terminals: Lead_1 at the -X end, Lead_2 at the +X
end. Terminals run the full body width (E1) and full height (A).
"""
from __future__ import annotations

import cadquery as cq

from ..spec import Body3DSpec
from .base import PackageTemplate

# Terminal band width as a fraction of body length when L is not supplied.
DEFAULT_BAND_FRACTION = 0.25

_BODY_COLOR = cq.Color(0.15, 0.15, 0.17)
_TERMINAL_COLOR = cq.Color(0.75, 0.75, 0.78)


class ChipTemplate(PackageTemplate):
    lead_style = "chip"

    def build(self, spec: Body3DSpec) -> cq.Assembly:
        D = spec.body_length_D
        E1 = spec.body_width_E1
        A = spec.body_height_A
        band = spec.lead_foot_L or DEFAULT_BAND_FRACTION * D

        asm = cq.Assembly()

        body = (
            cq.Workplane("XY")
            .box(D, E1, A)
            .translate((0, 0, A / 2.0))
        )
        asm.add(body, name="Body", color=_BODY_COLOR)

        for pin, s in ((1, -1.0), (2, 1.0)):
            cap = self._end_cap(s, D, E1, A, band)
            asm.add(cap, name=f"Lead_{pin}", color=_TERMINAL_COLOR)

        return asm

    @staticmethod
    def _end_cap(s: float, D: float, E1: float, A: float, band: float) -> cq.Workplane:
        """One end-cap terminal: full width/height, `band` deep from the X end."""
        return (
            cq.Workplane("XY")
            .box(band, E1, A)
            .translate((s * (D / 2.0 - band / 2.0), 0, A / 2.0))
        )
