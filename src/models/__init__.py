"""Data models for pin and package information."""

from .pin_data import Pin, PackageInfo, PinData
from .component_record import (
    ComponentRecord,
    PackageVariant,
    Mechanical,
    Dimension,
    Identity,
    Provenance,
    ArtifactLinks,
    Ratings,
    RecordPin,
    # Output-contract vocabularies + validation helpers
    ELECTRICAL_TYPES,
    PIN_ROLES,
    DEVICE_CLASSES,
    REFDES_PREFIX,
    ROLE_SIDE,
    LAND_PATTERN_SOURCES,
    normalize_electrical_type,
    normalize_role,
    role_side,
    refdes_prefix,
    validate_pin_semantics,
)
from .pin_classifier import classify_pin_name, detect_active_low

__all__ = [
    "Pin", "PackageInfo", "PinData",
    # Component Record v1 (canonical extraction schema)
    "ComponentRecord", "PackageVariant", "Mechanical", "Dimension",
    "Identity", "Provenance", "ArtifactLinks", "Ratings", "RecordPin",
    # Extraction output contract
    "ELECTRICAL_TYPES", "PIN_ROLES", "DEVICE_CLASSES", "REFDES_PREFIX",
    "ROLE_SIDE", "LAND_PATTERN_SOURCES",
    "normalize_electrical_type", "normalize_role", "role_side",
    "refdes_prefix", "validate_pin_semantics",
    "classify_pin_name", "detect_active_low",
]
