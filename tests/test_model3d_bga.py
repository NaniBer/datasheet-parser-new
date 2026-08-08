"""Tests for the BGA / LGA grid-array package-body template."""
from __future__ import annotations

import math

import pytest

from src.model3d.spec import Body3DSpec
from src.model3d.templates.bga import BgaTemplate


def _bga_spec(pin_count: int) -> Body3DSpec:
    """A near-square grid-array part (BGA) with the given ball count."""
    return Body3DSpec(
        component_name=f"BGA{pin_count}",
        package_type="BGA",
        package_family="BGA",
        lead_style="bga",
        pin_count=pin_count,
        pins_per_side=[0, 0, 0, 0],   # not meaningful for a grid array
        body_length_D=8.0,
        body_width_E1=8.0,
        body_height_A=1.4,
        standoff_A1=0.0,
        lead_span_E=8.0,
        lead_pitch_e=0.8,
        lead_width_b=0.5,             # ball diameter
        lead_foot_L=0.0,
        dims_source="text",
        confidence="verified",
    )


def test_lead_style():
    assert BgaTemplate.lead_style == "bga"


def test_ball_count_64():
    spec = _bga_spec(64)
    asm = BgaTemplate().build(spec)
    balls = [c for c in asm.children if c.name.startswith("Lead_")]
    assert len(balls) == 64


def test_ball_count_depopulated_63():
    spec = _bga_spec(63)
    asm = BgaTemplate().build(spec)
    balls = [c for c in asm.children if c.name.startswith("Lead_")]
    assert len(balls) == 63


def test_balls_rest_on_seating_plane():
    spec = _bga_spec(64)
    asm = BgaTemplate().build(spec)
    bb = asm.toCompound().BoundingBox()
    assert bb.zmin == pytest.approx(0.0, abs=0.02)


def test_overall_height_matches_A():
    spec = _bga_spec(64)
    asm = BgaTemplate().build(spec)
    bb = asm.toCompound().BoundingBox()
    assert bb.zlen == pytest.approx(spec.body_height_A, abs=0.05)


def test_body_extents_match_E1_D():
    spec = _bga_spec(64)
    asm = BgaTemplate().build(spec)
    body = next(c for c in asm.children if c.name == "Body")
    bb = body.obj.val().BoundingBox()
    assert bb.xlen == pytest.approx(spec.body_width_E1, abs=0.1)
    assert bb.ylen == pytest.approx(spec.body_length_D, abs=0.1)


def test_grid_is_near_square():
    # 64 balls -> 8x8 grid; verify the ball footprint spans the expected pitch.
    spec = _bga_spec(64)
    asm = BgaTemplate().build(spec)
    cols = math.ceil(math.sqrt(spec.pin_count))
    balls = [c for c in asm.children if c.name.startswith("Lead_")]
    xs = sorted({round(b.obj.val().Center().x, 3) for b in balls})
    # 8 distinct columns spaced at pitch e.
    assert len(xs) == cols
    assert (xs[1] - xs[0]) == pytest.approx(spec.lead_pitch_e, abs=0.01)
