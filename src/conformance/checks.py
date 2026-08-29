"""Concrete conformance checks.

Each check inspects a part's generated artifacts and returns an ``_Outcome``
(status + measured value + message). The runner wraps that with the rule's
identity. Checks read the GLBs the pipeline already emits — no re-generation —
so the harness can grade artifacts that already exist on disk.

Geometry note: glTF stores each mesh's local-space AABB in the POSITION
accessor's ``min``/``max``. We accumulate node transforms from the scene root to
put those boxes in world space (mm), then reason about clearance between
silkscreen and copper *in the board plane*. The exporter bakes a Z-up->Y-up
rotation on the root, so the flat footprint can lie in X-Z rather than X-Y; we
detect the board plane per-GLB as the two largest-extent axes and ignore the
thin (thickness) axis, so the check is orientation-agnostic. AABB clearance is
*conservative* — it can under-report the true gap for rotated/curved art, but it
never misses a genuine overlap, which is exactly the reported defect (silk drawn
across pads).
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from .model import CheckStatus

try:
    from pygltflib import GLTF2
except ImportError:  # pragma: no cover
    GLTF2 = None

# House rules (mm) — configurable process parameters per the spec footnote.
SILK_PAD_CLEARANCE_MM = 0.20   # FP-07
PAD_PAD_CLEARANCE_MM = 0.15    # FP-14
ANNULAR_RING_MIN_MM = 0.05     # FP-10 (IPC-2221 Class 2 external ring)
SCHEM_GRID_MM = 2.54           # SYM-02
GRID_TOL_MM = 0.05             # SYM-02 snap tolerance
CENTROID_TOL_MM = 0.10         # FP-03 origin vs body centroid
COURTYARD_TOL_MM = 0.05        # 3D-11 body envelope inside courtyard
SEATING_TOL_MM = 0.10          # 3D-02 seating plane
BODY_VERTICAL_AXIS = 1         # body GLB is Y-up (exporter bakes Z-up->Y-up)


@dataclass
class _Outcome:
    status: CheckStatus
    message: str = ""
    measured: Optional[str] = None
    threshold: Optional[str] = None


# ---------------------------------------------------------------------------
# Part context — lazily loads the artifacts a check needs.
# ---------------------------------------------------------------------------
class PartContext:
    """Holds artifact paths for one part and caches loaded GLBs."""

    def __init__(self, part: str, artifacts: Dict[str, str]):
        self.part = part
        self.artifacts = artifacts   # kind -> path, e.g. {"footprint": "...glb"}
        self._glb_cache: Dict[str, "GLTF2"] = {}

    def has(self, kind: str) -> bool:
        path = self.artifacts.get(kind)
        return bool(path and Path(path).is_file())

    def glb(self, kind: str) -> Optional["GLTF2"]:
        if not self.has(kind):
            return None
        if kind not in self._glb_cache:
            self._glb_cache[kind] = GLTF2().load_binary(self.artifacts[kind])
        return self._glb_cache[kind]


# ---------------------------------------------------------------------------
# glTF graph helpers
# ---------------------------------------------------------------------------
def _local_matrix(node) -> np.ndarray:
    if node.matrix:
        # glTF matrices are column-major; reshape+T gives a row-major math matrix.
        return np.array(node.matrix, dtype=float).reshape(4, 4).T
    t = node.translation or [0.0, 0.0, 0.0]
    r = node.rotation or [0.0, 0.0, 0.0, 1.0]
    s = node.scale or [1.0, 1.0, 1.0]
    x, y, z, w = r
    rot = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w),     2 * (x * z + y * w),     0],
        [2 * (x * y + z * w),     1 - 2 * (x * x + z * z), 2 * (y * z - x * w),     0],
        [2 * (x * z - y * w),     2 * (y * z + x * w),     1 - 2 * (x * x + y * y), 0],
        [0, 0, 0, 1],
    ], dtype=float)
    scale = np.diag([s[0], s[1], s[2], 1.0])
    trans = np.eye(4)
    trans[:3, 3] = t
    return trans @ rot @ scale


def _world_matrices(gltf) -> Dict[int, np.ndarray]:
    """World transform for every node, walking down from the scene roots."""
    world: Dict[int, np.ndarray] = {}
    roots = gltf.scenes[0].nodes if gltf.scenes else []

    def walk(idx: int, parent: np.ndarray) -> None:
        m = parent @ _local_matrix(gltf.nodes[idx])
        world[idx] = m
        for c in (gltf.nodes[idx].children or []):
            walk(c, m)

    for r in roots:
        walk(r, np.eye(4))
    return world


def _find_child(gltf, node_index: int, name: str) -> Optional[int]:
    for c in (gltf.nodes[node_index].children or []):
        if gltf.nodes[c].name == name:
            return c
    return None


def _root(gltf) -> Optional[int]:
    if not gltf.scenes or not gltf.scenes[0].nodes:
        return None
    return gltf.scenes[0].nodes[0]


# A world-space box is (lo, hi) with lo/hi as length-3 numpy arrays.
Box = Tuple[np.ndarray, np.ndarray]


def _mesh_aabb3(gltf, node_index: int, world: np.ndarray) -> Optional[Box]:
    """3D world AABB of a node's own mesh, or None."""
    node = gltf.nodes[node_index]
    if node.mesh is None:
        return None
    corners: List[np.ndarray] = []
    for prim in gltf.meshes[node.mesh].primitives:
        acc = gltf.accessors[prim.attributes.POSITION]
        if not acc.min or not acc.max:
            continue
        lo, hi = acc.min, acc.max
        for cx in (lo[0], hi[0]):
            for cy in (lo[1], hi[1]):
                for cz in (lo[2], hi[2]):
                    corners.append((world @ np.array([cx, cy, cz, 1.0]))[:3])
    if not corners:
        return None
    pts = np.array(corners)
    return pts.min(axis=0), pts.max(axis=0)


def _subtree_aabb3(gltf, root_index: int, world: Dict[int, np.ndarray]) -> Optional[Box]:
    """Union 3D AABB over every mesh in a subtree."""
    los: List[np.ndarray] = []
    his: List[np.ndarray] = []

    def walk(idx: int) -> None:
        b = _mesh_aabb3(gltf, idx, world[idx])
        if b:
            los.append(b[0])
            his.append(b[1])
        for c in (gltf.nodes[idx].children or []):
            walk(c)

    walk(root_index)
    if not los:
        return None
    return np.array(los).min(axis=0), np.array(his).max(axis=0)


