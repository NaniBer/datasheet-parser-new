"""Inject GLTF extras into all nodes of a PCB footprint GLB file.

CadQuery has no concept of GLTF extras, so they must be added as a
post-processing step after the GLB is saved.  Every node in the reference
2d.glb carries a rich extras object (renderOrder, pinData, originalName,
hideTransformControls, etc.) that the viewer needs for interactivity and
correct rendering.  This module replicates that behaviour.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from pygltflib import GLTF2
except ImportError:
    GLTF2 = None


_HIDE_CONTROLS = {"translate": "xyz", "rotate": "xyz", "scale": "xyz"}

# Tolerance for float colour comparisons
_CTOL = 0.01


def _color_matches(factor, r, g, b, a=1.0) -> bool:
    if not factor or len(factor) < 4:
        return False
    return all(abs(factor[i] - v) < _CTOL for i, v in enumerate([r, g, b, a]))


def _fix_materials(gltf) -> None:
    """
    Correct material metallic/roughness/extension properties to match the
    reference 2d.glb.  CadQuery always emits metallic=1.0/roughness=1.0;
    the reference uses different values per material role.
    """
    for mat in gltf.materials or []:
        pbr = mat.pbrMetallicRoughness
        if pbr is None:
            continue
        color = list(pbr.baseColorFactor or [])

        # ── Transparent BoundingBox ───────────────────────────────────────────
        if _color_matches(color, 1, 1, 1, 0):
            pbr.metallicFactor = 0.0
            pbr.roughnessFactor = 0.9
            mat.alphaMode = "BLEND"
            _set_unlit(mat)

        # ── Dark purple (PackageValue text) ───────────────────────────────────
        elif _color_matches(color, 0.093, 0.015, 0.165):
            pbr.metallicFactor = 0.0
            pbr.roughnessFactor = 0.9
            _set_unlit(mat)

        # ── Pure white (DesignatorName text / silk lines / pin text) ─────────
        elif _color_matches(color, 1, 1, 1):
            pbr.metallicFactor = 0.0
            pbr.roughnessFactor = 0.9
            _set_unlit(mat)

        # ── Yellow (fab BodyLines / fab_firstPinMarker) ───────────────────────
        elif _color_matches(color, 1, 1, 0):
            pbr.metallicFactor = 0.5
            pbr.roughnessFactor = 0.5

        # ── Red (copper pads / rings) ─────────────────────────────────────────
        elif _color_matches(color, 1, 0, 0):
            pbr.metallicFactor = 0.5
            pbr.roughnessFactor = 0.5

        # ── Dark brown (SolderMask) ───────────────────────────────────────────
        elif _color_matches(color, 0.220, 0.122, 0.002):
            pbr.metallicFactor = 0.5
            pbr.roughnessFactor = 0.5

        # ── Black (HoleCylinderPin) ───────────────────────────────────────────
        elif _color_matches(color, 0, 0, 0):
            pbr.metallicFactor = 0.5
            pbr.roughnessFactor = 0.5

        # ── Magenta (crtyd BodyLines) ─────────────────────────────────────────
        elif _color_matches(color, 0.831, 0.005, 0.913):
            pbr.metallicFactor = 0.0
            pbr.roughnessFactor = 1.0
            mat.doubleSided = False


def _set_unlit(mat) -> None:
    """Add KHR_materials_unlit extension to a material."""
    if mat.extensions is None:
        mat.extensions = {}
    mat.extensions["KHR_materials_unlit"] = {}
    # Ensure the extension is declared at top level
    # (pygltflib handles extensionsUsed automatically on save)


def _build_parent_map(nodes) -> Dict[int, int]:
    """Return {child_index: parent_index} for every node in the list."""
    parent: Dict[int, int] = {}
    for i, node in enumerate(nodes):
        for child in node.children or []:
            parent[child] = i
    return parent


def _parent_name(idx: int, nodes, parent_map: Dict[int, int]) -> str:
    p = parent_map.get(idx)
    return (nodes[p].name or "") if p is not None else ""


def _grandparent_name(idx: int, nodes, parent_map: Dict[int, int]) -> str:
    p = parent_map.get(idx)
    if p is None:
        return ""
    gp = parent_map.get(p)
    return (nodes[gp].name or "") if gp is not None else ""


def _sibling_index(idx: int, nodes, parent_map: Dict[int, int]) -> int:
    """Return the 0-based position of *idx* among its siblings."""
    p = parent_map.get(idx)
    if p is None:
        return 0
    siblings = nodes[p].children or []
    try:
        return siblings.index(idx)
    except ValueError:
        return 0


def _build_pin_extras(
    pin_number: str,
    x: float,
    y: float,
    is_through_hole: bool,
) -> dict:
    is_pin1 = pin_number == "1"
    if is_through_hole:
        if is_pin1:
            pin_data = {
                "unit": "mm",
                "pinType": "ThroughHole",
                "pinShape": "rectangle",
                "coordinates": [],
                "length": 1.25,
                "width": 1.25,
                "outerDiameter": None,
                "thruHoleType": "plated",
                "thruHoleShape": "circle",
                "innerDiameter": 0.83,
                "thruHoleLth": 0,
                "thruHoleWth": 0,
                "position": {"x": x, "y": y},
                "rotation": 0,
                "solder_mask_margin": 0.102,
            }
        else:
            pin_data = {
                "unit": "mm",
                "pinType": "ThroughHole",
                "pinShape": "circle",
                "coordinates": [],
                "length": None,
                "width": None,
                "outerDiameter": 1.25,
                "thruHoleType": "plated",
                "thruHoleShape": "circle",
                "innerDiameter": 0.83,
                "thruHoleLth": 0,
                "thruHoleWth": 0,
                "position": {"x": x, "y": y},
                "rotation": 0,
                "solder_mask_margin": 0.102,
            }
    else:
        pin_data = {
            "unit": "mm",
            "pinType": "SMD",
            "pinShape": "circle",
            "coordinates": [],
            "outerDiameter": 1.25,
            "position": {"x": x, "y": y},
            "rotation": 0,
            "solder_mask_margin": 0.102,
        }

    return {
        "pinData": pin_data,
        "originalName": pin_number,
        "renderOrder": 0,
        "dragEffect": False,
    }


def inject_pcb_footprint_extras(
    glb_path: str,
    component_name: str,
    package_type: str,
    pin_position_map: Dict[str, Tuple[float, float]],
) -> int:
    """
    Walk every node in *glb_path* and attach the correct extras dict.

    Args:
        glb_path: Path to the GLB file (modified in-place).
        component_name: Component identifier written into PackageValue extras.
        package_type: Package type string (e.g. "DIP-8") — used to determine
                      through-hole vs SMD pin extras.
        pin_position_map: Mapping of pin_number_str -> (x, y) in mm, used to
                          populate pinData.position in pin-group extras.

    Returns:
        Number of nodes that received extras.
    """
    if GLTF2 is None:
        raise ImportError("pygltflib is required for extras injection")

    gltf = GLTF2().load_binary(str(Path(glb_path)))
    nodes = gltf.nodes
    if not nodes:
        return 0

    is_through_hole = package_type.upper().startswith(("DIP", "CDIP"))
    parent_map = _build_parent_map(nodes)
    updated = 0

    for i, node in enumerate(nodes):
        name = node.name or ""
        par_name = _parent_name(i, nodes, parent_map)
        gpar_name = _grandparent_name(i, nodes, parent_map)

        extras: Optional[dict] = None

        # ── Root ──────────────────────────────────────────────────────────────
        if name == "Package":
            extras = {
                "viewType": "2d",
                "dragEffect": True,
                "originalName": "Package",
                "renderOrder": 0,
            }

        # ── Labels ────────────────────────────────────────────────────────────
        elif name == "DesignatorName":
            extras = {
                "value": "REF**",
                "size": 1.27,
                "selectParent": True,
                "dragEffect": True,
                "renderOrder": 0,
                "originalName": "DesignatorName",
                "hideTransformControls": _HIDE_CONTROLS,
            }

        elif name == "PackageValue":
            extras = {
                "value": component_name,
                "size": 1.27,
                "selectParent": True,
                "dragEffect": True,
                "renderOrder": 0,
                "originalName": "PackageValue",
                "hideTransformControls": _HIDE_CONTROLS,
            }

        # Body child of DesignatorName / PackageValue (text mesh node)
        elif name == "Body" and par_name in ("DesignatorName", "PackageValue"):
            extras = {
                "originalName": "Body",
                "renderOrder": 0,
                "selectParent": True,
                "hideTransformControls": _HIDE_CONTROLS,
            }

        elif name == "BoundingBox":
            extras = {
                "originalName": "BoundingBox",
                "renderOrder": 0,
                "selectParent": True,
                "hideTransformControls": _HIDE_CONTROLS,
            }

        # ── Pin 1 marker ──────────────────────────────────────────────────────
        elif name == "FirstPinMarker":
            extras = {"originalName": "FirstPinMarker", "renderOrder": 0}

        elif name == "silk_firstPinMarker":
            extras = {"originalName": "silk_firstPinMarker", "renderOrder": 2}

        elif name == "fab_firstPinMarker":
            extras = {"originalName": "fab_firstPinMarker", "renderOrder": 2}

        # ── Legs container ────────────────────────────────────────────────────
        elif name == "Legs":
            extras = {"originalName": "Legs", "renderOrder": 0}

        # ── Individual pin groups (named by pin number) ────────────────────────
        elif name.isdigit() and par_name == "Legs":
            x, y = pin_position_map.get(name, (0.0, 0.0))
            extras = _build_pin_extras(name, x, y, is_through_hole)

        # ── Pin sub-components ────────────────────────────────────────────────
        elif name == "CopperCirclePad":
            extras = {
                "originalName": "CopperCirclePad",
                "renderOrder": 3,
                "selectParent": True,
                "hideTransformControls": _HIDE_CONTROLS,
            }

        elif name == "SolderMask":
            extras = {
                "originalName": "SolderMask",
                "renderOrder": 2,
                "selectParent": True,
                "hideTransformControls": _HIDE_CONTROLS,
            }

        elif name == "HoleCylinderPin":
            extras = {
                "originalName": "HoleCylinderPin",
                "renderOrder": 10,
                "selectParent": True,
                "hideTransformControls": _HIDE_CONTROLS,
            }

        elif name == "CopperCylinderPin":
            extras = {
                "originalName": "CopperCylinderPin",
                "renderOrder": 3,
                "selectParent": True,
                "hideTransformControls": _HIDE_CONTROLS,
            }

        elif name == "CopperCirclePin":
            extras = {
                "originalName": "CopperCirclePin",
                "renderOrder": 3,
                "selectParent": True,
                "hideTransformControls": _HIDE_CONTROLS,
            }

        elif name == "text" and par_name.isdigit():
            extras = {
                "pinNumber": par_name,
                "renderOrder": 10,
                "selectParent": True,
                "hideTransformControls": _HIDE_CONTROLS,
                "originalName": "text",
            }

        # ── Body outline container ─────────────────────────────────────────────
        elif name == "Body" and par_name == "Package":
            extras = {"originalName": "Body", "renderOrder": 0}

        elif name in ("fab_layer", "silk_layer", "crtyd_layer"):
            extras = {"originalName": name, "renderOrder": 0}

        elif name == "BodyLine":
            sibling_idx = _sibling_index(i, nodes, parent_map)
            extras = {
                "body": "2d",
                "index": sibling_idx,
                "originalName": "BodyLine",
                "renderOrder": 0,
            }
            # Raise BodyLines 0.015 mm above the board surface (matches reference)
            t = list(node.translation) if node.translation else [0.0, 0.0, 0.0]
            if len(t) >= 3:
                t[2] = 0.015
            else:
                t = [t[0] if len(t) > 0 else 0.0, t[1] if len(t) > 1 else 0.0, 0.015]
            node.translation = t

        # FirstPinMarker sits at z=0.15 in the reference
        if name == "FirstPinMarker":
            t = list(node.translation) if node.translation else [0.0, 0.0, 0.0]
            if len(t) >= 3:
                t[2] = 0.15
            else:
                t = [t[0] if len(t) > 0 else 0.0, t[1] if len(t) > 1 else 0.0, 0.15]
            node.translation = t

        if extras is not None:
            node.extras = extras
            updated += 1

    _fix_materials(gltf)
    gltf.save(str(Path(glb_path)))
    return updated
