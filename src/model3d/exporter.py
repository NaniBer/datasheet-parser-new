"""Export a package-body Assembly to STEP (B-rep) and GLB (web preview).

STEP is the accurate MCAD-exchange format; GLB is the tessellated mesh for the
web viewer (same OCCT kernel, no extra dependency). Note: cadquery's GLB export
rewrites CAD Z-up into glTF Y-up, so validation should measure the in-memory
B-rep (CAD coordinates), not the GLB.
"""
from __future__ import annotations

from typing import Dict

import cadquery as cq


def export_model(assembly: cq.Assembly, base_path: str) -> Dict[str, str]:
    """Write ``<base_path>.step`` and ``<base_path>.glb``.

    Args:
        assembly: the package-body assembly.
        base_path: output path without extension.

    Returns:
        {"step": <path>, "glb": <path>}.
    """
    step_path = f"{base_path}.step"
    glb_path = f"{base_path}.glb"
    assembly.export(step_path)
    assembly.export(glb_path)
    return {"step": step_path, "glb": glb_path}
