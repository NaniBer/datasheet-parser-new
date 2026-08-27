"""Slice C sub-step 2: SYM-11 no-connect marking (drawn + tagged, metadata)."""
import tempfile
from pathlib import Path

from pygltflib import GLTF2

from src.schematic_generator.adapter import build_schematic_from_pin_data
from src.models import ComponentRecord
from src.models.pin_data import PinData, PackageInfo, Pin
from src.conformance.checks import check_nc_pins_marked, PartContext
from src.conformance.model import CheckStatus


def _pd():
    return PinData(
        component_name="X",
        package=PackageInfo(type="SOIC-8", pin_count=8, width=0, height=0),
        pins=[Pin(1, "VCC"),
              Pin(2, "OUT"),
              Pin(3, "NC"),                                  # no-connect by name
              Pin(4, "DNC", nc_instruction="do not connect"),  # explicit instruction
              Pin(5, "GND")] + [Pin(i, f"S{i}") for i in range(6, 9)],
    )


def _build(out: str) -> str:
    pd = _pd()
    build_schematic_from_pin_data(pin_data=pd, output_path=out,
                                  record=ComponentRecord.from_pin_data(pd))
    return out


def _legs_extras(glb: str) -> dict:
    g = GLTF2().load_binary(glb)
    root = g.scenes[g.scene or 0].nodes[0]
    legs = next(c for c in g.nodes[root].children if g.nodes[c].name == "Legs")
    return {g.nodes[p].name: (g.nodes[p].extras or {}) for p in g.nodes[legs].children}


# --- the classifier tags no-connect pins (fill-only) on the record ------------
def test_record_flags_no_connect_names():
    rec = ComponentRecord.from_pin_data(_pd())
    by_num = {p.number: p for p in rec.selected().pins}
    assert by_num["3"].nc is True and by_num["4"].nc is True    # NC / DNC
    assert by_num["1"].nc is False and by_num["5"].nc is False   # VCC / GND
    assert by_num["4"].nc_instruction == "do not connect"


# --- extras written on the symbol, NC pins still drawn ------------------------
def test_nc_extras_written_and_pins_still_drawn():
    ex = _legs_extras(_build(str(Path(tempfile.mkdtemp()) / "sym.glb")))
    # every pin node still present (drawn, not omitted) and carries an nc flag
    assert set(ex.keys()) == {str(i) for i in range(1, 9)}
    assert ex["3"]["nc"] is True and ex["4"]["nc"] is True
    assert ex["4"]["ncInstruction"] == "do not connect"
    assert ex["1"]["nc"] is False and ex["5"]["nc"] is False


def test_conformance_sym11_passes():
    out = _build(str(Path(tempfile.mkdtemp()) / "sym.glb"))
    outcome = check_nc_pins_marked(PartContext("x", {"symbol": out}))
    assert outcome.status is CheckStatus.PASS
