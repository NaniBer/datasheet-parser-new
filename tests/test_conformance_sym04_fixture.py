"""Slice C.5: SYM-04 graded through the conformance HARNESS on static fixtures.

Unlike the inline check tests (test_slice_c_sym04*.py) which call the check
directly, this grades a deterministically-built symbol through the full runner
path (discover_artifacts -> evaluate_part), mirroring tools/gen_conformance.py.
Fixtures-only and LLM-free: pins come from src/conformance/fixtures.py and the
record is built by the name-based classifier, never the network.
"""
import tempfile
from pathlib import Path

from src.conformance.fixtures import FIXTURES, FamilyFixture
from src.conformance.runner import discover_artifacts, evaluate_part
from src.conformance.model import CheckStatus
from src.schematic_generator.adapter import build_schematic_from_pin_data
from src.models import PinData, PackageInfo, Pin, ComponentRecord


def _fx(key: str) -> FamilyFixture:
    return next(f for f in FIXTURES if f.key == key)


def _pin_data(fx: FamilyFixture) -> PinData:
    # Same construction tools/gen_conformance.py uses (roles flow through).
    return PinData(
        component_name=fx.component_name,
        package=PackageInfo(type=fx.package_type, pin_count=fx.pin_count, width=6.0, height=5.0),
        pins=[Pin(number=int(p["number"]), name=p["name"], role=p.get("role")) for p in fx.pins],
    )


def _grade_symbol(fx: FamilyFixture) -> dict:
    """Build only the symbol, then grade the part through the harness runner."""
    part_dir = Path(tempfile.mkdtemp())
    out = part_dir / f"{fx.key}_schematic.glb"
    pd = _pin_data(fx)
    ok = build_schematic_from_pin_data(
        pin_data=pd, output_path=str(out), record=ComponentRecord.from_pin_data(pd))
    assert ok and out.is_file()
    report = evaluate_part(fx.key, discover_artifacts(part_dir, base=fx.key))
    return {r.rule_id: r for r in report.results}


def test_func8_fixture_grades_sym04_pass_through_harness():
    by_id = _grade_symbol(_fx("func8"))
    assert by_id["SYM-04"].status is CheckStatus.PASS, by_id["SYM-04"].message
    # the whole symbol battery grades PASS on the same functional artifact
    for rid in ("SYM-01", "SYM-02", "SYM-05", "SYM-07", "SYM-08", "SYM-11", "SYM-12"):
        assert by_id[rid].status is CheckStatus.PASS, (rid, by_id[rid].message)


def test_roleless_fixture_skips_sym04_through_harness():
    # A generic P1..Pn fixture is below the gate: the function-dependent rules
    # SKIP (not penalised), while the rest of the symbol battery still PASSes.
    by_id = _grade_symbol(_fx("dip8"))
    for rid in ("SYM-01", "SYM-04", "SYM-05"):
        assert by_id[rid].status is CheckStatus.SKIP, (rid, by_id[rid].message)
    assert by_id["SYM-12"].status is CheckStatus.PASS
    assert by_id["SYM-02"].status is CheckStatus.PASS
