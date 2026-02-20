"""
Schematic symbol geometry parameters for different IC package types.

This module defines the physical dimensions and layout parameters for creating
schematic symbols using cadquery. Parameters are based on standard package
dimensions and can be customized as needed.
"""

from dataclasses import dataclass
from typing import Tuple, List
from enum import Enum


class PackageType(Enum):
    """Supported package types for schematic symbols."""
    DIP = "DIP"  # Dual Inline Package
    SOIC = "SOIC"  # Small Outline IC
    TQFP = "TQFP"  # Thin Quad Flat Package
    QFN = "QFN"  # Quad Flat No-leads
    LQFP = "LQFP"  # Low-profile Quad Flat Package
    BGA = "BGA"  # Ball Grid Array


@dataclass
class PinGeometry:
    """Geometry parameters for individual pins."""
    leg_length: float = 6.0  # Length of pin leg (mm)
    leg_width: float = 0.15  # Width of pin leg (mm)
    leg_thickness: float = 0.5  # Extrusion thickness (mm)
    point_size: float = 0.5  # Size of pin point (mm)

    # Text positioning
    pin_num_size: float = 1.5  # Font size for pin number
    pin_num_offset: float = 4.0  # Distance from body edge to pin number
    pin_name_size: float = 2.0  # Font size for pin name
    pin_name_offset: float = 8.0  # Distance from body edge to pin name
    pin_name_height: float = 0.5  # Text height (extrusion)


@dataclass
class BodyGeometry:
    """Geometry parameters for the IC body."""
    border_thickness: float = 0.5  # Thickness of body border lines (mm)
    border_height: float = 0.5  # Extrusion height of border (mm)

    # Labels
    designator_name: str = "U"  # Designator letter
    designator_size: float = 4.0  # Font size for designator
    designator_offset: float = 8.0  # Distance above body
    designator_height: float = 0.5  # Text height

    value_size: float = 2.0  # Font size for package value
    value_offset: float = 3.0  # Distance above body (below designator)
    value_height: float = 0.5  # Text height

    # Spacing from body top to first pin
    top_margin: float = 10.0  # Margin from top to first pin row (mm)


@dataclass
class SchematicParameters:
    """
    Complete schematic symbol parameters for a specific package.

    These parameters define how to layout pins and body for schematic symbols.
    """
    package_type: PackageType
    pin_count: int
    pin_pitch: float  # Vertical/vertical spacing between pins (mm)
    body_width: float  # Width of component body (mm)
    body_height: float  # Height of component body (mm)
    pin_geometry: PinGeometry
    body_geometry: BodyGeometry

    # Pin layout: pins on each side [left, right, top, bottom]
    # For DIP: [left_count, right_count, 0, 0]
    # For TQFP: [left_count, right_count, top_count, bottom_count]
    pins_per_side: List[int]

    # Pin numbering order
    # True = counter-clockwise (TQFP, SOIC)
    # False = clockwise (DIP)
    counter_clockwise: bool = True


# ============================================================================
# Standard Package Parameters
# ============================================================================

def get_dip_parameters(pin_count: int) -> SchematicParameters:
    """
    Get schematic parameters for DIP (Dual Inline Package).

    DIP packages have pins on two sides (left and right).
    Pin numbering is clockwise: starts at top-left, goes down left side,
    then up right side.

    Examples:
        - DIP-8: NE555 timer
        - DIP-14: 74-series logic
        - DIP-28: ATmega328P
        - DIP-40: ATmega32
    """
    # Standard DIP pitch is 2.54mm (0.1 inch)
    pitch = 2.54

    # Calculate body dimensions based on pin count
    # DIP standard: width ~7.62mm, height scales with pin count
    width = 7.62

    # Height = (pins_per_side - 1) * pitch + margins
    pins_per_side = pin_count // 2
    height = (pins_per_side - 1) * pitch + 15.0  # 15mm for margins

    return SchematicParameters(
        package_type=PackageType.DIP,
        pin_count=pin_count,
        pin_pitch=pitch,
        body_width=width,
        body_height=height,
        pin_geometry=PinGeometry(
            leg_length=5.0,
            leg_width=0.15,
            leg_thickness=0.5,
            point_size=0.5,
            pin_num_size=1.5,
            pin_num_offset=3.0,
            pin_name_size=2.0,
            pin_name_offset=7.0,
            pin_name_height=0.5
        ),
        body_geometry=BodyGeometry(
            border_thickness=0.5,
            border_height=0.5,
            designator_name="U",
            designator_size=4.0,
            designator_offset=5.0,
            designator_height=0.5,
            value_size=2.0,
            value_offset=2.0,
            value_height=0.5,
            top_margin=7.0
        ),
        pins_per_side=[pins_per_side, pins_per_side, 0, 0],
        counter_clockwise=True  # Counter-clockwise numbering for DIP
    )


