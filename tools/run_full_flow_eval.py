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
REPORT = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("eval_output/flow_eval_report.json")

# Part-number hints where the datasheet covers several variants.
PART_HINTS = {
    "74HC595_TI": "SN74HC595DWR",
    # The x in the filename is ST's wildcard (covers T6/C6/R6); pin the
    # eval to the 48-pin LQFP variant so extraction is deterministic.
    "STM32F103X6": "STM32F103C6",
}

# Fixtures that are not real component datasheets: clean failure = pass.
# The DigiKey bridge/diode parts have no pin-function table (pinout is a
# drawing or the part is 2-terminal), so refusing is the correct outcome;
# if extraction ever succeeds they are still graded via EXPECTED_PINS.
EXPECT_FAIL_OK = {
    "foo", "pages", "test",
    "2_CDBHM1100L-HF", "4_MB6S-E3-80", "8_MMBD3004CA-RFG",
    "18_HD06-T", "19_MB10F-13", "20_CDBU40-HF",
}

# Ground-truth pin counts per PDF stem. A footprint with a different pin
# count is a WRONG VARIANT, not a pass — grid-consistency checks alone
# cannot see this (STM32F103RBT7, a 64-pin part, once shipped a 100-pin
# footprint that measured perfectly consistent).
EXPECTED_PINS = {
    "74HC595_TI": 16, "ADXL345": 14, "AMS1117": 8, "ATmega328p": 28,
    "cd74hc4017": 16, "DFN": 8, "DS3231": 16, "DS_SX1261_2_V2-2": 24,
    "esp32-c3_datasheet_en": 32, "FT232R": 28, "INA219": 8, "L293D": 16,
    "lm358": 8, "MAX1487-MAX491": 8, "MAX202E": 16, "MC74HC595A": 16,
    "MCP3208": 16, "MPU-6000-Datasheet1": 24, "NE555": 8, "NRF24L01": 20,
    "PIC16F877A": 40, "STM32F103RBT7": 64, "STM32F103X6": 48,
    "tl072": 8, "TPS63060": 10, "TSSOP": 8, "ULN2001A-ULN2002A": 16,
    # DigiKey 20-part corpus (2026-07 batches), verified against the sheets.
    "1_LS7641-S": 14, "3_MB10S": 4, "4_MB6S-E3-80": 4,
    "5_SN6501QDBVRQ1": 5, "6_SN6505ADBVR": 6, "7_TPS2514DBVR": 6,
    "8_MMBD3004CA-RFG": 3, "9_BQ25570RGRT": 20, "10_BQ500211RGZR": 48,
    "11_BQ500511ARHAR": 40, "12_BQ51050BRHLR": 20, "13_MAX845EUA+": 8,
    "14_TPS23751PWP": 16, "15_SN65LVDS104PWR": 16, "16_TPS23751PWPR": 16,
    "17_DF10S": 4, "18_HD06-T": 4, "19_MB10F-13": 4,
}

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
        # Exit 3 = degraded: artifacts were produced but marked unvalidated
        # (e.g. --force-best-effort). Produced, so not a hard failure.
        "degraded": proc.returncode == 3,
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

    if ((proc.returncode not in (0, 3) or footprint_rejected) and not res["footprint"]
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
        expected = EXPECTED_PINS.get(stem)
        pin_count_ok = True
        for measured in (
            (res.get("geometry") or {}).get("pin_count"),
            sc_checks.get("pin_count"),
        ):
            if expected and measured and measured != expected:
                res["wrong_variant"] = f"expected {expected} pins, got {measured}"
                pin_count_ok = False
        res["status"] = "PASS" if (schematic_ok and pin_count_ok) else "FAIL"
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
