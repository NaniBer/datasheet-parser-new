"""P1-1: solder-paste apertures are a dedicated F.Paste layer, SMD-only.

CadQuery emits only copper + mask geometry, so no paste node existed at all: the
stencil exported empty and layer views drew the pads as bare copper. The extras
injector now adds one ``PasteMask`` node (layer ``F.Paste``) per SMD pad, derived
from the copper land. Through-hole pads (which have a drilled barrel) get none.
"""

import tempfile
from pathlib import Path

import pytest
from pygltflib import GLTF2

from src.core.pcb_footprint_extras import _footprint_layer_id
from src.core.pcb_footprint_hierarchy import validate_pcb_footprint_glb
from src.schematic_generator.pcb_footprint_builder import PcbFootprintBuilder


def _build(pkg: str, n: int, component: str = "U") -> str:
    out = str(Path(tempfile.mkdtemp()) / "fp.glb")
    b = PcbFootprintBuilder(pkg, n, component)
    pins = [{"number": i, "name": f"P{i}"} for i in range(1, n + 1)]
    assert b.save_glb(out, pins), "save_glb failed (hierarchy validation?)"
    return out


def _children(g: GLTF2, idx: int):
    return [(g.nodes[c].name, (g.nodes[c].extras or {}).get("layerId"))
            for c in (g.nodes[idx].children or [])]


def _legs(g: GLTF2) -> int:
    return next(i for i, nd in enumerate(g.nodes) if nd.name == "Legs")


def test_footprint_layer_id_maps_pastemask_to_f_paste():
    # Unit-level: the paste node is named + layered independently of copper.
    assert _footprint_layer_id("PasteMask", "1") == "F.Paste"
    assert _footprint_layer_id("CopperCirclePad", "1") == "F.Cu"


@pytest.mark.parametrize("pkg,n", [("SOIC-8", 8), ("TQFP-48", 48)])
def test_smd_pad_has_exactly_one_f_paste_aperture(pkg, n):
    g = GLTF2().load_binary(_build(pkg, n))
    legs = _legs(g)
    for pin_idx in g.nodes[legs].children or []:
        kids = _children(g, pin_idx)
        names = [name for name, _ in kids]
        # Exactly one paste aperture per pad, tagged F.Paste, after the copper.
        assert names.count("PasteMask") == 1, names
        paste_layer = next(lid for name, lid in kids if name == "PasteMask")
        assert paste_layer == "F.Paste"
        assert names.index("PasteMask") == names.index("CopperCirclePad") + 1
        # And it must NOT be mis-tagged as copper.
        assert ("PasteMask", "F.Cu") not in kids


def test_smd_has_one_paste_node_per_pad_globally():
    g = GLTF2().load_binary(_build("SOIC-8", 8))
    paste = [nd for nd in g.nodes if nd.name == "PasteMask"]
    assert len(paste) == 8
    assert {(nd.extras or {}).get("layerId") for nd in paste} == {"F.Paste"}


@pytest.mark.parametrize("pkg,n", [("DIP-8", 8), ("PDIP-16", 16)])
def test_through_hole_pads_have_no_paste(pkg, n):
    g = GLTF2().load_binary(_build(pkg, n))
    assert [nd for nd in g.nodes if nd.name == "PasteMask"] == []
    legs = _legs(g)
    for pin_idx in g.nodes[legs].children or []:
        names = [name for name, _ in _children(g, pin_idx)]
        assert "PasteMask" not in names


def test_qfn_exposed_pad_also_gets_paste_and_validates():
    # FP-02 exposed pad is an SMD-style land, so it carries paste too; the whole
    # footprint must still pass hierarchy validation with paste present.
    out = _build("QFN-48", 48)
    ok, errors = validate_pcb_footprint_glb(
        out, pin_count=48, through_hole=False, exposed_pad=True
    )
    assert ok, errors
    g = GLTF2().load_binary(out)
    # 48 perimeter + 1 exposed = 49 paste apertures.
    assert len([nd for nd in g.nodes if nd.name == "PasteMask"]) == 49


def test_through_hole_footprint_validates_without_paste():
    out = _build("DIP-8", 8)
    ok, errors = validate_pcb_footprint_glb(out, pin_count=8, through_hole=True)
    assert ok, errors
