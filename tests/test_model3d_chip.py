"""
Tests for the CHIP 2-terminal package template (src/model3d/templates/chip.py).

Surface-mount passives (resistors / capacitors / inductors): 0201, 0402, 0603,
0805, 1206. A rectangular body with two metallized end caps along the long (X)
axis. Coordinate contract: millimetres, +Z up, seating plane at Z=0, origin at
the component centre.

Specs are built by hand (no registry / validator) so this template can be
exercised before the parent wires it into spec.py and the registry.
"""
import pytest

from src.model3d.spec import Body3DSpec


def _chip_spec(D, E1, A, L) -> Body3DSpec:
    """A minimal two-terminal chip spec (an 0805-style passive by default)."""
    return Body3DSpec(
        component_name="CHIP",
        package_type="0805",
        package_family="R",
        lead_style="chip",
        pin_count=2,
        pins_per_side=[1, 1, 0, 0],
        body_length_D=D,
        body_width_E1=E1,
        body_height_A=A,
        standoff_A1=0.0,
        lead_span_E=D,
        lead_pitch_e=0.0,
        lead_width_b=0.0,
        lead_foot_L=L,
        dims_source="text",
        confidence="verified",
    )


class TestChipTemplate:
    def test_bbox_matches_body_dims_and_seats_at_z0(self):
        from src.model3d.templates.chip import ChipTemplate

        # 0805: 2.0 x 1.25 x 0.5, terminal band 0.4.
        spec = _chip_spec(D=2.0, E1=1.25, A=0.5, L=0.4)
        asm = ChipTemplate().build(spec)
        bb = asm.toCompound().BoundingBox()

        # X = body length D (long axis), Y = body width E1, Z = height A.
        assert bb.xlen == pytest.approx(2.0, abs=0.05)
        assert bb.ylen == pytest.approx(1.25, abs=0.05)
        assert bb.zlen == pytest.approx(0.5, abs=0.05)
        # Seating plane at Z=0.
        assert bb.zmin == pytest.approx(0.0, abs=0.05)

    def test_exactly_two_end_cap_terminals(self):
        from src.model3d.templates.chip import ChipTemplate

        spec = _chip_spec(D=2.0, E1=1.25, A=0.5, L=0.4)
        asm = ChipTemplate().build(spec)
        names = [child.name for child in asm.children]

        assert "Body" in names
        lead_names = [n for n in names if n.startswith("Lead_")]
        assert lead_names == ["Lead_1", "Lead_2"]

    def test_terminal_contacts_sit_at_x_ends_on_seating_plane(self):
        from src.model3d.templates.chip import ChipTemplate

        D, E1, A, L = 2.0, 1.25, 0.5, 0.4
        spec = _chip_spec(D=D, E1=E1, A=A, L=L)
        asm = ChipTemplate().build(spec)

        contacts = {}
        for child in asm.children:
            if not child.name.startswith("Lead_"):
                continue
            bb = child.toCompound().BoundingBox()
            contacts[child.name] = (
                (bb.xmin + bb.xmax) / 2.0,   # lowest-face centre X
                (bb.ymin + bb.ymax) / 2.0,   # lowest-face centre Y
                bb.zmin,                     # lowest face Z
            )

        band = L
        x1, y1, z1 = contacts["Lead_1"]
        x2, y2, z2 = contacts["Lead_2"]

        # Lead_1 at -X end, Lead_2 at +X end, both centred in Y on the board.
        assert x1 == pytest.approx(-(D / 2.0 - band / 2.0), abs=0.02)
        assert x2 == pytest.approx(+(D / 2.0 - band / 2.0), abs=0.02)
        assert y1 == pytest.approx(0.0, abs=0.02)
        assert y2 == pytest.approx(0.0, abs=0.02)
        assert z1 == pytest.approx(0.0, abs=0.02)
        assert z2 == pytest.approx(0.0, abs=0.02)

    def test_parametric_for_0402(self):
        from src.model3d.templates.chip import ChipTemplate

        # 0402: 1.0 x 0.5 x 0.35, terminal band 0.2.
        spec = _chip_spec(D=1.0, E1=0.5, A=0.35, L=0.2)
        asm = ChipTemplate().build(spec)
        bb = asm.toCompound().BoundingBox()

        assert bb.xlen == pytest.approx(1.0, abs=0.05)
        assert bb.ylen == pytest.approx(0.5, abs=0.05)
        assert bb.zlen == pytest.approx(0.35, abs=0.05)
        assert bb.zmin == pytest.approx(0.0, abs=0.05)
        assert len([c for c in asm.children if c.name.startswith("Lead_")]) == 2

    def test_default_band_when_L_absent(self):
        from src.model3d.templates.chip import ChipTemplate

        # No lead_foot_L: band defaults to a fraction of D, so caps stay inside
        # the body and the overall bounding box is still exactly D x E1 x A.
        spec = _chip_spec(D=2.0, E1=1.25, A=0.5, L=0.0)
        asm = ChipTemplate().build(spec)
        bb = asm.toCompound().BoundingBox()

        assert bb.xlen == pytest.approx(2.0, abs=0.05)
        assert bb.ylen == pytest.approx(1.25, abs=0.05)
        assert bb.zlen == pytest.approx(0.5, abs=0.05)
