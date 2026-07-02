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
    [("WSON-8", 8), ("SOT-23-6", 6), ("WLCSP-8", 8), ("SON-10", 10)],
)
def test_unknown_package_families_generate_valid_footprints(tmp_path, package_type, pin_count):
    output_path = tmp_path / f"{package_type.lower().replace('-', '_')}.glb"
    pins = [{"number": n, "name": f"PIN{n}"} for n in range(1, pin_count + 1)]

    assert build_pcb_footprint(package_type, pin_count, "TEST", pins, str(output_path))

    is_valid, errors = validate_pcb_footprint_glb(str(output_path), pin_count=pin_count, through_hole=False)
    assert is_valid, errors
    assert output_path.stat().st_size > 0


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
        content, api_key="dummy", model="dummy", verbose=False, part_number="TPS62160DSG"
    )

    assert pin_data.package is not None
    assert pin_data.package.pin_count == 8
    assert pin_data.package.type == "WSON"
    assert len(pin_data.pins) == 8
    assert {p.name for p in pin_data.pins} == {"PGND", "VIN", "EN", "AGND", "FB", "VOS", "SW", "PG"}


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
        content, api_key="dummy", model="dummy", verbose=False, part_number="MPU-6000"
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
        content, api_key="dummy", model="dummy",
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
