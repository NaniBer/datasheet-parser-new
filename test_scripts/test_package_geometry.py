#!/usr/bin/env python3
"""Test package geometry parameters."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.schematic_generator.package_geometry import (
    PackageType,
    get_dip_parameters,
    get_soic_parameters,
    get_tqfp_parameters,
    get_qfn_parameters,
    get_bga_parameters,
    parse_package_type,
    get_schematic_parameters,
    calculate_pin_position,
)


def test_dip_parameters():
    """Test DIP-8 parameters (NE555)."""
    print("Testing DIP-8 (NE555)...")
    params = get_dip_parameters(8)

    assert params.package_type == PackageType.DIP
    assert params.pin_count == 8
    assert params.pin_pitch == 2.54  # Standard DIP pitch
    assert params.pins_per_side == [4, 4, 0, 0]
    assert params.counter_clockwise == False  # Clockwise numbering

    print(f"  Body: {params.body_width} x {params.body_height} mm")
    print(f"  Pins per side: {params.pins_per_side}")
    print(f"  Pin pitch: {params.pin_pitch} mm")
    print(f"  Counter-clockwise: {params.counter_clockwise}")

    # Test pin positions
    for i in range(4):
        x, y, side = calculate_pin_position(i, params)
        print(f"  Pin {i+1}: ({x:.2f}, {y:.2f}) {side}")

    return True


def test_tqfp_parameters():
    """Test TQFP-44 parameters (ATmega164A)."""
    print("\nTesting TQFP-44 (ATmega164A)...")
    params = get_tqfp_parameters(44)

    assert params.package_type == PackageType.TQFP
    assert params.pin_count == 44
    assert params.pin_pitch == 0.5
    assert params.pins_per_side == [11, 11, 11, 11]
    assert params.counter_clockwise == True

    print(f"  Body: {params.body_width} x {params.body_height} mm")
    print(f"  Pins per side: {params.pins_per_side}")
    print(f"  Pin pitch: {params.pin_pitch} mm")
    print(f"  Counter-clockwise: {params.counter_clockwise}")

    # Test pin positions for each side
    print("  Sample pin positions:")
    for i in [0, 11, 22, 33]:
        x, y, side = calculate_pin_position(i, params)
        print(f"    Pin {i+1}: ({x:.2f}, {y:.2f}) {side}")

    return True


def test_lqfp_parameters():
    """Test LQFP-64 parameters (STM32F103)."""
    print("\nTesting LQFP-64 (STM32F103)...")
    params = get_tqfp_parameters(64)

    assert params.package_type == PackageType.TQFP
    assert params.pin_count == 64
    assert params.pins_per_side == [16, 16, 16, 16]

    print(f"  Body: {params.body_width} x {params.body_height} mm")
    print(f"  Pins per side: {params.pins_per_side}")

    return True


def test_parse_package_type():
    """Test package type parsing."""
    print("\nTesting package type parsing...")

    assert parse_package_type("DIP-8") == PackageType.DIP
    assert parse_package_type("DIP8") == PackageType.DIP
    assert parse_package_type("LQFP64") == PackageType.LQFP
    assert parse_package_type("LQFP-64") == PackageType.LQFP
    assert parse_package_type("TQFP-44") == PackageType.TQFP
    assert parse_package_type("QFN") == PackageType.QFN

    print("  Package type parsing working correctly")

    return True


def test_get_schematic_parameters():
    """Test the main parameter lookup function."""
    print("\nTesting get_schematic_parameters...")

    # DIP-8
    params = get_schematic_parameters("DIP-8", 8)
    assert params.pin_count == 8
    assert params.pins_per_side == [4, 4, 0, 0]
    print(f"  DIP-8: {params.body_width} x {params.body_height}")

    # LQFP-64
    params = get_schematic_parameters("LQFP64", 64)
    assert params.pin_count == 64
    assert params.pins_per_side == [16, 16, 16, 16]
    print(f"  LQFP64: {params.body_width} x {params.body_height}")

    # TQFP-44
    params = get_schematic_parameters("TQFP-44", 44)
    assert params.pin_count == 44
    assert params.pins_per_side == [11, 11, 11, 11]
    print(f"  TQFP-44: {params.body_width} x {params.body_height}")

    return True


def test_pin_geometry():
    """Test pin geometry parameters."""
    print("\nTesting pin geometry...")

    params = get_dip_parameters(8)
    pin = params.pin_geometry

    print(f"  Leg length: {pin.leg_length} mm")
    print(f"  Leg width: {pin.leg_width} mm")
    print(f"  Pin number size: {pin.pin_num_size}")
    print(f"  Pin name size: {pin.pin_name_size}")
    print(f"  Pin name offset: {pin.pin_name_offset} mm")

    return True


if __name__ == '__main__':
    print("=" * 60)
    print("Package Geometry Parameters Test")
    print("=" * 60)

    try:
        test_dip_parameters()
        test_tqfp_parameters()
        test_lqfp_parameters()
        test_parse_package_type()
        test_get_schematic_parameters()
        test_pin_geometry()

        print("\n" + "=" * 60)
        print("All tests passed!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()
