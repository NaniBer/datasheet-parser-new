"""
Direct Schematic Builder Test for TQFP Package
Tests schematic generation directly with TQFP pin data (no LLM extraction needed).
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.models.pin_data import PinData, Pin, PackageInfo
from src.schematic_generator import build_schematic_from_pin_data


# Sample TQFP pin data (ATmega328P or similar 32-pin TQFP)
# Based on typical ATmega328P TQFP-32 pinout
TQFP_PINS = [
    Pin(number=1, name="PD3", function="SPI MOSI"),
    Pin(number=2, name="PD4", function="SPI MISO"),
    Pin(number=3, name="PD5", function="SPI SCK"),
    Pin(number=4, name="PD6", function=""),
    Pin(number=5, name="PD7", function=""),
    Pin(number=6, name="PC6", function=""),
    Pin(number=7, name="PC7", function=""),
    Pin(number=8, name="PC8", function=""),
    Pin(number=9, name="PC9", function=""),
    Pin(number=10, name="PC10", function=""),
    Pin(number=11, name="PC11", function=""),
    Pin(number=12, name="PC12", function=""),
    Pin(number=13, name="PC13", function=""),
    Pin(number=14, name="PC14", function=""),
    Pin(number=15, name="PC15", function=""),
    Pin(number=16, name="PC16", function=""),
    Pin(number=17, name="PC17", function=""),
    Pin(number=18, name="PC18", function=""),
    Pin(number=19, name="PC19", function=""),
    Pin(number=20, name="PC20", function=""),
    Pin(number=21, name="PC21", function=""),
    Pin(number=22, name="PC22", function=""),
    Pin(number=23, name="PC23", function=""),
    Pin(number=24, name="PC24", function=""),
    Pin(number=25, name="PC25", function=""),
    Pin(number=26, name="PC26", function=""),
    Pin(number=27, name="PC27", function=""),
    Pin(number=28, name="PC28", function=""),
    Pin(number=29, name="PC29", function=""),
    Pin(number=30, name="PC30", function=""),
    Pin(number=31, name="AREF", function="Analog Reference"),
    Pin(number=32, name="GND", function="Ground"),
]


def main():
    print("=" * 70)
    print("DIRECT SCHEMATIC BUILDER TEST - TQFP PACKAGE")
    print("=" * 70)
    print()

    print("Sample TQFP Pin Data (32 pins):")
    print("-" * 70)
    print(f"{'Pin':<6} {'Name':<15} {'Function':<20}")
    print("-" * 70)
    for pin in TQFP_PINS:
        function_str = pin.function if pin.function else ""
        print(f"{pin.number:<6} {pin.name:<15} {function_str:<20}")

    print()
    print("-" * 70)

    # Create PinData object
    pin_data = PinData(
        component_name="ATmega328P",
        package=PackageInfo(
            type="TQFP",
            pin_count=32,
            width=7.0,   # Typical TQFP-32 width
            height=7.0,  # Typical TQFP-32 height
            pitch=0.8,   # TQFP typical pitch
            thickness=1.0,
        ),
        pins=TQFP_PINS,
        extraction_method="sample_data",
    )

    print("Testing schematic generation...")
    print("-" * 70)

    try:
        # Generate schematic
        output_path = "output/test_tqfp_direct.glb"
        result = build_schematic_from_pin_data(
            pin_data=pin_data,
            output_path=output_path,
        )

        if result:
            print(f"✅ Schematic generated: {output_path}")
            print()
            print("To view the schematic:")
            print(f"  1. Open a 3D viewer (e.g., https://3dviewer.net)")
            print(f"  2. Upload or drag-and-drop: {output_path}")
            print()
            print("TQFP Package Features in Schematic:")
            print("  • 32 pins distributed on all 4 sides")
            print("  • Pin 1-8: Left side (top to bottom)")
            print("  • Pin 9-16: Bottom side (left to right)")
            print("  • Pin 17-24: Right side (bottom to top)")
            print("  • Pin 25-32: Top side (right to left)")
            print("  • Counter-clockwise numbering starting from top-left")
            print("  • Character stacking for top/bottom pins (no rotation)")
            print("  • Pin names OUTSIDE, pin numbers INSIDE for top/bottom")
        else:
            print("❌ Schematic generation failed")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
