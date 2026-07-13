"""Consolidated test suite for datasheet-parser.

Covers the full stack from PDF ingestion through pin extraction to GLB output,
plus unit tests for every major module and the end-to-end pipeline.

Run all tests:
    pytest tests/test_suite.py -v

Run with coverage:
    pytest tests/test_suite.py --cov=src --cov-report=html:coverage_html

Run only fast tests (skip real-PDF integration):
    pytest tests/test_suite.py -v -m "not integration"
"""

import json
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pygltflib import GLTF2, Node, Scene

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks" / "manifest.json"


# ===========================================================================
# 0. OUTPUT PATH HELPER
# ===========================================================================

from src.main import _both_output_paths


def test_both_output_paths_strips_glb_extension():
    schematic, footprint = _both_output_paths("NE555.glb")
    assert schematic == "NE555_schematic.glb"
    assert footprint == "NE555_footprint.glb"


def test_both_output_paths_preserves_directory():
    schematic, footprint = _both_output_paths("output/NE555.glb")
    assert schematic == "output/NE555_schematic.glb"
    assert footprint == "output/NE555_footprint.glb"


def test_both_output_paths_no_extension():
    schematic, footprint = _both_output_paths("NE555")
    assert schematic == "NE555_schematic.glb"
    assert footprint == "NE555_footprint.glb"


# ===========================================================================
# 1. DATA MODELS
# ===========================================================================

from src.models.pin_data import Pin, PackageInfo, PinData


def test_pin_creation():
    pin = Pin(number=1, name="VCC", function="power")
    assert pin.number == 1
    assert pin.name == "VCC"
    assert pin.function == "power"


def test_pin_optional_function():
    pin = Pin(number=2, name="NC")
    assert pin.function is None


def test_package_info_creation():
    pkg = PackageInfo(type="DIP", pin_count=28, width=7.5, height=15.0, pitch=2.54, thickness=3.0)
    assert pkg.type == "DIP"
    assert pkg.pin_count == 28
    assert pkg.pitch == 2.54


def test_package_info_minimal():
    pkg = PackageInfo(type="QFN", pin_count=24, width=5.0, height=5.0)
    assert pkg.pitch is None
    assert pkg.thickness is None


def test_pin_data_single_package():
    pkg = PackageInfo(type="DIP", pin_count=4, width=5.0, height=5.0)
    pins = [Pin(number=i, name=n) for i, n in enumerate(["VCC", "OUT", "IN", "GND"], 1)]
    pd = PinData(component_name="NE555", package=pkg, pins=pins, extraction_method="Table")
    assert pd.component_name == "NE555"
    assert len(pd.pins) == 4


def test_pin_data_multi_package():
    pd = PinData(
        component_name="74HC595",
        packages=[
            {"type": "PDIP-16", "pin_count": 16, "pins": [{"number": 1, "name": "A"}]},
            {"type": "SOIC-16", "pin_count": 16, "pins": [{"number": 1, "name": "B"}]},
        ],
        selected_package_index=1,
        extraction_method="Table",
    )
    assert pd.selected_package_index == 1
    assert pd.packages[1]["type"] == "SOIC-16"


# ===========================================================================
# 2. PAGE DETECTOR
# ===========================================================================

from src.pdf_extractor.page_detector import PageCandidate, PageDetector


@pytest.fixture
def detector():
    mock_pdf = MagicMock()
    mock_pdf.pages = []
    with patch("src.pdf_extractor.page_detector.pdfplumber") as mock_plumber:
        mock_plumber.open.return_value = mock_pdf
        d = PageDetector("fake.pdf")
        d.total_pages = 20
        yield d


def _make_page(tables=None, images=None, width=612, height=792, text=""):
    page = MagicMock()
    page.extract_tables.return_value = tables or []
    page.images = images or []
    page.width = width
    page.height = height
    page.extract_text.return_value = text
    return page


def test_page_detector_pinout_heading_scores(detector):
    score, reason = detector._check_pinout_heading("Pin Configuration\nSome content here")
    assert score == 3
    assert "heading" in reason.lower()


def test_page_detector_no_heading_scores_zero(detector):
    score, reason = detector._check_pinout_heading("Electrical Characteristics\nVcc max 5V")
    assert score == 0
    assert reason == ""


def test_page_detector_pinout_table_scores(detector):
    table = [
        ["Pin No.", "Name", "Description"],
        ["1", "GND", "Ground"],
        ["2", "VCC", "Supply"],
    ]
    page = _make_page(tables=[table])
    score, has_table, reason = detector._check_pinout_table(page)
    assert score == 4
    assert has_table is True
    assert "pinout table" in reason.lower()


def test_page_detector_no_table_scores_zero(detector):
    page = _make_page(tables=[])
    score, has_table, _ = detector._check_pinout_table(page)
    assert score == 0
    assert has_table is False


def test_page_detector_keyword_density_high(detector):
    score, reason = detector._check_keyword_density("vcc gnd reset enable clock")
    assert score == 2
    assert "keyword" in reason.lower()


def test_page_detector_keyword_density_low(detector):
    filler = " ".join(["word"] * 199)
    score, _ = detector._check_keyword_density(filler + " gnd")
    assert score == 0


def test_page_detector_full_pinout_page_high_confidence(detector):
    table = [
        ["Pin No.", "Pin Name", "Description"],
        ["1", "GND", "Ground"],
        ["2", "VCC", "Supply"],
    ]
    page = _make_page(
        tables=[table],
        text="Pin Configuration\nvcc gnd reset enable clock input output",
    )
    candidate = detector._analyze_page(5, page, page.extract_text.return_value)
    assert candidate.confidence_score >= 9
    assert candidate.has_table is True


def test_page_detector_irrelevant_page_scores_zero(detector):
    page = _make_page(text="Introduction to the product family overview.")
    candidate = detector._analyze_page(20, page, page.extract_text.return_value)
    assert candidate.confidence_score == 0


def test_page_detector_needs_verification_without_table(detector):
    page = _make_page(text="pin vcc gnd reset enable output input clock")
    candidate = detector._analyze_page(8, page, page.extract_text.return_value)
    assert candidate.needs_verification is True


# ---------------------------------------------------------------------------
# 2a. Page detector benchmark: precision / recall against real PDFs
# ---------------------------------------------------------------------------

def _load_benchmark_cases():
    if not MANIFEST_PATH.exists():
        return []
    manifest = json.loads(MANIFEST_PATH.read_text())
    cases = []
    for entry in manifest["cases"]:
        case = json.loads((ROOT / entry["file"]).read_text())
        pdf_path = ROOT / case["pdf"]
        if pdf_path.exists():
            cases.append((case["id"], str(pdf_path), case["expected_pinout_pages"]))
    return cases


BENCHMARK_CASES = _load_benchmark_cases()


@pytest.mark.integration
@pytest.mark.parametrize("case_id,pdf_path,expected_pages", BENCHMARK_CASES)
def test_benchmark_recall_all_expected_pages_detected(case_id, pdf_path, expected_pages):
    """Every ground-truth pinout page must appear in the detected set (recall = 1.0)."""
    with PageDetector(pdf_path) as det:
        candidates = det.detect_relevant_pages(min_confidence=5)

    detected = {c.page_number for c in candidates}
    missed = [p for p in expected_pages if p not in detected]

    assert missed == [], (
        f"[{case_id}] Missed expected pinout pages: {missed}. Detected: {sorted(detected)}"
    )


# ===========================================================================
# 3. CONTENT EXTRACTION  (PyMuPDF primary, pdfplumber fallback)
# ===========================================================================

from src.pdf_extractor import content_extractor as content_extractor_module
from src.pdf_extractor.content_extractor import ContentExtractor


@pytest.mark.integration
def test_pdfplumber_fallback_when_pymupdf_unavailable(monkeypatch):
    """When PyMuPDF (fitz) is unavailable, pdfplumber should extract tables."""
    monkeypatch.setattr(content_extractor_module, "fitz", None)

    with ContentExtractor("pdfs/74HC595_TI.pdf") as extractor:
        page = extractor.pdf.pages[2]
        tables = extractor._extract_tables_from_page(page, 3)

    assert tables, "Expected pdfplumber fallback to extract at least one table"
    page_num, table_data = tables[0]
    assert page_num == 3
    assert len(table_data) >= 2
    assert all(isinstance(cell, str) for row in table_data for cell in row)


# ===========================================================================
# 4. PACKAGE DETECTOR
# ===========================================================================

from src.utils.package_detector import PackageDetector


def test_normalize_package_name():
    d = PackageDetector()
    assert d.normalize_package_name("DIP-8") == "DIP"
    assert d.normalize_package_name("soic-16") == "SOIC"
    assert d.normalize_package_name("QFN-24") == "QFN"
    assert d.normalize_package_name("VQFN") == "QFN"
    assert d.normalize_package_name("DIL") == "DIP"
    assert d.normalize_package_name("DFN-8") == "DFN"
    assert d.normalize_package_name("WSON-8") == "WSON"
    assert d.normalize_package_name("TSSOP-20") == "TSSOP"


def test_package_family_matching():
    d = PackageDetector()
    assert d.package_family("DFN-8") == "QFN"
    assert d.package_family("WSON-8") == "QFN"
    assert d.package_family("TSSOP-20") == "SOIC"
    assert d.package_family("SOIC-16") == "SOIC"


def test_detect_from_text():
    d = PackageDetector()
    assert d._detect_from_text("DIP-28 package") == "DIP"
    assert d._detect_from_text("QFN-24 pin configuration") == "QFN"
    assert d._detect_from_text("DFN-8 dual flat no-lead") == "DFN"
    assert d._detect_from_text("SOIC-8 small outline") == "SOIC"
    assert d._detect_from_text("BGA ball grid array") == "BGA"


def test_estimate_dimensions_dip():
    d = PackageDetector()
    width, height = d.estimate_dimensions("DIP", 28)
    assert width > 5.0
    assert height > 10.0


def test_estimate_dimensions_qfn():
    d = PackageDetector()
    width, height = d.estimate_dimensions("QFN", 24)
    assert abs(width - height) < 2.0


# ===========================================================================
# 5. PACKAGE LAYOUT FAMILIES
# ===========================================================================

from src.package_types import PackageType, get_schematic_parameters
from src.schematic_generator.pin_layout import layout_pins


def test_dfn_8_uses_dual_row_layout():
    params = get_schematic_parameters("DFN-8", 8)
    assert params.package_type == PackageType.DFN
    assert params.pins_per_side == [4, 4, 0, 0]

    positions = layout_pins(params)
    sides = [pos.side for pos in positions]
    assert sides == ["left"] * 4 + ["right"] * 4
    assert [pos.pin_number for pos in positions] == [str(i) for i in range(1, 9)]


def test_qfn_24_uses_quad_layout():
    params = get_schematic_parameters("QFN-24", 24)
    assert params.package_type == PackageType.QFN
    assert params.pins_per_side == [6, 6, 6, 6]

    positions = layout_pins(params)
    side_counts = {s: sum(1 for p in positions if p.side == s) for s in ["left", "bottom", "right", "top"]}
    assert side_counts == {"left": 6, "bottom": 6, "right": 6, "top": 6}


# ===========================================================================
# 6. PINOUT FILTER
# ===========================================================================

from src.pdf_extractor.content_extractor import ExtractedContent
from src.pdf_extractor.pinout_filter import PinoutFilter


def _build_74hc595_raw_content():
    pdf_path = "pdfs/74HC595_TI.pdf"
    with ContentExtractor(pdf_path) as extractor:
        pinout_page = extractor.pdf.pages[2]
        package_page = extractor.pdf.pages[20]
        tables = extractor._extract_tables_with_pdfplumber(pinout_page, 3)
        text_content = (
            extractor._extract_text_from_page(pinout_page, 3)
            + "\n\n"
            + extractor._extract_text_from_page(package_page, 21)
        )
    return ExtractedContent(pages=[3, 21], text_content=text_content, images=[], tables=tables)


