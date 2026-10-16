"""Acceptance test for the Part QC fix list (docs/part-qc-fix-list-2026-10-06.md).

One assertion per FIXED card: the measurable invariant that proves the fix is in
place, so the whole set can be re-verified in a single run and regressions are
caught. Card numbers refer to the Complete Card Inventory in the fix-list doc.

Deliberately uses the cheapest check that proves each fix (unit/builder level,
with GLB inspection only where a fix is a GLB-level change). Fixes whose outcome
is non-deterministic (ADV7180 GPO order #53, which needs a live vision read) are
NOT asserted here -- they fail closed by construction and are covered by mocked
routing tests in test_agentic.py.
"""
import os
import tempfile
from pathlib import Path

import pytest
from pygltflib import GLTF2

from src.schematic_generator.pcb_footprint_builder import PcbFootprintBuilder
from src.package_types.footprint_defaults import get_footprint_defaults
from src.package_types.package_geometry import BodyGeometry
from src.models.pin_classifier import classify_pin_name, detect_active_low
from src.agentic.repair import expand_groups_deterministic
from src.schematic_generator.functional_layout import _order_block


# --- shared GLB builder (built once per package, reused across tests) ----------
_GLB_CACHE: dict = {}


def _footprint_glb(pkg: str, n: int) -> GLTF2:
    if (pkg, n) not in _GLB_CACHE:
        out = str(Path(tempfile.mkdtemp()) / "f.glb")
        b = PcbFootprintBuilder(pkg, n, "U")
        b.save_glb(out, [{"number": i, "name": f"P{i}"} for i in range(1, n + 1)])
        _GLB_CACHE[(pkg, n)] = GLTF2().load(out)
    return _GLB_CACHE[(pkg, n)]


def _node_names(g: GLTF2):
    return [(nd.name or "") for nd in g.nodes]


def _legs_children(g: GLTF2):
    legs = next((i for i, nd in enumerate(g.nodes) if (nd.name or "") == "Legs"), None)
    return list(g.nodes[legs].children or []) if legs is not None else []


def _has_hole(g: GLTF2, pin_idx: int) -> bool:
    kids = [(g.nodes[c].name or "") for c in (g.nodes[pin_idx].children or [])]
    return any("Hole" in k or "Cylinder" in k for k in kids)


# ============================ PACKAGE / MOUNT TYPE ============================
# #20 74LVC1G99 (XSON), #32 AD9106 (LFCSP), #44 693 (unknown->SON): SMD, no holes.
@pytest.mark.parametrize("pkg,n", [("LFCSP-32", 32), ("XSON8", 8), ("QFN-32", 32)])
def test_smd_families_have_no_drilled_holes(pkg, n):
    g = _footprint_glb(pkg, n)
    assert not any(_has_hole(g, p) for p in _legs_children(g)), f"{pkg} has drilled holes (should be SMD)"


def test_through_hole_dip_does_have_holes():
    g = _footprint_glb("PDIP-16", 16)
    assert all(_has_hole(g, p) for p in _legs_children(g)[:16]), "PDIP-16 should be through-hole"


# ============================ SQUARE QUAD PADS (#6) ==========================
def test_square_quad_equal_pad_spans():
    b = PcbFootprintBuilder("TQFP-48", 48, "U")
    vert = [p for p in b.pin_positions if p.side in ("left", "right")]
    horiz = [p for p in b.pin_positions if p.side in ("top", "bottom")]
    assert abs(max(abs(p.x) for p in vert) - max(abs(p.y) for p in horiz)) < 1e-6


# ============================ EXPOSED PAD (#27, #33) =========================
def test_leadless_footprint_has_exposed_pad():
    g = _footprint_glb("QFN-32", 32)
    assert len(_legs_children(g)) == 33, "QFN-32 should have 32 pins + 1 EPAD"


# ============================ PASTE LAYER (#10,#23,#36,#48,#60) ==============
def test_smd_pads_carry_f_paste():
    g = _footprint_glb("QFN-32", 32)
    paste = [nd for nd in g.nodes if (nd.name or "") == "PasteMask"]
    assert paste, "SMD footprint must have PasteMask nodes"
    assert all((nd.extras or {}).get("layerId") == "F.Paste" for nd in paste)


def test_through_hole_pads_have_no_paste():
    g = _footprint_glb("PDIP-16", 16)
    assert not any((nd.name or "") == "PasteMask" for nd in g.nodes), "through-hole pads must not carry paste"


# ============================ PIN ELECTRICAL TYPES (#31,#42,#68) =============
@pytest.mark.parametrize("name,etype", [
    ("CLDO", "power_out"), ("DLDO1", "power_out"),         # AD9106 #31
    ("DAT0", "bidirectional"), ("CMD", "bidirectional"),   # 693 #42
    ("VD+", "power_in"), ("VA-", "power_in"), ("AGNDR", "power_in"),  # PGA2311P #68
    ("FSADJ2", "passive"), ("CAL_SENSE", "passive"),       # AD9106 #31
])
def test_pins_typed_not_unspecified(name, etype):
    assert classify_pin_name(name)[0] == etype, name


def test_classifier_regressions_intact():
    # the bare-SS over-match caught in review must stay fixed
    assert classify_pin_name("SS")[0] is None
    assert classify_pin_name("VSS")[0] == "power_in"
    assert classify_pin_name("VCC")[0] == "power_in"


