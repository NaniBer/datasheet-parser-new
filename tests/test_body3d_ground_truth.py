"""3D body-model dimensional ground-truth tests.

Drives the harness in tools/run_body3d_ground_truth_eval.py: builds our
generated package bodies and asserts their sorted bounding-box extents match
the official reference STEP models (KiCad / SnapEDA), centroid-normalized,
within a loose dimensional tolerance.

Each reference STEP is optional at test time: if the file is missing the case
skips gracefully rather than failing.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HARNESS_PATH = REPO_ROOT / "tools" / "run_body3d_ground_truth_eval.py"


def _load_harness():
    spec = importlib.util.spec_from_file_location("body3d_gt_eval", HARNESS_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


harness = _load_harness()

# Cases that MUST pass: both SOIC references plus one DIP. Selected by name from
# the harness CASES so the test and the eval stay in lockstep.
_REQUIRED_NAMES = {"TL072", "MM74HC594M", "ATMEGA328P-PU"}
_REQUIRED_CASES = [c for c in harness.CASES if c[0] in _REQUIRED_NAMES]


@pytest.mark.parametrize("case", _REQUIRED_CASES, ids=[c[0] for c in _REQUIRED_CASES])
def test_body_matches_reference_step(case):
    name, package_type, pin_count, extracted_dims, ref_rel_path = case
    ref_path = harness.GROUND_TRUTH_DIR / ref_rel_path
    if not ref_path.exists():
        pytest.skip(f"reference STEP missing: {ref_rel_path}")

    result = harness.run_case(*case)
    assert result["status"] == "ok"
    assert result["passed"], (
        f"{name}: our extents {result['ours']} vs reference "
        f"{result['reference']} exceed tolerance (delta {result['delta']}, "
        f"tol {result['tolerance']})"
    )


def test_all_required_cases_covered():
    """Guard: the harness still defines the three cases the gate depends on."""
    assert len(_REQUIRED_CASES) == 3
