"""QC re-check 2026-10-23, every part: symbol designator and pin-number placement.

* SCH-05 (B3): "U1" was drawn in the middle of the body. The platform re-renders
  the designator glyph at the DesignatorName node's own position, and ours sat at
  the origin with the position baked into the mesh. The node now carries the
  anchor (above the body, top-left) and the glyphs start at its local origin.
* SCH-09 (B2): pin numbers sat past the connection dot, where wires attach. They
  now sit just off the pin line, between the body edge and the connection end.
"""
import tempfile
from pathlib import Path

import numpy as np
import pytest
from pygltflib import GLTF2

from src.schematic_generator.pinout_diagram_builder import PinoutDiagramBuilder


def _build(pkg, n):
    pins = [{"number": str(i), "name": f"P{i}"} for i in range(1, n + 1)]
    b = PinoutDiagramBuilder(pkg, n, "PART", pin_data=pins)
    out = str(Path(tempfile.mkdtemp()) / "sym.glb")
    assert b.save_glb(out, pins)
    return b, GLTF2().load_binary(out)


def _parents(g):
    return {c: i for i, n in enumerate(g.nodes) for c in (n.children or [])}


def _world_bbox(g, par, i):
    off, j = np.zeros(3), i
    while True:
        if g.nodes[j].translation:
            off += g.nodes[j].translation
        if j not in par:
            break
        j = par[j]
    prims = g.meshes[g.nodes[i].mesh].primitives
    lo = np.min([g.accessors[p.attributes.POSITION].min for p in prims], axis=0) + off
    hi = np.max([g.accessors[p.attributes.POSITION].max for p in prims], axis=0) + off
    return lo, hi


def _child(g, i, name):
    return next(c for c in g.nodes[i].children if g.nodes[c].name == name)


@pytest.mark.parametrize("pkg,n", [("PDIP-16", 16), ("TQFP-48", 48)])
def test_designator_node_is_anchored_above_body_top_left(pkg, n):
    b, g = _build(pkg, n)
    par = _parents(g)
    half_w, half_h = b.params.body_width / 2, b.params.body_height / 2
    dn = next(i for i, nd in enumerate(g.nodes) if nd.name == "DesignatorName")
    tx, ty, _ = g.nodes[dn].translation
    assert tx == pytest.approx(-half_w)
    assert ty > half_h                                   # outside, above the body
    body = _child(g, dn, "Body")
    local_min = np.min([g.accessors[p.attributes.POSITION].min
                        for p in g.meshes[g.nodes[body].mesh].primitives], axis=0)
    assert abs(local_min[0]) < 0.5 and abs(local_min[1]) < 0.5   # glyphs at the node origin
    lo, _ = _world_bbox(g, par, body)
    assert lo[1] > half_h

    pv = next(i for i, nd in enumerate(g.nodes) if nd.name == "PackageValue")
    _, hi = _world_bbox(g, par, _child(g, pv, "Body"))
    assert g.nodes[pv].translation[0] == pytest.approx(-half_w)
    assert hi[1] < -half_h                               # value below the body


@pytest.mark.parametrize("pkg,n", [("PDIP-16", 16), ("TQFP-48", 48), ("SOIC-8", 8)])
def test_pin_number_sits_on_the_leg_not_past_the_connection_end(pkg, n):
    b, g = _build(pkg, n)
    par = _parents(g)
    legs = next(i for i, nd in enumerate(g.nodes) if nd.name == "Legs")
    sides = {p.pin_number: p.side for p in b.pin_positions}
    checked = 0
    for pin in g.nodes[legs].children:
        num = g.nodes[pin].name
        if num not in sides:
            continue
        leg_lo, leg_hi = _world_bbox(g, par, _child(g, pin, "leg"))
        t_lo, t_hi = _world_bbox(g, par, _child(g, pin, "text"))
        along, across = (0, 1) if sides[num] in ("left", "right") else (1, 0)
        # Within the leg's span (between the body edge and the connection end)...
        assert t_lo[along] >= leg_lo[along] - 1e-3 and t_hi[along] <= leg_hi[along] + 1e-3, num
        # ...and clear of the pin line: above it, or left of a vertical pin.
        if across == 1:
            assert t_lo[1] > leg_hi[1], num
        else:
            assert t_hi[0] < leg_lo[0], num
        checked += 1
    assert checked == n
