"""Schematic generator module for creating IC schematic symbols."""

from .package_geometry import (
    PackageType,
    PinGeometry,
    BodyGeometry,
    SchematicParameters,
    get_dip_parameters,
    get_soic_parameters,
    get_tqfp_parameters,
    get_qfn_parameters,
    get_bga_parameters,
    parse_package_type,
    get_schematic_parameters,
    calculate_pin_position,
)
from .pin_layout import (
    PinPosition,
    PinLayout,
    layout_pins,
)
from .schematic_builder import (
    SchematicBuilder,
    build_schematic_from_pin_data as builder_build_schematic,
)
from .adapter import (
    pin_data_to_builder_format,
    build_schematic_from_pin_data,
)

__all__ = [
    "PackageType",
    "PinGeometry",
    "BodyGeometry",
    "SchematicParameters",
    "PinPosition",
    "PinLayout",
    "SchematicBuilder",
    "get_dip_parameters",
    "get_soic_parameters",
    "get_tqfp_parameters",
    "get_qfn_parameters",
    "get_bga_parameters",
    "parse_package_type",
    "get_schematic_parameters",
    "calculate_pin_position",
    "layout_pins",
    "builder_build_schematic",
    "pin_data_to_builder_format",
    "build_schematic_from_pin_data",
]
