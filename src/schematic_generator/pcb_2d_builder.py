"""
2D PCB-style schematic builder.

Creates PCB-style schematics with through-hole pins matching 2D GLB format.
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
from .pin_layout import PinPosition, layout_pins

# Setup logging
logger = logging.getLogger(__name__)


class Pcb2dBuilder:
    """Build 2D PCB-style schematic symbols using cadquery."""

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

    """
    Build 2D PCB-style schematic symbols using cadquery.

    Creates assembly hierarchy:
    Package (main)
    ├── BodyLine (wireframe border)
    │   ├── BodyLine_Top
    │   ├── BodyLine_Bottom
    │   ├── BodyLine_Left
    │   └── BodyLine_Right
    ├── FirstPinMarker (pin 1 indicator)
    │   ├── silk_firstPinMarker
    │   └── fab_firstPinMarker
    └── Legs (all pins)
        ├── pin1 (leg, text, num)
        ├── pin2 (leg, text, num)
        └── ...
    """
    """
    Build 2D PCB-style schematic symbols using cadquery.

    Creates assembly hierarchy:
    Package (main)
    ├── BodyLine (wireframe border)
    │   ├── BodyLine_Top
    │   ├── BodyLine_Bottom
    │   ├── BodyLine_Left
    │   └── BodyLine_Right
    ├── FirstPinMarker (pin 1 indicator)
    │   ├── silk_firstPinMarker
    │   └── fab_firstPinMarker
    └── Legs (all pins)
        ├── pin1 (leg, text, num)
        ├── pin2 (leg, text, num)
        └── ...
    """

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
        Initialize 2D PCB schematic builder.

        Args:
            package_type: Package type (e.g., "DIP-8", "LQFP64")
            pin_count: Number of pins
            component_name: Component name (currently not used in 2D output)
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

    def calculate_pin_positions_2d(self) -> List[PinPosition]:
        """
        Get pin positions for 2D PCB schematic using the existing 3D pin layout.

        Returns:
            List of PinPosition objects
        """
        # Use the same pin layout as 3D schematic
        return self.pin_positions

    def build_body_line(self) -> cq.Assembly:
        """
        Build wireframe border for component body.

        Creates thin rectangles on each side of the body.
        Uses the same body dimensions as the 3D schematic.
        Returns BodyLine assembly with 4 border children.
        """
        body_line = cq.Assembly(name="BodyLine")

        # Use the same body dimensions as 3D schematic
        body_width = self.params.body_width
        body_height = self.params.body_height
        line_thickness = self.params.body_geometry.border_thickness
        line_height = self.params.body_geometry.border_height

        # Calculate line lengths
        top_line_length = body_width
        left_line_length = body_height

        # Top line
        top_line = cq.Workplane("XY").center(0, body_height / 2).rect(
            top_line_length, line_thickness
        ).extrude(line_height)
        top_line_assy = cq.Assembly(name="BodyLine_Top")
        top_line_assy.add(top_line, color=self.BLACK_COLOR)
        body_line.add(top_line_assy)

        # Bottom line
        bottom_line = cq.Workplane("XY").center(0, -body_height / 2).rect(
            top_line_length, line_thickness
        ).extrude(line_height)
        bottom_line_assy = cq.Assembly(name="BodyLine_Bottom")
        bottom_line_assy.add(bottom_line, color=self.BLACK_COLOR)
        body_line.add(bottom_line_assy)

        # Left line
        left_line = cq.Workplane("XY").center(-body_width / 2, 0).rect(
            line_thickness, left_line_length
        ).extrude(line_height)
        left_line_assy = cq.Assembly(name="BodyLine_Left")
        left_line_assy.add(left_line, color=self.BLACK_COLOR)
        body_line.add(left_line_assy)

        # Right line
        right_line = cq.Workplane("XY").center(body_width / 2, 0).rect(
            line_thickness, left_line_length
        ).extrude(line_height)
        right_line_assy = cq.Assembly(name="BodyLine_Right")
        right_line_assy.add(right_line, color=self.BLACK_COLOR)
        body_line.add(right_line_assy)

        return body_line

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

        # SolderMask (brown, largest)
        solder_mask_radius = self.SOLDER_MASK_DIAMETER / 2
        solder_mask = cq.Workplane("XY").workplane(offset=-self.PAD_HEIGHT/2).center(
            x, y
        ).circle(solder_mask_radius).extrude(self.PAD_HEIGHT)
        solder_mask_assy = cq.Assembly(name="SolderMask")
        solder_mask_assy.add(solder_mask, color=self.BROWN_COLOR)
        pin_assy.add(solder_mask_assy)

        # CopperCirclePad (red, medium)
        copper_pad_radius = self.COPPER_PAD_DIAMETER / 2
        copper_pad = cq.Workplane("XY").workplane(offset=-self.PAD_HEIGHT/2).center(
            x, y
        ).circle(copper_pad_radius).extrude(self.PAD_HEIGHT)
        copper_pad_assy = cq.Assembly(name="CopperCirclePad")
        copper_pad_assy.add(copper_pad, color=self.RED_COLOR)
        pin_assy.add(copper_pad_assy)

        # Check if through-hole (DIP) or surface mount (SOIC/TQFP/QFN)
        is_through_hole = self.package_type.startswith("DIP")

        if is_through_hole:
            # HoleCylinderPin (black) - for through-hole packages only
            hole_radius = self.HOLE_DIAMETER / 2
            hole_cylinder = cq.Workplane("XY").center(
                x, y
            ).circle(hole_radius).extrude(self.PIN_CYLINDER_HEIGHT)
            hole_cylinder_assy = cq.Assembly(name="HoleCylinderPin")
            hole_cylinder_assy.add(hole_cylinder, color=self.BLACK_COLOR)
            pin_assy.add(hole_cylinder_assy)

            # CopperCylinderPin (red) - for through-hole packages only
            copper_cylinder = cq.Workplane("XY").center(
                x, y
            ).circle(hole_radius).extrude(self.PIN_CYLINDER_HEIGHT)
            copper_cylinder_assy = cq.Assembly(name="CopperCylinderPin")
            copper_cylinder_assy.add(copper_cylinder, color=self.RED_COLOR)
            pin_assy.add(copper_cylinder_assy)

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
        Build complete 2D PCB schematic symbol assembly.

        Args:
            pin_data: List of pin dictionaries with 'number', 'name'

        Returns:
            Complete Package assembly with all components
        """
        # Main package assembly
        package_assy = cq.Assembly(name="Package")

        # Get pin positions using the same 3D pin layout
        pin_positions = self.calculate_pin_positions_2d()

        # Add body line
        logger.info("Building body line...")
        body_line = self.build_body_line()
        package_assy.add(body_line, name="BodyLine")

        # Add pin 1 marker
        logger.info("Building pin 1 marker...")
        markers = self.build_first_pin_marker(pin_positions)
        if markers:
            package_assy.add(markers, name="FirstPinMarker")

        # Add all pins
        logger.info("Building pins...")
        legs = self.build_all_pins(pin_data, pin_positions)
        package_assy.add(legs, name="Legs")

        logger.info(
            "2D PCB schematic assembly built: %d top-level components" % len(package_assy.children)
        )

        return package_assy

    def save_glb(self, output_path: str, pin_data: List[Dict[str, Any]]) -> bool:
        """
        Build and export 2D PCB schematic to GLB file.

        Args:
            output_path: Path to save GLB file
            pin_data: List of pin dictionaries

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("Building 2D PCB schematic for %s..." % output_path)

            # Build schematic assembly
            assembly = self.build_schematic(pin_data)

            # Save to GLB
            logger.info("Saving to %s..." % output_path)
            assembly.save(output_path)

            logger.info("Successfully saved 2D PCB schematic to %s" % output_path)

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


def build_pcb_2d_schematic(
    package_type: str,
    pin_count: int,
    component_name: str,
    pin_data: List[Dict[str, Any]],
    output_path: str,
    custom_layout: Optional[Dict[str, List[int]]] = None,
) -> bool:
    """
    Convenience function to build and export 2D PCB schematic from pin data.

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
    builder = Pcb2dBuilder(package_type, pin_count, component_name, custom_layout)
    return builder.save_glb(output_path, pin_data)
