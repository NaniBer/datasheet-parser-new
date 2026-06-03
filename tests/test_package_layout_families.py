"""Tests for package-specific pin side layouts."""

from src.package_types import PackageType, get_schematic_parameters
from src.schematic_generator.pin_layout import layout_pins


def test_dfn_8_uses_dual_row_layout():
    """DFN-8 should place four pins on the left and four on the right."""
    params = get_schematic_parameters("DFN-8", 8)

    assert params.package_type == PackageType.DFN
    assert params.pins_per_side == [4, 4, 0, 0]

    positions = layout_pins(params)
    sides = [pos.side for pos in positions]

    assert sides == ["left", "left", "left", "left", "right", "right", "right", "right"]
    assert [pos.pin_number for pos in positions] == [str(index) for index in range(1, 9)]


def test_qfn_24_uses_quad_layout():
    """QFN-24 should remain a four-side package with six pins per side."""
    params = get_schematic_parameters("QFN-24", 24)

    assert params.package_type == PackageType.QFN
    assert params.pins_per_side == [6, 6, 6, 6]

    positions = layout_pins(params)
    side_counts = {
        "left": sum(1 for pos in positions if pos.side == "left"),
        "bottom": sum(1 for pos in positions if pos.side == "bottom"),
        "right": sum(1 for pos in positions if pos.side == "right"),
        "top": sum(1 for pos in positions if pos.side == "top"),
    }

    assert side_counts == {"left": 6, "bottom": 6, "right": 6, "top": 6}
    assert [pos.pin_number for pos in positions] == [str(index) for index in range(1, 25)]

    left = [pos for pos in positions if pos.side == "left"]
    bottom = [pos for pos in positions if pos.side == "bottom"]
    right = [pos for pos in positions if pos.side == "right"]
    top = [pos for pos in positions if pos.side == "top"]

    assert [pos.pin_number for pos in left] == ["1", "2", "3", "4", "5", "6"]
    assert [pos.y for pos in left] == sorted([pos.y for pos in left], reverse=True)

    assert [pos.pin_number for pos in bottom] == ["7", "8", "9", "10", "11", "12"]
    assert [pos.x for pos in bottom] == sorted([pos.x for pos in bottom])

    assert [pos.pin_number for pos in right] == ["13", "14", "15", "16", "17", "18"]
    assert [pos.y for pos in right] == sorted([pos.y for pos in right])

    assert [pos.pin_number for pos in top] == ["19", "20", "21", "22", "23", "24"]
    assert [pos.x for pos in top] == sorted([pos.x for pos in top], reverse=True)
