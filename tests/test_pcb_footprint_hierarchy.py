"""Integration tests for PCB footprint hierarchy output."""

from pathlib import Path

from pygltflib import GLTF2

from src.core.pcb_footprint_hierarchy import validate_pcb_footprint_hierarchy
from src.schematic_generator.pcb_footprint_builder import build_pcb_footprint


def test_dip8_footprint_matches_documented_hierarchy(tmp_path):
    """Generated DIP footprints should follow docs/PCB_FOOTPRINT_HIERARCHY.md."""
    output_path = tmp_path / "ne555_dip8.glb"
    pins = [
        {"number": 1, "name": "GND"},
        {"number": 2, "name": "TRIG"},
        {"number": 3, "name": "OUT"},
        {"number": 4, "name": "RESET"},
        {"number": 5, "name": "CTRL"},
        {"number": 6, "name": "THRES"},
        {"number": 7, "name": "DISCH"},
        {"number": 8, "name": "VCC"},
    ]

    assert build_pcb_footprint("DIP-8", 8, "NE555", pins, str(output_path))

    gltf = GLTF2().load_binary(str(output_path))
    errors = validate_pcb_footprint_hierarchy(
        gltf,
        pin_count=8,
        through_hole=True,
    )

    assert errors == []