def _board_axes(boxes: List[Box]) -> Tuple[int, int]:
    """The two in-plane axes of a flat footprint (ignore the thin/normal axis).

    The exporter can leave the footprint in X-Y or X-Z; the board normal is
    whichever axis has the smallest total extent across all geometry.
    """
    lo = np.array([b[0] for b in boxes]).min(axis=0)
    hi = np.array([b[1] for b in boxes]).max(axis=0)
    normal = int(np.argmin(hi - lo))
    return tuple(a for a in (0, 1, 2) if a != normal)  # type: ignore[return-value]


def _planar_clearance(a: Box, b: Box, axes: Tuple[int, int]) -> float:
    """In-plane gap between two AABBs; 0 touching, negative when overlapping."""
    overlap = True
    seps: List[float] = []
    for ax in axes:
        d = max(b[0][ax] - a[1][ax], a[0][ax] - b[1][ax])
        seps.append(d)
        if d >= 0:
            overlap = False
    if overlap:
        return max(seps)                 # overlap depth (negative)
    return math.hypot(*[max(d, 0.0) for d in seps])


def _leg_names(gltf) -> Optional[List[str]]:
    root = _root(gltf)
    if root is None:
        return None
    legs = _find_child(gltf, root, "Legs")
    if legs is None:
        return None
    return [gltf.nodes[c].name for c in (gltf.nodes[legs].children or [])]


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
def _need_glb(ctx: PartContext, kind: str) -> Optional[_Outcome]:
    if GLTF2 is None:
        return _Outcome(CheckStatus.UNRUN, "pygltflib not installed")
    if not ctx.has(kind):
        return _Outcome(CheckStatus.SKIP, f"no {kind} artifact")
    return None


def check_pin_pad_set_mapping(ctx: PartContext) -> _Outcome:
    """V-01: the symbol's pin set equals the footprint's pad set (as a set)."""
    miss = _need_glb(ctx, "footprint") or _need_glb(ctx, "symbol")
    if miss:
        return miss
    sym = _leg_names(ctx.glb("symbol"))
    fp = _leg_names(ctx.glb("footprint"))
    if sym is None or fp is None:
        return _Outcome(CheckStatus.UNRUN, "could not read Legs from an artifact")
    sset, fset = set(sym), set(fp)
    if sset == fset:
        return _Outcome(CheckStatus.PASS, f"{len(fset)} pins map 1:1", measured=f"{len(fset)} pins")
    only_sym = sorted(sset - fset)
    only_fp = sorted(fset - sset)
    return _Outcome(
        CheckStatus.FAIL,
        f"symbol pins ({len(sset)}) != footprint pads ({len(fset)}); "
        f"symbol-only={only_sym or '-'} footprint-only={only_fp or '-'}",
        measured=f"sym={len(sset)} fp={len(fset)}",
    )


def check_symbol_pin_numbering(ctx: PartContext) -> _Outcome:
    """SYM-12: pin numbers are unique and complete 1..N with no gaps."""
    miss = _need_glb(ctx, "symbol")
    if miss:
        return miss
    names = _leg_names(ctx.glb("symbol"))
    if not names:
        return _Outcome(CheckStatus.UNRUN, "no Legs in symbol")
    nums: List[int] = []
    for n in names:
        try:
            nums.append(int(n))
        except ValueError:
            return _Outcome(CheckStatus.FAIL, f"non-numeric pin label {n!r}")
    dupes = sorted({x for x in nums if nums.count(x) > 1})
    expected = set(range(1, len(nums) + 1))
    gaps = sorted(expected - set(nums))
    if dupes or gaps:
        return _Outcome(
            CheckStatus.FAIL,
            f"duplicated={dupes or '-'} missing(1..{len(nums)})={gaps or '-'}",
            measured=f"{len(nums)} pins",
        )
    return _Outcome(CheckStatus.PASS, f"1..{len(nums)} contiguous, unique", measured=f"{len(nums)} pins")


def check_footprint_layers_present(ctx: PartContext) -> _Outcome:
    """FP-06 / LAY-01: Body carries distinct fab, silk, courtyard layers."""
    miss = _need_glb(ctx, "footprint")
    if miss:
        return miss
    g = ctx.glb("footprint")
    root = _root(g)
    body = _find_child(g, root, "Body") if root is not None else None
    if body is None:
        return _Outcome(CheckStatus.FAIL, "no Body node in footprint")
    want = ["fab_layer", "silk_layer", "crtyd_layer"]
    present = [w for w in want if _find_child(g, body, w) is not None]
    missing = [w for w in want if w not in present]
    if missing:
        return _Outcome(CheckStatus.FAIL, f"missing layers: {missing}", measured=str(present))
    return _Outcome(CheckStatus.PASS, "fab / silk / courtyard all present")


def check_pin1_marker_present(ctx: PartContext) -> _Outcome:
    """FP-08: a pin-1 marker exists on both silk and assembly (fab) layers."""
    miss = _need_glb(ctx, "footprint")
    if miss:
        return miss
    g = ctx.glb("footprint")
    root = _root(g)
    marker = _find_child(g, root, "FirstPinMarker") if root is not None else None
    if marker is None:
        return _Outcome(CheckStatus.FAIL, "no FirstPinMarker node")
    has_silk = _find_child(g, marker, "silk_firstPinMarker") is not None
    has_fab = _find_child(g, marker, "fab_firstPinMarker") is not None
    if has_silk and has_fab:
        return _Outcome(CheckStatus.PASS, "pin-1 marker on silk + fab")
    return _Outcome(
        CheckStatus.FAIL,
        f"pin-1 marker incomplete (silk={has_silk}, fab={has_fab})",
    )


def _copper_pad_boxes(g, world) -> Dict[str, Box]:
    """Per-pin copper-pad 3D AABB (union of copper nodes under each leg)."""
    root = _root(g)
    legs = _find_child(g, root, "Legs") if root is not None else None
    out: Dict[str, Box] = {}
    if legs is None:
        return out
    for pin in (g.nodes[legs].children or []):
        pin_name = g.nodes[pin].name
        los, his = [], []
        for cu in (g.nodes[pin].children or []):
            if "Copper" in (g.nodes[cu].name or ""):
                b = _subtree_aabb3(g, cu, world)
                if b:
                    los.append(b[0])
                    his.append(b[1])
        if los:
            out[pin_name] = (np.array(los).min(axis=0), np.array(his).max(axis=0))
    return out


