"""Inject IDEEZA schematic metadata (glTF extras) into a schematic GLB.

The platform's reference schematic GLB carries extras on every node: pin
groups hold id/side/pinLength/pinName, the "text" child holds pinNumber,
the "pinName" child holds the name string, BodyLine holds its polyline
points, and DesignatorName/PackageValue hold their label values. The
cadquery export produces the node hierarchy but no extras, so the frontend
cannot attach wires or show labels without this post-processing step.

Side codes follow the reference convention: 0 = left, 1 = top,
2 = right, 3 = bottom.
"""

from typing import Any, Dict, List, Optional, Tuple

try:
    from pygltflib import GLTF2
except ImportError:  # pragma: no cover - pygltflib is a hard runtime dep
    GLTF2 = None


_HIDE_TRANSFORM_CONTROLS = {"translate": "xyz", "rotate": "xyz", "scale": "xyz"}
_LABEL_TEXT_SIZE = 1.27


def _mesh_bounds(
    gltf: "GLTF2", node_index: int
) -> Optional[Tuple[List[float], List[float]]]:
    """(min, max) POSITION bounds of the node's own mesh, or None."""
    node = gltf.nodes[node_index]
    if node.mesh is None:
        return None
    primitives = gltf.meshes[node.mesh].primitives
    if not primitives or primitives[0].attributes.POSITION is None:
        return None
    accessor = gltf.accessors[primitives[0].attributes.POSITION]
    if accessor.min is None or accessor.max is None:
        return None
    return list(accessor.min), list(accessor.max)


def _subtree_bounds(
    gltf: "GLTF2", node_index: int
) -> Optional[Tuple[List[float], List[float]]]:
    """Combined mesh bounds of a node and all its descendants."""
    lo: Optional[List[float]] = None
    hi: Optional[List[float]] = None

    stack = [node_index]
    while stack:
        idx = stack.pop()
        bounds = _mesh_bounds(gltf, idx)
        if bounds:
            bmin, bmax = bounds
            if lo is None:
                lo, hi = list(bmin), list(bmax)
            else:
                lo = [min(a, b) for a, b in zip(lo, bmin)]
                hi = [max(a, b) for a, b in zip(hi, bmax)]
        stack.extend(gltf.nodes[idx].children or [])

    if lo is None or hi is None:
        return None
    return lo, hi


def _named_child(gltf: "GLTF2", parent_index: int, name: str) -> Optional[int]:
    for child_index in gltf.nodes[parent_index].children or []:
        if gltf.nodes[child_index].name == name:
            return child_index
    return None


def _set_extras(gltf: "GLTF2", node_index: int, extras: Dict[str, Any]) -> None:
    node = gltf.nodes[node_index]
    merged = dict(node.extras or {})
    merged.update(extras)
    node.extras = merged


def _pin_side(pin_center: List[float], body_center: List[float]) -> int:
    """Reference side code from the pin's position relative to the body."""
    dx = pin_center[0] - body_center[0]
    dy = pin_center[1] - body_center[1]
    if abs(dx) >= abs(dy):
        return 0 if dx < 0 else 2
    return 3 if dy < 0 else 1


def _annotate_label_group(gltf: "GLTF2", group_index: int, value: str) -> None:
    """DesignatorName / PackageValue group and its Body/BoundingBox children."""
    _set_extras(
        gltf,
        group_index,
        {
            "hideTransformControls": _HIDE_TRANSFORM_CONTROLS,
            "value": value,
            "size": _LABEL_TEXT_SIZE,
            "selectParent": True,
            "dragEffect": True,
            "originalName": gltf.nodes[group_index].name,
            "renderOrder": 0,
        },
    )
    body_index = _named_child(gltf, group_index, "Body")
    if body_index is not None:
        _set_extras(
            gltf, body_index,
            {"selectParent": False, "renderOrder": 3, "originalName": "Body"},
        )
    bbox_index = _named_child(gltf, group_index, "BoundingBox")
    if bbox_index is not None:
        _set_extras(
            gltf, bbox_index,
            {"selectParent": False, "originalName": "BoundingBox", "renderOrder": 2},
        )


def _annotate_bodyline(gltf: "GLTF2", container_index: int) -> None:
    _set_extras(
        gltf,
        container_index,
        {"body": "schematic", "index": 0, "originalName": "BodyLine", "renderOrder": 0},
    )
    for child_index in gltf.nodes[container_index].children or []:
        bounds = _subtree_bounds(gltf, child_index)
        extras: Dict[str, Any] = {
            "selectParent": False,
            "originalName": gltf.nodes[child_index].name,
            "renderOrder": 0,
        }
        if bounds:
            (min_x, min_y, _), (max_x, max_y, _) = bounds
            extras["points"] = [
                {"x": min_x, "y": min_y},
                {"x": min_x, "y": max_y},
                {"x": max_x, "y": max_y},
                {"x": max_x, "y": min_y},
                {"x": min_x, "y": min_y},
            ]
        _set_extras(gltf, child_index, extras)


ACTIVE_LOW_MARKER = "/"  # SYM-08: one consistent ASCII active-low notation


def _active_low_display(pin_name: str, active_low: bool) -> str:
    """Name with a single leading active-low marker, no double-marking.

    Strips any inversion marker already in the extracted name (leading '/',
    trailing '#', '_N' suffix) before applying the one canonical prefix.
    """
    if not active_low:
        return pin_name
    base = (pin_name or "").strip().lstrip("/").rstrip("#")
    if base.upper().endswith("_N"):
        base = base[:-2]
    return f"{ACTIVE_LOW_MARKER}{base}"


