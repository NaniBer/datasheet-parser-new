"""Ground-truth regression: our generated footprints vs official vendor footprints.

Each case pairs a datasheet PDF (run through the real pipeline) with an
official SnapEDA / UltraLibrarian .kicad_mod for the same package. We compare
the measurable contract of a footprint:

  - pin count and pin-number placement (per-pin position deltas, after
    converting KiCad's y-down convention to our y-up)
  - pitch and row spacing
  - drill diameter for through-hole packages
  - pad sizes (loose tolerance: vendors use different IPC density levels
    and toe/heel goals, so sizes legitimately differ by a few tenths)

Usage: python3 run_ground_truth_eval.py [report.json]
"""

import json
import re
import subprocess
import sys
from pathlib import Path

from pygltflib import GLTF2

OUT_DIR = Path("/tmp/ground_truth_eval")
REPORT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("ground_truth_report.json")

# (name, pdf, part_number hint or None, reference kicad_mod)
CASES = [
    ("TL072 SOIC-8", "pdfs/tl072.pdf", "TL072CDR",
     "TLO62CDR/SOIC127P600X175-8N.kicad_mod"),
    ("74HC595 narrow SOIC-16", "pdfs/74HC595_TI.pdf", "SN74HC595DR",
     "MM74HC594M/SOIC127P600X175-16N.kicad_mod"),
    ("ATmega328P DIP-28", "pdfs/ATmega328p.pdf", None,
     "ATMEGA328P-PU/DIP794W46P254L2967H457Q28B.kicad_mod"),
    ("MCP3208 PDIP-16", "pdfs/MCP3208.pdf", "MCP3208-CI/P",
     "MCP3208-CI_P/DIP254P762X432-16.kicad_mod"),
    ("74HC595A PDIP-16", "pdfs/MC74HC595A.PDF", None,
     "ul_74HC595/KiCADv6/footprints.pretty/DIP16_300_TEX.kicad_mod"),
]

# Tolerances (mm)
TOL_POSITION = 0.35   # pad-center placement varies between IPC density levels
TOL_PITCH = 0.05      # pitch is exact JEDEC data; no excuse for drift
TOL_DRILL = 0.35      # drill practice varies (0.85-1.2 for 0.46 DIP leads)
TOL_PAD_SIZE = 0.65   # toe/heel/side goals differ by vendor

PAD_RE = re.compile(
    r"\(pad\s+\"?(\w+)\"?\s+(thru_hole|smd)\s+\w+\s*"
    r"(?:\([^)]*\)\s*)*"  # optional groups like (roundrect_rratio 0.125)
    r"\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+[-\d.]+)?\)\s*"
    r"\(size\s+([-\d.]+)\s+([-\d.]+)\)"
    r"(?:.*?\(drill\s+([-\d.]+)\))?",
    re.DOTALL,
)


def parse_kicad_pads(path: Path) -> dict:
    pads = {}
    text = path.read_text(errors="ignore")
    for chunk in re.findall(r"\(pad\s.*?(?=\n\s*\(pad\s|\n\))", text, re.DOTALL):
        m = PAD_RE.match(chunk)
        if not m:
            continue
        num, kind, x, y, sx, sy, drill = m.groups()
        if not num.isdigit():
            continue
        pads[num] = {
            "kind": kind,
            # KiCad is y-down; our GLBs are y-up.
            "x": float(x), "y": -float(y),
            "size": (float(sx), float(sy)),
            "drill": float(drill) if drill else None,
        }
    return pads


def measure_our_glb(path: Path) -> dict:
    glb = GLTF2().load(str(path))
    pins = {}
    for n in glb.nodes:
        if n.extras and "pinData" in n.extras:
            pd = n.extras["pinData"]
            p = pd["position"]
            entry = {"x": p["x"], "y": p["y"]}
            # Through-hole pin 1 is a rect pad (pin-1 marking): classify by
            # the drill (innerDiameter), not by the pad-shape keys.
            if pd.get("innerDiameter") is not None:
                entry["kind"] = "thru_hole"
                entry["drill"] = pd.get("innerDiameter")
                od = pd.get("outerDiameter") or pd.get("length")
                entry["size"] = (od, od)
            else:
                entry["kind"] = "smd"
                entry["size"] = (pd.get("length"), pd.get("width"))
            pins[n.name] = entry
    return pins


def center_on_centroid(pads: dict) -> dict:
    """Vendors anchor footprints differently (origin vs pin 1); compare
    positions relative to the pad centroid."""
    if not pads:
        return pads
    cx = sum(p["x"] for p in pads.values()) / len(pads)
    cy = sum(p["y"] for p in pads.values()) / len(pads)
    return {num: {**p, "x": p["x"] - cx, "y": p["y"] - cy}
            for num, p in pads.items()}


