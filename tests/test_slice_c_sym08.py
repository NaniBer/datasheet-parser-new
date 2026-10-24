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
    assert _active_low_display("RESET", True) == "RESET#"
    assert _active_low_display("/CS", True) == "CS#"        # strip leading '/', no double mark
    assert _active_low_display("OE#", True) == "OE#"        # already '#', no double mark
    assert _active_low_display("RESET_N", True) == "RESET#"  # strip _N suffix
    assert _active_low_display("VCC", False) == "VCC"       # inactive -> unchanged
    # P1-2b: the extra notations the detector now recognises must also be
    # stripped so the displayName never double-marks.
    assert _active_low_display("RESET*", True) == "RESET#"  # strip trailing '*'
    assert _active_low_display("~CS", True) == "CS#"        # strip leading '~'
    assert _active_low_display("CS~", True) == "CS#"        # strip trailing '~'


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
    assert ex["1"]["activeLow"] is True and ex["1"]["displayName"] == "RESET#"
    assert ex["2"]["activeLow"] is True and ex["2"]["displayName"] == "CS#"
    assert ex["3"]["activeLow"] is False and ex["3"]["displayName"] == "VCC"


def test_conformance_sym08_passes():
    out = str(Path(tempfile.mkdtemp()) / "sym.glb")
    pd = _pd()
    build_schematic_from_pin_data(pin_data=pd, output_path=out,
                                  record=ComponentRecord.from_pin_data(pd))
    outcome = check_active_low_notation(PartContext("x", {"symbol": out}))
    assert outcome.status is CheckStatus.PASS


# --- P1-2b: the flag is set from the *, ~ markers (as well as #, /, _N) --------
def test_active_low_flag_set_from_extra_markers():
    """A pin whose name carries a '*' or '~' printed marker must come out
    activeLow=True with a single '#'-suffixed displayName, end-to-end."""
    pd = PinData(
        component_name="X",
        package=PackageInfo(type="SOIC-8", pin_count=8, width=0, height=0),
        pins=[Pin(1, "RESET*"),                      # trailing '*'
              Pin(2, "~TRIGGER"),                    # leading '~'
              Pin(3, "INTRQ#")] + [Pin(i, f"S{i}") for i in range(4, 9)],
    )
    out = str(Path(tempfile.mkdtemp()) / "sym.glb")
    build_schematic_from_pin_data(pin_data=pd, output_path=out,
                                  record=ComponentRecord.from_pin_data(pd))
    ex = _legs_extras(out)
    assert ex["1"]["activeLow"] is True and ex["1"]["displayName"] == "RESET#"
    assert ex["2"]["activeLow"] is True and ex["2"]["displayName"] == "TRIGGER#"
    assert ex["3"]["activeLow"] is True and ex["3"]["displayName"] == "INTRQ#"


# --- P1-3: the drawn label is sourced from the PER-PIN name, not a grouped row -
def _find_child(g, idx, name):
    for c in g.nodes[idx].children or []:
        if g.nodes[c].name == name:
            return c
    return None


def test_pin_label_drawn_from_per_pin_name():
    """Each pin's drawn ``pinName`` glyph mesh and its ``pinName`` extra are
    sourced from that pin's own name — never a shared/grouped string. Guards
    P1-3: feeding the builder split per-pin names (as /agentic produces) yields
    per-pin labels, and two differently-named pins produce distinct glyph
    geometry (so the mesh is name-derived, not a baked constant)."""
    pd = PinData(
        component_name="X",
        package=PackageInfo(type="SOIC-8", pin_count=8, width=0, height=0),
        # The datasheet grouped these as "CSA, CSB" / "GPO0 to GPO3"; /agentic
        # splits them. The builder must draw each split name on its own pin.
        pins=[Pin(1, "CSA"), Pin(2, "CSB"),
              Pin(3, "GPO0"), Pin(4, "GPO3"),
              Pin(5, "VCC"), Pin(6, "GND"),
              Pin(7, "VINR"), Pin(8, "AIN1")],
    )
    out = str(Path(tempfile.mkdtemp()) / "sym.glb")
    build_schematic_from_pin_data(pin_data=pd, output_path=out)

    g = GLTF2().load_binary(out)
    root = g.scenes[g.scene or 0].nodes[0]
    legs = _find_child(g, root, "Legs")
    want = {str(p.number): p.name for p in pd.pins}

    seen = {}
    for p in g.nodes[legs].children:
        num = g.nodes[p].name
        ex = g.nodes[p].extras or {}
        # the extra carries this pin's own name (no grouped row, no concatenation)
        assert ex.get("pinName") == want[num], (num, ex.get("pinName"))
        # the drawn glyph mesh for the name is present for every pin
        name_node = _find_child(g, p, "pinName")
        assert name_node is not None, f"pin {num} has no drawn pinName mesh"
        seen[num] = name_node

    # no two pins share the same name string (grouped-row bug would collide)
    assert len(set(want.values())) == len(want.values())