def _silk_boxes(g, world) -> List[Box]:
    """One 3D AABB per silkscreen object (each BodyLine + silk pin-1 marker)."""
    root = _root(g)
    boxes: List[Box] = []
    if root is None:
        return boxes
    body = _find_child(g, root, "Body")
    if body is not None:
        silk = _find_child(g, body, "silk_layer")
        if silk is not None:
            for obj in (g.nodes[silk].children or []):
                b = _subtree_aabb3(g, obj, world)
                if b:
                    boxes.append(b)
    marker = _find_child(g, root, "FirstPinMarker")
    if marker is not None:
        sm = _find_child(g, marker, "silk_firstPinMarker")
        if sm is not None:
            b = _subtree_aabb3(g, sm, world)
            if b:
                boxes.append(b)
    return boxes


def check_silk_pad_clearance(ctx: PartContext) -> _Outcome:
    """FP-07 / LAY-06: no silkscreen within 0.20 mm of any copper pad."""
    miss = _need_glb(ctx, "footprint")
    if miss:
        return miss
    g = ctx.glb("footprint")
    world = _world_matrices(g)
    pads = _copper_pad_boxes(g, world)
    silks = _silk_boxes(g, world)
    if not pads or not silks:
        return _Outcome(CheckStatus.UNRUN, f"no {'pads' if not pads else 'silk'} geometry found")
    axes = _board_axes(list(pads.values()) + silks)
    worst = math.inf
    worst_desc = ""
    violations = 0
    for pin, pad in pads.items():
        for si, silk in enumerate(silks):
            gap = _planar_clearance(silk, pad, axes)
            if gap < worst:
                worst, worst_desc = gap, f"silk#{si}->pad{pin}"
            if gap < SILK_PAD_CLEARANCE_MM:
                violations += 1
    measured = f"min gap {worst:.3f} mm ({worst_desc})"
    if worst < SILK_PAD_CLEARANCE_MM:
        return _Outcome(
            CheckStatus.FAIL,
            f"{violations} silk/pad pair(s) below {SILK_PAD_CLEARANCE_MM} mm; worst {worst:.3f} mm ({worst_desc})",
            measured=measured, threshold=f">= {SILK_PAD_CLEARANCE_MM} mm",
        )
    return _Outcome(CheckStatus.PASS, measured, measured=measured, threshold=f">= {SILK_PAD_CLEARANCE_MM} mm")


def check_pad_pad_clearance(ctx: PartContext) -> _Outcome:
    """FP-14: adjacent copper pads keep at least the minimum spacing."""
    miss = _need_glb(ctx, "footprint")
    if miss:
        return miss
    g = ctx.glb("footprint")
    world = _world_matrices(g)
    pads = _copper_pad_boxes(g, world)
    if len(pads) < 2:
        return _Outcome(CheckStatus.UNRUN, "fewer than two pads with geometry")
    axes = _board_axes(list(pads.values()))
    items = list(pads.items())
    worst = math.inf
    worst_desc = ""
    violations = 0
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            gap = _planar_clearance(items[i][1], items[j][1], axes)
            if gap < worst:
                worst, worst_desc = gap, f"pad{items[i][0]}<->pad{items[j][0]}"
            if gap < PAD_PAD_CLEARANCE_MM:
                violations += 1
    measured = f"min gap {worst:.3f} mm ({worst_desc})"
    if worst < PAD_PAD_CLEARANCE_MM:
        return _Outcome(
            CheckStatus.FAIL,
            f"{violations} pad pair(s) below {PAD_PAD_CLEARANCE_MM} mm; worst {worst:.3f} mm ({worst_desc})",
            measured=measured, threshold=f">= {PAD_PAD_CLEARANCE_MM} mm",
        )
    return _Outcome(CheckStatus.PASS, measured, measured=measured, threshold=f">= {PAD_PAD_CLEARANCE_MM} mm")


def _center_planar(box: Box, axes: Tuple[int, int]) -> Tuple[float, float]:
    lo, hi = box
    return (lo[axes[0]] + hi[axes[0]]) / 2, (lo[axes[1]] + hi[axes[1]]) / 2


def check_origin_at_centroid(ctx: PartContext) -> _Outcome:
    """FP-03: the footprint origin sits at the body centroid.

    The assembly (fab) body outline should be centred on (0,0) in the board
    plane; a pad-array centroid fallback covers footprints without a fab box.
    """
    miss = _need_glb(ctx, "footprint")
    if miss:
        return miss
    g = ctx.glb("footprint")
    world = _world_matrices(g)
    root = _root(g)
    body = _find_child(g, root, "Body") if root is not None else None
    fab = _find_child(g, body, "fab_layer") if body is not None else None
    box = _subtree_aabb3(g, fab, world) if fab is not None else None
    source = "fab outline"
    if box is None:
        pads = _copper_pad_boxes(g, world)
        if not pads:
            return _Outcome(CheckStatus.UNRUN, "no fab outline or pads to locate centroid")
        los = np.array([b[0] for b in pads.values()]).min(axis=0)
        his = np.array([b[1] for b in pads.values()]).max(axis=0)
        box = (los, his)
        source = "pad array"
    axes = _board_axes([box])
    cx, cy = _center_planar(box, axes)
    off = math.hypot(cx, cy)
    measured = f"{source} centroid ({cx:.3f},{cy:.3f}), |offset|={off:.3f} mm"
    if off > CENTROID_TOL_MM:
        return _Outcome(CheckStatus.FAIL, f"origin off {source} centroid by {off:.3f} mm",
                        measured=measured, threshold=f"<= {CENTROID_TOL_MM} mm")
    return _Outcome(CheckStatus.PASS, measured, measured=measured, threshold=f"<= {CENTROID_TOL_MM} mm")


