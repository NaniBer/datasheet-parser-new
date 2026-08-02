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


def test_page_detector_heading_found_below_line_10(detector):
    """Vendor boilerplate (part title, URLs, doc ids) routinely pushes the
    section heading past line 10; the heading check must scan the whole
    page, not only its top."""
    filler = "\n".join(f"boilerplate line {i}" for i in range(15))
    text = filler + "\nPin Configuration and Functions\n1 VCC supply"
    score, _ = detector._check_pinout_heading(text)
    assert score == 3


def test_page_detector_toc_page_scores_no_heading_bonus(detector):
    """A table of contents lists every section heading with dot leaders and
    page numbers; it must not collect the heading bonus meant for the real
    section page."""
    text = (
        "Table of Contents\n"
        "1 Features ................................ 1\n"
        "2 Applications ............................ 1\n"
        "3 Description ............................. 2\n"
        "4 Revision History ........................ 3\n"
        "5 Pin Configuration and Functions ......... 4\n"
        "6 Specifications .......................... 5\n"
    )
    score, _ = detector._check_pinout_heading(text)
    assert score == 0


def test_page_detector_revision_history_page_keeps_heading_bonus(detector):
    """A revision-history page carries dot-leader change entries (which trip
    the TOC detector) but also the real section heading on a plain line; the
    genuine heading must still earn the bonus (regression: SN6505A p3)."""
    text = (
        "SN6505A, SN6505B\n"
        "• Changed Table 9-3 ...................................... 12\n"
        "• Changed the Section 6.7 section........................ 8\n"
        "• Added the Section 6.8 section.......................... 9\n"
        "• Changed Table 9-3 ..................................... 12\n"
        "5 Pin Configuration and Functions\n"
        "Table 5-1. Pin Functions\n"
        "1 VCC Power supply\n"
    )
    score, _ = detector._check_pinout_heading(text)
    assert score == 3


def test_page_detector_early_page_gets_position_bonus(detector):
    """Long datasheets routinely put the pin table on page 3 of 40+; only
    the cover page and the legal/ordering tail are unlikely positions."""
    detector.total_pages = 40
    score, _ = detector._check_page_position(3)
    assert score == 1


def test_page_detector_cover_page_no_position_bonus(detector):
    detector.total_pages = 40
    score, _ = detector._check_page_position(1)
    assert score == 0


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


def test_single_filename_candidate_corroborated_by_text_wins():
    """A single filename token that is also present in the text is strong,
    corroborated evidence and wins even over noisier repeated tokens."""
    text_content = (
        "--- Page 1 ---\n"
        # Uppercase so the uppercase-only token pattern captures it (text_hits > 0)
        "ATMEGA328P\n"
        # Many occurrences of a plausible-but-wrong token (register bit name)
        "ICES1 ICES1 ICES1 ICES1 ICES1 ICES1\n"
        "--- Page 2 ---\n"
        "ICES1 ICES1 ICES1\n"
    )
    # "ATmega328P" → uppercased "ATMEGA328P" — plausible filename token, and it
    # occurs in the text (text_hits > 0), so it is returned.
    result = infer_part_number_hint(text_content, source_name="ATmega328P.pdf")
    assert result == "ATMEGA328P"


def test_filename_token_absent_from_text_does_not_override_strong_identifier():
    """Fix 10: an uncorroborated filename token (present nowhere in the text)
    must NOT override a strong in-document identifier — the in-text one wins."""
    text_content = (
        "--- Page 1 ---\n"
        "LM358 LM358 LM358\n"
        "--- Page 2 ---\n"
        "LM358\n"
    )
    # "ZZ8888" is a plausible single filename candidate but appears nowhere in
    # the text; the strong in-document identifier LM358 must win.
    result = infer_part_number_hint(text_content, source_name="ZZ8888.pdf")
    assert result == "LM358"


def test_hint_is_deterministic_across_source_names():
    """Fix 10 determinism guarantee: identical document text under two
    different (uncorroborated) source names resolves to the SAME part number,
    so byte-identical files renamed differently cannot diverge."""
    text_content = (
        "--- Page 1 ---\n"
        "LM358 LM358 LM358\n"
        "--- Page 2 ---\n"
        "LM358\n"
    )
    a = infer_part_number_hint(text_content, source_name="AA1111.pdf")
    b = infer_part_number_hint(text_content, source_name="BB2222.pdf")
    assert a == b == "LM358"


def test_filename_token_used_when_no_strong_in_document_identifier():
    """Existing conservative behavior preserved: when there is no trustworthy
    in-document identifier, the single filename token still resolves."""
    result = infer_part_number_hint("", source_name="ATmega328P.pdf")
    assert result == "ATMEGA328P"


def test_filename_hint_survives_underscore_separators():
    """Underscores in a stem are separators: the part token after an index
    prefix like `9_` must be found (regex \\b cannot see past `_` otherwise)."""
    result = infer_part_number_hint("", source_name="9_XC9536XL.pdf")
    assert result == "XC9536XL"


def test_filename_hint_returns_whole_token_not_suffix_fragment():
    """A hyphenated orderable like AB12C-E3-80 must never degrade to a
    fragment of itself (`E3-80`) because the leading chars were unreachable."""
    result = infer_part_number_hint("", source_name="4_AB12C-E3-80.pdf")
    assert result == "AB12C-E3-80"


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


def _four_pin_data(names):
    return PinData(
        component_name="AB1234",
        package=PackageInfo(type="DIP", pin_count=4, width=5.0, height=5.0),
        pins=[Pin(number=i, name=name) for i, name in enumerate(names, start=1)],
        extraction_method="LLM",
    )


def test_validate_flags_pin_names_absent_from_source_text():
    """A pin name that appears nowhere in the source text is fabricated
    (hallucinated or garbled OCR) and must fail validation."""
    pin_data = _four_pin_data(["VCC", "QZX_77", "OUT", "GND"])
    source = "Pin Functions\n1 VCC supply\n2 EN enable\n3 OUT output\n4 GND ground"
    result = validate_pin_data_extraction(
        pin_data, part_number="AB1234", source_text=source
    )
    assert not result.is_valid
    assert any("QZX_77" in e for e in result.errors)


def test_validate_accepts_pin_names_grounded_in_source_text():
    """Names present in the source pass, tolerating line wraps and
    punctuation differences (VOUT_SET wrapped as 'VOUT_\\nSET')."""
    pin_data = _four_pin_data(["VCC", "VOUT_SET", "OUT", "GND"])
    source = "Pin Functions\n1 VCC supply\n2 VOUT_\nSET adjust\n3 OUT output\n4 GND ground"
    result = validate_pin_data_extraction(
        pin_data, part_number="AB1234", source_text=source
    )
    assert result.is_valid


def test_validate_accepts_composite_name_with_segments_in_source():
    """Composite names the extractor joins itself (e.g. 'GND/PAD' when the
    sheet lists GND and PAD separately) stay valid when every segment is
    grounded — joining style must not fail a correct extraction."""
    pin_data = _four_pin_data(["VCC", "EN", "OUT", "GND/PAD"])
    source = "Pin Functions\n1 VCC supply\n2 EN enable\n3 OUT output\n4 GND ground\nExposed PAD"
    result = validate_pin_data_extraction(
        pin_data, part_number="AB1234", source_text=source
    )
    assert result.is_valid


def test_validate_grounding_skipped_without_source_text():
    """No source text means grounding cannot run — structural validation
    alone decides, so the fabricated name is not caught here."""
    pin_data = _four_pin_data(["VCC", "QZX_77", "OUT", "GND"])
    result = validate_pin_data_extraction(pin_data, part_number="AB1234")
    assert result.is_valid


def test_validate_grounding_skips_short_symbol_names():
    """One-character names (bridge-rectifier '+', '-', diode 'K') carry too
    little signal to ground; they must not be flagged."""
    pin_data = _four_pin_data(["+", "-", "AC", "K"])
    source = "Terminals\nAC input\npositive and negative outputs"
    result = validate_pin_data_extraction(
        pin_data, part_number="AB1234", source_text=source
    )
    assert result.is_valid