def grid_metrics(pads: dict) -> dict:
    xs = sorted({round(p["x"], 3) for p in pads.values()})
    ys = sorted({round(p["y"], 3) for p in pads.values()})
    pitch = None
    col_ys = sorted(p["y"] for p in pads.values()
                    if round(p["x"], 3) == xs[0])
    if len(col_ys) > 1:
        pitch = round(col_ys[1] - col_ys[0], 3)
    return {"row_spacing": round(xs[-1] - xs[0], 3), "pitch": pitch,
            "ys_span": round(ys[-1] - ys[0], 3)}


def compare(ours: dict, ref: dict) -> dict:
    issues = []
    result = {"pin_count_ours": len(ours), "pin_count_ref": len(ref)}
    if set(ours) != set(ref):
        issues.append(f"pin sets differ: ours-only {sorted(set(ours)-set(ref))}, "
                      f"ref-only {sorted(set(ref)-set(ours))}")
        result["issues"] = issues
        result["ok"] = False
        return result

    gm_ours, gm_ref = grid_metrics(ours), grid_metrics(ref)
    result["grid_ours"], result["grid_ref"] = gm_ours, gm_ref
    if gm_ours["pitch"] and gm_ref["pitch"] and \
            abs(gm_ours["pitch"] - gm_ref["pitch"]) > TOL_PITCH:
        issues.append(f"pitch {gm_ours['pitch']} vs ref {gm_ref['pitch']}")
    if abs(gm_ours["row_spacing"] - gm_ref["row_spacing"]) > 2 * TOL_POSITION:
        issues.append(f"row spacing {gm_ours['row_spacing']} vs ref {gm_ref['row_spacing']}")

    # Per-pin placement: same pin number must land in the same spot.
    worst = ("", 0.0)
    for num in sorted(ours, key=int):
        dx = ours[num]["x"] - ref[num]["x"]
        dy = ours[num]["y"] - ref[num]["y"]
        d = (dx * dx + dy * dy) ** 0.5
        if d > worst[1]:
            worst = (num, d)
    result["worst_pin_delta"] = {"pin": worst[0], "mm": round(worst[1], 3)}
    if worst[1] > TOL_POSITION:
        issues.append(f"pin {worst[0]} is {worst[1]:.3f}mm from reference position")

    kinds_ours = {p["kind"] for p in ours.values()}
    kinds_ref = {p["kind"] for p in ref.values()}
    if kinds_ours != kinds_ref:
        issues.append(f"mount type {kinds_ours} vs ref {kinds_ref}")
    elif kinds_ref == {"thru_hole"}:
        d_ours = next(iter(ours.values()))["drill"]
        d_ref = next(iter(ref.values()))["drill"]
        result["drill_ours"], result["drill_ref"] = d_ours, d_ref
        if d_ours and d_ref and abs(d_ours - d_ref) > TOL_DRILL:
            issues.append(f"drill {d_ours} vs ref {d_ref}")

    so, sr = next(iter(ours.values()))["size"], next(iter(ref.values()))["size"]
    result["pad_size_ours"], result["pad_size_ref"] = so, sr
    if all(so) and all(sr):
        # compare axis-agnostically (length/width order differs)
        diff = max(abs(max(so) - max(sr)), abs(min(so) - min(sr)))
        result["pad_size_max_diff"] = round(diff, 3)
        if diff > TOL_PAD_SIZE:
            issues.append(f"pad size {so} vs ref {sr}")

    result["issues"] = issues
    result["ok"] = not issues
    return result


def main():
    OUT_DIR.mkdir(exist_ok=True)
    results = []
    for name, pdf, part, ref_mod in CASES:
        print(f"=== {name} ===", flush=True)
        stem = re.sub(r"\W+", "_", name)
        out = OUT_DIR / f"{stem}.glb"
        fp = OUT_DIR / f"{stem}_footprint.glb"
        cmd = [sys.executable, "-m", "src.main", pdf, str(out), "--both"]
        if part:
            cmd += ["--part-number", part]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        entry = {"case": name, "pdf": pdf, "part_number": part, "reference": ref_mod}
        rejected = ("Failed to generate footprint" in proc.stdout
                    or "Error generating footprint" in proc.stdout)
        if not fp.exists() or rejected:
            tail = [l for l in (proc.stdout + proc.stderr).splitlines() if l.strip()]
            entry.update({"status": "NO_FOOTPRINT", "error_tail": tail[-3:]})
        else:
            ours = center_on_centroid(measure_our_glb(fp))
            ref = center_on_centroid(parse_kicad_pads(Path(ref_mod)))
            entry.update(compare(ours, ref))
            entry["status"] = "MATCH" if entry["ok"] else "MISMATCH"
        results.append(entry)
        print(json.dumps(entry, default=str), flush=True)
        REPORT.write_text(json.dumps(results, indent=2, default=str))

    n_ok = sum(1 for r in results if r.get("status") == "MATCH")
    print(f"\n{n_ok}/{len(results)} footprints match official references")


if __name__ == "__main__":
    main()