def check_pad_numbering_perimeter(ctx: PartContext) -> _Outcome:
    """FP-04: pads are numbered in one consistent sweep around the perimeter.

    Verifies pin 1..N step monotonically around the body centroid (all turns the
    same rotational sense) with pin 1 at an extreme corner — this catches the
    scattered / wrong-order defect. Absolute CW-vs-CCW-from-top handedness is not
    asserted here (it depends on the viewer's up convention).
    """
    miss = _need_glb(ctx, "footprint")
    if miss:
        return miss
    g = ctx.glb("footprint")
    world = _world_matrices(g)
    pads = _copper_pad_boxes(g, world)
    if len(pads) < 4:
        return _Outcome(CheckStatus.SKIP, "too few pads for a perimeter test")
    axes = _board_axes(list(pads.values()))
    try:
        ordered = sorted(pads.items(), key=lambda kv: int(kv[0]))
    except ValueError:
        return _Outcome(CheckStatus.SKIP, "non-numeric pad labels (e.g. BGA grid)")
    pts = [np.array(_center_planar(b, axes)) for _, b in ordered]
    centroid = np.mean(pts, axis=0)

    def ang(p):
        d = p - centroid
        return math.atan2(d[1], d[0])

    # Consecutive cross-products around the centroid: a clean sweep keeps one sign.
    signs = []
    n = len(pts)
    for i in range(n):
        a = pts[i] - centroid
        b = pts[(i + 1) % n] - centroid
        cross = a[0] * b[1] - a[1] * b[0]
        if abs(cross) > 1e-6:
            signs.append(1 if cross > 0 else -1)
    if not signs:
        return _Outcome(CheckStatus.UNRUN, "degenerate pad geometry")
    turns = sum(1 for i in range(1, len(signs)) if signs[i] != signs[i - 1])
    # pin 1 should be a corner: farthest-ish from centroid, not mid-edge.
    dists = [np.linalg.norm(p - centroid) for p in pts]
    pin1_extreme = dists[0] >= 0.9 * max(dists)
    direction = "CCW" if signs[0] > 0 else "CW"
    if turns == 0 and pin1_extreme:
        return _Outcome(CheckStatus.PASS, f"monotonic {direction} sweep, pin 1 at corner",
                        measured=f"{direction}, {n} pads")
    reasons = []
    if turns:
        reasons.append(f"{turns} direction reversal(s) in numbering")
    if not pin1_extreme:
        reasons.append("pin 1 not at an extreme corner")
    return _Outcome(CheckStatus.FAIL, "; ".join(reasons), measured=f"{direction}, {n} pads")


def check_symbol_grid(ctx: PartContext) -> _Outcome:
    """SYM-02: every schematic pin endpoint lies on the 2.54 mm grid.

    Grid-snap is origin-independent: all pin endpoints differ from each other by
    whole multiples of 2.54 mm on both in-plane axes.
    """
    miss = _need_glb(ctx, "symbol")
    if miss:
        return miss
    g = ctx.glb("symbol")
    world = _world_matrices(g)
    root = _root(g)
    legs = _find_child(g, root, "Legs") if root is not None else None
    if legs is None:
        return _Outcome(CheckStatus.UNRUN, "no Legs in symbol")
    pts: List[np.ndarray] = []
    boxes: List[Box] = []
    for pin in (g.nodes[legs].children or []):
        pp = _find_child(g, pin, "pinPoint")
        node = pp if pp is not None else pin
        b = _subtree_aabb3(g, node, world)
        if b:
            boxes.append(b)
    if len(boxes) < 2:
        return _Outcome(CheckStatus.UNRUN, "not enough pin endpoints")
    axes = _board_axes(boxes)
    centers = [np.array(_center_planar(b, axes)) for b in boxes]
    base = centers[0]
    worst = 0.0
    off_pins = 0
    for c in centers:
        for k in (0, 1):
            rem = abs((c[k] - base[k]) % SCHEM_GRID_MM)
            rem = min(rem, SCHEM_GRID_MM - rem)   # distance to nearest grid line
            if rem > worst:
                worst = rem
        if any(min(abs((c[k] - base[k]) % SCHEM_GRID_MM),
                   SCHEM_GRID_MM - abs((c[k] - base[k]) % SCHEM_GRID_MM)) > GRID_TOL_MM
               for k in (0, 1)):
            off_pins += 1
    measured = f"worst off-grid {worst:.3f} mm over {len(centers)} pins"
    if off_pins:
        return _Outcome(CheckStatus.FAIL, f"{off_pins} pin(s) off the {SCHEM_GRID_MM} mm grid; {measured}",
                        measured=measured, threshold=f"<= {GRID_TOL_MM} mm")
    return _Outcome(CheckStatus.PASS, measured, measured=measured, threshold=f"<= {GRID_TOL_MM} mm")


def _is_through_hole(ctx: PartContext) -> Optional[bool]:
    """True if the footprint has plated through-holes (leads pass below Z=0)."""
    if not ctx.has("footprint"):
        return None
    g = ctx.glb("footprint")
    root = _root(g)
    legs = _find_child(g, root, "Legs") if root is not None else None
    if legs is None:
        return None
    for pin in (g.nodes[legs].children or []):
        for c in (g.nodes[pin].children or []):
            if "Hole" in (g.nodes[c].name or "") or "Cylinder" in (g.nodes[c].name or ""):
                return True
    return False


def check_body_seating_plane(ctx: PartContext) -> _Outcome:
    """3D-02: Z=0 is the seating plane, body in +Z — not the body centre.

    In the body GLB (Y-up) the seating plane is Y=0. For surface-mount parts the
    body bottom sits at ~0; for through-hole parts the leads legitimately reach
    below 0 while the body stays above, so THT-ness (read from the footprint's
    plated holes) relaxes the lower bound. The defect this guards is the datum
    placed at the body *centre*, sinking the part into the board.
    """
    miss = _need_glb(ctx, "body")
    if miss:
        return miss
    g = ctx.glb("body")
    box = _subtree_aabb3(g, _root(g), _world_matrices(g)) if _root(g) is not None else None
    if box is None:
        return _Outcome(CheckStatus.UNRUN, "no body geometry")
    lo_y = float(box[0][BODY_VERTICAL_AXIS])
    hi_y = float(box[1][BODY_VERTICAL_AXIS])
    measured = f"vertical extent [{lo_y:.3f}, {hi_y:.3f}] mm"
    if hi_y <= 0:
        return _Outcome(CheckStatus.FAIL, f"body not above the seating plane; {measured}", measured=measured)

    if _is_through_hole(ctx):
        # Leads below Z=0 are expected; only require the body to rise above it.
        return _Outcome(CheckStatus.PASS, f"through-hole: body above Z=0, leads below; {measured}",
                        measured=measured)
    # Surface-mount: the body bottom must sit on the seating plane, not below it.
    if lo_y < -SEATING_TOL_MM:
        return _Outcome(CheckStatus.FAIL,
                        f"body dips {abs(lo_y):.3f} mm below the seating plane (datum not at Z=0); {measured}",
                        measured=measured, threshold=f"lo >= -{SEATING_TOL_MM} mm")
    return _Outcome(CheckStatus.PASS, f"seats on Z=0; {measured}",
                    measured=measured, threshold=f"lo >= -{SEATING_TOL_MM} mm")


