"""Batch end-to-end eval: every datasheet PDF -> schematic + footprint GLB.

For each PDF, runs `python3 -m src.main <pdf> <out> --both` and records:
  - exit status and whether each GLB was produced
  - extracted dims line (or JEDEC-defaults fallback)
  - footprint geometry measured from the GLB pinData extras:
    pin count, pad pitch, row spacing, column centering
Writes a JSON report + prints a summary table.

Before running, a corpus-intake step (Fix 11) validates the inputs: it groups
byte-identical PDFs by MD5 (scoring/running only one copy per group) and flags
documents that are not component datasheets (tutorials / user guides /
reference designs / demo-board guides / application notes) so they are excluded
from scoring. Both heuristics are generalizable and touch only this harness.

Deliberate expectations:
  - foo/pages/test are junk fixtures; failing cleanly is a PASS (fail-closed).
  - Module/exotic packages must fail closed, not emit a guessed footprint.
"""

import hashlib
import json
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

from pygltflib import GLTF2

try:
    import fitz  # PyMuPDF; used only for the first-page intake heuristic.
except ImportError:  # pragma: no cover - fitz is a hard dep elsewhere
    fitz = None

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
    # --- pdfs/ regression fixtures (pre-corpus) ---
    "74HC595_TI": 16, "ADXL345": 14, "AMS1117": 8, "ATmega328p": 28, "cd74hc4017": 16,
    "DFN": 8, "DS3231": 16, "DS_SX1261_2_V2-2": 24, "esp32-c3_datasheet_en": 32,
    "FT232R": 28, "INA219": 8, "L293D": 16, "lm358": 8, "MAX1487-MAX491": 8,
    "MAX202E": 16, "MC74HC595A": 16, "MCP3208": 16, "MPU-6000-Datasheet1": 24,
    "NE555": 8, "NRF24L01": 20, "PIC16F877A": 40, "STM32F103RBT7": 64,
    "STM32F103X6": 48, "tl072": 8, "TPS63060": 10, "TSSOP": 8, "ULN2001A-ULN2002A": 16,
    # --- datasheets/ corpus: full ground truth, verified 2026-07-29 from
    #     each datasheet's package/ordering section + ordered part-number
    #     suffix (5-way parallel cross-check; thermal/EP pads excluded).
    #     142_1982/143_1982 omitted: Adafruit tutorials, not datasheets.
    "1_LS7641-S": 14, "2_CDBHM1100L-HF": 4, "3_MB10S": 4, "4_MB6S-E3-80": 4,
    "5_SN6501QDBVRQ1": 5, "6_SN6505ADBVR": 6, "7_TPS2514DBVR": 6, "8_MMBD3004CA-RFG": 3,
    "9_BQ25570RGRT": 20, "10_BQ500211RGZR": 48, "11_BQ500511ARHAR": 40,
    "12_BQ51050BRHLR": 20, "13_MAX845EUA+": 8, "14_TPS23751PWP": 16, "15_SN65LVDS104PWR": 16,
    "16_TPS23751PWPR": 16, "17_DF10S": 4, "18_HD06-T": 4, "19_MB10F-13": 4,
    "20_CDBU40-HF": 2, "21_ATTINY13A-MMU": 10, "22_MAX5969BETB+T": 10,
    "23_NCP4308DMTTWG": 8, "24_UCC24610DRBT": 8, "25_B40C800DM-E3-45": 4,
    "26_B80C800DM-E3-45": 4, "27_DB102-BP": 4, "28_DB107-BP": 4, "29_AVR128DA48-I-PT": 48,
    "30_dsPIC33FJ128MC204-I-PT": 44, "31_dsPIC33FJ128MC710A-I-PF": 100,
    "32_dsPIC33FJ256MC710A-I-PF": 100, "33_INA234AIYBJR": 8, "34_MKL17Z256CAL4R": 36,
    "35_MKL43Z256VMP4": 64, "36_MKL46Z256VMC4": 121, "37_ESP32-WROOM-32D-N16": 38,
    "38_ESP32C3WROOM02H4": 19, "39_MAX-M10S-00B": 18, "40_CAM-M8Q-0": 31,
    "41_SN6507DGQR": 10, "42_INA228AIDGSR": 10, "43_INA238AIDGSR": 10,
    "44_TPS51100DGQ": 10, "45_NCP5623BMUTBG": 12, "46_LSM6DSO32TR": 14,
    "47_NRF9160-SICA": 127, "48_NRF9160-SICA": 127, "49_ADT7516ARQZ-REEL7": 16,
    "50_ADT7470ARQZ-REEL7": 16, "51_AMC6821SDBQR": 16, "52_PIC16F1512-I-SS": 28,
    "53_MBR1535CTG": 3, "54_STPS30M60ST": 3, "55_STTH8R06DIRG": 2, "56_BT136-600E-127": 3,
    "57_1N4001RLG": 2, "58_1N5408-E3-54": 2, "59_MBRA140T3G": 2, "60_SS14": 2,
    "61_X0202NN-5BA4": 3, "62_Z0103NN5AA4": 3, "63_Z0107MN-5AA4": 4, "64_Z0109MN-6AA4": 3,
    "65_STPS20L60CG-TR": 3, "66_STTH2003CG-TR": 3, "67_MBRB60H100CTT4G": 3,
    "68_LM2673S-5.0-NOPB": 7, "69_AD536AKH": 10, "70_AD636JHZ": 10, "71_AD537JH": 10,
    "72_AD537KH": 10, "73_GBU6K-E3-45": 4, "74_GBJ2506-F": 4, "75_GBU4M-E3-51": 4,
    "76_GBU8D-E3-45": 4, "77_MC34064P-5G": 3, "78_MCP100-450DI-TO": 3,
    "79_MCP101-450DI-TO": 3, "80_MCP101-460DI-TO": 3, "81_1N4148W-E3-08": 2,
    "82_BAT48ZFILM": 2, "83_BAV21W-7-F": 2, "84_BYD17G,115": 2, "85_IS82C59AZX96": 28,
    "86_PIC16F871-I-L": 44, "87_NOIP1SE1300A-QTI": 48, "88_NOIP1SN1300A-QTI": 48,
    "89_ACS758LCB-050B-PFF-T": 5, "90_ACS758LCB-050U-PFF-T": 5, "91_ACS758LCB-050B-PFF-T": 5,
    "92_ACS773LCB-100B-PFF-T": 5, "93_BAS4002ARPPE6327HTSA1": 4, "94_CAT811LTBI-GT3": 4,
    "95_CAT811MTBI-GT3": 4, "96_CAT811STBI-GT3": 4, "97_C3D16060D": 3,
    "98_C3D16065D1": 3, "99_C3D20060D": 3, "100_C3D30065D": 3, "101_L78L33ABUTR": 3,
    "102_MCP1700T-3002E-MB": 3, "103_L78L05ABUTR": 3, "104_L78L10ACUTR": 3,
    "105_PB86-BP": 4, "106_VS-KBPC102": 4, "107_VS-KBPC104": 4, "108_VS-KBPC6005PBF": 4,
    "109_PMEG030V030EPDZ": 3, "110_PMEG045V100EPDAZ": 3, "111_PMEG060V050EPDZ": 3,
    "112_PMEG100V080ELPDZ": 3, "113_IKCM30F60GDXKMA1": 24, "114_SQJ974EP-T1_GE3": 8,
    "115_AL5809-15P1-7": 2, "116_AL5809-100P1-7": 2, "117_BD135": 3, "118_BD137G": 3,
    "119_BD441G": 3, "120_MJE13003G": 3, "121_BSD840NH6327XTSA1": 6, "122_BSD235CH6327XTSA1": 6,
    "123_L4984D": 10, "124_L6564TDTR": 10, "125_ADXRS645HDYZ": 15, "126_ADXRS645HDYZ": 15,
    "127_ADXRS645HDYZ": 15, "128_MJL3281AG": 3, "129_MJL21193G": 3, "130_BD9778HFP-TR": 7,
    "131_BD9781HFP-TR": 7, "132_ABS25-32.768KHZ-T": 2, "133_MA-506-4.0000M-D0_ROHS": 2,
    "134_XC6218P332HR-G": 3, "135_SFH-3219-Z": 2, "136_TDA7850": 25, "137_0ZCM0003FF2G": 2,
    "138_0ZCM0005FF2G": 2, "139_TPS2378DDA": 8, "140_TPS2378DDAR": 8, "141_UC200AGLAA-N06-TA0AA": 112,
    "144_MAXREFDES117#": 8, "145_LPS4018-223MRB": 2, "146_W25Q128JVSIM_TR": 8,
    "147_LPS4018-103MLB": 2, "148_STM32L031E4Yx": 25, "BQ25570RGRR": 20,
}

