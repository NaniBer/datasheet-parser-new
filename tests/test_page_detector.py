"""Unit tests for PageDetector scoring signals."""

from unittest.mock import MagicMock, patch

import pytest

from src.pdf_extractor.page_detector import PageCandidate, PageDetector


# ---------------------------------------------------------------------------
# Fixture: detector without a real PDF
# ---------------------------------------------------------------------------

@pytest.fixture
def detector():
    """Return a PageDetector whose PDF is fully mocked out."""
    mock_pdf = MagicMock()
    mock_pdf.pages = []
    with patch("src.pdf_extractor.page_detector.pdfplumber") as mock_plumber:
        mock_plumber.open.return_value = mock_pdf
        d = PageDetector("fake.pdf")
        d.total_pages = 20
        yield d


def _make_page(tables=None, images=None, width=612, height=792, text=""):
    """Build a minimal mock pdfplumber page."""
    page = MagicMock()
    page.extract_tables.return_value = tables or []
    page.images = images or []
    page.width = width
    page.height = height
    page.extract_text.return_value = text
    return page


# ---------------------------------------------------------------------------
# _check_pinout_heading
# ---------------------------------------------------------------------------

class TestCheckPinoutHeading:
    def test_pin_configuration_in_first_line(self, detector):
        score, reason = detector._check_pinout_heading("Pin Configuration\nSome content here")
        assert score == 3
        assert "heading" in reason.lower()

    def test_pinout_keyword_in_first_line(self, detector):
        score, _ = detector._check_pinout_heading("PINOUT\ndetails follow")
        assert score == 3

    def test_package_information_heading(self, detector):
        score, _ = detector._check_pinout_heading("Package Information\nDIP-8 drawing")
        assert score == 3

    def test_pin_assignments_heading(self, detector):
        score, _ = detector._check_pinout_heading("Pin Assignments\n1 GND\n2 VCC")
        assert score == 3

    def test_pin_description_heading(self, detector):
        score, _ = detector._check_pinout_heading("Pin Descriptions\nEach pin is described below.")
        assert score == 3

    def test_no_pinout_heading(self, detector):
        score, reason = detector._check_pinout_heading(
            "Electrical Characteristics\nVcc max 5V\nIcc 10mA"
        )
        assert score == 0
        assert reason == ""

    def test_pattern_buried_deep_in_body_not_a_heading(self, detector):
        # Pattern appears only after 10 lines, so not treated as a heading
        lines = "\n".join([f"Body line {i}" for i in range(15)])
        text = lines + "\nThis section covers pin configuration in detail."
        score, _ = detector._check_pinout_heading(text)
        # Only checked in first 10 lines — should miss this
        assert score == 0

    def test_case_insensitive_match(self, detector):
        score, _ = detector._check_pinout_heading("PIN CONFIGURATION\nsome content")
        assert score == 3

    def test_pin_functions_heading(self, detector):
        score, _ = detector._check_pinout_heading("Pin Functions\ndetails follow")
        assert score == 3


# ---------------------------------------------------------------------------
# _check_keyword_density
# ---------------------------------------------------------------------------

class TestCheckKeywordDensity:
    def test_high_density_returns_score(self, detector):
        # "vcc gnd reset" = 3 keywords in 5 words → density = 60%, well above threshold
        text = "vcc gnd reset enable clock"
        score, reason = detector._check_keyword_density(text)
        assert score == 2
        assert "keyword" in reason.lower()

    def test_low_density_returns_zero(self, detector):
        # 1 keyword in 200 words → density well below 2%
        filler = " ".join(["word"] * 199)
        text = filler + " gnd"
        score, _ = detector._check_keyword_density(text)
        assert score == 0

    def test_empty_text_returns_zero(self, detector):
        score, reason = detector._check_keyword_density("")
        assert score == 0
        assert reason == ""

    def test_boundary_exactly_2_per_100(self, detector):
        # 2 keywords in exactly 100 words → density = 2.0, should pass
        filler = " ".join(["word"] * 98)
        text = filler + " vcc gnd"
        score, _ = detector._check_keyword_density(text)
        assert score == 2

    def test_repeated_keywords_count_multiple_times(self, detector):
        # "pin" repeated 5 times in 10 words → very high density
        text = " ".join(["pin"] * 5 + ["word"] * 5)
        score, _ = detector._check_keyword_density(text)
        assert score == 2

    def test_no_keywords_at_all(self, detector):
        text = "The quick brown fox jumps over the lazy dog around the corner"
        score, _ = detector._check_keyword_density(text)
        assert score == 0


