#!/usr/bin/env python3
"""Test schematic builder."""

import sys
import os
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.schematic_generator import build_schematic_from_pin_data


def test_dip_8_schematic():
    """Test building DIP-8 schematic (NE555)."""
    print("Testing DIP-8 schematic (NE555)...")

    # NE555 pin data
    pin_data = [
        {"number": "1", "name": "GND"},
        {"number": "2", "name": "TRIG"},
        {"number": "3", "name": "OUT"},
        {"number": "4", "name": "RESET"},
        {"number": "5", "name": "CV"},
        {"number": "6", "name": "THR"},
        {"number": "7", "name": "DIS"},
        {"number": "8", "name": "VCC"},
    ]

    # Create temporary output file
    with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as f:
        output_path = f.name

    # Build and save
    result = build_schematic_from_pin_data(
        package_type="DIP-8",
        pin_count=8,
        component_name="NE555",
        pin_data=pin_data,
        output_path=output_path,
    )

    if result:
        import os
        size = os.path.getsize(output_path)
        print(f"  Success! GLB size: {size} bytes")
        print(f"  Saved to: {output_path}")

        # Clean up
        os.unlink(output_path)
        return True
    else:
        print("  Failed to build schematic")
        return False


def test_tqfp_44_schematic():
    """Test building TQFP-44 schematic (ATmega164A)."""
    print("\nTesting TQFP-44 schematic (ATmega164A)...")

    # Simplified pin data for TQFP-44
    pin_data = [
        {"number": str(i+1), "name": f"PIN{i+1}"}
        for i in range(44)
    ]

    with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as f:
        output_path = f.name

        result = build_schematic_from_pin_data(
            package_type="TQFP-44",
            pin_count=44,
            component_name="ATmega164A",
            pin_data=pin_data,
            output_path=output_path,
        )

        if result:
            import os
            size = os.path.getsize(output_path)
            print(f"  Success! GLB size: {size} bytes")

            os.unlink(output_path)
            return True
        return False


def test_lqfp_64_schematic():
    """Test building LQFP-64 schematic (STM32F103)."""
    print("\nTesting LQFP-64 schematic (STM32F103)...")

    # Simplified pin data for LQFP-64
    pin_data = [
        {"number": str(i+1), "name": f"PA{i}"}
        for i in range(64)
    ]

    with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as f:
        output_path = f.name

        result = build_schematic_from_pin_data(
            package_type="LQFP64",
            pin_count=64,
            component_name="STM32F103",
            pin_data=pin_data,
            output_path=output_path,
        )

        if result:
            import os
            size = os.path.getsize(output_path)
            print(f"  Success! GLB size: {size} bytes")

            os.unlink(output_path)
            return True
        return False


def test_soic_16_schematic():
    """Test building SOIC-16 schematic."""
    print("\nTesting SOIC-16 schematic...")

    pin_data = [
        {"number": str(i+1), "name": f"I{i}"}
        for i in range(16)
    ]

    with tempfile.NamedTemporaryFile(suffix=".glb", delete=False) as f:
        output_path = f.name

        result = build_schematic_from_pin_data(
            package_type="SOIC-16",
            pin_count=16,
            component_name="SOIC16",
            pin_data=pin_data,
            output_path=output_path,
        )

        if result:
            import os
            size = os.path.getsize(output_path)
            print(f"  Success! GLB size: {size} bytes")

            os.unlink(output_path)
            return True
        return False


if __name__ == '__main__':
    print("=" * 60)
    print("Schematic Builder Test")
    print("=" * 60)

    import logging
    logging.basicConfig(level=logging.INFO)

    try:
        results = []
        results.append(test_dip_8_schematic())
        results.append(test_tqfp_44_schematic())
        results.append(test_lqfp_64_schematic())
        results.append(test_soic_16_schematic())

        print("\n" + "=" * 60)
        if all(results):
            print("All tests passed!")
        else:
            print(f"Some tests failed: {sum(not r for r in results)} failed")
        print("=" * 60)
    except Exception as e:
        print(f"\nTest error: {e}")
        import traceback
        traceback.print_exc()
