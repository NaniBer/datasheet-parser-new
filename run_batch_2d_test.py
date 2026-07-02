"""
Batch 2d PCB footprint test: generate + analyze one at a time.
"""
import subprocess
import json
import struct
import os
import sys

try:
    import pygltflib
except ImportError:
    print("pygltflib not found")
    sys.exit(1)

COMPONENTS = [
    ("NE555",      "pdfs/NE555.PDF"),
    ("74HC595",    "pdfs/74HC595_TI.pdf"),
    ("ADXL345",    "pdfs/ADXL345.PDF"),
    ("AMS1117",    "pdfs/AMS1117.pdf"),
    ("ATmega328p", "pdfs/ATmega328p.pdf"),
    ("CD4017",     "pdfs/cd74hc4017.pdf"),
    ("DS3231",     "pdfs/DS3231.PDF"),
    ("ESP32-C3",   "pdfs/esp32-c3_datasheet_en.pdf"),
    ("FT232R",     "pdfs/FT232R.pdf"),
    ("INA219",     "pdfs/INA219.PDF"),
    ("LM358",      "pdfs/lm358.pdf"),
    ("MAX202E",    "pdfs/MAX202E.PDF"),
    ("MCP3208",    "pdfs/MCP3208.pdf"),
    ("MPU-6000",   "pdfs/MPU-6000-Datasheet1.pdf"),
    ("nRF24L01",   "pdfs/NRF24L01.PDF"),
    ("PIC16F877A", "pdfs/PIC16F877A.PDF"),
    ("STM32F103",  "pdfs/STM32F103RBT7.PDF"),
    ("TL072",      "pdfs/tl072.pdf"),
    ("ULN2003A",   "pdfs/ULN2001A-ULN2002A.PDF"),
]

OUT_DIR = "output/batch_pcb2d_test"
REPORT = []


def analyze_glb(path, component):
    glb = pygltflib.GLTF2().load(path)
    nodes = glb.nodes

    # Pin nodes: named as integers
    pin_nodes = [n for n in nodes if (n.name or "").lstrip('-').isdigit()]
    pin_nums = sorted(set(int(n.name) for n in pin_nodes), key=int)

    # Pin name from extras
    pin_info = {}
    for node in nodes:
        name = node.name or ""
        if name.lstrip('-').isdigit():
            extras = node.extras or {}
            pin_name = extras.get("pinName") or extras.get("pin_name") or extras.get("name") or ""
            pin_info[int(name)] = pin_name

    # Body lines
    bodylines = [n for n in nodes if "BodyLine" in (n.name or "")]

    # Package type from any extras
    pkg_type = None
    for node in nodes:
        extras = node.extras or {}
        pkg_type = extras.get("packageType") or extras.get("package_type")
        if pkg_type:
            break

    # BodyLine layer extents
    layer_extents = {}
    for node in nodes:
        if "BodyLine" not in (node.name or ""):
            continue
        extras = node.extras or {}
        pts = extras.get("points") or []
        layer = extras.get("layer", "")
        if pts and len(pts) >= 2:
            xs = [p["x"] for p in pts]
            ys = [p["y"] for p in pts]
            key = f"x=[{round(min(xs),3)},{round(max(xs),3)}] y=[{round(min(ys),3)},{round(max(ys),3)}]"
            layer_extents[key] = layer_extents.get(key, 0) + 1

    return {
        "component": component,
        "file": path,
        "file_size_kb": round(os.path.getsize(path) / 1024, 1),
        "total_nodes": len(nodes),
        "pin_count": len(pin_nums),
        "pin_range": f"{min(pin_nums)}-{max(pin_nums)}" if pin_nums else "none",
        "missing_pins": [i for i in range(1, max(pin_nums)+1) if i not in pin_nums] if pin_nums else [],
        "pin_names": pin_info,
        "bodyline_count": len(bodylines),
        "package_type": pkg_type,
        "layer_extents": layer_extents,
    }


def print_result(r):
    ok = "OK" if not r.get("error") and not r.get("missing_pins") else "WARN"
    if r.get("error"):
        ok = "FAIL"

    print(f"\n{'='*60}")
    print(f"[{ok}] {r['component']}")
    print(f"{'='*60}")

    if r.get("error"):
        print(f"  ERROR: {r['error']}")
        return

    print(f"  File size : {r['file_size_kb']} KB")
    print(f"  Nodes     : {r['total_nodes']}")
    print(f"  Pins      : {r['pin_count']}  (range {r['pin_range']})")
    if r["missing_pins"]:
        print(f"  MISSING   : {r['missing_pins']}")
    print(f"  BodyLines : {r['bodyline_count']}")
    if r["package_type"]:
        print(f"  Package   : {r['package_type']}")

    if r["pin_names"]:
        named = {k: v for k, v in r["pin_names"].items() if v}
        if named:
            print(f"  Pin names ({len(named)}/{r['pin_count']} named):")
            for pnum in sorted(named):
                print(f"    pin {pnum:>3}: {named[pnum]}")
        else:
            print(f"  Pin names: (none in extras)")

    if r["layer_extents"]:
        print(f"  Layer extents:")
        for ext, count in r["layer_extents"].items():
            print(f"    {ext}  x{count}")

    sys.stdout.flush()


for component, pdf in COMPONENTS:
    out_path = os.path.join(OUT_DIR, f"{component}_2d.glb")
    print(f"\n>>> Generating {component} from {pdf} ...", flush=True)

    result = {"component": component}

    # Run generation
    proc = subprocess.run(
        ["python3", "-m", "src.main", pdf, out_path, "--pcb-2d"],
        capture_output=True, text=True, timeout=300
    )

    if proc.returncode != 0 or not os.path.exists(out_path):
        result["error"] = (proc.stderr or proc.stdout or "unknown error").strip()[-300:]
        print_result(result)
        REPORT.append(result)
        continue

    # Analyze
    try:
        result.update(analyze_glb(out_path, component))
    except Exception as e:
        result["error"] = f"Analysis failed: {e}"

    print_result(result)
    REPORT.append(result)

# Summary
print(f"\n\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
print(f"{'Component':<15} {'Pins':>6} {'BodyLines':>10} {'Named':>8} {'Status':>8}")
print("-"*55)
for r in REPORT:
    if r.get("error"):
        print(f"{r['component']:<15} {'--':>6} {'--':>10} {'--':>8} {'FAIL':>8}")
    else:
        named = len({k: v for k, v in r.get("pin_names", {}).items() if v})
        status = "WARN" if r.get("missing_pins") else "OK"
        print(f"{r['component']:<15} {r['pin_count']:>6} {r['bodyline_count']:>10} {named:>8} {status:>8}")