# ---------------------------------------------------------------------------
# _check_page_position
# ---------------------------------------------------------------------------

class TestCheckPagePosition:
    def test_middle_of_datasheet_scores(self, detector):
        # Page 10 of 20 = 50%, within 20-70% range
        score, reason = detector._check_page_position(10)
        assert score == 1
        assert "20-70%" in reason

    def test_at_20_percent_boundary(self, detector):
        # Page 4 of 20 = 20%, boundary should include
        score, _ = detector._check_page_position(4)
        assert score == 1

    def test_at_70_percent_boundary(self, detector):
        # Page 14 of 20 = 70%, boundary should include
        score, _ = detector._check_page_position(14)
        assert score == 1

    def test_too_early_returns_zero(self, detector):
        # Page 1 of 20 = 5%, before range
        score, _ = detector._check_page_position(1)
        assert score == 0

    def test_too_late_returns_zero(self, detector):
        # Page 20 of 20 = 100%, after range
        score, _ = detector._check_page_position(20)
        assert score == 0

    def test_zero_total_pages_returns_zero(self, detector):
        detector.total_pages = 0
        score, _ = detector._check_page_position(1)
        assert score == 0


# ---------------------------------------------------------------------------
# _check_pinout_table
# ---------------------------------------------------------------------------

class TestCheckPinoutTable:
    def test_pin_number_and_function_columns(self, detector):
        # Table with "Pin No." and "Function" headers
        table = [
            ["Pin No.", "Name", "Function"],
            ["1", "GND", "Ground"],
            ["2", "VCC", "Power supply"],
        ]
        page = _make_page(tables=[table])
        score, has_table, reason = detector._check_pinout_table(page)
        assert score == 4
        assert has_table is True
        assert "pinout table" in reason.lower()

    def test_pin_name_and_description_columns(self, detector):
        table = [
            ["Pin Name", "I/O", "Description"],
            ["RESET", "I", "System reset, active low"],
        ]
        page = _make_page(tables=[table])
        score, has_table, _ = detector._check_pinout_table(page)
        assert score == 4
        assert has_table is True

    def test_signal_name_and_symbol(self, detector):
        table = [
            ["Signal Name", "Symbol", "Direction"],
            ["Serial data", "SDA", "I/O"],
        ]
        page = _make_page(tables=[table])
        score, has_table, _ = detector._check_pinout_table(page)
        assert score == 4
        assert has_table is True

    def test_no_tables_returns_zero(self, detector):
        page = _make_page(tables=[])
        score, has_table, reason = detector._check_pinout_table(page)
        assert score == 0
        assert has_table is False
        assert reason == ""

    def test_table_too_short(self, detector):
        # Only one row — not a valid pinout table
        table = [["Pin No.", "Function"]]
        page = _make_page(tables=[table])
        score, has_table, _ = detector._check_pinout_table(page)
        assert score == 0
        assert has_table is False

    def test_table_with_only_one_matching_column(self, detector):
        # Only "Description" matches — not enough
        table = [
            ["Item", "Description", "Value"],
            ["R1", "Resistor", "10k"],
        ]
        page = _make_page(tables=[table])
        score, has_table, _ = detector._check_pinout_table(page)
        assert score == 0

    def test_multi_row_header_table(self, detector):
        # Patterns are matched per-row and accumulated across rows 0-2.
        # Row 0: "I/O" → matches i/o pattern; "Description" → matches description pattern
        # Row 1: "Pin No." → matches pin_no pattern
        # Row 2: data row — not checked for patterns
        table = [
            ["I/O", "Description"],
            ["Pin No.", "Name"],
            ["I", "GND", "Ground"],
        ]
        page = _make_page(tables=[table])
        score, has_table, _ = detector._check_pinout_table(page)
        # row0: 2 matches (i/o + description) ≥ 2 → short-circuit gives score 4
        assert score == 4
        assert has_table is True

    def test_none_cells_in_header(self, detector):
        # Tables from pdfplumber can have None cells
        table = [
            [None, "Pin No.", None, "Description"],
            ["1", None, "GND", "Ground reference"],
        ]
        page = _make_page(tables=[table])
        score, has_table, _ = detector._check_pinout_table(page)
        assert score == 4
        assert has_table is True


