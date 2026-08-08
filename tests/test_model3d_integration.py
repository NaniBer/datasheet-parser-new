"""Integration tests for the parent wiring of the 3D body layer.

The per-template suites (test_model3d_bga, _powertab, _leadless, ...) test each
generator in isolation. These tests cover the wiring that joins them to the
spec/registry: family -> lead_style routing, the new c / exposed-pad spec
fields flowing from extracted_dims into geometry, and the fail-closed guarantee
for still-unsupported families.
"""
from src.model3d.registry import select_template
from src.model3d.spec import build_spec


def _leads(asm):
    return sum(1 for c in asm.children if c.name.startswith("Lead_"))


class TestPowerTabRouting:
    def test_to220_routes_to_power_tab(self):
        # The footprint-family detector does not recognise TO-220; build_spec
        # must still route it to the power_tab template off the raw string.
        spec = build_spec("TO-220", 3, "LM317", {"e": 2.54, "dims_source": "text"})
        assert spec.lead_style == "power_tab"
        asm = select_template(spec).build(spec)
        assert _leads(asm) == 3
        assert any(c.name == "Tab" for c in asm.children)

    def test_dpak_routes_to_power_tab(self):
        spec = build_spec("DPAK", 3, "X", {"e": 2.28})
        assert spec.lead_style == "power_tab"


class TestExposedPadWiring:
    def test_qfn_with_d2_e2_emits_exposed_pad(self):
        spec = build_spec(
            "QFN-32", 32, "X",
            {"e": 0.5, "D": 5.0, "E": 5.0, "E1": 5.0,
             "D2": 3.6, "E2": 3.6, "A": 0.9, "A1": 0.0, "dims_source": "text"},
        )
        assert spec.exposed_pad == (3.6, 3.6)
        asm = select_template(spec).build(spec)
        assert any(c.name == "ExposedPad" for c in asm.children)

    def test_qfn_without_exposed_pad_has_none(self):
        spec = build_spec("QFN-32", 32, "X", {"e": 0.5, "D": 5.0, "E": 5.0})
        assert spec.exposed_pad is None
        asm = select_template(spec).build(spec)
        assert not any(c.name == "ExposedPad" for c in asm.children)


class TestLeadThicknessWiring:
    def test_c_flows_from_dims(self):
        spec = build_spec("SOIC-8", 8, "X", {"e": 1.27, "c": 0.19, "dims_source": "text"})
        assert spec.lead_thickness_c == 0.19

    def test_c_absent_is_none(self):
        spec = build_spec("SOIC-8", 8, "X", {"e": 1.27})
        assert spec.lead_thickness_c is None


class TestGridArrayNowSupported:
    def test_bga_builds_the_pin_count_balls(self):
        spec = build_spec("BGA-64", 64, "X", {"e": 0.8, "dims_source": "text"})
        assert spec.lead_style == "bga"
        assert _leads(select_template(spec).build(spec)) == 64


class TestUnsupportedFamilyFailsClosed:
    def test_lccc_jlead_fails_closed(self):
        import pytest

        spec = build_spec("LCCC-20", 20, "X", {"e": 1.27})
        assert spec.lead_style == "jlead"
        with pytest.raises(Exception):
            select_template(spec)
