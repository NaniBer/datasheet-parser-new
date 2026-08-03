"""Validate a generated package body against its Body3DSpec.

Measures the in-memory cadquery B-rep in CAD coordinates (millimetres, +Z up)
and compares overall extents and lead count to the spec within tolerance. This
is the build-fidelity gate: does the geometry we produced match the dimensions
we fed the generator? Tolerances follow docs/3d-model-generation-architecture.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import cadquery as cq

from .spec import Body3DSpec

# Tolerances (mm). Tight band for our own build fidelity.
TOL_SPAN = 0.15       # lead span E
TOL_BODY_ABS = 0.10   # body length/width (or 2%, whichever larger)
TOL_BODY_PCT = 0.02
TOL_HEIGHT = 0.05     # overall height A
TOL_SEATING = 0.02    # seating plane at Z=0


@dataclass
class Body3DValidationResult:
    ok: bool
    issues: List[str] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)


def _count_leads(assembly: cq.Assembly) -> int:
    return sum(1 for c in assembly.children if c.name.startswith("Lead_"))


def validate_body(assembly: cq.Assembly, spec: Body3DSpec) -> Body3DValidationResult:
    """Check the built body against the spec; return ok + human-readable issues."""
    issues: List[str] = []
    bb = assembly.toCompound().BoundingBox()
    lead_count = _count_leads(assembly)

    metrics = {
        "span_x": bb.xlen,
        "length_y": bb.ylen,
        "height_z": bb.zlen,
        "z_min": bb.zmin,
        "z_max": bb.zmax,
        "lead_count": lead_count,
    }

    # Lead count is exact — a right-sized body with the wrong pin count is wrong.
    if lead_count != spec.pin_count:
        issues.append(
            f"lead count {lead_count} != expected {spec.pin_count}"
        )

    # Lead span (X).
    if abs(bb.xlen - spec.lead_span_E) > TOL_SPAN:
        issues.append(
            f"lead span {bb.xlen:.3f} != E {spec.lead_span_E:.3f} (tol {TOL_SPAN})"
        )

    # Body length (Y).
    tol_len = max(TOL_BODY_ABS, TOL_BODY_PCT * spec.body_length_D)
    if abs(bb.ylen - spec.body_length_D) > tol_len:
        issues.append(
            f"body length {bb.ylen:.3f} != D {spec.body_length_D:.3f} (tol {tol_len:.3f})"
        )

    # Overall height (Z) and seating plane.
    if abs(bb.zlen - spec.body_height_A) > TOL_HEIGHT:
        issues.append(
            f"height {bb.zlen:.3f} != A {spec.body_height_A:.3f} (tol {TOL_HEIGHT})"
        )
    if abs(bb.zmin) > TOL_SEATING:
        issues.append(
            f"seating plane z_min {bb.zmin:.3f} != 0 (tol {TOL_SEATING})"
        )

    return Body3DValidationResult(ok=not issues, issues=issues, metrics=metrics)
