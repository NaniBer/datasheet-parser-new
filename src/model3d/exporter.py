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
    assembly: cq.Assembly, base_path: str, ref_des: str = "U1",
    provenance: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Write ``<base_path>.step`` and ``<base_path>.glb``.

    Args:
        assembly: the package-body assembly.
        base_path: output path without extension.
        ref_des: reference-designator node name inserted between ``Body`` and the
            solids (placeholder default until the real source is wired in).
        provenance: F-04 dimension provenance stamped on the Package root
            (e.g. ``{"method": <confidence>, "component": <name>}``).

    Returns:
        {"step": <path>, "glb": <path>}.
    """
    step_path = f"{base_path}.step"
    glb_path = f"{base_path}.glb"
    assembly.export(step_path)
    try:
        # Preferred path: build the GLB from scratch with one glTF node per
        # B-rep face (matches the reference model's per-face COMPOUND convention).
        _build_faceted_glb(assembly, glb_path, ref_des, provenance)
    except Exception as exc:  # fail-open: fall back to the per-solid rewrite
        logger.warning(
            "Faceted GLB build failed for %s (%s); falling back to per-solid rewrite",
            glb_path, exc,
        )
        assembly.export(glb_path)
        try:
            _rewrite_glb_hierarchy(glb_path, ref_des, provenance)
        except Exception as exc2:  # keep the raw GLB rather than none
            logger.warning("GLB hierarchy rewrite skipped for %s: %s", glb_path, exc2)
    return {"step": step_path, "glb": glb_path}


def _package_extras(provenance: Optional[Dict[str, str]]) -> dict:
    """Package-root extras, with F-04 provenance when supplied."""
    extras = {"originalName": "Package", "renderOrder": 0}
    if provenance:
        extras["provenance"] = provenance
    return extras


# --- Faceted GLB build (one node per B-rep face) ---------------------------

# Z-up (CAD) -> Y-up (glTF) rotation quaternion (-90 deg about X), placed on the
# Package root so vertices stay in CAD coordinates.
_ZUP_TO_YUP = [-0.7071067811865476, 0.0, 0.0, 0.7071067811865476]

_TESS_TOL = 0.02  # mm; face tessellation tolerance

# Two-material palette (matches gullwing template colors).
_BODY_RGB = (0.15, 0.15, 0.17)
_LEAD_RGB = (0.75, 0.75, 0.78)


def _build_faceted_glb(assembly: cq.Assembly, glb_path: str, ref_des: str,
                       provenance: Optional[Dict[str, str]] = None) -> None:
    """Build a binary GLB with one glTF node per B-rep face.

    Node tree: ``Package -> Body -> <ref_des> -> [COMPOUND, COMPOUND_1, ...]``
    with one COMPOUND per tessellated face (all Body faces first, then each
    Lead's faces in order). Vertices stay in CAD Z-up coordinates; the Z-up->Y-up
    rotation is carried on the Package root. Two materials: 0 = body, 1 = lead.
    """
    import numpy as np
    from pygltflib import (
        FLOAT,
        UNSIGNED_INT,
        ARRAY_BUFFER,
        ELEMENT_ARRAY_BUFFER,
        GLTF2,
        Accessor,
        Attributes,
        Buffer,
        BufferView,
        Material,
        Mesh,
        Node,
        PbrMetallicRoughness,
        Primitive,
        Scene,
    )

    blob = bytearray()
    buffer_views: List[BufferView] = []
    accessors: List[Accessor] = []
    meshes: List[Mesh] = []

    def _add_face(verts, tris, material_index: int) -> Optional[int]:
        """Append geometry for one face; return the new mesh index (or None)."""
        if not verts or not tris:
            return None
        positions = np.array(
            [[v.x, v.y, v.z] for v in verts], dtype=np.float32
        )
        indices = np.array(tris, dtype=np.uint32).reshape(-1)
        if positions.size == 0 or indices.size == 0:
            return None

        # Per-vertex normals: average adjacent triangle normals.
        normals = np.zeros_like(positions)
        faces = indices.reshape(-1, 3)
        p0 = positions[faces[:, 0]]
        p1 = positions[faces[:, 1]]
        p2 = positions[faces[:, 2]]
        tri_n = np.cross(p1 - p0, p2 - p0)
        for k in range(3):
            np.add.at(normals, faces[:, k], tri_n)
        lengths = np.linalg.norm(normals, axis=1)
        lengths[lengths == 0] = 1.0
        normals = (normals / lengths[:, None]).astype(np.float32)

        pos_bytes = positions.tobytes()
        nrm_bytes = normals.tobytes()
        idx_bytes = indices.tobytes()

        pos_off = len(blob)
        blob.extend(pos_bytes)
        nrm_off = len(blob)
        blob.extend(nrm_bytes)
        idx_off = len(blob)
        blob.extend(idx_bytes)

        pos_view = len(buffer_views)
        buffer_views.append(BufferView(
            buffer=0, byteOffset=pos_off, byteLength=len(pos_bytes),
            target=ARRAY_BUFFER,
        ))
        nrm_view = len(buffer_views)
        buffer_views.append(BufferView(
            buffer=0, byteOffset=nrm_off, byteLength=len(nrm_bytes),
            target=ARRAY_BUFFER,
        ))
        idx_view = len(buffer_views)
        buffer_views.append(BufferView(
            buffer=0, byteOffset=idx_off, byteLength=len(idx_bytes),
            target=ELEMENT_ARRAY_BUFFER,
        ))

        n_verts = int(positions.shape[0])
        pos_acc = len(accessors)
        accessors.append(Accessor(
            bufferView=pos_view, componentType=FLOAT, count=n_verts, type="VEC3",
            min=positions.min(axis=0).tolist(), max=positions.max(axis=0).tolist(),
        ))
        nrm_acc = len(accessors)
        accessors.append(Accessor(
            bufferView=nrm_view, componentType=FLOAT, count=n_verts, type="VEC3",
        ))
        idx_acc = len(accessors)
        accessors.append(Accessor(
            bufferView=idx_view, componentType=UNSIGNED_INT,
            count=int(indices.shape[0]), type="SCALAR",
        ))

        mesh_index = len(meshes)
        meshes.append(Mesh(primitives=[Primitive(
            attributes=Attributes(POSITION=pos_acc, NORMAL=nrm_acc),
            indices=idx_acc, material=material_index,
        )]))
        return mesh_index

    # Walk children in order, emitting one COMPOUND node per face.
    compound_nodes: List[Node] = []

    def _emit(name: str) -> None:
        node = Node(
            name=name, mesh=mesh_index,
            extras={"originalName": name, "renderOrder": 0},
        )
        compound_nodes.append(node)

    face_counter = 0
    for child in assembly.children:
        obj = child.obj
        shape = obj.val() if isinstance(obj, cq.Workplane) else obj
        shape = shape.located(child.loc)
        material_index = 0 if child.name == "Body" else 1
        for solid in shape.Solids():
            for face in solid.Faces():
                verts, tris = face.tessellate(_TESS_TOL)
                mesh_index = _add_face(verts, tris, material_index)
                if mesh_index is None:
                    continue
                name = "COMPOUND" if face_counter == 0 else "COMPOUND_%d" % face_counter
                _emit(name)
                face_counter += 1

    if not compound_nodes:
        raise ValueError("no tessellated faces produced")

    # Assemble the node tree (COMPOUNDs first, then wrappers).
    nodes: List[Node] = list(compound_nodes)
    compound_indices = list(range(len(compound_nodes)))

    refdes = Node(
        name=ref_des, children=compound_indices,
        extras={"name": ref_des, "originalName": ref_des, "renderOrder": 0},
    )
    nodes.append(refdes)
    refdes_index = len(nodes) - 1

    body = Node(
        name="Body", children=[refdes_index],
        extras={"originalName": "Body", "renderOrder": 0},
    )
    nodes.append(body)
    body_index = len(nodes) - 1

    package = Node(
        name="Package", children=[body_index], rotation=list(_ZUP_TO_YUP),
        extras=_package_extras(provenance),
    )
    nodes.append(package)
    package_index = len(nodes) - 1

    def _material(rgb) -> Material:
        return Material(
            pbrMetallicRoughness=PbrMetallicRoughness(
                baseColorFactor=[rgb[0], rgb[1], rgb[2], 1.0],
                metallicFactor=1.0, roughnessFactor=1.0,
            ),
        )

    gltf = GLTF2(
        scene=0,
        scenes=[Scene(nodes=[package_index])],
        nodes=nodes,
        meshes=meshes,
        materials=[_material(_BODY_RGB), _material(_LEAD_RGB)],
        accessors=accessors,
        bufferViews=buffer_views,
        buffers=[Buffer(byteLength=len(blob))],
    )
    gltf.set_binary_blob(bytes(blob))
    gltf.save(glb_path)


# --- GLB re-hierarchy ------------------------------------------------------

def _rewrite_glb_hierarchy(glb_path: str, ref_des: str,
                           provenance: Optional[Dict[str, str]] = None) -> None:
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
        extras=_package_extras(provenance),
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
