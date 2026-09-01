"""FP-19 / QC T-2D-2: the fab (yellow/body) outline never crosses a copper pad.

Root-cause fix (option B): the fab/body outline is sourced from the real molded
body E1/D1 as the PRIMARY dimension (never the lead span E), with body-based
E1/D1 now published for the leadless families too. The pad-clearance clamp is a
LAST-RESORT constraint: it engages only when the true body would actually cross
a pad, and leaves a body that already fits inside the pad ring at its real size.
FP-19 guards the invariant permanently.
"""
import tempfile
from pathlib import Path

from src.schematic_generator import build_pcb_2d_schematic
from src.schematic_generator.pcb_footprint_builder import PcbFootprintBuilder
from src.package_types.footprint_defaults import get_footprint_defaults
from src.conformance.checks import check_fab_pad_clearance, PartContext
from src.conformance.model import CheckStatus


def _footprint(pkg, n, dims=None) -> str:
    out = str(Path(tempfile.mkdtemp()) / "f.glb")
    ok = build_pcb_2d_schematic(package_type=pkg, pin_count=n, component_name="X",
                                pin_data=[{"number": str(i), "name": f"P{i}"} for i in range(1, n + 1)],
                                output_path=out, extracted_dims=dims)
    assert ok and Path(out).is_file()
    return out


# Leaded, leadless, quad, and through-hole all used to cross before the clamp.
FAMILIES = [("SOIC-8", 8), ("WSON-8", 8), ("DFN-8", 8), ("SON-8", 8),
            ("TSSOP-20", 20), ("LQFP-48", 48), ("DIP-8", 8)]


def test_fab_clears_pads_across_families():
    for pkg, n in FAMILIES:
        outcome = check_fab_pad_clearance(PartContext("x", {"footprint": _footprint(pkg, n)}))
        assert outcome.status is CheckStatus.PASS, (pkg, outcome.message)


def test_fab_clears_pads_with_extracted_dims():
    dims = {"e": 1.27, "E": 10.325, "D": 9.90, "b": 0.41, "L": 0.835}  # 74HC595 SOIC-16
    outcome = check_fab_pad_clearance(PartContext("x", {"footprint": _footprint("SOIC-16", 16, dims)}))
    assert outcome.status is CheckStatus.PASS, outcome.message


def test_fp19_skips_without_footprint():
    assert check_fab_pad_clearance(PartContext("x", {})).status is CheckStatus.SKIP


# --- option B: E1/D1 is the primary source, clamp is last-resort -------------
def test_leadless_families_publish_body_e1_d1():
    # The leadless families used to have no E1/D1, so the fab outline fell back
    # to the terminal span. They now carry body-based E1/D1 (E1 == E, D1 == D).
    for fam, n in (("WSON-8", 8), ("DFN-8", 8), ("SON-8", 8), ("QFN-32", 32)):
        d = get_footprint_defaults(fam, n)
        assert d.get("E1") and d.get("D1"), (fam, d)
        assert d["E1"] == d["E"] and d["D1"] == d["D"], (fam, d)


def test_fab_outline_comes_from_e1_not_lead_span():
    # E (lead span) = 6.0 but the real body E1 = 3.9: the drawn fab half-width
    # must derive from E1 (<= E1/2), never from the lead span E/2 = 3.0.
    b = PcbFootprintBuilder("SOIC-8", 8, "IC")
    fab_hw, *_ = b._layer_half_dims()
    assert fab_hw <= b.fab_outline_width / 2 + 1e-9        # from body, possibly inset
    assert fab_hw < b.params.body_width / 2                # never the lead span


def test_clamp_is_last_resort_body_that_fits_is_not_shrunk():
    # A small molded body (extracted E1 = 2.0) sits well inside the pad ring, so
    # the last-resort clamp must NOT engage: the outline keeps its true E1/2.
    dims = {"e": 1.27, "E": 6.0, "E1": 2.0, "D": 4.9, "b": 0.41, "L": 0.84}
    b = PcbFootprintBuilder("SOIC-8", 8, "IC", extracted_dims=dims)
    fab_hw, *_ = b._layer_half_dims()
    assert abs(fab_hw - b.fab_outline_width / 2) < 1e-9    # unclamped == real body
    assert abs(fab_hw - 1.0) < 1e-9


def test_leadless_fab_clears_pads_and_stays_off_lead_span():
    # Leadless body sits over its own terminals -> clamp engages, FP-19 passes.
    out = _footprint("WSON-8", 8)
    assert check_fab_pad_clearance(PartContext("x", {"footprint": out})).status is CheckStatus.PASS
