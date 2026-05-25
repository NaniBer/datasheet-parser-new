"""Backward-compatibility layer for the legacy PCB 2D builder module."""

from .pcb_footprint_builder import (
    PcbFootprintBuilder as Pcb2dBuilder,
    build_pcb_footprint as build_pcb_2d_schematic,
)

__all__ = ["Pcb2dBuilder", "build_pcb_2d_schematic"]
