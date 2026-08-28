"""Slice C: SYM-01 layout not physical order (gated delegate of SYM-04)."""
import tempfile
from pathlib import Path

from src.schematic_generator.adapter import build_schematic_from_pin_data
from src.models import ComponentRecord
from src.models.pin_data import PinData, PackageInfo, Pin
from src.conformance.checks import check_layout_not_physical, PartContext
from src.conformance.model import CheckStatus


def _build(pd: PinData) -> str:
    out = str(Path(tempfile.mkdtemp()) / "s.glb")
    build_schematic_from_pin_data(pin_data=pd, output_path=out,
                                  record=ComponentRecord.from_pin_data(pd))
    return out


def _gated_pd() -> PinData:
    # concrete supply + ground + 100% concrete roles -> clears the gate
    return PinData(
        component_name="X",
        package=PackageInfo(type="SOIC-8", pin_count=8, width=0, height=0),
        pins=[Pin(1, "CLK", role="clock"), Pin(2, "RST", role="reset"),
              Pin(3, "IN0", role="input"), Pin(4, "GND", role="ground"),
              Pin(5, "OUT0", role="output"), Pin(6, "OUT1", role="output"),
              Pin(7, "IO0", role="io"), Pin(8, "VCC", role="supply")],
    )


def test_gated_functional_layout_not_physical_passes():
    outcome = check_layout_not_physical(PartContext("x", {"symbol": _build(_gated_pd())}))
    assert outcome.status is CheckStatus.PASS


def test_below_gate_skips():
    # role-less physical layout is expected and correct -> SKIP (never faulted)
    pd = PinData(
        component_name="X",
        package=PackageInfo(type="SOIC-8", pin_count=8, width=0, height=0),
        pins=[Pin(i, f"P{i}") for i in range(1, 9)],
    )
    outcome = check_layout_not_physical(PartContext("x", {"symbol": _build(pd)}))
    assert outcome.status is CheckStatus.SKIP