def test_validate_rejects_sibling_device_extraction():
    """Multi-device datasheets (e.g. AB1233/AB1234 on one page) are the top
    wrong-output cause: extracting the sibling's column must be an error so
    the retry loop re-extracts the target device, not a mere warning."""
    pin_data = _four_pin_data(["VCC", "EN", "OUT", "GND"])
    pin_data.component_name = "AB1233"
    result = validate_pin_data_extraction(pin_data, part_number="AB1234")
    assert not result.is_valid
    assert any("AB1233" in e and "AB1234" in e for e in result.errors)


def test_validate_allows_component_name_that_contains_target():
    """Base name vs orderable suffix (AB1234 vs AB1234ZZ) is the same
    device — containment must never be treated as a sibling mismatch.
    (The suffix must not decode as a package designator, which is a
    separate, legitimate check.)"""
    pin_data = _four_pin_data(["VCC", "EN", "OUT", "GND"])
    pin_data.component_name = "AB1234"
    result = validate_pin_data_extraction(pin_data, part_number="AB1234ZZ")
    assert result.is_valid


def test_validate_letter_divergence_is_not_sibling_error():
    """Wildcard family names (STM32F103xB vs STM32F103RBT7) diverge at a
    letter, not inside the numeric device id — warning territory, not an
    extraction error."""
    pin_data = _four_pin_data(["VCC", "EN", "OUT", "GND"])
    pin_data.component_name = "STM32F103XB"
    result = validate_pin_data_extraction(pin_data, part_number="STM32F103RBT7")
    # May carry a mismatch warning, but must not fail as a sibling extraction.
    assert not any("sibling" in e.lower() for e in result.errors)


def _sixteen_pin_data(package_type, component="AB1234"):
    return PinData(
        component_name=component,
        package=PackageInfo(type=package_type, pin_count=16, width=5.0, height=5.0),
        pins=[Pin(number=i, name=f"P{i}") for i in range(1, 17)],
        extraction_method="LLM",
    )


def test_validate_flags_package_family_conflicting_with_designator():
    """The order-code package designator is ground truth (AB1234PWP is a
    PowerPAD TSSOP): an extracted family whose grid differs (QFN, 0.5 mm)
    is a wrong-package read and must fail so the retry can fix it."""
    pin_data = _sixteen_pin_data("QFN")
    result = validate_pin_data_extraction(pin_data, part_number="AB1234PWP")
    assert not result.is_valid
    assert any("TSSOP" in e for e in result.errors)


def test_validate_flags_unknown_package_type_against_known_designator():
    """Garbage package strings ('P-20') paired with a decodable designator
    must fail at validation, not later at geometry build."""
    pin_data = _sixteen_pin_data("P-20")
    result = validate_pin_data_extraction(pin_data, part_number="AB1234PWP")
    assert not result.is_valid
    assert any("TSSOP" in e for e in result.errors)


def test_validate_accepts_package_family_matching_designator():
    pin_data = _sixteen_pin_data("TSSOP")
    result = validate_pin_data_extraction(pin_data, part_number="AB1234PWP")
    assert result.is_valid


def test_validate_single_letter_designators_not_escalated():
    """Single-letter suffixes (D, N, P) are too generic across vendors to
    treat as a package claim."""
    pin_data = _sixteen_pin_data("DIP")
    result = validate_pin_data_extraction(pin_data, part_number="AB1234D")
    assert result.is_valid


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

# Ground truth read visually from the drawings (read from the datasheet drawings).
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
    assert result == {**complete, "dims_source": "text"}


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
    assert result == {**_PARTIAL_TEXT_DIMS, "dims_source": "text"}


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


def test_odd_pin_count_dual_row_places_all_pins():
    """SOT-23-5 style packages put 3 pins on one row and 2 on the other; the
    symmetric n//2 split placed only 4 of 5 pins and the last pin silently
    vanished from the schematic (and broke footprint hierarchy validation)."""
    from src.package_types import get_schematic_parameters
    from src.schematic_generator.pin_layout import layout_pins

    params = get_schematic_parameters("SOT-23", 5)
    positions = layout_pins(params, None)
    assert sorted(int(p.pin_number) for p in positions) == [1, 2, 3, 4, 5]
    assert sum(1 for p in positions if p.side == "left") == 3
    assert sum(1 for p in positions if p.side == "right") == 2


def test_dual_row_family_refuses_quad_custom_layout():
    """A vision misread can hand a four-sided pin layout to a dual-row
    package family; the footprint would look plausible and never fit the
    part. The builder must refuse instead of shipping it."""
    from src.exceptions import SchematicGenerationError

    quad_layout = {
        "left_side": [1, 2, 3, 4],
        "bottom_edge": [5, 6, 7, 8],
        "right_side": [9, 10, 11, 12],
        "top_edge": [13, 14, 15, 16],
    }
    with pytest.raises(SchematicGenerationError):
        PcbFootprintBuilder("TSSOP-16", 16, "X", custom_layout=quad_layout)


def test_dual_row_family_accepts_two_sided_custom_layout():
    """Two opposite sides is the correct topology for a dual-row family;
    a custom layout that matches it must still build."""
    layout = {
        "left_side": [1, 2, 3, 4, 5, 6, 7, 8],
        "right_side": [9, 10, 11, 12, 13, 14, 15, 16],
    }
    b = PcbFootprintBuilder("TSSOP-16", 16, "X", custom_layout=layout)
    assert b.params.pin_pitch == pytest.approx(0.65)


def test_quad_family_accepts_quad_custom_layout():
    """Quad families keep their four-sided layouts untouched."""
    quad_layout = {
        "left_side": [1, 2, 3, 4],
        "bottom_edge": [5, 6, 7, 8],
        "right_side": [9, 10, 11, 12],
        "top_edge": [13, 14, 15, 16],
    }
    b = PcbFootprintBuilder("QFN-16", 16, "X", custom_layout=quad_layout)
    assert b.params.pin_pitch == pytest.approx(0.5)


def test_umax_normalizes_to_msop():
    """Maxim's µMAX is a published MO-187 (MSOP-class) package: it must map
    to the MSOP 0.65 mm grid, never degrade toward SOIC's 1.27 mm."""
    detector = PackageDetector()
    assert detector.normalize_package_name("8-Pin µMAX") == "MSOP"
    assert detector.normalize_package_name("uMAX-8") == "MSOP"
    from src.package_types.footprint_defaults import get_footprint_defaults
    assert get_footprint_defaults("MSOP", 8)["e"] == pytest.approx(0.65)


def test_failed_validation_leaves_no_footprint_file(tmp_path, monkeypatch):
    """A footprint that fails hierarchy validation must not remain on disk
    looking like valid output; downstream tooling globs for *.glb (F8)."""
    import src.schematic_generator.pcb_footprint_builder as fpb

    monkeypatch.setattr(
        fpb, "validate_pcb_footprint_glb", lambda *a, **k: (False, ["forced failure"])
    )
    pins = [{"number": str(i), "name": f"P{i}"} for i in range(1, 9)]
    b = fpb.PcbFootprintBuilder("SOIC-8", 8, "X")
    out = tmp_path / "footprint.glb"
    assert b.save_glb(str(out), pins) is False
    assert not out.exists()
    assert list(tmp_path.iterdir()) == []  # no temp litter either


def test_footprint_glb_records_dims_provenance(tmp_path):
    # Production gate: the platform must be able to tell verified dims
    # (datasheet text) from assumed ones (JEDEC defaults) to decide what
    # to flag for review. Recorded as dimsSource on the Package root.
    from pygltflib import GLTF2

    pins = [{"number": str(i), "name": f"P{i}"} for i in range(1, 9)]

    out_text = tmp_path / "text_dims.glb"
    dims = {"e": 1.27, "E": 6.0, "D": 4.9, "b": 0.41, "L": 0.84,
            "dims_source": "text"}
    assert build_pcb_footprint_direct(
        "SOIC-8", 8, "NE555", pins, str(out_text), extracted_dims=dims)
    g = GLTF2().load(str(out_text))
    root = g.nodes[g.scenes[g.scene or 0].nodes[0]]
    assert root.extras["dimsSource"] == "text"

    out_default = tmp_path / "default_dims.glb"
    assert build_pcb_footprint_direct(
        "SOIC-8", 8, "NE555", pins, str(out_default))
    g = GLTF2().load(str(out_default))
    root = g.nodes[g.scenes[g.scene or 0].nodes[0]]
    assert root.extras["dimsSource"] == "jedec_default"


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


