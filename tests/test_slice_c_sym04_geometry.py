"""Slice C sub-step 4b: SYM-04 functional-grouping GEOMETRY.

4b lays gated parts out by function (Decisions A2 + B) so SYM-04 flips to PASS,
while SYM-02 (grid), SYM-12 (numbering) and pin completeness (V-01 proxy) stay
satisfied, and below-gate parts remain byte-identical to the physical layout.
"""
import tempfile
from pathlib import Path

from pygltflib import GLTF2

from src.schematic_generator.adapter import build_schematic_from_pin_data
from src.schematic_generator.functional_layout import (
    functional_side_layout,
    size_functional_body,
)
from src.schematic_generator.pin_layout import layout_pins
from src.schematic_generator.pinout_diagram_builder import PinoutDiagramBuilder
from src.package_types import get_schematic_parameters
from src.models import ComponentRecord
from src.models.pin_data import PinData, PackageInfo, Pin
from src.conformance.checks import (
    check_functional_grouping,
    check_symbol_grid,
    check_symbol_pin_numbering,
    PartContext,
)
from src.conformance.model import CheckStatus

GRID = 2.54
_SIDE = {0: "left", 1: "top", 2: "right", 3: "bottom"}


def _d(number, name, role=None, nc=False):
    return {"number": str(number), "name": name, "role": role, "nc": nc}


def _build(pd: PinData) -> str:
    out = str(Path(tempfile.mkdtemp()) / "s.glb")
    build_schematic_from_pin_data(pin_data=pd, output_path=out,
                                  record=ComponentRecord.from_pin_data(pd))
    return out


def _legs(glb: str) -> dict:
    g = GLTF2().load_binary(glb)
    root = g.scenes[g.scene or 0].nodes[0]
    legs = next(c for c in g.nodes[root].children if g.nodes[c].name == "Legs")
    return {g.nodes[p].name: (g.nodes[p].extras or {}) for p in g.nodes[legs].children}


# ---------------------------------------------------------------------------
# functional_side_layout — pure unit tests (Decision A2)
# ---------------------------------------------------------------------------
def test_side_assignment_by_role():
    pins = [_d(1, "VCC", "supply"), _d(2, "GND", "ground"), _d(3, "CLK", "clock"),
            _d(4, "RST", "reset"), _d(5, "OUT", "output"), _d(6, "IO0", "io")]
    lay = functional_side_layout(pins)
    # SnapEDA: supply/output/ground on the right; control/inputs/io on the left.
    assert "1" in lay["right"] and "2" in lay["right"]      # supply + ground right
    assert not lay["top"] and not lay["bottom"]             # top/bottom unused
    assert [n for n in lay["left"] if n] == ["3", "4", "6"]   # clock, reset, io
    assert [n for n in lay["right"] if n] == ["1", "5", "2"]  # supply, output, ground


def test_blank_between_role_blocks():
    pins = [_d(1, "VCC", "supply"), _d(2, "GND", "ground"),
            _d(3, "CLK", "clock"), _d(4, "RST", "reset")]
    lay = functional_side_layout(pins)
    # two distinct role blocks (clock, reset) => exactly one blank between them
    assert lay["left"] == ["3", None, "4"]


def test_within_block_sorted_by_pin_number():
    # two inputs in the same block keep pin-number order, no blank between them
    pins = [_d(1, "VCC", "supply"), _d(2, "GND", "ground"),
            _d(7, "IN1", "input"), _d(3, "IN0", "input")]
    lay = functional_side_layout(pins)
    assert lay["left"] == ["3", "7"]                        # sorted, no blank


def test_nc_clustered_on_left_after_placed():
    pins = [_d(1, "VCC", "supply"), _d(2, "GND", "ground"), _d(3, "CLK", "clock"),
            _d(4, "OUT", "output"), _d(5, "NC", nc=True), _d(6, "DNC", nc=True)]
    lay = functional_side_layout(pins)
    # SnapEDA keeps the right column clean (supply/output/ground); NC pins trail
    # at the BOTTOM of the LEFT column, after the placed clock pin.
    left = lay["left"]
    assert [n for n in left if n] == ["3", "5", "6"]        # clock, then NC cluster
    assert left.index("3") < left.index(None) < left.index("5")


def test_shorter_side_centred_by_leading_blanks():
    # 3 left blocks (clock/reset/enable) => left = [3,None,4,None,5] (5 slots);
    # the 2-block right column (supply/ground => 3 slots) is centred by
    # floor((5-3)/2)=1 leading blank.
    pins = [_d(1, "VCC", "supply"), _d(2, "GND", "ground"),
            _d(3, "CLK", "clock"), _d(4, "RST", "reset"), _d(5, "EN", "enable")]
    lay = functional_side_layout(pins)
    assert lay["left"] == ["3", None, "4", None, "5"]
    assert lay["right"] == [None, "1", None, "2"]           # centred in the 5-slot span


