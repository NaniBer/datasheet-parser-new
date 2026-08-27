"""Slice C sub-step 3: SYM-08 active-low notation (flag + ASCII marker, metadata)."""
import tempfile
from pathlib import Path

from pygltflib import GLTF2

from src.core.schematic_extras import _active_low_display
from src.schematic_generator.adapter import build_schematic_from_pin_data
from src.models import ComponentRecord
from src.models.pin_data import PinData, PackageInfo, Pin
from src.conformance.checks import check_active_low_notation, PartContext
from src.conformance.model import CheckStatus


# --- the one canonical ASCII marker, no double-marking ------------------------
def test_active_low_display_marker():
    assert _active_low_display("RESET", True) == "/RESET"
    assert _active_low_display("/CS", True) == "/CS"        # no double '/'
    assert _active_low_display("OE#", True) == "/OE"        # strip trailing '#'
    assert _active_low_display("RESET_N", True) == "/RESET"  # strip _N suffix
    assert _active_low_display("VCC", False) == "VCC"       # inactive -> unchanged


def _pd():
    return PinData(
        component_name="X",
        package=PackageInfo(type="SOIC-8", pin_count=8, width=0, height=0),
        pins=[Pin(1, "RESET", active_low=True),   # explicit flag
              Pin(2, "/CS"),                        # marker in name -> classifier flags
              Pin(3, "VCC")] + [Pin(i, f"S{i}") for i in range(4, 9)],
    )


def _legs_extras(glb: str) -> dict:
    g = GLTF2().load_binary(glb)
    root = g.scenes[g.scene or 0].nodes[0]
    legs = next(c for c in g.nodes[root].children if g.nodes[c].name == "Legs")
    return {g.nodes[p].name: (g.nodes[p].extras or {}) for p in g.nodes[legs].children}


def test_active_low_extras_written():
    out = str(Path(tempfile.mkdtemp()) / "sym.glb")
    pd = _pd()
    build_schematic_from_pin_data(pin_data=pd, output_path=out,
                                  record=ComponentRecord.from_pin_data(pd))
    ex = _legs_extras(out)
    assert ex["1"]["activeLow"] is True and ex["1"]["displayName"] == "/RESET"
    assert ex["2"]["activeLow"] is True and ex["2"]["displayName"] == "/CS"
    assert ex["3"]["activeLow"] is False and ex["3"]["displayName"] == "VCC"


def test_conformance_sym08_passes():
    out = str(Path(tempfile.mkdtemp()) / "sym.glb")
    pd = _pd()
    build_schematic_from_pin_data(pin_data=pd, output_path=out,
                                  record=ComponentRecord.from_pin_data(pd))
    outcome = check_active_low_notation(PartContext("x", {"symbol": out}))
    assert outcome.status is CheckStatus.PASS
