"""QC (AD9106 / LFCSP-32): schematic-symbol lines and text were too thin.

The QFN/LFCSP symbol used sub-standard pin-line and text sizes (leg 0.05mm,
text 0.5-0.6mm), which QC flagged as "line too thin" / "text too thin". Align to
the KiCad Library Convention (KLC): pin text 1.27mm (50 mil), pin line ~0.15mm
(6 mil), body outline 0.254mm (10 mil).
"""
from src.package_types.package_geometry import get_qfn_parameters


def test_qfn_symbol_uses_klc_text_and_line_sizes():
    p = get_qfn_parameters(32)
    g = p.pin_geometry
    b = p.body_geometry
    # KLC pin name/number text height = 1.27 mm (50 mil)
    assert abs(g.pin_num_size - 1.27) < 1e-6, f"pin number text {g.pin_num_size} != 1.27 (KLC)"
    assert abs(g.pin_name_size - 1.27) < 1e-6, f"pin name text {g.pin_name_size} != 1.27 (KLC)"
    # KLC pin line width ~0.15 mm (6 mil) — must not regress to the old 0.05
    assert g.leg_width >= 0.15 - 1e-6, f"pin line width {g.leg_width} below KLC ~0.15"
    # KLC body outline 0.254 mm (10 mil)
    assert abs(b.border_thickness - 0.254) < 1e-6, f"body outline {b.border_thickness} != 0.254 (KLC)"


def test_qfn_symbol_text_fits_within_pin_pitch():
    # Bigger text must still clear the pin-to-pin spacing (no vertical overlap).
    p = get_qfn_parameters(32)
    assert p.pin_geometry.pin_name_size < p.pin_pitch
    assert p.pin_geometry.pin_num_size < p.pin_pitch


def test_qfn_label_gaps_symmetric_across_sides():
    # QC (AD9106): right-side labels sat farther from the pin than left-side ones.
    # Every side must share the same name/number gap magnitude.
    from src.schematic_generator.pin_layout import layout_pins
    p = get_qfn_parameters(32)
    pins = layout_pins(p, None)

    def gaps(side):
        ps = [pp for pp in pins if pp.side == side]
        pp = ps[len(ps) // 2]
        if side in ("left", "right"):
            return abs(round(pp.text_x - pp.x, 3)), abs(round(pp.num_x - pp.x, 3))
        return abs(round(pp.text_y - pp.y, 3)), abs(round(pp.num_y - pp.y, 3))

    g = {s: gaps(s) for s in ("left", "right", "top", "bottom")}
    name_mags = {v[0] for v in g.values()}
    num_mags = {v[1] for v in g.values()}
    assert len(name_mags) == 1, f"name gaps not symmetric: {g}"
    assert len(num_mags) == 1, f"number gaps not symmetric: {g}"


def test_tqfp_symbol_klc_and_symmetric_gaps():
    # TL16C2550 (TQFP-48) QC: thin lines/text + right-side names on the body line.
    from src.package_types.package_geometry import get_tqfp_parameters
    from src.schematic_generator.pin_layout import layout_pins
    p = get_tqfp_parameters(48)
    g = p.pin_geometry
    assert abs(g.pin_name_size - 1.27) < 1e-6 and abs(g.pin_num_size - 1.27) < 1e-6
    assert g.leg_width >= 0.15 - 1e-6
    assert abs(p.body_geometry.border_thickness - 0.254) < 1e-6
    pins = layout_pins(p, None)
    def gaps(side):
        ps = [pp for pp in pins if pp.side == side]; pp = ps[len(ps) // 2]
        if side in ("left", "right"): return abs(round(pp.text_x - pp.x, 2)), abs(round(pp.num_x - pp.x, 2))
        return abs(round(pp.text_y - pp.y, 2)), abs(round(pp.num_y - pp.y, 2))
    gg = {s: gaps(s) for s in ("left", "right", "top", "bottom")}
    assert len({v[0] for v in gg.values()}) == 1, f"name gaps asymmetric: {gg}"
    assert len({v[1] for v in gg.values()}) == 1, f"num gaps asymmetric: {gg}"
