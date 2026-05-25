"""Validate PCB footprint hierarchy similarity against a reference GLB."""

from pathlib import Path
from typing import List, Optional, Tuple

try:
    from pygltflib import GLTF2
except ImportError:
    GLTF2 = None


def _child_names(gltf: "GLTF2", node_index: int) -> List[str]:
    node = gltf.nodes[node_index]
    return [gltf.nodes[child_index].name for child_index in (node.children or [])]


def _find_named_child(
    gltf: "GLTF2", parent_index: int, child_name: str
) -> Optional[int]:
    for child_index in (gltf.nodes[parent_index].children or []):
        if gltf.nodes[child_index].name == child_name:
            return child_index
    return None


def _get_root_node(gltf: "GLTF2") -> Optional[int]:
    if not gltf.scenes:
        return None
    scene_index = gltf.scene if gltf.scene is not None else 0
    scene = gltf.scenes[scene_index]
    if not scene.nodes:
        return None
    return scene.nodes[0]


def _normalize_body_line_names(names: List[str]) -> List[str]:
    normalized: List[str] = []
    for name in names:
        if name and name.startswith("BodyLine"):
            normalized.append("BodyLine")
        else:
            normalized.append(name)
    return normalized


def validate_pcb_footprint_similarity_to_reference(
    gltf: "GLTF2", reference_gltf: "GLTF2"
) -> List[str]:
    """
    Validate structural similarity to a reference footprint GLB.

    This comparison is intentionally shape-focused:
    - Allows any pin count
    - Allows either BodyLine or BodyLine_* naming
    - Allows pin child order differences as long as required names exist
    """
    errors: List[str] = []

    output_root = _get_root_node(gltf)
    ref_root = _get_root_node(reference_gltf)
    if output_root is None:
        return ["Output GLB has no scene root"]
    if ref_root is None:
        return ["Reference GLB has no scene root"]

    output_root_name = gltf.nodes[output_root].name
    ref_root_name = reference_gltf.nodes[ref_root].name
    if output_root_name != ref_root_name:
        errors.append(
            "Root name mismatch: expected %r, got %r"
            % (ref_root_name, output_root_name)
        )
        return errors

    ref_top = _child_names(reference_gltf, ref_root)
    output_top = _child_names(gltf, output_root)
    if output_top != ref_top:
        errors.append(
            "Top-level children mismatch: expected %s, got %s"
            % (ref_top, output_top)
        )

    # Validate container children for shared named sections.
    for section_name in ["DesignatorName", "PackageValue", "FirstPinMarker", "Body"]:
        ref_section = _find_named_child(reference_gltf, ref_root, section_name)
        out_section = _find_named_child(gltf, output_root, section_name)
        if ref_section is None:
            continue
        if out_section is None:
            errors.append("Missing top-level section: %s" % section_name)
            continue

        ref_children = _child_names(reference_gltf, ref_section)
        out_children = _child_names(gltf, out_section)
        if out_children != ref_children:
            errors.append(
                "%s children mismatch: expected %s, got %s"
                % (section_name, ref_children, out_children)
            )

    # Validate body line structure with normalized line names.
    ref_body = _find_named_child(reference_gltf, ref_root, "Body")
    out_body = _find_named_child(gltf, output_root, "Body")
    if ref_body is not None and out_body is not None:
        for layer_name in _child_names(reference_gltf, ref_body):
            ref_layer = _find_named_child(reference_gltf, ref_body, layer_name)
            out_layer = _find_named_child(gltf, out_body, layer_name)
            if ref_layer is None:
                continue
            if out_layer is None:
                errors.append("Body missing layer: %s" % layer_name)
                continue

            ref_lines = _normalize_body_line_names(
                _child_names(reference_gltf, ref_layer)
            )
            out_lines = _normalize_body_line_names(_child_names(gltf, out_layer))
            if out_lines != ref_lines:
                errors.append(
                    "%s lines mismatch (normalized): expected %s, got %s"
                    % (layer_name, ref_lines, out_lines)
                )

    ref_legs = _find_named_child(reference_gltf, ref_root, "Legs")
    out_legs = _find_named_child(gltf, output_root, "Legs")
    if ref_legs is None:
        return errors
    if out_legs is None:
        errors.append("Missing top-level section: Legs")
        return errors

    out_pin_names = _child_names(gltf, out_legs)
    if not out_pin_names:
        errors.append("Legs has no pins")
        return errors

    # Require the workflow output to keep numeric sequential pin naming.
    expected_pin_names = [str(index) for index in range(1, len(out_pin_names) + 1)]
    if out_pin_names != expected_pin_names:
        errors.append(
            "Leg names should be sequential numeric labels: expected %s, got %s"
            % (expected_pin_names, out_pin_names)
        )

    ref_pin_names = _child_names(reference_gltf, ref_legs)
    if not ref_pin_names:
        errors.append("Reference Legs has no pins")
        return errors

    ref_pin = _find_named_child(reference_gltf, ref_legs, ref_pin_names[0])
    if ref_pin is None:
        errors.append("Could not resolve reference pin node")
        return errors

    expected_pin_child_names = _child_names(reference_gltf, ref_pin)
    expected_pin_child_set = set(expected_pin_child_names)

    for pin_name in out_pin_names:
        out_pin = _find_named_child(gltf, out_legs, pin_name)
        if out_pin is None:
            errors.append("Missing pin node: %s" % pin_name)
            continue
        out_pin_children = _child_names(gltf, out_pin)
        out_pin_child_set = set(out_pin_children)
        if out_pin_child_set != expected_pin_child_set:
            errors.append(
                "Pin %s children mismatch: expected names %s, got %s"
                % (pin_name, sorted(expected_pin_child_set), sorted(out_pin_child_set))
            )

    return errors


def validate_glb_similarity_to_reference(
    glb_path: str, reference_glb_path: Optional[str] = None
) -> Tuple[bool, List[str]]:
    """
    Validate a footprint GLB against a reference hierarchy template.

    Returns:
        Tuple of (is_similar, errors)
    """
    if GLTF2 is None:
        raise ImportError("pygltflib is required for GLB hierarchy validation")

    output_path = Path(glb_path)
    if reference_glb_path is None:
        # src/core/reference_glb_hierarchy.py -> repo root
        reference_path = Path(__file__).resolve().parents[2] / "2d.glb"
    else:
        reference_path = Path(reference_glb_path)

    if not output_path.exists():
        return False, ["Output GLB not found: %s" % output_path]
    if not reference_path.exists():
        return False, ["Reference GLB not found: %s" % reference_path]

    gltf = GLTF2().load_binary(str(output_path))
    reference_gltf = GLTF2().load_binary(str(reference_path))
    errors = validate_pcb_footprint_similarity_to_reference(gltf, reference_gltf)
    return len(errors) == 0, errors