@pytest.mark.integration
def test_pinout_filter_keeps_pinout_page_and_drops_packaging_page():
    extracted = _build_74hc595_raw_content()
    filtered = PinoutFilter().filter_content(extracted)
    assert filtered.pages == [3]
    assert [pn for pn, _ in filtered.tables] == [3]
    assert "--- Page 3 ---" in filtered.text_content
    assert "--- Page 21 ---" not in filtered.text_content


@pytest.mark.integration
def test_pdfplumber_table_shape_recognized_as_pinout_table():
    extracted = _build_74hc595_raw_content()
    table_data = extracted.tables[0][1]
    assert PinoutFilter().is_pinout_table(table_data)


# ===========================================================================
# 7. PART NUMBER HINT
# ===========================================================================

from src.pdf_extractor.part_number_hint import infer_part_number_hint


def test_infer_part_number_hint_prefers_datasheet_text():
    """High-frequency text token wins when filename has no plausible part number."""
    text_content = (
        "--- Page 1 ---\n"
        "NE555 Timer\n"
        "Pin Configuration and Functions\n\n"
        "--- Page 2 ---\n"
        "NE555\n"
    )
    # "foo" → "FOO" fails _token_is_plausible (no digit), so NE555 wins via scoring
    assert infer_part_number_hint(text_content, source_name="foo.pdf") == "NE555"


def test_single_filename_candidate_wins_unconditionally():
    """A single plausible token in the filename takes priority over text scores."""
    text_content = (
        "--- Page 1 ---\n"
        # Many occurrences of a plausible-but-wrong token
        "ICES1 ICES1 ICES1 ICES1 ICES1 ICES1\n"
        "--- Page 2 ---\n"
        "ICES1 ICES1 ICES1\n"
    )
    # "ATmega328P" → uppercased "ATMEGA328P" — plausible, single filename candidate
    result = infer_part_number_hint(text_content, source_name="ATmega328P.pdf")
    assert result == "ATMEGA328P"


# ===========================================================================
# 8. EXTRACTION VALIDATION
# ===========================================================================

from src.pdf_extractor.extraction_validator import validate_pin_data_extraction


def test_validate_rejects_duplicate_pin_numbers():
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
    assert any("duplicate pin number 1" in e.lower() for e in result.errors)


def test_validate_accepts_explicitly_numbered_thermal_pad():
    """Thermal pads with an explicit datasheet pin number are treated as real pins."""
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
    # Explicitly numbered exposed pad is accepted as a real pin (may carry a warning)
    assert result.is_valid
    assert any("exposed thermal pad" in w.lower() or "package feature" in w.lower() for w in result.warnings)


# ===========================================================================
# 9. LLM PROMPTS
# ===========================================================================

from src.chat_bot import build_pin_extraction_prompt, build_table_extraction_prompt


def test_pin_extraction_prompts_include_target_and_retry_feedback():
    pin_prompt = build_pin_extraction_prompt(
        "sample content",
        part_number="SN74HC595DR",
        validation_feedback="Fix the pin count",
    )
    table_prompt = build_table_extraction_prompt(
        '[[\"PIN\", \"NAME\"]]',
        part_number="SN74HC595DR",
        validation_feedback="Fix the pin count",
    )
    assert any("SN74HC595DR" in m["content"] for m in pin_prompt)
    assert any("Fix the pin count" in m["content"] for m in pin_prompt)
    assert any("SN74HC595DR" in m["content"] for m in table_prompt)
    assert any("Fix the pin count" in m["content"] for m in table_prompt)
    assert any("selected_package_index" in m["content"] for m in pin_prompt)
    assert any("selected_package_index" in m["content"] for m in table_prompt)


# ===========================================================================
# 10. LLM CLIENT VALIDATION (new in this release)
# ===========================================================================

from src.llm.client import LLMClient, _parse_pin_count_from_package_type


def test_parse_pin_count_standard_packages():
    assert _parse_pin_count_from_package_type("SOIC-8") == 8
    assert _parse_pin_count_from_package_type("LQFP-64") == 64
    assert _parse_pin_count_from_package_type("QFN-32") == 32
    assert _parse_pin_count_from_package_type("DIP-28") == 28


def test_parse_pin_count_special_cases():
    assert _parse_pin_count_from_package_type("SOT-23") == 3
    assert _parse_pin_count_from_package_type("SOT-223") == 4
    assert _parse_pin_count_from_package_type("TO-220") == 3


def test_parse_pin_count_unknown_returns_none():
    assert _parse_pin_count_from_package_type("CUSTOM-999") is None
    assert _parse_pin_count_from_package_type("") is None
    assert _parse_pin_count_from_package_type(None) is None


def test_validate_pin_data_no_pins():
    client = LLMClient()
    pd = PinData(component_name="X", pins=[], extraction_method="Table")
    issue = client._validate_pin_data(pd)
    assert issue is not None
    assert "no pins" in issue.lower() or "0 pin" in issue.lower()


def test_validate_pin_data_duplicate_pin_numbers():
    client = LLMClient()
    pd = PinData(
        component_name="X",
        package=PackageInfo(type="DIP-8", pin_count=8, width=5.0, height=10.0),
        pins=[Pin(number=n, name=f"P{n}") for n in [1, 2, 2, 3, 4, 5, 6, 7]],
        extraction_method="Table",
    )
    issue = client._validate_pin_data(pd)
    assert issue is not None
    assert "duplicate" in issue.lower()


def test_validate_pin_data_large_gap_in_numbering():
    client = LLMClient()
    # 8 pins but a huge gap between 3 and 50 — clearly skipped pins
    pd = PinData(
        component_name="X",
        package=PackageInfo(type="DIP-8", pin_count=8, width=5.0, height=10.0),
        pins=[Pin(number=n, name=f"P{n}") for n in [1, 2, 3, 50, 51, 52, 53, 54]],
        extraction_method="Table",
    )
    issue = client._validate_pin_data(pd)
    assert issue is not None
    assert "gap" in issue.lower()


def test_validate_pin_data_package_type_mismatch():
    client = LLMClient()
    # SOIC-8 implies 8 pins; only 4 provided
    pd = PinData(
        component_name="X",
        package=PackageInfo(type="SOIC-8", pin_count=4, width=4.0, height=6.0),
        pins=[Pin(number=n, name=f"P{n}") for n in range(1, 5)],
        extraction_method="Table",
    )
    issue = client._validate_pin_data(pd)
    assert issue is not None
    assert "soic-8" in issue.lower() or "8 pins" in issue.lower()


def test_validate_pin_data_clean_data_passes():
    client = LLMClient()
    pd = PinData(
        component_name="NE555",
        package=PackageInfo(type="DIP-8", pin_count=8, width=5.0, height=10.0),
        pins=[Pin(number=n, name=f"P{n}") for n in range(1, 9)],
        extraction_method="Table",
    )
    assert client._validate_pin_data(pd) is None


# ===========================================================================
# 11. LLM RESPONSE PARSING
# ===========================================================================

def test_llm_client_parses_selected_variant_metadata():
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
    pd = LLMClient()._parse_llm_response(response)
    assert pd.selected_package_index == 1
    assert pd.selected_package_type == "SOIC-16"
    assert "SOIC" in (pd.selection_reason or "")


def test_llm_client_clamps_stray_index_on_single_package():
    # AMS1117 flow-eval find: the LLM extracted one package but said
    # selected_package_index 2, hard-failing validation. With a single
    # variant there is no ambiguity — the index must normalize to 0.
    response = """
    {
      "component_name": "AMS1117",
      "packages": [
        {"type": "SOIC-8", "pin_count": 8, "pins": [{"number": 1, "name": "GND"}]}
      ],
      "selected_package_index": 2,
      "extraction_method": "Table"
    }
    """
    pd = LLMClient()._parse_llm_response(response)
    assert pd.selected_package_index == 0

    # Multiple variants: an out-of-range index is real ambiguity and must
    # be preserved so validation rejects it.
    multi = response.replace(
        '{"type": "SOIC-8", "pin_count": 8, "pins": [{"number": 1, "name": "GND"}]}',
        '{"type": "SOIC-8", "pin_count": 8, "pins": [{"number": 1, "name": "GND"}]},'
        ' {"type": "DIP-8", "pin_count": 8, "pins": [{"number": 1, "name": "GND"}]}',
    )
    pd = LLMClient()._parse_llm_response(multi)
    assert pd.selected_package_index == 2


def test_llm_client_preserves_explicitly_numbered_thermal_pad():
    """_parse_llm_response keeps all pins returned by the LLM, including explicitly
    numbered thermal pads — filtering is the LLM's responsibility via prompts."""
    response = """
    {
      "component_name": "TPS62160",
      "package": {"type": "QFN-8", "pin_count": 8, "width": 4.0, "height": 4.0, "pitch": 0.5},
      "pins": [
        {"number": 1, "name": "VIN",  "function": "power"},
        {"number": 2, "name": "EN",   "function": "input"},
        {"number": 3, "name": "GND",  "function": "ground"},
        {"number": 4, "name": "SW",   "function": "output"},
        {"number": 5, "name": "PG",   "function": "output"},
        {"number": 6, "name": "VOS",  "function": "input"},
        {"number": 7, "name": "FB",   "function": "input"},
        {"number": 8, "name": "PGND", "function": "ground"},
        {"number": 9, "name": "Exposed Thermal Pad", "function": "ground"}
      ],
      "extraction_method": "Table"
    }
    """
    pd = LLMClient()._parse_llm_response(response)
    assert pd.package is not None
    # All 9 entries (including the explicitly numbered thermal pad) are preserved
    assert len(pd.pins or []) == 9


# ===========================================================================
# 12. VARIANT SELECTION
# ===========================================================================

from src.pdf_extractor.variant_selection import select_package_variant
from src.schematic_generator.adapter import pin_data_to_builder_format


