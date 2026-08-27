"""Slice C sub-step 1: SYM-07 electrical-type GLB extra (metadata only)."""
import tempfile
from pathlib import Path

from pygltflib import GLTF2

from src.schematic_generator.adapter import build_schematic_from_pin_data
from src.models import ComponentRecord, ELECTRICAL_TYPES
from src.models.pin_data import PinData, PackageInfo, Pin
from src.conformance.checks import check_symbol_electrical_types, PartContext
from src.conformance.model import CheckStatus


def _build_with_record(out: str) -> str:
    pd = PinData(
        component_name="X",
        package=PackageInfo(type="SOIC-8", pin_count=8, width=0, height=0),
        pins=[Pin(1, "VCC", electrical_type="power_in"),
              Pin(2, "OUT", electrical_type="output"),
              Pin(3, "GND", electrical_type="power_in")]
             + [Pin(i, f"S{i}") for i in range(4, 9)],   # no type -> unspecified
    )
    build_schematic_from_pin_data(pin_data=pd, output_path=out,
                                  record=ComponentRecord.from_pin_data(pd))
    return out


def _legs_electrical_types(glb: str) -> dict:
    g = GLTF2().load_binary(glb)
    root = g.scenes[g.scene or 0].nodes[0]
    legs = next(c for c in g.nodes[root].children if g.nodes[c].name == "Legs")
    return {g.nodes[p].name: (g.nodes[p].extras or {}).get("electricalType")
            for p in g.nodes[legs].children}


def test_electrical_type_extra_written_from_record():
    out = _build_with_record(str(Path(tempfile.mkdtemp()) / "sym.glb"))
    et = _legs_electrical_types(out)
    assert et["1"] == "power_in" and et["2"] == "output" and et["3"] == "power_in"
    # every pin carries a valid contract value; unknown -> "unspecified"
    assert all(v in ELECTRICAL_TYPES for v in et.values())
    assert et["4"] == "unspecified"


def test_conformance_sym07_passes():
    out = _build_with_record(str(Path(tempfile.mkdtemp()) / "sym.glb"))
    outcome = check_symbol_electrical_types(PartContext("x", {"symbol": out}))
    assert outcome.status is CheckStatus.PASS


def test_electrical_type_defaults_unspecified_without_record():
    # No record + plain pins -> every pin still gets a valid "unspecified".
    pd = PinData(component_name="X",
                 package=PackageInfo(type="SOIC-8", pin_count=8, width=0, height=0),
                 pins=[Pin(i, f"S{i}") for i in range(1, 9)])
    out = str(Path(tempfile.mkdtemp()) / "sym.glb")
    build_schematic_from_pin_data(pin_data=pd, output_path=out)   # record=None
    et = _legs_electrical_types(out)
    assert all(v == "unspecified" for v in et.values())
