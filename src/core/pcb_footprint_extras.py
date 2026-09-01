"""Inject GLTF extras into all nodes of a PCB footprint GLB file.

CadQuery has no concept of GLTF extras, so they must be added as a
post-processing step after the GLB is saved.  Every node in the reference
2d.glb carries a rich extras object (renderOrder, pinData, originalName,
hideTransformControls, etc.) that the viewer needs for interactivity and
correct rendering.  This module replicates that behaviour.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from pygltflib import GLTF2
except ImportError:
    GLTF2 = None


_HIDE_CONTROLS = {"translate": "xyz", "rotate": "xyz", "scale": "xyz"}

# Tolerance for float colour comparisons
_CTOL = 0.01

# PCB geometry constants (matching reference 2d.glb)
_PAD_OUTER_RADIUS = 0.625   # CopperCirclePad / CopperCirclePin (1.25mm / 2)
_HOLE_RADIUS = 0.415        # HoleCylinderPin / CopperCylinderPin (0.83mm / 2)
_MARKER_RADIUS = 0.1        # silk/fab firstPinMarker
_CIRCLE_STEPS = 20          # 21-point circle (20 steps + closing point)


def _circle_points(radius: float, steps: int = _CIRCLE_STEPS) -> List[dict]:
    """Return a list of {x, y} dicts tracing a circle at *radius*.

    Generates *steps* evenly-spaced vertices starting at angle 0, plus a
    closing point identical to the first (matching the reference 2d.glb pattern
    of 21 points for a 20-step circle).
    """
    pts = []
    for k in range(steps + 1):
        angle = 2.0 * math.pi * k / steps
        pts.append({"x": radius * math.cos(angle), "y": radius * math.sin(angle)})
    return pts


def _rect_points(half_w: float, half_h: float) -> List[dict]:
    """Return 5 {x, y} dicts tracing a closed rectangle (corners + close)."""
    return [
        {"x": -half_w, "y":  half_h},
        {"x":  half_w, "y":  half_h},
        {"x":  half_w, "y": -half_h},
        {"x": -half_w, "y": -half_h},
        {"x": -half_w, "y":  half_h},
    ]


def _bodyline_points(
    sibling_idx: int,
    layer_name: str,
    body_half_width: float,
    body_half_height: float,
) -> List[dict]:
    """Compute the 2D endpoint pair for a BodyLine node.

    Uses sibling index and known layer structure to determine orientation:
    - fab / crtyd: index 0=top, 1=bottom, 2=left, 3=right
    - silk:        index 0=top, 1=bottom  (no side lines)

    Points are in Package coordinate space (mm from component centre).
    """
    bw, bh = body_half_width, body_half_height
    if sibling_idx == 0:   # top
        return [{"x": -bw, "y": bh}, {"x": bw, "y": bh}]
    elif sibling_idx == 1: # bottom
        return [{"x": -bw, "y": -bh}, {"x": bw, "y": -bh}]
    elif sibling_idx == 2: # left
        return [{"x": -bw, "y": -bh}, {"x": -bw, "y": bh}]
    else:                  # right (index 3)
        return [{"x": bw, "y": -bh}, {"x": bw, "y": bh}]


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


def _rect_pad_xy_extents(pad_spec: dict, side: Optional[str]) -> Tuple[float, float]:
    """X/Y extents of a rect pad: pad length runs toward the body, so it lies
    along X for left/right pins and along Y for top/bottom pins."""
    if side in ("top", "bottom"):
        return pad_spec["width"], pad_spec["length"]
    return pad_spec["length"], pad_spec["width"]


def _build_pin_extras(
    pin_number: str,
    x: float,
    y: float,
    is_through_hole: bool,
    pad_spec: Optional[dict] = None,
    side: Optional[str] = None,
) -> dict:
    spec = pad_spec or {}
    is_pin1 = pin_number == "1"
    if is_through_hole:
        pad_diameter = spec.get("diameter", _PAD_OUTER_RADIUS * 2)
        drill = spec.get("drill", _HOLE_RADIUS * 2)
        if is_pin1:
            pin_data = {
                "unit": "mm",
                "pinType": "ThroughHole",
                "pinShape": "rectangle",
                "coordinates": [],
                "length": pad_diameter,
                "width": pad_diameter,
                "outerDiameter": None,
                "thruHoleType": "plated",
                "thruHoleShape": "circle",
                "innerDiameter": drill,
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
                "outerDiameter": pad_diameter,
                "thruHoleType": "plated",
                "thruHoleShape": "circle",
                "innerDiameter": drill,
                "thruHoleLth": 0,
                "thruHoleWth": 0,
                "position": {"x": x, "y": y},
                "rotation": 0,
                "solder_mask_margin": 0.102,
            }
    elif spec.get("shape") == "rect":
        length_x, width_y = _rect_pad_xy_extents(spec, side)
        pin_data = {
            "unit": "mm",
            "pinType": "SMD",
            "pinShape": "rectangle",
            "coordinates": [],
            "length": length_x,
            "width": width_y,
            "outerDiameter": None,
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
            "outerDiameter": spec.get("diameter", _PAD_OUTER_RADIUS * 2),
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


# LAY-02: KiCad-style layer for every drawn footprint object, derived
# deterministically from the node name (+ its parent layer / pin). Copper spans
# layers on through-hole barrels ("*.Cu"); SMD pads are top copper ("F.Cu").
def _footprint_layer_id(name: str, par_name: str) -> Optional[str]:
    if name == "CopperCirclePad":
        return "F.Cu"
    if name in ("CopperCirclePin", "CopperCylinderPin"):
        return "*.Cu"                              # through-hole barrel: all copper
    if name == "SolderMask":
        return "F.Mask"
    if name == "HoleCylinderPin":
        return "drill"
    if name == "silk_firstPinMarker":
        return "F.SilkS"
    if name == "fab_firstPinMarker":
        return "F.Fab"
    if name == "text" and par_name.isdigit():
        return "F.Fab"                             # pin-number labels
    if name == "BodyLine":
        return {"fab_layer": "F.Fab", "silk_layer": "F.SilkS",
                "crtyd_layer": "F.CrtYd"}.get(par_name)
    if name == "Body" and par_name == "DesignatorName":
        return "F.SilkS"                           # reference designator on silk
    if name == "Body" and par_name == "PackageValue":
        return "F.Fab"
    return None


def inject_pcb_footprint_extras(
    glb_path: str,
    component_name: str,
    package_type: str,
    pin_position_map: Dict[str, Tuple[float, float]],
    fab_dims: Optional[Tuple[float, float]] = None,
    silk_dims: Optional[Tuple[float, float]] = None,
    crtyd_dims: Optional[Tuple[float, float]] = None,
    pad_spec: Optional[dict] = None,
    pin_side_map: Optional[Dict[str, str]] = None,
    dims_source: Optional[str] = None,
    component_height: Optional[float] = None,
    # Legacy params kept for backwards compatibility
    body_width: Optional[float] = None,
    body_height: Optional[float] = None,
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
        fab_dims: (half_width, half_height) of the fab layer in mm.
        silk_dims: (half_width, half_height) of the silk layer in mm.
        crtyd_dims: (half_width, half_height) of the crtyd layer in mm.
        pad_spec: PcbFootprintBuilder.pad_spec dict describing the real pad
                  geometry ({"shape": "rect", "width", "length"} or
                  {"shape": "circle", "diameter", ["drill"]}). Falls back to
                  the legacy reference-GLB circles when omitted.
        pin_side_map: pin_number_str -> side ("left"/"right"/"top"/"bottom"),
                      used to orient rect pads in pinData and pad outlines.
        body_width: Deprecated — use fab_dims instead.
        body_height: Deprecated — use fab_dims instead.

    Returns:
        Number of nodes that received extras.
    """
    if GLTF2 is None:
        raise ImportError("pygltflib is required for extras injection")

    gltf = GLTF2().load_binary(str(Path(glb_path)))
    nodes = gltf.nodes
    if not nodes:
        return 0

    is_through_hole = package_type.upper().startswith(("DIP", "PDIP", "CDIP"))
    parent_map = _build_parent_map(nodes)

    # Resolve per-layer half-dimensions, falling back to legacy body_width/height
    if fab_dims is None and body_width is not None and body_height is not None:
        fab_dims = (body_width / 2.0, body_height / 2.0)
    if silk_dims is None and fab_dims is not None:
        silk_dims = fab_dims
    if crtyd_dims is None and fab_dims is not None:
        crtyd_dims = fab_dims

    _layer_dims: Dict[str, Optional[Tuple[float, float]]] = {
        "fab_layer": fab_dims,
        "silk_layer": silk_dims,
        "crtyd_layer": crtyd_dims,
    }

    # Pre-compute point lists (shared across all pins) from the real pad
    # geometry when available, else the legacy reference-GLB sizes.
    spec = pad_spec or {}
    sides = pin_side_map or {}
    pad_radius = spec.get("diameter", _PAD_OUTER_RADIUS * 2) / 2.0
    hole_radius = spec.get("drill", _HOLE_RADIUS * 2) / 2.0
    pad_circle_pts = _circle_points(pad_radius)
    hole_circle_pts = _circle_points(hole_radius)
    marker_circle_pts = _circle_points(_MARKER_RADIUS)
    pad_rect_pts = _rect_points(pad_radius, pad_radius)

    updated = 0

    for i, node in enumerate(nodes):
        name = node.name or ""
        par_name = _parent_name(i, nodes, parent_map)

        extras: Optional[dict] = None

        # ── Root ──────────────────────────────────────────────────────────────
        if name == "Package":
            extras = {
                "viewType": "2d",
                "dragEffect": True,
                "originalName": "Package",
                "renderOrder": 0,
                # The footprint is a flat top-view artifact: never rotated or
                # scaled (drag/placement stays allowed). Locked on the root.
                "hideTransformControls": {"rotate": "xyz", "scale": "xyz"},
                # FP-18: pick-and-place zero orientation. A fixed convention —
                # 0 deg with pin 1 as the reference — so assembly has a defined
                # placement datum. Deterministic; no datasheet input needed.
                "zeroOrientation": {"angle": 0.0, "unit": "deg", "reference": "pin1"},
            }
            if dims_source:
                # Dimension provenance: "text" (deterministic datasheet
                # text), "vision"/"text+vision" (model-read drawing),
                # "jedec_default" (family defaults), "unverified".
                extras["dimsSource"] = dims_source
                # F-04: uniform provenance key across artifacts (method-level;
                # datasheet URL/revision/page await extraction).
                extras["provenance"] = {"method": dims_source, "component": component_name}
            if component_height is not None:
                # FP-17: component Z height (mm). Source mirrors dimsSource —
                # "unverified"/"jedec_default" until a datasheet "A" is extracted.
                extras["componentHeight"] = {
                    "value": component_height, "unit": "mm", "source": dims_source,
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
        # ref: selectParent=false, renderOrder=3, no hideTransformControls
        elif name == "Body" and par_name in ("DesignatorName", "PackageValue"):
            extras = {
                "originalName": "Body",
                "renderOrder": 3,
                "selectParent": False,
            }

        # BoundingBox: ref has selectParent=false, renderOrder=2, no hideTransformControls
        elif name == "BoundingBox":
            extras = {
                "originalName": "BoundingBox",
                "renderOrder": 2,
                "selectParent": False,
            }

        # ── Pin 1 marker ──────────────────────────────────────────────────────
        elif name == "FirstPinMarker":
            extras = {"originalName": "FirstPinMarker", "renderOrder": 0}

        elif name == "silk_firstPinMarker":
            extras = {
                "points": marker_circle_pts,
                "originalName": "silk_firstPinMarker",
                "renderOrder": 2,
            }

        elif name == "fab_firstPinMarker":
            extras = {
                "points": marker_circle_pts,
                "originalName": "fab_firstPinMarker",
                "renderOrder": 2,
            }

        # ── Legs container ────────────────────────────────────────────────────
        elif name == "Legs":
            extras = {"originalName": "Legs", "renderOrder": 0}

        # ── Individual pin groups (named by pin number) ────────────────────────
        elif name.isdigit() and par_name == "Legs":
            x, y = pin_position_map.get(name, (0.0, 0.0))
            extras = _build_pin_extras(
                name, x, y, is_through_hole, pad_spec=spec, side=sides.get(name)
            )

        # ── Pin sub-components ────────────────────────────────────────────────
        # ref: no selectParent, no hideTransformControls
        elif name == "CopperCirclePad":
            is_pin1 = par_name == "1"
            if not is_through_hole and spec.get("shape") == "rect":
                ext_x, ext_y = _rect_pad_xy_extents(spec, sides.get(par_name))
                pts = _rect_points(ext_x / 2.0, ext_y / 2.0)
            elif is_through_hole and is_pin1:
                pts = pad_rect_pts
            else:
                pts = pad_circle_pts
            extras = {
                "points": pts,
                "originalName": "CopperCirclePad",
                "renderOrder": 3,
            }

        elif name == "SolderMask":
            extras = {
                "originalName": "SolderMask",
                "renderOrder": 2,
            }

        elif name == "HoleCylinderPin":
            extras = {
                "points": hole_circle_pts,
                "renderOrder": 10,
                "originalName": "HoleCylinderPin",
            }

        elif name == "CopperCylinderPin":
            extras = {
                "points": hole_circle_pts,
                "originalName": "CopperCylinderPin",
                "renderOrder": 2,
            }

        elif name == "CopperCirclePin":
            extras = {
                "points": hole_circle_pts,
                "originalName": "CopperCirclePin",
                "renderOrder": 2,
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
        # ref: includes body:"2d"
        elif name == "Body" and par_name == "Package":
            extras = {"body": "2d", "originalName": "Body", "renderOrder": 0}

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
            # Add points using the per-layer half-dimensions
            layer_dim = _layer_dims.get(par_name)
            if layer_dim is not None:
                extras["points"] = _bodyline_points(
                    sibling_idx, par_name, layer_dim[0], layer_dim[1]
                )
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

        # LAY-02: stamp the layerId on every drawn (mesh-bearing) fab object.
        # BoundingBox is a transparent selection helper, not a fab object, so it
        # is intentionally left without one.
        if extras is not None and node.mesh is not None and name != "BoundingBox":
            lid = _footprint_layer_id(name, par_name)
            if lid:
                extras["layerId"] = lid

        if extras is not None:
            node.extras = extras
            updated += 1

    _fix_materials(gltf)
    gltf.save(str(Path(glb_path)))
    return updated