def _annotate_pin_group(
    gltf: "GLTF2",
    pin_index: int,
    pin_name: str,
    body_center: List[float],
    semantics: Optional[Dict[str, Any]] = None,
) -> None:
    pin_node = gltf.nodes[pin_index]
    pin_number = pin_node.name
    semantics = semantics or {}
    # SYM-07: electrical type as a pin extra. Unknown -> the contract's explicit
    # "unspecified" member (never invented).
    electrical_type = semantics.get("electrical_type") or "unspecified"
    # SYM-11: no-connect pins are drawn but tagged, keeping the datasheet's
    # verbatim instruction ("do not connect" vs "tie to GND").
    nc = bool(semantics.get("nc"))
    nc_instruction = semantics.get("nc_instruction")
    # SYM-08: active-low as a flag + a displayName carrying ONE consistent ASCII
    # marker (leading "/"). The geometry name mesh keeps the base name unchanged;
    # the frontend renders the notation (a true overbar) from these extras.
    active_low = bool(semantics.get("active_low"))
    display_name = _active_low_display(pin_name, active_low)
    # SYM-04: functional role drives which SIDE the pin is grouped on. Carried as
    # an extra so the conformance check can verify grouping (side vs role) and the
    # frontend can cluster pins by function. Left as-is (may be None/"other" when
    # the extractor could not classify the pin); the layout gate decides whether
    # role actually moves the pin.
    role = semantics.get("role")

    side = 0
    pin_length = 0.0
    leg_index = _named_child(gltf, pin_index, "leg")
    pin_point_index = _named_child(gltf, pin_index, "pinPoint")

    anchor_index = pin_point_index if pin_point_index is not None else pin_index
    anchor_bounds = _subtree_bounds(gltf, anchor_index)
    if anchor_bounds:
        lo, hi = anchor_bounds
        center = [(a + b) / 2.0 for a, b in zip(lo, hi)]
        side = _pin_side(center, body_center)

    if leg_index is not None:
        leg_bounds = _subtree_bounds(gltf, leg_index)
        if leg_bounds:
            lo, hi = leg_bounds
            pin_length = round(max(hi[0] - lo[0], hi[1] - lo[1]), 2)

    _set_extras(
        gltf,
        pin_index,
        {
            "id": [pin_number],
            "side": side,
            "pinLength": pin_length,
            "selectParent": True,
            "hideTransformControls": _HIDE_TRANSFORM_CONTROLS,
            "value": pin_name,
            "pinName": pin_name,
            "electricalType": electrical_type,
            "role": role,
            "nc": nc,
            "ncInstruction": nc_instruction,
            "activeLow": active_low,
            "displayName": display_name,
            "dragEffect": False,
            "originalName": pin_number,
            "renderOrder": 0,
        },
    )

    for child_name, extras in (
        ("leg", {"originalName": "leg", "renderOrder": 0}),
        ("pinPoint", {"originalName": "pinPoint", "renderOrder": 0}),
        (
            "text",
            {
                "renderOrder": 0,
                "selectParent": True,
                "pinNumber": pin_number,
                "hideTransformControls": _HIDE_TRANSFORM_CONTROLS,
                "originalName": "text",
            },
        ),
        ("boundingBox", {"originalName": "boundingBox", "renderOrder": 0}),
        ("pinName", {"pinName": pin_name, "originalName": "pinName", "renderOrder": 0}),
    ):
        child_index = _named_child(gltf, pin_index, child_name)
        if child_index is not None:
            _set_extras(gltf, child_index, extras)


def inject_schematic_extras(
    glb_path: str,
    pin_names: Dict[str, str],
    component_name: str,
    designator: str = "U",
    pin_semantics: Optional[Dict[str, Dict[str, Any]]] = None,
) -> bool:
    """
    Annotate a generated schematic GLB with IDEEZA frontend extras.

    Args:
        glb_path: Path to the schematic GLB written by the builder
        pin_names: Pin number (string) -> pin name
        component_name: Label for the PackageValue node
        designator: Label for the DesignatorName node

    Returns:
        True when the Package root was found and annotated.
    """
    if GLTF2 is None:
        return False

    gltf = GLTF2().load_binary(str(glb_path))
    if not gltf.scenes or not gltf.scenes[gltf.scene or 0].nodes:
        return False

    package_index = gltf.scenes[gltf.scene or 0].nodes[0]
    if gltf.nodes[package_index].name != "Package":
        return False

    _set_extras(
        gltf,
        package_index,
        {
            "dragEffect": True,
            "viewType": "schematic",
            "originalName": "Package",
            "renderOrder": 0,
        },
    )

    body_center = [0.0, 0.0, 0.0]
    bodyline_index = _named_child(gltf, package_index, "BodyLine")
    if bodyline_index is not None:
        bounds = _subtree_bounds(gltf, bodyline_index)
        if bounds:
            body_center = [(a + b) / 2.0 for a, b in zip(*bounds)]

    for child_index in gltf.nodes[package_index].children or []:
        child = gltf.nodes[child_index]
        if child.name == "DesignatorName":
            _annotate_label_group(gltf, child_index, designator)
        elif child.name == "PackageValue":
            _annotate_label_group(gltf, child_index, component_name)
        elif child.name == "BodyLine":
            _annotate_bodyline(gltf, child_index)
        elif child.name == "Legs":
            _set_extras(
                gltf,
                child_index,
                {
                    "selectParent": True,
                    "viewType": "schematic",
                    "originalName": "Legs",
                    "renderOrder": 0,
                },
            )
            for pin_index in child.children or []:
                pin_number = gltf.nodes[pin_index].name
                pin_name = pin_names.get(pin_number, "")
                sem = (pin_semantics or {}).get(pin_number)
                _annotate_pin_group(gltf, pin_index, pin_name, body_center, semantics=sem)

    gltf.save(str(glb_path))
    return True
