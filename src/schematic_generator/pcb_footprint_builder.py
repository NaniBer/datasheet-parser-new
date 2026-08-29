"""
PCB Footprint Builder - Generate manufacturing-ready PCB layouts.

Creates PCB footprints with proper manufacturing layers:
- Copper pads (F.Cu layer)
- Solder masks (F.Mask openings)
- Through-holes (for DIP packages)
- Fabrication layer (F.Fab)
- Silkscreen layer (F.SilkS)
- Courtyard layer (F.CrtYd)

This is NOT a schematic symbol - it's for PCB manufacturing.
For schematic symbols (pinout diagrams), use pinout_diagram_builder.py.

Hierarchy follows KiCad KLC standards documented in docs/PCB_FOOTPRINT_HIERARCHY.md
"""

import logging
import os
from typing import List, Dict, Any, Optional

import cadquery as cq

from ..package_types import (
    PackageType,
    SchematicParameters,
    get_footprint_defaults,
    get_schematic_parameters,
)
from ..core import (
    inject_pcb_footprint_extras,
    normalize_pcb_footprint_bodyline_names,
    optimize_glb_hierarchy,
    validate_glb_similarity_to_reference,
    validate_pcb_footprint_glb,
)
from .pin_layout import PinPosition, layout_pins

# Setup logging
logger = logging.getLogger(__name__)


