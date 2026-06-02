"""Validation helpers for PCB footprint GLB hierarchy."""

from pathlib import Path
from typing import List, Optional, Tuple

try:
    from pygltflib import GLTF2
except ImportError:
    GLTF2 = None


def _child_names(gltf: "GLTF2", node_index: int) -> List[str]:
    """Return the names of a node's direct children."""
    node = gltf.nodes[node_index]
    return [
        gltf.nodes[child_index].name
        for child_index in (node.children or [])
    ]


def _find_named_child(
    gltf: "GLTF2", node_index: int, child_name: str
) -> Optional[int]:
    """Find a direct child by name."""
    node = gltf.nodes[node_index]
    for child_index in (node.children or []):
        if gltf.nodes[child_index].name == child_name:
            return child_index
    return None


def _expect_child_order(
    gltf: "GLTF2",
    node_index: int,
    expected_names: List[str],
    errors: List[str],
) -> None:
    """Append an error when a node's children do not match the expected order."""
    actual_names = _child_names(gltf, node_index)
    node_name = gltf.nodes[node_index].name
    if actual_names != expected_names:
        errors.append(
            "%s children mismatch: expected %s, got %s"
            % (node_name, expected_names, actual_names)
        )


def normalize_pcb_footprint_bodyline_names(glb_path: str) -> int:
    """
    Rename PCB footprint body outline nodes to match the reference 2d.glb.

    CadQuery requires unique names during construction, so the exporter emits
    temporary names like BodyLine_Top and then normalizes them here to the
    repeated BodyLine naming used by the reference GLB.

    Returns:
        Number of body-line nodes renamed.
    """
    if GLTF2 is None:
        raise ImportError("pygltflib is required for PCB footprint normalization")

    gltf = GLTF2().load_binary(str(Path(glb_path)))
    if not gltf.scenes or not gltf.scenes[0].nodes:
        return 0

    package_index = gltf.scenes[0].nodes[0]
    body_index = _find_named_child(gltf, package_index, "Body")
    if body_index is None:
        gltf.save(str(Path(glb_path)))
        return 0

    renamed = 0
    for layer_name in ["fab_layer", "silk_layer", "crtyd_layer"]:
        layer_index = _find_named_child(gltf, body_index, layer_name)
        if layer_index is None:
            continue

        for child_index in (gltf.nodes[layer_index].children or []):
            child_node = gltf.nodes[child_index]
            if child_node.name != "BodyLine":
                child_node.name = "BodyLine"
                renamed += 1

    gltf.save(str(Path(glb_path)))
    return renamed


def validate_pcb_footprint_hierarchy(
    gltf: "GLTF2",
    pin_count: Optional[int] = None,
    through_hole: bool = True,
) -> List[str]:
    """
    Validate that a GLB follows docs/PCB_FOOTPRINT_HIERARCHY.md.

    Returns:
        A list of validation errors. Empty means valid.
    """
    errors: List[str] = []

    if not gltf.scenes or not gltf.scenes[0].nodes:
        return ["GLB has no scene root"]

    package_index = gltf.scenes[0].nodes[0]
    package_node = gltf.nodes[package_index]
    if package_node.name != "Package":
        errors.append("Scene root must be 'Package', got %r" % package_node.name)
        return errors

    _expect_child_order(
        gltf,
        package_index,
        ["DesignatorName", "PackageValue", "FirstPinMarker", "Legs", "Body"],
        errors,
    )

    designator_index = _find_named_child(gltf, package_index, "DesignatorName")
    package_value_index = _find_named_child(gltf, package_index, "PackageValue")
    marker_index = _find_named_child(gltf, package_index, "FirstPinMarker")
    legs_index = _find_named_child(gltf, package_index, "Legs")
    body_index = _find_named_child(gltf, package_index, "Body")

    if designator_index is not None:
        _expect_child_order(gltf, designator_index, ["Body", "BoundingBox"], errors)
    else:
        errors.append("Package is missing DesignatorName")

    if package_value_index is not None:
        _expect_child_order(gltf, package_value_index, ["Body", "BoundingBox"], errors)
    else:
        errors.append("Package is missing PackageValue")

    if marker_index is not None:
        _expect_child_order(
            gltf,
            marker_index,
            ["silk_firstPinMarker", "fab_firstPinMarker"],
            errors,
        )
    else:
        errors.append("Package is missing FirstPinMarker")

    if body_index is not None:
        _expect_child_order(
            gltf,
            body_index,
            ["fab_layer", "silk_layer", "crtyd_layer"],
            errors,
        )

        fab_index = _find_named_child(gltf, body_index, "fab_layer")
        silk_index = _find_named_child(gltf, body_index, "silk_layer")
        crtyd_index = _find_named_child(gltf, body_index, "crtyd_layer")

        if fab_index is not None:
            _expect_child_order(
                gltf,
                fab_index,
                ["BodyLine", "BodyLine", "BodyLine", "BodyLine"],
                errors,
            )
        else:
            errors.append("Body is missing fab_layer")

        if silk_index is not None:
            _expect_child_order(
                gltf,
                silk_index,
                ["BodyLine", "BodyLine"],
                errors,
            )
        else:
            errors.append("Body is missing silk_layer")

        if crtyd_index is not None:
            _expect_child_order(
                gltf,
                crtyd_index,
                ["BodyLine", "BodyLine", "BodyLine", "BodyLine"],
                errors,
            )
        else:
            errors.append("Body is missing crtyd_layer")
    else:
        errors.append("Package is missing Body")

    if legs_index is None:
        errors.append("Package is missing Legs")
        return errors

    leg_names = _child_names(gltf, legs_index)
    if pin_count is not None:
        expected_leg_names = [str(pin_number) for pin_number in range(1, pin_count + 1)]
        if leg_names != expected_leg_names:
            errors.append(
                "Legs children mismatch: expected %s, got %s"
                % (expected_leg_names, leg_names)
            )

    if through_hole:
        expected_pin_children = [
            "CopperCirclePad",
            "SolderMask",
            "HoleCylinderPin",
            "CopperCylinderPin",
            "CopperCirclePin",
            "text",
        ]
    else:
        expected_pin_children = [
            "SolderMask",
            "CopperCirclePad",
            "text",
        ]

    for pin_name in leg_names:
        pin_index = _find_named_child(gltf, legs_index, pin_name)
        if pin_index is None:
            errors.append("Legs is missing pin node %s" % pin_name)
            continue
        _expect_child_order(gltf, pin_index, expected_pin_children, errors)

    return errors


def validate_pcb_footprint_glb(
    glb_path: str,
    pin_count: Optional[int] = None,
    through_hole: bool = True,
) -> Tuple[bool, List[str]]:
    """
    Validate a saved GLB file against the PCB footprint hierarchy spec.

    Returns:
        Tuple of (is_valid, errors)
    """
    if GLTF2 is None:
        raise ImportError("pygltflib is required for PCB footprint validation")

    gltf = GLTF2().load_binary(str(Path(glb_path)))
    errors = validate_pcb_footprint_hierarchy(
        gltf,
        pin_count=pin_count,
        through_hole=through_hole,
    )
    return len(errors) == 0, errors
