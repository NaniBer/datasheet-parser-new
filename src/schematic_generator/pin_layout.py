"""
Pin layout algorithms for schematic symbols.

This module implements algorithms to position pins correctly for different
package types, handling the specific pin numbering conventions for each.
"""

from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional
import math

from .package_geometry import SchematicParameters, PackageType


@dataclass
class PinPosition:
    """Position and orientation for a pin in a schematic."""
    pin_index: int  # Index in sorted pin list (0-based)
    pin_number: str  # Display number (e.g., "1", "2", "A1")
    x: float  # X coordinate (mm)
    y: float  # Y coordinate (mm)
    side: str  # "left", "right", "top", "bottom"
    rotation: float  # Rotation angle in degrees (0 = pointing right)

    # Text positions
    text_x: float  # X for pin name text
    text_y: float  # Y for pin name text
    text_halign: str  # "left", "right", or "center"

    num_x: float  # X for pin number
    num_y: float  # Y for pin number
    num_halign: str  # "left", "right", or "center"


class PinLayout:
    """
    Pin layout algorithm for schematic symbols.

    Handles different pin numbering conventions for each package type:
    - DIP: Clockwise numbering (1 at top-left, down left, up right)
    - TQFP/LQFP: Counter-clockwise numbering (1 at top-left, counter-clockwise)
    - SOIC: Counter-clockwise numbering
    - Custom: Layout defined by Vision API (non-standard packages)
    """

    def __init__(self, params: SchematicParameters, custom_layout: Optional[Dict[str, List[int]]] = None):
        """
        Initialize pin layout with schematic parameters.

        Args:
            params: SchematicParameters for the package
            custom_layout: Optional dict mapping side names to pin numbers
                         (e.g., {"left_side": [1,2,3], "bottom_edge": [4,5,6]})
        """
        self.params = params
        self.custom_layout = custom_layout

    def layout_all_pins(self) -> List[PinPosition]:
        """
        Calculate positions for all pins in the package.

        Returns:
            List of PinPosition for all pins (in sorted order)
        """
        positions = []

        # Use custom layout if provided (from Vision API)
        if self.custom_layout:
            positions = self._layout_custom_pins()
        elif self.params.package_type == PackageType.DIP:
            positions = self._layout_dip_pins()
        elif self.params.package_type in [PackageType.TQFP, PackageType.LQFP]:
            positions = self._layout_quad_pins()
        elif self.params.package_type == PackageType.QFN:
            positions = self._layout_quad_pins()
        elif self.params.package_type == PackageType.BGA:
            positions = self._layout_bga_pins()
        else:
            # Default to DIP
            positions = self._layout_dip_pins()

        return positions

    def _layout_dip_pins(self) -> List[PinPosition]:
        """
        Layout pins for DIP (Dual Inline Package).

        Pin numbering is COUNTER-CLOCKWISE:
        - Pin 1: Top-left corner
        - Pins 1 to N/2: Left side, going DOWN
        - Pins N/2+1 to N: Right side, going UP

        Example for DIP-8:
            Pin 1 ┐  Pin 8
            Pin 2 │  Pin 7
            Pin 3 │  Pin 6
            Pin 4 ┘  Pin 5
        """
        positions = []
        pin_count = self.params.pin_count
        pins_per_side = pin_count // 2

        # Left side: pins 1 to pins_per_side (top to bottom)
        for i in range(pins_per_side):
            y = (self.params.body_height / 2) - self.params.body_geometry.top_margin - (i * self.params.pin_pitch)
            x = -self.params.body_width / 2

            # Pin leg points left
            # Text should be OUTSIDE the component (left side)
            text_x = x - self.params.pin_geometry.pin_name_offset
            num_x = x - self.params.pin_geometry.pin_num_offset

            positions.append(PinPosition(
                pin_index=i,
                pin_number=str(i + 1),
                x=x,
                y=y,
                side="left",
                rotation=180,  # Pointing left
                text_x=text_x,
                text_y=y,
                text_halign="left",
                num_x=num_x,
                num_y=y,
                num_halign="left"
            ))

        # Right side: pins pins_per_side+1 to pin_count (bottom to top)
        # For DIP counter-clockwise: pin 5 at bottom, pin 8 at top
        # IMPORTANT: Right side must go BOTTOM to TOP for counter-clockwise numbering
        for i in range(pins_per_side):
            # Calculate Y position - need to go bottom-to-top for counter-clockwise
            # Use reversed index: pins_per_side - 1 - i
            reversed_idx = pins_per_side - 1 - i
            y = (self.params.body_height / 2) - self.params.body_geometry.top_margin - (reversed_idx * self.params.pin_pitch)
            x = self.params.body_width / 2
            pin_num = pins_per_side + i + 1

            # Pin leg points right
            # Text should be OUTSIDE the component (right side)
            text_x = x + self.params.pin_geometry.pin_name_offset
            num_x = x + self.params.pin_geometry.pin_num_offset

            positions.append(PinPosition(
                pin_index=pins_per_side + i,
                pin_number=str(pin_num),
                x=x,
                y=y,
                side="right",
                rotation=0,  # Pointing right
                text_x=text_x,
                text_y=y,
                text_halign="right",
                num_x=num_x,
                num_y=y,
                num_halign="right"
            ))

        return positions

    def _layout_quad_pins(self) -> List[PinPosition]:
        """
        Layout pins for TQFP/LQFP (Quad Flat Package).

        Pin numbering is COUNTER-CLOCKWISE:
        - Pin 1: Top-left corner
        - Left side: Top to bottom
        - Bottom side: Left to right
        - Right side: Bottom to top
        - Top side: Right to left

        Example for TQFP-44 (11 pins per side):
            Pin 11  Pin 10  ...  Pin 12
            Pin 1            ...            Pin 23
            Pin 2            ...            Pin 22
            ...              ...            ...
            Pin 12           ...            Pin 34
            Pin 34  Pin 35  ...  Pin 33
        """
        positions = []
        pin_count = self.params.pin_count
        pins_per_side = pin_count // 4
        top_margin = self.params.body_geometry.top_margin

        # LEFT SIDE: pins 0 to pins_per_side-1 (top to bottom)
        for i in range(pins_per_side):
            y = (self.params.body_height / 2) - top_margin - (i * self.params.pin_pitch)
            x = -self.params.body_width / 2

            text_x = x + self.params.pin_geometry.pin_name_offset
            num_x = x + self.params.pin_geometry.pin_num_offset

            positions.append(PinPosition(
                pin_index=i,
                pin_number=str(i + 1),
                x=x,
                y=y,
                side="left",
                rotation=180,
                text_x=text_x,
                text_y=y,
                text_halign="left",
                num_x=num_x,
                num_y=y,
                num_halign="left"
            ))

        # BOTTOM SIDE: pins pins_per_side to 2*pins_per_side-1 (left to right)
        for i in range(pins_per_side):
            x = -(self.params.body_width / 2) + top_margin + (i * self.params.pin_pitch)
            y = -self.params.body_height / 2
            pin_idx = pins_per_side + i

            text_x = x
            text_y = y - self.params.pin_geometry.pin_name_offset
            num_x = x
            num_y = y - self.params.pin_geometry.pin_num_offset

            positions.append(PinPosition(
                pin_index=pin_idx,
                pin_number=str(pin_idx + 1),
                x=x,
                y=y,
                side="bottom",
                rotation=270,  # Pointing down
                text_x=text_x,
                text_y=text_y,
                text_halign="center",
                num_x=num_x,
                num_y=num_y,
                num_halign="center"
            ))

        # RIGHT SIDE: pins 2*pins_per_side to 3*pins_per_side-1 (bottom to top)
        for i in range(pins_per_side):
            right_idx = pins_per_side - 1 - i  # Reverse for bottom-to-top
            y = -(self.params.body_height / 2) + top_margin + (right_idx * self.params.pin_pitch)
            x = self.params.body_width / 2
            pin_idx = 2 * pins_per_side + i

            text_x = x - self.params.pin_geometry.pin_name_offset
            num_x = x - self.params.pin_geometry.pin_num_offset

            positions.append(PinPosition(
                pin_index=pin_idx,
                pin_number=str(pin_idx + 1),
                x=x,
                y=y,
                side="right",
                rotation=0,
                text_x=text_x,
                text_y=y,
                text_halign="right",
                num_x=num_x,
                num_y=y,
                num_halign="right"
            ))

        # TOP SIDE: pins 3*pins_per_side to 4*pins_per_side-1 (right to left)
        for i in range(pins_per_side):
            top_idx = pins_per_side - 1 - i  # Reverse for right-to-left
            x = (self.params.body_width / 2) - top_margin - (top_idx * self.params.pin_pitch)
            y = self.params.body_height / 2
            pin_idx = 3 * pins_per_side + i

            text_x = x
            text_y = y + self.params.pin_geometry.pin_name_offset
            num_x = x
            num_y = y + self.params.pin_geometry.pin_num_offset

            positions.append(PinPosition(
                pin_index=pin_idx,
                pin_number=str(pin_idx + 1),
                x=x,
                y=y,
                side="top",
                rotation=90,  # Pointing up
                text_x=text_x,
                text_y=text_y,
                text_halign="center",
                num_x=num_x,
                num_y=num_y,
                num_halign="center"
            ))

        return positions

    def _layout_bga_pins(self) -> List[PinPosition]:
        """
        Layout pins for BGA (Ball Grid Array).

        BGA pins are arranged in a grid on the bottom of the package.
        Numbering follows a row/column scheme (e.g., A1, A2, ..., B1, B2, ...).

        This is a simplified 2D representation with balls shown around the edges.
        """
        positions = []
        pin_count = self.params.pin_count

        # For BGA, distribute pins evenly around the perimeter
        # This is a simplified representation
        perimeter_pins = min(pin_count, int(self.params.body_width + self.params.body_height) * 2)

        for i in range(perimeter_pins):
            # Distribute around perimeter (top, right, bottom, left)
            perimeter = 2 * (self.params.body_width + self.params.body_height)
            position = (i * perimeter) / perimeter_pins

            if position < self.params.body_width:
                # Top side (left to right)
                x = -self.params.body_width / 2 + position
                y = self.params.body_height / 2
                side = "top"
                rotation = 90
            elif position < self.params.body_width + self.params.body_height:
                # Right side (top to bottom)
                right_pos = position - self.params.body_width
                x = self.params.body_width / 2
                y = self.params.body_height / 2 - right_pos
                side = "right"
                rotation = 0
            elif position < 2 * self.params.body_width + self.params.body_height:
                # Bottom side (right to left)
                bottom_pos = position - (self.params.body_width + self.params.body_height)
                x = self.params.body_width / 2 - bottom_pos
                y = -self.params.body_height / 2
                side = "bottom"
                rotation = 270
            else:
                # Left side (bottom to top)
                left_pos = position - (2 * self.params.body_width + self.params.body_height)
                x = -self.params.body_width / 2
                y = -self.params.body_height / 2 + left_pos
                side = "left"
                rotation = 180

            # Set text positions based on side
            if side == "left":
                text_x = x + self.params.pin_geometry.pin_name_offset
                num_x = x + self.params.pin_geometry.pin_num_offset
                text_halign = num_halign = "left"
            elif side == "right":
                text_x = x - self.params.pin_geometry.pin_name_offset
                num_x = x - self.params.pin_geometry.pin_num_offset
                text_halign = num_halign = "right"
            elif side == "top":
                text_x = x
                num_x = x
                text_y = y + self.params.pin_geometry.pin_name_offset
                num_y = y + self.params.pin_geometry.pin_num_offset
                text_halign = num_halign = "center"
            else:  # bottom
                text_x = x
                num_x = x
                text_y = y - self.params.pin_geometry.pin_name_offset
                num_y = y - self.params.pin_geometry.pin_num_offset
                text_halign = num_halign = "center"

            positions.append(PinPosition(
                pin_index=i,
                pin_number=str(i + 1),
                x=x,
                y=y,
                side=side,
                rotation=rotation,
                text_x=text_x,
                text_y=text_y if side in ["top", "bottom"] else y,
                text_halign=text_halign,
                num_x=num_x,
                num_y=num_y if side in ["top", "bottom"] else y,
                num_halign=num_halign
            ))

        return positions

    def _layout_custom_pins(self) -> List[PinPosition]:
        """
        Layout pins using custom layout data from Vision API.

        Uses layout_sections dict that maps section names to pin numbers:
        {
            "left_side": [1, 2, 3, ...],
            "bottom_edge": [15, 16, ...],
            "right_side": [25, 26, ...],
            "top_edge": [10, 11, ...]  # optional
        }

        Parses section names to determine side and placement order.
        """
        positions = []

        # Map section names to sides
        side_mapping = {
            "left": "left",
            "left_side": "left",
            "left column": "left",
            "left side column": "left",
            "right": "right",
            "right_side": "right",
            "right column": "right",
            "right side column": "right",
            "top": "top",
            "top_edge": "top",
            "top edge": "top",
            "bottom": "bottom",
            "bottom_edge": "bottom",
            "bottom edge": "bottom",
        }

        # Group sections by side and determine order
        sections_by_side = {}
        section_order = []  # Track order sections were provided

        for section_name, pin_numbers in self.custom_layout.items():
            # Parse section name to get side
            section_lower = section_name.lower()
            side = "left"  # default

            # Try to find matching side
            for key, mapped_side in side_mapping.items():
                if key in section_lower:
                    side = mapped_side
                    break

            if side not in sections_by_side:
                sections_by_side[side] = []
            sections_by_side[side].append((section_name, pin_numbers))
            section_order.append((side, section_name, pin_numbers))

        # Layout parameters
        body_width = self.params.body_width
        body_height = self.params.body_height
        pin_pitch = self.params.pin_pitch
        top_margin = self.params.body_geometry.top_margin

        # Process each section in order
        pin_index = 0
        for side, section_name, pin_numbers in section_order:
            if side == "left":
                # Left side: top to bottom
                for i, pin_num in enumerate(pin_numbers):
                    y = (body_height / 2) - top_margin - (i * pin_pitch)
                    x = -body_width / 2

                    positions.append(PinPosition(
                        pin_index=pin_index,
                        pin_number=str(pin_num),
                        x=x,
                        y=y,
                        side=side,
                        rotation=180,  # Pointing left
                        text_x=x - self.params.pin_geometry.pin_name_offset,
                        text_y=y,
                        text_halign="left",
                        num_x=x - self.params.pin_geometry.pin_num_offset,
                        num_y=y,
                        num_halign="left"
                    ))
                    pin_index += 1

            elif side == "right":
                # Right side: top to bottom (or bottom to top depending on data)
                for i, pin_num in enumerate(pin_numbers):
                    y = (body_height / 2) - top_margin - (i * pin_pitch)
                    x = body_width / 2

                    positions.append(PinPosition(
                        pin_index=pin_index,
                        pin_number=str(pin_num),
                        x=x,
                        y=y,
                        side=side,
                        rotation=0,  # Pointing right
                        text_x=x + self.params.pin_geometry.pin_name_offset,
                        text_y=y,
                        text_halign="right",
                        num_x=x + self.params.pin_geometry.pin_num_offset,
                        num_y=y,
                        num_halign="right"
                    ))
                    pin_index += 1

            elif side == "bottom":
                # Bottom side: left to right
                for i, pin_num in enumerate(pin_numbers):
                    x = -(body_width / 2) + top_margin + (i * pin_pitch)
                    y = -body_height / 2

                    positions.append(PinPosition(
                        pin_index=pin_index,
                        pin_number=str(pin_num),
                        x=x,
                        y=y,
                        side=side,
                        rotation=270,  # Pointing down
                        text_x=x,
                        text_y=y - self.params.pin_geometry.pin_name_offset,
                        text_halign="center",
                        num_x=x,
                        num_y=y - self.params.pin_geometry.pin_num_offset,
                        num_halign="center"
                    ))
                    pin_index += 1

            elif side == "top":
                # Top side: left to right
                for i, pin_num in enumerate(pin_numbers):
                    x = -(body_width / 2) + top_margin + (i * pin_pitch)
                    y = body_height / 2

                    positions.append(PinPosition(
                        pin_index=pin_index,
                        pin_number=str(pin_num),
                        x=x,
                        y=y,
                        side=side,
                        rotation=90,  # Pointing up
                        text_x=x,
                        text_y=y + self.params.pin_geometry.pin_name_offset,
                        text_halign="center",
                        num_x=x,
                        num_y=y + self.params.pin_geometry.pin_num_offset,
                        num_halign="center"
                    ))
                    pin_index += 1

        return positions


def layout_pins(params: SchematicParameters, custom_layout: Optional[Dict[str, List[int]]] = None) -> List[PinPosition]:
    """
    Convenience function to layout pins for a package.

    Args:
        params: SchematicParameters for the package
        custom_layout: Optional dict mapping side names to pin numbers
                     (e.g., {"left_side": [1,2,3], "bottom_edge": [4,5,6]})

    Returns:
        List of PinPosition for all pins

    Example:
        >>> from src.schematic_generator import get_schematic_parameters, layout_pins
        >>> params = get_schematic_parameters("DIP-8", 8)
        >>> positions = layout_pins(params)
        >>> for pos in positions[:4]:
        ...     print(f"Pin {pos.pin_number}: ({pos.x:.2f}, {pos.y:.2f}) {pos.side}")
    """
    layout = PinLayout(params, custom_layout)
    return layout.layout_all_pins()
