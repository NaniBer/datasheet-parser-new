"""
Adapter to convert PinData model to PinoutDiagramBuilder format.

This module provides functions to convert between the PinData model
(from the pin extraction pipeline) and the format expected by PinoutDiagramBuilder.
"""

from typing import List, Dict, Any, Optional
from src.models.pin_data import PinData, Pin
from src.models.component_record import ComponentRecord, refdes_prefix
from src.pdf_extractor.variant_selection import select_package_variant
from .pinout_diagram_builder import build_pinout_diagram as build_schematic


_SEMANTIC_KEYS = ("electrical_type", "role", "active_low", "nc", "nc_instruction")


def _enrich_builder_pins(
    pins_for_builder: List[Dict[str, Any]],
    record: Optional[ComponentRecord],
) -> List[Dict[str, Any]]:
    """Slice C plumbing: attach per-pin contract semantics (electrical_type,
    role, active_low, nc, nc_instruction) from the ComponentRecord onto the
    builder pin dicts, matched by pin number.

    Additive only — number/name/order are untouched, and the builder currently
    reads only number/name, so generated output is byte-identical until a later
    sub-step consumes these keys. When no record is supplied, a no-op.
    """
    if record is None:
        return pins_for_builder
    variant = record.selected()
    if variant is None:
        return pins_for_builder
    by_number = {str(p.number): p for p in variant.pins}
    for d in pins_for_builder:
        rp = by_number.get(str(d.get("number")))
        if rp is None:
            continue
        d.setdefault("electrical_type", rp.electrical_type)
        d.setdefault("role", rp.role)
        d.setdefault("active_low", rp.active_low)
        d.setdefault("nc", rp.nc)
        d.setdefault("nc_instruction", rp.nc_instruction)
    return pins_for_builder


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
    record: Optional[ComponentRecord] = None,
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

    # Slice C plumbing (inert): attach contract semantics from the record. The
    # builder ignores these keys today, so output is unchanged.
    pins_for_builder = _enrich_builder_pins(pins_for_builder, record)

    # SYM-10: reference-designator prefix from the device class (U when unknown).
    designator = "U"
    if record is not None and record.identity is not None:
        designator = refdes_prefix(record.identity.device_class)

    # Build schematic
    return build_schematic(package_type, pin_count, component_name, pins_for_builder,
                           output_path, custom_layout, designator=designator)
