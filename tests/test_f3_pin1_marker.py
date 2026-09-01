"""QC F3: both pin-1 markers (silk + fab) sit top-left OUTSIDE the copper.

Root-cause fix (fab marker moved off the pad to pin-1's outside corner, matching
the silk marker) + the FP-08 guard extended to fail if either marker overlaps a
pad, so it can't silently regress.
"""
import tempfile
from pathlib import Path

from pygltflib import GLTF2

from src.schematic_generator import build_pcb_2d_schematic
from src.conformance.checks import (
    check_pin1_marker_present, PartContext,
    _world_matrices, _copper_pad_boxes, _subtree_aabb3, _find_child, _root,
    _board_axes, _planar_clearance,
)
from src.conformance.model import CheckStatus


def _footprint(pkg="SOIC-8", n=8) -> str:
    out = str(Path(tempfile.mkdtemp()) / "f.glb")
    build_pcb_2d_schematic(package_type=pkg, pin_count=n, component_name="X",
                           pin_data=[{"number": str(i), "name": f"P{i}"} for i in range(1, n + 1)],
                           output_path=out)
    return out


def _marker_clearances(glb: str):
    g = GLTF2().load_binary(glb)
    w = _world_matrices(g)
    root = _root(g)
    mk = _find_child(g, root, "FirstPinMarker")
    pads = _copper_pad_boxes(g, w)
    axes = _board_axes(list(pads.values()))
    out = {}
    for nm in ("silk_firstPinMarker", "fab_firstPinMarker"):
        node = _find_child(g, mk, nm)
        box = _subtree_aabb3(g, node, w)
        out[nm] = min(_planar_clearance(box, p, axes) for p in pads.values())
    return out


def test_both_markers_off_copper():
    for pkg, n in (("SOIC-8", 8), ("DIP-8", 8)):
        cl = _marker_clearances(_footprint(pkg, n))
        assert cl["silk_firstPinMarker"] > 0, cl
        assert cl["fab_firstPinMarker"] > 0, cl        # QC F3: fab is off the pad now


def test_fab_marker_matches_silk_position():
    # Both markers now sit at the same outside corner.
    cl = _marker_clearances(_footprint())
    assert abs(cl["silk_firstPinMarker"] - cl["fab_firstPinMarker"]) < 1e-6


def test_fp08_passes_off_copper():
    outcome = check_pin1_marker_present(PartContext("x", {"footprint": _footprint()}))
    assert outcome.status is CheckStatus.PASS


def test_fp08_skips_without_footprint():
    assert check_pin1_marker_present(PartContext("x", {})).status is CheckStatus.SKIP
