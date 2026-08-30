#!/usr/bin/env python3
"""Per-family generation conformance driver.

Feeds each known-good fixture (src/conformance/fixtures.py) straight into the
three builders — schematic, footprint, 3D body — exactly as the pipeline's
``process_datasheet_both`` does, but with correct inputs and no PDF/LLM. Then
grades every produced artifact with the conformance harness and prints the
generation generality map: family x MUST-rule pass/fail.

    python tools/gen_conformance.py                 # all families
    python tools/gen_conformance.py soic8 qfn32     # a subset
    python tools/gen_conformance.py --out gen_out    # keep artifacts

This isolates the deterministic half: any failure here is a generator defect,
not an extraction defect.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

# Repo root on path so `python tools/...` resolves `src` as a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.conformance.fixtures import FIXTURES, FamilyFixture
from src.conformance.model import CheckStatus, PartReport
from src.conformance.runner import (
    discover_artifacts,
    evaluate_part,
    print_corpus_summary,
    print_part_report,
)
from src.models import PinData, PackageInfo, Pin, ComponentRecord

# {rule_id: (status, message)} for build-time-only rules the static artifacts
# can't express (3D-03 needs per-lead identity + the footprint pad map).
BuildResults = Dict[str, tuple]


def _pin_data(fx: FamilyFixture) -> PinData:
    """A legacy single-package PinData carrying the fixture's correct pins.

    Pin roles (when the fixture supplies them) flow through so the schematic
    builder can group by function (SYM-04); role-less fixtures stay physical.
    """
    return PinData(
        component_name=fx.component_name,
        package=PackageInfo(type=fx.package_type, pin_count=fx.pin_count, width=6.0, height=5.0),
        pins=[Pin(number=int(p["number"]), name=p["name"], role=p.get("role")) for p in fx.pins],
    )


def generate_family(fx: FamilyFixture, out_dir: Path) -> tuple:
    """Build all three artifacts for one fixture.

    Returns ``(produced, build_results)`` where ``produced`` is {kind: path} and
    ``build_results`` carries verdicts for build-time-only rules (3D-03). Each
    builder is guarded: a fail-closed refusal (e.g. BGA footprint) is recorded as
    "not produced", not a crash — the harness then SKIPs it.
    """
    from src.schematic_generator import (
        build_pcb_2d_schematic,
        build_schematic_from_pin_data,
        pin_data_to_builder_format,
    )
    from src.schematic_generator.pcb_footprint_builder import PcbFootprintBuilder
    from src.model3d import build_body_model
    from src.model3d.builder import footprint_alignment_verdict

    out_dir.mkdir(parents=True, exist_ok=True)
    pin_data = _pin_data(fx)
    produced: Dict[str, str] = {}
    build_results: BuildResults = {}

    schematic = out_dir / f"{fx.key}_schematic.glb"
    try:
        # Record carries per-pin roles to the builder so functional grouping
        # (SYM-04) applies to gated fixtures; role-less fixtures stay physical.
        record = ComponentRecord.from_pin_data(pin_data)
        if build_schematic_from_pin_data(pin_data=pin_data, output_path=str(schematic), record=record) and schematic.is_file():
            produced["symbol"] = str(schematic)
    except Exception as e:
        print(f"  [{fx.key}] schematic refused/failed: {e}")

    footprint = out_dir / f"{fx.key}_footprint.glb"
    try:
        _, _, _, pins_for_builder = pin_data_to_builder_format(pin_data)
        ok = build_pcb_2d_schematic(
            package_type=fx.package_type,
            pin_count=fx.pin_count,
            component_name=fx.component_name,
            pin_data=pins_for_builder,
            output_path=str(footprint),
            extracted_dims=fx.extracted_dims,
        )
        if ok and footprint.is_file():
            produced["footprint"] = str(footprint)
            # V-02: when the fixture carries datasheet dims, grade the built
            # footprint against them (build-time verdict; UNRUN otherwise).
            if fx.extracted_dims:
                from src.conformance.checks import footprint_dims_verdict
                verdict = footprint_dims_verdict(str(footprint), fx.extracted_dims)
                if verdict is not None:
                    passed, msg = verdict
                    build_results["V-02"] = (
                        CheckStatus.PASS if passed else CheckStatus.FAIL, msg,
                    )
    except Exception as e:
        print(f"  [{fx.key}] footprint refused/failed: {e}")

    # Pad map from the footprint (shared mm/origin-centred frame) so the body's
    # lead feet can be validated against pad centres — that's rule 3D-03.
    pad_map = None
    if "footprint" in produced:
        try:
            fb = PcbFootprintBuilder(fx.package_type, fx.pin_count, fx.component_name,
                                     extracted_dims=fx.extracted_dims)
            pad_map = {str(p.pin_number): (p.x, p.y) for p in fb.pin_positions}
        except Exception:
            pad_map = None

    body_base = out_dir / f"{fx.key}_body"
    try:
        body = build_body_model(
            package_type=fx.package_type,
            pin_count=fx.pin_count,
            component_name=fx.component_name,
            extracted_dims=fx.extracted_dims,
            output_base=str(body_base),
            footprint_pad_map=pad_map,
        )
        if body.success:
            if body.glb_path and Path(body.glb_path).is_file():
                produced["body"] = body.glb_path
            if body.step_path and Path(body.step_path).is_file():
                produced["body_step"] = body.step_path
            # 3D-03: every lead foot landed on its numbered pad.
            if body.align_ok is True:
                build_results["3D-03"] = (
                    CheckStatus.PASS,
                    f"lead feet on numbered pads (worst {body.worst_align_delta:.3f} mm)",
                )
            elif body.align_ok is False:
                build_results["3D-03"] = (
                    CheckStatus.FAIL,
                    f"lead/pad numbering or position mismatch (worst {body.worst_align_delta:.3f} mm); "
                    + "; ".join(body.issues[:2]),
                )
            # V-03: composite body->footprint alignment (origin, leads, height).
            verdict = footprint_alignment_verdict(body)
            if verdict is not None:
                ok, msg = verdict
                build_results["V-03"] = (
                    CheckStatus.PASS if ok else CheckStatus.FAIL, msg,
                )
        else:
            print(f"  [{fx.key}] body skipped: {body.reason}")
    except Exception as e:
        print(f"  [{fx.key}] body refused/failed: {e}")

    return produced, build_results


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Grade generation conformance per package family.")
    ap.add_argument("keys", nargs="*", help="Fixture keys to run (default: all).")
    ap.add_argument("--out", help="Directory for artifacts (default: a temp dir, cleaned up).")
    ap.add_argument("--show-unrun", action="store_true")
    args = ap.parse_args(argv)

    selected = [fx for fx in FIXTURES if not args.keys or fx.key in args.keys]
    if not selected:
        ap.error(f"no fixtures match {args.keys}; known: {[f.key for f in FIXTURES]}")

    tmp = None
    if args.out:
        root = Path(args.out)
    else:
        tmp = tempfile.TemporaryDirectory(prefix="gen_conf_")
        root = Path(tmp.name)

    reports: List[PartReport] = []
    try:
        for fx in selected:
            print(f"\n--- generating {fx.key} ({fx.package_type}, {fx.lead_style}) ---")
            produced, build_results = generate_family(fx, root / fx.key)
            if not produced:
                print(f"  no artifacts produced for {fx.key}")
                continue
            report = evaluate_part(
                fx.key,
                discover_artifacts(root / fx.key, base=fx.key),
                extra_results=build_results,
            )
            print_part_report(report, show_unrun=args.show_unrun)
            reports.append(report)

        if reports:
            print_corpus_summary(reports)
            _print_family_rule_matrix(reports)
    finally:
        if tmp is not None:
            tmp.cleanup()

    # Non-zero exit if any family fails a MUST — useful as a CI gate later.
    return 0 if all(r.passes_all_must for r in reports) else 1


def _print_family_rule_matrix(reports: List[PartReport]) -> None:
    """Compact family x rule grid for MUST rules that ran on at least one part."""
    ran = [r for r in reports]
    rule_ids: List[str] = []
    for rep in ran:
        for res in rep.results:
            if res.tier == "must" and res.status is not CheckStatus.UNRUN and res.rule_id not in rule_ids:
                rule_ids.append(res.rule_id)
    if not rule_ids:
        return
    glyph = {CheckStatus.PASS: ".", CheckStatus.FAIL: "X", CheckStatus.SKIP: "-", CheckStatus.UNRUN: " "}
    print("\nGeneration map (MUST rules; . pass  X fail  - n/a):")
    print("  " + "".join(f"{rid.split('-')[0]:>4}" for rid in rule_ids) + "   (rule prefix)")
    print("  " + "".join(f"{rid.split('-')[1]:>4}" for rid in rule_ids))
    for rep in ran:
        by_id = {res.rule_id: res.status for res in rep.results}
        row = "".join(f"{glyph.get(by_id.get(rid, CheckStatus.UNRUN), ' '):>4}" for rid in rule_ids)
        print(f"  {row}  {rep.part}")


if __name__ == "__main__":
    sys.exit(main())