# ---------------------------------------------------------------------------
# size_functional_body — Decision B
# ---------------------------------------------------------------------------
def _is_even_grid(value: float) -> bool:
    step = 2 * GRID
    return abs(round(value / step) * step - value) < 1e-6


def test_body_sized_to_even_grid_multiples():
    pins = [_d(1, "VCC", "supply"), _d(2, "GND", "ground"), _d(3, "CLK", "clock"),
            _d(4, "RST", "reset"), _d(5, "OUT", "output"), _d(6, "IO0", "io")]
    params = get_schematic_parameters("DIP-6", 6)
    lay = functional_side_layout(pins)
    size_functional_body(lay, pins, params)
    assert _is_even_grid(params.body_width)
    assert _is_even_grid(params.body_height)
    # height driven by the taller of left/right. SnapEDA: left = clock/reset/io
    # (5 slots incl. blanks), right = supply/output/ground (5 slots).
    assert params.body_height >= (5 - 1) * GRID


# ---------------------------------------------------------------------------
# Integration — gated part is grouped and stays conformant
# ---------------------------------------------------------------------------
def _gated_pd() -> PinData:
    return PinData(
        component_name="X",
        package=PackageInfo(type="DIP-6", pin_count=6, width=0, height=0),
        pins=[Pin(1, "VCC", role="supply"), Pin(2, "GND", role="ground"),
              Pin(3, "CLK", role="clock"), Pin(4, "RST", role="reset"),
              Pin(5, "OUT", role="output"), Pin(6, "IO0", role="io")],
    )


def test_gated_symbol_sides_match_roles_and_stay_conformant():
    glb = _build(_gated_pd())
    ex = _legs(glb)
    assert _SIDE[ex["1"]["side"]] == "right"      # supply
    assert _SIDE[ex["2"]["side"]] == "right"      # ground
    assert _SIDE[ex["3"]["side"]] == "left"       # clock
    assert _SIDE[ex["5"]["side"]] == "right"      # output
    ctx = PartContext("x", {"symbol": glb})
    assert check_functional_grouping(ctx).status is CheckStatus.PASS
    assert check_symbol_grid(ctx).status is CheckStatus.PASS         # SYM-02
    assert check_symbol_pin_numbering(ctx).status is CheckStatus.PASS  # SYM-12


def test_nc_pins_drawn_and_grouped_left():
    pd = PinData(
        component_name="Y",
        package=PackageInfo(type="SOIC-8", pin_count=8, width=0, height=0),
        pins=[Pin(1, "VCC"), Pin(2, "OUT"), Pin(3, "NC"),
              Pin(4, "DNC", nc_instruction="do not connect"), Pin(5, "GND"),
              Pin(6, "CLK"), Pin(7, "IN0"), Pin(8, "D0")],
    )
    glb = _build(pd)
    ex = _legs(glb)
    assert set(ex.keys()) == {str(i) for i in range(1, 9)}   # V-01 proxy: none dropped
    assert ex["3"]["nc"] is True and ex["4"]["nc"] is True
    # SnapEDA: NC pins trail at the bottom of the LEFT column.
    assert _SIDE[ex["3"]["side"]] == "left" and _SIDE[ex["4"]["side"]] == "left"
    ctx = PartContext("x", {"symbol": glb})
    assert check_functional_grouping(ctx).status is CheckStatus.PASS
    assert check_symbol_grid(ctx).status is CheckStatus.PASS
    assert check_symbol_pin_numbering(ctx).status is CheckStatus.PASS


# ---------------------------------------------------------------------------
# Below-gate parts stay byte-identical to the physical layout
# ---------------------------------------------------------------------------
def test_below_gate_layout_identical_to_physical():
    # 8 pins, no roles -> gate fails -> physical dual-row layout, unchanged.
    pin_data = [_d(i, f"P{i}") for i in range(1, 9)]
    builder = PinoutDiagramBuilder("DIP-8", 8, "X", pin_data=pin_data)
    physical = layout_pins(get_schematic_parameters("DIP-8", 8))
    got = [(p.pin_number, round(p.x, 6), round(p.y, 6), p.side) for p in builder.pin_positions]
    want = [(p.pin_number, round(p.x, 6), round(p.y, 6), p.side) for p in physical]
    assert got == want
    # and body dims are the untouched physical params
    assert builder.params.body_width == get_schematic_parameters("DIP-8", 8).body_width
    assert builder.params.body_height == get_schematic_parameters("DIP-8", 8).body_height


def test_vision_custom_layout_wins_over_functional():
    # An explicit custom_layout is authoritative even if roles would gate in.
    pin_data = [_d(1, "VCC", "supply"), _d(2, "GND", "ground"),
                _d(3, "CLK", "clock"), _d(4, "OUT", "output")]
    custom = {"left_side": [1, 2], "right_side": [3, 4]}
    builder = PinoutDiagramBuilder("DIP-4", 4, "X", custom_layout=custom, pin_data=pin_data)
    by_num = {p.pin_number: p.side for p in builder.pin_positions}
    assert by_num["1"] == "left" and by_num["3"] == "right"   # vision layout, not role
