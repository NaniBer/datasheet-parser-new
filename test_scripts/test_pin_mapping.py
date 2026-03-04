"""
Test script to debug pin mapping and positions.
"""

import sys
import os

# Add parent directory to path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parent_dir)

from src.schematic_generator.package_geometry import get_schematic_parameters, PackageType
from src.schematic_generator.pin_layout import layout_pins

# Test DIP-8
params = get_schematic_parameters("DIP-8", 8)
pin_positions = layout_pins(params)

print("=" * 60)
print("DIP-8 Pin Positions")
print("=" * 60)
print(f"Package type: {params.package_type}")
print(f"Pin count: {params.pin_count}")
print(f"Body width: {params.body_width}")
print(f"Body height: {params.body_height}")
print(f"Pin pitch: {params.pin_pitch}")
print()

print("Pin positions:")
print("-" * 60)
for pos in pin_positions:
    print(f"  Pin {pos.pin_number}: x={pos.x:.2f}, y={pos.y:.2f}, side={pos.side}, rotation={pos.rotation}")

print()

# Test with NE555 pin data (from LLM output)
ne555_pins = [
    {"number": 1, "name": "GND"},
    {"number": 2, "name": "TRIGGER"},
    {"number": 3, "name": "OUTPUT"},
    {"number": 4, "name": "RESET"},
    {"number": 5, "name": "CONTROL VOLTAGE"},
    {"number": 6, "name": "THRESHOLD"},
    {"number": 7, "name": "DISCHARGE"},
    {"number": 8, "name": "VCC"},
]

print("NE555 Pin Mapping:")
print("-" * 60)

# Create mapping
pin_number_to_position = {
    pos.pin_number: pos for pos in pin_positions
}

for pin in ne555_pins:
    pin_num = str(pin["number"])
    pin_name = pin["name"]
    pos = pin_number_to_position.get(pin_num)
    if pos:
        print(f"  Pin {pin_num} ({pin_name}): x={pos.x:.2f}, y={pos.y:.2f}, side={pos.side}")
    else:
        print(f"  Pin {pin_num} ({pin_name}): NO POSITION!")
