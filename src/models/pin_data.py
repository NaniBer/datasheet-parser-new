"""Data models for pin and package information."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Pin:
    """Represents a single pin on an electronic component."""

    number: int
    name: str
    function: Optional[str] = None  # power, ground, input, output, etc.


@dataclass
class PackageInfo:
    """Represents the physical package information of a component."""

    type: str  # DIP, QFN, SOIC, TSSOP, etc.
    pin_count: int
    width: float  # mm
    height: float  # mm
    pitch: Optional[float] = None  # Pin spacing in mm
    thickness: Optional[float] = None  # Component thickness in mm


@dataclass
class PinData:
    """Complete pin data extracted from a datasheet."""

    component_name: str
    package: PackageInfo
    pins: List[Pin]
    extraction_method: str  # Table, Diagram, Mixed
