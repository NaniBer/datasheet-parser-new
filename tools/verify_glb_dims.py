"""
Verify that extracted dimensions actually land in the exported GLB geometry.

Builds a SOIC-16 footprint twice (JEDEC defaults vs. 74HC595 extracted dims),
loads each GLB with trimesh, and measures:
  - pad pitch (Y spacing within a column)  -> expected e
  - pad row span (X between column centers) -> expected E - L (IPC-7351 inset)
  - pad size (X x Y)                        -> expected L x b
  - fab outline extents                     -> expected E x D
Usage: python3 -u verify_glb_dims.py
"""
import sys
import numpy as np
import trimesh

sys.path.insert(0, ".")

from src.schematic_generator.pcb_footprint_builder import build_pcb_footprint

PIN_DATA = [{"number": i, "name": f"P{i}"} for i in range(1, 17)]

# Midpoints of the SOIC-16 entry in pdfs/74HC595_TI_dimensions.json (page 23)
EXTRACTED = {"e": 1.27, "E": 10.325, "D": 9.90, "b": 0.41, "L": 0.835}


def measure(glb_path):
    scene = trimesh.load(glb_path)
    pads = {}   # node name -> world-space bounds of pad-ish geometry
    others = {}
    for node in scene.graph.nodes_geometry:
        T, geom_name = scene.graph[node]
        geom = scene.geometry[geom_name]
        g = geom.copy()
        g.apply_transform(T)
        lo, hi = g.bounds
        entry = dict(center=((lo + hi) / 2), size=(hi - lo), node=node)
        if "pad" in node.lower() or "pin" in node.lower():
            pads[node] = entry
        else:
            others[node] = entry
    return pads, others, scene


def report(tag, glb_path, expect):
    pads, others, scene = measure(glb_path)
    print(f"\n=== {tag} ({glb_path}) ===")
    print(f"nodes with geometry: {len(pads) + len(others)} "
          f"({len(pads)} pad/pin-named, {len(others)} other)")

    if not pads:
        print("No pad-named nodes found; node names present:")
        for n in list(others)[:40]:
            print("  ", n)
        return

    centers = np.array([p["center"] for p in pads.values()])
    sizes = np.array([p["size"] for p in pads.values()])

    xs = centers[:, 0]
    left = centers[xs < 0]
    right = centers[xs > 0]

    # pitch: sorted Y spacing within the left column
    ys = np.sort(left[:, 1])
    pitches = np.diff(ys)
    pitch = float(np.median(pitches)) if len(pitches) else float("nan")

    row_span = float(np.median(right[:, 0]) - np.median(left[:, 0])) if len(left) and len(right) else float("nan")

    pad_x = float(np.median(sizes[:, 0]))
    pad_y = float(np.median(sizes[:, 1]))

    # fab outline from "other" nodes named BodyLine (union of bounds)
    body_nodes = [v for k, v in others.items() if "bodyline" in k.lower() or "body" in k.lower()]
    if body_nodes:
        los = np.array([v["center"] - v["size"] / 2 for v in body_nodes])
        his = np.array([v["center"] + v["size"] / 2 for v in body_nodes])
        body_ext = his.max(axis=0) - los.min(axis=0)
    else:
        body_ext = [float("nan")] * 3

    def line(label, got, want):
        ok = "OK " if (want is not None and abs(got - want) < 0.02) else ("?  " if want is None else "DIFF")
        print(f"  {label:<28} measured={got:8.3f}  expected={want if want is not None else '  n/a'}   {ok}")

    line("pad pitch (e)", pitch, expect.get("e"))
    line("pad row span (E - L)", row_span, expect.get("row_span"))
    line("pad size X (L)", pad_x, expect.get("L"))
    line("pad size Y (b)", pad_y, expect.get("b"))
    line("body outline X (E?)", float(body_ext[0]), expect.get("E"))
    line("body outline Y (D?)", float(body_ext[1]), expect.get("D"))


# 1. Defaults only (JEDEC table)
ok = build_pcb_footprint("SOIC-16", 16, "TEST", PIN_DATA, "/tmp/soic16_default.glb")
print("build default:", ok)

# 2. With extracted dims
ok = build_pcb_footprint("SOIC-16", 16, "TEST", PIN_DATA, "/tmp/soic16_extracted.glb",
                         extracted_dims=EXTRACTED)
print("build extracted:", ok)

report("JEDEC defaults", "/tmp/soic16_default.glb", {})
report(
    "74HC595 extracted dims", "/tmp/soic16_extracted.glb",
    {
        "e": EXTRACTED["e"],
        "row_span": EXTRACTED["E"] - EXTRACTED["L"],
        "L": EXTRACTED["L"],
        "b": EXTRACTED["b"],
        "E": EXTRACTED["E"],
        "D": EXTRACTED["D"],
    },
)
