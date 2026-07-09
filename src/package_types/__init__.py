"""
Package Type Definitions and Geometry Parameters.

This module contains definitions for different IC package types
and their geometry parameters for schematic generation.
"""

from .package_geometry import (
    PackageType,
    PinGeometry,
    BodyGeometry,
    SchematicParameters,
    get_schematic_parameters,
    parse_package_type,
    calculate_pin_position,
    # Parameter functions
    get_dip_parameters,
    get_soic_parameters,
    get_tssop_parameters,
    get_dfn_parameters,
    get_wson_parameters,
    get_son_parameters,
    get_tqfp_parameters,
    get_qfn_parameters,
    get_bga_parameters,
    get_lccc_parameters,
    get_cdip_parameters,
)
from .footprint_defaults import get_footprint_defaults

__all__ = [
    "PackageType",
    "PinGeometry",
    "BodyGeometry",
    "SchematicParameters",
    "get_schematic_parameters",
    "get_footprint_defaults",
    "parse_package_type",
    "calculate_pin_position",
    # Parameter functions
    "get_dip_parameters",
    "get_soic_parameters",
    "get_tssop_parameters",
    "get_dfn_parameters",
    "get_wson_parameters",
    "get_son_parameters",
    "get_tqfp_parameters",
    "get_qfn_parameters",
    "get_bga_parameters",
    "get_lccc_parameters",
    "get_cdip_parameters",
]
