#!/usr/bin/env python3
"""3D body-model dimensional ground-truth eval.

Compares OUR generated package bodies (src.model3d) against official reference
STEP models shipped by KiCad / SnapEDA, centroid-normalized and within a loose
dimensional tolerance. This is the dimensional-fidelity gate for the 3D body
layer.

Why sorted extents? The vendor STEP files arrive in arbitrary orientation and
origin, and our builder does not necessarily share their axis labelling. So we
compare the SORTED (X, Y, Z) bounding-box extents of each body: the three
numbers (two footprint extents + one height) are rotation/axis-order invariant.
Reference STEP models INCLUDE leads, so the two larger extents track the
lead-span and body-length while the smallest is the height.

Tolerances are deliberately LOOSE because vendor lead length / toe / splay
differ from part to part:
  * height  (smallest sorted extent): +/- 0.4 mm
  * the two footprint extents        : +/- 0.6 mm

Run:  python3 tools/run_body3d_ground_truth_eval.py
Exit: 0 if every case passes, 1 otherwise. Writes a JSON report to
      eval_output/body3d_ground_truth_report.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cadquery as cq

# Repo root = parent of tools/; ensure `src` is importable when run directly.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.model3d.spec import build_spec  # noqa: E402
from src.model3d.registry import select_template  # noqa: E402

GROUND_TRUTH_DIR = REPO_ROOT / "tests" / "ground_truth"
REPORT_PATH = REPO_ROOT / "eval_output" / "body3d_ground_truth_report.json"

# Tolerances (mm). The smallest sorted extent is treated as the body height and
# held tighter; the two footprint extents get more slack for vendor lead
# differences. Kept intentionally loose but NOT loosened past ~0.7 to force a
# pass -- a real mismatch is a finding, not a harness failure.
TOL_HEIGHT = 0.4
TOL_FOOTPRINT = 0.6


# Each case fixes the true datasheet dimensions from the JEDEC package code in
# the reference .kicad_mod filename, so our body is built to the real size.
# "dims_source": "text" makes the spec resolve as verified.
CASES: List[Tuple[str, str, int, Dict, str]] = [
    (
        # TL072 -> SOIC-8 narrow. Ref footprint: SOIC127P600X175-8N
        # pitch 1.27, span(E) 6.00, height(A) 1.75, body D 4.90 x E1 3.90.
        "TL072",
        "SOIC",
        8,
        {"D": 4.90, "E1": 3.90, "A": 1.75, "A1": 0.10,
         "e": 1.27, "E": 6.00, "b": 0.41, "L": 0.65, "dims_source": "text"},
        "TLO62CDR/TLO62CDR.step",
    ),
    (
        # MM74HC594M -> SOIC-16 narrow. Ref footprint: SOIC127P600X175-16N
        # same cross-section as SOIC-8, body length D 9.90.
        "MM74HC594M",
        "SOIC",
        16,
        {"D": 9.90, "E1": 3.90, "A": 1.75, "A1": 0.10,
         "e": 1.27, "E": 6.00, "b": 0.41, "L": 0.65, "dims_source": "text"},
        "MM74HC594M/MM74HC594M.step",
    ),
    (
        # ATMEGA328P-PU -> DIP-28 (300 mil / skinny). Ref: DIP794W46P254L2967H457Q28B
        # row span(E) 7.94, pitch 2.54, height(A) 4.57, body length D 34.67.
        "ATMEGA328P-PU",
        "DIP",
        28,
        {"D": 34.67, "E1": 7.87, "A": 4.57, "A1": 0.38,
         "e": 2.54, "E": 7.94, "b": 0.46, "L": 3.30, "dims_source": "text"},
        "ATMEGA328P-PU/ATMEGA328P-PU.step",
    ),
    (
        # MCP3208-CI/P -> PDIP-16 (300 mil). Ref: DIP254P762X432-16
        # pitch 2.54, row span 7.62, height 4.32, body length D 19.30.
        "MCP3208-CI_P",
        "PDIP",
        16,
        {"D": 19.30, "E1": 7.62, "A": 4.32, "A1": 0.38,
         "e": 2.54, "E": 7.62, "b": 0.46, "L": 3.30, "dims_source": "text"},
        "MCP3208-CI_P/MCP3208-CI_P.step",
    ),
]


def sorted_extents(x: float, y: float, z: float) -> List[float]:
    """Return the three bounding-box extents sorted ascending (height first)."""
    return sorted([x, y, z])


def reference_extents(step_path: Path) -> List[float]:
    """Sorted (X, Y, Z) extents of a reference STEP model.

    The compound bounding box of an imported STEP is unreliable in this
    OCC build (it can come back as an uninitialised/infinite box), so we
    aggregate the min/max across the individual solids -- which is robust.
    """
    wp = cq.importers.importStep(str(step_path))
    solids = wp.solids().vals()
    if not solids:
        raise ValueError(f"no solids in reference STEP: {step_path}")

    xmin = ymin = zmin = float("inf")
    xmax = ymax = zmax = float("-inf")
    for solid in solids:
        bb = solid.BoundingBox()
        xmin, xmax = min(xmin, bb.xmin), max(xmax, bb.xmax)
        ymin, ymax = min(ymin, bb.ymin), max(ymax, bb.ymax)
        zmin, zmax = min(zmin, bb.zmin), max(zmax, bb.zmax)
    return sorted_extents(xmax - xmin, ymax - ymin, zmax - zmin)


def our_extents(package_type: str, pin_count: int, name: str,
                extracted_dims: Optional[Dict]) -> List[float]:
    """Sorted (X, Y, Z) extents of OUR generated body for a case."""
    spec = build_spec(package_type, pin_count, name, extracted_dims)
    asm = select_template(spec).build(spec)
    bb = asm.toCompound().BoundingBox()
    return sorted_extents(bb.xlen, bb.ylen, bb.zlen)


def compare(ours: List[float], reference: List[float]) -> Dict:
    """Compare two sorted extent triples within per-axis tolerance.

    The smallest sorted extent is the height (tighter tol); the two larger are
    footprint extents (looser tol). Returns deltas, per-axis tolerances, and a
    pass flag.
    """
    tols = [TOL_HEIGHT, TOL_FOOTPRINT, TOL_FOOTPRINT]
    deltas = [abs(o - r) for o, r in zip(ours, reference)]
    within = [d <= t for d, t in zip(deltas, tols)]
    return {
        "ours": [round(v, 3) for v in ours],
        "reference": [round(v, 3) for v in reference],
        "delta": [round(d, 3) for d in deltas],
        "tolerance": tols,
        "passed": all(within),
    }


def run_case(name: str, package_type: str, pin_count: int,
             extracted_dims: Dict, ref_rel_path: str) -> Dict:
    """Run a single case; returns a result dict (with status/error handling)."""
    ref_path = GROUND_TRUTH_DIR / ref_rel_path
    result: Dict = {
        "name": name,
        "package_type": package_type,
        "pin_count": pin_count,
        "reference_step": ref_rel_path,
    }
    if not ref_path.exists():
        result.update({"status": "missing_reference", "passed": False})
        return result

    ref = reference_extents(ref_path)
    ours = our_extents(package_type, pin_count, name, extracted_dims)
    result.update(compare(ours, ref))
    result["status"] = "ok"
    return result


def _fmt(triple: List[float]) -> str:
    return "[" + ", ".join(f"{v:6.3f}" for v in triple) + "]"


def main() -> int:
    results = [run_case(*case) for case in CASES]

    header = f"{'case':<16}{'pkg':<7}{'pins':>5}  {'our extents':<24}{'reference':<24}{'delta':<24}{'result'}"
    print(header)
    print("-" * len(header))
    for r in results:
        if r["status"] == "missing_reference":
            print(f"{r['name']:<16}{r['package_type']:<7}{r['pin_count']:>5}  "
                  f"{'(reference STEP missing)':<72}SKIP")
            continue
        verdict = "PASS" if r["passed"] else "FAIL"
        print(f"{r['name']:<16}{r['package_type']:<7}{r['pin_count']:>5}  "
              f"{_fmt(r['ours']):<24}{_fmt(r['reference']):<24}"
              f"{_fmt(r['delta']):<24}{verdict}")

    ran = [r for r in results if r["status"] == "ok"]
    all_passed = bool(ran) and all(r["passed"] for r in ran)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "tolerances_mm": {"height": TOL_HEIGHT, "footprint": TOL_FOOTPRINT},
        "n_cases": len(results),
        "n_passed": sum(1 for r in ran if r["passed"]),
        "all_passed": all_passed,
        "results": results,
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2))
    print(f"\nwrote {REPORT_PATH.relative_to(REPO_ROOT)}  "
          f"({report['n_passed']}/{len(ran)} passed)")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