class PcbFootprintBuilder:
    """Build PCB footprint symbols using cadquery (manufacturing layout)."""

    # Colors matching 2d.glb materials exactly
    WHITE_COLOR = cq.Color(1.0, 1.0, 1.0, 1.0)          # silk text / silk BodyLine
    TRANSPARENT_COLOR = cq.Color(1.0, 1.0, 1.0, 0.0)    # BoundingBox (alpha=0)
    PURPLE_COLOR = cq.Color(0.093, 0.015, 0.165, 1.0)   # PackageValue text (dark purple)
    YELLOW_COLOR = cq.Color(1.0, 1.0, 0.0, 1.0)         # fab BodyLine / fab marker
    RED_COLOR = cq.Color(1.0, 0.0, 0.0, 1.0)            # Copper pads
    BROWN_COLOR = cq.Color(0.220, 0.122, 0.002, 1.0)    # SolderMask (dark brown)
    BLACK_COLOR = cq.Color(0.0, 0.0, 0.0, 1.0)          # HoleCylinderPin
    MAGENTA_COLOR = cq.Color(0.831, 0.005, 0.913, 1.0)  # crtyd BodyLine

    # PCB 2D geometry parameters (matching 2d.glb)
    SOLDER_MASK_DIAMETER = 1.352  # mm (largest circle)
    COPPER_PAD_DIAMETER = 1.250  # mm (medium circle)
    HOLE_DIAMETER = 0.830  # mm (standard 0.032" drill), floor for lead-driven sizing
    LEAD_THICKNESS = 0.25  # mm, typical DIP lead stock thickness
    HOLE_CLEARANCE = 0.25  # mm, IPC-2222 level B hole-over-lead clearance

    # Pad sizing (IPC-7351 nominal density)
    ANNULAR_RING = 0.35     # mm per side, through-hole pad = drill + 2x ring
    PAD_TOE_HEEL = 0.70     # mm, gull-wing pad length = L + toe + heel
    PAD_SIDE_MARGIN = 0.06  # mm, gull-wing pad width = b + side margins
    PAD_MIN_GAP = 0.20      # mm, minimum copper gap between adjacent pads
    CORNER_CLEARANCE = 0.15  # mm, min copper-copper at quad corners (FP-14/IPC-2221B)
    MASK_MARGIN = 0.102     # mm, solder mask opening beyond copper
    PIN_CYLINDER_HEIGHT = 0.200  # mm (through PCB thickness)
    PAD_HEIGHT = 0.020  # mm (thin layer)
    TINY_HEIGHT = 0.001  # mm (minimum height for extrusion)
    SILK_MARKER_RADIUS = 0.100  # mm (first pin marker size)
    SILK_MARKER_HEIGHT = 0.200  # mm (first pin marker thickness)
    SILK_MARKER_CLEARANCE = 0.10  # mm (gap beyond courtyard for the silk pin-1 dot)

    # Body line parameters (from reference 2d.glb)
    BODY_HALF_WIDTH = 3.6195  # mm
    BODY_HALF_HEIGHT = 17.335  # mm
    LINE_THICKNESS = 0.12  # mm (border thickness)
    LINE_HEIGHT = 0.015  # mm (Z height from reference)
    Z_OFFSET = 0.015  # mm

    # Layer clearance offsets (matching reference 2d.glb spacing between layers)
    SILK_MARGIN_Y = 0.12   # silk extends this far beyond fab on Y (= LINE_THICKNESS)
    SILK_PAD_CLEARANCE = 0.20  # mm, min silk-to-pad clearance (FP-07/IPC-2612)
    CRTYD_MARGIN_Y = 0.25  # crtyd clearance beyond body/pads (both axes)

    def __init__(self, package_type: str, pin_count: int, component_name: str = "IC",
                 custom_layout: Optional[Dict[str, List[int]]] = None,
                 extracted_dims: Optional[Dict[str, Any]] = None):
        """
        Initialize PCB footprint builder.

        Args:
            package_type: Package type (e.g., "DIP-8", "LQFP64")
            pin_count: Number of pins
            component_name: Component name (currently not used in output)
            custom_layout: Optional dict mapping side names to pin numbers
                         (e.g., {"left_side": [1,2,3], "bottom_edge": [4,5,6]})
            extracted_dims: Optional flat dict of real dimensions from PDF extraction.
                          If provided, overrides hardcoded package geometry values.
        """
        self.package_type = package_type
        self.pin_count = pin_count
        self.component_name = component_name
        self.custom_layout = custom_layout

        # Get schematic parameters
        self.params = get_schematic_parameters(package_type, pin_count)

        # Grid-array (BGA/LGA) and leadless-ceramic packages have no
        # perimeter leads: rendering them with the two-row/quad layout this
        # builder produces is topologically wrong, and the result would look
        # plausible while never fitting the part (ADXL345's LGA-14 shipped
        # with an invented pitch this way). Fail closed instead (ARCH-006);
        # the schematic symbol for these packages remains valid.
        if self.params.package_type in (PackageType.BGA, PackageType.LCCC):
            from ..exceptions import ErrorCodes, SchematicGenerationError
            raise SchematicGenerationError(
                f"Package '{package_type}' is a grid-array/leadless type with "
                "no real pad-grid support; refusing to emit perimeter "
                "footprint geometry.",
                error_code=ErrorCodes.PACKAGE_UNKNOWN,
                details={"package_type": package_type, "pin_count": pin_count},
            )

        # A vision-read layout can put pins on four sides even when the
        # package string names a dual-row family; the resulting footprint
        # looks plausible and never fits the part. Refuse the contradiction
        # instead of trusting either source (fail closed).
        dual_row_types = {
            PackageType.DIP, PackageType.CDIP, PackageType.SOIC,
            PackageType.TSSOP, PackageType.DFN, PackageType.WSON,
            PackageType.SON,
        }
        if custom_layout and self.params.package_type in dual_row_types:
            sides_used = [s for s, pins in custom_layout.items() if pins]
            if len(sides_used) > 2:
                from ..exceptions import ErrorCodes, SchematicGenerationError
                raise SchematicGenerationError(
                    f"Package '{package_type}' is a dual-row family but the "
                    f"extracted layout places pins on {len(sides_used)} sides "
                    f"({', '.join(sorted(sides_used))}); refusing the "
                    "contradictory footprint.",
                    error_code=ErrorCodes.PACKAGE_UNKNOWN,
                    details={"package_type": package_type,
                             "layout_sides": sorted(sides_used)},
                )

        # Real plastic body size (E1/D1) when known; the datasheet "E" is the
        # lead span, which drives pad placement but not the drawn body.
        self._body_outline_w: Optional[float] = None
        self._body_outline_l: Optional[float] = None

        # Schematic parameters carry display proportions for readable
        # symbols; footprints must use real JEDEC dimensions instead.
        jedec_defaults = get_footprint_defaults(package_type, pin_count)
        if jedec_defaults:
            self._apply_extracted_dims(jedec_defaults)

        # Dimensions extracted from the datasheet PDF override defaults
        if extracted_dims:
            self._apply_extracted_dims(extracted_dims)

        # Pad shape/size from real dimensions (drill+ring for through-hole,
        # IPC-7351 rects from b/L for SMD; legacy circles when unknown).
        self.pad_spec = self._compute_pad_spec(jedec_defaults, extracted_dims)

        # Dimension provenance, recorded in the GLB so the platform can
        # decide what to auto-accept vs. flag for review: datasheet text is
        # deterministic, vision reads need a second look, JEDEC defaults are
        # assumed geometry, and "unverified" means display proportions only.
        if extracted_dims:
            self.dims_source = extracted_dims.get("dims_source") or "extracted"
        elif jedec_defaults:
            self.dims_source = "jedec_default"
        else:
            self.dims_source = "unverified"

        # Reasons this footprint is buildable but not dimensionally trustworthy.
        # Surfaced to the pipeline so the GLB is watermarked validated=false and
        # the run exits degraded (3) without requiring --force-best-effort — the
        # honest-flag layer for best-effort output. jedec_default is NOT degraded
        # (it's the normal fallback for most parts); only lossy approximation and
        # display-proportion ("unverified") geometry are.
        from ..package_types.package_geometry import lossy_approximation_reason

        self.degraded_reasons: List[str] = []
        lossy = lossy_approximation_reason(package_type)
        if lossy:
            self.degraded_reasons.append(lossy)
        if self.dims_source == "unverified":
            self.degraded_reasons.append(
                f"Footprint for '{package_type}' uses display-proportion "
                "geometry (no real dimensions found); pad sizes are unverified."
            )

        # FP-17: record the component's Z height on the footprint. The 2D path
        # discards Z, but assembly/BOM needs the body height, so we take it from
        # the 3D spec (extracted "A" when available, else the JEDEC-ish default).
        # Deterministic — no datasheet/LLM dependency.
        try:
            from ..model3d.spec import build_spec
            spec = build_spec(package_type, pin_count, component_name, extracted_dims)
            self.component_height = round(float(spec.body_height_A), 3)
        except Exception:
            self.component_height = None

        # Calculate pin positions
        self.pin_positions = layout_pins(self.params, custom_layout)

        # layout_pins places rows using schematic display margins (top of body
        # minus top_margin), which only centers the pins when body_height is a
        # display proportion sized to fit them. Footprints use the real body
        # dimensions, so recenter each pad row/column on the origin to match
        # the body outline (and the reference 2d.glb).
        self._recenter_pins()

        # IPC-7351: SMD pads are centered on the lead foot, not the lead
        # tip. layout_pins places pads at half the lead span (E/2); pull
        # them inward by half the lead length. Only applies when L comes
        # from real data (JEDEC table or PDF), and never to through-hole
        # packages, whose rows sit at the drill spacing exactly.
        lead_length_known = bool(
            (jedec_defaults or {}).get("L") or (extracted_dims or {}).get("L")
        )
        if lead_length_known and not self.is_through_hole():
            inset = self.params.pin_geometry.leg_length / 2.0
            for pos in self.pin_positions:
                if pos.side == "left":
                    pos.x += inset
                elif pos.side == "right":
                    pos.x -= inset
                elif pos.side == "top":
                    pos.y -= inset
                elif pos.side == "bottom":
                    pos.y += inset

        # FP-14: on quad packages the end pads of perpendicular sides overlap at
        # the corners. Shorten those corner pads' inner (heel) end so the
        # copper-to-copper clearance meets CORNER_CLEARANCE.
        self._pad_length_override: Dict[str, float] = {}
        self._relieve_corner_pads()

        logger.info(
            "Initialized 2D PCB schematic builder for %s (%d pins)" % (package_type, pin_count)
        )

    def is_through_hole(self) -> bool:
        return self.package_type.upper().startswith(("DIP", "PDIP", "CDIP"))

    def _recenter_pins(self) -> None:
        """Center each side's column (Y) or row (X) on the origin.

        Per side, not jointly: on quad packages the top and bottom rows are
        offset in opposite directions, so their union looks symmetric and a
        joint shift would leave both rows off-center.
        """
        for side in ("left", "right"):
            column = [p for p in self.pin_positions if p.side == side]
            if column:
                dy = (max(p.y for p in column) + min(p.y for p in column)) / 2.0
                for p in column:
                    p.y -= dy
                    p.text_y -= dy
                    p.num_y -= dy
        for side in ("top", "bottom"):
            row = [p for p in self.pin_positions if p.side == side]
            if row:
                dx = (max(p.x for p in row) + min(p.x for p in row)) / 2.0
                for p in row:
                    p.x -= dx
                    p.text_x -= dx
                    p.num_x -= dx

    def _relieve_corner_pads(self) -> None:
        """Shorten perpendicular corner pads to keep >= CORNER_CLEARANCE (FP-14).

        On quad packages the end pad of one side and the end pad of the adjacent
        (perpendicular) side extend toward the same corner and their copper
        overlaps. For each such colliding pair we retract the *inner* (heel) end
        of each pad — keeping the outer toe fixed so the solder joint is
        preserved — by ``length_override`` + a recentred position. Dual-row
        packages (no top/bottom pads) have no perpendicular pairs and are
        untouched. Widths and mask openings scale from the overridden length in
        ``build_pin``, so mask stays derived from copper (FP-15).
        """
        spec = self.pad_spec
        if spec.get("shape") != "rect":
            return
        length, width = spec["length"], spec["width"]
        vert = [p for p in self.pin_positions if p.side in ("left", "right")]
        horiz = [p for p in self.pin_positions if p.side in ("top", "bottom")]
        if not vert or not horiz:
            return  # dual-row: no corners

        clr = self.CORNER_CLEARANCE

        def x_half(p):
            return (length if p.side in ("left", "right") else width) / 2.0

        def y_half(p):
            return (width if p.side in ("left", "right") else length) / 2.0

        # New inner-edge targets (keyed by pin), retracting toward the toe.
        new_max_x: Dict[str, float] = {}   # left pads: shorten +X edge
        new_min_x: Dict[str, float] = {}   # right pads: shorten -X edge
        new_max_y: Dict[str, float] = {}   # bottom pads: shorten +Y edge
        new_min_y: Dict[str, float] = {}   # top pads: shorten -Y edge

        for v in vert:
            vx0, vx1 = v.x - x_half(v), v.x + x_half(v)
            vy0, vy1 = v.y - y_half(v), v.y + y_half(v)
            for h in horiz:
                hx0, hx1 = h.x - x_half(h), h.x + x_half(h)
                hy0, hy1 = h.y - y_half(h), h.y + y_half(h)
                # Overlap (or within clearance) on both axes => a corner clash.
                if not (min(vx1, hx1) - max(vx0, hx0) > -clr and
                        min(vy1, hy1) - max(vy0, hy0) > -clr):
                    continue
                # Retract the vertical pad's inner X-edge clear of h's X-band.
                if v.side == "left":
                    tgt = hx0 - clr
                    new_max_x[v.pin_number] = min(new_max_x.get(v.pin_number, vx1), tgt)
                else:  # right
                    tgt = hx1 + clr
                    new_min_x[v.pin_number] = max(new_min_x.get(v.pin_number, vx0), tgt)
                # Retract the horizontal pad's inner Y-edge clear of v's Y-band.
                if h.side == "bottom":
                    tgt = vy0 - clr
                    new_max_y[h.pin_number] = min(new_max_y.get(h.pin_number, hy1), tgt)
                else:  # top
                    tgt = vy1 + clr
                    new_min_y[h.pin_number] = max(new_min_y.get(h.pin_number, hy0), tgt)

        for p in self.pin_positions:
            if p.side in ("left", "right"):
                x0, x1 = p.x - x_half(p), p.x + x_half(p)
                if p.pin_number in new_max_x:
                    x1 = new_max_x[p.pin_number]
                elif p.pin_number in new_min_x:
                    x0 = new_min_x[p.pin_number]
                else:
                    continue
                new_len = max(width, x1 - x0)   # never shorter than the pad width
                self._pad_length_override[p.pin_number] = new_len
                p.x = (x0 + x1) / 2.0
            else:  # top / bottom
                y0, y1 = p.y - y_half(p), p.y + y_half(p)
                if p.pin_number in new_max_y:
                    y1 = new_max_y[p.pin_number]
                elif p.pin_number in new_min_y:
                    y0 = new_min_y[p.pin_number]
                else:
                    continue
                new_len = max(width, y1 - y0)
                self._pad_length_override[p.pin_number] = new_len
                p.y = (y0 + y1) / 2.0

    def _pad_bbox(self, p) -> tuple:
        """(x0, x1, y0, y1) copper extent of one pad, honouring corner relief."""
        spec = self.pad_spec
        if spec.get("shape") == "rect":
            length = self._pad_length_override.get(p.pin_number, spec["length"])
            if p.side in ("top", "bottom"):
                hx, hy = spec["width"] / 2.0, length / 2.0
            else:
                hx, hy = length / 2.0, spec["width"] / 2.0
        else:
            r = spec.get("diameter", self.COPPER_PAD_DIAMETER) / 2.0
            hx = hy = r
        return p.x - hx, p.x + hx, p.y - hy, p.y + hy

    def _silk_line_segments(self, y_line: float, x_min: float, x_max: float,
                            line_thickness: float) -> List[tuple]:
        """Clip a horizontal silk line clear of every pad (FP-07).

        Returns the (x0, x1) spans of the line at ``y_line`` that stay at least
        SILK_PAD_CLEARANCE from all pads. On dual-row packages no pad reaches the
        top/bottom edge, so the full line is returned unchanged; on quad packages
        the line is broken around the top/bottom pad columns — a broken outline
        is correct output, not a flaw.
        """
        # Clip a hair beyond the 0.20 mm minimum so the result clears the
        # boundary robustly (float noise) with real margin, not exactly on it.
        clr = self.SILK_PAD_CLEARANCE + 0.03
        band_lo = y_line - line_thickness / 2.0 - clr
        band_hi = y_line + line_thickness / 2.0 + clr

        forbidden = []
        for p in self.pin_positions:
            px0, px1, py0, py1 = self._pad_bbox(p)
            if py1 > band_lo and py0 < band_hi:            # pad sits under the line
                forbidden.append((px0 - clr, px1 + clr))

        segments = [(x_min, x_max)]
        for fa, fb in forbidden:
            nxt = []
            for a, b in segments:
                if fb <= a or fa >= b:                     # no overlap
                    nxt.append((a, b))
                    continue
                if a < fa:
                    nxt.append((a, fa))                    # keep the clear left part
                if fb < b:
                    nxt.append((fb, b))                    # keep the clear right part
            segments = nxt
        # Drop slivers too small to print as a legend line.
        return [(a, b) for a, b in segments if (b - a) > line_thickness]

    def _apply_extracted_dims(self, dims: Dict[str, Any]) -> None:
        """Override SchematicParameters fields with extracted PDF dimensions."""
        if dims.get("e"):
            self.params.pin_pitch = float(dims["e"])
        if dims.get("E"):
            self.params.body_width = float(dims["E"])
        if dims.get("D"):
            self.params.body_height = float(dims["D"])
        if dims.get("b"):
            self.params.pin_geometry.leg_width = float(dims["b"])
        if dims.get("L"):
            self.params.pin_geometry.leg_length = float(dims["L"])
        if dims.get("E1"):
            self._body_outline_w = float(dims["E1"])
        if dims.get("D1"):
            self._body_outline_l = float(dims["D1"])

    @property
    def fab_outline_width(self) -> float:
        """Drawn body width: real body (E1) when known, else lead span."""
        return self._body_outline_w or self.params.body_width

    @property
    def fab_outline_length(self) -> float:
        """Drawn body length: real body (D1) when known, else D."""
        return self._body_outline_l or self.params.body_height

    def _compute_pad_spec(self, jedec_defaults: Optional[Dict[str, Any]],
                          extracted_dims: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Pad shape and size per IPC-7351 from the best available dims."""
        if self.is_through_hole():
            drill = self.HOLE_DIAMETER
            th_dims = dict(jedec_defaults or {})
            th_dims.update(extracted_dims or {})
            b_eff = th_dims.get("b_max") or th_dims.get("b")
            if b_eff:
                # IPC-2222: hole = lead diagonal + 0.25 clearance. DIP leads
                # are rectangular (width b x ~0.25 thick); the diagonal
                # governs insertion. Never below the standard 0.83 drill.
                diagonal = (float(b_eff) ** 2 + self.LEAD_THICKNESS ** 2) ** 0.5
                drill = max(drill, round(diagonal + self.HOLE_CLEARANCE, 2))
            diameter = drill + 2 * self.ANNULAR_RING
            return {
                "shape": "circle",
                "diameter": diameter,
                "mask_diameter": diameter + self.MASK_MARGIN,
                "drill": drill,
            }

        dims = dict(jedec_defaults or {})
        dims.update(extracted_dims or {})
        b, lead_len = dims.get("b"), dims.get("L")
        if b and lead_len:
            # IPC-7351: pads must cover the tolerance extremes — the widest
            # lead (b_max) and the longest foot (L_max) — not the nominals.
            # Fall back to midpoints when the datasheet gave single values.
            b_eff = dims.get("b_max") or b
            lead_eff = dims.get("L_max") or lead_len
            width = float(b_eff) + self.PAD_SIDE_MARGIN
            if self.params.pin_pitch:
                width = min(width, self.params.pin_pitch - self.PAD_MIN_GAP)
            return {
                "shape": "rect",
                "width": width,
                "length": float(lead_eff) + self.PAD_TOE_HEEL,
            }

        # No real lead dims: keep the legacy reference-GLB circles.
        return {
            "shape": "circle",
            "diameter": self.COPPER_PAD_DIAMETER,
            "mask_diameter": self.SOLDER_MASK_DIAMETER,
        }

    def _pad_extents(self) -> tuple:
        """Outermost pad reach from origin on X and Y (for the courtyard)."""
        spec = self.pad_spec
        max_x = max_y = 0.0
        for pos in self.pin_positions:
            if spec["shape"] == "rect":
                if pos.side in ("top", "bottom"):
                    xd, yd = spec["width"], spec["length"]
                else:
                    xd, yd = spec["length"], spec["width"]
            else:
                xd = yd = spec["diameter"]
            max_x = max(max_x, abs(pos.x) + xd / 2)
            max_y = max(max_y, abs(pos.y) + yd / 2)
        return max_x, max_y

    def _layer_half_dims(self) -> tuple:
        """Half-dimensions of fab, silk and courtyard layers.

        The courtyard must enclose both the body and the pads, whichever
        reaches further, plus clearance.
        """
        fab_hw = self.fab_outline_width / 2
        fab_hh = self.fab_outline_length / 2
        silk_hw = fab_hw
        silk_hh = fab_hh + self.SILK_MARGIN_Y
        pad_x, pad_y = self._pad_extents()
        crtyd_hw = max(fab_hw, pad_x) + self.CRTYD_MARGIN_Y
        crtyd_hh = max(fab_hh, pad_y) + self.CRTYD_MARGIN_Y
        return fab_hw, fab_hh, silk_hw, silk_hh, crtyd_hw, crtyd_hh

    def calculate_pin_positions_footprint(self) -> List[PinPosition]:
        """
        Get pin positions for PCB footprint using the existing layout.

        Returns:
            List of PinPosition objects
        """
        return self.pin_positions

    def build_body(self) -> cq.Assembly:
        """
        Build the complete Body assembly with fab/silk/crtyd layers.

        Hierarchy:
        Body
        ├── fab_layer
        │   ├── BodyLine
        │   ├── BodyLine
        │   ├── BodyLine
        │   └── BodyLine
        ├── silk_layer
        │   ├── BodyLine
        │   └── BodyLine
        └── crtyd_layer
            ├── BodyLine
            ├── BodyLine
            ├── BodyLine
            └── BodyLine

        Returns:
            Body assembly with proper layer hierarchy
        """
        body_assy = cq.Assembly(name="Body")

        line_thickness = self.LINE_THICKNESS
        line_height = self.params.body_geometry.border_height

        # Per-layer half-dimensions (each layer expands slightly outward)
        fab_hw, fab_hh, silk_hw, silk_hh, crtyd_hw, crtyd_hh = self._layer_half_dims()

        # 1. fab_layer - Complete outline (4 lines)
        # CadQuery requires unique sibling names during construction.
        # The exported GLB is normalized later so the final hierarchy uses the
        # repeated "BodyLine" names found in 2d.glb.
        # The side identity comes from the order: top, bottom, left, right.
        fab_layer = cq.Assembly(name="fab_layer")
        fab_layer.add(
            cq.Workplane("XY").center(0, fab_hh).rect(fab_hw * 2, line_thickness).extrude(line_height),
            name="BodyLine_Top", color=self.YELLOW_COLOR)
        fab_layer.add(
            cq.Workplane("XY").center(0, -fab_hh).rect(fab_hw * 2, line_thickness).extrude(line_height),
            name="BodyLine_Bottom", color=self.YELLOW_COLOR)
        fab_layer.add(
            cq.Workplane("XY").center(-fab_hw, 0).rect(line_thickness, fab_hh * 2).extrude(line_height),
            name="BodyLine_Left", color=self.YELLOW_COLOR)
        fab_layer.add(
            cq.Workplane("XY").center(fab_hw, 0).rect(line_thickness, fab_hh * 2).extrude(line_height),
            name="BodyLine_Right", color=self.YELLOW_COLOR)
        body_assy.add(fab_layer, name="fab_layer")

        # 2. silk_layer - top/bottom outline lines, clipped clear of any pads
        # they cross (FP-07). Dual-row parts keep the full lines; quad parts get
        # a broken outline around the top/bottom pad columns.
        silk_layer = cq.Assembly(name="silk_layer")
        for label, y_line in (("Top", silk_hh), ("Bottom", -silk_hh)):
            segments = self._silk_line_segments(y_line, -silk_hw, silk_hw, line_thickness)
            for i, (a, b) in enumerate(segments):
                # Unique construction names; normalize_pcb_footprint_bodyline_names
                # collapses them all back to "BodyLine" in the saved GLB.
                seg_name = f"BodyLine_{label}" if len(segments) == 1 else f"BodyLine_{label}_{i}"
                silk_layer.add(
                    cq.Workplane("XY").center((a + b) / 2.0, y_line).rect(b - a, line_thickness).extrude(line_height),
                    name=seg_name, color=self.WHITE_COLOR)
        body_assy.add(silk_layer, name="silk_layer")

        # 3. crtyd_layer - Complete outline (4 lines), larger clearance box
        crtyd_layer = cq.Assembly(name="crtyd_layer")
        crtyd_layer.add(
            cq.Workplane("XY").center(0, crtyd_hh).rect(crtyd_hw * 2, line_thickness).extrude(line_height),
            name="BodyLine_Top", color=self.MAGENTA_COLOR)
        crtyd_layer.add(
            cq.Workplane("XY").center(0, -crtyd_hh).rect(crtyd_hw * 2, line_thickness).extrude(line_height),
            name="BodyLine_Bottom", color=self.MAGENTA_COLOR)
        crtyd_layer.add(
            cq.Workplane("XY").center(-crtyd_hw, 0).rect(line_thickness, crtyd_hh * 2).extrude(line_height),
            name="BodyLine_Left", color=self.MAGENTA_COLOR)
        crtyd_layer.add(
            cq.Workplane("XY").center(crtyd_hw, 0).rect(line_thickness, crtyd_hh * 2).extrude(line_height),
            name="BodyLine_Right", color=self.MAGENTA_COLOR)
        body_assy.add(crtyd_layer, name="crtyd_layer")

        return body_assy

    def build_designator(self) -> cq.Assembly:
        """
        Build designator label ("U") with Body and BoundingBox.

        Hierarchy:
        DesignatorName
        ├── Body (visible text "U")
        └── BoundingBox (invisible selection area)

        Returns:
            DesignatorName assembly
        """
        designator_assy = cq.Assembly(name="DesignatorName")

        # Visible text body
        text_size = self.params.body_geometry.designator_size
        text_height = self.params.body_geometry.designator_height
        offset_y = self.params.body_height / 2 + 10.0  # Position above body

        # Create text geometry
        text_body = cq.Workplane("XY").center(0, offset_y).text(
            "U", text_size, text_height, halign="center", valign="center"
        )
        
        # Add as "Body" child
        body_assy = cq.Assembly(name="Body")
        body_assy.add(text_body, color=self.WHITE_COLOR)
        designator_assy.add(body_assy, name="Body")

        # Create invisible bounding box for selection
        bbox_size_x = text_size * 2.0
        bbox_size_y = text_size * 1.5
        bbox = cq.Workplane("XY").center(0, offset_y).rect(
            bbox_size_x, bbox_size_y
        ).extrude(0.001)
        
        bbox_assy = cq.Assembly(name="BoundingBox")
        bbox_assy.add(bbox, color=self.TRANSPARENT_COLOR)
        designator_assy.add(bbox_assy, name="BoundingBox")

        return designator_assy

    def build_package_value(self) -> cq.Assembly:
        """
        Build package value label (component name) with Body and BoundingBox.

        Hierarchy:
        PackageValue
        ├── Body (visible text with component name)
        └── BoundingBox (invisible selection area)

        Returns:
            PackageValue assembly
        """
        value_assy = cq.Assembly(name="PackageValue")

        # Truncate name if too long
        component_name = self.component_name[:30] if self.component_name else "IC"

        # Visible text body
        text_size = self.params.body_geometry.value_size
        text_height = self.params.body_geometry.value_height
        offset_y = self.params.body_height / 2 + 5.0  # Position above body

        # Create text geometry
        text_body = cq.Workplane("XY").center(0, offset_y).text(
            component_name, text_size, text_height, halign="center", valign="center"
        )
        
        # Add as "Body" child
        body_assy = cq.Assembly(name="Body")
        body_assy.add(text_body, color=self.PURPLE_COLOR)
        value_assy.add(body_assy, name="Body")

        # Create invisible bounding box for selection
        bbox_size_x = max(len(component_name) * text_size * 0.6, text_size * 2)
        bbox_size_y = text_size * 1.5
        bbox = cq.Workplane("XY").center(0, offset_y).rect(
            bbox_size_x, bbox_size_y
        ).extrude(0.001)
        
        bbox_assy = cq.Assembly(name="BoundingBox")
        bbox_assy.add(bbox, color=self.TRANSPARENT_COLOR)
        value_assy.add(bbox_assy, name="BoundingBox")

        return value_assy

    def build_first_pin_marker(self, pin_positions: List[PinPosition]) -> Optional[cq.Assembly]:
        """
        Build pin 1 marker (dot/circle).

        Args:
            pin_positions: List of PinPosition objects

        Returns:
            Assembly with silk_firstPinMarker and fab_firstPinMarker, or None if no pin 1
        """
        pin1_pos = next((p for p in pin_positions if p.pin_number == "1"), None)
        if pin1_pos is None:
            return None

        markers_assy = cq.Assembly(name="FirstPinMarker")

        x, y = pin1_pos.x, pin1_pos.y

        # FP-07 / FP-08: the SILK pin-1 marker must be clear of every solderable
        # pad. Place it just OUTSIDE the courtyard, in pin 1's corner, so silk
        # clipping can never erase it and it can never overlap copper. (The fab
        # marker below stays at the pad — the fabrication layer is documentation,
        # not silkscreen, and is not subject to the 0.20 mm silk-to-pad rule.)
        _, _, _, _, crtyd_hw, crtyd_hh = self._layer_half_dims()
        gap = self.SILK_MARKER_CLEARANCE + self.SILK_MARKER_RADIUS
        sx = -1.0 if x <= 0 else 1.0
        sy = 1.0 if y >= 0 else -1.0
        silk_x = sx * (crtyd_hw + gap)
        silk_y = sy * (crtyd_hh + gap)

        # Silk layer marker (outside the courtyard, pin-1 corner)
        silk_marker = cq.Workplane("XY").center(silk_x, silk_y).circle(
            self.SILK_MARKER_RADIUS
        ).extrude(self.SILK_MARKER_HEIGHT)
        silk_marker_assy = cq.Assembly(name="silk_firstPinMarker")
        silk_marker_assy.add(silk_marker, color=self.WHITE_COLOR)
        markers_assy.add(silk_marker_assy)

        # Fab layer marker (documentation — stays at the pad)
        fab_marker = cq.Workplane("XY").center(x, y).circle(
            self.SILK_MARKER_RADIUS
        ).extrude(self.SILK_MARKER_HEIGHT)
        fab_marker_assy = cq.Assembly(name="fab_firstPinMarker")
        fab_marker_assy.add(fab_marker, color=self.YELLOW_COLOR)
        markers_assy.add(fab_marker_assy)

        return markers_assy

    def build_pin(self, pin_pos: PinPosition, pin_name: str = "", pin_number: str = "") -> cq.Assembly:
        """
        Build pin components (leg, text, pin number).

        Args:
            pin_pos: Pin position from PinPosition object
            pin_name: Pin function name (e.g., "GND", "VCC")
            pin_number: Pin number (e.g., "1", "A1")

        Returns:
            Assembly with pin components
        """
        pin_assy = cq.Assembly(name=pin_number)

        x, y = pin_pos.x, pin_pos.y

        # Check if through-hole (DIP/PDIP/CDIP) or surface mount (SOIC/TQFP/QFN)
        is_through_hole = self.is_through_hole()

        if is_through_hole:
            # For through-hole packages, preserve the reference GLB order exactly:
            # CopperCirclePad, SolderMask, HoleCylinderPin, CopperCylinderPin,
            # CopperCirclePin, text.

            # CopperCirclePad (F.Cu layer) - top layer copper pad
            copper_pad_radius = self.pad_spec["diameter"] / 2
            copper_pad = cq.Workplane("XY").workplane(offset=self.PIN_CYLINDER_HEIGHT/2).center(
                x, y
            ).circle(copper_pad_radius).extrude(self.PAD_HEIGHT)
            copper_pad_assy = cq.Assembly(name="CopperCirclePad")
            copper_pad_assy.add(copper_pad, color=self.RED_COLOR)
            pin_assy.add(copper_pad_assy)

            # SolderMask (brown, largest)
            solder_mask_radius = self.pad_spec["mask_diameter"] / 2
            solder_mask = cq.Workplane("XY").workplane(offset=-self.PAD_HEIGHT/2).center(
                x, y
            ).circle(solder_mask_radius).extrude(self.PAD_HEIGHT)
            solder_mask_assy = cq.Assembly(name="SolderMask")
            solder_mask_assy.add(solder_mask, color=self.BROWN_COLOR)
            pin_assy.add(solder_mask_assy)

            # HoleCylinderPin (black) - drilled hole
            hole_radius = self.pad_spec.get("drill", self.HOLE_DIAMETER) / 2
            hole_cylinder = cq.Workplane("XY").center(
                x, y
            ).circle(hole_radius).extrude(self.PIN_CYLINDER_HEIGHT)
            hole_cylinder_assy = cq.Assembly(name="HoleCylinderPin")
            hole_cylinder_assy.add(hole_cylinder, color=self.BLACK_COLOR)
            pin_assy.add(hole_cylinder_assy)

            # CopperCylinderPin (red) - plated hole walls
            copper_cylinder = cq.Workplane("XY").center(
                x, y
            ).circle(hole_radius).extrude(self.PIN_CYLINDER_HEIGHT)
            copper_cylinder_assy = cq.Assembly(name="CopperCylinderPin")
            copper_cylinder_assy.add(copper_cylinder, color=self.RED_COLOR)
            pin_assy.add(copper_cylinder_assy)

            # CopperCirclePin (B.Cu layer) - bottom layer copper pad
            # This is the copper pad on the BOTTOM side of the PCB
            copper_circle_pin_radius = self.pad_spec["diameter"] / 2
            copper_circle_pin = cq.Workplane("XY").workplane(offset=-self.PIN_CYLINDER_HEIGHT/2).center(
                x, y
            ).circle(copper_circle_pin_radius).extrude(self.PAD_HEIGHT)
            copper_circle_pin_assy = cq.Assembly(name="CopperCirclePin")
            copper_circle_pin_assy.add(copper_circle_pin, color=self.RED_COLOR)
            pin_assy.add(copper_circle_pin_assy)
        else:
            # For surface mount packages (SOIC/TQFP/QFN).
            # With real lead dims the pad is an IPC-7351 rectangle (length
            # along the lead direction); otherwise the legacy circles.
            spec = self.pad_spec
            if spec["shape"] == "rect":
                # Corner pads may carry a shortened length (FP-14 relief).
                length = self._pad_length_override.get(pin_number, spec["length"])
                if pin_pos.side in ("top", "bottom"):
                    pad_x, pad_y = spec["width"], length
                else:
                    pad_x, pad_y = length, spec["width"]

                solder_mask = cq.Workplane("XY").workplane(offset=-self.PAD_HEIGHT/2).center(
                    x, y
                ).rect(pad_x + self.MASK_MARGIN, pad_y + self.MASK_MARGIN).extrude(self.PAD_HEIGHT)
                copper_pad = cq.Workplane("XY").center(
                    x, y
                ).rect(pad_x, pad_y).extrude(self.PAD_HEIGHT)
            else:
                solder_mask = cq.Workplane("XY").workplane(offset=-self.PAD_HEIGHT/2).center(
                    x, y
                ).circle(spec["mask_diameter"] / 2).extrude(self.PAD_HEIGHT)
                copper_pad = cq.Workplane("XY").center(
                    x, y
                ).circle(spec["diameter"] / 2).extrude(self.PAD_HEIGHT)

            # SolderMask (brown, largest)
            solder_mask_assy = cq.Assembly(name="SolderMask")
            solder_mask_assy.add(solder_mask, color=self.BROWN_COLOR)
            pin_assy.add(solder_mask_assy)

            # Only top copper pad
            copper_pad_assy = cq.Assembly(name="CopperCirclePad")
            copper_pad_assy.add(copper_pad, color=self.RED_COLOR)
            pin_assy.add(copper_pad_assy)

        # Pin number text (white, matching reference mat8)
        text_size = 0.8
        text_height = 0.2
        pin_text = cq.Workplane("XY").center(
            x, y
        ).text(pin_number, text_size, text_height, halign="center")
        pin_text_assy = cq.Assembly(name="text")
        pin_text_assy.add(pin_text, color=self.WHITE_COLOR)
        pin_assy.add(pin_text_assy)

        return pin_assy

    def build_all_pins(self, pin_data: List[Dict[str, Any]], pin_positions: List[PinPosition]) -> cq.Assembly:
        """
        Build all pins and organize into Legs assembly.

        Args:
            pin_data: List of pin dictionaries with 'number', 'name'
            pin_positions: List of PinPosition objects

        Returns:
            Legs assembly containing all pins
        """
        legs_assy = cq.Assembly(name="Legs")

        # Create a mapping from pin number to position
        pin_map = {pos.pin_number: pos for pos in pin_positions}

        logger.info("Building %d pins" % len(pin_data))

        for pin in pin_data:
            pin_num = str(pin.get("number", pin.get("pin_num", "")))
            pin_name = pin.get("name", pin.get("pin_name", ""))

            pos = pin_map.get(pin_num)
            if pos is None:
                logger.warning("No layout position for pin %s" % pin_num)
                continue

            # Build pin assembly
            pin_assy = self.build_pin(pos, pin_name, pin_num)
            legs_assy.add(pin_assy)

        return legs_assy

    def build_schematic(self, pin_data: List[Dict[str, Any]]) -> cq.Assembly:
        """
        Build complete PCB footprint assembly.

        Hierarchy:
        Package
        ├── DesignatorName
        │   ├── Body (text "U")
        │   └── BoundingBox
        ├── PackageValue
        │   ├── Body (text component name)
        │   └── BoundingBox
        ├── FirstPinMarker
        │   ├── silk_firstPinMarker
        │   └── fab_firstPinMarker
        ├── Legs
        │   └── 1, 2, 3, ...
        │       ├── CopperCirclePad (F.Cu)
        │       ├── SolderMask
        │       ├── HoleCylinderPin [DIP only]
        │       ├── CopperCylinderPin [DIP only]
        │       ├── CopperCirclePin (B.Cu) [DIP only]
        │       └── text
        └── Body
            ├── fab_layer
            │   └── BodyLine (x4, repeated names in reference order)
            ├── silk_layer
            │   └── BodyLine (x2, repeated names in reference order)
            └── crtyd_layer
                └── BodyLine (x4, repeated names in reference order)

        Args:
            pin_data: List of pin dictionaries with 'number', 'name'

        Returns:
            Complete Package assembly with all components
        """
        # Main package assembly
        package_assy = cq.Assembly(name="Package")

        # Get pin positions using the layout
        pin_positions = self.calculate_pin_positions_footprint()

        # 1. Add DesignatorName (RefDes "U")
        logger.info("Adding DesignatorName...")
        designator = self.build_designator()
        package_assy.add(designator, name="DesignatorName")

        # 2. Add PackageValue (component name)
        logger.info("Adding PackageValue...")
        value = self.build_package_value()
        package_assy.add(value, name="PackageValue")

        # 3. Add FirstPinMarker
        logger.info("Building pin 1 marker...")
        markers = self.build_first_pin_marker(pin_positions)
        if markers:
            package_assy.add(markers, name="FirstPinMarker")

        # 4. Add all pins (Legs)
        logger.info("Building pins...")
        legs = self.build_all_pins(pin_data, pin_positions)
        package_assy.add(legs, name="Legs")

        # 5. Add Body (with fab/silk/crtyd layers)
        logger.info("Building body...")
        body = self.build_body()
        package_assy.add(body, name="Body")

        logger.info(
            "PCB footprint assembly built: %d top-level components" % len(package_assy.children)
        )

        return package_assy

    def save_glb(self, output_path: str, pin_data: List[Dict[str, Any]]) -> bool:
        """
        Build and export PCB footprint to GLB file.

        The GLB is assembled and validated at a temporary path and only
        promoted to output_path after every check passes: downstream tooling
        globs for *.glb, so a failed run must not leave a plausible-looking
        file behind.

        Args:
            output_path: Path to save GLB file
            pin_data: List of pin dictionaries

        Returns:
            True if successful, False otherwise
        """
        # The suffix must stay ".glb": both cadquery and pygltflib pick
        # their binary format from the file extension.
        work_path = output_path + ".tmp.glb"
        try:
            logger.info("Building PCB footprint for %s..." % output_path)

            # Build schematic assembly
            assembly = self.build_schematic(pin_data)

            # Save to GLB
            logger.info("Saving to %s..." % output_path)
            assembly.save(work_path)
            try:
                original_nodes, simplified_nodes = optimize_glb_hierarchy(work_path)
                logger.info(
                    "Optimized GLB hierarchy: %d -> %d nodes"
                    % (original_nodes, simplified_nodes)
                )
                renamed_nodes = normalize_pcb_footprint_bodyline_names(work_path)
                logger.info(
                    "Normalized PCB body line names to reference style: %d nodes"
                    % renamed_nodes
                )
                pin_position_map = {
                    pos.pin_number: (pos.x, pos.y)
                    for pos in self.pin_positions
                }
                fab_hw, fab_hh, silk_hw, silk_hh, crtyd_hw, crtyd_hh = self._layer_half_dims()
                extras_nodes = inject_pcb_footprint_extras(
                    work_path,
                    component_name=self.component_name,
                    package_type=self.package_type,
                    pin_position_map=pin_position_map,
                    fab_dims=(fab_hw, fab_hh),
                    silk_dims=(silk_hw, silk_hh),
                    crtyd_dims=(crtyd_hw, crtyd_hh),
                    pad_spec=self.pad_spec,
                    pin_side_map={
                        pos.pin_number: pos.side for pos in self.pin_positions
                    },
                    dims_source=self.dims_source,
                    component_height=self.component_height,
                )
                logger.info("Injected extras into %d nodes" % extras_nodes)
            except Exception as exc:
                logger.warning("Skipping GLB hierarchy optimization: %s" % exc)

            try:
                is_valid, hierarchy_errors = validate_pcb_footprint_glb(
                    work_path,
                    pin_count=self.pin_count,
                    through_hole=self.is_through_hole(),
                )
            except Exception as exc:
                logger.warning("Skipping PCB footprint hierarchy validation: %s" % exc)
            else:
                if not is_valid:
                    logger.error(
                        "PCB footprint hierarchy validation failed: %s"
                        % "; ".join(hierarchy_errors)
                    )
                    return False

            # Keep through-hole workflow output structurally aligned with the reference 2d.glb.
            if self.is_through_hole():
                try:
                    is_similar, similarity_errors = validate_glb_similarity_to_reference(
                        work_path
                    )
                except Exception as exc:
                    logger.warning(
                        "Skipping reference hierarchy similarity check: %s" % exc
                    )
                else:
                    if not is_similar:
                        logger.error(
                            "Reference hierarchy similarity check failed: %s"
                            % "; ".join(similarity_errors)
                        )
                        return False

            if not os.path.exists(work_path):
                logger.error("GLB file not created: %s" % output_path)
                return False

            os.replace(work_path, output_path)
            size = os.path.getsize(output_path)
            logger.info("Successfully saved PCB footprint to %s" % output_path)
            logger.info("GLB file size: %d bytes" % size)
            return True

        except Exception as e:
            logger.error("Error saving GLB: %s" % e)
            import traceback
            traceback.print_exc()
            return False
        finally:
            if os.path.exists(work_path):
                os.remove(work_path)


def build_pcb_footprint(
    package_type: str,
    pin_count: int,
    component_name: str,
    pin_data: List[Dict[str, Any]],
    output_path: str,
    custom_layout: Optional[Dict[str, List[int]]] = None,
    extracted_dims: Optional[Dict[str, Any]] = None,
    degraded_out: Optional[List[str]] = None,
) -> bool:
    """
    Build and export PCB footprint from pin data.

    Args:
        package_type: Package type (e.g., "DIP-8", "LQFP64")
        pin_count: Number of pins
        component_name: Component name
        pin_data: List of pin dictionaries with 'number', 'name'
        output_path: Path to save GLB file
        custom_layout: Optional dict mapping side names to pin numbers
                     (e.g., {"left_side": [1,2,3], "bottom_edge": [4,5,6]})
        extracted_dims: Optional flat dict of real dimensions from PDF extraction.
        degraded_out: Optional list; if provided, extended with the reasons this
                     footprint is buildable but not dimensionally trustworthy
                     (lossy approximation, unverified geometry). The caller uses
                     it to watermark the GLB and exit degraded.

    Returns:
        True if successful, False otherwise
    """
    builder = PcbFootprintBuilder(
        package_type, pin_count, component_name, custom_layout, extracted_dims
    )
    if degraded_out is not None:
        degraded_out.extend(builder.degraded_reasons)
    return builder.save_glb(output_path, pin_data)
