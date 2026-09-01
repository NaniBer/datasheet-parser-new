"""FP-19 / QC T-2D-2: the fab (yellow/body) outline never crosses a copper pad.

Root-cause fix: the fab/body outline is clamped inside the innermost pad edge
(so it can't span the full lead-tip width and land on the pads) + the guard.
"""
import tempfile
from pathlib import Path

from src.schematic_generator import build_pcb_2d_schematic
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
