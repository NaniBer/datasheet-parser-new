"""Square quad packages get a square pad ring, fab and courtyard.

Regression for TL16C2550 FP-01 (P0-2) and the P2-1/P2-2 geometry cards:
a square QFP/QFN has D == E, but the extractor can read D as the molded body
while E is the full lead span, so the top/bottom pad rows landed on a smaller
span than left/right and 24 of 48 pads fell ~1 mm short of their leads. The
builder must snap both axes to the same (true lead-span) distance, and the fab
and courtyard that follow the pads must come out square too.
"""

import pytest

from src.schematic_generator.pcb_footprint_builder import PcbFootprintBuilder

# A square TQFP-48 (7x7 body, 9x9 lead span) whose extraction mixed the body
# dimension into the D (span) axis: E = 9.0 lead span, D = 7.0 body.
ASYM = {"e": 0.5, "E": 9.0, "D": 7.0, "b": 0.22, "L": 0.6}


def _spans(b):
    lr = max(abs(p.x) for p in b.pin_positions if p.side in ("left", "right"))
    tb = max(abs(p.y) for p in b.pin_positions if p.side in ("top", "bottom"))
    return lr, tb


def test_square_quad_pad_rows_equal_on_both_axes():
    b = PcbFootprintBuilder("TQFP-48", 48, "TL16C2550", extracted_dims=ASYM)
    lr, tb = _spans(b)
    assert lr == pytest.approx(tb), f"square package must have equal spans: {lr} vs {tb}"


def test_square_quad_recovers_the_larger_lead_span():
    # The misread (smaller) D axis must move OUT to the real E lead span, never
    # the other way round — pads reaching their leads is the safe direction.
    b = PcbFootprintBuilder("TQFP-48", 48, "TL16C2550", extracted_dims=ASYM)
    lr, tb = _spans(b)
    # Left/right were correct at E/2 - L/2 = 4.5 - 0.3 = 4.2.
    assert lr == pytest.approx(4.2, abs=0.01)
    assert tb == pytest.approx(4.2, abs=0.01)


def test_square_quad_pad_extents_fab_and_courtyard_are_square():
    b = PcbFootprintBuilder("TQFP-48", 48, "TL16C2550", extracted_dims=ASYM)
    pad_x, pad_y = b._pad_extents()
    assert pad_x == pytest.approx(pad_y)
    fab_hw, fab_hh, _, _, crtyd_hw, crtyd_hh = b._layer_half_dims()
    assert fab_hw == pytest.approx(fab_hh), "square body must draw a square fab outline"
    assert crtyd_hw == pytest.approx(crtyd_hh), "square body must draw a square courtyard"


def test_square_quad_courtyard_is_pad_extent_plus_margin():
    # P2-2: courtyard = outermost pad reach + 0.25 mm (no double clearance).
    b = PcbFootprintBuilder("TQFP-48", 48, "TL16C2550", extracted_dims=ASYM)
    pad_x, pad_y = b._pad_extents()
    _, _, _, _, crtyd_hw, crtyd_hh = b._layer_half_dims()
    assert crtyd_hw == pytest.approx(max(pad_x, pad_y) + b.CRTYD_MARGIN_Y, abs=1e-6)
    assert crtyd_hh == pytest.approx(max(pad_x, pad_y) + b.CRTYD_MARGIN_Y, abs=1e-6)


def test_qfn_courtyard_encloses_silk_without_double_margin():
    # AD9106 QFN-32 (square 5x5) came out 6.5 x 7.2: the silk-relocation path
    # added a second full clearance on the silk axis only. It must now enclose
    # the silk tightly and stay square.
    b = PcbFootprintBuilder("QFN-32", 32, "AD9106")
    _, _, silk_hw, silk_hh, crtyd_hw, crtyd_hh = b._layer_half_dims()
    assert crtyd_hw == pytest.approx(crtyd_hh), "square QFN courtyard must be square"
    assert crtyd_hh >= silk_hh + b.LINE_THICKNESS / 2            # encloses the silk
    # No second full margin beyond the silk edge (the old bug added +0.25 here).
    assert crtyd_hh < silk_hh + b.LINE_THICKNESS / 2 + b.CRTYD_MARGIN_Y


def test_rectangular_quad_is_not_squared():
    # A genuinely rectangular quad package (unequal pins per axis) must keep its
    # different spans — squaring would misplace the longer axis' pads.
    cl = {
        "left_side": [1, 2, 3, 4, 5, 6, 7, 8],
        "bottom_edge": [9, 10, 11, 12],
        "right_side": [13, 14, 15, 16, 17, 18, 19, 20],
        "top_edge": [21, 22, 23, 24],
    }
    b = PcbFootprintBuilder("LQFP-24", 24, "RECT", custom_layout=cl,
                            extracted_dims={"e": 0.5, "E": 9.0, "D": 5.0,
                                            "b": 0.22, "L": 0.6})
    assert b.is_square_quad() is False
    lr, tb = _spans(b)
    assert lr != pytest.approx(tb), "rectangular quad must keep asymmetric spans"


def test_dual_row_package_is_untouched():
    b = PcbFootprintBuilder("SOIC-16", 16, "X")
    assert b.is_square_quad() is False
    # No top/bottom pads at all; squaring must be a no-op.
    assert not any(p.side in ("top", "bottom") for p in b.pin_positions)


def test_already_square_extraction_is_idempotent():
    # When E == D the ring is already square; squaring must not move anything.
    sym = {"e": 0.5, "E": 9.0, "D": 9.0, "b": 0.22, "L": 0.6}
    b = PcbFootprintBuilder("TQFP-48", 48, "X", extracted_dims=sym)
    lr, tb = _spans(b)
    assert lr == pytest.approx(tb)
    assert lr == pytest.approx(4.2, abs=0.01)
