"""FP-17: footprint records the component Z height (stamp + check)."""
import tempfile
from pathlib import Path

from src.schematic_generator import build_pcb_2d_schematic
from src.conformance.checks import check_component_height_present, PartContext
from src.conformance.model import CheckStatus


def _build_footprint(package_type="SOIC-8", pin_count=8) -> str:
    out = str(Path(tempfile.mkdtemp()) / "x_footprint.glb")
    pins = [{"number": str(i), "name": f"P{i}"} for i in range(1, pin_count + 1)]
    ok = build_pcb_2d_schematic(package_type=package_type, pin_count=pin_count,
                                component_name="X", pin_data=pins, output_path=out)
    assert ok and Path(out).is_file()
    return out


def test_fp17_height_recorded_passes():
    outcome = check_component_height_present(PartContext("x", {"footprint": _build_footprint()}))
    assert outcome.status is CheckStatus.PASS
    assert outcome.measured.endswith("mm")


def test_fp17_height_positive_for_through_hole():
    outcome = check_component_height_present(
        PartContext("x", {"footprint": _build_footprint("DIP-8", 8)}))
    assert outcome.status is CheckStatus.PASS


def test_fp17_skips_without_footprint():
    outcome = check_component_height_present(PartContext("x", {}))
    assert outcome.status is CheckStatus.SKIP
