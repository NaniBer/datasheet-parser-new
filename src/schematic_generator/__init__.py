"""Schematic generator module for creating IC schematics and PCB footprints."""
from ..package_types import (
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

from .pinout_diagram_builder import (
    PinoutDiagramBuilder,
    build_pinout_diagram,
)

from .adapter import (
    pin_data_to_builder_format,
    build_schematic_from_pin_data,
)

from .pcb_footprint_builder import (
    PcbFootprintBuilder,
    build_pcb_footprint,
)

# Alias for backward compatibility
build_pcb_2d_schematic = build_pcb_footprint
build_schematic = build_schematic_from_pin_data

__all__ = [
    "PackageType",
    "PinGeometry",
    "BodyGeometry",
    "SchematicParameters",
    "get_dip_parameters",
    "get_soic_parameters",
    "get_tqfp_parameters",
    "get_qfn_parameters",
    "get_bga_parameters",
    "parse_package_type",
    "get_schematic_parameters",
    "calculate_pin_position",
    "PinPosition",
    "PinLayout",
    "layout_pins",
    "PinoutDiagramBuilder",
    "build_pinout_diagram",
    "pin_data_to_builder_format",
    "build_schematic_from_pin_data",
    "build_schematic",
    "PcbFootprintBuilder",
    "build_pcb_footprint",
    "build_pcb_2d_schematic",
]
