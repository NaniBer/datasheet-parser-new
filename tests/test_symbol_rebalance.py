"""QC ADV7180 SCH-05: a lopsided SnapEDA layout is rebalanced, not drawn as a tower.

The SnapEDA right column carries supplies, outputs AND grounds, so an
output-heavy part (ADV7180: 8-bit pixel bus, GPOs, syncs) became ~18 x 89 mm
against QC's ~41 x 69 mm reference. When the right column far exceeds the left,
whole power groups move off it -- grounds to the bottom edge, then supplies to
the top -- while inputs stay left, outputs right, and each group contiguous.
"""
import tempfile
from collections import Counter
from pathlib import Path

import pytest
from pygltflib import GLTF2

from src.conformance.checks import (
    PartContext,
    check_functional_grouping,
    check_symbol_grid,
    check_symbol_pin_numbering,
)
from src.conformance.model import CheckStatus
from src.models import ComponentRecord
from src.models.pin_data import PackageInfo, Pin, PinData
from src.schematic_generator.adapter import build_schematic_from_pin_data
from src.schematic_generator.functional_layout import functional_side_layout
from src.schematic_generator.pinout_diagram_builder import PinoutDiagramBuilder


def _pins(spec):
    """``[(name, role), ...]`` -> pin dicts numbered 1..n."""
    return [{"number": str(i), "name": n, "role": r} for i, (n, r) in enumerate(spec, 1)]


def _placed(lay, side):
    return [n for n in lay[side] if n]


def _output_heavy(n_out=16, n_gnd=6, n_sup=4, n_in=12):
    spec = ([(f"IN{i}", "input") for i in range(n_in)] + [("SCL", "clock"), ("RST", "reset")]
            + [(f"VDD{i}", "supply") for i in range(n_sup)]
            + [(f"Q{i}", "output") for i in range(n_out)]
            + [(f"GND{i}", "ground") for i in range(n_gnd)])
    return _pins(spec)


def test_lopsided_right_column_sends_grounds_to_the_bottom():
    pins = _output_heavy()
    role = {p["number"]: p["role"] for p in pins}
    lay = functional_side_layout(pins)
    assert {role[n] for n in _placed(lay, "bottom")} == {"ground"}
    assert len(_placed(lay, "bottom")) == 6 and None not in lay["bottom"]   # one block
    assert {role[n] for n in _placed(lay, "right")} == {"supply", "output"}
    assert {role[n] for n in _placed(lay, "left")} == {"input", "clock", "reset"}
    assert not _placed(lay, "top")           # one move was enough


def test_still_lopsided_after_grounds_sends_supplies_to_the_top():
    pins = _output_heavy(n_out=24, n_gnd=8, n_sup=8, n_in=2)
    role = {p["number"]: p["role"] for p in pins}
    lay = functional_side_layout(pins)
    assert {role[n] for n in _placed(lay, "top")} == {"supply"}
    assert {role[n] for n in _placed(lay, "bottom")} == {"ground"}
    assert {role[n] for n in _placed(lay, "right")} == {"output"}


@pytest.mark.parametrize("spec", [
    # PGA2311P-like: 3 supplies, 3 outputs, 3 grounds vs 7 controls/inputs.
    [("ZCEN", "control"), ("CS", "control"), ("SDI", "input"), ("VD+", "supply"),
     ("DGND", "ground"), ("SCLK", "clock"), ("SDO", "output"), ("MUTE", "control"),
     ("VINR", "input"), ("AGNDR", "ground"), ("VOUTR", "output"), ("VA+", "supply"),
     ("VA-", "supply"), ("VOUTL", "output"), ("AGNDL", "ground"), ("VINL", "input")],
    # Tiny part: right column longer, but only by a few slots.
    [("VCC", "supply"), ("Y", "output"), ("GND", "ground"), ("A", "input")],
    # Left column is the tall one: nothing to relieve on the right.
    [(f"D{i}", "data") for i in range(30)] + [("VCC", "supply"), ("GND", "ground")],
])
def test_balanced_or_small_parts_keep_the_two_column_layout(spec):
    lay = functional_side_layout(_pins(spec))
    assert not lay["top"] and not lay["bottom"]


