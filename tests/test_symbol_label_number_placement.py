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
    cx, cy = b._body_center()
    left = cx - b.params.body_width / 2
    top, bottom = cy + b.params.body_height / 2, cy - b.params.body_height / 2
    dn = next(i for i, nd in enumerate(g.nodes) if nd.name == "DesignatorName")
    tx, ty, _ = g.nodes[dn].translation
    assert tx == pytest.approx(left)
    assert ty > top                                      # outside, above the body
    body = _child(g, dn, "Body")
    local_min = np.min([g.accessors[p.attributes.POSITION].min
                        for p in g.meshes[g.nodes[body].mesh].primitives], axis=0)
    assert abs(local_min[0]) < 0.5 and abs(local_min[1]) < 0.5   # glyphs at the node origin
    lo, _ = _world_bbox(g, par, body)
    assert lo[1] > top

    pv = next(i for i, nd in enumerate(g.nodes) if nd.name == "PackageValue")
    _, hi = _world_bbox(g, par, _child(g, pv, "Body"))
    assert g.nodes[pv].translation[0] == pytest.approx(left)
    assert hi[1] < bottom                                # value below the body


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


@pytest.mark.parametrize("pkg,n", [("PDIP-16", 16), ("SOIC-8", 8), ("SOIC-14", 14),
                                   ("TQFP-48", 48), ("LQFP-64", 64), ("QFN-32", 32),
                                   ("TSSOP-20", 20)])
def test_pins_centred_in_body_with_ends_on_grid(pkg, n):
    # QC SCH-06 (B4): the body was snapped to an even grid multiple, leaving an
    # empty 5.08 mm band below the last pin (top 2.54 vs bottom 5.08). Now one
    # grid step of clearance at both ends of every full side, pin ends on grid.
    pins = [{"number": str(i), "name": f"P{i}"} for i in range(1, n + 1)]
    b = PinoutDiagramBuilder(pkg, n, "PART", pin_data=pins)
    g, leg = b.params.pin_pitch, b.params.pin_geometry.leg_length
    cx, cy = b._body_center()
    L, R = cx - b.params.body_width / 2, cx + b.params.body_width / 2
    T, B = cy + b.params.body_height / 2, cy - b.params.body_height / 2
    by_side = {}
    for p in b.pin_positions:
        by_side.setdefault(p.side, []).append(p)
    longest = max(len(v) for s, v in by_side.items() if s in ("left", "right"))
    quad = "top" in by_side or "bottom" in by_side
    for side, ps in by_side.items():
        if side in ("left", "right"):
            if len(ps) != longest:
                continue                     # shorter column (EPAD on the other side)
            ys = [p.y for p in ps]
            ends = (T - max(ys), min(ys) - B)
        else:
            xs = [p.x for p in ps]
            ends = (min(xs) - L, R - max(xs))
        # Same clearance at both ends; exactly one grid step on dual-row parts
        # (quads keep extra corner room for the names, see the test below).
        assert ends[0] == pytest.approx(ends[1]), (side, ends)
        assert ends[0] == pytest.approx(g) if not quad else ends[0] >= g - 1e-6, (side, ends)
    for p in b.pin_positions:
        dx, dy = {"left": (-leg, 0), "right": (leg, 0),
                  "top": (0, leg), "bottom": (0, -leg)}[p.side]
        for v in ((p.x + dx) / g, (p.y + dy) / g):
            assert v == pytest.approx(round(v), abs=1e-6), (p.pin_number, v)


def test_epad_pin_not_on_the_body_corner():
    # QC AD9106 SCH-10: the EPAD pin sat on the body's bottom-left corner.
    pins = [{"number": str(i), "name": f"P{i}"} for i in range(1, 33)]
    b = PinoutDiagramBuilder("LFCSP-32", 32, "PART", pin_data=pins)
    epad = next(p for p in b.pin_positions if p.pin_number == "33")
    cy = b._body_center()[1]
    top, bottom = cy + b.params.body_height / 2, cy - b.params.body_height / 2
    first = max(p.y for p in b.pin_positions if p.side == "left")
    # The EPAD closes the left column with the same clearance as its top end.
    assert epad.y - bottom == pytest.approx(top - first)
    assert epad.y - bottom >= b.params.pin_pitch - 1e-6


def test_quad_names_share_one_inset_and_clear_the_corners():
    # QC AD9106 SCH-10: names started 2.65 mm inside the edge on the left but
    # 0.6 mm on the right; top/bottom names (one letter per line) ran into the
    # side columns at the corners. Now one inset everywhere, and the corner
    # clearance leaves room for the longest names on both sides.
    names = ["D5", "D6", "D7", "RXB", "RXA", "TXRDYB", "TXA", "TXB", "OPB", "CSA",
             "CSB", "NC"] * 4
    pins = [{"number": str(i), "name": n} for i, n in enumerate(names, 1)]
    b = PinoutDiagramBuilder("TQFP-48", 48, "PART", pin_data=pins)
    inset = {p.side: round(abs((p.text_x - p.x) if p.side in ("left", "right")
                               else (p.text_y - p.y)), 6) for p in b.pin_positions}
    assert len(set(inset.values())) == 1, inset
    g = b.params.pin_pitch
    cx, cy = b._body_center()
    top = cy + b.params.body_height / 2
    left = cx - b.params.body_width / 2
    first_left = max(p.y for p in b.pin_positions if p.side == "left")
    first_top = min(p.x for p in b.pin_positions if p.side == "top")
    size = b.params.pin_geometry.pin_name_size
    longest = max(len(n) for n in names) * size * 0.6
    assert top - first_left >= inset["top"] + longest   # top names end above pin 1's name
    assert first_top - left >= inset["left"] + longest  # pin 1's name ends left of the top row
