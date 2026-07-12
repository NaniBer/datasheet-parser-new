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
    HOLE_DIAMETER = 0.830  # mm (standard 0.032" drill)

    # Pad sizing (IPC-7351 nominal density)
    ANNULAR_RING = 0.35     # mm per side, through-hole pad = drill + 2x ring
    PAD_TOE_HEEL = 0.70     # mm, gull-wing pad length = L + toe + heel
    PAD_SIDE_MARGIN = 0.06  # mm, gull-wing pad width = b + side margins
    PAD_MIN_GAP = 0.20      # mm, minimum copper gap between adjacent pads
    MASK_MARGIN = 0.102     # mm, solder mask opening beyond copper
    PIN_CYLINDER_HEIGHT = 0.200  # mm (through PCB thickness)
    PAD_HEIGHT = 0.020  # mm (thin layer)
    TINY_HEIGHT = 0.001  # mm (minimum height for extrusion)
    SILK_MARKER_RADIUS = 0.100  # mm (first pin marker size)
    SILK_MARKER_HEIGHT = 0.200  # mm (first pin marker thickness)

    # Body line parameters (from reference 2d.glb)
    BODY_HALF_WIDTH = 3.6195  # mm
    BODY_HALF_HEIGHT = 17.335  # mm
    LINE_THICKNESS = 0.12  # mm (border thickness)
    LINE_HEIGHT = 0.015  # mm (Z height from reference)
    Z_OFFSET = 0.015  # mm

    # Layer clearance offsets (matching reference 2d.glb spacing between layers)
    SILK_MARGIN_Y = 0.12   # silk extends this far beyond fab on Y (= LINE_THICKNESS)
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

        logger.info(
            "Initialized 2D PCB schematic builder for %s (%d pins)" % (package_type, pin_count)
        )

    def is_through_hole(self) -> bool:
        return self.package_type.upper().startswith(("DIP", "PDIP", "CDIP"))

    def _recenter_pins(self) -> None:
        """Center left/right columns (Y) and top/bottom rows (X) on the origin."""
        columns = [p for p in self.pin_positions if p.side in ("left", "right")]
        if columns:
            dy = (max(p.y for p in columns) + min(p.y for p in columns)) / 2.0
            for p in columns:
                p.y -= dy
                p.text_y -= dy
                p.num_y -= dy
        rows = [p for p in self.pin_positions if p.side in ("top", "bottom")]
        if rows:
            dx = (max(p.x for p in rows) + min(p.x for p in rows)) / 2.0
            for p in rows:
                p.x -= dx
                p.text_x -= dx
                p.num_x -= dx

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
            diameter = self.HOLE_DIAMETER + 2 * self.ANNULAR_RING
            return {
                "shape": "circle",
                "diameter": diameter,
                "mask_diameter": diameter + self.MASK_MARGIN,
                "drill": self.HOLE_DIAMETER,
            }

        dims = dict(jedec_defaults or {})
        dims.update(extracted_dims or {})
        b, lead_len = dims.get("b"), dims.get("L")
        if b and lead_len:
            width = float(b) + self.PAD_SIDE_MARGIN
            if self.params.pin_pitch:
                width = min(width, self.params.pin_pitch - self.PAD_MIN_GAP)
            return {
                "shape": "rect",
                "width": width,
                "length": float(lead_len) + self.PAD_TOE_HEEL,
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

        # 2. silk_layer - Top/bottom only (avoids pin areas on left/right for DIP)
        silk_layer = cq.Assembly(name="silk_layer")
        silk_layer.add(
            cq.Workplane("XY").center(0, silk_hh).rect(silk_hw * 2, line_thickness).extrude(line_height),
            name="BodyLine_Top", color=self.WHITE_COLOR)
        silk_layer.add(
            cq.Workplane("XY").center(0, -silk_hh).rect(silk_hw * 2, line_thickness).extrude(line_height),
            name="BodyLine_Bottom", color=self.WHITE_COLOR)
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

        # Silk layer marker
        silk_marker = cq.Workplane("XY").center(x, y).circle(
            self.SILK_MARKER_RADIUS
        ).extrude(self.SILK_MARKER_HEIGHT)
        silk_marker_assy = cq.Assembly(name="silk_firstPinMarker")
        silk_marker_assy.add(silk_marker, color=self.WHITE_COLOR)
        markers_assy.add(silk_marker_assy)

        # Fab layer marker
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
            hole_radius = self.HOLE_DIAMETER / 2
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
                if pin_pos.side in ("top", "bottom"):
                    pad_x, pad_y = spec["width"], spec["length"]
                else:
                    pad_x, pad_y = spec["length"], spec["width"]

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

        Args:
            output_path: Path to save GLB file
            pin_data: List of pin dictionaries

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("Building PCB footprint for %s..." % output_path)

            # Build schematic assembly
            assembly = self.build_schematic(pin_data)

            # Save to GLB
            logger.info("Saving to %s..." % output_path)
            assembly.save(output_path)
            try:
                original_nodes, simplified_nodes = optimize_glb_hierarchy(output_path)
                logger.info(
                    "Optimized GLB hierarchy: %d -> %d nodes"
                    % (original_nodes, simplified_nodes)
                )
                renamed_nodes = normalize_pcb_footprint_bodyline_names(output_path)
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
                    output_path,
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
                )
                logger.info("Injected extras into %d nodes" % extras_nodes)
            except Exception as exc:
                logger.warning("Skipping GLB hierarchy optimization: %s" % exc)

            try:
                is_valid, hierarchy_errors = validate_pcb_footprint_glb(
                    output_path,
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
                        output_path
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

            logger.info("Successfully saved PCB footprint to %s" % output_path)

            # Verify file exists
            if os.path.exists(output_path):
                size = os.path.getsize(output_path)
                logger.info("GLB file size: %d bytes" % size)
                return True
            else:
                logger.error("GLB file not created: %s" % output_path)
                return False

        except Exception as e:
            logger.error("Error saving GLB: %s" % e)
            import traceback
            traceback.print_exc()
            return False


def build_pcb_footprint(
    package_type: str,
    pin_count: int,
    component_name: str,
    pin_data: List[Dict[str, Any]],
    output_path: str,
    custom_layout: Optional[Dict[str, List[int]]] = None,
    extracted_dims: Optional[Dict[str, Any]] = None,
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

    Returns:
        True if successful, False otherwise
    """
    builder = PcbFootprintBuilder(
        package_type, pin_count, component_name, custom_layout, extracted_dims
    )
    return builder.save_glb(output_path, pin_data)