def check_body_within_courtyard(ctx: PartContext) -> _Outcome:
    """3D-11: the body's board-plane envelope fits inside the footprint courtyard."""
    m1 = _need_glb(ctx, "body")
    if m1:
        return m1
    m2 = _need_glb(ctx, "footprint")
    if m2:
        return _Outcome(CheckStatus.SKIP, "no footprint to compare the envelope against")
    gb = ctx.glb("body")
    gf = ctx.glb("footprint")
    body_box = _subtree_aabb3(gb, _root(gb), _world_matrices(gb))
    gfw = _world_matrices(gf)
    rootf = _root(gf)
    body_f = _find_child(gf, rootf, "Body") if rootf is not None else None
    crt = _find_child(gf, body_f, "crtyd_layer") if body_f is not None else None
    crt_box = _subtree_aabb3(gf, crt, gfw) if crt is not None else None
    if body_box is None or crt_box is None:
        return _Outcome(CheckStatus.UNRUN, "missing body or courtyard geometry")
    axes = (0, 2)  # board plane for both (Y-up)
    # Overrun = how far the body sticks out past the courtyard on any side.
    overrun = 0.0
    for ax in axes:
        overrun = max(overrun, crt_box[0][ax] - body_box[0][ax], body_box[1][ax] - crt_box[1][ax])
    measured = f"max overrun {overrun:.3f} mm"
    if overrun > COURTYARD_TOL_MM:
        return _Outcome(CheckStatus.FAIL, f"body envelope exceeds courtyard by {overrun:.3f} mm",
                        measured=measured, threshold=f"<= {COURTYARD_TOL_MM} mm")
    return _Outcome(CheckStatus.PASS, f"envelope inside courtyard ({measured})",
                    measured=measured, threshold=f"<= {COURTYARD_TOL_MM} mm")


def check_body_step_present(ctx: PartContext) -> _Outcome:
    """3D-01: STEP is the primary 3D format (emitted alongside the GLB)."""
    has_step = ctx.has("body_step")
    has_glb = ctx.has("body")
    if not has_step and not has_glb:
        return _Outcome(CheckStatus.SKIP, "no 3D body generated for this part")
    if has_step:
        return _Outcome(CheckStatus.PASS, "STEP present")
    return _Outcome(CheckStatus.FAIL, "body GLB present but STEP (primary) missing")


def _planar_diameter(g, node_index: int, world, axes: Tuple[int, int]) -> Optional[float]:
    """Max in-plane extent of a node's subtree (a circle's diameter)."""
    b = _subtree_aabb3(g, node_index, world)
    if b is None:
        return None
    return max(b[1][axes[0]] - b[0][axes[0]], b[1][axes[1]] - b[0][axes[1]])


def _hole_node(g, pin_index: int) -> Optional[int]:
    return _find_child(g, pin_index, "HoleCylinderPin") or _find_child(g, pin_index, "CopperCylinderPin")


def check_annular_ring(ctx: PartContext) -> _Outcome:
    """FP-10: through-hole pads keep >= 0.05 mm annular ring on every side."""
    miss = _need_glb(ctx, "footprint")
    if miss:
        return miss
    g = ctx.glb("footprint")
    world = _world_matrices(g)
    root = _root(g)
    legs = _find_child(g, root, "Legs") if root is not None else None
    if legs is None:
        return _Outcome(CheckStatus.UNRUN, "no Legs in footprint")
    worst = math.inf
    worst_pin = None
    n_tht = 0
    for pin in (g.nodes[legs].children or []):
        pad = _find_child(g, pin, "CopperCirclePad")
        hole = _hole_node(g, pin)
        if pad is None or hole is None:
            continue                              # surface-mount pin
        n_tht += 1
        axes = _board_axes([_subtree_aabb3(g, pad, world), _subtree_aabb3(g, hole, world)])
        pad_d = _planar_diameter(g, pad, world, axes)
        hole_d = _planar_diameter(g, hole, world, axes)
        if pad_d is None or hole_d is None:
            continue
        ring = (pad_d - hole_d) / 2.0
        if ring < worst:
            worst, worst_pin = ring, g.nodes[pin].name
    if n_tht == 0:
        return _Outcome(CheckStatus.SKIP, "surface-mount: no through-holes")
    measured = f"min ring {worst:.3f} mm (pin {worst_pin})"
    if worst < ANNULAR_RING_MIN_MM:
        return _Outcome(CheckStatus.FAIL, f"annular ring below {ANNULAR_RING_MIN_MM} mm; {measured}",
                        measured=measured, threshold=f">= {ANNULAR_RING_MIN_MM} mm")
    return _Outcome(CheckStatus.PASS, measured, measured=measured, threshold=f">= {ANNULAR_RING_MIN_MM} mm")


def check_tht_pad_multilayer(ctx: PartContext) -> _Outcome:
    """LAY-05: through-hole pads are multi-layer objects with an explicit drill."""
    miss = _need_glb(ctx, "footprint")
    if miss:
        return miss
    g = ctx.glb("footprint")
    root = _root(g)
    legs = _find_child(g, root, "Legs") if root is not None else None
    if legs is None:
        return _Outcome(CheckStatus.UNRUN, "no Legs in footprint")
    pins = list(g.nodes[legs].children or [])
    tht_pins = [p for p in pins if _hole_node(g, p) is not None]
    if not tht_pins:
        return _Outcome(CheckStatus.SKIP, "surface-mount: no through-holes")
    bad = []
    for p in pins:
        has_copper = _find_child(g, p, "CopperCirclePad") is not None
        has_drill = _hole_node(g, p) is not None
        if not (has_copper and has_drill):
            bad.append(g.nodes[p].name)
    if bad:
        return _Outcome(CheckStatus.FAIL,
                        f"{len(bad)} THT pin(s) not multi-layer (missing copper or drill): {bad[:5]}")
    return _Outcome(CheckStatus.PASS, f"{len(tht_pins)} THT pads carry copper + drill")