# Grid-array parts: the correct outcome is a schematic plus a refused
# footprint (no real pad-grid support; perimeter geometry would be wrong).
EXPECT_NO_FOOTPRINT = {"ADXL345"}

DIMS_RE = re.compile(r"\[DimensionExtractor\] Extracted dims: (\{.*\})")


# --------------------------------------------------------------------------
# Corpus-intake validation (Fix 11).
#
# Two generalizable, corpus-agnostic heuristics that run *before* scoring:
#   1. MD5 byte-duplicate grouping so shared family sheets are not scored
#      (and re-run) once per identical copy.
#   2. A conservative first-page document-type detector that flags docs that
#      are clearly NOT component datasheets (tutorials / user guides /
#      reference designs / demo-board guides / application notes) so they do
#      not skew pass/fail counts.
# Neither touches the parser; both use only file bytes and first-page text.
# --------------------------------------------------------------------------

# Phrases that, when they appear near the *top* of the first page (the title
# block), indicate the document is not a component datasheet. Kept as coarse
# categories so the report reads clearly. These are matched against the title
# region only, and are overridden when the page carries strong datasheet
# structure (see DATASHEET_MARKERS) -- so a real datasheet that merely mentions
# an "evaluation board" in its body is never excluded.
NON_DATASHEET_SIGNALS = [
    ("getting-started", [r"getting\s+started", r"quick\s*start"]),
    ("user-guide", [r"user'?s?\s+guide", r"user'?s?\s+manual",
                    r"owner'?s?\s+manual", r"instruction\s+manual"]),
    ("tutorial", [r"tutorial", r"how[-\s]to\s+guide", r"step[-\s]by[-\s]step"]),
    # NB: "reference design" was removed as a signal -- vendors (notably TI)
    # print it as a boilerplate header/navigation link ("Product Folder | Order
    # Now | ... | Reference Design") on ordinary chip datasheets, so it wrongly
    # excluded 4 real datasheets (7_TPS2514, 14_TPS23751, 24_UCC24610,
    # 139_TPS2378). Same header-chrome trap avoided in module_detector. A
    # genuine reference-design doc that merely runs and refuses is far cheaper
    # than dropping a real datasheet from scoring. "design guide" is retained.
    ("reference-design", [r"design\s+guide"]),
    ("reference-manual", [r"reference\s+manual"]),
    ("demo-board", [r"demo(?:nstration)?\s+board", r"demo(?:nstration)?\s+kit",
                    r"evaluation\s+board", r"evaluation\s+kit",
                    r"evaluation\s+module", r"development\s+board",
                    r"development\s+kit", r"starter\s+kit"]),
    ("application-note", [r"application\s+note", r"application\s+report"]),
]

