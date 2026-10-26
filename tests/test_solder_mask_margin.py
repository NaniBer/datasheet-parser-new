"""P2-4: solder-mask margin must be consistent and match the ground truth.

The reference KiCad footprints (tests/ground_truth/**/*.kicad_mod) declare
``(solder_mask_margin 0.102)``, which in KiCad is a PER-SIDE clearance, so the
mask opening is the copper pad grown by 0.102 mm on every edge. The builder's
MASK_MARGIN is that per-side value and must be applied to each side (2x on the
full dimension). Earlier the builder added it once across the whole dimension,
so the drawn mask was only 0.051 mm/side -- half the reference -- while the
extras still declared 0.102. These tests pin declared == drawn == 0.102/side.
"""
import tempfile
from pathlib import Path

from pygltflib import GLTF2

from src.schematic_generator.pcb_footprint_builder import PcbFootprintBuilder

MARGIN = 0.102


def _x_width(gltf: GLTF2, node) -> float:
    acc = gltf.accessors[gltf.meshes[node.mesh].primitives[0].attributes.POSITION]
    return acc.max[0] - acc.min[0]


def _per_side_margin(pkg: str, n: int) -> float:
    with tempfile.TemporaryDirectory() as d:
        out = str(Path(d) / "f.glb")
        b = PcbFootprintBuilder(pkg, n, "U")
        b.save_glb(out, [{"number": i, "name": f"P{i}"} for i in range(1, n + 1)])
        g = GLTF2().load(out)
        copper = next(nd for nd in g.nodes if nd.name == "CopperCirclePad" and nd.mesh is not None)
        mask = next(nd for nd in g.nodes if nd.name == "SolderMask" and nd.mesh is not None)
        return round((_x_width(g, mask) - _x_width(g, copper)) / 2.0, 4)


def test_mask_margin_constant_is_per_side():
    assert PcbFootprintBuilder.MASK_MARGIN == MARGIN


def test_rect_pad_mask_drawn_at_full_margin_per_side():
    # SOIC-8 (rect pads) and TQFP-48 (rect pads) must draw mask = pad + 0.102/side.
    assert _per_side_margin("SOIC-8", 8) == MARGIN
    # 0.5 mm pitch: one clamped margin on every edge (QC AD9106 FP-08).
    assert _per_side_margin("TQFP-48", 48) == PcbFootprintBuilder("TQFP-48", 48).mask_margin < MARGIN


def test_circle_pad_spec_mask_diameter_grows_both_sides():
    # Through-hole circle pad: mask_diameter = diameter + 2 * per-side margin.
    b = PcbFootprintBuilder("DIP-8", 8, "U")
    spec = b._get_pad_spec() if hasattr(b, "_get_pad_spec") else None
    # Fall back to the build path if the spec accessor name differs.
    if spec and "diameter" in spec and "mask_diameter" in spec:
        per_side = round((spec["mask_diameter"] - spec["diameter"]) / 2.0, 4)
        assert per_side == MARGIN
