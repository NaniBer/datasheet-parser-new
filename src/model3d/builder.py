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
from typing import Dict, List, Optional

from src.exceptions import SchematicGenerationError

from .exporter import export_model
from .registry import select_template
from .spec import build_spec
from .validator import validate_body

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
    reason: Optional[str] = None


def build_body_model(
    package_type: str,
    pin_count: int,
    component_name: str,
    extracted_dims: Optional[Dict],
    output_base: str,
) -> Body3DResult:
    """Generate a package-body STEP + GLB from pipeline data.

    Args:
        package_type: e.g. "SOIC-16".
        pin_count: number of pins.
        component_name: part name (metadata).
        extracted_dims: flat dict from DimensionExtractor.extract() (or None).
        output_base: output path without extension; writes ``<base>.step`` and
            ``<base>.glb``.
    """
    spec = build_spec(package_type, pin_count, component_name, extracted_dims)

    try:
        template = select_template(spec)
    except SchematicGenerationError as exc:
        logger.info("3D body skipped: %s", exc)
        return Body3DResult(success=False, reason=str(exc), confidence=spec.confidence)

    assembly = template.build(spec)
    validation = validate_body(assembly, spec)
    paths = export_model(assembly, output_base)

    validated = validation.ok and spec.confidence == "verified"
    if not validation.ok:
        logger.warning(
            "3D body for %s failed geometry checks: %s",
            component_name, "; ".join(validation.issues),
        )

    return Body3DResult(
        success=True,
        step_path=paths["step"],
        glb_path=paths["glb"],
        validated=validated,
        confidence=spec.confidence,
        issues=validation.issues,
        metrics=validation.metrics,
    )
