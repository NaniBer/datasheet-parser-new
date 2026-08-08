"""Tests for the DIP through-hole package-body template (src/model3d/templates/dip.py).

Reference part: a generic DIP-8 (PDIP, 300-mil / 7.62mm row spacing). Unlike the
surface-mount gull-wing families, DIP leads pass straight DOWN through the board,
so the assembly geometry extends BELOW the seating plane (Z<0). These tests build
Body3DSpec instances by hand and exercise the template directly -- they do NOT go
through the shared registry or validator (the validator is not through-hole-aware).
"""
import pytest

from src.model3d.spec import Body3DSpec


def _dip_spec(pin_count: int) -> Body3DSpec:
    """A hand-built DIP Body3DSpec (300-mil row spacing, 2.54mm pitch)."""
    half = pin_count // 2
    return Body3DSpec(
        component_name=f"DIP{pin_count}",
        package_type=f"DIP-{pin_count}",
        package_family="DIP",
        lead_style="through_hole",
        pin_count=pin_count,
        pins_per_side=[half, pin_count - half, 0, 0],
        body_length_D=9.2 if pin_count == 8 else 19.05,
        body_width_E1=6.35,
        body_height_A=4.0,
        standoff_A1=0.38,
        lead_span_E=7.62,
        lead_pitch_e=2.54,
        lead_width_b=0.46,
        lead_foot_L=0.0,
        dims_source="text",
        confidence="verified",
    )


class TestDIPTemplate:
    def test_has_body_and_one_node_per_lead(self):
        from src.model3d.templates.dip import DIPTemplate

        spec = _dip_spec(8)
        asm = DIPTemplate().build(spec)
        names = [child.name for child in asm.children]
        assert "Body" in names
        lead_names = [n for n in names if n.startswith("Lead_")]
        assert len(lead_names) == 8

    def test_bbox_spans_below_board_and_body_above(self):
        from src.model3d.templates.dip import DIPTemplate

        spec = _dip_spec(8)
        asm = DIPTemplate().build(spec)
        bb = asm.toCompound().BoundingBox()

        # X = lead-span E (+ blade thickness), Y = body length D.
        assert bb.xlen == pytest.approx(spec.lead_span_E, abs=0.5)
        assert bb.ylen == pytest.approx(spec.body_length_D, abs=0.3)
        # CRUCIAL: leads pass through the board, so zmin is NEGATIVE (~ -3.0)...
        assert bb.zmin < 0
        assert bb.zmin == pytest.approx(-3.0, abs=0.05)
        # ...while the moulded body top sits at overall height A.
        assert bb.zmax == pytest.approx(spec.body_height_A, abs=0.05)

    def test_body_child_sits_above_the_board(self):
        from src.model3d.templates.dip import DIPTemplate

        spec = _dip_spec(8)
        asm = DIPTemplate().build(spec)
        body = next(c for c in asm.children if c.name == "Body")
        bb = body.toCompound().BoundingBox()

        # The body proper is clear of the board, standing on its A1 standoff.
        assert bb.zmin == pytest.approx(spec.standoff_A1, abs=0.02)
        assert bb.zmin > 0
        assert bb.zmax == pytest.approx(spec.body_height_A, abs=0.02)

    def test_lead_lowest_face_centre_is_the_through_hole(self):
        from src.model3d.templates.dip import DIPTemplate

        spec = _dip_spec(8)
        asm = DIPTemplate().build(spec)

        half_span = spec.lead_span_E / 2.0
        for child in asm.children:
            if not child.name.startswith("Lead_"):
                continue
            bb = child.toCompound().BoundingBox()
            # The tip (lowest -Z face) sits below the board at -3.0mm.
            assert bb.zmin == pytest.approx(-3.0, abs=0.02)
            # ...and centres on one of the two lead-span columns at +/- E/2.
            x_centre = (bb.xmin + bb.xmax) / 2.0
            assert abs(x_centre) == pytest.approx(half_span, abs=0.02)

    def test_dip14_is_parametric(self):
        from src.model3d.templates.dip import DIPTemplate

        spec = _dip_spec(14)
        asm = DIPTemplate().build(spec)
        lead_names = [c.name for c in asm.children if c.name.startswith("Lead_")]
        assert len(lead_names) == 14

        bb = asm.toCompound().BoundingBox()
        assert bb.xlen == pytest.approx(spec.lead_span_E, abs=0.5)
        assert bb.ylen == pytest.approx(spec.body_length_D, abs=0.3)
        assert bb.zmin == pytest.approx(-3.0, abs=0.05)
        assert bb.zmax == pytest.approx(spec.body_height_A, abs=0.05)
