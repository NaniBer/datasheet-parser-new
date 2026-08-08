"""
Tests for the quad gull-wing (QFP / TQFP / LQFP) package-body template.

These tests build a Body3DSpec by hand (no shared registry / validator) and
assert directly on the cadquery assembly, following the shared coordinate
contract: millimetres, +Z up, seating plane at Z=0, origin at component centre.

Reference part: a square LQFP-32 (7x7 body, 9x9 including leads):
    e 0.8, E 9.0 (X lead span, tip-to-tip), D 9.0 (Y lead span, tip-to-tip),
    E1 7.0 (body width, X), b 0.37, L 0.6, A 1.6, A1 0.10.
"""
import pytest

import cadquery as cq

from src.model3d.spec import Body3DSpec


def _foot_center(assembly, pin):
    """(x, y) of a lead's seating-plane foot, from its lowest (-Z) face."""
    child = next(c for c in assembly.children if c.name == f"Lead_{pin}")
    wp = child.obj if isinstance(child.obj, cq.Workplane) else cq.Workplane(child.obj)
    center = wp.faces("<Z").val().Center()
    return center.x, center.y


def _lqfp32_spec() -> Body3DSpec:
    """A square LQFP-32: 8 leads per side, 9x9 tip-to-tip, 7x7 body."""
    return Body3DSpec(
        component_name="LQFP32_TEST",
        package_type="LQFP-32",
        package_family="LQFP",
        lead_style="quad_gullwing",
        pin_count=32,
        pins_per_side=[8, 8, 8, 8],   # [left, right, top, bottom]
        body_length_D=9.0,
        body_width_E1=7.0,
        body_height_A=1.6,
        standoff_A1=0.10,
        lead_span_E=9.0,
        lead_pitch_e=0.8,
        lead_width_b=0.37,
        lead_foot_L=0.6,
        dims_source="text",
        confidence="verified",
    )


class TestQuadGullwingTemplate:
    def test_has_body_and_one_node_per_lead(self):
        from src.model3d.templates.quad_gullwing import QuadGullwingTemplate

        spec = _lqfp32_spec()
        asm = QuadGullwingTemplate().build(spec)

        names = [child.name for child in asm.children]
        assert "Body" in names
        lead_names = [n for n in names if n.startswith("Lead_")]
        assert len(lead_names) == spec.pin_count == 32

    def test_bbox_matches_spans_height_and_seats_at_z0(self):
        from src.model3d.templates.quad_gullwing import QuadGullwingTemplate

        spec = _lqfp32_spec()
        bb = QuadGullwingTemplate().build(spec).toCompound().BoundingBox()

        # X = lead span E, Y = lead span D (square here), Z = overall height A.
        assert bb.xlen == pytest.approx(spec.lead_span_E, abs=0.05)      # 9.0
        assert bb.ylen == pytest.approx(spec.body_length_D, abs=0.05)    # 9.0
        assert bb.zlen == pytest.approx(spec.body_height_A, abs=0.05)    # 1.6
        # Seating plane at Z=0; top of body at A.
        assert bb.zmin == pytest.approx(0.0, abs=0.05)
        assert bb.zmax == pytest.approx(spec.body_height_A, abs=0.05)

    def test_ccw_pin_numbering(self):
        from src.model3d.templates.quad_gullwing import QuadGullwingTemplate

        spec = _lqfp32_spec()
        asm = QuadGullwingTemplate().build(spec)

        # Foot tips: left/right at x = +/- E/2, top/bottom at y = +/- D/2. The
        # flat foot centre sits L/2 inboard of the tip.
        x_left = -(spec.lead_span_E / 2.0)
        x_right = spec.lead_span_E / 2.0
        y_bottom = -(spec.body_length_D / 2.0)
        y_top = spec.body_length_D / 2.0
        y_hi = (8 - 1) / 2.0 * spec.lead_pitch_e     # topmost of an 8-pin column

        # Pin 1: top of the LEFT side.
        x1, y1 = _foot_center(asm, 1)
        assert x1 < x_left + spec.lead_foot_L        # on the left column
        assert y1 == pytest.approx(y_hi, abs=0.05)

        # Numbers run DOWN the left side: pin 8 is the bottom of the left column.
        x8, y8 = _foot_center(asm, 8)
        assert x8 < x_left + spec.lead_foot_L
        assert y8 == pytest.approx(-y_hi, abs=0.05)
        assert y8 < y1                               # descending down the side

        # Pin 9 starts the BOTTOM row, running left -> right.
        x9, y9 = _foot_center(asm, 9)
        assert y9 < y_bottom + spec.lead_foot_L      # on the bottom row
        x16, _ = _foot_center(asm, 16)
        assert x16 > x9                              # left -> right across bottom

        # Pin 17 starts the RIGHT side, running bottom -> top.
        x17, y17 = _foot_center(asm, 17)
        assert x17 > x_right - spec.lead_foot_L      # on the right column
        _, y24 = _foot_center(asm, 24)
        assert y24 > y17                             # bottom -> up the right side

        # Pin 25 starts the TOP row, running right -> left.
        x25, y25 = _foot_center(asm, 25)
        assert y25 > y_top - spec.lead_foot_L        # on the top row
        x32, _ = _foot_center(asm, 32)
        assert x32 < x25                             # right -> left across top

    def test_non_square_qfp(self):
        from src.model3d.templates.quad_gullwing import QuadGullwingTemplate

        # Rectangular QFP: longer in Y (D=13) than X (E=9), so more leads on the
        # left/right columns than on the top/bottom rows.
        spec = Body3DSpec(
            component_name="QFP_RECT",
            package_type="QFP-32",
            package_family="QFP",
            lead_style="quad_gullwing",
            pin_count=32,
            pins_per_side=[12, 12, 4, 4],   # [left, right, top, bottom]
            body_length_D=13.0,
            body_width_E1=7.0,
            body_height_A=1.6,
            standoff_A1=0.10,
            lead_span_E=9.0,
            lead_pitch_e=0.8,
            lead_width_b=0.37,
            lead_foot_L=0.6,
            dims_source="text",
            confidence="verified",
        )
        asm = QuadGullwingTemplate().build(spec)

        lead_names = [c.name for c in asm.children if c.name.startswith("Lead_")]
        assert len(lead_names) == 32

        bb = asm.toCompound().BoundingBox()
        assert bb.xlen == pytest.approx(spec.lead_span_E, abs=0.05)      # 9.0
        assert bb.ylen == pytest.approx(spec.body_length_D, abs=0.05)    # 13.0
        assert bb.zlen == pytest.approx(spec.body_height_A, abs=0.05)    # 1.6
        assert bb.zmin == pytest.approx(0.0, abs=0.05)

        # CCW numbering still starts at the top of the left column.
        x1, y1 = _foot_center(asm, 1)
        assert x1 < 0 and y1 > 0
        assert y1 == pytest.approx((12 - 1) / 2.0 * spec.lead_pitch_e, abs=0.05)
