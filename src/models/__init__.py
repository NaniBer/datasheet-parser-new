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
)

__all__ = [
    "Pin", "PackageInfo", "PinData",
    # Component Record v1 (canonical extraction schema — Phase 1: model only)
    "ComponentRecord", "PackageVariant", "Mechanical", "Dimension",
    "Identity", "Provenance", "ArtifactLinks", "Ratings", "RecordPin",
]
