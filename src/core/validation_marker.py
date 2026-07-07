"""Mark GLB output that was generated from unvalidated pin data (ARCH-005).

When the user forces best-effort output (--force-best-effort) after extraction
validation failed, the GLB is watermarked so downstream viewers and tooling can
distinguish trusted output from unvalidated output.
"""

from typing import List

try:
    from pygltflib import GLTF2
except ImportError:  # pragma: no cover - optional dependency guard
    GLTF2 = None


def mark_glb_unvalidated(glb_path: str, errors: List[str]) -> None:
    """Write ``validated: false`` and the validation errors into scene extras.

    Args:
        glb_path: Path to an existing GLB file to mark in place.
        errors: Validation error messages explaining why the data is untrusted.
    """
    if GLTF2 is None:
        raise ImportError("pygltflib is required to mark GLB output: pip install pygltflib")

    gltf = GLTF2().load_binary(glb_path)
    scene_index = gltf.scene if gltf.scene is not None else 0
    scene = gltf.scenes[scene_index]
    extras = dict(scene.extras or {})
    extras["validated"] = False
    extras["validationErrors"] = list(errors)
    scene.extras = extras
    gltf.save_binary(glb_path)
