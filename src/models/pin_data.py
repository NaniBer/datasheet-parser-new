"""Data models for pin and package information."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Pin:
    """Represents a single pin on an electronic component."""

    number: int
    name: str
    function: Optional[str] = None  # legacy free-text (kept = role for back-compat)
    # Slice A — extraction output contract (see docs/extraction-output-contract.md).
    # Additive + Optional so nothing downstream is forced; generation ignores these.
    electrical_type: Optional[str] = None  # ERC type (contract) [SYM-07]
    role: Optional[str] = None             # functional role (contract) [SYM-04]
    active_low: bool = False               # [SYM-08]
    nc: bool = False                       # [SYM-11]
    nc_instruction: Optional[str] = None   # verbatim datasheet wording [SYM-11]


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
    # Ground truth read from the datasheet's own ordering table for the ordered
    # part number (see pdf_extractor.ordering_table). When set, these outrank
    # the LLM's variant choice during selection.
    ordered_pin_count: Optional[int] = None  # Pin count printed on the ordered part's row
    ordered_package_type: Optional[str] = None  # Package family printed on the ordered part's row
    extraction_method: str = "Table"  # Table, Diagram, Mixed
    validation_errors: Optional[List[str]] = None  # Reasons output is unvalidated: forced best-effort, or lossy/unverified geometry. Drives the GLB watermark + exit 3.
    footprint_unsupported_reason: Optional[str] = None  # Set when the part is a module/SiP/grid-array whose footprint we won't build; the pipeline emits schematic-only.
