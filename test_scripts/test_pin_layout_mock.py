#!/usr/bin/env python3
"""Test pin layout with mock data (no LLM required)."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.schematic_generator.pin_layout import PinLayout
from src.schematic_generator.schematic_builder import SchematicBuilder
from src.schematic_generator import get_schematic_parameters

def test_package_layout(package_type, pin_count, expected_positions):
    """Test pin layout for a package."""
    print(f"\n{'='*60}")
    print(f"Testing: {package_type} ({pin_count} pins)")
    print(f"{'='*60}")

    try:
        # Get schematic parameters
        params = get_schematic_parameters(package_type, pin_count)
        print(f"✓ SchematicParameters created")

        # Create pin layout
        pin_layout = PinLayout(params)
        print(f"✓ PinLayout created")

        # Get all pin positions
        positions = pin_layout.layout_all_pins()
        print(f"✓ Generated {len(positions)} pin positions")

        # Check pin count
        if len(positions) != pin_count:
            print(f"❌ ERROR: Expected {pin_count} positions, got {len(positions)}")
            return False

        # Show sample positions
        print(f"\nSample pin positions:")
        for pos in positions[:5]:
            print(f"  Pin {pos.pin_number}: ({pos.x:.2f}, {pos.y:.2f}) {pos.side} (rot: {pos.rotation}°)")

        # Verify positions are unique
        coords = [(p.x, p.y) for p in positions]
        if len(coords) != len(set(coords)):
            print(f"❌ ERROR: Duplicate positions found!")
            return False

        print(f"\n✓ All positions unique")
        print(f"✓ Test passed for {package_type}")
        return True

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_schematic_builder(package_type, pin_count):
    """Test SchematicBuilder with package."""
    print(f"\n{'='*60}")
    print(f"Testing SchematicBuilder: {package_type} ({pin_count} pins)")
    print(f"{'='*60}")

    try:
        builder = SchematicBuilder(package_type, pin_count)
        print(f"✓ SchematicBuilder created")
        print(f"  Package type: {builder.params.package_type}")
        print(f"  Pin count: {builder.params.pin_count}")
        print(f"  Body size: {builder.params.body_width:.2f} x {builder.params.body_height:.2f} mm")
        print(f"  Pin pitch: {builder.params.pin_pitch:.2f} mm")

        # Test pin layout from builder
        pin_layout = PinLayout(builder.params)
        positions = pin_layout.layout_all_pins()
        print(f"✓ Pin layout generated: {len(positions)} positions")

        print(f"\n✓ Test passed for SchematicBuilder")
        return True

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("=" * 80)
    print("PIN LAYOUT TEST (Mock Data - No LLM Required)")
    print("=" * 80)

    # Test cases with different package types
    test_cases = [
        # (package_type, pin_count)
        ("DIP-8", 8),
        ("DIP-16", 16),
        ("DIP-40", 40),
        ("SOIC-8", 8),
        ("SOIC-16", 16),
        ("SOIC-20", 20),
        ("TQFP-44", 44),
        ("TQFP-64", 64),
        ("LQFP-48", 48),
        ("QFN-32", 32),
        ("LCCC-20", 20),
    ]

    results = []

    for package_type, pin_count in test_cases:
        # Test pin layout
        layout_result = test_package_layout(package_type, pin_count, None)
        results.append(("layout", package_type, layout_result))

        # Test schematic builder
        builder_result = test_schematic_builder(package_type, pin_count)
        results.append(("builder", package_type, builder_result))

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    layout_success = sum(1 for t, pkg, r in results if t == "layout" and r)
    layout_total = sum(1 for t, pkg, r in results if t == "layout")
    builder_success = sum(1 for t, pkg, r in results if t == "builder" and r)
    builder_total = sum(1 for t, pkg, r in results if t == "builder")

    print(f"\nPin Layout Tests: {layout_success}/{layout_total} passed")
    print(f"SchematicBuilder Tests: {builder_success}/{builder_total} passed")

    failed = [(t, pkg) for t, pkg, r in results if not r]
    if failed:
        print(f"\nFailed tests:")
        for t, pkg in failed:
            print(f"  ❌ {t}: {pkg}")
    else:
        print(f"\n✓ All tests passed!")

    print("\n" + "=" * 80)

if __name__ == "__main__":
    main()
