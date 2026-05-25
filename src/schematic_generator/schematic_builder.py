"""Backward-compatibility layer for the legacy schematic builder module."""

from .pinout_diagram_builder import (
    PinoutDiagramBuilder as SchematicBuilder,
    build_pinout_diagram as build_schematic_from_pin_data,
)

__all__ = ["SchematicBuilder", "build_schematic_from_pin_data"]
