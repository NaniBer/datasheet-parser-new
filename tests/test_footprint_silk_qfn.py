"""Silk outline on quad leadless packages.

On QFN parts the fab outline is clamped inside the pad ring, so the silk lines at
fab_hh + margin run through the top/bottom pad rows; FP-07 clipping then left
no segment and the footprint failed hierarchy validation
("silk_layer has no BodyLine segments"). FT813Q-T (VQFN-56) and TLE9278BQXX
(PG-VQFN-48) both died this way in production. The silk must move outside the
pad tips in that case, and the courtyard must stay outside the silk.
"""

import pytest

from src.core.pcb_footprint_hierarchy import validate_pcb_footprint_glb
from src.schematic_generator.pcb_footprint_builder import PcbFootprintBuilder


def _silk_segments(b):
    body = b.build_body()
    silk = next(c for c in body.children if c.name == "silk_layer")
    return len(silk.children)


@pytest.mark.parametrize("pkg,n", [("QFN-16", 16), ("QFN-48", 48), ("QFN-56", 56)])
def test_qfn_silk_is_never_empty_and_sits_outside_the_pads(pkg, n):
    b = PcbFootprintBuilder(pkg, n, "X")
    fab_hw, fab_hh, silk_hw, silk_hh, crtyd_hw, crtyd_hh = b._layer_half_dims()
    pad_x, pad_y = b._pad_extents()
    assert _silk_segments(b) >= 2
    assert silk_hh > pad_y + b.SILK_PAD_CLEARANCE          # clear of the pad tips (FP-07)
    assert crtyd_hh >= silk_hh + b.LINE_THICKNESS / 2      # courtyard encloses the silk
    assert silk_hw >= pad_x                                # spans the pad row


@pytest.mark.parametrize("pkg,n,segments", [("LQFP-64", 64, 4), ("TQFP-48", 48, 4), ("SOIC-16", 16, 2)])
def test_leaded_packages_keep_their_original_silk(pkg, n, segments):
    b = PcbFootprintBuilder(pkg, n, "X")
    fab_hw, fab_hh, silk_hw, silk_hh, crtyd_hw, crtyd_hh = b._layer_half_dims()
    assert _silk_segments(b) == segments
    assert silk_hh == pytest.approx(fab_hh + b.SILK_MARGIN_Y)   # unchanged geometry
    pad_x, pad_y = b._pad_extents()
    assert crtyd_hh == pytest.approx(max(fab_hh, pad_y) + b.CRTYD_MARGIN_Y)


def test_qfn48_footprint_glb_passes_hierarchy_validation(tmp_path):
    # FP-02: a QFN carries a central exposed thermal pad, so it has one extra
    # Legs child (pin 49) and must validate with exposed_pad=True.
    b = PcbFootprintBuilder("QFN-48", 48, "U")
    assert b._has_exposed_pad
    pins = [{"number": i, "name": f"P{i}"} for i in range(1, 49)]
    out = tmp_path / "qfn48_footprint.glb"
    assert b.save_glb(str(out), pins)
    ok, errors = validate_pcb_footprint_glb(
        str(out), pin_count=48, through_hole=False, exposed_pad=True
    )
    assert ok, errors


def test_dip_has_no_exposed_pad():
    # Leaded / through-hole parts must NOT get an exposed pad.
    assert not PcbFootprintBuilder("DIP-8", 8, "U")._has_exposed_pad
    assert not PcbFootprintBuilder("SOIC-8", 8, "U")._has_exposed_pad
