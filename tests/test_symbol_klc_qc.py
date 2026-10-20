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
