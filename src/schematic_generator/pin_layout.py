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
    """

    def __init__(self, params: SchematicParameters):
        """
        Initialize pin layout with schematic parameters.

        Args:
            params: SchematicParameters for the package
        """
        self.params = params

    def layout_all_pins(self) -> List[PinPosition]:
        """
        Calculate positions for all pins in the package.

        Returns:
            List of PinPosition for all pins (in sorted order)
        """
        positions = []

        if self.params.package_type == PackageType.DIP:
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
            text_x = x + self.params.pin_geometry.pin_name_offset
            num_x = x + self.params.pin_geometry.pin_num_offset

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
        # For DIP clockwise: pin 5 at bottom, pin 8 at top
        for i in range(pins_per_side):
            # Calculate Y position from bottom to top
            y = -(self.params.body_height / 2) + self.params.body_geometry.top_margin + (i * self.params.pin_pitch)
            x = self.params.body_width / 2
            pin_num = pins_per_side + i + 1

            # Pin leg points right
            text_x = x - self.params.pin_geometry.pin_name_offset
            num_x = x - self.params.pin_geometry.pin_num_offset

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


def layout_pins(params: SchematicParameters) -> List[PinPosition]:
    """
    Convenience function to layout pins for a package.

    Args:
        params: SchematicParameters for the package

    Returns:
        List of PinPosition for all pins

    Example:
        >>> from src.schematic_generator import get_schematic_parameters, layout_pins
        >>> params = get_schematic_parameters("DIP-8", 8)
        >>> positions = layout_pins(params)
        >>> for pos in positions[:4]:
        ...     print(f"Pin {pos.pin_number}: ({pos.x:.2f}, {pos.y:.2f}) {pos.side}")
    """
    layout = PinLayout(params)
    return layout.layout_all_pins()
