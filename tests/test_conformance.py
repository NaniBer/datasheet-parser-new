"""Tests for the conformance harness.

Pure-logic tests are deterministic and committed-safe. The end-to-end test runs
against the generated_output artifacts if present, and skips otherwise (those
artifacts are not committed — see the untracked-reference-asset gotcha).
"""
from pathlib import Path

import numpy as np
import pytest

from src.conformance.checks import (
    _board_axes,
    _planar_clearance,
    check_pin_pad_set_mapping,
    check_silk_pad_clearance,
    check_symbol_pin_numbering,
)
from src.conformance.model import CheckStatus, PartReport, CheckResult
from src.conformance.rules import RULES, coverage
from src.conformance.runner import discover_artifacts, evaluate_part

REPO = Path(__file__).resolve().parents[1]


def _box(lo, hi):
    return np.array(lo, dtype=float), np.array(hi, dtype=float)


# --- pure geometry ----------------------------------------------------------
def test_board_axes_picks_the_two_large_extent_axes():
    # Flat in X-Z (thin in Y) — the Y-up-baked footprint case.
    boxes = [_box([-5, 0, -5], [5, 0.02, 5]), _box([-1, 0, -1], [1, 0.02, 1])]
    assert _board_axes(boxes) == (0, 2)


def test_planar_clearance_separated_and_overlapping():
    axes = (0, 2)
    a = _box([0, 0, 0], [1, 0.02, 1])
    b = _box([2, 0, 0], [3, 0.02, 1])          # 1.0 mm gap in X
    assert _planar_clearance(a, b, axes) == pytest.approx(1.0)
    c = _box([0.5, 0, 0], [1.5, 0.02, 1])      # overlaps a in X by 0.5
    assert _planar_clearance(a, c, axes) < 0   # negative => overlap


# --- rule inventory ---------------------------------------------------------
def test_coverage_reports_a_subset_of_must_rules():
    impl, total = coverage()
    assert 0 < impl <= total
    assert total == sum(1 for r in RULES if r.tier == "must")


def test_unrun_must_rule_blocks_the_pass():
    # A report with a single unchecked MUST rule must not pass.
    rep = PartReport("x", {}, [
        CheckResult("Z-01", "must", "t", CheckStatus.UNRUN),
    ])
    assert rep.passes_all_must is False


# --- end-to-end against real artifacts (skip if absent) ---------------------
def _first_available_part():
    root = REPO / "generated_output"
    if not root.is_dir():
        return None
    for d in sorted(root.iterdir()):
        if d.is_dir() and discover_artifacts(d):
            return d
    return None


def test_evaluate_part_grades_a_real_footprint():
    part = _first_available_part()
    if part is None:
        pytest.skip("no generated_output artifacts to grade")
    report = evaluate_part(part.name, discover_artifacts(part))
    by_id = {r.rule_id: r for r in report.results}

    # V-01 (pin/pad set) must have actually run on a real part.
    assert by_id["V-01"].status in (CheckStatus.PASS, CheckStatus.FAIL)
    # The report is well-formed and self-consistent.
    assert report.must_total == sum(1 for r in RULES if r.tier == "must")
    assert isinstance(report.to_dict()["summary"]["passes_all_must"], bool)
