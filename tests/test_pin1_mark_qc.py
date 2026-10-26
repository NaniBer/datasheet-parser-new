"""QC re-check 2026-10-23 (item F1): pin-1 mark on F.SilkS, beside pad 1, INSIDE the courtyard.

All five re-checked parts (PGA2311P FP-03, AD9106 FP-07, TL16C2550 FP-07,
74LVC1G99 FP-06, ADV7180 FP-06) flagged "no pin-1 mark on the silkscreen;
pin-1 dot outside the courtyard". The 14 Oct convention (dot past the courtyard
corner) is replaced: the silk dot sits next to pad 1, inside the courtyard,
>= 0.20 mm off every copper land (exposed pad included). Covered per family.
"""
import tempfile
from functools import lru_cache
from pathlib import Path

import pytest
from pygltflib import GLTF2

from src.conformance.checks import (
    PartContext, _board_axes, _copper_pad_boxes, _find_child, _planar_clearance,
    _root, _subtree_aabb3, _world_matrices, check_pin1_marker_present,
    check_silk_pad_clearance,
)
from src.conformance.model import CheckStatus
from src.schematic_generator.pcb_footprint_builder import PcbFootprintBuilder

SILK_PAD_CLEARANCE = 0.20

# AD9106 CP-32-12 outline (LFCSP-32 with a 3.75 mm exposed pad).
LFCSP_DIMS = {"e": 0.5, "D": 5.0, "E": 5.0, "D1": 5.0, "E1": 5.0, "D2": 3.6, "E2": 3.6,
              "D2_max": 3.75, "E2_max": 3.75, "b": 0.25, "b_max": 0.3, "L": 0.4,
              "L_max": 0.5, "A": 0.8}

FAMILIES = [
    ("PDIP-16", 16, None),      # through-hole (PGA2311P)
    ("SOIC-8", 8, None),
    ("TSSOP-14", 14, None),
    ("TQFP-48", 48, None),      # TL16C2550
    ("LQFP-48", 48, None),      # ADV7180
    ("LFCSP-32", 32, "lfcsp"),  # AD9106, exposed pad
    ("SOT833-1", 8, None),      # 74LVC1G99, tiny 1.0 x 1.95 body
]


@lru_cache(maxsize=None)
def _build(pkg: str, n: int, dims_key):
    dims = dict(LFCSP_DIMS) if dims_key == "lfcsp" else None
    b = PcbFootprintBuilder(pkg, n, "X", extracted_dims=dims)
    out = str(Path(tempfile.mkdtemp()) / "f.glb")
    assert b.save_glb(out, [{"number": str(i), "name": f"P{i}"} for i in range(1, n + 1)])
    return b, out


def _geometry(glb: str):
    g = GLTF2().load_binary(glb)
    w = _world_matrices(g)
    root = _root(g)
    mk = _find_child(g, root, "FirstPinMarker")
    silk = _find_child(g, mk, "silk_firstPinMarker")
    crt = _find_child(g, _find_child(g, root, "Body"), "crtyd_layer")
    pads = _copper_pad_boxes(g, w)
    axes = _board_axes(list(pads.values()))
    return g, silk, _subtree_aabb3(g, silk, w), _subtree_aabb3(g, crt, w), pads, axes


def _layer_ids(g, node) -> set:
    ids, stack = set(), [node]
    while stack:
        i = stack.pop()
        lid = (g.nodes[i].extras or {}).get("layerId")
        if lid:
            ids.add(lid)
        stack.extend(g.nodes[i].children or [])
    return ids


@pytest.mark.parametrize("pkg,n,dims", FAMILIES)
def test_silk_pin1_mark_beside_pad1_inside_courtyard(pkg, n, dims):
    b, glb = _build(pkg, n, dims)
    g, silk, dot, crt, pads, axes = _geometry(glb)

    assert _layer_ids(g, silk) == {"F.SilkS"}, "pin-1 mark must print on the silkscreen"
    # Inside the courtyard outline (outer AABB of the courtyard lines) ...
    for ax in axes:
        assert crt[0][ax] <= dot[0][ax] and dot[1][ax] <= crt[1][ax], (pkg, dot, crt)
    # ... and inside the courtyard line's inner edge in the builder frame.
    *_, cw, ch = b._layer_half_dims()
    mx, my = b._pin1_marker_xy(*b._layer_half_dims(include_pin1_marker=False)[4:])
    inner = b.SILK_MARKER_RADIUS + b.LINE_THICKNESS / 2 - 1e-9
    assert abs(mx) + inner <= cw and abs(my) + inner <= ch

    # >= 0.20 mm off every copper land (exposed pad included), and pad 1 is
    # the nearest land so the mark reads as pin 1.
    clear = {name: _planar_clearance(dot, box, axes) for name, box in pads.items()}
    assert min(clear.values()) >= SILK_PAD_CLEARANCE - 1e-6, (pkg, clear)
    assert clear["1"] == pytest.approx(min(clear.values())), (pkg, clear)
    assert clear["1"] < 0.5, f"{pkg}: mark is not beside pad 1 ({clear['1']:.3f} mm)"


@pytest.mark.parametrize("pkg,n,dims", FAMILIES)
def test_conformance_pin1_and_silk_clearance_pass(pkg, n, dims):
    _, glb = _build(pkg, n, dims)
    ctx = PartContext("x", {"footprint": glb})
    assert check_pin1_marker_present(ctx).status is CheckStatus.PASS
    assert check_silk_pad_clearance(ctx).status is CheckStatus.PASS


def test_quad_courtyards_unchanged_when_the_mark_fits():
    # The dot fits in the pin-1 corner of a QFP/QFN: no courtyard growth.
    for pkg, n, dims in (("TQFP-48", 48, None), ("LFCSP-32", 32, "lfcsp")):
        b, _ = _build(pkg, n, dims)
        assert b._layer_half_dims()[4:] == b._layer_half_dims(include_pin1_marker=False)[4:]


def test_conformance_fails_a_mark_outside_the_courtyard():
    # Regression guard for the rejected 14 Oct convention.
    _, glb = _build("SOIC-8", 8, None)
    g, silk, dot, crt, _, axes = _geometry(glb)
    mk = _find_child(g, _root(g), "FirstPinMarker")
    t = list(g.nodes[mk].translation or [0.0, 0.0, 0.0])
    t[axes[0]] -= float(crt[1][axes[0]] - crt[0][axes[0]])   # push it a courtyard-width away
    g.nodes[mk].translation = t
    moved = str(Path(tempfile.mkdtemp()) / "moved.glb")
    g.save_binary(moved)
    outcome = check_pin1_marker_present(PartContext("x", {"footprint": moved}))
    assert outcome.status is CheckStatus.FAIL
    assert "outside the courtyard" in outcome.message
