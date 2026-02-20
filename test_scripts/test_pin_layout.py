#!/usr/bin/env python3
"""Test pin layout algorithms."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.schematic_generator import (
    get_schematic_parameters,
    layout_pins,
    PackageType,
)


def test_dip_8_layout():
    """Test DIP-8 pin layout (NE555)."""
    print("Testing DIP-8 pin layout...")
    params = get_schematic_parameters("DIP-8", 8)
    positions = layout_pins(params)

    assert len(positions) == 8, f"Expected 8 positions, got {len(positions)}"

    # Check left side (pins 1-4, top to bottom)
    left_pins = [p for p in positions if p.side == "left"]
    assert len(left_pins) == 4, f"Expected 4 left pins, got {len(left_pins)}"
    assert left_pins[0].pin_number == "1", f"Expected pin 1 at top-left, got {left_pins[0].pin_number}"
    assert left_pins[0].y > left_pins[1].y, "Pins should go top to bottom on left side"

    # Check right side (pins 5-8, bottom to top)
    right_pins = [p for p in positions if p.side == "right"]
    assert len(right_pins) == 4, f"Expected 4 right pins, got {len(right_pins)}"
    assert right_pins[0].pin_number == "5", f"Expected pin 5 at bottom-right, got {right_pins[0].pin_number}"
    assert right_pins[0].y < right_pins[1].y, "Pins should go bottom to top on right side"

    print("  Left side (top to bottom):")
    for p in left_pins:
        print(f"    Pin {p.pin_number}: ({p.x:.2f}, {p.y:.2f})")

    print("  Right side (bottom to top):")
    for p in right_pins:
        print(f"    Pin {p.pin_number}: ({p.x:.2f}, {p.y:.2f})")

    return True


def test_tqfp_44_layout():
    """Test TQFP-44 pin layout (ATmega164A)."""
    print("\nTesting TQFP-44 pin layout...")
    params = get_schematic_parameters("TQFP-44", 44)
    positions = layout_pins(params)

    assert len(positions) == 44, f"Expected 44 positions, got {len(positions)}"

    # Check each side has 11 pins
    for side in ["left", "right", "top", "bottom"]:
        side_pins = [p for p in positions if p.side == side]
        assert len(side_pins) == 11, f"Expected 11 pins on {side}, got {len(side_pins)}"

    # Check pin 1 is at top-left
    pin1 = positions[0]
    assert pin1.pin_number == "1", f"Expected pin 1 at index 0, got {pin1.pin_number}"
    assert pin1.side == "left", f"Expected pin 1 on left side, got {pin1.side}"

    # Check counter-clockwise order: left, bottom, right, top
    assert positions[10].side == "left", "Pin 11 should be last on left side"
    assert positions[11].side == "bottom", "Pin 12 should be first on bottom side"
    assert positions[21].side == "bottom", "Pin 22 should be last on bottom side"
    assert positions[22].side == "right", "Pin 23 should be first on right side"
    assert positions[32].side == "right", "Pin 33 should be last on right side"
    assert positions[33].side == "top", "Pin 34 should be first on top side"

    print("  Pin distribution:")
    for side in ["left", "bottom", "right", "top"]:
        side_pins = [p for p in positions if p.side == side]
        first = side_pins[0].pin_number
        last = side_pins[-1].pin_number
        print(f"    {side:6s}: pins {first}-{last} ({len(side_pins)} pins)")

    return True


def test_lqfp_64_layout():
    """Test LQFP-64 pin layout (STM32F103)."""
    print("\nTesting LQFP-64 pin layout...")
    params = get_schematic_parameters("LQFP64", 64)
    positions = layout_pins(params)

    assert len(positions) == 64, f"Expected 64 positions, got {len(positions)}"

    # Check each side has 16 pins
    for side in ["left", "right", "top", "bottom"]:
        side_pins = [p for p in positions if p.side == side]
        assert len(side_pins) == 16, f"Expected 16 pins on {side}, got {len(side_pins)}"

    print(f"  Total pins: {len(positions)}")
    print(f"  Body size: {params.body_width:.1f} x {params.body_height:.1f} mm")

    # Show some pin positions
    print("  Sample pin positions:")
    for idx in [0, 15, 16, 31, 32, 47, 48, 63]:
        p = positions[idx]
        print(f"    Pin {p.pin_number}: ({p.x:.2f}, {p.y:.2f}) {p.side}")

    return True


def test_pin_rotation_and_text():
    """Test that pins have correct rotation and text alignment."""
    print("\nTesting pin rotation and text alignment...")

    # Test DIP
    params = get_schematic_parameters("DIP-8", 8)
    positions = layout_pins(params)

    left_pins = [p for p in positions if p.side == "left"]
    right_pins = [p for p in positions if p.side == "right"]

    # Left side pins should point left (180 degrees) and have left-aligned text
    assert left_pins[0].rotation == 180, "Left pins should point left"
    assert left_pins[0].text_halign == "left", "Left pins should have left-aligned text"

    # Right side pins should point right (0 degrees) and have right-aligned text
    assert right_pins[0].rotation == 0, "Right pins should point right"
    assert right_pins[0].text_halign == "right", "Right pins should have right-aligned text"

    print("  DIP rotation and text alignment: OK")

    # Test TQFP
    params = get_schematic_parameters("TQFP-44", 44)
    positions = layout_pins(params)

    for side, expected_rotation, expected_halign in [
        ("left", 180, "left"),
        ("right", 0, "right"),
        ("top", 90, "center"),
        ("bottom", 270, "center"),
    ]:
        side_pins = [p for p in positions if p.side == side]
        assert side_pins[0].rotation == expected_rotation, f"{side} pins should have rotation {expected_rotation}"
        assert side_pins[0].text_halign == expected_halign, f"{side} pins should have {expected_halign} alignment"

    print("  TQFP rotation and text alignment: OK")

    return True


def test_soic_layout():
    """Test SOIC pin layout."""
    print("\nTesting SOIC-16 pin layout...")

    params = get_schematic_parameters("SOIC-16", 16)
    positions = layout_pins(params)

    assert len(positions) == 16

    left_pins = [p for p in positions if p.side == "left"]
    right_pins = [p for p in positions if p.side == "right"]

    assert len(left_pins) == 8, "SOIC-16 should have 8 pins on left"
    assert len(right_pins) == 8, "SOIC-16 should have 8 pins on right"

    print(f"  SOIC-16: {params.body_width:.1f} x {params.body_height:.1f} mm")
    print(f"  Pin pitch: {params.pin_pitch:.2f} mm")

    return True


if __name__ == '__main__':
    print("=" * 60)
    print("Pin Layout Algorithms Test")
    print("=" * 60)

    try:
        test_dip_8_layout()
        test_tqfp_44_layout()
        test_lqfp_64_layout()
        test_pin_rotation_and_text()
        test_soic_layout()

        print("\n" + "=" * 60)
        print("All tests passed!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()
