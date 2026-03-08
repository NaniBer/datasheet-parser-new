#!/usr/bin/env python3
"""
Fast schematic testing script.

Loads saved pins from JSON and generates schematic.
Use this for fast iterations when modifying schematic builder.

Run after save_pins_from_pdf.py to extract pins once.
"""

import json
import sys
from pathlib import Path
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.schematic_generator.schematic_builder import build_schematic_from_pin_data


def test_schematic_from_pins(pins_json: str, output_glb: str = None):
    """
    Load pins from JSON and generate schematic.

    Args:
        pins_json: Path to JSON file with extracted pins
        output_glb: Path to save GLB (default: derived from pins_json)
    """
    print("=" * 60)
    print("Fast Schematic Test")
    print("=" * 60)

    # Load pins from JSON
    print(f"Loading pins from: {pins_json}")
    with open(pins_json, 'r') as f:
        data = json.load(f)

    component_name = data.get("component_name", "Unknown")
    package_type = data.get("package_type", "DIP-8")
    pin_count = data.get("pin_count", 8)
    pins = data.get("pins", [])

    print(f"  Component: {component_name}")
    print(f"  Package: {package_type}")
    print(f"  Pin count: {pin_count}")
    print(f"  Pins to build: {len(pins)}")
    print()

    # Set default output path
    if output_glb is None:
        input_path = Path(pins_json)
        output_glb = input_path.parent / "output" / f"{input_path.stem}_schematic.glb"

    # Ensure output directory exists
    output_path = Path(output_glb)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate schematic
    print("Building schematic...")
    print(f"  Output: {output_glb}")
    print()

    start_time = time.time()
    success = build_schematic_from_pin_data(
        package_type=package_type,
        pin_count=pin_count,
        component_name=component_name,
        pin_data=pins,
        output_path=str(output_glb)
    )
    elapsed = time.time() - start_time

    if success:
        print(f"✅ Success in {elapsed:.2f} seconds")
        print(f"   File: {output_glb}")

        # Show file size
        if output_path.exists():
            size_mb = output_path.stat().st_size / (1024 * 1024)
            print(f"   Size: {size_mb:.2f} MB")
    else:
        print("❌ Failed to generate schematic")

    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_schematic_from_pins.py <pins_json> [output_glb]")
        print()
        print("Example:")
        print("  python test_schematic_from_pins.py pins/NE555_pins.json")
        print("  python test_schematic_from_pins.py pins/NE555_pins.json output/test.glb")
        print()
        print("Workflow:")
        print("  1. Run once: python save_pins_from_pdf.py pdfs/NE555.PDF pins/NE555_pins.json")
        print("  2. Test fast: python test_schematic_from_pins.py pins/NE555_pins.json")
        print("  3. Repeat step 2 as you modify schematic builder")
        sys.exit(1)

    pins_json = sys.argv[1]
    output_glb = sys.argv[2] if len(sys.argv) > 2 else None

    test_schematic_from_pins(pins_json, output_glb)
