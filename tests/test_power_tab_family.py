"""Upstream recognition of power-tab families (TO-220 / DPAK / D2PAK / TO-247).

`_family()` used to return None for these, so a real PDF's power-tab part never
reached the 3D body layer. It must now classify them into a stable family token
WITHOUT `get_footprint_defaults()` fabricating an (inevitably wrong) SMD/DIP pad
grid for a tab package.
"""

import pytest

from src.package_types.footprint_defaults import _family, get_footprint_defaults


@pytest.mark.parametrize(
    "package_type, expected_family",
    [
        ("TO-220", "TO220"),
        ("TO220", "TO220"),
        ("TO-252", "DPAK"),
        ("TO252", "DPAK"),
        ("DPAK", "DPAK"),
        ("D2PAK", "D2PAK"),
        ("TO-263", "D2PAK"),
        ("TO263", "D2PAK"),
        ("TO-247", "TO247"),
        ("TO247", "TO247"),
    ],
)
def test_power_tab_family_recognized(package_type, expected_family):
    assert _family(package_type) == expected_family


@pytest.mark.parametrize(
    "package_type",
    ["TO-220", "TO220", "TO-252", "DPAK", "D2PAK", "TO-263", "TO-247"],
)
def test_power_tab_has_no_fabricated_footprint(package_type):
    # Recognition only: no tabulated pad grid, so the footprint builder never
    # invents an SMD/DIP layout for a tab package.
    assert get_footprint_defaults(package_type, 3) is None


@pytest.mark.parametrize(
    "package_type, expected_family",
    [
        ("SOIC-8", "SOIC"),
        ("TSSOP16", "TSSOP"),
        ("SSOP20", "SSOP"),
        ("QFN-32", "QFN"),
        ("DIP-8", "DIP"),
        ("BGA-64", "BGA"),
        ("LGA-16", "LGA"),
    ],
)
def test_existing_families_unchanged(package_type, expected_family):
    assert _family(package_type) == expected_family
