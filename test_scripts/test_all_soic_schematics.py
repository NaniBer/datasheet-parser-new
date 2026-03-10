#!/usr/bin/env python3
"""
Test script to generate schematics for all SOIC packages.

Usage:
    python test_all_soic_schematics.py

This script will find all SOIC*_test.json files in the pins directory
and generate schematics for each.
"""

import json
import sys
from pathlib import Path
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.schematic_generator.schematic_builder import build_schematic_from_pin_data


def find_soic_pin_files():
    """Find all SOIC pin definition files."""
    pins_dir = Path(__file__).parent.parent / "pins"
    return sorted(pins_dir.glob("SOIC*_test.json"))


def test_single_soic(pins_json: str):
    """
    Load pins from JSON and generate schematic.

    Args:
        pins_json: Path to JSON file with extracted pins

    Returns:
        bool: True if successful, False otherwise
    """
    print(f"Processing: {pins_json}")

    # Load pins from JSON
    with open(pins_json, 'r') as f:
        data = json.load(f)

    component_name = data.get("component_name", "Unknown")
    package_type = data.get("package_type", "SOIC")
    pin_count = data.get("pin_count", 8)
    pins = data.get("pins", [])

    print(f"  Component: {component_name}")
    print(f"  Package: {package_type}")
    print(f"  Pin count: {pin_count}")

    # Set output path
    input_path = Path(pins_json)
    output_glb = input_path.parent / "output" / f"{input_path.stem}_schematic.glb"

    # Ensure output directory exists
    output_path = Path(output_glb)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Generate schematic
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
        # Show file size
        if output_path.exists():
            size_mb = output_path.stat().st_size / (1024 * 1024)
            print(f"  ✅ Success in {elapsed:.2f}s ({size_mb:.2f} MB)")
        else:
            print(f"  ✅ Success in {elapsed:.2f}s")
    else:
        print(f"  ❌ Failed")

    print()
    return success


def main():
    """Run schematic generation for all SOIC packages."""
    print("=" * 60)
    print("SOIC Schematic Generation Test")
    print("=" * 60)
    print()

    soic_files = find_soic_pin_files()

    if not soic_files:
        print("No SOIC pin files found in pins/ directory")
        return

    print(f"Found {len(soic_files)} SOIC package(s) to test:")
    for f in soic_files:
        print(f"  - {f.name}")
    print()
    print("-" * 60)
    print()

    results = []
    for pins_file in soic_files:
        success = test_single_soic(str(pins_file))
        results.append((pins_file.name, success))

    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    for filename, success in results:
        status = "✅" if success else "❌"
        print(f"  {status} {filename}")

    total = len(results)
    passed = sum(1 for _, s in results if s)
    print()
    print(f"Total: {passed}/{total} passed")


if __name__ == "__main__":
    main()
