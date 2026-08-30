"""Evaluate parts against the rule inventory and aggregate a corpus report.

    # grade already-generated artifacts
    python -m src.conformance.runner generated_output/LM358 generated_output/74HC595

    # grade every part folder under a root
    python -m src.conformance.runner --corpus generated_output

Prints a per-part battery and a corpus roll-up: the single pass-rate number plus
a per-rule failure count, so you fix by defect *class* across the whole corpus.
Writes a machine-readable ``conformance.json`` next to each part (spec V-05).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

from .checks import REGISTRY, PartContext, _Outcome
from .model import CheckResult, CheckStatus, PartReport
from .rules import RULES, coverage

# CLI artifact suffix -> context kind.
_ARTIFACT_SUFFIXES = {
    "_schematic.glb": "symbol",
    "_footprint.glb": "footprint",
    "_body.glb": "body",
    "_body.step": "body_step",
}


def discover_artifacts(part_dir: Path, base: Optional[str] = None) -> Dict[str, str]:
    """Find the generated artifacts in a part directory.

    ``base`` defaults to the directory name (matches ``generated_output/<NAME>/``
    and the API job layout where the base stem is ``output``).
    """
    candidates = [base] if base else [part_dir.name, "output"]
    found: Dict[str, str] = {}
    for stem in candidates:
        for suffix, kind in _ARTIFACT_SUFFIXES.items():
            path = part_dir / f"{stem}{suffix}"
            if path.is_file() and kind not in found:
                found[kind] = str(path)
    return found


def evaluate_part(
    part: str,
    artifacts: Dict[str, str],
    extra_results: Optional[Dict[str, tuple]] = None,
) -> PartReport:
    """Run every rule's check against one part's artifacts.

    ``extra_results`` supplies verdicts for build-time-only rules (e.g. 3D-03,
    which needs per-lead identity absent from the static artifacts) as
    ``{rule_id: (CheckStatus, message)}``. It only fills rules that have no
    static check, so it can never silently override an automated result.
    """
    ctx = PartContext(part, artifacts)
    cache: Dict[str, _Outcome] = {}
    results: List[CheckResult] = []
    extra_results = extra_results or {}

    for rule in RULES:
        if rule.check is None:
            if rule.id in extra_results:
                status, message = extra_results[rule.id]
                results.append(CheckResult(rule.id, rule.tier, rule.title, status, message=message))
                continue
            results.append(CheckResult(
                rule.id, rule.tier, rule.title, CheckStatus.UNRUN,
                message="no automated check yet",
            ))
            continue
        fn = REGISTRY.get(rule.check)
        if fn is None:
            results.append(CheckResult(
                rule.id, rule.tier, rule.title, CheckStatus.UNRUN,
                message=f"check {rule.check!r} not registered",
            ))
            continue
        if rule.check not in cache:
            cache[rule.check] = fn(ctx)
        o = cache[rule.check]
        results.append(CheckResult(
            rule.id, rule.tier, rule.title, o.status,
            message=o.message, measured=o.measured, threshold=o.threshold,
        ))

    return PartReport(part=part, artifacts=artifacts, results=results)


_ICON = {
    CheckStatus.PASS: "PASS",
    CheckStatus.FAIL: "FAIL",
    CheckStatus.SKIP: "skip",
    CheckStatus.UNRUN: "----",
}


def print_part_report(report: PartReport, show_unrun: bool = False) -> None:
    print(f"\n=== {report.part} ===")
    for r in report.results:
        if r.status is CheckStatus.UNRUN and not show_unrun:
            continue
        line = f"  [{_ICON[r.status]}] {r.rule_id:<7} {r.title}"
        if r.message:
            line += f"  — {r.message}"
        print(line)
    print(
        f"  MUST: {report.must_pass} pass / {report.must_fail} fail / "
        f"{report.must_unrun} unrun of {report.must_total}"
        f"   ->  {'PASS' if report.passes_all_must else 'BLOCKED'}"
    )


def print_corpus_summary(reports: List[PartReport]) -> None:
    total = len(reports)
    passing = sum(1 for r in reports if r.passes_all_must)
    impl, must_total = coverage()

    # Per-rule failure tally across the corpus — the fix-by-class view.
    fails: Dict[str, int] = {}
    titles: Dict[str, str] = {}
    for rep in reports:
        for r in rep.results:
            if r.status is CheckStatus.FAIL:
                fails[r.rule_id] = fails.get(r.rule_id, 0) + 1
                titles[r.rule_id] = r.title

    print("\n" + "=" * 60)
    print("CORPUS CONFORMANCE SUMMARY")
    print("=" * 60)
    print(f"Parts passing all MUST : {passing}/{total}"
          + (f"  ({100 * passing / total:.0f}%)" if total else ""))
    print(f"MUST coverage automated: {impl}/{must_total} rules")
    if fails:
        print("\nMost frequent MUST failures (fix by class):")
        for rid, n in sorted(fails.items(), key=lambda kv: kv[1], reverse=True):
            print(f"  {n:>3} x  {rid:<7} {titles[rid]}")
    else:
        print("\nNo MUST failures across graded parts.")


def _write_json(report: PartReport, out_dir: Path) -> None:
    (out_dir / "conformance.json").write_text(json.dumps(report.to_dict(), indent=2))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Grade generated parts against the IDEEZA spec.")
    ap.add_argument("parts", nargs="*", help="Part directories (each holds the generated artifacts).")
    ap.add_argument("--corpus", help="Root dir; every immediate subdirectory is graded as a part.")
    ap.add_argument("--base", help="Artifact base stem (default: part dir name, then 'output').")
    ap.add_argument("--show-unrun", action="store_true", help="List inventoried-but-unautomated rules too.")
    ap.add_argument("--json", action="store_true", help="Write conformance.json into each part dir.")
    args = ap.parse_args(argv)

    part_dirs: List[Path] = [Path(p) for p in args.parts]
    if args.corpus:
        root = Path(args.corpus)
        part_dirs += sorted(d for d in root.iterdir() if d.is_dir())
    if not part_dirs:
        ap.error("give one or more part directories, or --corpus <root>")

    reports: List[PartReport] = []
    for d in part_dirs:
        artifacts = discover_artifacts(d, base=args.base)
        if not artifacts:
            print(f"\n=== {d.name} ===\n  (no artifacts found — skipped)")
            continue
        report = evaluate_part(d.name, artifacts)
        print_part_report(report, show_unrun=args.show_unrun)
        if args.json:
            _write_json(report, d)
        reports.append(report)

    if reports:
        print_corpus_summary(reports)
    return 0


if __name__ == "__main__":
    sys.exit(main())