def test_select_package_variant_uses_llm_selected_index():
    pd = PinData(
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
    sel = select_package_variant(pd)
    assert sel.index == 1
    assert sel.package["type"] == "SOIC-16"
    assert "Target part number" in sel.reason


def test_pin_data_to_builder_format_respects_selected_variant():
    pd = PinData(
        component_name="74HC595",
        packages=[
            {"type": "PDIP-16", "pin_count": 16, "pins": [{"number": 1, "name": "A"}]},
            {"type": "SOIC-16", "pin_count": 16, "pins": [{"number": 1, "name": "B"}]},
        ],
        selected_package_index=1,
        selected_package_type="SOIC-16",
        extraction_method="Table",
    )
    package_type, pin_count, name, pins = pin_data_to_builder_format(pd)
    assert package_type == "SOIC-16"
    assert pin_count == 16
    assert name == "74HC595"
    assert pins == [{"number": "1", "name": "B"}]


def test_select_package_variant_rejects_ambiguous_without_selection():
    pd = PinData(
        component_name="74HC595",
        packages=[
            {"type": "PDIP-16", "pin_count": 16, "pins": [{"number": 1, "name": "A"}]},
            {"type": "SOIC-16", "pin_count": 16, "pins": [{"number": 1, "name": "B"}]},
        ],
        extraction_method="Table",
    )
    with pytest.raises(ValueError, match="(?i)multiple package variants"):
        select_package_variant(pd)


# ===========================================================================
# 13. GLB OPTIMIZER
# ===========================================================================

from src.core.glb_optimizer import simplify_glb_hierarchy


def test_simplify_glb_collapses_identity_wrapper_chain():
    gltf = GLTF2(
        nodes=[
            Node(name="Package", children=[1, 4], rotation=[0.0, 0.0, 0.0, 1.0]),
            Node(name="DesignatorName", children=[2], extras={}),
            Node(name="uuid-node", children=[3], extras={}),
            Node(name="uuid-node_part", mesh=0, extras={}),
            Node(name="PackageValue", mesh=1, extras={}),
        ],
        scenes=[Scene(nodes=[0])],
    )
    original_count, simplified_count = simplify_glb_hierarchy(gltf)
    assert original_count == 5
    assert simplified_count == 3
    assert [n.name for n in gltf.nodes] == ["Package", "DesignatorName", "PackageValue"]
    assert gltf.nodes[1].mesh == 0


def test_simplify_glb_keeps_branch_nodes_with_transforms():
    gltf = GLTF2(
        nodes=[
            Node(name="Package", children=[1, 6], rotation=[0.0, 0.0, 0.70710678, 0.70710678]),
            Node(name="BodyLine", children=[2, 4], extras={}),
            Node(name="BodyLine_Top", children=[3], extras={}),
            Node(name="BodyLine_Top_part", mesh=0, extras={}),
            Node(name="BodyLine_Bottom", children=[5], extras={}),
            Node(name="BodyLine_Bottom_part", mesh=1, extras={}),
            Node(name="RotatedWrapper", children=[7], translation=[1.0, 0.0, 0.0], extras={}),
            Node(name="RotatedWrapper_part", mesh=2, extras={}),
        ],
        scenes=[Scene(nodes=[0])],
    )
    original_count, simplified_count = simplify_glb_hierarchy(gltf)
    assert original_count == 8
    assert simplified_count == 6
    assert gltf.nodes[4].translation == [1.0, 0.0, 0.0]


# ===========================================================================
# 14. PCB FOOTPRINT GENERATION
# ===========================================================================

from src.core.pcb_footprint_hierarchy import validate_pcb_footprint_hierarchy
from src.core.reference_glb_hierarchy import validate_glb_similarity_to_reference
from src.core import validate_pcb_footprint_glb
from src.schematic_generator import build_pcb_footprint
from src.schematic_generator.pcb_footprint_builder import build_pcb_footprint as build_pcb_footprint_direct


_NE555_DIP8_PINS = [
    {"number": 1, "name": "GND"},
    {"number": 2, "name": "TRIG"},
    {"number": 3, "name": "OUT"},
    {"number": 4, "name": "RESET"},
    {"number": 5, "name": "CTRL"},
    {"number": 6, "name": "THRES"},
    {"number": 7, "name": "DISCH"},
    {"number": 8, "name": "VCC"},
]


def test_dip8_footprint_matches_documented_hierarchy(tmp_path):
    output_path = tmp_path / "ne555_dip8.glb"
    assert build_pcb_footprint_direct("DIP-8", 8, "NE555", _NE555_DIP8_PINS, str(output_path))

    gltf = GLTF2().load_binary(str(output_path))
    errors = validate_pcb_footprint_hierarchy(gltf, pin_count=8, through_hole=True)
    assert errors == []


def test_generated_dip8_similar_to_reference_glb(tmp_path):
    output_path = tmp_path / "dip8_ref.glb"
    assert build_pcb_footprint_direct("DIP-8", 8, "NE555", _NE555_DIP8_PINS, str(output_path))
    is_similar, errors = validate_glb_similarity_to_reference(str(output_path))
    assert is_similar, errors


def test_generated_dip28_matches_reference_glb_structure(tmp_path):
    output_path = tmp_path / "dip28_ref.glb"
    pins = [{"number": n, "name": f"PIN{n}"} for n in range(1, 29)]
    assert build_pcb_footprint_direct("DIP-28", 28, "GENERIC28", pins, str(output_path))
    is_similar, errors = validate_glb_similarity_to_reference(str(output_path))
    assert is_similar, errors


def test_reference_file_is_self_similar():
    ref = ROOT / "2d.glb"
    is_similar, errors = validate_glb_similarity_to_reference(str(ref), str(ref))
    assert is_similar, errors


@pytest.mark.parametrize(
    "package_type,pin_count",
    [("WSON-8", 8), ("SON-10", 10)],
)
def test_aliased_package_families_generate_valid_footprints(tmp_path, package_type, pin_count):
    output_path = tmp_path / f"{package_type.lower().replace('-', '_')}.glb"
    pins = [{"number": n, "name": f"PIN{n}"} for n in range(1, pin_count + 1)]

    assert build_pcb_footprint(package_type, pin_count, "TEST", pins, str(output_path))

    is_valid, errors = validate_pcb_footprint_glb(str(output_path), pin_count=pin_count, through_hole=False)
    assert is_valid, errors
    assert output_path.stat().st_size > 0


@pytest.mark.parametrize(
    "package_type,pin_count",
    [("SOD-123", 2), ("WLCSP-8", 8)],
)
def test_unknown_package_families_fail_closed(tmp_path, package_type, pin_count):
    """ARCH-006: packages with no known geometry must raise, not render as DIP."""
    from src.exceptions import ErrorCodes, SchematicGenerationError

    output_path = tmp_path / f"{package_type.lower().replace('-', '_')}.glb"
    pins = [{"number": n, "name": f"PIN{n}"} for n in range(1, pin_count + 1)]

    with pytest.raises(SchematicGenerationError) as exc_info:
        build_pcb_footprint(package_type, pin_count, "TEST", pins, str(output_path))

    assert exc_info.value.error_code == ErrorCodes.PACKAGE_UNKNOWN
    assert not output_path.exists(), "no GLB may be written for unknown packages"


def _unknown_package_pin_data():
    return PinData(
        component_name="MYSTERY",
        package=PackageInfo(type="WLCSP-8", pin_count=8, width=2.0, height=2.0),
        pins=[Pin(number=n, name=f"P{n}") for n in range(1, 9)],
        extraction_method="Table",
    )


def test_enforce_known_package_type_raises_without_force():
    from src.exceptions import ErrorCodes, SchematicGenerationError
    from src.main import enforce_known_package_type

    pin_data = _unknown_package_pin_data()
    with pytest.raises(SchematicGenerationError) as exc_info:
        enforce_known_package_type(pin_data)

    assert exc_info.value.error_code == ErrorCodes.PACKAGE_UNKNOWN
    assert "--force-best-effort" in str(exc_info.value)
    assert pin_data.package.type == "WLCSP-8", "package must not be mutated on failure"


def test_enforce_known_package_type_force_substitutes_dip_and_flags():
    from src.main import enforce_known_package_type

    pin_data = _unknown_package_pin_data()
    enforce_known_package_type(pin_data, force_best_effort=True)

    # Substitution is explicit: type rewritten and recorded so the GLB
    # gets the unvalidated watermark.
    assert pin_data.package.type == "DIP-8"
    assert any("WLCSP-8" in e and "DIP-8" in e for e in pin_data.validation_errors)


def test_enforce_known_package_type_force_substitutes_multi_package_variant():
    from src.main import enforce_known_package_type

    pin_data = PinData(
        component_name="MYSTERY",
        packages=[
            {
                "type": "WLCSP-8",
                "pin_count": 8,
                "pins": [{"number": n, "name": f"P{n}"} for n in range(1, 9)],
            }
        ],
        extraction_method="Table",
    )
    enforce_known_package_type(pin_data, force_best_effort=True)

    assert pin_data.packages[0]["type"] == "DIP-8"
    assert pin_data.validation_errors


def test_enforce_known_package_type_accepts_known_packages():
    from src.main import enforce_known_package_type

    pin_data = PinData(
        component_name="NE555",
        package=PackageInfo(type="DIP-8", pin_count=8, width=6.5, height=10.2),
        pins=[Pin(number=n, name=f"P{n}") for n in range(1, 9)],
        extraction_method="Table",
    )
    enforce_known_package_type(pin_data)

    assert pin_data.package.type == "DIP-8"
    assert not pin_data.validation_errors


# ===========================================================================
# 15. DETERMINISTIC TABLE PARSER  (integration — no LLM)
# ===========================================================================

from src.main import detect_relevant_pages, extract_content, extract_pin_data


def _no_llm_call(*args, **kwargs):
    raise AssertionError("LLM should not be called — deterministic parser should handle this PDF")


def _build_content(pdf_path: str):
    """Detect relevant pages and extract content from a PDF."""
    candidates = detect_relevant_pages(pdf_path, 3, verbose=False)
    return extract_content(pdf_path, candidates, verbose=False)


@pytest.mark.integration
def test_dfn_pinout_uses_deterministic_table_parser(monkeypatch):
    """DFN.pdf pin table should parse to 8 pins without calling the LLM."""
    monkeypatch.setattr("src.main.LLMClient.extract_pin_data", _no_llm_call)

    content = _build_content("pdfs/DFN.pdf")
    pin_data = extract_pin_data(
        content, model="dummy", verbose=False, part_number="TPS62160DSG"
    )

    assert pin_data.package is not None
    assert pin_data.package.pin_count == 8
    assert pin_data.package.type == "WSON"
    assert len(pin_data.pins) == 8
    assert {p.name for p in pin_data.pins} == {"PGND", "VIN", "EN", "AGND", "FB", "VOS", "SW", "PG"}


def test_deterministic_parser_needs_family_evidence():
    # TPS63060 flow-eval find: the parser invented "SOIC-9" from the pin
    # count when the page named no family. With no evidence at all in the
    # text it must produce no candidate (LLM fallback), not a guess.
    from src.pdf_extractor.deterministic_table_parser import _infer_family
    assert _infer_family("Pin Functions PIN I/O DESCRIPTION", 9) is None
    assert _infer_family("SOIC-16 package pinout", 16) == "SOIC"


@pytest.mark.integration
def test_mpu_pinout_uses_deterministic_table_parser(monkeypatch):
    """MPU-6000 pin table should parse to 24 pins without calling the LLM.

    PyMuPDF produces a table format the deterministic parser cannot consume for
    this PDF, so pdfplumber is used as the extractor (fitz patched to None).
    """
    monkeypatch.setattr("src.main.LLMClient.extract_pin_data", _no_llm_call)
    monkeypatch.setattr(content_extractor_module, "fitz", None)

    content = _build_content("pdfs/MPU-6000-Datasheet1.pdf")
    pin_data = extract_pin_data(
        content, model="dummy", verbose=False, part_number="MPU-6000"
    )

    assert pin_data.package is not None
    assert pin_data.package.pin_count == 24
    assert pin_data.package.type == "QFN"
    assert len(pin_data.pins) == 24
    pins_by_number = {p.number: p.name for p in pin_data.pins}
    assert pins_by_number[1] == "CLKIN"
    assert pins_by_number[24] == "SDA / SDI"


# ===========================================================================
# 16. BENCHMARK MANIFEST INTEGRITY
# ===========================================================================

REQUIRED_CASE_KEYS = {
    "id", "pdf", "component_name", "expected_package_family",
    "expected_pin_count", "expected_pin_map", "expected_pinout_pages",
}


def test_benchmark_manifest_points_to_valid_case_files():
    manifest = json.loads(MANIFEST_PATH.read_text())
    assert manifest["schema_version"] == 1
    cases = manifest["cases"]
    assert cases, "Expected at least one benchmark case"

    case_ids = []
    for entry in cases:
        case_ids.append(entry["id"])
        case_path = ROOT / entry["file"]
        assert case_path.exists(), f"Missing benchmark case file: {case_path}"
        case = json.loads(case_path.read_text())
        assert case["id"] == entry["id"]
        assert REQUIRED_CASE_KEYS.issubset(case)
        assert (ROOT / case["pdf"]).exists(), f"Missing benchmark PDF: {case['pdf']}"

        pin_map = case["expected_pin_map"]
        assert pin_map
        assert [p["number"] for p in pin_map] == list(range(1, len(pin_map) + 1))
        assert case["expected_pin_count"] == len(pin_map)

    assert len(case_ids) == len(set(case_ids)), "Benchmark case IDs must be unique"


# ===========================================================================
# 17. FULL PIPELINE — PDF → pin extraction → PCB footprint GLB  (end-to-end)
# ===========================================================================

@pytest.mark.integration
def test_full_pipeline_dfn_pdf_to_pcb_footprint_glb(monkeypatch, tmp_path):
    """
    End-to-end smoke test: DFN.pdf → detect pages → extract content →
    extract pins (deterministic) → build PCB footprint GLB → validate output.
    """
    monkeypatch.setattr("src.main.LLMClient.extract_pin_data", _no_llm_call)

    # Stage 1: page detection
    candidates = detect_relevant_pages("pdfs/DFN.pdf", min_confidence=3, verbose=False)
    assert candidates, "No pinout pages detected in DFN.pdf"

    # Stage 2: content extraction
    content = extract_content("pdfs/DFN.pdf", candidates, verbose=False)
    assert content.text_content or content.tables, "No content extracted"

    # Stage 3: pin extraction (deterministic table parser — no LLM)
    pin_data = extract_pin_data(
        content, model="dummy",
        part_number="TPS62160DSG", verbose=False,
    )
    assert pin_data.pins and len(pin_data.pins) == 8

    # Stage 4: build PCB footprint GLB
    package_type, pin_count, name, pins = pin_data_to_builder_format(pin_data)
    output_path = tmp_path / "dfn_e2e.glb"
    success = build_pcb_footprint(package_type, pin_count, name, pins, str(output_path))
    assert success, "build_pcb_footprint returned falsy"

    # Stage 5: validate output
    assert output_path.exists()
    assert output_path.stat().st_size > 0

    is_valid, errors = validate_pcb_footprint_glb(str(output_path), pin_count=pin_count, through_hole=False)
    assert is_valid, f"GLB validation failed: {errors}"


@pytest.mark.integration
def test_both_flag_produces_schematic_and_footprint_glb(monkeypatch, tmp_path):
    """--both mode should write *_schematic.glb and *_footprint.glb in one pipeline run."""
    monkeypatch.setattr("src.main.LLMClient.extract_pin_data", _no_llm_call)

    base = tmp_path / "dfn_both.glb"
    schematic_path = tmp_path / "dfn_both_schematic.glb"
    footprint_path = tmp_path / "dfn_both_footprint.glb"

    candidates = detect_relevant_pages("pdfs/DFN.pdf", min_confidence=3, verbose=False)
    content = extract_content("pdfs/DFN.pdf", candidates, verbose=False)
    pin_data = extract_pin_data(
        content, model="dummy",
        part_number="TPS62160DSG", verbose=False,
    )

    from src.main import process_datasheet_both
    result = process_datasheet_both(pin_data=pin_data, output_path=base)

    assert result is True
    assert schematic_path.exists(), "schematic GLB not created"
    assert footprint_path.exists(), "footprint GLB not created"
    assert schematic_path.stat().st_size > 0
    assert footprint_path.stat().st_size > 0


# ===========================================================================
# 18. FAIL-CLOSED VALIDATION (ARCH-005)
# ===========================================================================
# Regression tests for the fail-open validation fix: invalid pin data must
# never silently reach GLB generation. See datasheet-parser-new_review.md
# ARCH-005. No network, no CadQuery — pure mock-based unit tests.

from types import SimpleNamespace

from src.exceptions import LLMExtractionError, ValidationError as DSValidationError
from src.llm.client import LLMClient


_INVALID_LEGACY_RESPONSE = json.dumps({
    "component_name": "TESTPART",
    "package": {"type": "DIP-8", "pin_count": 8, "width": 6.0, "height": 9.0},
    # Duplicate pin number 1 -> fails self-consistency validation every time
    "pins": [
        {"number": 1, "name": "VCC"},
        {"number": 1, "name": "GND"},
        {"number": 3, "name": "OUT"},
        {"number": 4, "name": "IN1"},
        {"number": 5, "name": "IN2"},
        {"number": 6, "name": "EN"},
        {"number": 7, "name": "NC"},
        {"number": 8, "name": "VSS"},
    ],
})


def test_llm_client_raises_on_validation_exhaustion(monkeypatch):
    """ARCH-005: client must raise, not return known-bad data (client.py fail-open)."""
    monkeypatch.setattr(
        "src.llm.client.get_completion_from_messages",
        lambda messages, **kwargs: _INVALID_LEGACY_RESPONSE,
    )
    client = LLMClient(model="test")

    with pytest.raises(LLMExtractionError) as exc_info:
        client.extract_pin_data(content="irrelevant", max_retries=2, retry_delay=0)

    assert "Duplicate pin numbers" in str(exc_info.value)


def _make_invalid_pin_data():
    return PinData(
        component_name="TESTPART",
        package=PackageInfo(type="DIP-8", pin_count=8, width=6.0, height=9.0),
        pins=[
            Pin(number=1, name="VCC"),
            Pin(number=1, name="GND"),  # duplicate
            Pin(number=3, name="OUT"),
            Pin(number=4, name="IN1"),
            Pin(number=5, name="IN2"),
            Pin(number=6, name="EN"),
            Pin(number=7, name="NC"),
            Pin(number=8, name="VSS"),
        ],
    )


@pytest.fixture
def _pipeline_with_invalid_llm(monkeypatch):
    """Route src.main.extract_pin_data to an LLM stub that always returns invalid data."""
    import src.main as main_module
    from src.pdf_extractor.content_extractor import ContentExtractor

    monkeypatch.setattr(main_module, "parse_pin_data_from_tables", lambda *a, **k: None)
    monkeypatch.setattr(
        ContentExtractor, "format_for_llm",
        staticmethod(lambda content, tables_only=False: "formatted"),
    )

    class _StubLLMClient:
        def __init__(self, *args, **kwargs):
            pass

        def extract_pin_data(self, **kwargs):
            return _make_invalid_pin_data()

    monkeypatch.setattr(main_module, "LLMClient", _StubLLMClient)
    content = SimpleNamespace(tables=[], images=[], text_content="datasheet text")
    return main_module, content


def test_main_extract_pin_data_fails_closed(_pipeline_with_invalid_llm):
    """ARCH-005: exhausted validation retries must raise, not return bad data."""
    main_module, content = _pipeline_with_invalid_llm

    with pytest.raises(DSValidationError) as exc_info:
        main_module.extract_pin_data(
            content, model="m", verbose=False, part_number="TESTPART",
        )

    assert "force-best-effort" in str(exc_info.value)
    assert exc_info.value.details.get("errors")


def test_main_extract_pin_data_force_best_effort(_pipeline_with_invalid_llm):
    """ARCH-005: --force-best-effort returns the data but records the errors."""
    main_module, content = _pipeline_with_invalid_llm

    pin_data = main_module.extract_pin_data(
        content, model="m", verbose=False, part_number="TESTPART",
        force_best_effort=True,
    )

    assert pin_data is not None
    assert pin_data.validation_errors, "forced output must carry its validation errors"
    assert any("duplicate" in e.lower() for e in pin_data.validation_errors)


def test_mark_glb_unvalidated_sets_scene_extras(tmp_path):
    """ARCH-005: forced output is watermarked as validated=false in scene extras."""
    from src.core.validation_marker import mark_glb_unvalidated

    glb_path = tmp_path / "unvalidated.glb"
    gltf = GLTF2(scene=0, scenes=[Scene(nodes=[])], nodes=[])
    gltf.save_binary(str(glb_path))

    mark_glb_unvalidated(str(glb_path), ["duplicate pin number 1"])

    reloaded = GLTF2().load_binary(str(glb_path))
    extras = reloaded.scenes[0].extras
    assert extras["validated"] is False
    assert extras["validationErrors"] == ["duplicate pin number 1"]


# ===========================================================================
# 19. LAZY LLM CLIENT / API KEY HANDLING (BUG-001)
# ===========================================================================
# Regression tests for the fail-closed/lazy-client fix of review issue
# BUG-001. FASTCHAT_API_KEY is the single source of truth and must be read
# at call time, not import time. No network — the OpenAI class is stubbed.


@pytest.fixture
def _fresh_chat_bot_client(monkeypatch):
    """Reset the cached chat_bot client so each test exercises lazy creation."""
    from src import chat_bot

    monkeypatch.setattr(chat_bot, "_client", None)
    return chat_bot


def test_missing_api_key_raises_credentials_error(_fresh_chat_bot_client, monkeypatch):
    """BUG-001: a missing FASTCHAT_API_KEY fails loudly, not with an opaque 401."""
    from src.exceptions import APICredentialsError

    chat_bot = _fresh_chat_bot_client
    monkeypatch.delenv("FASTCHAT_API_KEY", raising=False)

    with pytest.raises(APICredentialsError) as exc_info:
        chat_bot.get_completion_from_messages([{"role": "user", "content": "hi"}])

    assert "FASTCHAT_API_KEY" in str(exc_info.value)


def test_client_reads_key_at_call_time(_fresh_chat_bot_client, monkeypatch):
    """BUG-001: the client picks up a key set after import, and is cached."""
    chat_bot = _fresh_chat_bot_client
    captured = {}

    class _StubOpenAI:
        def __init__(self, api_key=None, base_url=None):
            captured["api_key"] = api_key
            captured["base_url"] = base_url

    monkeypatch.setattr(chat_bot, "OpenAI", _StubOpenAI)
    monkeypatch.setenv("FASTCHAT_API_KEY", "key-set-after-import")

    first = chat_bot._get_client()
    second = chat_bot._get_client()

    assert captured["api_key"] == "key-set-after-import"
    assert first is second, "client must be created once and cached"


def test_api_key_cli_flag_removed(monkeypatch):
    """BUG-001: the dead --api-key flag is gone; argparse rejects it."""
    import sys

    from src import main as main_module

    monkeypatch.setattr(
        sys, "argv", ["prog", "in.pdf", "out.glb", "--api-key", "x"]
    )
    with pytest.raises(SystemExit) as exc_info:
        main_module.parse_arguments()
    assert exc_info.value.code == 2  # argparse usage error


# ===========================================================================
# 20. VISION RESPONSE PARSING (BUG-002)
# ===========================================================================
# Regression tests for the json_str NameError in ImageOCRClient's raw_text
# branch. _parse_api_response is exercised directly — no network calls.


@pytest.fixture
def _ocr_client():
    from src.llm.image_ocr_client import ImageOCRClient

    return ImageOCRClient()


def test_raw_text_without_json_returns_empty(_ocr_client):
    """BUG-002: a JSON-free raw_text must return an empty result, not NameError."""
    result = _ocr_client._parse_api_response(
        {"raw_text": "I cannot identify a pinout diagram in this image."}
    )

    assert result.pin_count == 0
    assert result.pins == []
    assert result.component_name == ""


def test_raw_text_with_fenced_json_parses(_ocr_client):
    """BUG-002: the happy path still parses a fenced JSON block from raw_text."""
    raw_text = (
        "Here is the pinout:\n```json\n"
        '{"component_name": "NE555", "package_type": "DIP-8", "pin_count": 2,'
        ' "pins": [{"number": 1, "name": "GND"}, {"number": 2, "name": "TRIG"}],'
        ' "extraction_confidence": 0.9}\n```'
    )

    result = _ocr_client._parse_api_response({"raw_text": raw_text})

    assert result.component_name == "NE555"
    assert result.package_type == "DIP-8"
    assert len(result.pins) == 2


def test_stale_json_str_not_reused_from_description_branch(_ocr_client):
    """BUG-002: a broken JSON candidate from the description branch must not
    leak into the raw_text branch as a stale json_str."""
    result = _ocr_client._parse_api_response(
        {
            "description": "```json\n{not valid json}\n```",
            "raw_text": "No structured data was found.",
        }
    )

    assert result.pin_count == 0
    assert result.pins == []


# ===========================================================================
# 21. DEPENDENCY MANIFEST CONSISTENCY (CFG-001)
# ===========================================================================
# Regression tests keeping pyproject.toml (the single source of truth),
# the generated requirements.txt, and the CI workflow in sync with the
# packages src/ actually hard-imports. Pure file checks — nothing installed.

# Distributions hard-imported somewhere in src/ (import name differs for
# fitz->PyMuPDF, PIL->Pillow, dotenv->python-dotenv).
_REQUIRED_DISTS = [
    "pdfplumber",
    "PyMuPDF",
    "cadquery",
    "Pillow",
    "pygltflib",
    "openai",
    "requests",
    "python-dotenv",
    "nest_asyncio",
]


def _normalize_dist(name):
    return name.lower().replace("-", "_")


def test_pyproject_declares_all_hard_imports():
    """CFG-001: every hard-imported package must be a core dependency."""
    text = (ROOT / "pyproject.toml").read_text()
    deps_block = text.split("dependencies = [", 1)[1].split("]", 1)[0]
    declared = {_normalize_dist(d) for d in re.findall(r'"([A-Za-z0-9_.-]+?)[><=~!\[]', deps_block)}

    missing = [d for d in _REQUIRED_DISTS if _normalize_dist(d) not in declared]
    assert not missing, f"pyproject.toml core dependencies missing: {missing}"


def test_requirements_txt_pins_all_hard_imports():
    """CFG-001: requirements.txt must pin (not comment out) every hard import."""
    pinned = set()
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            pinned.add(_normalize_dist(re.split(r"[><=~!\[]", line)[0]))

    missing = [d for d in _REQUIRED_DISTS if _normalize_dist(d) not in pinned]
    assert not missing, f"requirements.txt missing pinned entries for: {missing}"


def test_ci_installs_from_requirements():
    """CFG-001: CI must install the pinned manifest (which includes cadquery),
    not an ad-hoc package list."""
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "pip install -r requirements.txt" in ci


# ===========================================================================
# 22. SECRETS HYGIENE (SEC-003)
# ===========================================================================
# .env.example is the committed onboarding template — it must exist and
# must never contain an actual secret value.


def test_env_example_exists_with_placeholders_only():
    """SEC-003: .env.example declares the required vars with empty values."""
    env_example = ROOT / ".env.example"
    assert env_example.exists(), ".env.example template is missing"

    text = env_example.read_text()
    assignments = dict(
        line.split("=", 1)
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    )

    assert "FASTCHAT_API_KEY" in assignments
    for key, value in assignments.items():
        assert value.strip() == "", f"{key} in .env.example must be a placeholder, not a value"


# ===========================================================================
# 23. DIMENSION EXTRACTOR DOCUMENT LIFECYCLE (BUG-003)
# ===========================================================================
# _render_page used to fitz.open() the PDF for every page render and never
# close it — one leaked handle plus a full re-parse per page. The document
# must now be opened exactly once per extract() call and always closed.
# fitz and the vision API are stubbed — no files, no network.

_SCAN_JSON = '{"has_dimensions": true, "page_type": "package_drawing", "package_type": "SOIC-16"}'
_EXTRACT_JSON = '{"package_type": "SOIC-16", "unit": "mm", "dimensions": {"e": 1.27, "D": 9.9}}'


class _FakePixmap:
    def tobytes(self, fmt):
        return b"png-bytes"


class _FakePage:
    def get_pixmap(self, matrix=None):
        return _FakePixmap()

    def get_text(self):
        # No text content: the text-based phase finds nothing and the
        # extractor falls through to the vision flow under test here.
        return ""


class _FakeFitzDoc:
    def __init__(self):
        self.closed = False

    def __len__(self):
        return 3

    def __getitem__(self, index):
        return _FakePage()

    def close(self):
        self.closed = True


class _FakeFitz:
    Matrix = staticmethod(lambda *a: None)

    def __init__(self):
        self.open_calls = 0
        self.docs = []

    def open(self, path):
        self.open_calls += 1
        doc = _FakeFitzDoc()
        self.docs.append(doc)
        return doc


@pytest.fixture
def _dim_extractor(monkeypatch):
    from src.pdf_extractor import dimension_extractor as dim_mod

    fake_fitz = _FakeFitz()
    monkeypatch.setattr(dim_mod, "fitz", fake_fitz)
    monkeypatch.setattr(dim_mod.time, "sleep", lambda s: None)
    return dim_mod, fake_fitz


def test_extract_opens_document_once_and_closes(_dim_extractor, monkeypatch):
    """BUG-003: a full scan+extract run must use a single, closed fitz handle."""
    dim_mod, fake_fitz = _dim_extractor

    def _fake_api(self, image_bytes, prompt):
        return _SCAN_JSON if prompt == dim_mod.SCAN_PROMPT else _EXTRACT_JSON

    monkeypatch.setattr(dim_mod.DimensionExtractor, "_call_api", _fake_api)

    result = dim_mod.DimensionExtractor().extract("fake.pdf")

    assert result is not None and result["e"] == 1.27
    assert fake_fitz.open_calls == 1, "PDF must be opened exactly once per extract()"
    assert all(doc.closed for doc in fake_fitz.docs)


def test_extract_closes_document_on_failure(_dim_extractor, monkeypatch):
    """BUG-003: the handle is closed even when the vision API blows up."""
    dim_mod, fake_fitz = _dim_extractor

    def _boom(self, image_bytes, prompt):
        raise RuntimeError("vision API down")

    monkeypatch.setattr(dim_mod.DimensionExtractor, "_call_api", _boom)

    result = dim_mod.DimensionExtractor().extract("fake.pdf")

    assert result is None
    assert fake_fitz.open_calls == 1
    assert all(doc.closed for doc in fake_fitz.docs)


# ===========================================================================
# 24. TEXT-BASED DIMENSION EXTRACTION (no vision API, no table of contents)
# ===========================================================================
# Dimensions in vector-drawn datasheets are real PDF text. The text phase
# must find drawing pages by scanning page content only — never the PDF
# table of contents — and its output must pass the plausibility gate that
# also guards the vision fallback.

import fitz as _fitz

from src.pdf_extractor.text_dimensions import (
    extract_text_dimensions,
    find_dimension_pages,
    parse_prose,
    parse_ti_outline,
    plausible_dims,
)

# Ground truth read visually from the drawings (see test_dimension_api.py).
_TSSOP16_TRUTH = {"e": 0.65, "E": 6.4, "D": 5.0, "b": 0.235, "L": 0.625, "A": 1.2}


def test_text_dims_ti_tssop16_matches_ground_truth():
    with _fitz.open("pdfs/74HC595_TI.pdf") as doc:
        result = extract_text_dimensions(doc, target_package_type="TSSOP-16")

    assert result is not None
    for key, truth in _TSSOP16_TRUTH.items():
        assert result.get(key) == pytest.approx(truth, abs=0.05), key


def test_text_dims_selects_target_variant_among_multiple_drawings():
    # 74HC595 documents SOIC/CDIP/LCCC/TSSOP/PDIP/SSOP variants; asking for
    # SSOP must not return TSSOP values even though both are 0.65mm pitch.
    with _fitz.open("pdfs/74HC595_TI.pdf") as doc:
        result = extract_text_dimensions(doc, target_package_type="SSOP-16")

    assert result is not None
    assert result["e"] == pytest.approx(0.65, abs=0.03)
    assert result["E"] == pytest.approx(7.8, abs=0.1)   # SSOP span, not TSSOP 6.4
    assert result["A"] == pytest.approx(2.0, abs=0.05)  # SSOP height, not TSSOP 1.2


def test_text_dims_prose_style_ft232r():
    # FTDI states dimensions in prose; the drawing itself is a raster image.
    with _fitz.open("pdfs/FT232R.pdf") as doc:
        result = extract_text_dimensions(doc, target_package_type="SSOP-28")

    assert result is not None
    assert result["e"] == pytest.approx(0.65, abs=0.03)
    assert result["D"] == pytest.approx(10.2, abs=0.1)
    assert result["E1"] == pytest.approx(5.3, abs=0.1)


def test_text_dims_work_without_table_of_contents():
    # Many datasheets have no TOC/bookmarks; page discovery must rely on
    # page content only. Strip the TOC and expect identical results.
    with _fitz.open("pdfs/74HC595_TI.pdf") as doc:
        with_toc = extract_text_dimensions(doc, target_package_type="TSSOP-16")
        doc.set_toc([])
        without_toc = extract_text_dimensions(doc, target_package_type="TSSOP-16")

    assert without_toc == with_toc
    assert without_toc is not None


def test_find_dimension_pages_skips_board_layout_pages():
    with _fitz.open("pdfs/74HC595_TI.pdf") as doc:
        pages = find_dimension_pages(doc)
        texts = [doc[p].get_text().upper() for p in pages]

    assert pages, "expected mechanical drawing pages to be found"
    assert all("BOARD LAYOUT" not in t for t in texts)


def test_parse_ti_outline_pitch_crosscheck_rejects_bad_span():
    # If the "2X <row span>" annotation contradicts the pitch, drop the pitch.
    text = "14X 0.65\n2X 9.99\n"
    assert "e" not in parse_ti_outline(text, 16)


def test_parse_prose_orders_body_axes():
    text = "nominally 10.20mm x 5.30mm body (7.80mm x 10.20mm including pins) on a 0.65 mm pitch"
    dims = parse_prose(text)
    assert dims["E1"] == 5.30 and dims["D"] == 10.20
    assert dims["E"] == 7.80 and dims["e"] == 0.65


def test_package_designator_from_part_number():
    from src.pdf_extractor.part_number_hint import package_designator_from_part_number as pd

    assert pd("SN74HC595DW") == "DW"
    assert pd("SN74HC595DWR") == "DW"   # tape/reel suffix stripped
    assert pd("SN74HC595D") == "D"
    assert pd("SN74HC595PWR") == "PW"
    assert pd("SN74HC595N") == "N"
    assert pd("sn74hc595dbr") == "DB"
    assert pd("SN74HC595") is None      # no package suffix
    assert pd("ATMEGA328P-PU") is None  # non-TI convention must not misfire
    assert pd(None) is None


def test_text_dims_pick_variant_by_part_number_designator():
    # The 74HC595 datasheet carries only the WIDE SOIC drawing (DW0016A).
    # A DW part number must match it; a narrow D part must NOT silently
    # receive wide-body dimensions (fall back to JEDEC defaults instead).
    with _fitz.open("pdfs/74HC595_TI.pdf") as doc:
        wide = extract_text_dimensions(
            doc, target_package_type="SOIC-16", part_number="SN74HC595DWR"
        )
        narrow = extract_text_dimensions(
            doc, target_package_type="SOIC-16", part_number="SN74HC595D"
        )

    assert wide is not None
    assert wide["A"] == pytest.approx(2.65, abs=0.05)  # DW height
    assert narrow is None


class _HintPage:
    def __init__(self, page_number):
        self.page_number = page_number
        self.reasons = ["mechanical drawing"]


def test_extract_vision_path_respects_part_number_designator(monkeypatch):
    from src.pdf_extractor import dimension_extractor as dim_mod

    def _fake_api(self, image_bytes, prompt):
        return _FULL_SOIC_EXTRACT_JSON

    monkeypatch.setattr(dim_mod.DimensionExtractor, "_call_api", _fake_api)
    monkeypatch.setattr(dim_mod.time, "sleep", lambda s: None)
    hints = [_HintPage(24)]  # 1-indexed: the DW0016A wide-SOIC drawing page

    wide = dim_mod.DimensionExtractor().extract(
        "pdfs/74HC595_TI.pdf", target_package_type="SOIC-16",
        hint_pages=hints, part_number="SN74HC595DW",
    )
    assert wide is not None
    assert wide["E"] == pytest.approx(10.325, abs=0.01)

    narrow = dim_mod.DimensionExtractor().extract(
        "pdfs/74HC595_TI.pdf", target_package_type="SOIC-16",
        hint_pages=hints, part_number="SN74HC595D",
    )
    assert narrow is None  # no D drawing in this PDF -> no override


def test_extract_rejects_wrong_variant_from_codeless_page(monkeypatch):
    # Old-style "MECHANICAL DATA" pages carry no TI drawing code, so the
    # designator page-filter cannot exclude them. If such a page yields
    # wide-SOIC dims for a narrow-D part, the lead-span consistency gate
    # must reject the override (JEDEC narrow defaults are then correct).
    from src.pdf_extractor import dimension_extractor as dim_mod

    def _fake_api(self, image_bytes, prompt):
        return _FULL_SOIC_EXTRACT_JSON  # wide SOIC: E = 10.00-10.65

    monkeypatch.setattr(dim_mod.DimensionExtractor, "_call_api", _fake_api)
    monkeypatch.setattr(dim_mod.time, "sleep", lambda s: None)
    hints = [_HintPage(33)]  # 1-indexed: codeless mechanical-data page

    narrow = dim_mod.DimensionExtractor().extract(
        "pdfs/74HC595_TI.pdf", target_package_type="SOIC-16",
        hint_pages=hints, part_number="SN74HC595D",
    )
    assert narrow is None

    wide = dim_mod.DimensionExtractor().extract(
        "pdfs/74HC595_TI.pdf", target_package_type="SOIC-16",
        hint_pages=hints, part_number="SN74HC595DW",
    )
    assert wide is not None
    assert wide["E"] == pytest.approx(10.325, abs=0.01)


def test_plausible_dims_rejects_scrambled_vision_output():
    # Real responses observed from the vision API on 74HC595: values read
    # off the drawing but assigned to the wrong dimension letters.
    scrambled_tssop = {"e": 0.15, "E": 0.75, "D": 0.3, "b": 4.5, "L": 0.25, "A": 6.2}
    scrambled_soic = {"e": 0.07, "D": 9.3, "E1": 0.05, "A": 2.65, "b": 1.27, "L": 0.07}
    assert not plausible_dims(scrambled_tssop)
    assert not plausible_dims(scrambled_soic)


def test_plausible_dims_accepts_real_packages():
    assert plausible_dims(_TSSOP16_TRUTH)
    assert plausible_dims({"e": 1.27, "E": 6.0, "D": 9.9, "b": 0.41, "A": 1.75})  # SOIC-16
    assert plausible_dims({"e": 2.54, "E": 7.62, "b": 0.46, "A": 4.57})           # DIP


_PARTIAL_TEXT_DIMS = {
    "package_type": "SOIC",
    "unit": "mm",
    "A": 2.65,
    "e": 1.27,
    "b": 0.45,
}

_FULL_SOIC_EXTRACT_JSON = (
    '{"package_type": "SOIC-16", "unit": "mm", "dimensions": {'
    '"b": {"min": "0.31", "max": "0.51"},'
    '"D": {"min": "9.80", "max": "10.00"},'
    '"E": {"min": "10.00", "max": "10.65"},'
    '"e": "1.27",'
    '"L": {"min": "0.40", "max": "1.27"}}}'
)


def test_partial_text_result_does_not_short_circuit_vision(_dim_extractor, monkeypatch):
    # 74HC595 regression: text extraction returned only A/e/b and the vision
    # phase (which reads the full table) never ran. Partial text hits must
    # continue to vision and merge, with deterministic text values winning.
    dim_mod, _ = _dim_extractor
    monkeypatch.setattr(
        dim_mod, "extract_text_dimensions", lambda doc, tgt=None, **kw: dict(_PARTIAL_TEXT_DIMS)
    )

    def _fake_api(self, image_bytes, prompt):
        return _SCAN_JSON if prompt == dim_mod.SCAN_PROMPT else _FULL_SOIC_EXTRACT_JSON

    monkeypatch.setattr(dim_mod.DimensionExtractor, "_call_api", _fake_api)

    result = dim_mod.DimensionExtractor().extract("fake.pdf", target_package_type="SOIC-16")

    assert result is not None
    # vision fills the keys text missed
    assert result["E"] == pytest.approx(10.325, abs=0.01)
    assert result["D"] == pytest.approx(9.90, abs=0.01)
    assert result["L"] == pytest.approx(0.835, abs=0.01)
    # text (deterministic) wins over vision for keys both provide
    assert result["b"] == pytest.approx(0.45, abs=0.001)


def test_complete_text_result_skips_vision(_dim_extractor, monkeypatch):
    dim_mod, _ = _dim_extractor
    complete = {
        "package_type": "SOIC-16", "unit": "mm",
        "e": 1.27, "E": 6.0, "D": 9.9, "b": 0.41, "L": 0.84,
    }
    monkeypatch.setattr(
        dim_mod, "extract_text_dimensions", lambda doc, tgt=None, **kw: dict(complete)
    )

    def _no_api(self, image_bytes, prompt):
        raise AssertionError("vision API must not be called for a complete text result")

    monkeypatch.setattr(dim_mod.DimensionExtractor, "_call_api", _no_api)

    result = dim_mod.DimensionExtractor().extract("fake.pdf", target_package_type="SOIC-16")
    assert result == complete


def test_partial_text_result_survives_vision_failure(_dim_extractor, monkeypatch):
    # If vision yields nothing, the partial text dims are still a valid
    # override (the builder overlays them on JEDEC defaults).
    dim_mod, _ = _dim_extractor
    monkeypatch.setattr(
        dim_mod, "extract_text_dimensions", lambda doc, tgt=None, **kw: dict(_PARTIAL_TEXT_DIMS)
    )

    def _boom(self, image_bytes, prompt):
        raise RuntimeError("vision API down")

    monkeypatch.setattr(dim_mod.DimensionExtractor, "_call_api", _boom)

    result = dim_mod.DimensionExtractor().extract("fake.pdf", target_package_type="SOIC-16")
    assert result == _PARTIAL_TEXT_DIMS


def test_merge_candidates_combines_partial_pages():
    from src.pdf_extractor.dimension_extractor import DimensionExtractor

    candidates = [
        {"page": 3, "data": {"package_type": "SOIC-16", "unit": "mm", "dimensions": {
            "e": "1.27", "b": {"min": "0.31", "max": "0.51"},
        }}},
        {"page": 5, "data": {"package_type": "SOIC-16", "unit": "mm", "dimensions": {
            "E": {"min": "10.00", "max": "10.65"},
            "D": {"min": "9.80", "max": "10.00"},
            "L": {"min": "0.40", "max": "1.27"},
            "b": "0.4",  # single value must NOT displace page 3's min/max pair
        }}},
    ]

    merged = DimensionExtractor()._merge_candidates(candidates)
    dims = merged["dimensions"]
    assert set(dims) == {"e", "b", "E", "D", "L"}
    assert dims["b"] == {"min": "0.31", "max": "0.51"}


def test_merge_candidates_ignores_other_package_families():
    from src.pdf_extractor.dimension_extractor import DimensionExtractor

    candidates = [
        {"page": 3, "data": {"package_type": "SOIC-16", "unit": "mm", "dimensions": {
            "e": "1.27", "E": {"min": "5.80", "max": "6.20"},
        }}},
        {"page": 9, "data": {"package_type": "PDIP-16", "unit": "mm", "dimensions": {
            "e": "2.54", "E": "7.62", "D": "19.3", "b": "0.46", "L": "3.3",
        }}},
    ]

    merged = DimensionExtractor()._merge_candidates(candidates)
    dims = merged["dimensions"]
    # PDIP page has more keys and would win a completeness contest, but it
    # must not contribute values to a SOIC merge... the base is whichever
    # scores best; the other family is excluded entirely.
    assert merged["package_type"] == "PDIP-16"
    assert dims["e"] == "2.54"
    assert "E" in dims and dims["E"] == "7.62"


def test_vision_fallback_result_is_gated(_dim_extractor, monkeypatch):
    # A vision response with implausible values must be discarded, not
    # forwarded into footprint geometry.
    dim_mod, _ = _dim_extractor
    bad_extract = (
        '{"package_type": "SOIC-16", "unit": "mm",'
        ' "dimensions": {"e": 0.07, "b": 1.27, "D": 9.3}}'
    )

    def _fake_api(self, image_bytes, prompt):
        return _SCAN_JSON if prompt == dim_mod.SCAN_PROMPT else bad_extract

    monkeypatch.setattr(dim_mod.DimensionExtractor, "_call_api", _fake_api)

    assert dim_mod.DimensionExtractor().extract("fake.pdf") is None


# ===========================================================================
# 25. JEDEC FOOTPRINT DEFAULTS (footprints must not inherit display dims)
# ===========================================================================
# Schematic symbols use exaggerated "display" proportions for readability
# (e.g. DIP: 2.5mm pitch / 20mm body). Footprints must default to real
# JEDEC package dimensions instead, with PDF-extracted dims overriding.

from src.package_types.footprint_defaults import get_footprint_defaults


def _glb_pad_positions(path):
    glb = GLTF2().load(str(path))
    pos = {}
    for n in glb.nodes:
        if n.extras and "pinData" in n.extras:
            p = n.extras["pinData"]["position"]
            pos[int(n.name)] = (p["x"], p["y"])
    return pos


def _row_spacing_and_pitch(pos):
    xs = sorted({round(x, 3) for x, _ in pos.values()})
    ys = sorted({round(y, 3) for _, y in pos.values()})
    row_spacing = xs[-1] - xs[0]
    pitch = ys[1] - ys[0]
    return row_spacing, pitch


def test_dip8_footprint_uses_jedec_row_spacing(tmp_path):
    out = tmp_path / "dip8.glb"
    pins = [{"number": n, "name": f"P{n}"} for n in range(1, 9)]
    assert build_pcb_footprint_direct("DIP-8", 8, "NE555", pins, str(out))

    row_spacing, pitch = _row_spacing_and_pitch(_glb_pad_positions(out))
    assert row_spacing == pytest.approx(7.62, abs=0.01), "DIP rows must be 300mil apart"
    assert pitch == pytest.approx(2.54, abs=0.01), "DIP pitch must be 100mil"


def test_tssop16_footprint_uses_jedec_defaults(tmp_path):
    out = tmp_path / "tssop16.glb"
    pins = [{"number": n, "name": f"P{n}"} for n in range(1, 17)]
    assert build_pcb_footprint_direct("TSSOP-16", 16, "X", pins, str(out))

    # IPC-7351: pads centered on the lead foot -> span = E - L = 6.4 - 0.6
    row_spacing, pitch = _row_spacing_and_pitch(_glb_pad_positions(out))
    assert row_spacing == pytest.approx(5.8, abs=0.01)
    assert pitch == pytest.approx(0.65, abs=0.01)


def test_soic16_footprint_uses_jedec_defaults(tmp_path):
    out = tmp_path / "soic16.glb"
    pins = [{"number": n, "name": f"P{n}"} for n in range(1, 17)]
    assert build_pcb_footprint_direct("SOIC-16", 16, "X", pins, str(out))

    # narrow SOIC: pad span = E - L = 6.0 - 0.84
    row_spacing, pitch = _row_spacing_and_pitch(_glb_pad_positions(out))
    assert row_spacing == pytest.approx(5.16, abs=0.01)
    assert pitch == pytest.approx(1.27, abs=0.01)


from src.schematic_generator.pcb_footprint_builder import PcbFootprintBuilder


def test_through_hole_pad_has_annular_ring():
    # IPC minimum annular ring: pad = drill + 2 * 0.35mm ring.
    # Reference: Ultra Librarian DIP16_300_TEX uses 1.524 pad / 0.813 drill.
    b = PcbFootprintBuilder("DIP-16", 16, "X")
    assert b.pad_spec["shape"] == "circle"
    assert b.pad_spec["diameter"] == pytest.approx(1.53, abs=0.05)
    assert b.pad_spec["mask_diameter"] > b.pad_spec["diameter"]


def test_smd_pads_are_rects_sized_from_b_and_l():
    # IPC-7351 gull-wing: length = L + toe + heel, width = b + side margins.
    b = PcbFootprintBuilder("TSSOP-16", 16, "X")
    assert b.pad_spec["shape"] == "rect"
    assert b.pad_spec["length"] == pytest.approx(0.6 + 0.7, abs=0.05)
    assert b.pad_spec["width"] == pytest.approx(0.25 + 0.06, abs=0.02)
    # adjacent pads must keep clearance at 0.65mm pitch
    assert b.pad_spec["width"] <= 0.65 - 0.2


def test_smd_pad_width_respects_extracted_b():
    b = PcbFootprintBuilder(
        "SOIC-16", 16, "X",
        extracted_dims={"e": 1.27, "E": 10.325, "b": 0.51, "L": 0.835},
    )
    assert b.pad_spec["shape"] == "rect"
    assert b.pad_spec["width"] == pytest.approx(0.51 + 0.06, abs=0.02)
    assert b.pad_spec["length"] == pytest.approx(0.835 + 0.7, abs=0.05)


def test_grid_array_footprints_fail_closed(tmp_path):
    # ADXL345 flow-eval find: its LGA-14 rendered as a two-row perimeter
    # footprint with an invented pitch — plausible-looking, never fits the
    # part. Grid-array/leadless packages must refuse footprint generation
    # (ARCH-006) while the schematic symbol stays available.
    from src.exceptions import SchematicGenerationError
    from src.schematic_generator.pinout_diagram_builder import build_pinout_diagram

    pins = [{"number": str(i), "name": f"P{i}"} for i in range(1, 15)]
    for pkg in ("BGA-14", "LGA-14", "LCCC-20"):
        with pytest.raises(SchematicGenerationError, match="grid-array/leadless"):
            build_pcb_footprint_direct(pkg, 14, "ADXL345", pins, str(tmp_path / "no.glb"))
    assert not (tmp_path / "no.glb").exists()

    # The schematic for the same package still builds.
    out = tmp_path / "adxl_schematic.glb"
    assert build_pinout_diagram("BGA-14", 14, "ADXL345", pins, str(out))
    assert out.exists()


def test_schematic_glb_carries_frontend_extras(tmp_path):
    # The platform reference schematic carries extras on every node (pin
    # groups: id/side/pinLength/pinName; text: pinNumber; pinName: the name
    # string; BodyLine: polyline points). The cadquery export produced none,
    # so the frontend could not attach wires or show labels.
    from pygltflib import GLTF2
    from src.schematic_generator.pinout_diagram_builder import build_pinout_diagram

    out = tmp_path / "lm358_schematic.glb"
    pins = [
        {"number": "1", "name": "OUT1"}, {"number": "2", "name": "IN1-"},
        {"number": "3", "name": "IN1+"}, {"number": "4", "name": "V-"},
        {"number": "5", "name": "IN2+"}, {"number": "6", "name": "IN2-"},
        {"number": "7", "name": "OUT2"}, {"number": "8", "name": "V+"},
    ]
    assert build_pinout_diagram("DIP-8", 8, "LM358", pins, str(out))

    g = GLTF2().load(str(out))
    root = g.nodes[g.scenes[g.scene or 0].nodes[0]]
    assert root.extras["viewType"] == "schematic"

    pin_groups = {n.extras["id"][0]: n for n in g.nodes if "id" in (n.extras or {})}
    assert sorted(pin_groups, key=int) == [str(i) for i in range(1, 9)]
    # DIP-8 symbol: 1-4 on the left (side 0), 5-8 on the right (side 2).
    assert all(pin_groups[str(i)].extras["side"] == 0 for i in range(1, 5))
    assert all(pin_groups[str(i)].extras["side"] == 2 for i in range(5, 9))
    assert pin_groups["8"].extras["pinName"] == "V+"
    assert pin_groups["1"].extras["pinLength"] > 0

    node_by_index = g.nodes
    children = {node_by_index[ci].name: node_by_index[ci] for ci in pin_groups["1"].children}
    assert children["text"].extras["pinNumber"] == "1"
    assert children["pinName"].extras["pinName"] == "OUT1"

    labels = {n.name: n.extras for n in g.nodes if "value" in (n.extras or {}) and "id" not in (n.extras or {})}
    assert labels["DesignatorName"]["value"] == "U"
    assert labels["PackageValue"]["value"] == "LM358"

    points = next(n.extras["points"] for n in g.nodes if "points" in (n.extras or {}))
    assert len(points) == 5 and points[0] == points[-1]


def test_schematic_quad_side_codes(tmp_path):
    # Reference side convention: 0=left, 1=top, 2=right, 3=bottom. Quad
    # packages number pins counterclockwise from the top-left corner.
    from pygltflib import GLTF2
    from src.schematic_generator.pinout_diagram_builder import build_pinout_diagram

    out = tmp_path / "qfn20_schematic.glb"
    pins = [{"number": str(i), "name": f"P{i}"} for i in range(1, 21)]
    assert build_pinout_diagram("QFN-20", 20, "NRF24L01", pins, str(out))

    g = GLTF2().load(str(out))
    sides = {}
    for n in g.nodes:
        e = n.extras or {}
        if "id" in e:
            sides.setdefault(e["side"], set()).add(int(e["id"][0]))
    assert sides[0] == {1, 2, 3, 4, 5}
    assert sides[3] == {6, 7, 8, 9, 10}
    assert sides[2] == {11, 12, 13, 14, 15}
    assert sides[1] == {16, 17, 18, 19, 20}


def test_glb_pin_extras_match_pad_spec(tmp_path):
    # The pinData extras must mirror the computed pad_spec: an SMD footprint
    # with real b/L dims gets rectangle pads, not the legacy 1.25mm circles.
    out = tmp_path / "soic16_extras.glb"
    pins = [{"number": n, "name": f"P{n}"} for n in range(1, 17)]
    assert build_pcb_footprint_direct(
        "SOIC-16", 16, "X", pins, str(out),
        extracted_dims={"e": 1.27, "E": 10.325, "D": 9.90, "b": 0.41, "L": 0.835},
    )

    glb = GLTF2().load(str(out))
    pads = {
        n.name: n.extras["pinData"]
        for n in glb.nodes
        if n.extras and "pinData" in n.extras
    }
    assert len(pads) == 16
    for pd in pads.values():
        assert pd["pinType"] == "SMD"
        assert pd["pinShape"] == "rectangle"
        assert pd.get("outerDiameter") is None
        # SOIC pins sit on left/right columns: pad length runs along X
        assert pd["length"] == pytest.approx(0.835 + 0.7, abs=0.01)
        assert pd["width"] == pytest.approx(0.41 + 0.06, abs=0.01)


def test_glb_through_hole_extras_use_pad_spec(tmp_path):
    # Through-hole pinData must carry the annular-ring pad diameter and the
    # real drill size from pad_spec, not hardcoded 1.25/0.83 legacy values.
    out = tmp_path / "dip16_extras.glb"
    pins = [{"number": n, "name": f"P{n}"} for n in range(1, 17)]
    assert build_pcb_footprint_direct("DIP-16", 16, "X", pins, str(out))

    glb = GLTF2().load(str(out))
    pads = {
        n.name: n.extras["pinData"]
        for n in glb.nodes
        if n.extras and "pinData" in n.extras
    }
    assert len(pads) == 16
    for num, pd in pads.items():
        assert pd["pinType"] == "ThroughHole"
        assert pd["innerDiameter"] == pytest.approx(0.83, abs=0.01)
        if num == "1":
            assert pd["pinShape"] == "rectangle"
            assert pd["length"] == pytest.approx(0.83 + 2 * 0.35, abs=0.01)
        else:
            assert pd["pinShape"] == "circle"
            assert pd["outerDiameter"] == pytest.approx(0.83 + 2 * 0.35, abs=0.01)


def test_fab_outline_uses_body_width_not_lead_span():
    # SOIC-16 narrow: body E1 = 3.9, lead span E = 6.0. The drawn body
    # must be E1 wide while pads stay placed from E.
    b = PcbFootprintBuilder("SOIC-16", 16, "X")
    assert b.fab_outline_width == pytest.approx(3.9, abs=0.01)
    assert abs(b.pin_positions[0].x) == pytest.approx((6.0 - 0.84) / 2, abs=0.01)

    b2 = PcbFootprintBuilder("DIP-16", 16, "X")
    assert b2.fab_outline_width == pytest.approx(6.35, abs=0.01)
    assert abs(b2.pin_positions[0].x) == pytest.approx(7.62 / 2, abs=0.01)


def test_dip16_pins_match_official_kicad_footprint(tmp_path):
    # Per-pin regression against the Ultra Librarian DIP16_300_TEX footprint.
    kicad_mod = Path("ul_74HC595/KiCADv6/footprints.pretty/DIP16_300_TEX.kicad_mod")
    if not kicad_mod.exists():
        pytest.skip("official footprint fixture not present")

    import re as _re
    text = kicad_mod.read_text()
    matches = _re.findall(r'\(pad "(\d+)" thru_hole \w+ \(at ([\d.-]+) ([\d.-]+)\)', text)
    official = {int(n): (float(x), float(y)) for n, x, y in matches}
    ox = [p[0] for p in official.values()]
    oy = [p[1] for p in official.values()]
    cx, cy = (min(ox) + max(ox)) / 2, (min(oy) + max(oy)) / 2

    out = tmp_path / "dip16.glb"
    pins = [{"number": n, "name": f"P{n}"} for n in range(1, 17)]
    assert build_pcb_footprint_direct("DIP-16", 16, "74HC595", pins, str(out))
    ours = _glb_pad_positions(out)

    for n, (x, y) in official.items():
        # KiCad Y grows downward; ours grows upward
        expected = (x - cx, -(y - cy))
        assert ours[n][0] == pytest.approx(expected[0], abs=0.01), f"pin {n} x"
        assert ours[n][1] == pytest.approx(expected[1], abs=0.01), f"pin {n} y"


def test_footprint_pad_columns_centered_on_body(tmp_path):
    out = tmp_path / "soic16_centered.glb"
    pins = [{"number": n, "name": f"P{n}"} for n in range(1, 17)]
    assert build_pcb_footprint_direct(
        "SOIC-16", 16, "X", pins, str(out),
        extracted_dims={"e": 1.27, "E": 10.325, "D": 9.90, "b": 0.41, "L": 0.835},
    )

    # Real body dims must not inherit the schematic top_margin offset:
    # each pad column has to be symmetric about the body center (y=0).
    pos = _glb_pad_positions(out)
    ys = [y for _, y in pos.values()]
    assert (max(ys) + min(ys)) / 2 == pytest.approx(0.0, abs=0.01)


def test_extracted_dims_still_override_jedec_defaults(tmp_path):
    out = tmp_path / "tssop16_dims.glb"
    pins = [{"number": n, "name": f"P{n}"} for n in range(1, 17)]
    assert build_pcb_footprint_direct(
        "TSSOP-16", 16, "X", pins, str(out),
        extracted_dims={"e": 0.65, "E": 6.6},
    )

    # extracted E=6.6 wins over JEDEC 6.4; default L=0.6 still insets pads
    row_spacing, _ = _row_spacing_and_pitch(_glb_pad_positions(out))
    assert row_spacing == pytest.approx(6.0, abs=0.01)


def test_pdip_footprint_is_through_hole_at_drill_spacing(tmp_path):
    # PDIP was previously treated as SMD (startswith check missed it) and
    # through-hole rows must sit at the drill spacing with no IPC inset.
    out = tmp_path / "pdip8.glb"
    pins = [{"number": n, "name": f"P{n}"} for n in range(1, 9)]
    assert build_pcb_footprint_direct("PDIP-8", 8, "X", pins, str(out))

    glb = GLTF2().load(str(out))
    pin_types = {
        n.extras["pinData"]["pinType"]
        for n in glb.nodes
        if n.extras and "pinData" in n.extras
    }
    assert pin_types == {"ThroughHole"}

    row_spacing, pitch = _row_spacing_and_pitch(_glb_pad_positions(out))
    assert row_spacing == pytest.approx(7.62, abs=0.01)
    assert pitch == pytest.approx(2.54, abs=0.01)


def test_schematic_symbol_keeps_display_proportions():
    # The readable schematic-symbol geometry must be unaffected.
    params = get_schematic_parameters("DIP-8", 8)
    assert params.body_width == 20.0
    assert params.pin_pitch == 2.5


def test_so_alias_resolves_to_soic():
    # AMS1117 datasheet calls its package "SO-8" — the classic name for
    # SOIC-8. Must resolve instead of failing as unknown (flow eval find).
    from src.package_types.package_geometry import parse_package_type, PackageType
    assert parse_package_type("SO-8") == PackageType.SOIC
    # The 2-letter alias must not shadow longer families via prefix match,
    # and must not swallow unsupported letter-adjacent families like SOJ.
    assert parse_package_type("SON-8") == PackageType.SON
    assert parse_package_type("SOP-16") == PackageType.SOIC
    with pytest.raises(Exception):
        parse_package_type("SOJ-16")


def test_sot23_family_is_supported():
    # INA219 ships in SOT23-8 (JEDEC MO-178), a dual-row gull-wing package;
    # it must build with SOIC-class geometry and MO-178 dimensions.
    from src.package_types.package_geometry import parse_package_type, PackageType
    assert parse_package_type("SOT-23-8") == PackageType.SOIC
    assert parse_package_type("SOT23-8") == PackageType.SOIC

    d8 = get_footprint_defaults("SOT23-8", 8)
    assert d8["e"] == 0.65 and d8["E"] == 2.8 and d8["E1"] == 1.63
    d6 = get_footprint_defaults("SOT-23-6", 6)
    assert d6["e"] == 0.95 and d6["E"] == 2.8


def test_sot23_8_footprint_grid(tmp_path):
    out = tmp_path / "sot23_8.glb"
    pins = [{"number": n, "name": f"P{n}"} for n in range(1, 9)]
    assert build_pcb_footprint_direct("SOT-23-8", 8, "INA219", pins, str(out))

    # IPC: pads centered on the lead foot -> span = E - L = 2.8 - 0.45
    row_spacing, pitch = _row_spacing_and_pitch(_glb_pad_positions(out))
    assert row_spacing == pytest.approx(2.35, abs=0.01)
    assert pitch == pytest.approx(0.65, abs=0.01)

    d = get_footprint_defaults("SO-8", 8)
    assert d is not None and d["E"] == 6.0 and d["e"] == 1.27


def test_family_from_page_designators():
    # TI pin-table headers name the mechanical designator; that names the
    # package family ("DSC PACKAGE" = VSON/WSON — the TPS63060 case where
    # the LLM invented QFN-12).
    from src.pdf_extractor.part_number_hint import family_from_page_designators as ffd
    assert ffd("DSC PACKAGE\n(TOP VIEW)") == "WSON"
    assert ffd("DCN PACKAGE (TOP VIEW)") == "SOT23"
    assert ffd("PW PACKAGE (TOP VIEW)") == "TSSOP"
    # Multi-designator headers are ambiguous without a part number...
    header_74 = "D, DW, N, NS, OR PW PACKAGE\n(TOP VIEW)"
    assert ffd(header_74) is None
    # ...but the part-number designator resolves them.
    assert ffd(header_74, part_number="SN74HC595PWR") == "TSSOP"
    assert ffd(header_74, part_number="SN74HC595DWR") == "SOIC"
    # No designator header at all -> None, never a guess.
    assert ffd("Pin Functions PIN I/O DESCRIPTION") is None
    # The content extractor squeezes spaces ("DSCPACKAGE"); headers must
    # still parse in that form.
    assert ffd("DSCPACKAGE\n(TOPVIEW)") == "WSON"
    assert ffd("D,DW,N,NS,ORPWPACKAGE", part_number="SN74HC595PWR") == "TSSOP"


def test_fused_name_number_column_parses_all_pins():
    # TPS63060's pin table fuses "NAME NO." into one cell ("L2 10"); the
    # parser dropped that row (label check failed on "L210") and kept
    # fused names like "L1 1". All ten pins must parse with clean names.
    from src.pdf_extractor.deterministic_table_parser import _parse_table_rows
    table = [
        ["PIN\nNAME NO.", "I/O", "DESCRIPTION"],
        ["EN 3", "I", "Enable input."],
        ["FB 8", "I", "Voltage feedback."],
        ["GND 7", "", "Control ground"],
        ["L1 1", "I", "Connection for Inductor"],
        ["L2 10", "I", "Connection for Inductor"],
        ["PS/SYNC 4", "I", "Power save mode"],
        ["PG 5", "O", "Power good"],
        ["PGND PowerPAD™", "", "Power ground"],
        ["VIN 2", "I", "Supply voltage"],
        ["VOUT 9", "O", "Converter output"],
        ["VAUX 6", "", "Connection for Capacitor"],
    ]
    cand = _parse_table_rows(table, 4, "DSCPACKAGE (TOPVIEW)", "TPS63060")
    assert cand is not None
    pins = {p.number: p.name for p in cand.pin_data.pins}
    assert len(pins) == 10
    assert pins[10] == "L2"
    assert pins[1] == "L1"
    assert pins[9] == "VOUT"
    assert cand.pin_data.package.type == "WSON-10"


def test_multi_package_pin_table_selects_family_column():
    # LM358's Table 4-1 lists one pin-number column per package group
    # (LCCC vs SOIC/PDIP/...). Reading the first numeric cell took the
    # 20-pin LCCC numbering — the NC row alone contributed 12 pins — so
    # an 8-pin part extracted 16-20 pins nondeterministically.
    from src.pdf_extractor.deterministic_table_parser import _parse_table_rows
    table = [
        ["PIN", "", "", "", ""],
        ["NAME", "LCCC(1)", "SOIC, SOT23-8, VSSOP, CDIP, PDIP, SO, TSSOP", "I/O", "DESCRIPTION"],
        ["IN1–", "5", "2", "I", "Negative input"],
        ["IN1+", "7", "3", "I", "Positive input"],
        ["IN2–", "15", "6", "I", "Negative input"],
        ["IN2+", "12", "5", "I", "Positive input"],
        ["OUT1", "2", "1", "O", "Output"],
        ["OUT2", "17", "7", "O", "Output"],
        ["V–", "10", "4", "—", "Negative (lowest) supply"],
        ["NC", "1, 3, 4, 6, 8, 9, 11, 13, 14, 16, 18, 19", "—", "—", "No internal connection"],
        ["V+", "20", "8", "—", "Positive (highest) supply"],
    ]
    text = "Figure 4-1. D, P, PS, PW Package 8-Pin SOIC, PDIP, SO, TSSOP Top View"
    cand = _parse_table_rows(table, 3, text, "LM358")
    assert cand is not None
    pins = {p.number: p.name for p in cand.pin_data.pins}
    assert sorted(pins) == [1, 2, 3, 4, 5, 6, 7, 8]
    assert pins[4] == "V–" and pins[8] == "V+"
    functions = {p.number: p.function for p in cand.pin_data.pins}
    assert functions[4] == "ground" and functions[8] == "power"
    assert cand.pin_data.package.pin_count == 8


def test_package_pin_column_requires_unambiguous_header():
    from src.pdf_extractor.deterministic_table_parser import _package_pin_column
    header = [["NAME", "LCCC(1)", "SOIC, CDIP, PDIP", "I/O"]]
    assert _package_pin_column(header, "DIP") == 2
    assert _package_pin_column(header, "SOIC") == 2
    assert _package_pin_column(header, "LCCC") == 1
    # No family evidence, or a family matching several columns: no column.
    assert _package_pin_column(header, None) is None
    assert _package_pin_column([["NAME", "SOIC", "SOIC (DW)", "I/O"]], "SOIC") is None
    # Single-package tables have no per-package columns to choose between.
    assert _package_pin_column([["PIN NO.", "NAME", "DESCRIPTION"]], "SOIC") is None


def test_through_hole_span_snaps_to_jedec_grid(_dim_extractor):
    # ULN2001A flow-eval find: ST's dimension letter "E" is the shoulder
    # width (8.5), not JEDEC's row spacing. DIP leads insert on the
    # standard 300/600-mil grid regardless of vendor drawing conventions.
    dim_mod, _ = _dim_extractor
    ext = dim_mod.DimensionExtractor()
    flat = {"e": 2.54, "E": 8.5, "D": 20.0}
    out = ext._normalize_through_hole_span("DIP-16", dict(flat))
    assert out["E"] == pytest.approx(7.62)
    out = ext._normalize_through_hole_span("PDIP-40", {"e": 2.54, "E": 14.8})
    assert out["E"] == pytest.approx(15.24)
    # Way off any grid position: drop the span rather than snap blindly.
    out = ext._normalize_through_hole_span("DIP-16", {"e": 2.54, "E": 11.5})
    assert "E" not in out
    # SMD packages are untouched.
    out = ext._normalize_through_hole_span("SOIC-16", {"e": 1.27, "E": 10.3})
    assert out["E"] == 10.3


def test_quad_footprint_rows_centered_per_side():
    # STM32 flow-eval find: LQFP top/bottom rows were each shoved 4.2mm
    # sideways (top all-negative x, bottom all-positive), because joint
    # recentering saw a symmetric union and shifted nothing. Every side's
    # row must be centered on the origin individually.
    b = PcbFootprintBuilder("LQFP-64", 64, "X")
    for side in ("top", "bottom"):
        row = [p.x for p in b.pin_positions if p.side == side]
        assert (max(row) + min(row)) / 2 == pytest.approx(0.0, abs=0.01), side
    for side in ("left", "right"):
        col = [p.y for p in b.pin_positions if p.side == side]
        assert (max(col) + min(col)) / 2 == pytest.approx(0.0, abs=0.01), side

    # Pin ring must sit at the JEDEC lead span (E - L inset), not beyond.
    xs = [p.x for p in b.pin_positions]
    assert max(xs) - min(xs) == pytest.approx(11.5 - 0.6, abs=0.05)


def test_dims_family_consistency_gate(_dim_extractor):
    # STM32 flow-eval find: vision returned TSSOP-shaped dims (e=0.65,
    # E=6.4) for an LQFP-64 target and nothing rejected them. Extracted
    # dims must be consistent with the target family's JEDEC geometry.
    dim_mod, _ = _dim_extractor
    ext = dim_mod.DimensionExtractor()
    tssop_shaped = {"e": 0.65, "E": 6.4, "D": 5.0, "b": 0.245, "L": 0.6}
    assert not ext._consistent_with_family("LQFP-64", tssop_shaped)
    # Correct LQFP-64 dims pass.
    assert ext._consistent_with_family("LQFP-64", {"e": 0.5, "E": 12.0})
    # Both SOIC width variants are legitimate for a SOIC target.
    assert ext._consistent_with_family("SOIC-16", {"e": 1.27, "E": 10.325})
    assert ext._consistent_with_family("SOIC-16", {"e": 1.27, "E": 6.0})
    # No target or unknown family: gate stays open.
    assert ext._consistent_with_family(None, tssop_shaped)
    assert ext._consistent_with_family("LCCC-20", tssop_shaped)


def test_infer_family_uses_page_designator():
    from src.pdf_extractor.deterministic_table_parser import _infer_family
    assert _infer_family("DSC PACKAGE (TOP VIEW) pin functions", 10) == "WSON"
    # Explicit family names still win over designators.
    assert _infer_family("SOIC-16 package pinout", 16) == "SOIC"


def test_package_pin_count_respects_explicit_suffix():
    # INA219 is a SOT23-8: the "-8" is an explicit pin count and must win
    # over the bare SOT-23 family default of 3 (flow eval find).
    from src.llm.client import _parse_pin_count_from_package_type as ppc
    assert ppc("SOT23-8") == 8
    assert ppc("SOT-23-5") == 5
    assert ppc("SOT-23") == 3
    assert ppc("SOT23") == 3
    assert ppc("TO-220") == 3
    assert ppc("SOIC-16") == 16


def test_footprint_defaults_known_families():
    assert get_footprint_defaults("DIP-8", 8)["E"] == 7.62
    assert get_footprint_defaults("PDIP-16", 16)["e"] == 2.54
    assert get_footprint_defaults("SOIC-28", 28)["E"] == 10.3   # wide body
    assert get_footprint_defaults("SSOP-28", 28)["E"] == 7.8
    assert get_footprint_defaults("QFN-32", 32)["e"] == 0.5


def test_footprint_defaults_unknown_family_returns_none():
    assert get_footprint_defaults("LCCC-20", 20) is None


def test_footprint_defaults_are_plausible():
    for pkg, pins in [("DIP-8", 8), ("SOIC-16", 16), ("TSSOP-16", 16),
                      ("SSOP-28", 28), ("QFN-32", 32), ("DFN-8", 8)]:
        dims = get_footprint_defaults(pkg, pins)
        assert dims is not None, pkg
        assert plausible_dims(dims), (pkg, dims)
