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
    package: Optional[PackageInfo] = None  # Single package (legacy format)
    pins: Optional[List[Pin]] = None  # Single package pins (legacy format)
    packages: Optional[List[dict]] = None  # Multiple packages with their pins (new format)
    selected_package_index: Optional[int] = None  # Preferred package index when multiple variants exist
    selected_package_type: Optional[str] = None  # Preferred package label/type when available
    selection_reason: Optional[str] = None  # Human-readable explanation for the chosen variant
    extraction_method: str = "Table"  # Table, Diagram, Mixed
    validation_errors: Optional[List[str]] = None  # Set only when invalid data was accepted via --force-best-effort
