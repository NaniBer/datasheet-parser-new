"""Tests for the power-tab package-body template (src/model3d/templates/powertab.py).

Reference family: TO-220 / DPAK(TO-252) / D2PAK(TO-263) -- a moulded body with a
metal heat-sink tab (mounting hole on the TO-220) and a small number of leads.
This first cut models the TO-220 through-hole style: leads exit the front (-Y)
face and run straight DOWN through the board (Z<0, like the DIP template), while
the moulded body stands on its A1 standoff and the metal tab protrudes in +Y with
a mounting hole cut through it.

These tests build Body3DSpec instances by hand and exercise the template directly
-- they do NOT go through the shared registry or validator.
"""
import pytest

from src.model3d.spec import Body3DSpec


def _to220_spec(pin_count: int) -> Body3DSpec:
    """A hand-built TO-220-ish Body3DSpec.

    Axis contract (shared): E1 -> X (body width, across the leads),
    D -> Y (body depth, the tab protrudes further in +Y), A -> Z (height).
    """
    return Body3DSpec(
        component_name=f"TO220-{pin_count}",
        package_type=f"TO-220-{pin_count}",
        package_family="TO220",
        lead_style="power_tab",
        pin_count=pin_count,
        pins_per_side=[pin_count, 0, 0, 0],
        body_length_D=4.5,       # Y depth of the moulded body
        body_width_E1=10.0,      # X width (comfortably holds the leads)
        body_height_A=9.0,       # Z height
        standoff_A1=2.5,         # body stands this far above the board
        lead_span_E=0.0,
        lead_pitch_e=2.54,
        lead_width_b=0.9,
        lead_foot_L=0.0,
        dims_source="text",
        confidence="verified",
    )


class TestPowerTabTemplate:
    def test_lead_style_string(self):
        from src.model3d.templates.powertab import PowerTabTemplate

        assert PowerTabTemplate.lead_style == "power_tab"

    def test_one_node_per_lead_plus_body_and_tab(self):
        from src.model3d.templates.powertab import PowerTabTemplate

        spec = _to220_spec(3)
        asm = PowerTabTemplate().build(spec)
        names = [c.name for c in asm.children]
        assert "Body" in names
        assert "Tab" in names
        lead_names = [n for n in names if n.startswith("Lead_")]
        assert len(lead_names) == spec.pin_count == 3

    def test_leads_spaced_at_pitch_e_along_x(self):
        from src.model3d.templates.powertab import PowerTabTemplate

        spec = _to220_spec(3)
        asm = PowerTabTemplate().build(spec)

        xs = []
        for c in asm.children:
            if not c.name.startswith("Lead_"):
                continue
            bb = c.toCompound().BoundingBox()
            xs.append((bb.xmin + bb.xmax) / 2.0)
        xs.sort()
        assert len(xs) == 3
        # Neighbouring lead centres are one pitch apart, centred on the origin.
        assert (xs[1] - xs[0]) == pytest.approx(spec.lead_pitch_e, abs=1e-6)
        assert (xs[2] - xs[1]) == pytest.approx(spec.lead_pitch_e, abs=1e-6)
        assert sum(xs) == pytest.approx(0.0, abs=1e-6)

    def test_leads_pass_below_the_board(self):
        from src.model3d.templates.powertab import PowerTabTemplate

        spec = _to220_spec(3)
        asm = PowerTabTemplate().build(spec)
        bb = asm.toCompound().BoundingBox()
        # Through-hole leads intentionally protrude below the seating plane.
        assert bb.zmin < 0

    def test_body_stands_on_its_standoff(self):
        from src.model3d.templates.powertab import PowerTabTemplate

        spec = _to220_spec(3)
        asm = PowerTabTemplate().build(spec)
        body = next(c for c in asm.children if c.name == "Body")
        bb = body.toCompound().BoundingBox()
        assert bb.zmin == pytest.approx(spec.standoff_A1, abs=0.02)
        assert bb.zmin > 0
        assert bb.zmax == pytest.approx(spec.body_height_A, abs=0.02)

    def test_tab_protrudes_beyond_body_in_y(self):
        from src.model3d.templates.powertab import PowerTabTemplate

        spec = _to220_spec(3)
        asm = PowerTabTemplate().build(spec)
        body_bb = next(c for c in asm.children if c.name == "Body").toCompound().BoundingBox()
        tab_bb = next(c for c in asm.children if c.name == "Tab").toCompound().BoundingBox()
        # The metal tab reaches further back (+Y) than the moulded body.
        assert tab_bb.ymax > body_bb.ymax

    def test_tab_has_a_mounting_hole(self):
        from src.model3d.templates.powertab import PowerTabTemplate

        spec = _to220_spec(3)
        asm = PowerTabTemplate().build(spec)
        tab_child = next(c for c in asm.children if c.name == "Tab")
        shape = tab_child.obj.val() if hasattr(tab_child.obj, "val") else tab_child.obj
        actual_vol = shape.Volume()
        bb = tab_child.toCompound().BoundingBox()
        solid_plate_vol = bb.xlen * bb.ylen * bb.zlen
        # A hole was cut, so the tab holds less material than a solid plate.
        assert actual_vol < solid_plate_vol

    def test_two_lead_variant_is_parametric(self):
        from src.model3d.templates.powertab import PowerTabTemplate

        spec = _to220_spec(2)
        asm = PowerTabTemplate().build(spec)
        lead_names = [c.name for c in asm.children if c.name.startswith("Lead_")]
        assert len(lead_names) == 2
        assert "Tab" in [c.name for c in asm.children]

    def test_missing_dims_do_not_crash(self):
        from src.model3d.templates.powertab import PowerTabTemplate

        spec = _to220_spec(3)
        # Zero-out everything the datasheet might omit; template must fall back.
        spec.body_length_D = 0.0
        spec.body_width_E1 = 0.0
        spec.body_height_A = 0.0
        spec.standoff_A1 = 0.0
        spec.lead_pitch_e = 0.0
        spec.lead_width_b = 0.0
        asm = PowerTabTemplate().build(spec)
        lead_names = [c.name for c in asm.children if c.name.startswith("Lead_")]
        assert len(lead_names) == 3
        assert "Tab" in [c.name for c in asm.children]
