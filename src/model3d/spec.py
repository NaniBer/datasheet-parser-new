"""
Body3DSpec: the normalized, generator-ready description of a package body.

build_spec() folds together everything the existing pipeline already produces
(the flat extracted-dims dict from DimensionExtractor, the package family, and
the pin count) plus JEDEC defaults (package_types.footprint_defaults), and
resolves the two dimensions the footprint path discards today (body height A,
standoff A1). The result feeds a parametric template (see templates/).

Coordinate contract (shared with the footprint builder): millimetres, +Z up,
seating plane at Z=0, origin at the component centre. For a dual-row package the
lead columns are separated along X (that is the lead-span E axis) and the pins
run along Y at pitch e (that is the body-length D axis).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from src.package_types.footprint_defaults import get_footprint_defaults, _family


# Family -> lead style. Each style maps to a template in templates/ (registry).
_LEAD_STYLE = {
    # Dual-row gull-wing
    "SOIC": "gullwing", "SOP": "gullwing", "SO": "gullwing",
    "SSOP": "gullwing", "TSSOP": "gullwing", "MSOP": "gullwing",
    "QSOP": "gullwing", "HVSSOP": "gullwing", "VSSOP": "gullwing",
    "SOT23": "gullwing",
    # Quad gull-wing (leads on all four sides)
    "QFP": "quad_gullwing", "LQFP": "quad_gullwing", "TQFP": "quad_gullwing",
    # Leadless (flush bottom terminals; QFN is quad, DFN/WSON/SON dual-row)
    "QFN": "leadless", "DFN": "leadless", "WSON": "leadless", "SON": "leadless",
    # Through-hole
    "DIP": "through_hole", "PDIP": "through_hole", "CDIP": "through_hole",
    # Chip passives (routes here once the pipeline recognises passive families)
    "R": "chip", "C": "chip", "L": "chip",
    "RES": "chip", "CAP": "chip", "IND": "chip",
    # BGA has no template yet -> fail closed rather than emit a wrong body.
    "BGA": "bga", "LGA": "bga",
}

# Families whose leads run along all four sides (quad pins_per_side split).
_QUAD_FAMILIES = {"QFP", "LQFP", "TQFP", "QFN"}

# SOIC-family (span, body-width) pairs. A 16-pin SOIC is ambiguous between the
# narrow "D" and wide "DW" body; the extracted lead span disambiguates them.
_SOIC_BODY_VARIANTS = [
    (6.0, 3.9),    # narrow
    (10.3, 7.5),   # wide (DW)
]


@dataclass
class Body3DSpec:
    """Generator-ready package-body description (all lengths in mm)."""

    component_name: str
    package_type: str
    package_family: str
    lead_style: str
    pin_count: int
    pins_per_side: List[int]        # [left, right, top, bottom]

    # Body
    body_length_D: float
    body_width_E1: float
    body_height_A: float
    standoff_A1: float

    # Leads
    lead_span_E: float
    lead_pitch_e: float
    lead_width_b: float
    lead_foot_L: float

    dims_source: str                # text | vision | text+vision | jedec_default
    confidence: str                 # verified | unverified


def _soic_e1_from_span(span_E: Optional[float], default_e1: float) -> float:
    """Resolve SOIC body width when E1 was not extracted.

    A 16-pin SOIC's pin count cannot distinguish narrow from wide body, but the
    lead span can: pick the JEDEC body-width whose tabulated span is nearest the
    extracted span. Falls back to the pin-count-derived default when no span.
    """
    if span_E is None:
        return default_e1
    nearest = min(_SOIC_BODY_VARIANTS, key=lambda pair: abs(pair[0] - span_E))
    return nearest[1]


def _pins_per_side(family: str, pin_count: int) -> List[int]:
    """Split pin_count across sides: quad [L,R,T,B] for QFP/QFN, else dual-row.

    Quad split spreads any remainder onto the first sides so the total always
    equals pin_count (e.g. 30 pins -> [8, 8, 7, 7]).
    """
    if family in _QUAD_FAMILIES:
        base, rem = divmod(pin_count, 4)
        return [base + (1 if i < rem else 0) for i in range(4)]
    half = pin_count // 2
    return [half, pin_count - half, 0, 0]


def build_spec(
    package_type: str,
    pin_count: int,
    component_name: str,
    extracted_dims: Optional[Dict] = None,
) -> Body3DSpec:
    """Build a Body3DSpec from extracted dimensions + JEDEC defaults."""
    dims = dict(extracted_dims or {})
    family = _family(package_type) or ""
    defaults = get_footprint_defaults(package_type, pin_count) or {}

    lead_style = _LEAD_STYLE.get(family, "gullwing")

    def pick(key: str) -> Optional[float]:
        val = dims.get(key)
        if val is None:
            val = defaults.get(key)
        return float(val) if val is not None else None

    lead_pitch_e = pick("e") or 0.0
    lead_span_E = pick("E") or 0.0
    body_length_D = pick("D") or 0.0
    lead_width_b = pick("b") or 0.0
    lead_foot_L = pick("L") or 0.0

    # Body width: prefer extracted/default E1; for SOIC disambiguate by span.
    body_width_E1 = pick("E1")
    if body_width_E1 is None or family in ("SOIC", "SOP", "SO"):
        default_e1 = defaults.get("E1", body_width_E1 or lead_span_E)
        if dims.get("E1") is not None:
            body_width_E1 = float(dims["E1"])
        elif family in ("SOIC", "SOP", "SO"):
            body_width_E1 = _soic_e1_from_span(dims.get("E"), float(default_e1))
        else:
            body_width_E1 = float(default_e1)

    # Height A / standoff A1: extracted (preferred) or a JEDEC-ish default.
    # These drive the Z profile the footprint path throws away today.
    height_extracted = dims.get("A") is not None and dims.get("A1") is not None
    body_height_A = float(dims["A"]) if dims.get("A") is not None else 1.75
    standoff_A1 = float(dims["A1"]) if dims.get("A1") is not None else 0.10

    dims_source = dims.get("dims_source", "jedec_default")
    verified = height_extracted and dims_source in ("text", "vision", "text+vision")
    confidence = "verified" if verified else "unverified"

    pins_per_side = _pins_per_side(family, pin_count)

    return Body3DSpec(
        component_name=component_name,
        package_type=package_type,
        package_family=family,
        lead_style=lead_style,
        pin_count=pin_count,
        pins_per_side=pins_per_side,
        body_length_D=body_length_D,
        body_width_E1=body_width_E1,
        body_height_A=body_height_A,
        standoff_A1=standoff_A1,
        lead_span_E=lead_span_E,
        lead_pitch_e=lead_pitch_e,
        lead_width_b=lead_width_b,
        lead_foot_L=lead_foot_L,
        dims_source=dims_source,
        confidence=confidence,
    )
