"""
Tests for JEDEC mechanical-symbol extraction of:
  - c  = lead thickness (mm), small (~0.05-0.60)
  - D2 = exposed thermal-pad length (mm), for QFN/DFN/leadless
  - E2 = exposed thermal-pad width  (mm), for QFN/DFN/leadless

These keys are OPTIONAL. Their absence must not change any existing behavior:
they are not in CRITICAL_KEYS, and extraction must still succeed without them.
"""

from src.pdf_extractor.dimension_extractor import DimensionExtractor
from src.pdf_extractor.text_dimensions import (
    parse_ti_outline,
    plausible_dims,
)


# --------------------------------------------------------------------------- #
# _flatten(): nested {min,max} collapse + passthrough
# --------------------------------------------------------------------------- #

def test_flatten_collapses_c_min_max_to_midpoint():
    ext = DimensionExtractor()
    raw = {
        "package_type": "QFN-16",
        "unit": "mm",
        "dimensions": {
            "e": "0.5",
            "c": {"min": "0.09", "max": "0.20"},
        },
    }
    flat = ext._flatten(raw)
    assert flat is not None
    assert abs(flat["c"] - 0.145) < 1e-9


def test_flatten_passes_d2_e2_through():
    ext = DimensionExtractor()
    raw = {
        "package_type": "QFN-16",
        "unit": "mm",
        "dimensions": {
            "e": "0.5",
            "D2": {"min": "2.0", "max": "2.2"},
            "E2": "2.1",
        },
    }
    flat = ext._flatten(raw)
    assert flat is not None
    assert abs(flat["D2"] - 2.1) < 1e-9
    assert abs(flat["E2"] - 2.1) < 1e-9


# --------------------------------------------------------------------------- #
# plausible_dims(): accept valid, reject implausible c / D2 / E2
# --------------------------------------------------------------------------- #

def test_plausible_accepts_valid_c_d2_e2():
    dims = {
        "e": 0.5, "D": 4.0, "E": 4.0, "E1": 4.0, "b": 0.25,
        "c": 0.15, "D2": 2.6, "E2": 2.6,
    }
    assert plausible_dims(dims) is True


def test_plausible_rejects_thick_c():
    # c = 5.0 mm cannot be a lead thickness.
    assert plausible_dims({"e": 0.5, "c": 5.0}) is False


def test_plausible_rejects_thin_c():
    # c = 0.01 mm is below any real lead thickness.
    assert plausible_dims({"e": 0.5, "c": 0.01}) is False


def test_plausible_rejects_d2_bigger_than_body():
    # Exposed pad D2 cannot exceed the body length D.
    assert plausible_dims({"e": 0.5, "D": 4.0, "D2": 5.0}) is False


def test_plausible_rejects_e2_bigger_than_body():
    # Exposed pad E2 cannot exceed the body width E1.
    assert plausible_dims({"e": 0.5, "E1": 4.0, "E2": 5.0}) is False


def test_plausible_rejects_nonpositive_d2():
    assert plausible_dims({"e": 0.5, "D": 4.0, "D2": 0.0}) is False


# --------------------------------------------------------------------------- #
# Optional guard: a dict without c/D2/E2 behaves exactly as before
# --------------------------------------------------------------------------- #

def test_dict_without_new_keys_still_plausible():
    dims = {"e": 1.27, "E": 10.3, "D": 9.9, "E1": 7.5, "b": 0.4, "L": 0.8, "A": 2.5}
    assert plausible_dims(dims) is True


def test_new_keys_not_in_critical_keys():
    # Optional keys must not be treated as required for a complete extraction.
    for k in ("c", "D2", "E2"):
        assert k not in DimensionExtractor.CRITICAL_KEYS


# --------------------------------------------------------------------------- #
# Text parsing: QFN outline snippet with c and exposed-pad lines
# --------------------------------------------------------------------------- #

def test_parse_ti_outline_captures_c():
    # A QFN outline lists lead thickness c as a small MIN/MAX pair labelled c.
    text = "\n".join([
        "14X 0.50",
        "16X 0.50",
        "0.30",
        "0.80 MAX",
        "0.203",
        "0.152",
        "c",
    ])
    dims = parse_ti_outline(text, 16)
    assert "c" in dims
    assert abs(dims["c"] - (0.203 + 0.152) / 2.0) < 1e-9


def test_parse_ti_outline_captures_exposed_pad():
    text = "\n".join([
        "14X 0.50",
        "EXPOSED THERMAL PAD",
        "2.60",
        "2.60",
    ])
    dims = parse_ti_outline(text, 16)
    assert abs(dims.get("D2", 0) - 2.60) < 1e-9
    assert abs(dims.get("E2", 0) - 2.60) < 1e-9
