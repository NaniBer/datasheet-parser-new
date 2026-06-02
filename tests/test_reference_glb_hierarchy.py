"""Integration tests for reference hierarchy similarity checks."""

from pathlib import Path

from src.core.reference_glb_hierarchy import validate_glb_similarity_to_reference
from src.schematic_generator.pcb_footprint_builder import build_pcb_footprint


def test_generated_dip8_is_similar_to_reference_2d_glb(tmp_path):
    """DIP workflow output should stay structurally similar to 2d.glb."""
    output_path = tmp_path / "dip8_reference_similarity.glb"
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

    is_similar, errors = validate_glb_similarity_to_reference(str(output_path))
    assert is_similar, errors


def test_generated_dip28_matches_reference_2d_glb_structure(tmp_path):
    """A 28-pin DIP export should match the reference 2d.glb hierarchy."""
    output_path = tmp_path / "dip28_reference_similarity.glb"
    pins = [
        {"number": pin_number, "name": f"PIN{pin_number}"}
        for pin_number in range(1, 29)
    ]

    assert build_pcb_footprint("DIP-28", 28, "GENERIC28", pins, str(output_path))

    is_similar, errors = validate_glb_similarity_to_reference(str(output_path))
    assert is_similar, errors


def test_reference_file_is_self_similar():
    """Sanity check that the reference file validates against itself."""
    reference_path = Path(__file__).resolve().parents[1] / "2d.glb"

    is_similar, errors = validate_glb_similarity_to_reference(
        str(reference_path),
        str(reference_path),
    )
    assert is_similar, errors
