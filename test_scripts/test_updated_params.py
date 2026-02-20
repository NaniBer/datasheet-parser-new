#!/usr/bin/env python3
"""Test schematic builder with updated parameters."""

from src.schematic_generator import build_schematic_from_pin_data

# Manual NE555 pins
NE555_PINS = [
    {"number": "1", "name": "GND"},
    {"number": "2", "name": "TRIG"},
    {"number": "3", "name": "OUT"},
    {"number": "4", "name": "RESET"},
    {"number": "5", "name": "CV"},
    {"number": "6", "name": "THR"},
    {"number": "7", "name": "DIS"},
    {"number": "8", "name": "VCC"},
]

print("Testing schematic with updated parameters...")
result = build_schematic_from_pin_data(
    pin_data=NE555_PINS,
    output_path="output/NE555_schematic.glb"
)

if result:
    print(f"  Success! GLB generated")
else:
    print(f"  Failed to generate schematic")
EOF
