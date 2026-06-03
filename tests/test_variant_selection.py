"""Tests for package variant selection."""

import pytest

from src.models.pin_data import PinData
from src.llm.client import LLMClient
from src.pdf_extractor.variant_selection import select_package_variant
from src.schematic_generator.adapter import pin_data_to_builder_format


def test_select_package_variant_uses_llm_selected_index():
    """The extractor should respect the selected package index when present."""
    pin_data = PinData(
        component_name="74HC595",
        packages=[
            {"type": "PDIP-16", "pin_count": 16, "pins": [{"number": 1, "name": "A"}]},
            {"type": "SOIC-16", "pin_count": 16, "pins": [{"number": 1, "name": "B"}]},
        ],
        selected_package_index=1,
        selected_package_type="SOIC-16",
        selection_reason="Target part number matched the SOIC variant",
        extraction_method="Table",
    )

    selection = select_package_variant(pin_data)

    assert selection.index == 1
    assert selection.package["type"] == "SOIC-16"
    assert "Target part number" in selection.reason


def test_pin_data_to_builder_format_respects_selected_variant():
    """The schematic adapter should use the selected package variant."""
    pin_data = PinData(
        component_name="74HC595",
        packages=[
            {"type": "PDIP-16", "pin_count": 16, "pins": [{"number": 1, "name": "A"}]},
            {"type": "SOIC-16", "pin_count": 16, "pins": [{"number": 1, "name": "B"}]},
        ],
        selected_package_index=1,
        selected_package_type="SOIC-16",
        extraction_method="Table",
    )

    package_type, pin_count, component_name, pins = pin_data_to_builder_format(pin_data)

    assert package_type == "SOIC-16"
    assert pin_count == 16
    assert component_name == "74HC595"
    assert pins == [{"number": "1", "name": "B"}]


def test_llm_client_parses_selected_variant_metadata():
    """The LLM client should preserve variant-selection metadata from JSON."""
    response = """
    {
      "component_name": "74HC595",
      "packages": [
        {"type": "PDIP-16", "pin_count": 16, "pins": [{"number": 1, "name": "A"}]},
        {"type": "SOIC-16", "pin_count": 16, "pins": [{"number": 1, "name": "B"}]}
      ],
      "selected_package_index": 1,
      "selected_package_type": "SOIC-16",
      "selection_reason": "Target part number matches the SOIC package",
      "extraction_method": "Table"
    }
    """

    pin_data = LLMClient()._parse_llm_response(response)

    assert pin_data.selected_package_index == 1
    assert pin_data.selected_package_type == "SOIC-16"
    assert "SOIC" in (pin_data.selection_reason or "")


def test_llm_client_drops_non_pin_feature_rows():
    """Thermal pads should be filtered out before validation and geometry."""
    response = """
    {
      "component_name": "TPS62160",
      "package": {
        "type": "QFN-8",
        "pin_count": 8,
        "width": 4.0,
        "height": 4.0,
        "pitch": 0.5
      },
      "pins": [
        {"number": 1, "name": "VIN", "function": "power"},
        {"number": 2, "name": "EN", "function": "input"},
        {"number": 3, "name": "GND", "function": "ground"},
        {"number": 4, "name": "SW", "function": "output"},
        {"number": 5, "name": "PG", "function": "output"},
        {"number": 6, "name": "VOS", "function": "input"},
        {"number": 7, "name": "FB", "function": "input"},
        {"number": 8, "name": "PGND", "function": "ground"},
        {"number": 9, "name": "Exposed Thermal Pad", "function": "ground"}
      ],
      "extraction_method": "Table"
    }
    """

    pin_data = LLMClient()._parse_llm_response(response)

    assert pin_data.package is not None
    assert len(pin_data.pins or []) == 8
    assert all("thermal pad" not in pin.name.lower() for pin in pin_data.pins or [])


def test_select_package_variant_rejects_ambiguous_multi_package_data():
    """Multiple packages without selection metadata should fail closed."""
    pin_data = PinData(
        component_name="74HC595",
        packages=[
            {"type": "PDIP-16", "pin_count": 16, "pins": [{"number": 1, "name": "A"}]},
            {"type": "SOIC-16", "pin_count": 16, "pins": [{"number": 1, "name": "B"}]},
        ],
        extraction_method="Table",
    )

    with pytest.raises(ValueError, match="(?i)multiple package variants"):
        select_package_variant(pin_data)
