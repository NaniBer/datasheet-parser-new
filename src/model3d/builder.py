"""build_body_model: public entry point for the 3D body layer.

Given the package type, pin count and the flat extracted-dims dict the pipeline
already produces, generate a package-body model and export STEP + GLB. Fails
*closed* on unsupported families (returns success=False with a reason) so the
caller can skip the body without failing the footprint/schematic that preceded
it.
"""
from __future__ import annotations

import logging
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

    paths = export_model(assembly, output_base)

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
