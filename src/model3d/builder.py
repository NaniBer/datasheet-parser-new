"""build_body_model: public entry point for the 3D body layer.

Given the package type, pin count and the flat extracted-dims dict the pipeline
already produces, generate a package-body model and export STEP + GLB. Fails
*closed* on unsupported families (returns success=False with a reason) so the
caller can skip the body without failing the footprint/schematic that preceded
it.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.exceptions import SchematicGenerationError

from .exporter import export_model
from .registry import select_template
from .spec import build_spec
from .validator import validate_alignment, validate_body

logger = logging.getLogger(__name__)


@dataclass
class Body3DResult:
    success: bool
    step_path: Optional[str] = None
    glb_path: Optional[str] = None
    validated: bool = False
    confidence: str = "unverified"
    issues: List[str] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)
    align_ok: Optional[bool] = None          # None when no pad map supplied
    worst_align_delta: Optional[float] = None
    reason: Optional[str] = None


# V-03: the 3D body aligns to the footprint in origin, leads, and height. This
# is a build-time verdict (like 3D-03) because per-lead identity and the CAD
# B-rep are gone from the tessellated GLB — it must be computed while the
# in-memory assembly + footprint pad map are still available.
V03_ORIGIN_TOL_MM = 0.10


def footprint_alignment_verdict(result: "Body3DResult") -> Optional[Tuple[bool, str]]:
    """V-03 composite verdict, or None when it cannot be assessed.

    Returns ``(ok, message)``. None when there is no body, or no footprint pad
    map was supplied (``align_ok is None``) so lead alignment is unknown — the
    rule then stays UNRUN for that part, mirroring 3D-03. PASS requires all
    three: lead feet on their pads (3D-03's check), the body XY centroid on the
    shared origin, and the built height matching spec A (no height issue).
    """
    if not result.success or result.align_ok is None:
        return None
    m = result.metrics or {}
    origin = math.hypot(float(m.get("center_x", 0.0)), float(m.get("center_y", 0.0)))
    leads_ok = result.align_ok is True
    origin_ok = origin <= V03_ORIGIN_TOL_MM
    height_ok = not any(
        ("height" in s) or ("body top" in s) or ("!= A " in s) for s in result.issues
    )
    ok = leads_ok and origin_ok and height_ok
    msg = (
        f"leads {'ok' if leads_ok else 'off'} (worst {result.worst_align_delta or 0.0:.3f} mm); "
        f"origin {origin:.3f} mm {'ok' if origin_ok else '> tol'}; "
        f"height {'ok' if height_ok else 'off'}"
    )
    return ok, msg


def build_body_model(
    package_type: str,
    pin_count: int,
    component_name: str,
    extracted_dims: Optional[Dict],
    output_base: str,
    footprint_pad_map: Optional[Dict[str, Tuple[float, float]]] = None,
) -> Body3DResult:
    """Generate a package-body STEP + GLB from pipeline data.

    Args:
        package_type: e.g. "SOIC-16".
        pin_count: number of pins.
        component_name: part name (metadata).
        extracted_dims: flat dict from DimensionExtractor.extract() (or None).
        output_base: output path without extension; writes ``<base>.step`` and
            ``<base>.glb``.
        footprint_pad_map: optional ``{pin(str): (x, y)}`` pad centres from the
            footprint. When supplied, lead-foot placement is validated against
            it (the "body matches the footprint" guarantee).
    """
    spec = build_spec(package_type, pin_count, component_name, extracted_dims)

    try:
        template = select_template(spec)
    except SchematicGenerationError as exc:
        logger.info("3D body skipped: %s", exc)
        return Body3DResult(success=False, reason=str(exc), confidence=spec.confidence)

    assembly = template.build(spec)
    validation = validate_body(assembly, spec)
    issues = list(validation.issues)

    align_ok: Optional[bool] = None
    worst_align: Optional[float] = None
    if footprint_pad_map:
        alignment = validate_alignment(assembly, footprint_pad_map)
        align_ok = alignment.ok
        worst_align = alignment.worst_delta
        issues.extend(alignment.issues)

    # F-04: record dimension provenance on the artifact. Method-level only for
    # now (confidence + component); datasheet URL/revision/page await extraction.
    provenance = {"method": spec.confidence, "component": component_name}
    paths = export_model(assembly, output_base, provenance=provenance)

    validated = (
        validation.ok
        and spec.confidence == "verified"
        and align_ok is not False
    )
    if issues:
        logger.warning(
            "3D body for %s has checks to review: %s",
            component_name, "; ".join(issues),
        )

    return Body3DResult(
        success=True,
        step_path=paths["step"],
        glb_path=paths["glb"],
        validated=validated,
        confidence=spec.confidence,
        issues=issues,
        metrics=validation.metrics,
        align_ok=align_ok,
        worst_align_delta=worst_align,
    )
