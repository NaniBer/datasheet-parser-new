"""QC regressions for two package-definition defects.

1. 74LVC1G99 (XSON8 / SOT833-1) came out ~3x too big because XSON canonicalises
   to SON and then inherited the generic SON-8 grid (~3.0 x 3.35 mm, 0.65 mm
   pitch). SOT833-1 is a tiny leadless SON (body 1.0 x 1.95 mm, 0.5 mm pitch).

2. The package value/MPN label rendered ~20-30 mm wide because value_size was
   3.0-4.0. It must be ~1 mm tall so a long MPN stays a few mm wide and fits the
   (real-dimension) footprint body. The designator uses its own knob and must
   stay larger.
"""

import pytest

from src.package_types.footprint_defaults import get_footprint_defaults
from src.package_types import package_geometry as pg


# --------------------------------------------------------------------------- #
# Defect 1 — XSON8 / SOT833-1 small outline
# --------------------------------------------------------------------------- #

# Published SOT833-1 (8-pin XSON) outline: body 1.0 (E) x 1.95 (D) mm, 0.5 pitch.
_SMALL = {"e": 0.5, "E": 1.0, "E1": 1.0, "D": 1.95, "D1": 1.95}


@pytest.mark.parametrize("pkg", ["XSON8", "XSON-8", "SOT833-1", "SOT833", "XSON"])
def test_xson8_sot833_uses_small_outline(pkg):
    dims = get_footprint_defaults(pkg, 8)
    assert dims is not None
    for k, v in _SMALL.items():
        assert dims[k] == pytest.approx(v), f"{pkg}: {k}={dims.get(k)} != {v}"
    # Must NOT be the oversized generic SON-8 grid.
    assert dims["E1"] < 3.0 and dims["D1"] < 3.35
    # Tiny logic package: no fabricated exposed thermal pad.
    assert "D2" not in dims and "E2" not in dims


@pytest.mark.parametrize("pkg", ["SON8", "SON-8", "DFN8", "WSON8"])
def test_generic_son_dfn_unchanged(pkg):
    # The fix must be specific to XSON/SOT833 — a normal SON/DFN-8 keeps the
    # generic leadless grid (0.65 mm pitch, 3.0 x 3.35 mm body).
    dims = get_footprint_defaults(pkg, 8)
    assert dims["e"] == 0.65
    assert dims["E1"] == 3.0 and dims["D1"] == 3.35


def test_other_xson_pin_counts_fall_through():
    # Only the 8-pin SOT833-1 outline is tabulated; other XSON sizes (SOT886 …)
    # are not, so they keep the generic SON grid rather than the 8-pin values.
    dims = get_footprint_defaults("XSON6", 6)
    assert dims["E1"] == 3.0 and dims["e"] == 0.65


def test_xson8_footprint_courtyard_is_small():
    # End-to-end: the built footprint body + courtyard must shrink to the real
    # outline, not the old ~4.2 x 3.85 mm courtyard.
    from src.schematic_generator.pcb_footprint_builder import PcbFootprintBuilder

    b = PcbFootprintBuilder("XSON8", 8, "74LVC1G99")
    fab_hw, fab_hh, _sw, _sh, crtyd_hw, crtyd_hh = b._layer_half_dims()
    assert b.fab_outline_width == pytest.approx(1.0)
    assert b.fab_outline_length == pytest.approx(1.95)
    assert b.params.pin_pitch == pytest.approx(0.5)
    # Courtyard encloses the ~1 x 1.95 mm body + small pads; well under the old
    # oversized grid.
    assert 2 * crtyd_hw < 3.0, f"courtyard width {2 * crtyd_hw:.2f} mm too big"
    assert 2 * crtyd_hh < 3.5, f"courtyard length {2 * crtyd_hh:.2f} mm too big"


# --------------------------------------------------------------------------- #
# Defect 2 — value/MPN label text size
# --------------------------------------------------------------------------- #

# One representative package string per supported geometry builder.
_PKGS = ["DIP-8", "SOIC-8", "TSSOP-16", "DFN-8", "WSON-8", "SON-8",
         "TQFP-44", "LQFP-64", "QFN-32", "CDIP-8"]


@pytest.mark.parametrize("pkg", _PKGS)
def test_value_size_is_about_one_mm(pkg):
    n = int(pkg.split("-")[-1])
    params = pg.get_schematic_parameters(pkg, n)
    # ~1 mm, never the old 3-4 mm.
    assert params.body_geometry.value_size <= 1.0
    # Designator stays on its own (larger) knob — unaffected.
    assert params.body_geometry.designator_size > params.body_geometry.value_size


def test_value_size_dataclass_default():
    assert pg.BodyGeometry().value_size <= 1.0


def test_long_mpn_renders_narrow():
    # Firsthand render: a long MPN at the new value_size must be a few mm wide
    # and ~1 mm tall, not the ~20-30 mm it was at value_size 3-4.
    import cadquery as cq

    size = pg.BodyGeometry().value_size
    mpn = "TPS62177DQCT"  # 12 chars
    shape = cq.Workplane("XY").text(mpn, size, 0.5, halign="center", valign="center")
    bb = shape.val().BoundingBox()
    assert bb.xlen < 10.0, f"rendered value width {bb.xlen:.2f} mm too wide"
    assert bb.ylen < 1.2, f"rendered value height {bb.ylen:.2f} mm too tall"


@pytest.mark.parametrize("pkg", ["XSON-8", "XSON8 (SOT833-1)", "SOT833-1"])
def test_xson_symbol_has_no_epad_pin(pkg):
    # QC re-check LVC SCH-07: the 74LVC1G99 (XSON8 / SOT833-1) has no exposed
    # pad, so the symbol must not add an EPAD pin 9 the footprint never has.
    from src.schematic_generator.pinout_diagram_builder import PinoutDiagramBuilder

    sym = PinoutDiagramBuilder(pkg, 8, "74LVC1G99")
    assert not sym._has_exposed_pad
    assert all(str(p.pin_number) != "9" for p in sym.pin_positions)


@pytest.mark.parametrize("pkg,n", [("QFN-16", 16), ("LFCSP-32", 32), ("SON-8", 8),
                                   ("XSON-8", 8), ("SOIC-8", 8)])
def test_symbol_and_footprint_agree_on_exposed_pad(pkg, n):
    from src.schematic_generator.pcb_footprint_builder import PcbFootprintBuilder
    from src.schematic_generator.pinout_diagram_builder import PinoutDiagramBuilder

    assert (PinoutDiagramBuilder(pkg, n, "IC")._has_exposed_pad
            == PcbFootprintBuilder(pkg, n, "IC")._has_exposed_pad)
