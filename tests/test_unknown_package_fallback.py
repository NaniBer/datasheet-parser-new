"""Smoke tests for package families that are not explicitly modeled."""

from pathlib import Path

import pytest

from src.core import validate_pcb_footprint_glb
from src.schematic_generator import build_pcb_footprint


@pytest.mark.parametrize(
    "package_type,pin_count",
    [
        ("WSON-8", 8),
        ("SOT-23-6", 6),
        ("WLCSP-8", 8),
        ("SON-10", 10),
    ],
)
def test_unknown_package_families_still_generate_valid_footprints(
    tmp_path,
    package_type,
    pin_count,
):
    """Undefined package labels should still fall back to a valid generic footprint."""
    output_path = tmp_path / f"{package_type.lower().replace('-', '_')}.glb"
    pin_data = [
        {"number": pin_number, "name": f"PIN{pin_number}"}
        for pin_number in range(1, pin_count + 1)
    ]

    assert build_pcb_footprint(
        package_type,
        pin_count,
        "TEST",
        pin_data,
        str(output_path),
    )

    is_valid, errors = validate_pcb_footprint_glb(
        str(output_path),
        pin_count=pin_count,
        through_hole=False,
    )
    assert is_valid, errors

    assert output_path.exists()
    assert output_path.stat().st_size > 0