def get_soic_parameters(pin_count: int) -> SchematicParameters:
    """
    Get schematic parameters for SOIC (Small Outline IC).

    SOIC packages are surface-mount with pins on two sides.
    Smaller than DIP, typically 1.27mm pitch.
    """
    pitch = 1.27
    width = 5.0
    pins_per_side = pin_count // 2
    height = (pins_per_side - 1) * pitch + 8.0

    return SchematicParameters(
        package_type=PackageType.SOIC,
        pin_count=pin_count,
        pin_pitch=pitch,
        body_width=width,
        body_height=height,
        pin_geometry=PinGeometry(leg_length=4.0, leg_width=0.1, pin_name_offset=6.0),
        body_geometry=BodyGeometry(top_margin=5.0),
        pins_per_side=[pins_per_side, pins_per_side, 0, 0],
        counter_clockwise=True
    )


def get_tqfp_parameters(pin_count: int) -> SchematicParameters:
    """
    Get schematic parameters for TQFP (Thin Quad Flat Package).

    TQFP packages have pins on all 4 sides.
    Pin numbering is counter-clockwise starting at top-left.
    Common pin counts: 32, 44, 48, 64, 100, 128, 144.
    Pin pitch is typically 0.5mm or 0.8mm.

    Examples:
        - TQFP-44: ATmega164A
        - LQFP-64: STM32F103
    """
    pitch = 0.5  # 0.5mm is common for TQFP

    # Calculate body width based on pin count
    # More pins = larger body
    pins_per_side = pin_count // 4

    # Body size scales with pin count
    # TQFP-44: ~10mm, TQFP-64: ~12mm, TQFP-100: ~14mm
    width = 8.0 + (pins_per_side * pitch)
    height = width  # Square

    return SchematicParameters(
        package_type=PackageType.TQFP,
        pin_count=pin_count,
        pin_pitch=pitch,
        body_width=width,
        body_height=height,
        pin_geometry=PinGeometry(
            leg_length=3.0,
            leg_width=0.1,
            leg_thickness=0.3,
            point_size=0.3,
            pin_num_size=1.0,
            pin_num_offset=2.0,
            pin_name_size=1.5,
            pin_name_offset=4.0,
            pin_name_height=0.3
        ),
        body_geometry=BodyGeometry(
            border_thickness=0.3,
            border_height=0.3,
            designator_size=3.0,
            designator_offset=5.0,
            top_margin=4.0
        ),
        pins_per_side=[pins_per_side, pins_per_side, pins_per_side, pins_per_side],
        counter_clockwise=True
    )


def get_qfn_parameters(pin_count: int) -> SchematicParameters:
    """
    Get schematic parameters for QFN (Quad Flat No-leads).

    Similar to TQFP but smaller footprint, typically 0.4-0.5mm pitch.
    """
    pitch = 0.5
    pins_per_side = pin_count // 4
    width = 6.0 + (pins_per_side * pitch)
    height = width

    return SchematicParameters(
        package_type=PackageType.QFN,
        pin_count=pin_count,
        pin_pitch=pitch,
        body_width=width,
        body_height=height,
        pin_geometry=PinGeometry(leg_length=2.0, leg_width=0.1, pin_name_offset=3.5),
        body_geometry=BodyGeometry(top_margin=3.0),
        pins_per_side=[pins_per_side, pins_per_side, pins_per_side, pins_per_side],
        counter_clockwise=True
    )


def get_bga_parameters(pin_count: int) -> SchematicParameters:
    """
    Get schematic parameters for BGA (Ball Grid Array).

    BGA packages have solder balls in a grid on the bottom.
    This is a simplified 2D representation.
    """
    # Calculate grid size (roughly square)
    grid_size = int((pin_count) ** 0.5)

    pitch = 1.0  # Typical BGA pitch 1.0mm
    width = (grid_size - 1) * pitch + 4.0
    height = width

    return SchematicParameters(
        package_type=PackageType.BGA,
        pin_count=pin_count,
        pin_pitch=pitch,
        body_width=width,
        body_height=height,
        pin_geometry=PinGeometry(
            leg_length=1.5,
            leg_width=0.3,
            leg_thickness=0.3,
            point_size=0.3,
            pin_num_size=0.8,
            pin_name_size=1.2
        ),
        body_geometry=BodyGeometry(top_margin=3.0),
        pins_per_side=[grid_size, grid_size, grid_size, grid_size],
        counter_clockwise=True
    )


# ============================================================================
# Parameter Lookup
# ============================================================================

