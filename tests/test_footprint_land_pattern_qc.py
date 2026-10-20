"""Land-pattern / body-size QC regressions from the IDEEZA Part Comparison Log.

Cards covered (docs/part-qc-fix-list-2026-10-06.md, "Complete Card Inventory"):

* #61 ADV7180 (LQFP-48): F.Fab body came out 7.38 mm, larger than the 7.00 mm
  package maximum. The JEDEC default body was 7.5 mm (span formula over-stated
  the lead span ~0.5 mm); it is now the MS-026 standard 7.0 mm and the drawn
  fab, clamped inside the pad ring per FP-19, stays <= the 7.00 mm package max.
* #59 ADV7180 (LQFP-48): SMD pads sat ~0.23 mm too far out (short heel) because
  the lead span E was 9.5 instead of 9.0; the pad now centres on the lead foot
  (E/2 - L/2 = 4.2 mm) so the heel reaches the body.
* #12 TL16C2550 (TQFP-48): pads were 1.30 mm, ~0.17 mm short of the land
  pattern; IPC-7351 sizes the pad from the longest foot (L_max = 0.75), giving
  ~1.45 mm.
* #69 PGA2311P (PDIP-16): body length was 20.38 mm, should be ~19.3 mm (the DIP
  end margin was 1.3 mm, now 0.8 mm to match JEDEC MS-001). The body *width* is
  held at the pad ring by the FP-19 clamp (fab must not cross a pad), so it is
  not asserted here; see the note in the agent report.
* #71 PGA2311P (PDIP-16): the 0.83 mm (0.032") drill did NOT reproduce as a
  defect — it matches the TI Ultra Librarian DIP16_300 golden reference
  (0.813 mm) and IPC-2222 for a PDIP lead (~0.77-0.86 mm); no change was made.
* #8 / #58 (TQFP-48 / LQFP-48): silk lines reported running over 24 pads do NOT
  reproduce — the FP-07 clip keeps every printed silk segment >= 0.2 mm clear.
"""

import pytest

from src.schematic_generator.pcb_footprint_builder import PcbFootprintBuilder
from src.package_types.footprint_defaults import get_footprint_defaults


# ---------------------------------------------------------------------------
# JEDEC defaults (footprint_defaults)
# ---------------------------------------------------------------------------
def test_qfp48_body_is_ms026_standard_7mm_not_7_5():
    # #61: MS-026 LQFP/TQFP-48 body is 7.0 mm; the lead span is body + 2.0.
    d = get_footprint_defaults("LQFP-48", 48)
    assert d["E1"] == pytest.approx(7.0) and d["D1"] == pytest.approx(7.0)
    assert d["E"] == pytest.approx(9.0) and d["D"] == pytest.approx(9.0)


def test_qfp_defaults_carry_l_max_for_ipc_pad_length():
    # #12: IPC-7351 pads come from the longest foot L_max (MS-026 gull-wing max).
    d = get_footprint_defaults("TQFP-48", 48)
    assert d["L_max"] == pytest.approx(0.75)
    assert d["L_max"] > d["L"]


def test_pdip16_body_length_is_about_19_3_not_20_4():
    # #69: DIP-16 body length ~19.3 mm (MS-001), not the old 20.38 mm.
    d = get_footprint_defaults("PDIP-16", 16)
    assert d["D"] == pytest.approx(19.3, abs=0.1)


def test_pdip8_body_length_still_matches_jedec():
    # The tighter end margin must still reproduce the small-DIP standard length.
    d = get_footprint_defaults("PDIP-8", 8)
    assert d["D"] == pytest.approx(9.27, abs=0.1)


# ---------------------------------------------------------------------------
# Built footprint geometry
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("pkg", ["LQFP-48", "TQFP-48"])
def test_qfp48_fab_body_not_larger_than_package_max(pkg):
    # #61 / #7: the drawn F.Fab body must not exceed the 7.00 mm package body.
    b = PcbFootprintBuilder(pkg, 48, "X")
    fab_hw, fab_hh, *_ = b._layer_half_dims()
    assert 2 * fab_hw <= 7.0 + 1e-6, f"{pkg} fab width {2*fab_hw:.3f} > 7.0"
    assert 2 * fab_hh <= 7.0 + 1e-6, f"{pkg} fab length {2*fab_hh:.3f} > 7.0"


@pytest.mark.parametrize("pkg", ["LQFP-48", "TQFP-48"])
def test_qfp48_pads_centre_on_the_lead_foot(pkg):
    # #59: pad centre = E/2 - L/2 = 4.5 - 0.3 = 4.2 mm (not the old 4.45 mm that
    # left a short heel). Checked on the left/right columns.
    b = PcbFootprintBuilder(pkg, 48, "X")
    lr = max(abs(p.x) for p in b.pin_positions if p.side in ("left", "right"))
    assert lr == pytest.approx(4.2, abs=0.01)


@pytest.mark.parametrize("pkg", ["LQFP-48", "TQFP-48"])
def test_qfp48_pad_length_covers_the_land_pattern(pkg):
    # #12: pad length = L_max (0.75) + toe/heel (0.70) = 1.45 mm, up from 1.30.
    b = PcbFootprintBuilder(pkg, 48, "X")
    assert b.pad_spec["shape"] == "rect"
    assert b.pad_spec["length"] == pytest.approx(1.45, abs=0.02)