def check_mask_from_copper(ctx: PartContext) -> _Outcome:
    """FP-15: the solder-mask opening is derived by expanding the copper pad."""
    miss = _need_glb(ctx, "footprint")
    if miss:
        return miss
    g = ctx.glb("footprint")
    world = _world_matrices(g)
    root = _root(g)
    legs = _find_child(g, root, "Legs") if root is not None else None
    if legs is None:
        return _Outcome(CheckStatus.UNRUN, "no Legs in footprint")
    checked = 0
    worst_exp = math.inf
    bad = []
    for pin in (g.nodes[legs].children or []):
        cu = _find_child(g, pin, "CopperCirclePad")
        mk = _find_child(g, pin, "SolderMask")
        if cu is None or mk is None:
            continue
        cub = _subtree_aabb3(g, cu, world)
        mkb = _subtree_aabb3(g, mk, world)
        if cub is None or mkb is None:
            continue
        axes = _board_axes([cub, mkb])
        checked += 1
        for ax in axes:
            exp = ((mkb[1][ax] - mkb[0][ax]) - (cub[1][ax] - cub[0][ax])) / 2.0
            worst_exp = min(worst_exp, exp)
            if exp <= 0:
                bad.append(g.nodes[pin].name)
                break
    if checked == 0:
        return _Outcome(CheckStatus.UNRUN, "no copper/mask pad pairs found")
    measured = f"min mask expansion {worst_exp:.3f} mm/side over {checked} pads"
    if bad:
        return _Outcome(CheckStatus.FAIL,
                        f"{len(bad)} pad(s) with mask not expanded beyond copper: {bad[:5]}",
                        measured=measured, threshold="> 0 mm/side")
    return _Outcome(CheckStatus.PASS, measured, measured=measured, threshold="> 0 mm/side")


def check_body_units_mm(ctx: PartContext) -> _Outcome:
    """3D-09: the STEP file declares its length unit as millimetres."""
    if not ctx.has("body_step"):
        return _Outcome(CheckStatus.SKIP, "no STEP body to inspect")
    try:
        text = Path(ctx.artifacts["body_step"]).read_text(errors="replace")
    except OSError as e:
        return _Outcome(CheckStatus.UNRUN, f"could not read STEP: {e}")
    compact = "".join(text.split()).upper()
    if "SI_UNIT(.MILLI.,.METRE.)" in compact:
        return _Outcome(CheckStatus.PASS, "STEP length unit = millimetre")
    return _Outcome(CheckStatus.FAIL, "STEP does not declare a millimetre length unit")


def check_body_watertight(ctx: PartContext) -> _Outcome:
    """3D-06: the STEP body is closed, valid solids (watertight B-rep).

    B-rep validity needs topology, not the tessellated per-face GLB, so we read
    the STEP through the OCCT kernel (cadquery) and require at least one solid
    with every solid passing BRepCheck (``Shape.isValid``).
    """
    if not ctx.has("body_step"):
        return _Outcome(CheckStatus.SKIP, "no STEP body to inspect")
    try:
        import cadquery as cq
    except ImportError:  # pragma: no cover
        return _Outcome(CheckStatus.UNRUN, "cadquery not installed")
    try:
        shape = cq.importers.importStep(ctx.artifacts["body_step"])
    except Exception as e:
        return _Outcome(CheckStatus.FAIL, f"STEP failed to import: {e}")
    solids = shape.solids().vals()
    if not solids:
        return _Outcome(CheckStatus.FAIL, "STEP contains no solids")
    invalid = sum(1 for s in solids if not s.isValid())
    if invalid:
        return _Outcome(CheckStatus.FAIL,
                        f"{invalid}/{len(solids)} solids fail B-rep validity (not watertight)",
                        measured=f"{len(solids)} solids")
    return _Outcome(CheckStatus.PASS, f"{len(solids)} closed, valid solids",
                    measured=f"{len(solids)} solids")


def check_symbol_electrical_types(ctx: PartContext) -> _Outcome:
    """SYM-07: every symbol pin carries a contract electrical_type extra."""
    miss = _need_glb(ctx, "symbol")
    if miss:
        return miss
    from ..models import ELECTRICAL_TYPES
    g = ctx.glb("symbol")
    root = _root(g)
    legs = _find_child(g, root, "Legs") if root is not None else None
    if legs is None:
        return _Outcome(CheckStatus.UNRUN, "no Legs in symbol")
    pins = g.nodes[legs].children or []
    missing, bad = [], []
    for pin in pins:
        et = (g.nodes[pin].extras or {}).get("electricalType")
        if et is None:
            missing.append(g.nodes[pin].name)
        elif et not in ELECTRICAL_TYPES:
            bad.append(f"{g.nodes[pin].name}:{et}")
    if missing:
        return _Outcome(CheckStatus.FAIL, f"{len(missing)} pin(s) missing electricalType extra")
    if bad:
        return _Outcome(CheckStatus.FAIL, f"off-contract electricalType: {bad[:5]}")
    typed = sum(1 for p in pins if (g.nodes[p].extras or {}).get("electricalType") != "unspecified")
    return _Outcome(CheckStatus.PASS, f"{len(pins)} pins typed ({typed} concrete, rest unspecified)",
                    measured=f"{typed}/{len(pins)} concrete")


def check_nc_pins_marked(ctx: PartContext) -> _Outcome:
    """SYM-11: no-connect pins are drawn and explicitly tagged (nc extra).

    Every pin carries an ``nc`` flag, and any pin whose name is a no-connect
    label (NC/DNC/RESERVED) must be flagged nc=true (drawn, not omitted).
    """
    miss = _need_glb(ctx, "symbol")
    if miss:
        return miss
    g = ctx.glb("symbol")
    root = _root(g)
    legs = _find_child(g, root, "Legs") if root is not None else None
    if legs is None:
        return _Outcome(CheckStatus.UNRUN, "no Legs in symbol")

    def _is_nc_name(name: str) -> bool:
        return re.sub(r"[^A-Z]", "", (name or "").upper()) in {
            "NC", "DNC", "NOCONNECT", "NOCONNECTION", "RESERVED", "DNU"}

    pins = g.nodes[legs].children or []
    missing, unmarked = [], []
    for p in pins:
        ex = g.nodes[p].extras or {}
        if "nc" not in ex:
            missing.append(g.nodes[p].name)
            continue
        name = ex.get("pinName") or ex.get("value") or ""
        if _is_nc_name(name) and not ex.get("nc"):
            unmarked.append(g.nodes[p].name)
    if missing:
        return _Outcome(CheckStatus.FAIL, f"{len(missing)} pin(s) missing nc flag")
    if unmarked:
        return _Outcome(CheckStatus.FAIL, f"no-connect-named pins not tagged nc: {unmarked[:5]}")
    nc_n = sum(1 for p in pins if (g.nodes[p].extras or {}).get("nc"))
    return _Outcome(CheckStatus.PASS, f"{len(pins)} pins tagged ({nc_n} no-connect)",
                    measured=f"{nc_n} nc")