# Structural section headings that only a real datasheet carries. Two or more
# distinct hits on the first page mean "this is a datasheet" and veto any
# non-datasheet signal, keeping the flagger conservative.
DATASHEET_MARKERS = [
    r"absolute\s+maximum\s+ratings",
    r"electrical\s+characteristics",
    r"recommended\s+operating\s+conditions",
    r"pin\s+configuration",
    r"pin\s+description",
    r"pin\s+function",
    r"ordering\s+information",
    r"thermal\s+information",
    r"functional\s+block\s+diagram",
]

# How much of the first page counts as the "title region" for signal matching.
_TITLE_REGION_CHARS = 800


def file_md5(path: Path) -> str:
    """MD5 of the raw file bytes (streamed, so large PDFs are fine)."""
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def group_by_md5(paths) -> dict:
    """Map md5 -> sorted list of file names sharing those exact bytes."""
    groups = defaultdict(list)
    for p in paths:
        groups[file_md5(Path(p))].append(Path(p).name)
    return {digest: sorted(names) for digest, names in groups.items()}


def first_page_text(path: Path) -> str:
    """Text of the first page only (empty string if PyMuPDF is unavailable)."""
    if fitz is None:  # pragma: no cover
        return ""
    doc = fitz.open(str(path))
    try:
        return doc[0].get_text() if len(doc) else ""
    finally:
        doc.close()


def classify_non_datasheet(text: str) -> Optional[dict]:
    """Conservative document-type flagger.

    Returns ``{"doc_type": <category>, "signal": <matched phrase>}`` when the
    first-page text looks like a non-datasheet document, else ``None``.

    Rules (deliberately biased toward *not* flagging real datasheets):
      * A non-datasheet signal must appear in the title region (first ~800
        chars), not merely somewhere in the body.
      * Two or more distinct datasheet structural markers anywhere on the
        first page veto the flag -- such a page is a datasheet even if its
        title mentions, say, an evaluation board.
    """
    if not text or not text.strip():
        return None
    lowered = text.lower()
    title = lowered[:_TITLE_REGION_CHARS]

    hit = None
    for doc_type, patterns in NON_DATASHEET_SIGNALS:
        for pat in patterns:
            m = re.search(pat, title)
            if m:
                hit = {"doc_type": doc_type, "signal": m.group(0)}
                break
        if hit:
            break
    if hit is None:
        return None

    markers = {p for p in DATASHEET_MARKERS if re.search(p, lowered)}
    if len(markers) >= 2:
        return None
    return hit


