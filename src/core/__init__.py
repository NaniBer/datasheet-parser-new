"""Core utility modules."""

from .clean_output import format_pin_data
from .glb_optimizer import optimize_glb_hierarchy, simplify_glb_hierarchy
from .pcb_footprint_extras import inject_pcb_footprint_extras
from .pcb_footprint_hierarchy import (
    normalize_pcb_footprint_bodyline_names,
    validate_pcb_footprint_glb,
    validate_pcb_footprint_hierarchy,
)
from .reference_glb_hierarchy import (
    validate_glb_similarity_to_reference,
    validate_pcb_footprint_similarity_to_reference,
)

__all__ = [
    "format_pin_data",
    "optimize_glb_hierarchy",
    "simplify_glb_hierarchy",
    "inject_pcb_footprint_extras",
    "normalize_pcb_footprint_bodyline_names",
    "validate_pcb_footprint_glb",
    "validate_pcb_footprint_hierarchy",
    "validate_glb_similarity_to_reference",
    "validate_pcb_footprint_similarity_to_reference",
]
