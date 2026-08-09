"""Tests for the DIP through-hole package-body template (src/model3d/templates/dip.py).

Reference part: a generic DIP-8 (PDIP, 300-mil / 7.62mm row spacing). Unlike the
surface-mount gull-wing families, DIP leads pass straight DOWN through the board,
so the assembly geometry extends BELOW the seating plane (Z<0). These tests build
Body3DSpec instances by hand and exercise the template directly -- they do NOT go
through the shared registry or validator (the validator is not through-hole-aware).
"""
import pytest

from src.model3d.spec import Body3DSpec


def _lead_bottom_center(child):
    """(x, y) of a lead child's lowest (-Z) face -- the through-hole foot."""
    center = child.obj.faces("<Z").val().Center()
    return center.x, center.y


def _lead_top_center(child):
    """(x, y) of a lead child's highest (+Z) face -- the body-exit shoulder."""
    center = child.obj.faces(">Z").val().Center()
    return center.x, center.y


def _span_x(centers):
    xs = [c[0] for c in centers]
    return max(xs) - min(xs)


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

    def test_lead_foot_is_the_through_hole_at_row_spacing(self):
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
            # The FOOT (lowest-face centre, not the bbox centre) seats on one of
            # the two through-hole columns at +/- E/2 -- what the validator reads.
            fx, _ = _lead_bottom_center(child)
            assert abs(fx) == pytest.approx(half_span, abs=0.02)

    def test_leads_splay_outward_below_the_shoulder(self):
        """Tip row spacing (feet at E) is wider than the body-exit spacing."""
        from src.model3d.templates.dip import DIPTemplate

        spec = _dip_spec(8)          # E (7.62) > body width E1 (6.35) -> splay
        assert spec.lead_span_E > spec.body_width_E1
        asm = DIPTemplate().build(spec)

        leads = [c for c in asm.children if c.name.startswith("Lead_")]
        foot_span = _span_x(_lead_bottom_center(c) for c in leads)
        exit_span = _span_x(_lead_top_center(c) for c in leads)

        # Feet seat at the mounting row spacing E...
        assert foot_span == pytest.approx(spec.lead_span_E, abs=0.02)
        # ...while the leads exit the body at (roughly) the narrower body width.
        assert exit_span == pytest.approx(spec.body_width_E1, abs=0.05)
        # The splay is real: the tips are wider than the body's lead exit.
        assert foot_span > exit_span + 0.5

    def test_protrusion_is_parametric_from_lead_length(self):
        from src.model3d.templates.dip import DIPTemplate

        spec = _dip_spec(8)
        spec.lead_foot_L = 3.30           # datasheet JEDEC lead length L
        asm = DIPTemplate().build(spec)
        bb = asm.toCompound().BoundingBox()
        # Leads now protrude the datasheet L below the board, not the default.
        assert bb.zmin == pytest.approx(-3.30, abs=0.02)

    def test_validate_body_passes_for_dip8_and_dip16(self):
        from src.model3d.templates.dip import DIPTemplate
        from src.model3d.validator import validate_body

        for pin_count in (8, 16):
            spec = _dip_spec(pin_count)
            asm = DIPTemplate().build(spec)
            res = validate_body(asm, spec)
            assert res.ok, res.issues
            assert res.metrics["lead_count"] == pin_count
            assert res.metrics["z_min"] < 0     # leads pass below the board

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
