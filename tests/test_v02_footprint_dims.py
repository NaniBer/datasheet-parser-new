"""V-02: footprint dimensions match the datasheet — build-time verdict.

Like V-03, V-02 needs data absent from the on-disk artifact (the datasheet
dims), so it is graded where the driver holds both the extracted dims and the
built footprint. Tests inject SYNTHETIC dims (no LLM) and check the verdict.
"""
import tempfile
from pathlib import Path

from src.schematic_generator.pcb_footprint_builder import build_pcb_footprint
from src.conformance.checks import footprint_dims_verdict
from src.conformance.fixtures import FIXTURES
from src.conformance.runner import discover_artifacts, evaluate_part
from src.conformance.model import CheckStatus

# 74HC595 (TI) SOIC-16 datasheet dims.
SOIC16 = {"e": 1.27, "E": 10.325, "D": 9.90, "b": 0.41, "L": 0.835}


def _footprint(dims=None, pkg="SOIC-16", n=16) -> str:
    out = str(Path(tempfile.mkdtemp()) / "fp.glb")
    pins = [{"number": i, "name": f"P{i}"} for i in range(1, n + 1)]
    assert build_pcb_footprint(pkg, n, "X", pins, out, extracted_dims=dims)
    return out


def test_v02_passes_when_geometry_matches_datasheet():
    ok, msg = footprint_dims_verdict(_footprint(SOIC16), SOIC16)
    assert ok is True, msg


def test_v02_fails_when_dims_contradict_geometry():
    # Build with the real dims, then grade against contradictory dims.
    ok, msg = footprint_dims_verdict(
        _footprint(SOIC16), {"e": 2.54, "E": 20.0, "D": 20.0, "b": 0.9, "L": 1.6})
    assert ok is False


def test_v02_none_when_nothing_comparable():
    # No e / E / D in the dict -> nothing to compare -> None (rule stays UNRUN).
    assert footprint_dims_verdict(_footprint(SOIC16), {"b": 0.41}) is None


def test_v02_graded_pass_through_driver():
    import tools.gen_conformance as gc
    fx = next(f for f in FIXTURES if f.key == "soic16d")
    part_dir = Path(tempfile.mkdtemp()) / fx.key
    _, build_results = gc.generate_family(fx, part_dir)
    assert "V-02" in build_results, "driver did not emit a V-02 verdict"
    report = evaluate_part(fx.key, discover_artifacts(part_dir, base=fx.key),
                           extra_results=build_results)
    by_id = {r.rule_id: r for r in report.results}
    assert by_id["V-02"].status is CheckStatus.PASS, by_id["V-02"].message
