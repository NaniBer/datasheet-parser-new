"""FP-18: footprint declares a pick-and-place zero orientation (stamp + check)."""
import tempfile
from pathlib import Path

from src.schematic_generator import build_pcb_2d_schematic
from src.conformance.checks import check_pnp_zero_orientation, PartContext
from src.conformance.model import CheckStatus


def _build_footprint(package_type="SOIC-8", pin_count=8) -> str:
    out = str(Path(tempfile.mkdtemp()) / "x_footprint.glb")
    pins = [{"number": str(i), "name": f"P{i}"} for i in range(1, pin_count + 1)]
    ok = build_pcb_2d_schematic(package_type=package_type, pin_count=pin_count,
                                component_name="X", pin_data=pins, output_path=out)
    assert ok and Path(out).is_file()
    return out


def test_fp18_zero_orientation_present_passes():
    outcome = check_pnp_zero_orientation(PartContext("x", {"footprint": _build_footprint()}))
    assert outcome.status is CheckStatus.PASS
    assert outcome.measured == "0 deg"


def test_fp18_skips_without_footprint():
    outcome = check_pnp_zero_orientation(PartContext("x", {}))
    assert outcome.status is CheckStatus.SKIP
