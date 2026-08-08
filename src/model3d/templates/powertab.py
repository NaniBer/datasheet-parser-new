"""Power-tab package-body template (TO-220 / DPAK(TO-252) / D2PAK(TO-263)).

These parts are a moulded plastic body fused to a metal heat-sink tab plus a
small number of leads (usually 3, sometimes 2 or 5/7 for multi-lead variants).
This template models the TO-220 THROUGH-HOLE style: the leads exit the front
(-Y) face and run straight DOWN through the board, so -- like the DIP template
-- the assembly's bounding-box zmin is negative by design. The moulded body
stands on its A1 standoff (Z = A1 .. A) and the metal tab protrudes in +Y with a
mounting hole cut through its thickness (Z). DPAK/D2PAK are the surface-mount
cousins of the same drawing; this first cut targets the TO-220 through-hole form.

Axis contract (shared coordinate frame: mm, +Z up, seating plane Z=0, origin at
component centre): body width E1 -> X (leads spread along X at pitch e), body
depth D -> Y (the tab reaches further back in +Y), body height A -> Z.
"""
from __future__ import annotations

from typing import List

import cadquery as cq

from ..spec import Body3DSpec
from .base import PackageTemplate

# How far a through-hole lead protrudes below the seating plane (Z=0), in mm.
LEAD_LENGTH_BELOW_BOARD = 3.0
# Lead-blade thickness (front-to-back, Y) when the datasheet omits it.
DEFAULT_LEAD_THICKNESS = 0.5

# JEDEC-ish fallbacks for a standing TO-220 when the spec leaves a value at 0.
DEFAULT_BODY_WIDTH_E1 = 10.0     # X, across the leads
DEFAULT_BODY_DEPTH_D = 4.5       # Y, front-to-back of the moulded body
DEFAULT_BODY_HEIGHT_A = 9.0      # Z, standing height
DEFAULT_STANDOFF_A1 = 2.5        # body stands this far above the board
DEFAULT_PITCH_E = 2.54
DEFAULT_LEAD_WIDTH_B = 0.9

# Metal heat-sink tab.
TAB_THICKNESS = 0.5              # plate thickness (Z)
TAB_PROTRUSION_Y = 6.0          # how far the tab reaches beyond the body (+Y)
TAB_BODY_OVERLAP_Y = 1.0        # how far the tab bites back into the body (-Y)
TAB_WIDTH_MARGIN = 1.0          # tab is E1 minus this on each of X (total)
TAB_HOLE_DIAMETER = 3.6         # TO-220 mounting-hole diameter

_BODY_COLOR = cq.Color(0.15, 0.15, 0.17)
_METAL_COLOR = cq.Color(0.75, 0.75, 0.78)


def _lead_x_positions(pin_count: int, pitch: float) -> List[float]:
    """X coordinates for the leads, centred on the origin, left -> right."""
    return [(i - (pin_count - 1) / 2.0) * pitch for i in range(pin_count)]


class PowerTabTemplate(PackageTemplate):
    """Parametric TO-220/DPAK/D2PAK power-tab body generator."""

    lead_style = "power_tab"

    def build(self, spec: Body3DSpec) -> cq.Assembly:
        E1 = spec.body_width_E1 or DEFAULT_BODY_WIDTH_E1
        D = spec.body_length_D or DEFAULT_BODY_DEPTH_D
        A = spec.body_height_A or DEFAULT_BODY_HEIGHT_A
        A1 = spec.standoff_A1 or DEFAULT_STANDOFF_A1
        A2 = max(A - A1, 0.05)              # moulded body thickness (Z)
        e = spec.lead_pitch_e or DEFAULT_PITCH_E
        b = spec.lead_width_b or DEFAULT_LEAD_WIDTH_B
        c = DEFAULT_LEAD_THICKNESS
        pin_count = max(int(spec.pin_count or 0), 1)

        asm = cq.Assembly()

        # --- Moulded body: box E1 (X) x D (Y) x A2 (Z), standing on A1. --------
        body = (
            cq.Workplane("XY")
            .box(E1, D, A2)
            .translate((0, 0, A1 + A2 / 2.0))
        )
        asm.add(body, name="Body", color=_BODY_COLOR)

        # --- Metal heat-sink tab: flat plate protruding in +Y, hole in Z. -----
        asm.add(self._tab(E1, D, A), name="Tab", color=_METAL_COLOR)

        # --- Leads: exit the front (-Y) face, drop straight through the board. -
        top_z = A1 + A2 / 2.0              # lead exits the body mid-height
        bottom_z = -LEAD_LENGTH_BELOW_BOARD
        y_front = -D / 2.0
        for n, x in enumerate(_lead_x_positions(pin_count, e), start=1):
            lead = self._lead(x, y_front, b, c, top_z, bottom_z)
            asm.add(lead, name=f"Lead_{n}", color=_METAL_COLOR)

        return asm

    @staticmethod
    def _tab(E1: float, D: float, A: float) -> cq.Workplane:
        """A thin metal plate flush with the body top, protruding in +Y, with a
        mounting hole cut through its thickness."""
        tab_width = max(E1 - TAB_WIDTH_MARGIN, TAB_HOLE_DIAMETER + 1.0)
        y_start = D / 2.0 - TAB_BODY_OVERLAP_Y
        y_end = D / 2.0 + TAB_PROTRUSION_Y
        tab_len_y = y_end - y_start
        y_center = (y_start + y_end) / 2.0
        z_center = A - TAB_THICKNESS / 2.0        # flush with the body top

        # Mounting-hole centre: out in the protruding region, on the axis.
        hole_y = D / 2.0 + TAB_PROTRUSION_Y * 0.6
        hole_r = min(TAB_HOLE_DIAMETER / 2.0, tab_width / 2.0 - 0.3, tab_len_y / 2.0 - 0.3)

        tab = (
            cq.Workplane("XY")
            .box(tab_width, tab_len_y, TAB_THICKNESS)
            .translate((0, y_center, z_center))
        )
        if hole_r > 0:
            hole = (
                cq.Workplane("XY")
                .circle(hole_r)
                .extrude(TAB_THICKNESS * 2.0)
                .translate((0, hole_y, z_center - TAB_THICKNESS))
            )
            tab = tab.cut(hole)
        return tab

    @staticmethod
    def _lead(
        x: float, y_front: float, b: float, c: float, top_z: float, bottom_z: float,
    ) -> cq.Workplane:
        """One straight lead: a vertical blade at the front face running from the
        body down through the board to a tip at Z = -LEAD_LENGTH_BELOW_BOARD."""
        height = top_z - bottom_z
        return (
            cq.Workplane("XY")
            .box(b, c, height)
            .translate((x, y_front, bottom_z + height / 2.0))
        )
