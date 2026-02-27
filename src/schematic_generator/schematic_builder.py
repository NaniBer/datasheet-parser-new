"""
Cadquery schematic builder for IC schematic symbols.

This module uses cadquery to create 3D schematic symbols from pin data.
Builds assembly hierarchy: Package -> BodyLine, Legs, DesignatorName, PackageValue
"""

import logging
import os
from typing import List, Dict, Any, Optional

import cadquery as cq

from .package_geometry import (
    PackageType,
    SchematicParameters,
    get_schematic_parameters,
)
from .pin_layout import PinPosition, layout_pins

# Setup logging
logger = logging.getLogger(__name__)


class SchematicBuilder:
    """
    Build schematic symbols using cadquery.

    Creates assembly hierarchy:
    Package (main)
    ├── BodyLine (wireframe border)
    │   ├── BodyLine_Top
    │   ├── BodyLine_Bottom
    │   ├── BodyLine_Left
    │   └── BodyLine_Right
    ├── Legs (all pins)
    │   ├── pin1 (leg, text, num)
    │   ├── pin2 (leg, text, num)
    │   └── ...
    ├── DesignatorName ("U")
    └── PackageValue (component name)
    """

    # Colors matching sample.gltf
    BLACK_COLOR = cq.Color(0, 0, 0, 1.0)
    PIN_COLOR = cq.Color(
        0.33725490196078434,
        0.12941176470588237,
        0.44313725490196076,
        1.0
    )

    def __init__(self, package_type: str, pin_count: int, component_name: str = "IC", custom_layout: Optional[Dict[str, List[int]]] = None):
        """
        Initialize schematic builder.

        Args:
            package_type: Package type (e.g., "DIP-8", "LQFP64")
            pin_count: Number of pins
            component_name: Component name for PackageValue label
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
            "Initialized schematic builder for %s (%d pins)" % (package_type, pin_count)
        )
        logger.info(
            "Body: %.1f x %.1f mm" % (self.params.body_width, self.params.body_height)
        )

    def build_body_border(self) -> cq.Assembly:
        """
        Build wireframe border for IC body.

        Creates thin rectangles on each side of the body.
        Returns BodyLine assembly with 4 border children.
        """
        body_line = cq.Assembly(name="BodyLine")

        bw = self.params.body_width
        bh = self.params.body_height
        thick = self.params.body_geometry.border_thickness
        height = self.params.body_geometry.border_height

        # Top border
        top = cq.Workplane("XY").center(0, bh / 2).rect(bw, thick).extrude(height)
        body_line.add(top, name="BodyLine_Top", color=self.BLACK_COLOR)

        # Bottom border
        bottom = cq.Workplane("XY").center(0, -bh / 2).rect(bw, thick).extrude(height)
        body_line.add(bottom, name="BodyLine_Bottom", color=self.BLACK_COLOR)

        # Left border
        left = cq.Workplane("XY").center(-bw / 2, 0).rect(thick, bh).extrude(height)
        body_line.add(left, name="BodyLine_Left", color=self.BLACK_COLOR)

        # Right border
        right = cq.Workplane("XY").center(bw / 2, 0).rect(thick, bh).extrude(height)
        body_line.add(right, name="BodyLine_Right", color=self.BLACK_COLOR)

        return body_line

    def build_pin(
        self, pin_pos: PinPosition, pin_name: str = "", pin_number: str = ""
    ) -> List[cq.Assembly]:
        """
        Build pin components (leg, text, pin number).

        Args:
            pin_pos: Pin position from layout algorithm
            pin_name: Pin function name (e.g., "GND", "VCC")
            pin_number: Pin number (e.g., "1", "A1")

        Returns:
            List of assemblies: [leg, pin_name_text, pin_number_text]
        """
        components = []

        # Pin leg (thin rectangle)
        leg_length = self.params.pin_geometry.leg_length
        leg_width = self.params.pin_geometry.leg_width
        leg_thickness = self.params.pin_geometry.leg_thickness

        # Create pin leg (for schematic symbols, we don't rotate - just position)
        pin_leg = cq.Workplane("XY").center(pin_pos.x, pin_pos.y).rect(
            leg_length, leg_width
        ).extrude(leg_thickness)

        leg_assy = cq.Assembly(name="%s_leg" % pin_number)
        leg_assy.add(pin_leg, color=self.PIN_COLOR)
        components.append(leg_assy)

        # Pin name text (function name)
        if pin_name:
            txt_size = self.params.pin_geometry.pin_name_size
            txt_height = self.params.pin_geometry.pin_name_height

            pin_name_text = cq.Workplane("XY").center(
                pin_pos.text_x, pin_pos.text_y
            ).text(pin_name[:30], txt_size, txt_height, halign=pin_pos.text_halign)

            name_assy = cq.Assembly(name="%s_text" % pin_number)
            name_assy.add(pin_name_text, color=self.BLACK_COLOR)
            components.append(name_assy)

        # Pin number text
        num_size = self.params.pin_geometry.pin_num_size
        num_height = self.params.pin_geometry.pin_num_height

        pin_num_text = cq.Workplane("XY").center(
            pin_pos.num_x, pin_pos.num_y
        ).text(pin_number, num_size, num_height, halign=pin_pos.num_halign)

        num_assy = cq.Assembly(name="%s_num" % pin_number)
        num_assy.add(pin_num_text, color=self.BLACK_COLOR)
        components.append(num_assy)

        return components

    def build_all_pins(
        self, pin_data: List[Dict[str, Any]]
    ) -> cq.Assembly:
        """
        Build all pins and organize into Legs assembly.

        Args:
            pin_data: List of pin dictionaries with 'pin_num', 'pin_name'

        Returns:
            Legs assembly containing all pins
        """
        legs_assy = cq.Assembly(name="Legs")

        # Create a mapping from pin number to position
        pin_number_to_position = {
            pos.pin_number: pos for pos in self.pin_positions
        }

        logger.info("Building %d pins" % len(pin_data))

        # Debug: print pin positions
        logger.debug("Pin positions:")
        for pin_num, pos in pin_number_to_position.items():
            logger.debug("  Pin %s: (%.1f, %.1f) %s" % (pin_num, pos.x, pos.y, pos.side))

        # Debug: print input pin data
        logger.debug("Input pin data:")
        for pin in pin_data:
            pin_num = str(pin.get("number", pin.get("pin_num", "")))
            pin_name = pin.get("name", pin.get("pin_name", ""))
            logger.debug("  Pin %s: %s" % (pin_num, pin_name))

        # Build each pin
        for pin in pin_data:
            pin_num = str(pin.get("number", pin.get("pin_num", "")))
            pin_name = pin.get("name", pin.get("pin_name", ""))

            # Get position from layout algorithm by pin number
            pin_pos = pin_number_to_position.get(pin_num)
            if pin_pos is None:
                logger.warning("No layout position for pin %s" % pin_num)
                continue

            logger.info("Building pin %s (%s) at (%.1f, %.1f) side=%s" % (pin_num, pin_name, pin_pos.x, pin_pos.y, pin_pos.side))

            # Build pin components
            pin_components = self.build_pin(pin_pos, pin_name, pin_num)

            # Add all components to Legs assembly
            for comp in pin_components:
                legs_assy.add(comp)

        return legs_assy

    def build_designator(self) -> cq.Assembly:
        """
        Build designator label ("U").

        Returns:
            Assembly with "U" text above body
        """
        size = self.params.body_geometry.designator_size
        height = self.params.body_geometry.designator_height
        offset = self.params.body_geometry.designator_offset

        designator = cq.Workplane("XY").center(
            0, self.params.body_height / 2 + offset
        ).text(
            self.params.body_geometry.designator_name,
            size,
            height,
        )

        assy = cq.Assembly(name="DesignatorName")
        assy.add(designator, color=self.BLACK_COLOR)
        return assy

    def build_package_value(self) -> cq.Assembly:
        """
        Build package value label (component name).

        Returns:
            Assembly with component name text above body
        """
        size = self.params.body_geometry.value_size
        height = self.params.body_geometry.value_height
        offset = self.params.body_geometry.value_offset

        # Truncate name if too long
        name = self.component_name[:30]

        value = cq.Workplane("XY").center(
            0, self.params.body_height / 2 + offset
        ).text(name, size, height)

        assy = cq.Assembly(name="PackageValue")
        assy.add(value, color=self.BLACK_COLOR)
        return assy

    def build_schematic(self, pin_data: List[Dict[str, Any]]) -> cq.Assembly:
        """
        Build complete schematic symbol assembly.

        Args:
            pin_data: List of pin dictionaries with 'number', 'name'

        Returns:
            Complete Package assembly with all components
        """
        # Main package assembly
        package_assy = cq.Assembly(name="Package")

        # 1. Add body border
        logger.info("Building body border...")
        body_line = self.build_body_border()
        package_assy.add(body_line, name="BodyLine")

        # 2. Add all pins
        logger.info("Building pins...")
        legs = self.build_all_pins(pin_data)
        package_assy.add(legs, name="Legs")

        # 3. Add designator label
        logger.info("Adding designator label...")
        designator = self.build_designator()
        package_assy.add(designator, name="DesignatorName")

        # 4. Add package value label
        logger.info("Adding package value label...")
        value = self.build_package_value()
        package_assy.add(value, name="PackageValue")

        logger.info(
            "Schematic assembly built: %d top-level components" % len(package_assy.children)
        )

        return package_assy

    def save_glb(self, output_path: str, pin_data: List[Dict[str, Any]]) -> bool:
        """
        Build and export schematic to GLB file.

        Args:
            output_path: Path to save GLB file
            pin_data: List of pin dictionaries

        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("Building schematic for %s..." % output_path)

            # Build schematic assembly
            assembly = self.build_schematic(pin_data)

            # Save to GLB
            logger.info("Saving to %s..." % output_path)
            assembly.save(output_path)

            logger.info("Successfully saved schematic to %s" % output_path)

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


def build_schematic_from_pin_data(
    package_type: str,
    pin_count: int,
    component_name: str,
    pin_data: List[Dict[str, Any]],
    output_path: str,
    custom_layout: Optional[Dict[str, List[int]]] = None,
) -> bool:
    """
    Convenience function to build and export schematic from pin data.

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
    builder = SchematicBuilder(package_type, pin_count, component_name, custom_layout)
    return builder.save_glb(output_path, pin_data)
