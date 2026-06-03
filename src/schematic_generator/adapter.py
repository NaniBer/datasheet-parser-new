"""
Adapter to convert PinData model to PinoutDiagramBuilder format.

This module provides functions to convert between the PinData model
(from the pin extraction pipeline) and the format expected by PinoutDiagramBuilder.
"""

from typing import List, Dict, Any, Optional
from src.models.pin_data import PinData, Pin
from src.pdf_extractor.variant_selection import select_package_variant
from .pinout_diagram_builder import build_pinout_diagram as build_schematic


def pin_data_to_builder_format(
    pin_data: PinData,
    package_index: Optional[int] = None,
    part_number: Optional[str] = None,
) -> tuple:
    """
    Convert PinData to format expected by PinoutDiagramBuilder.

    Args:
        pin_data: PinData object from pin extraction
        package_index: Explicit package index override when multiple packages exist
        part_number: Optional target part number used to guide selection

    Returns:
        Tuple of (package_type, pin_count, component_name, pin_data_list)

    Example:
        >>> # Single package format (legacy)
        >>> pin_data = PinData(
        ...     component_name="NE555",
        ...     package=PackageInfo(type="DIP-8", pin_count=8, ...),
        ...     pins=[Pin(number="1", name="GND"), ...]
        ... )
        >>> pkg_type, count, name, pins = pin_data_to_builder_format(pin_data)

        >>> # Multiple packages format (new)
        >>> pin_data = PinData(
        ...     component_name="74HC595",
        ...     packages=[
        ...         {"type": "SOIC-16", "pin_count": 16, "pins": [...]},
        ...         {"type": "LCCC-20", "pin_count": 20, "pins": [...]}
        ...     ]
        ... )
        >>> # Use first package (SOIC-16)
        >>> pkg_type, count, name, pins = pin_data_to_builder_format(pin_data)
        >>> # Use second package (LCCC-20)
        >>> pkg_type, count, name, pins = pin_data_to_builder_format(pin_data, package_index=1)
    """
    component_name = pin_data.component_name

    # Handle new multi-package format
    if pin_data.packages:
        selection = select_package_variant(
            pin_data,
            part_number=part_number,
            package_index=package_index,
        )
        package_data = selection.package
        package_type = package_data["type"]
        pin_count = package_data["pin_count"]

        # Convert pins to builder format: List[Dict[str, Any]]
        pins_for_builder = [
            {"number": str(pin["number"]), "name": pin["name"]}
            for pin in package_data["pins"]
        ]
        return package_type, pin_count, component_name, pins_for_builder

    # Handle legacy single package format
    elif pin_data.package:
        package_type = pin_data.package.type
        pin_count = pin_data.package.pin_count

        # Convert pins to builder format: List[Dict[str, Any]]
        pins_for_builder = [
            {"number": str(pin.number), "name": pin.name}
            for pin in pin_data.pins
        ]

    else:
        raise ValueError("PinData must have either 'package' (legacy) or 'packages' (new format)")

    return package_type, pin_count, component_name, pins_for_builder


def build_schematic_from_pin_data(
    pin_data: PinData,
    output_path: str,
    custom_layout: Optional[Dict[str, List[int]]] = None,
    part_number: Optional[str] = None,
    package_index: Optional[int] = None,
) -> bool:
    """
    Build and export schematic from PinData.

    This is the main interface function that connects the pin extraction
    pipeline to the schematic generation.

    Args:
        pin_data: PinData object from pin extraction
        output_path: Path to save GLB file
        custom_layout: Optional dict mapping side names to pin numbers
                     (e.g., {"left_side": [1,2,3], "bottom_edge": [4,5,6]})

    Returns:
        True if successful, False otherwise
    """
    # Convert PinData to builder format
    package_type, pin_count, component_name, pins_for_builder = pin_data_to_builder_format(
        pin_data,
        package_index=package_index,
        part_number=part_number,
    )

    # Build schematic
    return build_schematic(package_type, pin_count, component_name, pins_for_builder, output_path, custom_layout)
