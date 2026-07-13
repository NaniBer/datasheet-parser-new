"""Batch end-to-end eval: every datasheet PDF -> schematic + footprint GLB.

For each PDF, runs `python3 -m src.main <pdf> <out> --both` and records:
  - exit status and whether each GLB was produced
  - extracted dims line (or JEDEC-defaults fallback)
  - footprint geometry measured from the GLB pinData extras:
    pin count, pad pitch, row spacing, column centering
Writes a JSON report + prints a summary table.

Deliberate expectations:
  - foo/pages/test are junk fixtures; failing cleanly is a PASS (fail-closed).
  - Module/exotic packages must fail closed, not emit a guessed footprint.
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

from pygltflib import GLTF2

PDF_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("pdfs")
OUT_DIR = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/tmp/flow_eval")
REPORT = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("flow_eval_report.json")

# Part-number hints where the datasheet covers several variants.
PART_HINTS = {
    "74HC595_TI": "SN74HC595DWR",
}

# Fixtures that are not real component datasheets: clean failure = pass.
EXPECT_FAIL_OK = {"foo", "pages", "test"}

# Grid-array parts: the correct outcome is a schematic plus a refused
# footprint (no real pad-grid support; perimeter geometry would be wrong).
EXPECT_NO_FOOTPRINT = {"ADXL345"}

DIMS_RE = re.compile(r"\[DimensionExtractor\] Extracted dims: (\{.*\})")


def measure_glb(path: Path) -> dict:
    glb = GLTF2().load(str(path))
    pos = {}
    for n in glb.nodes:
        if n.extras and "pinData" in n.extras:
            p = n.extras["pinData"]["position"]
            pos[n.name] = (p["x"], p["y"])
    out = {"pin_count": len(pos)}
    if len(pos) >= 4:
        xs = sorted({round(x, 3) for x, _ in pos.values()})
        ys = sorted({round(y, 3) for _, y in pos.values()})
        out["row_spacing"] = round(xs[-1] - xs[0], 3)
        out["pitch"] = round(ys[1] - ys[0], 3) if len(ys) > 1 else None
        out["y_centered"] = abs(max(y for _, y in pos.values())
                                + min(y for _, y in pos.values())) < 0.02
    return out


def measure_schematic(path: Path) -> dict:
    """Structural checks against the platform's reference schematic format."""
    glb = GLTF2().load(str(path))
    root = glb.nodes[glb.scenes[glb.scene or 0].nodes[0]]
    pins = [n for n in glb.nodes if "id" in (n.extras or {})]
    labels = {n.name: (n.extras or {}).get("value")
              for n in glb.nodes
              if "value" in (n.extras or {}) and "id" not in (n.extras or {})}
    out = {
        "pin_count": len(pins),
        "view_type_ok": (root.extras or {}).get("viewType") == "schematic",
        "all_pins_named": bool(pins) and all(p.extras.get("pinName") for p in pins),
        "sides": sorted({p.extras["side"] for p in pins}),
        "designator": labels.get("DesignatorName"),
        "component": labels.get("PackageValue"),
        "bodyline_points": any("points" in (n.extras or {}) for n in glb.nodes),
    }
    numbers = sorted(int(i) for p in pins for i in p.extras["id"])
    out["numbers_contiguous"] = numbers == list(range(1, len(numbers) + 1))
    return out


def run_one(pdf: Path) -> dict:
    stem = pdf.stem
    out = OUT_DIR / f"{stem}.glb"
    cmd = [sys.executable, "-m", "src.main", str(pdf), str(out), "--both"]
    hint = PART_HINTS.get(stem)
    if hint:
        cmd += ["--part-number", hint]

    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        return {"pdf": pdf.name, "status": "TIMEOUT", "seconds": 900}

    res = {
        "pdf": pdf.name,
        "seconds": round(time.time() - t0, 1),
        "exit_code": proc.returncode,
    }
    m = DIMS_RE.search(proc.stdout)
    res["extracted_dims"] = json.loads(m.group(1).replace("'", '"')) if m else None

    fp = OUT_DIR / f"{stem}_footprint.glb"
    sc = OUT_DIR / f"{stem}_schematic.glb"
    res["schematic"] = sc.exists()
    # A leftover GLB from a run whose hierarchy validation failed is not a
    # success (found via TPS63060: invalid file written before validation).
    footprint_rejected = "Failed to generate footprint" in proc.stdout
    res["footprint"] = fp.exists() and not footprint_rejected
    if footprint_rejected:
        res["footprint_rejected"] = True

    if res["footprint"]:
        try:
            res["geometry"] = measure_glb(fp)
        except Exception as exc:
            res["geometry_error"] = str(exc)

    if res["schematic"]:
        try:
            res["schematic_checks"] = measure_schematic(sc)
        except Exception as exc:
            res["schematic_error"] = str(exc)

    footprint_refused_ok = (
        stem in EXPECT_NO_FOOTPRINT and not res["footprint"] and res["schematic"]
    )
    if footprint_refused_ok:
        res["footprint_refused_expected"] = True

    if ((proc.returncode != 0 or footprint_rejected) and not res["footprint"]
            and not footprint_refused_ok):
        # last non-warning stderr/stdout lines for diagnosis
        tail = [l for l in (proc.stdout + proc.stderr).splitlines() if l.strip()]
        res["error_tail"] = tail[-4:]
        res["status"] = "FAIL_OK" if stem in EXPECT_FAIL_OK else "FAIL"
    else:
        sc_checks = res.get("schematic_checks") or {}
        schematic_ok = res["schematic"] and all(
            sc_checks.get(k) for k in
            ("view_type_ok", "all_pins_named", "numbers_contiguous", "bodyline_points")
        )
        res["status"] = "PASS" if schematic_ok else "FAIL"
    return res


def main():
    OUT_DIR.mkdir(exist_ok=True)
    pdfs = sorted(
        list(PDF_DIR.glob("*.pdf")) + list(PDF_DIR.glob("*.PDF")),
        key=lambda p: p.name.lower(),
    )
    results = []
    for pdf in pdfs:
        print(f"=== {pdf.name} ===", flush=True)
        r = run_one(pdf)
        results.append(r)
        print(json.dumps(r, indent=None), flush=True)
        REPORT.write_text(json.dumps(results, indent=2))

    n_pass = sum(1 for r in results if r["status"] == "PASS")
    n_ok_fail = sum(1 for r in results if r["status"] == "FAIL_OK")
    print(f"\n{n_pass} PASS, {n_ok_fail} expected-fail OK, "
          f"{len(results) - n_pass - n_ok_fail} FAIL of {len(results)}")


if __name__ == "__main__":
    main()
