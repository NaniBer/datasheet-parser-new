"""
3D component-body model layer.

Extends the existing component -> schematic -> footprint pipeline with a
component-body (physical package) 3D model, exported as STEP (B-rep) and GLB
(web preview). Reuses the mechanical dimensions the pipeline already extracts
(DimensionExtractor) and the JEDEC defaults in package_types.footprint_defaults.

See docs/3d-model-generation-architecture.md for the full design.
"""
from .builder import Body3DResult, build_body_model
from .spec import Body3DSpec, build_spec

__all__ = ["Body3DResult", "build_body_model", "Body3DSpec", "build_spec"]
