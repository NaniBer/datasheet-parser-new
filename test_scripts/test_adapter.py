#!/usr/bin/env python3
"""Test adapter module."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.models.pin_data import PinData, Pin, PackageInfo
from src.schematic_generator.adapter import (
    pin_data_to_builder_format,
    build_schematic_from_pin_data,
)


def test_adapter():
    """Test PinData to builder format conversion."""
    print("Testing PinData to builder format conversion...")
    
    # Create sample PinData
    pin_data = PinData(
        component_name="NE555",
        package=PackageInfo(type="DIP-8", pin_count=8, width=10.0, height=20.0),
        pins=[
            Pin(number="1", name="GND"),
            Pin(number="2", name="TRIG"),
            Pin(number="3", name="OUT"),
            Pin(number="4", name="RESET"),
            Pin(number="5", name="CV"),
            Pin(number="6", name="THR"),
            Pin(number="7", name="DIS"),
            Pin(number="8", name="VCC"),
        ],
        extraction_method="llm"
    )
    
    # Convert to builder format
    pkg_type, count, name, pins = pin_data_to_builder_format(pin_data)
    
    print(f"  Package type: {pkg_type}")
    print(f"  Pin count: {count}")
    print(f"  Component name: {name}")
    print(f"  Pin list length: {len(pins)}")
    
    # Verify conversion
    assert pkg_type == "DIP-8"
    assert count == 8
    assert name == "NE555"
    assert len(pins) == 8
    assert pins[0] == {"number": "1", "name": "GND"}
    assert pins[7] == {"number": "8", "name": "VCC"}
    
    print("\n  All assertions passed!")
    return True


if __name__ == '__main__':
    print("=" * 60)
    print("Adapter Module Test")
    print("=" * 60)
    
    try:
        test_adapter()
        print("\n" + "=" * 60)
        print("Test passed!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\nAssertion failed: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
