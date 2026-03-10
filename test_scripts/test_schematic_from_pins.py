#!/usr/bin/env python3
"""
Fast schematic testing script.

Loads saved pins from JSON and generates schematic.
Use this for fast iterations when modifying schematic builder.
"""
import json
import sys
import re
from pathlib import Path
import time
import os

# Add project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Use absolute import from project root
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
    # Parse package type from string like "QFN-32" or "TQFP-44"
    package_str = data.get("package_type", "DIP-8")
    pin_count_str = data.get("pin_count", "8")

    # Try to extract package type and pin count from combined string
    # Format: "QFN-32", "TQFP-44", "DIP-8", etc.
    package_match = re.match(r'([A-Z]+)-(\d+)', package_str)
    if package_match:
        package_type = package_match.group(1)
        pin_count = int(package_match.group(2))
        print(f" Parsed package: {package_type}-{pin_count}")
    else:
        # Use values directly from JSON (fallback to hardcoded defaults if needed)
        if "-" not in package_str:
            try:
                parts = package_str.split("-")
                if len(parts) >= 2:
                    package_type = parts[0]
                    pin_count = int(parts[1])
                    print(f" Parsed package (hyphen): {package_type}-{pin_count}")
            except Exception:
                pass

        # Fallback to values from JSON
        package_type = package_str
        pin_count = pin_count_str
        print(f" Using package_type from JSON: {package_type}-{pin_count}")

    pins = data.get("pins", [])
    print(f" Component: {component_name}")
    print(f" Package: {package_type}")
    print(f" Pin count: {pin_count}")
    print(f" Pins to build: {len(pins)}")
    print()

    # Set default output path
    if output_glb is None:
        input_path = Path(pins_json)
        output_glb = input_path.parent / "output" / f"{input_path.stem}_schematic.glb"
    else:
        output_glb = Path(output_glb)

    # Ensure output directory exists
    output_glb.parent.mkdir(parents=True, exist_ok=True)

    # Generate schematic
    print("Building schematic...")
    print(f" Output: {output_glb}")
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
        print(f"Success in {elapsed:.2f} seconds")
        print(f"   File: {output_glb}")

        # Show file size
        if output_glb.exists():
            size_mb = output_glb.stat().st_size / (1024 * 1024)
            print(f"   Size: {size_mb:.2f} MB")
    else:
        print("Failed to generate schematic")
        print("=" * 60)

    print("Usage:")
    print(" python test_schematic_from_pins.py <pins_json> [output_glb]")
    print()
    print("Example:")
    print("  python test_schematic_from_pins.py pins/NE555_pins.json")
    print("  python test_schematic_from_pins.py pins/NE555_pins.json output/test.glb")
    print()
    print("Workflow:")
    print(" 1. Run once: python save_pins_from_pdf.py pdfs/NE555.PDF pins/NE555_pins.json")
    print(" 2. Test fast: python test_schematic_from_pins.py pins/NE555_pins.json")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_schematic_from_pins.py <pins_json> [output_glb]")
        print()
        sys.exit(1)
    pins_json = sys.argv[1]
    output_glb = sys.argv[2] if len(sys.argv) > 2 else None
    test_schematic_from_pins(pins_json, output_glb)
