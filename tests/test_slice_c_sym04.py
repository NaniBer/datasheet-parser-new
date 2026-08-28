"""Slice C sub-step 4a: SYM-04 functional-grouping metadata + gate.

4a is the INERT half of SYM-04: it writes the ``role`` GLB extra and wires the
conformance check, but changes NO geometry. So on the current physical layout
the check is expected to FAIL for parts that clear the coverage gate (grouping
is not applied yet) and SKIP for below-gate/legacy parts. 4b flips the gated
parts to PASS by actually laying pins out by function.
"""
import tempfile
from pathlib import Path

from pygltflib import GLTF2

from src.schematic_generator.adapter import build_schematic_from_pin_data
from src.models import (
    ComponentRecord,
    functional_layout_applicable,
    role_coverage,
)
from src.models.pin_data import PinData, PackageInfo, Pin
from src.conformance.checks import check_functional_grouping, PartContext
from src.conformance.model import CheckStatus


def _legs_extras(glb: str) -> dict:
    g = GLTF2().load_binary(glb)
    root = g.scenes[g.scene or 0].nodes[0]
    legs = next(c for c in g.nodes[root].children if g.nodes[c].name == "Legs")
    return {g.nodes[p].name: (g.nodes[p].extras or {}) for p in g.nodes[legs].children}


def _build(pd: PinData) -> str:
    out = str(Path(tempfile.mkdtemp()) / "sym.glb")
    build_schematic_from_pin_data(pin_data=pd, output_path=out,
                                  record=ComponentRecord.from_pin_data(pd))
    return out


def _gated_pd() -> PinData:
    """6-pin part clearing the gate: supply + ground present, 100% concrete."""
    return PinData(
        component_name="X",
        package=PackageInfo(type="DIP-6", pin_count=6, width=0, height=0),
        pins=[Pin(1, "VCC", role="supply"),
              Pin(2, "GND", role="ground"),
              Pin(3, "CLK", role="clock"),
              Pin(4, "RST", role="reset"),
              Pin(5, "OUT", role="output"),
              Pin(6, "IO0", role="io")],
    )


# --- the shared coverage gate (single source of truth for 4a check + 4b gen) ---
def test_role_coverage():
    assert role_coverage(["supply", "ground", "other", None]) == 0.5
    assert role_coverage([]) == 0.0


def test_gate_requires_power_ground_and_coverage():
    # supply + ground + >=50% concrete -> applicable
    assert functional_layout_applicable(["supply", "ground", "clock", "output"]) is True
    # missing ground -> not applicable
    assert functional_layout_applicable(["supply", "clock", "output", "input"]) is False
    # power+ground present but coverage < 0.5 -> not applicable
    assert functional_layout_applicable(
        ["supply", "ground", "other", "other", "other", "other"]) is False
    # all unknown -> not applicable
    assert functional_layout_applicable([None, None, "other"]) is False


# --- role extra is written on every pin (inert metadata) ----------------------
def test_role_extra_written():
    ex = _legs_extras(_build(_gated_pd()))
    assert ex["1"]["role"] == "supply"
    assert ex["2"]["role"] == "ground"
    assert ex["5"]["role"] == "output"
    # every pin node carries the key (value may be None when unclassified)
    assert all("role" in v for v in ex.values())


# --- SYM-04 passes once C.4b lays gated parts out by function -----------------
def test_sym04_passes_on_functional_layout():
    outcome = check_functional_grouping(PartContext("x", {"symbol": _build(_gated_pd())}))
    # gate passes -> functional layout (C.4b) groups pins by role: supply on top,
    # ground on bottom, inputs left, outputs right => grouping satisfied.
    assert outcome.status is CheckStatus.PASS


# --- below-gate parts are SKIPped, never penalised (legacy compatibility) -----
def test_sym04_skips_below_gate():
    pd = PinData(
        component_name="Y",
        package=PackageInfo(type="DIP-4", pin_count=4, width=0, height=0),
        pins=[Pin(1, "A"), Pin(2, "B"), Pin(3, "C"), Pin(4, "D")],  # unclassified
    )
    outcome = check_functional_grouping(PartContext("x", {"symbol": _build(pd)}))
    assert outcome.status is CheckStatus.SKIP