def build_intake(paths) -> dict:
    """Precompute the intake section: duplicate groups + per-file flags.

    Returns a dict with:
      * ``duplicate_groups``  -- list of {md5, files, canonical} for groups
        with >1 byte-identical member.
      * ``non_datasheets``    -- list of {pdf, doc_type, signal}.
      * ``skip``              -- {name: reason} for files excluded from scoring
        (duplicates after the first, and flagged non-datasheets).
    """
    paths = [Path(p) for p in paths]
    md5_groups = group_by_md5(paths)

    duplicate_groups = []
    skip = {}
    for digest, names in sorted(md5_groups.items()):
        if len(names) < 2:
            continue
        canonical = names[0]  # sorted; first name is the one we score/run
        duplicate_groups.append(
            {"md5": digest, "files": names, "canonical": canonical}
        )
        for dup in names[1:]:
            skip[dup] = {"status": "DUP_SKIPPED", "duplicate_of": canonical,
                         "md5": digest}

    non_datasheets = []
    for p in paths:
        p = Path(p)
        if p.name in skip:
            continue  # already covered as a duplicate; classify the canonical
        try:
            flag = classify_non_datasheet(first_page_text(p))
        except Exception as exc:  # pragma: no cover - never let intake crash a run
            flag = None
            print(f"[intake] first-page read failed for {p.name}: {exc}",
                  flush=True)
        if flag:
            non_datasheets.append({"pdf": p.name, **flag})
            skip[p.name] = {"status": "EXCLUDED_NON_DATASHEET", **flag}

    return {
        "total_inputs": len(list(paths)),
        "md5_groups": md5_groups,
        "duplicate_groups": duplicate_groups,
        "non_datasheets": non_datasheets,
        "skip": skip,
    }


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


def print_intake_summary(intake: dict) -> None:
    """Console summary of the intake step (before the per-PDF runs)."""
    print("=== corpus intake ===", flush=True)
    dups = intake["duplicate_groups"]
    if dups:
        n_extra = sum(len(g["files"]) - 1 for g in dups)
        print(f"[intake] {len(dups)} byte-duplicate group(s), "
              f"{n_extra} redundant copy(ies) will be skipped:", flush=True)
        for g in dups:
            others = ", ".join(f for f in g["files"] if f != g["canonical"])
            print(f"  md5 {g['md5'][:12]}  keep {g['canonical']}  "
                  f"dup: {others}", flush=True)
    else:
        print("[intake] no byte-duplicate PDFs", flush=True)

    nds = intake["non_datasheets"]
    if nds:
        print(f"[intake] {len(nds)} non-datasheet doc(s) excluded from scoring:",
              flush=True)
        for d in nds:
            print(f"  {d['pdf']}  ->  {d['doc_type']} "
                  f"(matched '{d['signal']}')", flush=True)
    else:
        print("[intake] no non-datasheet documents flagged", flush=True)
    print(flush=True)


def main():
    OUT_DIR.mkdir(exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(
        list(PDF_DIR.glob("*.pdf")) + list(PDF_DIR.glob("*.PDF")),
        key=lambda p: p.name.lower(),
    )

    # --- Fix 11: corpus-intake validation (additive; runs before scoring) ---
    intake = build_intake(pdfs)
    print_intake_summary(intake)
    skip = intake["skip"]

    results = []
    for pdf in pdfs:
        reason = skip.get(pdf.name)
        if reason:
            # Byte-duplicate copy or flagged non-datasheet: report but do not
            # run (saves LLM calls) and exclude from PASS/FAIL scoring.
            r = {"pdf": pdf.name, **reason, "scored": False}
            results.append(r)
            print(f"=== {pdf.name} (skipped: {reason['status']}) ===",
                  flush=True)
            print(json.dumps(r, indent=None), flush=True)
            _write_report(intake, results)
            continue
        print(f"=== {pdf.name} ===", flush=True)
        r = run_one(pdf)
        r["scored"] = True
        results.append(r)
        print(json.dumps(r, indent=None), flush=True)
        _write_report(intake, results)

    scored = [r for r in results if r.get("scored")]
    n_pass = sum(1 for r in scored if r["status"] == "PASS")
    n_ok_fail = sum(1 for r in scored if r["status"] == "FAIL_OK")
    n_dup = sum(1 for r in results if r.get("status") == "DUP_SKIPPED")
    n_nds = sum(1 for r in results if r.get("status") == "EXCLUDED_NON_DATASHEET")
    print(f"\n{n_pass} PASS, {n_ok_fail} expected-fail OK, "
          f"{len(scored) - n_pass - n_ok_fail} FAIL of {len(scored)} scored "
          f"({n_dup} duplicate, {n_nds} non-datasheet excluded; "
          f"{len(results)} inputs total)")


def _write_report(intake: dict, results: list) -> None:
    """Persist the report.

    Existing consumers read the per-PDF result dicts; those are unchanged and
    still available under ``results``. The additive intake section lives under
    ``intake``. Kept as a dict wrapper so the new data is co-located with the
    runs it explains.
    """
    REPORT.write_text(json.dumps({"intake": intake, "results": results},
                                 indent=2))


if __name__ == "__main__":
    main()