# ============================ ACTIVE-LOW MARKERS (#2,#28,#55,#66) ============
@pytest.mark.parametrize("name", ["RESET*", "~CS", "CS~", "/CS", "CS#", "RESET_N"])
def test_active_low_detected(name):
    assert detect_active_low(name) is True


@pytest.mark.parametrize("name", ["CS", "RESET", "CLK"])
def test_active_high_not_flagged(name):
    assert detect_active_low(name) is False


# ============================ SOLDER-MASK MARGIN (#14,#24,#37,#49,#62,#73) ===
@pytest.mark.parametrize("pkg,n", [("SOIC-8", 8), ("TQFP-48", 48)])
def test_solder_mask_margin_per_side(pkg, n):
    g = _footprint_glb(pkg, n)
    def xw(nd):
        acc = g.accessors[g.meshes[nd.mesh].primitives[0].attributes.POSITION]
        return acc.max[0] - acc.min[0]
    copper = next(nd for nd in g.nodes if (nd.name or "") == "CopperCirclePad" and nd.mesh is not None)
    mask = next(nd for nd in g.nodes if (nd.name or "") == "SolderMask" and nd.mesh is not None)
    assert round((xw(mask) - xw(copper)) / 2.0, 4) == 0.102


# ============================ PAD-NUMBER FIT (#15,#64) =======================
def test_pad_number_fits_fine_pitch():
    b = PcbFootprintBuilder("TQFP-48", 48, "U")
    assert b._fit_number_size("48", 0.29, 1.3) < 0.29      # fits inside the pad
    assert b._fit_number_size("8", 1.5, 1.5) == 0.8        # large pad unchanged


# ============================ JEDEC MS-026 BODY (#7,#34,#61) =================
@pytest.mark.parametrize("pkg,n,body", [("LQFP-48", 48, 7.0), ("LQFP-64", 64, 10.0), ("TQFP-32", 32, 7.0)])
def test_qfp_body_is_ms026(pkg, n, body):
    d = get_footprint_defaults(pkg, n)
    assert d["E1"] == body and d["D1"] == body


# ============================ XSON SIZING + COURTYARD (#21,#22) ==============
def test_xson_small_body_and_courtyard():
    d = get_footprint_defaults("XSON8", 8)
    assert (d["E"], d["D"]) == (1.0, 1.95)                 # #21 body
    b = PcbFootprintBuilder("XSON8", 8, "U")
    *_, cw, ch = b._layer_half_dims()
    assert 2 * cw < 2.6 and 2 * ch < 2.9                   # #22 courtyard ~2.2x2.5


# ============================ VALUE-TEXT SIZE (#13) ==========================
def test_value_text_size_reduced():
    assert BodyGeometry().value_size == 1.0


# ============================ DIP BODY WIDTH / FP-19 (#69) ===================
def test_dip_body_keeps_true_width():
    b = PcbFootprintBuilder("PDIP-16", 16, "U")
    fab_hw, *_ = b._layer_half_dims()
    assert abs(2 * fab_hw - 6.35) < 0.01                   # true PDIP body, not clamped


# ============================ BUS ORDER (#3) ================================
def test_numbered_bus_drawn_in_bit_order():
    bus = [{"name": "D5-D7", "number": "1"}, {"name": "D5-D7", "number": "2"},
           {"name": "D5-D7", "number": "3"}, {"name": "D0-D4", "number": "44"},
           {"name": "D0-D4", "number": "45"}]
    out = [p["name"] for p in _order_block(bus)]
    assert out == ["D0-D4", "D0-D4", "D5-D7", "D5-D7", "D5-D7"]
    # a mixed-prefix block is NOT reordered (convention, #29/#43)
    mixed = [{"name": "IOUTP4", "number": "1"}, {"name": "FSADJ", "number": "2"}]
    assert [p["name"] for p in _order_block(mixed)] == ["IOUTP4", "FSADJ"]


# ============================ NON-CONTIGUOUS GROUP (#53 half) ================
def test_non_contiguous_group_not_expanded():
    pins = {5: "GPO0 to GPO3", 6: "GPO0 to GPO3", 41: "GPO0 to GPO3", 42: "GPO0 to GPO3"}
    out, _ = expand_groups_deterministic(pins)
    assert out == pins                                     # scattered -> left for the drawing


# ============================ ADV7180 VARIANT TABLE (#52) ====================
def test_adv7180_variant_table_read():
    pdf = "review_pdfs/ADV7180.PDF"
    if not os.path.exists(pdf):
        pytest.skip("ADV7180 datasheet not present")
    from src.pdf_extractor.ordering_table import full_pdf_text
    from src.agentic.repair import read_variant_pin_table
    r = read_variant_pin_table(full_pdf_text(pdf), 48, "LQFP-48")
    assert r is not None, "48-lead variant table should be read"
    assert r.get(24) == "ELPF" and r.get(25) == "PVDD"     # #52 ground truth


def test_variant_table_fails_closed_on_single_variant_parts():
    pdf = "review_pdfs/TL16C2550.PDF"
    if not os.path.exists(pdf):
        pytest.skip("TL16C2550 datasheet not present")
    from src.pdf_extractor.ordering_table import full_pdf_text
    from src.agentic.repair import read_variant_pin_table
    assert read_variant_pin_table(full_pdf_text(pdf), 48, "TQFP-48") is None
