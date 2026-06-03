"""Tests for the optional extraction benchmark scaffold."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "benchmarks" / "manifest.json"
REQUIRED_CASE_KEYS = {
    "id",
    "pdf",
    "component_name",
    "expected_package_family",
    "expected_pin_count",
    "expected_pin_map",
    "expected_pinout_pages",
}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def test_benchmark_manifest_points_to_valid_case_files():
    """The benchmark scaffold should stay self-contained and file-backed."""
    manifest = _load_json(MANIFEST_PATH)

    assert manifest["schema_version"] == 1
    cases = manifest["cases"]
    assert cases, "Expected at least one benchmark case"

    case_ids = []
    for case_entry in cases:
        case_ids.append(case_entry["id"])
        case_path = ROOT / case_entry["file"]
        assert case_path.exists(), f"Missing benchmark case file: {case_path}"

        case = _load_json(case_path)
        assert case["id"] == case_entry["id"]
        assert REQUIRED_CASE_KEYS.issubset(case)

        pdf_path = ROOT / case["pdf"]
        assert pdf_path.exists(), f"Missing benchmark PDF: {pdf_path}"

        pin_map = case["expected_pin_map"]
        assert pin_map, f"Expected a non-empty pin map for {case['id']}"

        expected_numbers = list(range(1, len(pin_map) + 1))
        actual_numbers = [pin["number"] for pin in pin_map]
        assert actual_numbers == expected_numbers, f"Unexpected pin numbering for {case['id']}"

        for pin in pin_map:
            assert pin["name"], f"Empty pin name in {case['id']}"

        expected_pages = case["expected_pinout_pages"]
        assert expected_pages, f"Expected pinout pages for {case['id']}"
        assert all(isinstance(page, int) and page > 0 for page in expected_pages)

        assert case["expected_pin_count"] == len(pin_map)

    assert len(case_ids) == len(set(case_ids)), "Benchmark case IDs must be unique"
