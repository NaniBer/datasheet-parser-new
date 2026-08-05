"""Validate a generated package body against its Body3DSpec.

Measures the in-memory cadquery B-rep in CAD coordinates (millimetres, +Z up)
and compares overall extents and lead count to the spec within tolerance. This
is the build-fidelity gate: does the geometry we produced match the dimensions
we fed the generator? Tolerances follow docs/3d-model-generation-architecture.md.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import cadquery as cq

from .spec import Body3DSpec

# Tolerances (mm). Tight band for our own build fidelity.
TOL_SPAN = 0.15       # lead span E
TOL_BODY_ABS = 0.10   # body length/width (or 2%, whichever larger)
TOL_BODY_PCT = 0.02
TOL_HEIGHT = 0.05     # overall height A
TOL_SEATING = 0.02    # seating plane at Z=0
TOL_ALIGN = 0.35      # lead-foot centre vs pad centre (IPC-7351 placement tol)


@dataclass
class Body3DValidationResult:
    ok: bool
    issues: List[str] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)


@dataclass
class AlignmentResult:
    ok: bool
    worst_delta: float = 0.0            # worst lead-foot -> pad centre distance (mm)
    issues: List[str] = field(default_factory=list)
    per_pin: Dict[str, float] = field(default_factory=dict)


def _count_leads(assembly: cq.Assembly) -> int:
    return sum(1 for c in assembly.children if c.name.startswith("Lead_"))


def _child_bbox(assembly: cq.Assembly, name: str):
    """BoundingBox of a named assembly child (CAD coords), or None if absent."""
    for child in assembly.children:
        if child.name == name:
            obj = child.obj
            shape = obj.val() if isinstance(obj, cq.Workplane) else obj
            return shape.BoundingBox()
    return None


def _lead_foot_span_x(assembly: cq.Assembly) -> float:
    """X span between the outermost lead-foot centres (row spacing E)."""
    xs = [
        _lead_foot_center(c.obj)[0]
        for c in assembly.children
        if c.name.startswith("Lead_")
    ]
    return (max(xs) - min(xs)) if xs else 0.0


def _lead_foot_center(obj) -> Tuple[float, float]:
    """(x, y) of a lead's seating-plane foot, from its lowest (-Z) face."""
    wp = obj if isinstance(obj, cq.Workplane) else cq.Workplane(obj)
    center = wp.faces("<Z").val().Center()
    return center.x, center.y


def validate_alignment(
    assembly: cq.Assembly,
    pad_map: Dict[str, Tuple[float, float]],
    tol: float = TOL_ALIGN,
) -> AlignmentResult:
    """Check that each lead's foot lands on its footprint pad.

    Args:
        assembly: the built body (leads named ``Lead_<pin>``).
        pad_map: ``{pin_number(str): (x, y)}`` pad centres from the footprint
            (e.g. PcbFootprintBuilder.pin_positions). Shared coordinate frame:
            mm, origin at component centre.
        tol: max lead-foot -> pad-centre distance before a pin is flagged.
    """
    issues: List[str] = []
    per_pin: Dict[str, float] = {}
    worst = 0.0

    for child in assembly.children:
        if not child.name.startswith("Lead_"):
            continue
        pin = child.name.split("_", 1)[1]
        if pin not in pad_map:
            issues.append(f"lead {pin} has no matching footprint pad")
            continue
        fx, fy = _lead_foot_center(child.obj)
        px, py = pad_map[pin]
        delta = math.hypot(fx - px, fy - py)
        per_pin[pin] = delta
        worst = max(worst, delta)
        if delta > tol:
            issues.append(
                f"pin {pin} lead foot ({fx:.3f},{fy:.3f}) off pad "
                f"({px:.3f},{py:.3f}) by {delta:.3f}mm (tol {tol})"
            )

    return AlignmentResult(
        ok=not issues, worst_delta=worst, issues=issues, per_pin=per_pin
    )


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

    through_hole = spec.lead_style == "through_hole"

    # Lead span (X). Through-hole leads are blades centred on the hole, so the
    # bbox overshoots by the lead thickness; measure the foot-centre span instead.
    span_x = _lead_foot_span_x(assembly) if through_hole else bb.xlen
    if abs(span_x - spec.lead_span_E) > TOL_SPAN:
        issues.append(
            f"lead span {span_x:.3f} != E {spec.lead_span_E:.3f} (tol {TOL_SPAN})"
        )

    # Body length (Y).
    tol_len = max(TOL_BODY_ABS, TOL_BODY_PCT * spec.body_length_D)
    if abs(bb.ylen - spec.body_length_D) > tol_len:
        issues.append(
            f"body length {bb.ylen:.3f} != D {spec.body_length_D:.3f} (tol {tol_len:.3f})"
        )

    if through_hole:
        # Through-hole: leads intentionally protrude below Z=0, so the overall
        # bbox is not the body envelope. Validate the moulded body instead: its
        # top at A and its underside sitting on the standoff A1 (> 0).
        body_bb = _child_bbox(assembly, "Body")
        if body_bb is None:
            issues.append("no Body node to validate")
        else:
            if abs(body_bb.zmax - spec.body_height_A) > TOL_HEIGHT:
                issues.append(
                    f"body top {body_bb.zmax:.3f} != A {spec.body_height_A:.3f} "
                    f"(tol {TOL_HEIGHT})"
                )
            if abs(body_bb.zmin - spec.standoff_A1) > TOL_SEATING:
                issues.append(
                    f"body standoff z_min {body_bb.zmin:.3f} != A1 "
                    f"{spec.standoff_A1:.3f} (tol {TOL_SEATING})"
                )
    else:
        # Surface-mount: whole body sits on the seating plane, Z = 0 .. A.
        if abs(bb.zlen - spec.body_height_A) > TOL_HEIGHT:
            issues.append(
                f"height {bb.zlen:.3f} != A {spec.body_height_A:.3f} (tol {TOL_HEIGHT})"
            )
        if abs(bb.zmin) > TOL_SEATING:
            issues.append(
                f"seating plane z_min {bb.zmin:.3f} != 0 (tol {TOL_SEATING})"
            )

    return Body3DValidationResult(ok=not issues, issues=issues, metrics=metrics)
