#!/usr/bin/env python3
"""Schematic design visualization."""

# Layout data from Vision API (38 pins)
layout_sections = {
    "left_side": list(range(1, 15)),      # Pins 1-14
    "bottom_edge": list(range(15, 25)),    # Pins 15-24
    "right_side": list(range(25, 39)),    # Pins 25-38
}

# Pin names from LLM
pin_names = {
    1: "GND", 2: "3V3", 3: "EN", 4: "SENSOR_VP", 5: "SENSOR_VN",
    6: "IO34", 7: "IO35", 8: "IO32", 9: "IO33", 10: "IO25",
    11: "IO26", 12: "IO27", 13: "IO14", 14: "IO12",
    15: "GND+1", 16: "IO13+1", 17: "NC+1", 18: "NC+1",
    19: "NC+1", 20: "NC+1", 21: "NC+1", 22: "NC+1",
    23: "IO15+1", 24: "IO2+1", 25: "GND+1", 26: "IO13+1",
    27: "IO16+1", 28: "IO17+1", 29: "IO5+1", 30: "IO18+1",
    31: "IO19+1", 32: "NC+1", 33: "IO21+1", 34: "RXD0",
    35: "TXD0", 36: "IO22+1", 37: "IO23+1", 38: "GND+1"
}

print("=" * 70)
print("SCHEMATIC DESIGN - 3-Side Grid Layout")
print("=" * 70)
print()

# Left Side
print("LEFT SIDE (Column 1, Pins 1-14)")
print("-" * 70)
for pin in layout_sections["left_side"]:
    name = pin_names.get(pin, "Unknown")
    print(f"  Pin {pin:>2}  {name}")
print()

# Bottom Edge
print("BOTTOM EDGE (Pins 15-24)")
print("-" * 70)
for pin in layout_sections["bottom_edge"]:
    name = pin_names.get(pin, "Unknown")
    print(f"  Pin {pin:>2}  {name}")
print()

# Right Side
print("RIGHT SIDE (Column 2, Pins 25-38)")
print("-" * 70)
for pin in layout_sections["right_side"]:
    name = pin_names.get(pin, "Unknown")
    print(f"  Pin {pin:>2}  {name}")
print()

print("=" * 70)
print("LAYOUT VISUALIZATION")
print("=" * 70)
print()

# Create ASCII art representation
print("       Top Edge (Empty)")
print("         " + "-" * 40)
print()

# Left side pins (vertical)
left_pins = [pin_names.get(pin, f"P{pin}")[:5] for pin in layout_sections["left_side"]]
print("Left Side:")
print("  " + "│")
for pin_name in left_pins:
    print(f"  │  {pin_name}")
print("  " + "│")
print()

# Bottom edge pins (horizontal)
bottom_pins = [pin_names.get(pin, f"P{pin}")[:5] for pin in layout_sections["bottom_edge"]]
print("Bottom Edge:")
print("  └" + "─" * 40 + "┘")
bottom_row = "  │ " + " ".join(bottom_pins[:6]) + "  │"
print(bottom_row)
if len(bottom_pins) > 6:
    bottom_row2 = "  │ " + " ".join(bottom_pins[6:12]) + "  │"
    print(bottom_row2)
if len(bottom_pins) > 12:
    bottom_row3 = "  │ " + " ".join(bottom_pins[12:18]) + "  │"
    print(bottom_row3)
print("  ┌" + "─" * 40 + "┐")
print()

# Right side pins (vertical)
right_pins = [pin_names.get(pin, f"P{pin}")[:5] for pin in layout_sections["right_side"]]
print("Right Side:")
print("  " + "│")
for pin_name in right_pins:
    print(f"  │  {pin_name}")
print("  " + "│")
print()

print("=" * 70)
print("COMPLETE: 38 Pins on 3 sides (Grid Layout)")
print("=" * 70)