def check_active_low_notation(ctx: PartContext) -> _Outcome:
    """SYM-08: active-low pins carry a flag + one consistent ASCII marker.

    Every pin has an ``activeLow`` flag; every active-low pin's ``displayName``
    carries the single leading '/' marker (frontend renders a true overbar).
    """
    miss = _need_glb(ctx, "symbol")
    if miss:
        return miss
    g = ctx.glb("symbol")
    root = _root(g)
    legs = _find_child(g, root, "Legs") if root is not None else None
    if legs is None:
        return _Outcome(CheckStatus.UNRUN, "no Legs in symbol")
    pins = g.nodes[legs].children or []
    missing, unmarked = [], []
    for p in pins:
        ex = g.nodes[p].extras or {}
        if "activeLow" not in ex:
            missing.append(g.nodes[p].name)
            continue
        if ex.get("activeLow") and not str(ex.get("displayName", "")).startswith("/"):
            unmarked.append(g.nodes[p].name)
    if missing:
        return _Outcome(CheckStatus.FAIL, f"{len(missing)} pin(s) missing activeLow flag")
    if unmarked:
        return _Outcome(CheckStatus.FAIL, f"active-low pins missing '/' marker: {unmarked[:5]}")
    al = sum(1 for p in pins if (g.nodes[p].extras or {}).get("activeLow"))
    return _Outcome(CheckStatus.PASS, f"{len(pins)} pins flagged ({al} active-low)",
                    measured=f"{al} active_low")


# Schematic side codes (schematic_extras convention): 0=left,1=top,2=right,3=bottom.
_SIDE_CODE_TO_NAME = {0: "left", 1: "top", 2: "right", 3: "bottom"}


def check_functional_grouping(ctx: PartContext) -> _Outcome:
    """SYM-04: pins are grouped on the symbol side their electrical function dictates.

    Grades only parts the generator would actually lay out functionally — i.e.
    that clear the shared coverage gate (power+ground concrete, >=50% concrete
    roles). Below the gate the symbol is legitimately physical, so the rule does
    not apply and we SKIP. For gated parts, every concretely-classified pin must
    sit on ``ROLE_SIDE[role]``; ``nc`` pins (role "unplaced") and unknown/``other``
    roles are exempt (they carry no side obligation).
    """
    miss = _need_glb(ctx, "symbol")
    if miss:
        return miss
    from ..models import ROLE_SIDE, normalize_role, functional_layout_applicable
    g = ctx.glb("symbol")
    root = _root(g)
    legs = _find_child(g, root, "Legs") if root is not None else None
    if legs is None:
        return _Outcome(CheckStatus.UNRUN, "no Legs in symbol")
    pins = g.nodes[legs].children or []

    raw_roles = [(g.nodes[p].extras or {}).get("role") for p in pins]
    if not functional_layout_applicable(raw_roles):
        return _Outcome(CheckStatus.SKIP,
                        "below functional-layout gate (physical layout is expected)")

    mismatches: List[str] = []
    graded = 0
    for p in pins:
        ex = g.nodes[p].extras or {}
        role = normalize_role(ex.get("role"))
        if role in (None, "other", "nc") or ex.get("nc"):
            continue                               # no side obligation
        expected = ROLE_SIDE.get(role)
        if expected in (None, "unplaced"):
            continue
        actual = _SIDE_CODE_TO_NAME.get(ex.get("side"))
        graded += 1
        if actual != expected:
            mismatches.append(f"{g.nodes[p].name}({role}):{actual}!={expected}")
    if graded == 0:
        return _Outcome(CheckStatus.SKIP, "no side-bearing roles to grade")
    measured = f"{graded - len(mismatches)}/{graded} grouped"
    if mismatches:
        return _Outcome(CheckStatus.FAIL,
                        f"{len(mismatches)} pin(s) not on their function side: {mismatches[:5]}",
                        measured=measured)
    return _Outcome(CheckStatus.PASS, f"all {graded} functional pins grouped by side",
                    measured=measured)


def check_power_ground_visible(ctx: PartContext) -> _Outcome:
    """SYM-05: power and ground pins are identified and drawn on the symbol.

    Every pin is emitted as a Leg node, so "visible" is structural. We grade
    whether the symbol carries identifiable power and/or ground pins: PASS when
    at least one is present (it is, by construction, drawn), SKIP when the part
    carries neither — a 2-pin passive or an unclassified part has nothing to
    grade. We never invent a missing ground, so a part is only reported on what
    it actually declares.
    """
    miss = _need_glb(ctx, "symbol")
    if miss:
        return miss
    g = ctx.glb("symbol")
    root = _root(g)
    legs = _find_child(g, root, "Legs") if root is not None else None
    if legs is None:
        return _Outcome(CheckStatus.UNRUN, "no Legs in symbol")
    power, ground = [], []
    for p in (g.nodes[legs].children or []):
        ex = g.nodes[p].extras or {}
        if ex.get("role") == "supply" or ex.get("electricalType") in ("power_in", "power_out"):
            power.append(g.nodes[p].name)
        if ex.get("role") == "ground":
            ground.append(g.nodes[p].name)
    if not power and not ground:
        return _Outcome(CheckStatus.SKIP, "no power/ground pins identified on this part")
    measured = f"{len(power)} power, {len(ground)} ground"
    return _Outcome(CheckStatus.PASS, f"power/ground pins drawn ({measured})", measured=measured)


def check_layout_not_physical(ctx: PartContext) -> _Outcome:
    """SYM-01: the symbol is laid out by function, not physical pin order.

    Only meaningful for parts the generator lays out functionally — those that
    clear the SYM-04 gate. Below the gate the physical layout is expected and
    correct, so this SKIPs (an unclassified or passive part is never faulted).
    For gated parts, functional grouping (every pin on ROLE_SIDE[role]) is
    exactly "not physical order", so this delegates to the SYM-04 grouping
    result rather than re-deriving it.
    """
    miss = _need_glb(ctx, "symbol")
    if miss:
        return miss
    from ..models import functional_layout_applicable
    g = ctx.glb("symbol")
    root = _root(g)
    legs = _find_child(g, root, "Legs") if root is not None else None
    if legs is None:
        return _Outcome(CheckStatus.UNRUN, "no Legs in symbol")
    raw_roles = [(g.nodes[p].extras or {}).get("role") for p in (g.nodes[legs].children or [])]
    if not functional_layout_applicable(raw_roles):
        return _Outcome(CheckStatus.SKIP, "below functional-layout gate (physical layout is expected)")
    inner = check_functional_grouping(ctx)
    if inner.status is CheckStatus.PASS:
        return _Outcome(CheckStatus.PASS, "grouped by function, not physical pin order",
                        measured=inner.measured)
    if inner.status is CheckStatus.FAIL:
        return _Outcome(CheckStatus.FAIL, f"layout still follows physical order: {inner.message}",
                        measured=inner.measured)
    return inner  # SKIP / UNRUN passthrough


