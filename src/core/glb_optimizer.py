"""Utilities for reducing redundant GLB hierarchy nodes."""

from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    from pygltflib import GLTF2, Node
except ImportError:
    GLTF2 = None
    Node = None


_IDENTITY_MATRIX = [
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, 0.0,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
]
_IDENTITY_TRANSLATION = [0.0, 0.0, 0.0]
_IDENTITY_ROTATION = [0.0, 0.0, 0.0, 1.0]
_IDENTITY_SCALE = [1.0, 1.0, 1.0]
_EPSILON = 1e-9


def _is_close_sequence(values: List[float], expected: List[float]) -> bool:
    """Return True when two numeric sequences are approximately equal."""
    return len(values) == len(expected) and all(
        abs(float(a) - float(b)) <= _EPSILON for a, b in zip(values, expected)
    )


def _is_identity_transform(node_data: Dict[str, Any]) -> bool:
    """Return True when a node has no effective transform."""
    matrix = node_data["matrix"]
    if matrix and not _is_close_sequence(matrix, _IDENTITY_MATRIX):
        return False

    translation = node_data["translation"]
    if translation and not _is_close_sequence(translation, _IDENTITY_TRANSLATION):
        return False

    rotation = node_data["rotation"]
    if rotation and not _is_close_sequence(rotation, _IDENTITY_ROTATION):
        return False

    scale = node_data["scale"]
    if scale and not _is_close_sequence(scale, _IDENTITY_SCALE):
        return False

    return True


def _extract_node_tree(gltf: "GLTF2", node_index: int) -> Dict[str, Any]:
    """Convert a GLTF node subtree into a plain Python structure."""
    node = gltf.nodes[node_index]
    return {
        "name": node.name,
        "mesh": node.mesh,
        "camera": getattr(node, "camera", None),
        "skin": getattr(node, "skin", None),
        "weights": getattr(node, "weights", None),
        "extras": getattr(node, "extras", None),
        "extensions": getattr(node, "extensions", None),
        "matrix": getattr(node, "matrix", None),
        "translation": getattr(node, "translation", None),
        "rotation": getattr(node, "rotation", None),
        "scale": getattr(node, "scale", None),
        "children": [
            _extract_node_tree(gltf, child_index)
            for child_index in (node.children or [])
        ],
    }


def _can_collapse_node(node_data: Dict[str, Any]) -> bool:
    """Return True when a node is only an identity wrapper around one child."""
    return (
        node_data["mesh"] is None
        and node_data["camera"] is None
        and node_data["skin"] is None
        and not node_data["weights"]
        and not node_data["extras"]
        and not node_data["extensions"]
        and len(node_data["children"]) == 1
        and _is_identity_transform(node_data)
    )


def _simplify_node_tree(node_data: Dict[str, Any]) -> Dict[str, Any]:
    """Collapse single-child identity wrapper chains while preserving parent names."""
    node_data["children"] = [
        _simplify_node_tree(child)
        for child in node_data["children"]
    ]

    while _can_collapse_node(node_data):
        child = node_data["children"][0]
        node_data = {
            "name": node_data["name"] or child["name"],
            "mesh": child["mesh"],
            "camera": child["camera"],
            "skin": child["skin"],
            "weights": child["weights"],
            "extras": child["extras"],
            "extensions": child["extensions"],
            "matrix": child["matrix"],
            "translation": child["translation"],
            "rotation": child["rotation"],
            "scale": child["scale"],
            "children": child["children"],
        }

    return node_data


def _append_node_tree(node_data: Dict[str, Any], nodes: List["Node"]) -> int:
    """Append a simplified node tree to a GLTF node list and return its new index."""
    node = Node(name=node_data["name"])
    if node_data["mesh"] is not None:
        node.mesh = node_data["mesh"]
    if node_data["camera"] is not None:
        node.camera = node_data["camera"]
    if node_data["skin"] is not None:
        node.skin = node_data["skin"]
    if node_data["weights"] is not None:
        node.weights = node_data["weights"]
    if node_data["extras"] is not None:
        node.extras = node_data["extras"]
    if node_data["extensions"] is not None:
        node.extensions = node_data["extensions"]
    if node_data["matrix"] is not None:
        node.matrix = node_data["matrix"]
    if node_data["translation"] is not None:
        node.translation = node_data["translation"]
    if node_data["rotation"] is not None:
        node.rotation = node_data["rotation"]
    if node_data["scale"] is not None:
        node.scale = node_data["scale"]

    node_index = len(nodes)
    nodes.append(node)

    child_indices = [
        _append_node_tree(child, nodes)
        for child in node_data["children"]
    ]
    if child_indices:
        node.children = child_indices

    return node_index


def simplify_glb_hierarchy(gltf: "GLTF2") -> Tuple[int, int]:
    """
    Simplify a GLTF hierarchy in-place by removing redundant wrapper chains.

    Returns:
        Tuple of (original_node_count, simplified_node_count)
    """
    if GLTF2 is None or Node is None:
        raise ImportError("pygltflib is required for GLB hierarchy optimization")

    original_count = len(gltf.nodes or [])
    if not gltf.nodes or not gltf.scenes:
        return original_count, original_count

    simplified_scene_roots = [
        [
            _simplify_node_tree(_extract_node_tree(gltf, node_index))
            for node_index in (scene.nodes or [])
        ]
        for scene in gltf.scenes
    ]

    simplified_nodes: List[Node] = []
    for scene, scene_roots in zip(gltf.scenes, simplified_scene_roots):
        scene.nodes = [
            _append_node_tree(root_node, simplified_nodes)
            for root_node in scene_roots
        ]

    gltf.nodes = simplified_nodes
    return original_count, len(simplified_nodes)


def optimize_glb_hierarchy(glb_path: str) -> Tuple[int, int]:
    """
    Simplify redundant wrapper nodes in a GLB file in-place.

    Returns:
        Tuple of (original_node_count, simplified_node_count)
    """
    if GLTF2 is None:
        raise ImportError("pygltflib is required for GLB hierarchy optimization")

    gltf = GLTF2().load_binary(str(Path(glb_path)))
    counts = simplify_glb_hierarchy(gltf)
    gltf.save(str(Path(glb_path)))
    return counts

