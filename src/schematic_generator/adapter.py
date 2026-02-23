"""
Adapter to convert PinData model to SchematicBuilder format.

This module provides functions to convert between the PinData model
(from the pin extraction pipeline) and the format expected by SchematicBuilder.
"""

from typing import List, Dict, Any
from src.models.pin_data import PinData, Pin
from .schematic_builder import build_schematic_from_pin_data as build_schematic


def pin_data_to_builder_format(pin_data: PinData) -> tuple:
    """
    Convert PinData to format expected by SchematicBuilder.

    Args:
        pin_data: PinData object from pin extraction

    Returns:
        Tuple of (package_type, pin_count, component_name, pin_data_list)

    Example:
        >>> pin_data = PinData(
        ...     component_name="NE555",
        ...     package=PackageInfo(type="DIP-8", pin_count=8, ...),
        ...     pins=[Pin(number="1", name="GND"), ...]
        ... )
        >>> pkg_type, count, name, pins = pin_data_to_builder_format(pin_data)
        >>> pkg_type
        "DIP-8"
        >>> name
        "NE555"
        >>> len(pins)
        8
    """
    # Extract package info
    package_type = pin_data.package.type
    pin_count = pin_data.package.pin_count
    component_name = pin_data.component_name

    # Convert pins to builder format: List[Dict[str, Any]]
    pins_for_builder = [
        {"number": str(pin.number), "name": pin.name}
        for pin in pin_data.pins
    ]

    return package_type, pin_count, component_name, pins_for_builder


def build_schematic_from_pin_data(pin_data: PinData, output_path: str) -> bool:
    """
    Build and export schematic from PinData.

    This is the main interface function that connects the pin extraction
    pipeline to the schematic generation.

    Args:
        pin_data: PinData object from pin extraction
        output_path: Path to save GLB file

    Returns:
        True if successful, False otherwise
    """
    # Convert PinData to builder format
    package_type, pin_count, component_name, pins_for_builder = pin_data_to_builder_format(pin_data)

    # Build schematic
    return build_schematic(package_type, pin_count, component_name, pins_for_builder, output_path)
