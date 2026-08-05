"""Tests for the leadless package-body template (QFN / DFN / WSON / SON)."""
from __future__ import annotations

import cadquery as cq
import pytest

from src.model3d.spec import Body3DSpec
from src.model3d.templates.leadless import LeadlessTemplate


def _dfn8_spec() -> Body3DSpec:
    """DFN-8 dual-row leadless part."""
    return Body3DSpec(
        component_name="DFN8",
        package_type="DFN",
        package_family="DFN",
        lead_style="leadless",
        pin_count=8,
        pins_per_side=[4, 4, 0, 0],
        body_length_D=3.0,
        body_width_E1=3.0,
        body_height_A=0.9,
        standoff_A1=0.0,
        lead_span_E=3.0,
        lead_pitch_e=0.5,
        lead_width_b=0.25,
        lead_foot_L=0.4,
        dims_source="text",
        confidence="verified",
    )


def _qfn16_spec() -> Body3DSpec:
    """QFN-16 quad leadless part."""
    return Body3DSpec(
        component_name="QFN16",
        package_type="QFN",
        package_family="QFN",
        lead_style="leadless",
        pin_count=16,
        pins_per_side=[4, 4, 4, 4],
        body_length_D=4.0,
        body_width_E1=4.0,
        body_height_A=0.9,
        standoff_A1=0.0,
        lead_span_E=4.0,
        lead_pitch_e=0.5,
        lead_width_b=0.25,
        lead_foot_L=0.4,
        dims_source="text",
        confidence="verified",
    )


def test_dfn8_bounding_box_and_lead_count():
    spec = _dfn8_spec()
    asm = LeadlessTemplate().build(spec)

    bb = asm.toCompound().BoundingBox()
    assert bb.xlen == pytest.approx(spec.body_width_E1, abs=0.05)
    assert bb.ylen == pytest.approx(spec.body_length_D, abs=0.05)
    assert bb.zlen == pytest.approx(spec.body_height_A, abs=0.05)
    assert bb.zmin == pytest.approx(0.0, abs=0.05)

    leads = [c for c in asm.children if c.name.startswith("Lead_")]
    assert len(leads) == spec.pin_count


def test_terminal_lowest_face_on_seating_plane_near_edge():
    spec = _dfn8_spec()
    asm = LeadlessTemplate().build(spec)

    child = next(c for c in asm.children if c.name == "Lead_1")
    lowest = cq.Workplane(child.obj.val()).faces("<Z").val().Center()

    # Bottom face sits on the seating plane.
    assert lowest.z == pytest.approx(0.0, abs=0.01)
    # Pin 1 is the top of the left column: outer face on the -X body edge,
    # first pin along +Y.
    L = spec.lead_foot_L
    assert lowest.x == pytest.approx(-(spec.body_width_E1 / 2.0 - L / 2.0), abs=0.05)
    assert lowest.y == pytest.approx((4 - 1) / 2.0 * spec.lead_pitch_e, abs=0.05)


def test_qfn16_bounding_box_and_lead_count():
    spec = _qfn16_spec()
    asm = LeadlessTemplate().build(spec)

    bb = asm.toCompound().BoundingBox()
    assert bb.xlen == pytest.approx(spec.body_width_E1, abs=0.05)
    assert bb.ylen == pytest.approx(spec.body_length_D, abs=0.05)
    assert bb.zlen == pytest.approx(spec.body_height_A, abs=0.05)
    assert bb.zmin == pytest.approx(0.0, abs=0.05)

    leads = [c for c in asm.children if c.name.startswith("Lead_")]
    assert len(leads) == spec.pin_count
