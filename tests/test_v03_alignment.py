"""V-03: 3D body aligns to footprint (origin, leads, height) — build-time verdict.

Like 3D-03, V-03 cannot be graded from the static GLB (per-lead identity is
gone), so it is supplied to the harness via extra_results from the driver. These
tests cover the composite verdict logic directly (fast) plus one end-to-end
grade through gen_conformance + evaluate_part.
"""
import tempfile
from pathlib import Path

from src.model3d.builder import Body3DResult, footprint_alignment_verdict
from src.conformance.fixtures import FIXTURES
from src.conformance.runner import discover_artifacts, evaluate_part
from src.conformance.model import CheckStatus


def _aligned(**kw) -> Body3DResult:
    base = dict(success=True, align_ok=True, worst_align_delta=0.05,
                metrics={"center_x": 0.0, "center_y": 0.0}, issues=[])
    base.update(kw)
    return Body3DResult(**base)


# --- composite verdict logic ------------------------------------------------
def test_verdict_none_without_body():
    assert footprint_alignment_verdict(Body3DResult(success=False)) is None


def test_verdict_none_without_pad_map():
    # align_ok None => alignment was never assessed -> rule stays UNRUN
    assert footprint_alignment_verdict(_aligned(align_ok=None)) is None


def test_verdict_pass_when_all_aligned():
    ok, msg = footprint_alignment_verdict(_aligned())
    assert ok is True


def test_verdict_fails_on_origin_offset():
    ok, _ = footprint_alignment_verdict(_aligned(metrics={"center_x": 0.5, "center_y": 0.0}))
    assert ok is False


def test_verdict_fails_on_lead_misalignment():
    ok, _ = footprint_alignment_verdict(
        _aligned(align_ok=False, worst_align_delta=0.9, issues=["pin 3 lead foot off pad"]))
    assert ok is False


def test_verdict_fails_on_height_mismatch():
    ok, _ = footprint_alignment_verdict(_aligned(issues=["height 2.100 != A 1.750 (tol 0.05)"]))
    assert ok is False


# --- end-to-end through the driver + harness runner -------------------------
def test_v03_graded_pass_through_driver():
    import tools.gen_conformance as gc
    fx = next(f for f in FIXTURES if f.key == "soic8")
    part_dir = Path(tempfile.mkdtemp()) / fx.key
    produced, build_results = gc.generate_family(fx, part_dir)
    assert "V-03" in build_results, "driver did not emit a V-03 verdict"
    report = evaluate_part(fx.key, discover_artifacts(part_dir, base=fx.key),
                           extra_results=build_results)
    by_id = {r.rule_id: r for r in report.results}
    assert by_id["V-03"].status is CheckStatus.PASS, by_id["V-03"].message