def test_rebalanced_symbol_is_compact_and_conformant():
    pins = _output_heavy()
    pd = PinData(component_name="X", package=PackageInfo(type="LQFP-40", pin_count=len(pins),
                                                         width=0, height=0),
                 pins=[Pin(int(p["number"]), p["name"], role=p["role"]) for p in pins])
    out = str(Path(tempfile.mkdtemp()) / "s.glb")
    assert build_schematic_from_pin_data(pin_data=pd, output_path=out,
                                         record=ComponentRecord.from_pin_data(pd))
    g = GLTF2().load_binary(out)
    legs = next(c for c in g.nodes[g.scenes[g.scene or 0].nodes[0]].children
                if g.nodes[c].name == "Legs")
    sides = Counter((g.nodes[p].extras or {}).get("side") for p in g.nodes[legs].children)
    assert sides[3] == 6                          # the grounds sit on the bottom edge
    ctx = PartContext("x", {"symbol": out})
    assert check_functional_grouping(ctx).status is CheckStatus.PASS   # SYM-04 accepts it
    assert check_symbol_grid(ctx).status is CheckStatus.PASS           # SYM-02
    assert check_symbol_pin_numbering(ctx).status is CheckStatus.PASS  # SYM-12


ADV = Path.home() / "Downloads/datasheets/ADV7180KST48Z.pdf"
ADV_NAMES = (
    "DGND DVDDIO SFL DVDDIO GPO1 GPO0 P7 P6 P5 P4 P3 P2 DGND LLC NC XTAL1 XTAL DVDD "
    "DGND P1 PWRDWN P0 AGND ELPF PVDD AIN1 AIN2 AGND VREFP VREFN AVDD AGND AIN3 AIN4 "
    "AIN5 AIN6 RESET ALSB SDATA SCLK GPO3 GPO2 DGND DVDD VS/FIELD INTRQ HS NC").split()


@pytest.mark.skipif(not ADV.exists(), reason="ADV7180 datasheet not available")
def test_adv7180_body_close_to_the_qc_reference():
    # QC SCH-05: our 18 x 89 mm tower vs the reference 40.6 x 68.6 mm.
    import pdfplumber
    from src.pdf_extractor.pin_direction import apply_pin_directions
    with pdfplumber.open(str(ADV)) as pdf:
        text = "\n".join(pg.extract_text() or "" for pg in pdf.pages[:20])
    pins = [Pin(number=i, name=n) for i, n in enumerate(ADV_NAMES, 1)]
    apply_pin_directions(pins, text)
    pd = PinData(component_name="ADV7180", pins=pins,
                 package=PackageInfo(type="LQFP-48", pin_count=48, width=0.0, height=0.0))
    rec = ComponentRecord.from_pin_data(pd, part_number="ADV7180KST48Z").selected()
    data = [{"number": str(p.number), "name": p.name, "role": p.role,
             "electrical_type": p.electrical_type} for p in rec.pins]
    b = PinoutDiagramBuilder("LQFP-48", 48, "ADV7180", pin_data=data)
    side = {str(p.pin_number): p.side for p in b.pin_positions}
    name = {d["number"]: d["name"] for d in data}
    assert {name[n] for n, s in side.items() if s == "bottom"} == {"DGND", "AGND"}
    for out in ("P0", "P7", "LLC", "HS", "GPO0"):
        assert side[str(ADV_NAMES.index(out) + 1)] == "right"
    for inp in ("AIN1", "SCLK", "RESET"):
        assert side[str(ADV_NAMES.index(inp) + 1)] == "left"
    w, h = b.params.body_width, b.params.body_height
    assert h <= 76.2 and w <= 45.72 and h / w < 2.5
