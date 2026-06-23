"""
Compare generated schematics in schematic_tests/ against reference files in compare/.
Checks: hierarchy structure, pin count, pin numbers.
"""

import json
import struct
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

COMPONENTS = [
    ("74HC595",   "schematic_tests/74HC595.glb",    "compare/74HC595.glb"),
    ("ATmega328p","schematic_tests/ATmega328p.glb",  "compare/ATmega328p.gltf"),
    ("ESP32-C3",  "schematic_tests/ESP32-C3.glb",    "compare/ESP32-C3.glb"),
    ("MCP3208",   "schematic_tests/MCP3208.glb",     "compare/MCP3208 .glb"),
    ("TL072",     "schematic_tests/TL072.glb",       "compare/TL072.glb"),
    ("AMS1117",   "schematic_tests/AMS1117.glb",     "compare/AMS1117.glb"),
    ("CD4017",    "schematic_tests/CD4017.glb",      "compare/CD4017.glb"),
    ("LM358",     "schematic_tests/LM358.glb",       "compare/LM358 .glb"),
    ("MPU-6000",  "schematic_tests/MPU-6000.glb",    "compare/MPU-6000.gltf"),
]

EXPECTED_TOP_LEVEL = {"DesignatorName", "PackageValue", "BodyLine", "Legs"}
EXPECTED_PIN_CHILDREN = {"leg", "pinPoint", "text", "boundingBox", "pinName"}


def load_nodes(path: str):
    """Load GLTF node list from GLB or GLTF file."""
    p = Path(path)
    if not p.exists():
        return None, f"FILE NOT FOUND: {path}"

    if p.suffix.lower() == ".gltf":
        with open(p) as f:
            data = json.load(f)
        return data.get("nodes", []), None

    # GLB
    with open(p, "rb") as f:
        magic = f.read(4)
        if magic != b"glTF":
            return None, "Not a valid GLB file"
        f.read(8)  # version + length
        chunk_len = struct.unpack("<I", f.read(4))[0]
        chunk_type = f.read(4)
        data = json.loads(f.read(chunk_len))
    return data.get("nodes", []), None


def get_children_names(nodes, idx):
    return [nodes[c].get("name", "") for c in (nodes[idx].get("children") or [])]


def extract_info(nodes):
    """Extract hierarchy and pin numbers from node list."""
    # Find root Package node
    all_children = set()
    for n in nodes:
        for c in n.get("children", []):
            all_children.add(c)
    roots = [i for i in range(len(nodes)) if i not in all_children]

    package_idx = None
    for r in roots:
        if nodes[r].get("name") == "Package":
            package_idx = r
            break
    if package_idx is None:
        # Try any root
        package_idx = roots[0] if roots else None

    if package_idx is None:
        return {}, set(), []

    top_children = get_children_names(nodes, package_idx)

    # Find Legs
    legs_idx = None
    for c in nodes[package_idx].get("children", []):
        if nodes[c].get("name") == "Legs":
            legs_idx = c
            break

    pin_numbers = set()
    pin_child_issues = []
    if legs_idx is not None:
        for pin_idx in nodes[legs_idx].get("children", []):
            pin_name = nodes[pin_idx].get("name", "")
            pin_numbers.add(pin_name)
            # Check pin children
            pin_children = set(get_children_names(nodes, pin_idx))
            missing = EXPECTED_PIN_CHILDREN - pin_children
            if missing:
                pin_child_issues.append(f"pin {pin_name} missing: {missing}")

    return top_children, pin_numbers, pin_child_issues


def compare(name, our_path, ref_path):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")

    our_nodes, our_err = load_nodes(str(ROOT / our_path))
    ref_nodes, ref_err = load_nodes(str(ROOT / ref_path))

    if our_err:
        print(f"  ✗ OUR FILE:  {our_err}")
    if ref_err:
        print(f"  ✗ REF FILE:  {ref_err}")
    if our_err or ref_err:
        return

    our_top, our_pins, our_pin_issues = extract_info(our_nodes)
    ref_top, ref_pins, ref_pin_issues = extract_info(ref_nodes)

    # --- Hierarchy ---
    print(f"\n  HIERARCHY (Package top-level children)")
    our_top_set = set(our_top)
    ref_top_set = set(ref_top)
    missing_keys = ref_top_set - our_top_set
    extra_keys   = our_top_set - ref_top_set
    if not missing_keys and not extra_keys:
        print(f"  ✓ Matches: {sorted(our_top_set)}")
    else:
        print(f"  ✗ Ours:      {sorted(our_top_set)}")
        print(f"    Reference: {sorted(ref_top_set)}")
        if missing_keys: print(f"    Missing:   {sorted(missing_keys)}")
        if extra_keys:   print(f"    Extra:     {sorted(extra_keys)}")

    # --- Pin count ---
    print(f"\n  PIN COUNT")
    if len(our_pins) == len(ref_pins):
        print(f"  ✓ {len(our_pins)} pins")
    else:
        print(f"  ✗ Ours: {len(our_pins)}  |  Reference: {len(ref_pins)}")

    # --- Pin numbers ---
    print(f"\n  PIN NUMBERS")
    missing_pins = ref_pins - our_pins
    extra_pins   = our_pins - ref_pins
    if not missing_pins and not extra_pins:
        print(f"  ✓ All pin numbers match")
    else:
        if missing_pins:
            print(f"  ✗ Missing pins: {sorted(missing_pins, key=lambda x: int(x) if x.isdigit() else x)}")
        if extra_pins:
            print(f"  ✗ Extra pins:   {sorted(extra_pins,   key=lambda x: int(x) if x.isdigit() else x)}")

    # --- Pin children structure ---
    if our_pin_issues:
        print(f"\n  PIN CHILDREN ISSUES")
        for issue in our_pin_issues[:5]:
            print(f"  ✗ {issue}")
    else:
        print(f"\n  PIN CHILDREN STRUCTURE")
        print(f"  ✓ All pins have correct children (leg/pinPoint/text/boundingBox/pinName)")


def main():
    print("SCHEMATIC COMPARISON REPORT")
    print(f"Generated vs Reference")
    for name, our, ref in COMPONENTS:
        compare(name, our, ref)
    print(f"\n{'='*60}")
    print("Done.")


if __name__ == "__main__":
    main()
