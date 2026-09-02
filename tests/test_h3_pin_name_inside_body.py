"""QC H3 / SYM-13: pin NAME text must be drawn inside the body outline.

On a functionally-laid-out (gated) symbol every pin name belongs inside the
body box, never out on the pin leg. This mirrors test_slice_c_sym04_geometry's
fixture-building: a gated part (supply + ground + concrete roles) is built via
``build_schematic_from_pin_data`` so functional grouping — and therefore the
name-inside-body expectation — applies. A below-gate part (no roles) must SKIP,
because its legacy physical layout legitimately draws names outside the body.
"""
import tempfile
from pathlib import Path

from src.schematic_generator.adapter import build_schematic_from_pin_data
from src.models import ComponentRecord
from src.models.pin_data import PinData, PackageInfo, Pin
from src.conformance.checks import check_pin_name_inside_body, PartContext
from src.conformance.model import CheckStatus


def _build(pd: PinData) -> str:
    out = str(Path(tempfile.mkdtemp()) / "s.glb")
    build_schematic_from_pin_data(pin_data=pd, output_path=out,
                                  record=ComponentRecord.from_pin_data(pd))
    return out


def _gated_pd() -> PinData:
    # Supply + ground + >=50% concrete roles -> clears the functional-layout gate.
    return PinData(
        component_name="X",
        package=PackageInfo(type="DIP-6", pin_count=6, width=0, height=0),
        pins=[Pin(1, "VCC", role="supply"), Pin(2, "GND", role="ground"),
              Pin(3, "CLK", role="clock"), Pin(4, "RST", role="reset"),
              Pin(5, "OUT", role="output"), Pin(6, "IO0", role="io")],
    )


def _ungated_pd() -> PinData:
    # No roles -> gate fails -> physical layout -> the rule does not apply.
    return PinData(
        component_name="P",
        package=PackageInfo(type="DIP-8", pin_count=8, width=0, height=0),
        pins=[Pin(i, f"P{i}") for i in range(1, 9)],
    )


def test_gated_pin_names_inside_body_outline():
    """Gated part: every pin name sits inside the body outline -> PASS.

    (Requires the geometry fix that moves names inward; with it in place the
    check passes, with names still on the leg it FAILs cleanly.)
    """
    glb = _build(_gated_pd())
    ctx = PartContext("gated", {"symbol": glb})
    outcome = check_pin_name_inside_body(ctx)
    assert outcome.status is CheckStatus.PASS, outcome.message


def test_below_gate_physical_part_also_inside():
    """Below-gate (physical dual-row) parts now draw names inside too -> PASS.

    The universal body sizing (QC H3/S2) fits names inside the body for every
    symbol, not just functionally-grouped ones, so SYM-13 grades the physical
    layout as well and it passes.
    """
    glb = _build(_ungated_pd())
    ctx = PartContext("ungated", {"symbol": glb})
    outcome = check_pin_name_inside_body(ctx)
    assert outcome.status is CheckStatus.PASS, outcome.message


def test_no_symbol_artifact_skips():
    """No symbol artifact present -> SKIP, never an error."""
    ctx = PartContext("none", {})
    outcome = check_pin_name_inside_body(ctx)
    assert outcome.status is CheckStatus.SKIP, outcome.message
