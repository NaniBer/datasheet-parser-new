"""Export a package-body Assembly to STEP (B-rep) and GLB (web preview).

STEP is the accurate MCAD-exchange format; GLB is the tessellated mesh for the
web viewer (same OCCT kernel, no extra dependency). Note: cadquery's GLB export
rewrites CAD Z-up into glTF Y-up, so validation should measure the in-memory
B-rep (CAD coordinates), not the GLB.

cadquery emits its own node tree (a uuid root with ``<name>``/``<name>_part``
children). The rest of the pipeline's GLBs (2d footprint, schematic) follow a
shared ``Package -> Body -> <RefDes> -> COMPOUND*`` convention, so after export
we rewrite the body GLB's node graph to match it (geometry untouched).
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import cadquery as cq

logger = logging.getLogger(__name__)


def export_model(
    assembly: cq.Assembly, base_path: str, ref_des: str = "U1"
) -> Dict[str, str]:
    """Write ``<base_path>.step`` and ``<base_path>.glb``.

    Args:
        assembly: the package-body assembly.
        base_path: output path without extension.
        ref_des: reference-designator node name inserted between ``Body`` and the
            solids (placeholder default until the real source is wired in).

    Returns:
        {"step": <path>, "glb": <path>}.
    """
    step_path = f"{base_path}.step"
    glb_path = f"{base_path}.glb"
    assembly.export(step_path)
    assembly.export(glb_path)
    try:
        _rewrite_glb_hierarchy(glb_path, ref_des)
    except Exception as exc:  # fail-open: keep the raw GLB rather than none
        logger.warning("GLB hierarchy rewrite skipped for %s: %s", glb_path, exc)
    return {"step": step_path, "glb": glb_path}


# --- GLB re-hierarchy ------------------------------------------------------

def _rewrite_glb_hierarchy(glb_path: str, ref_des: str) -> None:
    """Rewrite the cadquery node tree into ``Package -> Body -> <RefDes> ->
    COMPOUND*`` (matching the 2d/schematic/3d reference convention).

    Geometry (meshes, accessors, buffers) is reused verbatim; only the node
    graph is rebuilt. The cadquery root carries the Z-up->Y-up rotation, which we
    move onto the new ``Package`` root so the model renders identically. Any
    transform on intermediate nodes is baked into the corresponding solid.
    """
    import numpy as np
    from pygltflib import GLTF2, Node, Scene

    gltf = GLTF2().load(glb_path)
    if not gltf.scenes:
        return
    scene_index = gltf.scene if gltf.scene is not None else 0
    roots = gltf.scenes[scene_index].nodes or []
    if not roots:
        return
    root_index = roots[0]
    root = gltf.nodes[root_index]

    # Collect mesh-bearing leaves in DFS order, composing every transform BELOW
    # the root (the root's own transform is preserved on Package, so we start the
    # composition at identity for its children).
    leaves: List[Tuple[int, Optional["np.ndarray"], str]] = []

    def collect(node_index: int, parent: Optional["np.ndarray"]) -> None:
        node = gltf.nodes[node_index]
        matrix = _compose(parent, _local_matrix(node, np))
        if node.mesh is not None:
            leaves.append((node.mesh, matrix, node.name or ""))
        for child_index in (node.children or []):
            collect(child_index, matrix)

    for child_index in (root.children or []):
        collect(child_index, None)
    if root.mesh is not None:  # root itself carrying a mesh (unexpected, but safe)
        leaves.append((root.mesh, None, root.name or ""))

    if not leaves:
        return

    new_nodes: List[Node] = []
    compound_children: List[int] = []
    for i, (mesh_index, matrix, _orig) in enumerate(leaves):
        name = "COMPOUND" if i == 0 else "COMPOUND_%d" % i
        node = Node(
            name=name,
            mesh=mesh_index,
            extras={"originalName": name, "renderOrder": 0},
        )
        if matrix is not None:
            node.matrix = _to_gltf_matrix(matrix)
        new_nodes.append(node)
        compound_children.append(len(new_nodes) - 1)

    refdes = Node(
        name=ref_des,
        children=compound_children,
        extras={"name": ref_des, "originalName": ref_des, "renderOrder": 0},
    )
    new_nodes.append(refdes)
    refdes_index = len(new_nodes) - 1

    body = Node(
        name="Body",
        children=[refdes_index],
        extras={"originalName": "Body", "renderOrder": 0},
    )
    new_nodes.append(body)
    body_index = len(new_nodes) - 1

    package = Node(
        name="Package",
        children=[body_index],
        extras={"originalName": "Package", "renderOrder": 0},
    )
    # Preserve the cadquery root's placement (the Y-up rotation) on Package.
    package.matrix = root.matrix
    package.translation = root.translation
    package.rotation = root.rotation
    package.scale = root.scale
    new_nodes.append(package)
    package_index = len(new_nodes) - 1

    gltf.nodes = new_nodes
    gltf.scenes = [Scene(nodes=[package_index])]
    gltf.scene = 0
    gltf.save(glb_path)


def _local_matrix(node, np):
    """Return the node's local transform as a 4x4 row-major numpy array, or
    None when it is identity (no matrix and no TRS)."""
    if node.matrix:
        return np.array(node.matrix, dtype=float).reshape(4, 4).T
    if not (node.translation or node.rotation or node.scale):
        return None
    matrix = np.eye(4)
    if node.rotation:
        x, y, z, w = node.rotation
        matrix[:3, :3] = [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    if node.scale:
        matrix[:3, :3] = matrix[:3, :3] @ np.diag(node.scale)
    if node.translation:
        matrix[:3, 3] = node.translation
    return matrix


def _compose(parent, local):
    """Matrix product of two optional 4x4 transforms."""
    if parent is None:
        return local
    if local is None:
        return parent
    return parent @ local


def _to_gltf_matrix(matrix) -> List[float]:
    """Row-major numpy 4x4 -> glTF column-major flat list of 16 floats."""
    return [float(v) for v in matrix.T.flatten()]
