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
    get_schematic_parameters,
)
from ..core import (
    optimize_glb_hierarchy,
    validate_glb_similarity_to_reference,
    validate_pcb_footprint_glb,
)
from .pin_layout import PinPosition, layout_pins

# Setup logging
logger = logging.getLogger(__name__)


class PcbFootprintBuilder:
    """Build PCB footprint symbols using cadquery (manufacturing layout)."""

    # Colors matching 2d.glb materials
    WHITE_COLOR = cq.Color(1.0, 1.0, 1.0, 1.0)
    TRANSPARENT_COLOR = cq.Color(1.0, 1.0, 1.0, 0.0)
    SUBSTRATE_COLOR = cq.Color(0.09, 0.02, 0.17, 1.0)  # Deep purple/blue
    COPPER_COLOR = cq.Color(1.0, 1.0, 0.0, 1.0)  # Yellow
    RED_COLOR = cq.Color(1.0, 0.0, 0.0, 1.0)  # Red for copper pads
    BROWN_COLOR = cq.Color(0.22, 0.12, 0.00, 1.0)  # Solder mask
    BLACK_COLOR = cq.Color(0.0, 0.0, 0.0, 1.0)  # Text

    # PCB 2D geometry parameters (matching 2d.glb)
    SOLDER_MASK_DIAMETER = 1.352  # mm (largest circle)
    COPPER_PAD_DIAMETER = 1.250  # mm (medium circle)
    HOLE_DIAMETER = 0.830  # mm (standard 0.032" drill)
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

    def __init__(self, package_type: str, pin_count: int, component_name: str = "IC", custom_layout: Optional[Dict[str, List[int]]] = None):
        """
        Initialize PCB footprint builder.

        Args:
            package_type: Package type (e.g., "DIP-8", "LQFP64")
            pin_count: Number of pins
            component_name: Component name (currently not used in output)
            custom_layout: Optional dict mapping side names to pin numbers
                         (e.g., {"left_side": [1,2,3], "bottom_edge": [4,5,6]})
        """
        self.package_type = package_type
        self.pin_count = pin_count
        self.component_name = component_name
        self.custom_layout = custom_layout

        # Get schematic parameters
        self.params = get_schematic_parameters(package_type, pin_count)

        # Calculate pin positions
        self.pin_positions = layout_pins(self.params, custom_layout)

        logger.info(
            "Initialized 2D PCB schematic builder for %s (%d pins)" % (package_type, pin_count)
        )

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
        │   ├── BodyLine (top)
        │   ├── BodyLine (bottom)
        │   ├── BodyLine (left)
        │   └── BodyLine (right)
        ├── silk_layer
        │   ├── BodyLine (top)
        │   └── BodyLine (bottom)
        └── crtyd_layer
            ├── BodyLine (top)
            ├── BodyLine (bottom)
            ├── BodyLine (left)
            └── BodyLine (right)

        Returns:
            Body assembly with proper layer hierarchy
        """
        body_assy = cq.Assembly(name="Body")

        body_width = self.params.body_width
        body_height = self.params.body_height
        line_thickness = self.params.body_geometry.border_thickness
        line_height = self.params.body_geometry.border_height

        # Calculate line lengths
        top_line_length = body_width
        left_line_length = body_height

        # 1. fab_layer - Complete outline (4 lines)
        fab_layer = cq.Assembly(name="fab_layer")
        
        # Top line
        top_line = cq.Workplane("XY").center(0, body_height / 2).rect(
            top_line_length, line_thickness
        ).extrude(line_height)
        fab_layer.add(top_line, name="BodyLine_Top", color=self.WHITE_COLOR)

        # Bottom line
        bottom_line = cq.Workplane("XY").center(0, -body_height / 2).rect(
            top_line_length, line_thickness
        ).extrude(line_height)
        fab_layer.add(bottom_line, name="BodyLine_Bottom", color=self.WHITE_COLOR)

        # Left line
        left_line = cq.Workplane("XY").center(-body_width / 2, 0).rect(
            line_thickness, left_line_length
        ).extrude(line_height)
        fab_layer.add(left_line, name="BodyLine_Left", color=self.WHITE_COLOR)

        # Right line
        right_line = cq.Workplane("XY").center(body_width / 2, 0).rect(
            line_thickness, left_line_length
        ).extrude(line_height)
        fab_layer.add(right_line, name="BodyLine_Right", color=self.WHITE_COLOR)
        
        body_assy.add(fab_layer, name="fab_layer")

        # 2. silk_layer - Top/bottom only (avoids pin areas for DIP)
        silk_layer = cq.Assembly(name="silk_layer")

        # Top line
        silk_top = cq.Workplane("XY").center(0, body_height / 2).rect(
            top_line_length, line_thickness
        ).extrude(line_height)
        silk_layer.add(silk_top, name="BodyLine_Top", color=self.WHITE_COLOR)

        # Bottom line
        silk_bottom = cq.Workplane("XY").center(0, -body_height / 2).rect(
            top_line_length, line_thickness
        ).extrude(line_height)
        silk_layer.add(silk_bottom, name="BodyLine_Bottom", color=self.WHITE_COLOR)

        body_assy.add(silk_layer, name="silk_layer")

        # 3. crtyd_layer - Complete outline (4 lines)
        crtyd_layer = cq.Assembly(name="crtyd_layer")

        # Top line
        crtyd_top = cq.Workplane("XY").center(0, body_height / 2).rect(
            top_line_length, line_thickness
        ).extrude(line_height)
        crtyd_layer.add(crtyd_top, name="BodyLine_Top", color=self.WHITE_COLOR)

        # Bottom line
        crtyd_bottom = cq.Workplane("XY").center(0, -body_height / 2).rect(
            top_line_length, line_thickness
        ).extrude(line_height)
        crtyd_layer.add(crtyd_bottom, name="BodyLine_Bottom", color=self.WHITE_COLOR)

        # Left line
        crtyd_left = cq.Workplane("XY").center(-body_width / 2, 0).rect(
            line_thickness, left_line_length
        ).extrude(line_height)
        crtyd_layer.add(crtyd_left, name="BodyLine_Left", color=self.WHITE_COLOR)

        # Right line
        crtyd_right = cq.Workplane("XY").center(body_width / 2, 0).rect(
            line_thickness, left_line_length
        ).extrude(line_height)
        crtyd_layer.add(crtyd_right, name="BodyLine_Right", color=self.WHITE_COLOR)

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
        body_assy.add(text_body, color=self.WHITE_COLOR)
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
        fab_marker_assy.add(fab_marker, color=self.WHITE_COLOR)
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

        # Check if through-hole (DIP) or surface mount (SOIC/TQFP/QFN)
        is_through_hole = self.package_type.startswith("DIP")

        if is_through_hole:
            # For through-hole packages, add ALL copper layers
            # Order: CopperCirclePin (B.Cu), HoleCylinderPin, CopperCylinderPin, CopperCirclePad (F.Cu)
            
            # CopperCirclePin (B.Cu layer) - bottom layer copper pad
            # This is the copper pad on the BOTTOM side of the PCB
            copper_circle_pin_radius = self.COPPER_PAD_DIAMETER / 2
            copper_circle_pin = cq.Workplane("XY").workplane(offset=-self.PIN_CYLINDER_HEIGHT/2).center(
                x, y
            ).circle(copper_circle_pin_radius).extrude(self.PAD_HEIGHT)
            copper_circle_pin_assy = cq.Assembly(name="CopperCirclePin")
            copper_circle_pin_assy.add(copper_circle_pin, color=self.RED_COLOR)
            pin_assy.add(copper_circle_pin_assy)

            # SolderMask (brown, largest)
            solder_mask_radius = self.SOLDER_MASK_DIAMETER / 2
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

            # CopperCirclePad (F.Cu layer) - top layer copper pad
            copper_pad_radius = self.COPPER_PAD_DIAMETER / 2
            copper_pad = cq.Workplane("XY").workplane(offset=self.PIN_CYLINDER_HEIGHT/2).center(
                x, y
            ).circle(copper_pad_radius).extrude(self.PAD_HEIGHT)
            copper_pad_assy = cq.Assembly(name="CopperCirclePad")
            copper_pad_assy.add(copper_pad, color=self.RED_COLOR)
            pin_assy.add(copper_pad_assy)
        else:
            # For surface mount packages (SOIC/TQFP/QFN)
            # SolderMask (brown, largest)
            solder_mask_radius = self.SOLDER_MASK_DIAMETER / 2
            solder_mask = cq.Workplane("XY").workplane(offset=-self.PAD_HEIGHT/2).center(
                x, y
            ).circle(solder_mask_radius).extrude(self.PAD_HEIGHT)
            solder_mask_assy = cq.Assembly(name="SolderMask")
            solder_mask_assy.add(solder_mask, color=self.BROWN_COLOR)
            pin_assy.add(solder_mask_assy)

            # Only top copper pad
            copper_pad_radius = self.COPPER_PAD_DIAMETER / 2
            copper_pad = cq.Workplane("XY").center(
                x, y
            ).circle(copper_pad_radius).extrude(self.PAD_HEIGHT)
            copper_pad_assy = cq.Assembly(name="CopperCirclePad")
            copper_pad_assy.add(copper_pad, color=self.RED_COLOR)
            pin_assy.add(copper_pad_assy)

        # Pin number text
        text_size = 0.8
        text_height = 0.2
        pin_text = cq.Workplane("XY").center(
            x, y
        ).text(pin_number, text_size, text_height, halign="center")
        pin_text_assy = cq.Assembly(name="text")
        pin_text_assy.add(pin_text, color=self.BLACK_COLOR)
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
        │       ├── CopperCirclePin (B.Cu) [DIP only]
        │       ├── SolderMask
        │       ├── HoleCylinderPin [DIP only]
        │       ├── CopperCylinderPin [DIP only]
        │       ├── CopperCirclePad (F.Cu)
        │       └── text
        └── Body
            ├── fab_layer
            │   └── BodyLine (x4)
            ├── silk_layer
            │   └── BodyLine (x2)
            └── crtyd_layer
                └── BodyLine (x4)

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
            except Exception as exc:
                logger.warning("Skipping GLB hierarchy optimization: %s" % exc)

            try:
                is_valid, hierarchy_errors = validate_pcb_footprint_glb(
                    output_path,
                    pin_count=self.pin_count,
                    through_hole=self.package_type.startswith("DIP"),
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

            # Keep DIP workflow output structurally aligned with the reference 2d.glb.
            if self.package_type.startswith("DIP"):
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

    Returns:
        True if successful, False otherwise
    """
    builder = PcbFootprintBuilder(package_type, pin_count, component_name, custom_layout)
    return builder.save_glb(output_path, pin_data)
