"""Tests for extraction hardening helpers."""

from src.chat_bot import build_pin_extraction_prompt, build_table_extraction_prompt
from src.models.pin_data import PackageInfo, Pin, PinData
from src.pdf_extractor.extraction_validator import validate_pin_data_extraction
from src.pdf_extractor.part_number_hint import infer_part_number_hint


def test_infer_part_number_hint_prefers_datasheet_text():
    """The part-number heuristic should prefer repeated document text."""
    text_content = (
        "--- Page 1 ---\n"
        "NE555 Timer\n"
        "Pin Configuration and Functions\n\n"
        "--- Page 2 ---\n"
        "NE555\n"
    )

    assert infer_part_number_hint(text_content, source_name="foo.pdf") == "NE555"


def test_pin_extraction_prompts_include_target_and_retry_feedback():
    """Prompt builders should surface the target part number and retry feedback."""
    pin_prompt = build_pin_extraction_prompt(
        "sample content",
        part_number="SN74HC595DR",
        validation_feedback="Fix the pin count",
    )
    table_prompt = build_table_extraction_prompt(
        "[[\"PIN\", \"NAME\"]]",
        part_number="SN74HC595DR",
        validation_feedback="Fix the pin count",
    )

    assert any("SN74HC595DR" in message["content"] for message in pin_prompt)
    assert any("Fix the pin count" in message["content"] for message in pin_prompt)
    assert any("SN74HC595DR" in message["content"] for message in table_prompt)
    assert any("Fix the pin count" in message["content"] for message in table_prompt)
    assert any("selected_package_index" in message["content"] for message in pin_prompt)
    assert any("selected_package_index" in message["content"] for message in table_prompt)


def test_validate_pin_data_extraction_rejects_bad_pin_sequence():
    """Structural validation should reject duplicate and incomplete pin maps."""
    pin_data = PinData(
        component_name="NE555",
        package=PackageInfo(type="DIP", pin_count=4, width=5.0, height=5.0),
        pins=[
            Pin(number=1, name="VCC"),
            Pin(number=1, name="DUPLICATE"),
            Pin(number=3, name="OUT"),
            Pin(number=4, name="GND"),
        ],
        extraction_method="Table",
    )

    result = validate_pin_data_extraction(pin_data, part_number="NE555")

    assert not result.is_valid
    assert any("duplicate pin number 1" in error.lower() for error in result.errors)


def test_validate_pin_data_extraction_rejects_thermal_pad_as_pin():
    """Thermal/exposed pads should not be counted as electrical pins."""
    pin_data = PinData(
        component_name="TPS62160",
        package=PackageInfo(type="QFN", pin_count=9, width=4.0, height=4.0),
        pins=[
            Pin(number=1, name="VIN"),
            Pin(number=2, name="EN"),
            Pin(number=3, name="GND"),
            Pin(number=4, name="SW"),
            Pin(number=5, name="PG"),
            Pin(number=6, name="VOS"),
            Pin(number=7, name="FB"),
            Pin(number=8, name="PGND"),
            Pin(number=9, name="Exposed Thermal Pad"),
        ],
        extraction_method="Table",
    )

    result = validate_pin_data_extraction(pin_data, part_number="TPS62160")

    assert not result.is_valid
    assert any("non-pin package feature" in error.lower() for error in result.errors)