# ---------------------------------------------------------------------------
# _check_diagram
# ---------------------------------------------------------------------------

class TestCheckDiagram:
    def test_large_image_with_pinout_caption(self, detector):
        # Image covers 50% of page area, caption says "pinout"
        images = [{"width": 400, "height": 400}]  # 160000 px²
        page = _make_page(
            images=images,
            width=600,
            height=800,  # 480000 px², ratio = 0.33
            text="Figure 1. Pinout diagram for the device.",
        )
        score, has_diagram, reason = detector._check_diagram(page)
        assert score == 2
        assert has_diagram is True
        assert "diagram" in reason.lower()

    def test_small_image_below_threshold(self, detector):
        # Image covers only 5% of page — should be ignored
        images = [{"width": 50, "height": 50}]  # 2500 px²
        page = _make_page(
            images=images,
            width=600,
            height=800,  # 480000 px², ratio = 0.005
            text="Pinout diagram shown above.",
        )
        score, has_diagram, _ = detector._check_diagram(page)
        assert score == 0
        assert has_diagram is False

    def test_no_images_returns_zero(self, detector):
        page = _make_page(images=[], text="Pinout diagram description.")
        score, has_diagram, reason = detector._check_diagram(page)
        assert score == 0
        assert has_diagram is False
        assert reason == ""

    def test_large_image_no_matching_caption(self, detector):
        images = [{"width": 400, "height": 400}]
        page = _make_page(
            images=images,
            width=600,
            height=800,
            text="Typical application circuit.",
        )
        score, has_diagram, _ = detector._check_diagram(page)
        assert score == 0
        assert has_diagram is False

    def test_pin_configuration_caption(self, detector):
        images = [{"width": 300, "height": 300}]
        page = _make_page(
            images=images,
            width=600,
            height=800,  # ratio = 0.187 — just below 0.2
            text="Pin Configuration\nFigure shows package.",
        )
        # 300*300 = 90000 / (600*800=480000) = 0.1875 < 0.2 → no score
        score, _, _ = detector._check_diagram(page)
        assert score == 0

    def test_package_drawing_caption(self, detector):
        images = [{"width": 400, "height": 300}]
        page = _make_page(
            images=images,
            width=600,
            height=800,  # ratio = 120000/480000 = 0.25 > 0.2
            text="Package drawing dimensions.",
        )
        score, has_diagram, _ = detector._check_diagram(page)
        assert score == 2
        assert has_diagram is True


# ---------------------------------------------------------------------------
# _has_unusual_structure
# ---------------------------------------------------------------------------

class TestHasUnusualStructure:
    def test_keywords_but_no_table_or_diagram(self, detector):
        candidate = PageCandidate(
            page_number=3,
            confidence_score=4,
            has_table=False,
            has_diagram=False,
            text="pin vcc gnd reset enable",
        )
        assert detector._has_unusual_structure(candidate) is True

    def test_low_text_with_diagram(self, detector):
        candidate = PageCandidate(
            page_number=3,
            confidence_score=2,
            has_table=False,
            has_diagram=True,
            text="Pin",
        )
        assert detector._has_unusual_structure(candidate) is True

    def test_normal_page_with_table(self, detector):
        candidate = PageCandidate(
            page_number=3,
            confidence_score=6,
            has_table=True,
            has_diagram=False,
            text="A" * 200,
        )
        assert detector._has_unusual_structure(candidate) is False

    def test_low_score_no_trigger(self, detector):
        # score=1, no table, no diagram — score < 2 so not flagged
        candidate = PageCandidate(
            page_number=3,
            confidence_score=1,
            has_table=False,
            has_diagram=False,
            text="some text here",
        )
        assert detector._has_unusual_structure(candidate) is False


