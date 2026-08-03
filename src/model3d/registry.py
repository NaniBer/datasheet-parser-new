"""Package-template registry: lead style -> parametric template.

Fail-closed: an unsupported lead style raises rather than emitting a wrong body,
matching the pipeline's enforce_known_package_type contract.
"""
from __future__ import annotations

from src.exceptions import SchematicGenerationError, ErrorCodes

from .spec import Body3DSpec
from .templates import GullwingTemplate, PackageTemplate

_TEMPLATES = {
    GullwingTemplate.lead_style: GullwingTemplate,
}


def select_template(spec: Body3DSpec) -> PackageTemplate:
    """Return the template for spec.lead_style, or raise if unsupported."""
    template_cls = _TEMPLATES.get(spec.lead_style)
    if template_cls is None:
        raise SchematicGenerationError(
            f"No 3D body template for lead style '{spec.lead_style}' "
            f"(package '{spec.package_type}')",
            error_code=ErrorCodes.PACKAGE_UNKNOWN,
            details={"lead_style": spec.lead_style, "package_type": spec.package_type},
        )
    return template_cls()