PACKAGE_TYPE_ALIASES = {
    # DIP aliases
    "DIP": PackageType.DIP,
    "PDIP": PackageType.DIP,
    "CDIP": PackageType.DIP,

    # SOIC aliases
    "SOIC": PackageType.SOIC,
    "SOP": PackageType.SOIC,
    "SSOP": PackageType.SOIC,
    "TSOP": PackageType.SOIC,

    # TQFP aliases
    "TQFP": PackageType.TQFP,
    "LQFP": PackageType.LQFP,
    "QFP": PackageType.TQFP,

    # QFN aliases
    "QFN": PackageType.QFN,
    "DFN": PackageType.QFN,

    # BGA aliases
    "BGA": PackageType.BGA,
    "LGA": PackageType.BGA,
}


def parse_package_type(package_str: str) -> PackageType:
    """
    Parse package type from string (e.g., "LQFP64" → PackageType.LQFP).
    """
    package_str = package_str.upper().strip()

    # Try direct match
    if package_str in PACKAGE_TYPE_ALIASES:
        return PACKAGE_TYPE_ALIASES[package_str]

    # Try prefix match (e.g., "LQFP64" → "LQFP")
    for alias, ptype in PACKAGE_TYPE_ALIASES.items():
        if package_str.startswith(alias):
            return ptype

    # Default to DIP for unknown types
    return PackageType.DIP


def get_schematic_parameters(package_type: str, pin_count: int) -> SchematicParameters:
    """
    Get schematic parameters for a package.

    Args:
        package_type: Package type string (e.g., "DIP-8", "LQFP64", "TQFP-44")
        pin_count: Number of pins

    Returns:
        SchematicParameters for the package

    Example:
        >>> params = get_schematic_parameters("DIP-8", 8)
        >>> params.pin_count
        8
        >>> params.pins_per_side
        [4, 4, 0, 0]
    """
    ptype = parse_package_type(package_type)

    if ptype == PackageType.DIP:
        return get_dip_parameters(pin_count)
    elif ptype == PackageType.SOIC:
        return get_soic_parameters(pin_count)
    elif ptype == PackageType.TQFP or ptype == PackageType.LQFP:
        return get_tqfp_parameters(pin_count)
    elif ptype == PackageType.QFN:
        return get_qfn_parameters(pin_count)
    elif ptype == PackageType.BGA:
        return get_bga_parameters(pin_count)
    else:
        # Default to DIP
        return get_dip_parameters(pin_count)


# ============================================================================
# Pin Position Calculation
# ============================================================================

def calculate_pin_position(
    pin_index: int,
    params: SchematicParameters
) -> Tuple[float, float, str]:
    """
    Calculate the (x, y) position and side for a pin.

    Args:
        pin_index: 0-based index of the pin in the sorted list
        params: SchematicParameters for the package

    Returns:
        (x, y, side) where side is "left", "right", "top", or "bottom"

    Note:
        This is a simplified calculation. The actual implementation
        will need to handle the specific pin numbering order for each
        package type (clockwise vs counter-clockwise).
    """
    # Simplified: for DIP, just alternate left/right
    if params.package_type == PackageType.DIP:
        pins_per_side = params.pin_count // 2
        if pin_index < pins_per_side:
            # Left side
            y = (params.body_height / 2) - params.body_geometry.top_margin - (pin_index * params.pin_pitch)
            return (-params.body_width / 2, y, "left")
        else:
            # Right side
            right_index = pin_index - pins_per_side
            y = -(params.body_height / 2) + params.body_geometry.top_margin + (right_index * params.pin_pitch)
            return (params.body_width / 2, y, "right")

    # For TQFP, distribute pins on all 4 sides
    elif params.package_type in [PackageType.TQFP, PackageType.LQFP, PackageType.QFN]:
        pins_per_side = params.pin_count // 4

        if pin_index < pins_per_side:
            # Left side (top to bottom)
            y = (params.body_height / 2) - params.body_geometry.top_margin - (pin_index * params.pin_pitch)
            return (-params.body_width / 2, y, "left")
        elif pin_index < pins_per_side * 2:
            # Top side (left to right)
            top_index = pin_index - pins_per_side
            x = -(params.body_width / 2) + params.body_geometry.top_margin + (top_index * params.pin_pitch)
            return (x, params.body_height / 2, "top")
        elif pin_index < pins_per_side * 3:
            # Right side (bottom to top for counter-clockwise)
            right_index = pin_index - pins_per_side * 2
            y = -(params.body_height / 2) + params.body_geometry.top_margin + (right_index * params.pin_pitch)
            return (params.body_width / 2, y, "right")
        else:
            # Bottom side (right to left)
            bottom_index = pin_index - pins_per_side * 3
            x = (params.body_width / 2) - params.body_geometry.top_margin - (bottom_index * params.pin_pitch)
            return (x, -params.body_height / 2, "bottom")

    # Default
    return (0, 0, "left")
