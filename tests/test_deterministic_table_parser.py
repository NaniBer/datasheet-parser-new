"""Integration tests for the deterministic table parser path."""

from src.main import detect_relevant_pages, extract_content, extract_pin_data


def _no_llm_call(*args, **kwargs):
    raise AssertionError("LLM extraction should not be called for clean tables")


def _build_content(pdf_path: str, monkeypatch):
    monkeypatch.setattr("src.pdf_extractor.content_extractor.opendataloader_pdf", None)
    candidates = detect_relevant_pages(pdf_path, 3, verbose=False)
    return extract_content(pdf_path, candidates, verbose=False)


def test_dfn_pinout_uses_deterministic_table_parser(monkeypatch):
    """The DFN pin table should parse to 8 pins without involving the LLM."""
    monkeypatch.setattr("src.main.LLMClient.extract_pin_data", _no_llm_call)

    content = _build_content("pdfs/DFN.pdf", monkeypatch)
    pin_data = extract_pin_data(
        content,
        api_key="dummy",
        model="dummy",
        verbose=False,
        part_number="TPS62160DSG",
    )

    assert pin_data.package is not None
    assert pin_data.package.pin_count == 8
    assert pin_data.package.type == "WSON"
    assert len(pin_data.pins) == 8

    pin_names = {pin.name for pin in pin_data.pins}
    assert pin_names == {"PGND", "VIN", "EN", "AGND", "FB", "VOS", "SW", "PG"}


def test_mpu_pinout_uses_deterministic_table_parser(monkeypatch):
    """The MPU pin table should parse to the full 24-pin QFN package."""
    monkeypatch.setattr("src.main.LLMClient.extract_pin_data", _no_llm_call)

    content = _build_content("pdfs/MPU-6000-Datasheet1.pdf", monkeypatch)
    pin_data = extract_pin_data(
        content,
        api_key="dummy",
        model="dummy",
        verbose=False,
        part_number="MPU-6000",
    )

    assert pin_data.package is not None
    assert pin_data.package.pin_count == 24
    assert pin_data.package.type == "QFN"
    assert len(pin_data.pins) == 24

    pins_by_number = {pin.number: pin.name for pin in pin_data.pins}
    assert pins_by_number[1] == "CLKIN"
    assert pins_by_number[8] == "/CS"
    assert pins_by_number[9] == "AD0 / SDO"
    assert pins_by_number[24] == "SDA / SDI"