def test_shared_datasheet_selects_device_column_by_part_number():
    # MCP3204/3208 ground-truth find: one pin-number column per DEVICE
    # (not per package family). Reading the first numeric cell took the
    # 14-pin MCP3204 numbering for a 16-pin MCP3208 order code.
    from src.pdf_extractor.deterministic_table_parser import _parse_table_rows
    table = [
        ["MCP3204", "MCP3208", "Symbol", "Definition"],
        ["PDIP, SOIC, TSSOP", "PDIP, SOIC", "", ""],
        ["1", "1", "CH0", "Analog Input"],
        ["2", "2", "CH1", "Analog Input"],
        ["3", "3", "CH2", "Analog Input"],
        ["4", "4", "CH3", "Analog Input"],
        ["—", "5", "CH4", "Analog Input"],
        ["—", "6", "CH5", "Analog Input"],
        ["—", "7", "CH6", "Analog Input"],
        ["—", "8", "CH7", "Analog Input"],
        ["7", "9", "DGND", "Digital Ground"],
        ["8", "10", "CS/SHDN", "Chip Select/Shutdown Input"],
        ["9", "11", "DIN", "Serial Data In"],
        ["10", "12", "DOUT", "Serial Data Out"],
        ["11", "13", "CLK", "Serial Clock"],
        ["12", "14", "AGND", "Analog Ground"],
        ["13", "15", "VREF", "Reference Voltage Input"],
        ["14", "16", "VDD", "+2.7V to 5.5V Power Supply"],
        ["5, 6", "—", "NC", "No Connection"],
    ]
    text = "MCP3204/3208 PDIP, SOIC available"
    c8 = _parse_table_rows(table, 15, text, "MCP3208-CI/P")
    assert c8 is not None and len(c8.pin_data.pins) == 16
    assert {p.number: p.name for p in c8.pin_data.pins}[8] == "CH7"
    c4 = _parse_table_rows(table, 15, text, "MCP3204-CI/P")
    assert c4 is not None and len(c4.pin_data.pins) == 14
    # MCP3204: pins 5,6 are NC; CH-channels stop at CH3.
    assert {p.number: p.name for p in c4.pin_data.pins}[5] == "NC"


def test_cli_exit_code_contract(monkeypatch, tmp_path):
    # Exit-code contract under the fail-open default:
    #   0 = validated artifacts, 3 = best-effort artifacts produced,
    #   1 = domain failure (no artifacts), 2 = internal error (bug).
    # Automation and the future service wrapper depend on these being
    # distinguishable.
    import src.main as main_mod

    # Domain failure: nonexistent input file -> 1 (nothing to build from).
    monkeypatch.setattr("sys.argv", ["prog", str(tmp_path / "missing.pdf"), "out.glb"])
    with pytest.raises(SystemExit) as exc:
        main_mod.main()
    assert exc.value.code == main_mod.EXIT_DOMAIN_FAILURE

    # Fail-open: a datasheet whose pins fail a validation gate (foo.pdf is a
    # diode whose 'Anode'/'Cathode' names aren't groundable in the text) still
    # emits a watermarked best-effort GLB -> 3, instead of refusing.
    monkeypatch.setattr("sys.argv", ["prog", "pdfs/foo.pdf", str(tmp_path / "foo.glb")])
    with pytest.raises(SystemExit) as exc:
        main_mod.main()
    assert exc.value.code == main_mod.EXIT_DEGRADED

    # --strict restores fail-closed: the same validation failure -> domain
    # failure (1), no artifacts.
    monkeypatch.setattr("sys.argv", ["prog", "pdfs/foo.pdf", str(tmp_path / "foo_strict.glb"), "--strict"])
    with pytest.raises(SystemExit) as exc:
        main_mod.main()
    assert exc.value.code == main_mod.EXIT_DOMAIN_FAILURE

    # Internal error: a bug in a pipeline stage -> 2 (not silently 1)
    def _boom(*a, **k):
        raise TypeError("simulated bug")
    monkeypatch.setattr(main_mod, "detect_relevant_pages", _boom)
    monkeypatch.setattr("sys.argv", ["prog", "pdfs/foo.pdf", str(tmp_path / "x.glb")])
    with pytest.raises(SystemExit) as exc:
        main_mod.main()
    assert exc.value.code == main_mod.EXIT_INTERNAL_ERROR


def test_exit_degraded_on_unvalidated_output():
    # Fix 5: output produced from unvalidated data (--force-best-effort) exits
    # 3, not 0, so callers can tell a best-effort result from a trusted one.
    import src.main as main_mod
    from src.models.pin_data import PinData

    degraded = PinData(component_name="X",
                       validation_errors=["Unknown package type 'DDA-8'; substituted DIP-8"])
    with pytest.raises(SystemExit) as exc:
        main_mod._exit_if_degraded(degraded)
    assert exc.value.code == main_mod.EXIT_DEGRADED

    # Clean output (no validation errors) does not exit — stays on the 0 path.
    main_mod._exit_if_degraded(PinData(component_name="X"))
    main_mod._exit_if_degraded(None)