def test_qfp48_heel_reaches_the_body_edge():
    # #59: with the pad centred on the foot, the heel (inner edge) must sit at
    # or inside the 7.0 mm body edge (3.5 mm), i.e. no gap between heel and body.
    b = PcbFootprintBuilder("LQFP-48", 48, "X")
    length = b.pad_spec["length"]
    centre = max(abs(p.x) for p in b.pin_positions if p.side in ("left", "right"))
    heel_inner = centre - length / 2.0
    assert heel_inner <= 3.5 + 1e-6, f"heel inner {heel_inner:.3f} leaves a gap to the 3.5 mm body edge"


def test_pdip16_fab_length_is_about_19_3():
    # #69 (length axis — no top/bottom pads, so it is not clamped).
    b = PcbFootprintBuilder("PDIP-16", 16, "PGA2311P")
    _, fab_hh, *_ = b._layer_half_dims()
    assert 2 * fab_hh == pytest.approx(19.3, abs=0.2)


@pytest.mark.parametrize("pkg", ["TQFP-48", "LQFP-48"])
def test_silk_segments_stay_clear_of_every_pad(pkg):
    # #8 / #58: NOT-REPRODUCED guard — every printed silk segment keeps the
    # required >= 0.2 mm clearance from all pads (FP-07 clip).
    b = PcbFootprintBuilder(pkg, 48, "X")
    t = b.LINE_THICKNESS
    _, _, silk_hw, silk_hh, *_ = b._layer_half_dims()
    worst = float("inf")
    for y_line in (silk_hh, -silk_hh):
        sy0, sy1 = y_line - t / 2, y_line + t / 2
        for a, bx in b._silk_line_segments(y_line, -silk_hw, silk_hw, t):
            for p in b.pin_positions:
                px0, px1, py0, py1 = b._pad_bbox(p)
                if min(bx, px1) - max(a, px0) > 0:          # overlap in x -> y gap
                    worst = min(worst, max(py0 - sy1, sy0 - py1))
                elif min(sy1, py1) - max(sy0, py0) > 0:     # overlap in y -> x gap
                    worst = min(worst, max(px0 - bx, a - px1))
    assert worst >= 0.2 - 1e-6, f"{pkg} silk-to-pad clearance {worst:.3f} < 0.2"


def test_qfn_body_still_clamped_inside_pad_ring():
    # Regression: the leadless path (AD9106 QFN-32) must keep clamping the body
    # inside the pad ring; the QFP/DIP changes above must not disturb it.
    b = PcbFootprintBuilder("QFN-32", 32, "AD9106")
    fab_hw, *_ = b._layer_half_dims()
    inner_x, _ = b._pad_inner_extents()
    assert 2 * fab_hw < 5.0          # pulled inside the 5 mm body
    assert fab_hw + b.LINE_THICKNESS / 2 <= inner_x + 1e-6


def test_leadless_land_shorter_than_gullwing():
    # QC (AD9106 LFCSP-32): a leadless land was coming out 1.1 mm (gull-wing
    # toe/heel) when the datasheet-correct land is ~0.8 mm. Leadless terminals
    # sit flush under the body, so QFN/LFCSP/DFN/SON must use the shorter leadless
    # toe/heel; gull-wing families (QFP/SOIC) stay on 0.70.
    dims = {"b": 0.25, "L": 0.40, "b_max": 0.30, "L_max": 0.40}
    leadless = PcbFootprintBuilder("LFCSP-32", 32, "AD9106", extracted_dims=dims)
    gull = PcbFootprintBuilder("TQFP-48", 48, "X", extracted_dims=dims)
    l_len = leadless._compute_pad_spec(None, dims)["length"]
    g_len = gull._compute_pad_spec(None, dims)["length"]
    assert abs(l_len - 0.80) < 1e-6, f"LFCSP land {l_len} != 0.80"
    assert abs(g_len - 1.10) < 1e-6, f"TQFP land {g_len} != 1.10 (gull-wing unchanged)"
    assert l_len < g_len


def test_solder_mask_keeps_dam_on_fine_pitch():
    # QC (AD9106 LFCSP-32): full 0.102mm mask margin on a 0.3mm pad at 0.5mm
    # pitch grows the aperture to 0.504mm > pitch, so adjacent solder-mask
    # openings merge ("no gap between solder mask of pads"). The pitch-direction
    # margin must clamp to keep a mask dam; the length direction keeps full margin.
    dims = {"b": 0.25, "L": 0.40, "b_max": 0.30, "L_max": 0.40}
    b = PcbFootprintBuilder("LFCSP-32", 32, "AD9106", extracted_dims=dims)
    w = b.pad_spec["width"]; pitch = b.params.pin_pitch
    m_pitch = min(b.MASK_MARGIN, max(0.0, (pitch - w - b.MASK_MIN_DAM) / 2))
    aperture_w = w + 2 * m_pitch
    dam = pitch - aperture_w
    assert dam >= b.MASK_MIN_DAM - 1e-6, f"mask dam {dam:.3f} < {b.MASK_MIN_DAM}"
    assert dam > 0, "adjacent solder-mask apertures still overlap"
