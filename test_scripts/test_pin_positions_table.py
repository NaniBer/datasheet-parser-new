#!/usr/bin/env python3
"""Test pin position calculation with 74HC595 table data directly."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.chat_bot import build_table_extraction_prompt, get_completion_from_messages
from src.schematic_generator.package_geometry import get_schematic_parameters, calculate_pin_position

# Table data from 74HC595 datasheet (same as before)
table_data = """
[
  ["PIN", "I/O(1)", "DESCRIPTION"],
  ["NAME", "SOIC, PDIP, SO, CDIP, SSOP, or TSSOP", "LCCC"],
  ["GND", "8", "10", "\u2014", "Ground Pin"],
  ["OE", "13", "17", "I", "Output Enable"],
  ["QA", "15", "19", "O", "QA Output"],
  ["QB", "1", "2", "O", "QB Output"],
  ["QC", "2", "3", "O", "QC Output"],
  ["QD", "3", "4", "O", "QD Output"],
  ["QE", "4", "5", "O", "QE Output"],
  ["QF", "5", "7", "O", "QF Output"],
  ["QG", "6", "8", "O", "QG Output"],
  ["QH", "7", "9", "O", "QH Output"],
  ["QH'", "9", "12", "O", "QH' Output"],
  ["RCLK", "12", "14", "I", "RCLK Input"],
  ["SER", "14", "18", "I", "SER Input"],
  ["SRCLK", "11", "14", "I", "SRCLK Input"],
  ["SRCLR", "10", "13", "I", "SRCLR Input"],
  ["NC", "\u2014", "1", "\u2014", "No Connection"],
  ["16"],
  ["11"],
  ["16"],
  ["VCC", "\u2014", "20", "\u2014", "Power Pin"]
]
"""

print("=" * 80)
print("Testing Pin Position Calculation with 74HC595 Table Data")
print("=" * 80)

# Step 1: Extract with LLM using table data
print("\nStep 1: Extracting pin data from table...")
messages = build_table_extraction_prompt(table_data.strip())
response = get_completion_from_messages(messages)

# Parse response
import json
clean_response = response.strip()
if clean_response.startswith("```json"):
    clean_response = clean_response[7:]
if clean_response.startswith("```"):
    clean_response = clean_response[3:]
if clean_response.endswith("```"):
    clean_response = clean_response[:-3]
clean_response = clean_response.strip()

data = json.loads(clean_response)

print(f"\n✅ Extraction successful!")
print(f"Component: {data.get('component_name', 'Unknown')}")

# Step 2: Test with each package variant
if 'packages' in data:
    packages_list = data['packages']
    print(f"Number of packages: {len(packages_list)}")

    for i, pkg_data in enumerate(packages_list, 1):
        print(f"\n{'=' * 80}")
        print(f"Package {i}: {pkg_data['type']}")
        print("=" * 80)

        pkg_type = pkg_data['type']
        pin_count = pkg_data['pin_count']
        pins = pkg_data['pins']

        print(f"Pin count: {pin_count}")
        print(f"Pins extracted: {len(pins)}")

        # Get package geometry parameters
        try:
            params = get_schematic_parameters(pkg_type, pin_count)
            print(f"\n✅ Package parameters found:")
            print(f"  Package type: {params.package_type}")
            print(f"  Body width: {params.body_width} mm")
            print(f"  Body height: {params.body_height} mm")
            print(f"  Pin pitch: {params.pin_pitch} mm")
            print(f"  Pins per side: {params.pins_per_side}")
            print(f"  Counter-clockwise: {params.counter_clockwise}")

            # Calculate positions for all pins
            print(f"\n📍 Pin positions calculated:")

            # Sort pins by pin number to get correct indices
            sorted_pins = sorted(pins, key=lambda p: p['number'])

            for j, pin in enumerate(sorted_pins, 1):  # Show all pins
                pin_number = pin['number']
                pin_index = j - 1  # 0-based index in sorted list

                # Calculate position
                x, y, side = calculate_pin_position(pin_index, params)

                print(f"  Pin {pin_number:2d}: ({x:7.2f}, {y:7.2f}) {side:6s} - {pin['name']:8s}")

        except Exception as e:
            print(f"\n❌ Error calculating positions: {e}")
            import traceback
            traceback.print_exc()

else:
    print("\n❌ No packages found (got legacy format)")