@pytest.mark.integration
def test_cli_exit_zero_on_success(tmp_path):
    # Deterministic-path part (DFN.pdf needs no LLM): full run -> exit 0.
    import subprocess, sys
    proc = subprocess.run(
        [sys.executable, "-m", "src.main", "pdfs/DFN.pdf",
         str(tmp_path / "dfn.glb"), "--both"],
        capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, proc.stdout[-500:] + proc.stderr[-500:]
    assert (tmp_path / "dfn_schematic.glb").exists()
    assert (tmp_path / "dfn_footprint.glb").exists()


def test_stm32_order_code_pin_count_decoding():
    # RBT7 eval-v5 find: STM32F103RBT7 (a 64-pin part) shipped a 100-pin
    # footprint because the LLM read the LQFP100 column and nothing knew
    # better. ST order codes encode the pin count deterministically.
    from src.pdf_extractor.variant_selection import expected_pin_count_from_part_number as epc
    assert epc("STM32F103RBT7") == 64
    assert epc("STM32F103C6") == 48
    assert epc("STM32F103VET6") == 100
    assert epc("stm32f103zet6") == 144
    # Wildcard family names and non-ST parts decode to None — never guess.
    assert epc("STM32F103X6") is None
    assert epc("SN74HC595DWR") is None
    assert epc(None) is None


def test_variant_selection_prefers_order_code_pin_count():
    # The decoded pin count outranks the LLM's own variant choice.
    from src.pdf_extractor.variant_selection import select_package_variant
    pd = PinData(
        component_name="STM32F103RBT7",
        package=None,
        pins=[],
        packages=[
            {"type": "LQFP-100", "pin_count": 100, "pins": []},
            {"type": "LQFP-64", "pin_count": 64, "pins": []},
        ],
        selected_package_index=0,  # LLM picked the wrong one
    )
    sel = select_package_variant(pd, part_number="STM32F103RBT7")
    assert sel.package["pin_count"] == 64
    assert "implies 64 pins" in sel.reason


def test_validator_rejects_wrong_variant_pin_count():
    # If the order code implies 64 pins and no extracted variant has 64,
    # the extraction read the wrong column(s): hard error -> feedback retry.
    from src.pdf_extractor.extraction_validator import validate_pin_data_extraction
    pins100 = [{"number": n, "name": f"P{n}"} for n in range(1, 101)]
    pd = PinData(
        component_name="STM32F103RBT7",
        package=None,
        pins=[],
        packages=[{"type": "LQFP-100", "pin_count": 100, "pins": pins100}],
        selected_package_index=0,
    )
    result = validate_pin_data_extraction(pd, part_number="STM32F103RBT7")
    assert not result.is_valid
    assert any("implies a 64-pin" in e for e in result.errors)

    pins64 = [{"number": n, "name": f"P{n}"} for n in range(1, 65)]
    pd_ok = PinData(
        component_name="STM32F103RBT7",
        package=None,
        pins=[],
        packages=[{"type": "LQFP-64", "pin_count": 64, "pins": pins64}],
        selected_package_index=0,
    )
    assert validate_pin_data_extraction(pd_ok, part_number="STM32F103RBT7").is_valid


def test_unresolvable_multi_package_table_yields_no_candidate():
    # STM32F103X6 eval-v4 regression: its pin table has one number column
    # per package (BGA100 | LQFP48 | LQFP64 | LQFP100) and the part number
    # names none of them. Falling back to "first numeric cell per row"
    # mixed numbering schemes into a garbage BGA-25 candidate. The parser
    # must yield nothing and let the validated LLM path handle it.
    from src.pdf_extractor.deterministic_table_parser import _parse_table_rows
    table = [
        ["Pins", "", "", "", "Pin name", "Type", "Main function"],
        ["BGA100", "LQFP48", "LQFP64", "LQFP100", "", "", ""],
        ["A3", "-", "-", "1", "PE2/TRACECK", "I/O", "PE2"],
        ["B3", "-", "-", "2", "PE3/TRACED0", "I/O", "PE3"],
        ["B2", "1", "1", "6", "VBAT", "S", "VBAT"],
        ["A2", "2", "2", "7", "PC13", "I/O", "PC13"],
        ["A1", "3", "3", "8", "PC14", "I/O", "PC14"],
        ["B1", "4", "4", "9", "PC15", "I/O", "PC15"],
        ["C2", "-", "-", "10", "VSS_5", "S", "VSS_5"],
        ["D2", "-", "-", "11", "VDD_5", "S", "VDD_5"],
    ]
    text = "STM32F103xx pin definitions LQFP48 LQFP64 LQFP100 TFBGA64 packages"
    assert _parse_table_rows(table, 18, text, "STM32F103X6") is None

    # The guard must not disturb resolvable multi-package tables:
    # lm358 (family column) and MCP3208 (device column) still parse.
    from src.pdf_extractor.deterministic_table_parser import _has_multiple_package_columns
    assert _has_multiple_package_columns(table)
    assert not _has_multiple_package_columns(
        [["PIN NO.", "NAME", "I/O", "DESCRIPTION"], ["1", "OUT1", "O", "Output"]]
    )


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


def test_through_hole_drill_follows_lead_width():
    # IPC-2222: hole = lead diagonal + 0.25 clearance, floored at the
    # standard 0.83mm drill. A fixed drill under-sizes holes for parts
    # with heavy leads (power DIPs at b~1.0).
    thin = PcbFootprintBuilder("DIP-16", 16, "X",
                               extracted_dims={"e": 2.54, "b": 0.46})
    assert thin.pad_spec["drill"] == pytest.approx(0.83)

    heavy = PcbFootprintBuilder("DIP-16", 16, "X",
                                extracted_dims={"e": 2.54, "b": 0.9, "b_max": 1.04})
    expected = round((1.04 ** 2 + 0.25 ** 2) ** 0.5 + 0.25, 2)
    assert heavy.pad_spec["drill"] == pytest.approx(expected)
    assert heavy.pad_spec["diameter"] == pytest.approx(expected + 0.7)


def test_pads_sized_from_tolerance_extremes(_dim_extractor):
    # IPC-7351 sizes pads from b_max (widest lead) and L_max (longest
    # foot); midpoints leave pads marginally undersized for parts at the
    # tolerance limits. _flatten preserves the extremes for b and L.
    dim_mod, _ = _dim_extractor
    ext = dim_mod.DimensionExtractor()
    raw = {"package_type": "SOIC-8", "unit": "mm", "dimensions": {
        "e": "1.27", "E": "6.0", "D": "4.9",
        "b": {"min": "0.31", "max": "0.51"},
        "L": {"min": "0.40", "max": "1.27"},
    }}
    flat = ext._flatten(raw)
    assert flat["b"] == pytest.approx(0.41)
    assert flat["b_max"] == pytest.approx(0.51)
    assert flat["L_max"] == pytest.approx(1.27)

    b = PcbFootprintBuilder("SOIC-8", 8, "X", extracted_dims=flat)
    assert b.pad_spec["shape"] == "rect"
    # width from b_max + side margin (clamped by pitch), length from L_max
    assert b.pad_spec["width"] == pytest.approx(0.51 + 0.06, abs=0.01)
    assert b.pad_spec["length"] == pytest.approx(1.27 + 0.70, abs=0.01)


def test_impossible_lead_span_dropped(_dim_extractor):
    # TL072 ground-truth find: text+vision merge produced a narrow SO-8
    # body (E1=3.9) with a wide-body span (E=10.325) from another page's
    # drawing — 3.2mm of lead per side is physically impossible. The span
    # is dropped; the good keys survive and JEDEC defaults fill E.
    dim_mod, _ = _dim_extractor
    ext = dim_mod.DimensionExtractor()
    flat = {"e": 1.27, "E": 10.325, "E1": 3.895, "D": 4.9, "b": 0.41, "L": 0.835}
    out = ext._reconcile_spans(dict(flat))
    assert "E" not in out and out["E1"] == 3.895
    # A plausible pairing is untouched (wide SOIC-16: E=10.3, E1=7.5).
    out = ext._reconcile_spans({"E": 10.3, "E1": 7.5})
    assert out["E"] == 10.3


def test_wide_soic_span_needs_14_pins(_dim_extractor):
    # JEDEC MS-013 wide-body SOIC starts at 14 leads: a 10.3mm span on an
    # 8-pin SOIC target can only be a misread. Same span on 16 pins is fine.
    dim_mod, _ = _dim_extractor
    ext = dim_mod.DimensionExtractor()
    assert not ext._consistent_with_family("SOIC-8", {"e": 1.27, "E": 10.3})
    assert ext._consistent_with_family("SOIC-16", {"e": 1.27, "E": 10.3})
    assert ext._consistent_with_family("SOIC-8", {"e": 1.27, "E": 6.0})


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


# Fix 2: QSOP / HVSSOP / VSSOP get their own real pad grids instead of being
# refused or approximated onto SOIC's 1.27mm or SSOP's 0.65mm pitch.
def test_footprint_defaults_qsop_hvssop_grids():
    assert get_footprint_defaults("QSOP-16", 16)["e"] == 0.635
    assert get_footprint_defaults("HVSSOP-10", 10)["e"] == 0.5
    assert get_footprint_defaults("VSSOP-10", 10)["e"] == 0.5
    # QSOP body length comes from the JEDEC table, not a SOIC fallback.
    assert get_footprint_defaults("QSOP-16", 16)["E1"] == 3.9


def test_parse_package_type_qsop_hvssop_not_unknown():
    from src.package_types.package_geometry import parse_package_type
    # Previously raised PACKAGE_UNKNOWN and got refused / force-substituted.
    assert parse_package_type("QSOP-16") is not None
    assert parse_package_type("HVSSOP-10") is not None
    assert parse_package_type("VSSOP-10") is not None


def test_footprint_defaults_are_plausible():
    for pkg, pins in [("DIP-8", 8), ("SOIC-16", 16), ("TSSOP-16", 16),
                      ("SSOP-28", 28), ("QFN-32", 32), ("DFN-8", 8)]:
        dims = get_footprint_defaults(pkg, pins)
        assert dims is not None, pkg
        assert plausible_dims(dims), (pkg, dims)


# ---------------------------------------------------------------------------
# Fix 1: ground the ordered variant in the datasheet's own ordering table.
# The order-code -> package mapping is read from the document, not memorized,
# so these tests assert the *mechanism* (right row -> right package/pins),
# never a hardcoded per-part answer.
# ---------------------------------------------------------------------------
from src.pdf_extractor.ordering_table import find_ordering_match


def test_ordering_table_ti_addendum_row():
    # TI "PACKAGE OPTION ADDENDUM" row: PN, status, package, drawing code, pins.
    text = (
        "PACKAGE OPTION ADDENDUM\n"
        "Orderable Device   Status   Package Type   Package Drawing   Pins\n"
        "UCC24610DRBT       ACTIVE   SON            DRB               8\n"
        "UCC24610D          ACTIVE   SOIC           D                 8\n"
    )
    m = find_ordering_match(text, "UCC24610DRBT")
    assert m is not None
    assert m.exact is True
    assert m.package == "SON"
    # The sibling SOIC row must not win.
    assert "SON" in m.reason


def test_ordering_table_lead_count_form():
    # Microchip-style "44-Lead PLCC" row, separators differ from the filename.
    text = (
        "Ordering Information\n"
        "PIC16F871-I/L    Industrial   44-Lead PLCC\n"
    )
    m = find_ordering_match(text, "PIC16F871-I-L")
    assert m is not None
    assert m.package == "PLCC"
    assert m.pin_count == 44


def test_ordering_table_numbered_package_form():
    text = "ORDERING GUIDE\nAD536AKH   0C to 70C   TO-100 (10)\n"
    m = find_ordering_match(text, "AD536AKH")
    assert m is not None
    assert m.package.startswith("TO")
    assert m.pin_count == 10


def test_ordering_table_no_match_is_none():
    # No ordering section / no matching row -> None (caller keeps prior path).
    assert find_ordering_match("Just a pinout page with SOIC pins", "SN6501QDBVR") is None
    assert find_ordering_match("", "SN6501QDBVR") is None
    assert find_ordering_match("ORDERING INFORMATION\nSOIC 8\n", None) is None


def test_ordering_table_pin_count_grounds_variant_selection():
    # Ordering-table pin count outranks the LLM's wrong variant choice.
    pd = PinData(
        component_name="TPS23751",
        packages=[
            {"type": "TSSOP-20", "pin_count": 20, "pins": []},
            {"type": "HTSSOP-16", "pin_count": 16, "pins": []},
        ],
        selected_package_index=0,  # LLM picked the 20-pin column
        ordered_pin_count=16,      # read from the ordering table
    )
    sel = select_package_variant(pd, part_number="TPS23751PWP")
    assert sel.package["pin_count"] == 16
    assert "ordering table" in sel.reason


def test_ordering_table_family_grounds_variant_selection():
    # Package family alone disambiguates shape-different variants (no pins).
    pd = PinData(
        component_name="UCC24610",
        packages=[
            {"type": "SOIC-8", "pin_count": 8, "pins": []},
            {"type": "SON-8", "pin_count": 8, "pins": []},
        ],
        selected_package_index=0,       # LLM picked SOIC
        ordered_package_type="SON",     # ordering table says SON (DRB)
    )
    sel = select_package_variant(pd, part_number="UCC24610DRBT")
    assert sel.package["type"] == "SON-8"
    assert "SON" in sel.reason


def test_ordering_grounding_is_additive_when_absent():
    # With no ordering info, selection falls back to the LLM's choice.
    pd = PinData(
        component_name="X",
        packages=[
            {"type": "SOIC-8", "pin_count": 8, "pins": []},
            {"type": "SON-8", "pin_count": 8, "pins": []},
        ],
        selected_package_index=1,
    )
    sel = select_package_variant(pd, part_number="Xyz")
    assert sel.package["type"] == "SON-8"


# Fix 1 (fallback): when the deterministic parser can't read a vendor's
# ordering-table layout, the LLM reads it -- but its answer is trusted only
# after grounding against the document text.
from src.pdf_extractor.ordering_table import find_ordering_match_llm

# A layout the deterministic parser does not handle (multi-line, no TI cell).
_ST_ORDERING = (
    "ORDERING INFORMATION\n"
    "Order codes and package options for the L293DD family:\n"
    "L293DD  Powerdip  Tube\n"
    "L293DD  SOIC  20  Tape and reel\n"
)


def test_ordering_deterministic_handles_inline_row():
    # When a row carries the part number and package on one line, the
    # deterministic parser resolves it directly (no LLM fallback needed).
    from src.pdf_extractor.ordering_table import find_ordering_match
    m = find_ordering_match(_ST_ORDERING, "L293DD")
    assert m is not None and m.package == "SOIC"


def test_ordering_llm_fallback_grounded(monkeypatch):
    reply = '{"found": true, "package": "SOIC", "pin_count": 20}'
    monkeypatch.setattr("src.chat_bot.get_completion_from_messages",
                        lambda *a, **k: reply)
    m = find_ordering_match_llm(_ST_ORDERING, "L293DD")
    assert m is not None
    assert m.package == "SOIC"
    assert m.pin_count == 20


def test_ordering_llm_rejects_ungrounded_package(monkeypatch):
    # The model names a package that is NOT in the document -> reject it.
    reply = '{"found": true, "package": "QFN", "pin_count": 32}'
    monkeypatch.setattr("src.chat_bot.get_completion_from_messages",
                        lambda *a, **k: reply)
    assert find_ordering_match_llm(_ST_ORDERING, "L293DD") is None


def test_ordering_llm_not_found_returns_none(monkeypatch):
    reply = '{"found": false, "package": "", "pin_count": null}'
    monkeypatch.setattr("src.chat_bot.get_completion_from_messages",
                        lambda *a, **k: reply)
    assert find_ordering_match_llm(_ST_ORDERING, "L293DD") is None


def test_ordering_llm_api_failure_returns_none(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no API key")
    monkeypatch.setattr("src.chat_bot.get_completion_from_messages", boom)
    assert find_ordering_match_llm(_ST_ORDERING, "L293DD") is None


# Fix 6: pin-number cells that use enclosed/decorated numerals must parse,
# not crash. XC6218P332HR-G numbers its pins with circled digits and hit an
# unhandled ValueError: int('①②').
def test_extract_pin_numbers_circled_digits_no_crash():
    from src.pdf_extractor.deterministic_table_parser import _extract_pin_numbers
    # Circled digits: each character is a whole pin number.
    assert _extract_pin_numbers("①②③") == [1, 2, 3]
    assert _extract_pin_numbers("⑩") == [10]          # single char = 10
    assert _extract_pin_numbers("① ② ③") == [1, 2, 3]


def test_extract_pin_numbers_plain_and_fullwidth():
    from src.pdf_extractor.deterministic_table_parser import _extract_pin_numbers
    assert _extract_pin_numbers("1, 2, 3") == [1, 2, 3]
    assert _extract_pin_numbers("1-4") == [1, 2, 3, 4]
    assert _extract_pin_numbers("１２") == [12]        # full-width decimal


def test_extract_pin_numbers_rejects_non_pin_tokens():
    from src.pdf_extractor.deterministic_table_parser import _extract_pin_numbers
    assert _extract_pin_numbers("GND") == []
    assert _extract_pin_numbers("3.3") == []           # not a pin number
    assert _extract_pin_numbers("") == []


# Fix 3: grounded pins win over the LLM's package claim. The self-consistency
# feedback must NOT coerce the model into inventing pins to match a wrong
# package label, and an unreconcilable conflict must fail closed.
def test_validate_pin_data_does_not_coerce_pin_invention():
    from src.llm.client import LLMClient
    from src.models.pin_data import PinData, PackageInfo, Pin

    # Claims SOIC-16 (implies 16 pins) but only 12 pins were extracted.
    pd = PinData(
        component_name="X",
        package=PackageInfo(type="SOIC-16", pin_count=16, width=1.0, height=1.0),
        pins=[Pin(number=i, name=f"P{i}") for i in range(1, 13)],
    )
    msg = LLMClient(model="m")._validate_pin_data(pd)
    assert msg is not None
    low = msg.lower()
    # Must NOT tell the model to pad up to the claimed count...
    assert "ensure all 16 pins are present" not in low
    assert "do not invent" in low
    # ...and must steer it to fix the package instead.
    assert "correct the package" in low


def test_client_fails_closed_on_package_pin_conflict(monkeypatch):
    from src.llm import client as client_mod
    from src.llm.client import LLMClient
    from src.models.pin_data import PinData, PackageInfo, Pin
    from src.exceptions import LLMExtractionError

    conflicting = PinData(
        component_name="X",
        package=PackageInfo(type="SOIC-16", pin_count=16, width=1.0, height=1.0),
        pins=[Pin(number=i, name=f"P{i}") for i in range(1, 13)],  # only 12
    )
    monkeypatch.setattr(client_mod, "get_completion_from_messages", lambda *a, **k: "{}")
    client = LLMClient(model="m")
    monkeypatch.setattr(client, "_parse_llm_response", lambda resp: conflicting)

    # Every attempt sees the same conflict -> fail closed, never return padded data.
    with pytest.raises(LLMExtractionError):
        client.extract_pin_data(content="formatted", part_number="X",
                                max_retries=2, retry_delay=0)


# Task #13: the ordering-table grounded pin count fails closed when it matches
# no extracted variant (the LLM read the wrong single variant), and now applies
# in both single-output and --both paths.
def test_ordered_count_conflict_fails_closed():
    from src.main import _enforce_ordered_pin_count
    from src.models.pin_data import PinData, PackageInfo, Pin
    from src.exceptions import ValidationError
    pd = PinData(
        component_name="X",
        package=PackageInfo(type="SOIC-8", pin_count=8, width=1.0, height=1.0),
        pins=[Pin(number=i, name=f"P{i}") for i in range(1, 9)],
        ordered_pin_count=5,  # ordering table says this order code is 5-pin
    )
    with pytest.raises(ValidationError):
        _enforce_ordered_pin_count(pd, "PART-5PIN", force_best_effort=False)


def test_ordered_count_multivariant_no_match_fails_closed():
    from src.main import _enforce_ordered_pin_count
    from src.models.pin_data import PinData
    from src.exceptions import ValidationError
    pd = PinData(
        component_name="X",
        packages=[{"type": "SOIC-8", "pin_count": 8, "pins": []},
                  {"type": "SOIC-14", "pin_count": 14, "pins": []}],
        ordered_pin_count=20,  # no extracted variant has 20 pins
    )
    with pytest.raises(ValidationError):
        _enforce_ordered_pin_count(pd, "PART", force_best_effort=False)


def test_ordered_count_match_passes():
    from src.main import _enforce_ordered_pin_count
    from src.models.pin_data import PinData
    # A variant matches the grounded count -> OK.
    pd = PinData(
        component_name="X",
        packages=[{"type": "SOIC-8", "pin_count": 8, "pins": []},
                  {"type": "QFN-20", "pin_count": 20, "pins": []}],
        ordered_pin_count=20,
    )
    _enforce_ordered_pin_count(pd, "PART", force_best_effort=False)  # no raise


# The LLM sometimes pads a correctly-read pin table with fabricated NC
# (no-connect) pins to reach a larger, invented package size — e.g. it reads
# TPS51100's clean 10-pin HVSSOP table, then appends NC pins 11-20 and calls it
# a "QFN-20". "NC" trivially appears in the datasheet text, so the grounding
# gate misses it. When the ordering table grounds an authoritative smaller count
# and the *excess* pins are all NC, reconcile by trimming that fabricated
# padding to match ground truth (regression: TPS51100DGQ).
def test_ordered_count_trims_fabricated_nc_padding():
    from src.main import _enforce_ordered_pin_count
    from src.models.pin_data import PinData
    real_names = ["VDDQSNS", "VLDOIN", "VTT", "PGND", "VTTSNS",
                  "VTTREF", "S3", "GND", "S5", "VIN"]
    real = [{"number": i, "name": n, "function": None}
            for i, n in enumerate(real_names, start=1)]
    nc = [{"number": i, "name": "NC", "function": "none"} for i in range(11, 21)]
    pd = PinData(
        component_name="TPS51100",
        packages=[{"type": "QFN-20", "pin_count": 20, "pins": real + nc}],
        ordered_pin_count=10,  # ordering table: HVSSOP, 10 pins
    )
    # Must reconcile silently, not raise, and not fail closed.
    _enforce_ordered_pin_count(pd, "TPS51100DGQ", force_best_effort=False)
    pkg = pd.packages[0]
    assert pkg["pin_count"] == 10
    assert len(pkg["pins"]) == 10
    assert all(p["name"] != "NC" for p in pkg["pins"])  # only the padding went
    assert pkg["type"] == "QFN-10"  # suffix follows the corrected count


def test_ordered_count_does_not_trim_real_pin_excess():
    # Excess pins that are NOT no-connects are real disagreement, not padding:
    # never silently trim them — fail closed so the wrong variant is caught.
    from src.main import _enforce_ordered_pin_count
    from src.models.pin_data import PinData
    from src.exceptions import ValidationError
    pins = [{"number": i, "name": f"IO{i}", "function": None} for i in range(1, 13)]
    pd = PinData(
        component_name="X",
        packages=[{"type": "SOIC-12", "pin_count": 12, "pins": pins}],
        ordered_pin_count=10,
    )
    with pytest.raises(ValidationError):
        _enforce_ordered_pin_count(pd, "PART", force_best_effort=False)


def test_ordered_count_absent_is_additive_noop():
    from src.main import _enforce_ordered_pin_count
    from src.models.pin_data import PinData, PackageInfo, Pin
    pd = PinData(
        component_name="X",
        package=PackageInfo(type="SOIC-8", pin_count=8, width=1.0, height=1.0),
        pins=[Pin(number=i, name=f"P{i}") for i in range(1, 9)],
    )  # no ordered_pin_count
    _enforce_ordered_pin_count(pd, "PART", force_best_effort=False)  # no raise


def test_ordered_count_force_best_effort_records_instead_of_refusing():
    from src.main import _enforce_ordered_pin_count
    from src.models.pin_data import PinData, PackageInfo, Pin
    pd = PinData(
        component_name="X",
        package=PackageInfo(type="SOIC-16", pin_count=16, width=1.0, height=1.0),
        pins=[Pin(number=i, name=f"P{i}") for i in range(1, 17)],
        ordered_pin_count=12,
    )
    _enforce_ordered_pin_count(pd, "PART", force_best_effort=True)  # no raise
    assert pd.validation_errors
    assert any("wrong variant" in e.lower() for e in pd.validation_errors)


# Fix 1 coverage (#14/#15): ordering fallback fires for single-variant, and a
# grounded package FAMILY mismatch fails closed — but only for recognized
# families, so raw LLM strings ("SO20") can't force a false refusal.
def test_ordering_fallback_fires_for_single_variant(monkeypatch):
    import src.main as main_mod
    from src.pdf_extractor import ordering_table as ot
    from src.pdf_extractor.ordering_table import OrderingMatch
    from src.models.pin_data import PinData, PackageInfo, Pin
    from pathlib import Path

    monkeypatch.setattr(ot, "full_pdf_text", lambda p: "text")
    monkeypatch.setattr(ot, "find_ordering_match", lambda t, pn: None)  # deterministic miss
    fired = {}
    def fake_llm(t, pn, model="m", verbose=False):
        fired["yes"] = True
        return OrderingMatch(orderable=pn, package="SOIC", pin_count=8, exact=True, reason="llm")
    monkeypatch.setattr(ot, "find_ordering_match_llm", fake_llm)

    pd = PinData(component_name="X",
                 package=PackageInfo(type="SOIC-8", pin_count=8, width=1.0, height=1.0),
                 pins=[Pin(number=i, name=f"P{i}") for i in range(1, 9)])  # single variant
    main_mod.apply_ordering_ground_truth(pd, Path("x.pdf"), "PART", "m")
    assert fired.get("yes"), "LLM fallback must fire for single-variant now"
    assert pd.ordered_pin_count == 8


def test_ordered_family_mismatch_fails_closed():
    from src.main import _enforce_ordered_package_family
    from src.models.pin_data import PinData, PackageInfo, Pin
    from src.exceptions import ValidationError
    # Ordering says SON (leadless -> QFN family); extraction is SOIC-8.
    pd = PinData(component_name="X",
                 package=PackageInfo(type="SOIC-8", pin_count=8, width=1.0, height=1.0),
                 pins=[Pin(number=i, name=f"P{i}") for i in range(1, 9)],
                 ordered_package_type="SON")
    with pytest.raises(ValidationError):
        _enforce_ordered_package_family(pd, "UCC24610DRBT", force_best_effort=False)


def test_ordered_family_match_passes():
    from src.main import _enforce_ordered_package_family
    from src.models.pin_data import PinData, PackageInfo, Pin
    pd = PinData(component_name="X",
                 package=PackageInfo(type="SOIC-8", pin_count=8, width=1.0, height=1.0),
                 pins=[Pin(number=i, name=f"P{i}") for i in range(1, 9)],
                 ordered_package_type="SOIC")
    _enforce_ordered_package_family(pd, "PART", force_best_effort=False)  # no raise


def test_ordered_family_unrecognized_string_does_not_refuse():
    from src.main import _enforce_ordered_package_family
    from src.models.pin_data import PinData, PackageInfo, Pin
    # Raw LLM fallback string that package_family can't classify must be ignored.
    pd = PinData(component_name="X",
                 package=PackageInfo(type="SOIC-8", pin_count=8, width=1.0, height=1.0),
                 pins=[Pin(number=i, name=f"P{i}") for i in range(1, 9)],
                 ordered_package_type="SO20")
    _enforce_ordered_package_family(pd, "L293DD", force_best_effort=False)  # no raise


# ===========================================================================
# Fix 5 (completion): auto-degraded signal — lossy/unverified footprint output
# watermarks the GLB (validated=false) and exits 3 WITHOUT --force-best-effort,
# while cleanly-grounded output stays exit 0.
# ===========================================================================
def test_lossy_approximation_reason_flags_lossy_and_clears_clean():
    from src.package_types.package_geometry import lossy_approximation_reason
    # Families approximated with a nearest supported grid -> a reason.
    for lossy in ("SSOP-16", "MSOP-10", "SOP-8", "TSOP-48"):
        assert lossy_approximation_reason(lossy), f"{lossy} should be lossy"
    # Families with dedicated geometry -> no reason (must not over-flag).
    for clean in ("SOIC-8", "DIP-8", "TSSOP-8", "QFN-32", "LQFP64"):
        assert lossy_approximation_reason(clean) is None, f"{clean} not lossy"


def test_builder_records_degraded_for_lossy_package():
    from src.schematic_generator.pcb_footprint_builder import PcbFootprintBuilder
    b = PcbFootprintBuilder("SSOP-16", 16, "X")
    assert b.degraded_reasons
    assert any("approximated" in r.lower() for r in b.degraded_reasons)


def test_builder_no_degraded_for_grounded_jedec_default():
    # jedec_default is the normal fallback, NOT degraded (keeps the signal useful).
    from src.schematic_generator.pcb_footprint_builder import PcbFootprintBuilder
    b = PcbFootprintBuilder("DIP-8", 8, "X")
    assert b.dims_source == "jedec_default"
    assert b.degraded_reasons == []


def test_builder_records_degraded_for_unverified_dims(monkeypatch):
    # No jedec defaults and no extracted dims -> display-proportion geometry.
    import src.schematic_generator.pcb_footprint_builder as bmod
    monkeypatch.setattr(bmod, "get_footprint_defaults", lambda *a, **k: None)
    b = bmod.PcbFootprintBuilder("DIP-8", 8, "X")
    assert b.dims_source == "unverified"
    assert any("unverified" in r.lower() for r in b.degraded_reasons)


def test_build_pcb_footprint_populates_degraded_out(tmp_path):
    # End-to-end propagation: the out-list is filled for a lossy part.
    from src.schematic_generator import build_pcb_footprint
    pins = [{"number": i, "name": f"P{i}"} for i in range(1, 17)]
    degraded = []
    ok = build_pcb_footprint("SSOP-16", 16, "X", pins,
                             str(tmp_path / "ssop.glb"), degraded_out=degraded)
    assert ok
    assert degraded and any("approximated" in r.lower() for r in degraded)


def test_record_degraded_merges_and_dedupes():
    from src.main import _record_degraded
    from src.models.pin_data import PinData, PackageInfo, Pin
    pd = PinData(component_name="X",
                 package=PackageInfo(type="SSOP-16", pin_count=16, width=1.0, height=1.0),
                 pins=[Pin(number=i, name=f"P{i}") for i in range(1, 17)])
    _record_degraded(pd, ["reason A", "reason A", "reason B"])
    assert pd.validation_errors == ["reason A", "reason B"]
    # Idempotent: re-recording the same reason does not duplicate it.
    _record_degraded(pd, ["reason B", "reason C"])
    assert pd.validation_errors == ["reason A", "reason B", "reason C"]


def test_record_degraded_empty_is_noop():
    from src.main import _record_degraded
    from src.models.pin_data import PinData, PackageInfo, Pin
    pd = PinData(component_name="X",
                 package=PackageInfo(type="SOIC-8", pin_count=8, width=1.0, height=1.0),
                 pins=[Pin(number=i, name=f"P{i}") for i in range(1, 9)])
    _record_degraded(pd, [])
    # A cleanly-grounded part must stay non-degraded (exit 0).
    assert not pd.validation_errors


def test_resolve_best_effort_fail_open_default():
    # Fail-open flip (Option C): best-effort is ON by default so the product
    # always emits a GLB when it has pin data. --strict is the only opt-out.
    from src.main import _resolve_best_effort
    # Default invocation (no flags): fail-open.
    assert _resolve_best_effort(force_best_effort=False, strict=False) is True
    # --strict restores fail-closed.
    assert _resolve_best_effort(force_best_effort=False, strict=True) is False
    # --force-best-effort (legacy) still forces best-effort even under --strict.
    assert _resolve_best_effort(force_best_effort=True, strict=True) is True
    assert _resolve_best_effort(force_best_effort=True, strict=False) is True


def test_strict_flag_defaults_off():
    # The CLI must default to fail-open: --strict present but off unless passed.
    import src.main as main_mod
    monkeypatch_argv = ["prog", "in.pdf", "out.glb"]
    import sys
    old = sys.argv
    try:
        sys.argv = monkeypatch_argv
        args = main_mod.parse_arguments()
    finally:
        sys.argv = old
    assert args.strict is False
    assert main_mod._resolve_best_effort(args.force_best_effort, args.strict) is True


def test_exit_if_degraded_exits_3_when_reasons_present():
    from src.main import _exit_if_degraded
    from src.models.pin_data import PinData, PackageInfo, Pin
    pd = PinData(component_name="X",
                 package=PackageInfo(type="SSOP-16", pin_count=16, width=1.0, height=1.0),
                 pins=[Pin(number=i, name=f"P{i}") for i in range(1, 17)],
                 validation_errors=["lossy approximation"])
    with pytest.raises(SystemExit) as exc:
        _exit_if_degraded(pd)
    assert exc.value.code == 3


# ===========================================================================
# Fix 4: module / out-of-scope detector. Modules/SiPs/grid-array parts have no
# chip-style land pattern -> emit schematic only, never a wrong footprint.
# ===========================================================================
def test_module_reason_fires_on_castellated():
    from src.pdf_extractor.module_detector import module_footprint_reason
    assert module_footprint_reason("The XYZ has castellated pad edges for reflow")


def test_module_reason_fires_on_grid_array_family():
    from src.pdf_extractor.module_detector import module_footprint_reason
    assert module_footprint_reason("", package_family="LGA")
    assert module_footprint_reason("", package_family="bga")


def test_module_reason_fires_on_title_module_wording():
    from src.pdf_extractor.module_detector import module_footprint_reason
    assert module_footprint_reason("ESP32-WROOM Wi-Fi Module\n\nPin definitions ...")
    assert module_footprint_reason("IKCM IPM intelligent power module\n\n...")


def test_module_reason_fires_on_component_name():
    from src.pdf_extractor.module_detector import module_footprint_reason
    assert module_footprint_reason("some text", component_name="ESP32-WROOM-32 module")


def test_module_reason_none_for_plain_chip():
    from src.pdf_extractor.module_detector import module_footprint_reason
    # A normal chip datasheet, no module signals in the title region.
    text = "LM358 Low-Power Dual Operational Amplifiers. " * 40
    assert module_footprint_reason(text, component_name="LM358",
                                   package_family="SOIC") is None


def test_process_both_module_emits_schematic_only(monkeypatch, tmp_path):
    import src.main as m
    from src.models.pin_data import PinData, PackageInfo, Pin
    called = {"footprint": False}
    monkeypatch.setattr(m, "build_schematic_from_pin_data", lambda **k: True)

    def fake_footprint(**k):
        called["footprint"] = True
        return True
    monkeypatch.setattr(m, "build_pcb_2d_schematic", fake_footprint)

    pd = PinData(component_name="MOD",
                 package=PackageInfo(type="QFN-32", pin_count=32, width=1.0, height=1.0),
                 pins=[Pin(number=i, name=f"P{i}") for i in range(1, 33)],
                 footprint_unsupported_reason="castellated module")
    ok = m.process_datasheet_both(pd, tmp_path / "out")
    assert ok is True, "schematic-only should count as success"
    assert called["footprint"] is False, "footprint must NOT be built for a module"


def test_process_both_non_module_builds_footprint(monkeypatch, tmp_path):
    import src.main as m
    from src.models.pin_data import PinData, PackageInfo, Pin
    called = {"footprint": False}
    monkeypatch.setattr(m, "build_schematic_from_pin_data", lambda **k: True)

    def fake_footprint(**k):
        called["footprint"] = True
        if k.get("degraded_out") is not None:
            pass
        return True
    monkeypatch.setattr(m, "build_pcb_2d_schematic", fake_footprint)

    pd = PinData(component_name="U",
                 package=PackageInfo(type="SOIC-8", pin_count=8, width=1.0, height=1.0),
                 pins=[Pin(number=i, name=f"P{i}") for i in range(1, 9)])  # no module flag
    ok = m.process_datasheet_both(pd, tmp_path / "out")
    assert ok is True
    assert called["footprint"] is True, "a normal chip must still build a footprint"


# ===========================================================================
# FIX 9: DEEP / LONG-DOCUMENT PAGE DETECTION + PAGEVERIFIER FALLBACK
# ===========================================================================

from src.pdf_extractor.page_detector import PageDetector, PageCandidate
from src.llm.page_verifier import PageVerifier


def _detector_with_total(total_pages):
    """A PageDetector whose PDF is not opened, with a fixed page count.

    Bypasses __init__ (which would open a real PDF) so the pure scoring
    rules can be exercised on synthetic inputs.
    """
    det = PageDetector.__new__(PageDetector)
    det.total_pages = total_pages
    det.pdf = None
    return det


def test_position_neutral_in_long_document():
    """In a long document the early-page bonus is dropped, so a deep page is
    not out-scored by front matter purely on position."""
    det = _detector_with_total(400)
    early = det._check_page_position(2)[0]
    deep = det._check_page_position(385)[0]
    assert early == 0, "long docs must not reward early pages"
    assert deep == 0, "deep pages are not penalised relative to early pages"
    assert early == deep, "position must be neutral across a long document"


def test_position_bonus_kept_for_medium_document():
    """Short/medium datasheets keep the plausible-position bonus (regression)."""
    det = _detector_with_total(30)
    # Cover page earns nothing; a mid-document page earns the +1 bonus.
    assert det._check_page_position(1)[0] == 0
    assert det._check_page_position(3)[0] == 1
    # Very short sheets: any page is plausible.
    short = _detector_with_total(3)
    assert short._check_page_position(2)[0] == 1


def test_deep_pin_page_can_outscore_early_cover_in_long_doc():
    """Scoring rule: a deep page carrying a pinout heading + keywords out-scores
    an early cover page in a long document, because position no longer tips the
    balance toward the front."""
    det = _detector_with_total(400)

    pin_text = (
        "Pin Assignments\n"
        "Pin No. Pin Name Function\n"
        "1 VDD Power supply input\n"
        "2 GND Ground reference\n"
        "3 GPIO0 Digital input/output\n"
        "4 RESET Reset input enable clock\n"
    )
    cover_text = (
        "Acme Semiconductor\n"
        "Ultra SiP Reference Manual\n"
        "Document Rev 1.2\n"
        "www.example.com\n"
    )

    def score(text, page_num):
        total = 0
        total += det._check_pinout_heading(text)[0]
        total += det._check_keyword_density(text)[0]
        total += det._check_page_position(page_num)[0]
        return total

    deep_score = score(pin_text, 385)
    cover_score = score(cover_text, 2)
    assert deep_score > cover_score, (
        f"deep pin page ({deep_score}) must beat early cover page ({cover_score})"
    )


def test_page_verifier_locate_parses_page_number(monkeypatch):
    """The fallback returns the LLM-named page when it is in the supplied index."""
    import src.llm.page_verifier as pv
    monkeypatch.setattr(
        pv, "get_completion_from_messages",
        lambda messages, model=None: "385"
    )
    client = MagicMock()
    client.model = "test-model"
    verifier = PageVerifier(client)
    index = [(1, "Cover"), (200, "Registers"), (385, "Pin Assignments")]
    assert verifier.locate_pin_assignment_page(index) == 385


def test_page_verifier_locate_fails_closed_on_none(monkeypatch):
    """When the LLM cannot locate a page it answers NONE and the fallback
    returns None (no fabricated page)."""
    import src.llm.page_verifier as pv
    monkeypatch.setattr(
        pv, "get_completion_from_messages",
        lambda messages, model=None: "NONE - no pinout table present"
    )
    client = MagicMock()
    client.model = "test-model"
    verifier = PageVerifier(client)
    index = [(1, "Cover"), (2, "Features")]
    assert verifier.locate_pin_assignment_page(index) is None


def test_page_verifier_locate_rejects_out_of_range(monkeypatch):
    """A page number the LLM invents that is not in the index is rejected."""
    import src.llm.page_verifier as pv
    monkeypatch.setattr(
        pv, "get_completion_from_messages",
        lambda messages, model=None: "999"
    )
    client = MagicMock()
    client.model = "test-model"
    verifier = PageVerifier(client)
    assert verifier.locate_pin_assignment_page([(1, "Cover"), (2, "Pinout")]) is None


def test_page_verifier_locate_fails_closed_on_llm_error(monkeypatch):
    """Any LLM/transport error fails closed rather than guessing."""
    import src.llm.page_verifier as pv

    def boom(messages, model=None):
        raise RuntimeError("endpoint unreachable")

    monkeypatch.setattr(pv, "get_completion_from_messages", boom)
    client = MagicMock()
    client.model = "test-model"
    verifier = PageVerifier(client)
    assert verifier.locate_pin_assignment_page([(1, "Pinout")]) is None


def _patch_empty_detector(monkeypatch):
    """Make src.main.PageDetector return no candidates without opening a PDF."""
    import src.main as m

    class FakeDetector:
        def __init__(self, path):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def detect_relevant_pages(self, min_confidence):
            return []

    monkeypatch.setattr(m, "PageDetector", FakeDetector)
    monkeypatch.setattr(m, "LLMClient", lambda **k: object())


def test_detect_pages_invokes_fallback_and_uses_located_page(monkeypatch):
    """When the deterministic detector finds nothing, the PageVerifier fallback
    is invoked and its located deep page is used."""
    import src.main as m
    _patch_empty_detector(monkeypatch)
    monkeypatch.setattr(
        m, "_build_page_heading_index",
        lambda p, **k: [(1, "Cover"), (385, "Pin Assignments")]
    )

    class FakeVerifier:
        def __init__(self, client):
            pass

        def locate_pin_assignment_page(self, index):
            return 385

    monkeypatch.setattr(m, "PageVerifier", FakeVerifier)

    candidates = m.detect_relevant_pages("dummy.pdf", 4, False, model="test-model")
    assert len(candidates) == 1
    assert candidates[0].page_number == 385


def test_detect_pages_fallback_fails_closed(monkeypatch):
    """If the verifier cannot locate a page, the pipeline fails closed
    (SystemExit / domain failure) rather than fabricating a page."""
    import src.main as m
    _patch_empty_detector(monkeypatch)
    monkeypatch.setattr(
        m, "_build_page_heading_index",
        lambda p, **k: [(1, "Cover"), (2, "Features")]
    )

    class FakeVerifier:
        def __init__(self, client):
            pass

        def locate_pin_assignment_page(self, index):
            return None

    monkeypatch.setattr(m, "PageVerifier", FakeVerifier)

    with pytest.raises(SystemExit) as exc_info:
        m.detect_relevant_pages("dummy.pdf", 4, False, model="test-model")
    assert exc_info.value.code == m.EXIT_DOMAIN_FAILURE


def test_detect_pages_no_fallback_when_detector_succeeds(monkeypatch):
    """Short-datasheet regression: when the detector already surfaces a page,
    the LLM fallback is never consulted."""
    import src.main as m

    early = PageCandidate(page_number=3, confidence_score=7, reasons=["heading"])

    class FakeDetector:
        def __init__(self, path):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def detect_relevant_pages(self, min_confidence):
            return [early]

    monkeypatch.setattr(m, "PageDetector", FakeDetector)

    def fail_if_called(p, **k):
        raise AssertionError("fallback must not run when detector succeeds")

    monkeypatch.setattr(m, "_build_page_heading_index", fail_if_called)

    candidates = m.detect_relevant_pages("dummy.pdf", 4, False, model="test-model")
    assert candidates == [early]