# ---------------------------------------------------------------------------
# _analyze_page integration (full scoring)
# ---------------------------------------------------------------------------

class TestAnalyzePage:
    def test_high_confidence_full_pinout_page(self, detector):
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
        # heading(+3) + table(+4) + keyword_density(+2) + position(+1) = 10
        assert candidate.confidence_score >= 9
        assert candidate.has_table is True

    def test_zero_score_irrelevant_page(self, detector):
        page = _make_page(text="Introduction to the product family overview.")
        candidate = detector._analyze_page(20, page, page.extract_text.return_value)
        # Page 20 of 20 = 100% position → no position bonus
        # No keyword density, no heading, no table, no diagram
        assert candidate.confidence_score == 0

    def test_needs_verification_flagged_when_score_without_table(self, detector):
        # Keywords present (score ≥ 2) but no table or diagram
        page = _make_page(text="pin vcc gnd reset enable output input clock")
        candidate = detector._analyze_page(8, page, page.extract_text.return_value)
        assert candidate.needs_verification is True

    def test_candidate_page_number_stored(self, detector):
        page = _make_page(text="")
        candidate = detector._analyze_page(7, page, "")
        assert candidate.page_number == 7


# ---------------------------------------------------------------------------
# Benchmark: precision / recall against real PDFs
# ---------------------------------------------------------------------------
# These tests load ground-truth cases from benchmarks/cases/ and run the
# detector against real PDFs.  Each case asserts:
#   - Recall = 1.0  (every expected page is detected)
#   - Precision is reported but not enforced (false-positives are tracked)
#
# Run with:  pytest tests/test_page_detector.py -v -k benchmark
# ---------------------------------------------------------------------------

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks" / "manifest.json"


def _load_benchmark_cases():
    """Return list of (case_id, pdf_path, expected_pages) from the manifest."""
    manifest = json.loads(MANIFEST_PATH.read_text())
    cases = []
    for entry in manifest["cases"]:
        case = json.loads((ROOT / entry["file"]).read_text())
        pdf_path = ROOT / case["pdf"]
        if pdf_path.exists():
            cases.append((case["id"], str(pdf_path), case["expected_pinout_pages"]))
    return cases


BENCHMARK_CASES = _load_benchmark_cases()


@pytest.mark.parametrize("case_id,pdf_path,expected_pages", BENCHMARK_CASES)
def test_benchmark_recall_all_expected_pages_detected(case_id, pdf_path, expected_pages):
    """
    Every ground-truth pinout page must be in the detected set.
    Recall = |detected ∩ expected| / |expected|  must equal 1.0.
    """
    with PageDetector(pdf_path) as det:
        candidates = det.detect_relevant_pages(min_confidence=5)

    detected = {c.page_number for c in candidates}
    missed = [p for p in expected_pages if p not in detected]

    assert missed == [], (
        f"[{case_id}] Missed expected pinout pages: {missed}. "
        f"Detected: {sorted(detected)}"
    )


@pytest.mark.parametrize("case_id,pdf_path,expected_pages", BENCHMARK_CASES)
def test_benchmark_precision_report(case_id, pdf_path, expected_pages, capsys):
    """
    Report false-positive rate for each case.
    False positives are allowed (no hard assertion) — this test always passes
    and prints the precision so we have a baseline before improvements.
    """
    with PageDetector(pdf_path) as det:
        candidates = det.detect_relevant_pages(min_confidence=5)

    detected = sorted(c.page_number for c in candidates)
    expected_set = set(expected_pages)
    true_positives = [p for p in detected if p in expected_set]
    false_positives = [p for p in detected if p not in expected_set]

    precision = len(true_positives) / len(detected) if detected else 0.0
    recall = len(true_positives) / len(expected_pages) if expected_pages else 0.0

    print(
        f"\n[{case_id}]  detected={detected}  expected={sorted(expected_pages)}\n"
        f"  precision={precision:.2f}  recall={recall:.2f}  "
        f"  FP={false_positives}"
    )
    # No assertion — this is a measurement, not a pass/fail gate