def check_pnp_zero_orientation(ctx: PartContext) -> _Outcome:
    """FP-18: the footprint declares a pick-and-place zero orientation.

    Assembly/P&P needs a defined 0-degree placement datum. Generation stamps a
    fixed convention (0 deg, pin-1 reference) on the footprint Package root; this
    verifies it is present and zero. SKIP when there is no footprint artifact.
    """
    miss = _need_glb(ctx, "footprint")
    if miss:
        return miss
    g = ctx.glb("footprint")
    root = _root(g)
    if root is None:
        return _Outcome(CheckStatus.UNRUN, "no footprint root")
    zo = (g.nodes[root].extras or {}).get("zeroOrientation")
    if not isinstance(zo, dict) or "angle" not in zo:
        return _Outcome(CheckStatus.FAIL, "no pick-and-place zeroOrientation on footprint")
    angle = zo.get("angle")
    if angle != 0:
        return _Outcome(CheckStatus.FAIL, f"zero orientation not 0 deg (got {angle})",
                        measured=f"{angle} deg")
    return _Outcome(CheckStatus.PASS, "P&P zero orientation set (0 deg, pin-1 ref)",
                    measured="0 deg")


def check_component_height_present(ctx: PartContext) -> _Outcome:
    """FP-17: the footprint records the component's Z height.

    Assembly/BOM/collision needs the body height even though the 2D footprint
    plane discards Z. Generation stamps ``componentHeight`` on the Package root
    (from the 3D spec's body height). PASS when a positive height is present,
    FAIL when missing or non-positive; SKIP when there is no footprint artifact.
    """
    miss = _need_glb(ctx, "footprint")
    if miss:
        return miss
    g = ctx.glb("footprint")
    root = _root(g)
    if root is None:
        return _Outcome(CheckStatus.UNRUN, "no footprint root")
    ch = (g.nodes[root].extras or {}).get("componentHeight")
    value = ch.get("value") if isinstance(ch, dict) else None
    if not isinstance(value, (int, float)) or value <= 0:
        return _Outcome(CheckStatus.FAIL, "no positive componentHeight recorded on footprint",
                        measured=str(value))
    src = ch.get("source") if isinstance(ch, dict) else None
    return _Outcome(CheckStatus.PASS, f"component height {value} mm recorded ({src})",
                    measured=f"{value} mm")


_KNOWN_FOOTPRINT_LAYERS = {
    "F.Cu", "B.Cu", "*.Cu", "F.Mask", "B.Mask", "F.SilkS",
    "F.Fab", "F.CrtYd", "Edge.Cuts", "drill",
}


def check_every_object_layer_id(ctx: PartContext) -> _Outcome:
    """LAY-02: every drawn footprint object owns a layerId.

    Walk every mesh-bearing node; each must carry a ``layerId`` in the known
    KiCad-style layer set. Transparent UI helpers (BoundingBox) are exempt —
    they are selection aids, not fabrication objects. SKIP when there is no
    footprint artifact.
    """
    miss = _need_glb(ctx, "footprint")
    if miss:
        return miss
    g = ctx.glb("footprint")
    if not g.nodes:
        return _Outcome(CheckStatus.UNRUN, "empty footprint")
    missing, bad, checked = [], [], 0
    for node in g.nodes:
        if node.mesh is None or (node.name or "") == "BoundingBox":
            continue
        checked += 1
        lid = (node.extras or {}).get("layerId")
        if lid is None:
            missing.append(node.name)
        elif lid not in _KNOWN_FOOTPRINT_LAYERS:
            bad.append(f"{node.name}:{lid}")
    if checked == 0:
        return _Outcome(CheckStatus.UNRUN, "no drawable objects in footprint")
    if missing:
        return _Outcome(CheckStatus.FAIL, f"{len(missing)} object(s) without a layerId: {missing[:5]}",
                        measured=f"{len(missing)}/{checked} missing")
    if bad:
        return _Outcome(CheckStatus.FAIL, f"off-vocabulary layerId: {bad[:5]}")
    return _Outcome(CheckStatus.PASS, f"all {checked} objects own a layerId",
                    measured=f"{checked} objects")


def check_report_emitted(ctx: PartContext) -> _Outcome:
    """V-05: a machine-readable report exists — true by construction here."""
    return _Outcome(CheckStatus.PASS, "conformance report generated")


REGISTRY: Dict[str, Callable[[PartContext], _Outcome]] = {
    "pin_pad_set_mapping": check_pin_pad_set_mapping,
    "symbol_pin_numbering": check_symbol_pin_numbering,
    "footprint_layers_present": check_footprint_layers_present,
    "pin1_marker_present": check_pin1_marker_present,
    "silk_pad_clearance": check_silk_pad_clearance,
    "pad_pad_clearance": check_pad_pad_clearance,
    "annular_ring": check_annular_ring,
    "tht_pad_multilayer": check_tht_pad_multilayer,
    "mask_from_copper": check_mask_from_copper,
    "body_units_mm": check_body_units_mm,
    "origin_at_centroid": check_origin_at_centroid,
    "pad_numbering_perimeter": check_pad_numbering_perimeter,
    "symbol_grid": check_symbol_grid,
    "body_seating_plane": check_body_seating_plane,
    "body_within_courtyard": check_body_within_courtyard,
    "body_step_present": check_body_step_present,
    "body_watertight": check_body_watertight,
    "symbol_electrical_types": check_symbol_electrical_types,
    "nc_pins_marked": check_nc_pins_marked,
    "active_low_notation": check_active_low_notation,
    "functional_grouping": check_functional_grouping,
    "power_ground_visible": check_power_ground_visible,
    "layout_not_physical": check_layout_not_physical,
    "pnp_zero_orientation": check_pnp_zero_orientation,
    "component_height_present": check_component_height_present,
    "every_object_layer_id": check_every_object_layer_id,
    "report_emitted": check_report_emitted,
}
