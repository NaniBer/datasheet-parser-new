"""Slice C: SYM-05 power/ground pins visible (pure check, no generation change)."""
import tempfile
from pathlib import Path

from src.schematic_generator.adapter import build_schematic_from_pin_data
from src.models import ComponentRecord
from src.models.pin_data import PinData, PackageInfo, Pin
from src.conformance.checks import check_power_ground_visible, PartContext
from src.conformance.model import CheckStatus


def _build(pd: PinData) -> str:
    out = str(Path(tempfile.mkdtemp()) / "s.glb")
    build_schematic_from_pin_data(pin_data=pd, output_path=out,
                                  record=ComponentRecord.from_pin_data(pd))
    return out


def test_power_and_ground_present_passes():
    pd = PinData(
        component_name="X",
        package=PackageInfo(type="SOIC-8", pin_count=8, width=0, height=0),
        pins=[Pin(1, "VCC", role="supply"), Pin(2, "GND", role="ground")]
             + [Pin(i, f"IO{i}", role="io") for i in range(3, 9)],
    )
    outcome = check_power_ground_visible(PartContext("x", {"symbol": _build(pd)}))
    assert outcome.status is CheckStatus.PASS


def test_no_power_ground_skips():
    # role-less generic pins: nothing power/ground to grade -> SKIP (not FAIL)
    pd = PinData(
        component_name="X",
        package=PackageInfo(type="SOIC-8", pin_count=8, width=0, height=0),
        pins=[Pin(i, f"P{i}") for i in range(1, 9)],
    )
    outcome = check_power_ground_visible(PartContext("x", {"symbol": _build(pd)}))
    assert outcome.status is CheckStatus.SKIP
