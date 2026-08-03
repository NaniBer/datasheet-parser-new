"""
Tests for the 3D component-body model layer (src/model3d).

Milestone 1 vertical slice: SOIC gull-wing, end-to-end.

Reference part: SN74HC595 in SOIC-16 (wide body, DW). Dimensions are the
midpoints of the SOIC-16 mechanical drawing in
eval_output/74HC595_TI_dimensions.json (page 23):
    A 2.35-2.65, A1 0.10-0.25, b 0.31-0.51, D 9.80-10.00,
    E 10.00-10.65, e 1.27, L 0.40-1.27
"""
import pytest

# The flat extracted-dims dict, exactly as DimensionExtractor.extract() emits it.
SOIC16_DIMS = {
    "package_type": "SOIC-16",
    "unit": "mm",
    "e": 1.27,
    "E": 10.325,   # lead span, tip-to-tip
    "D": 9.90,     # body length
    "b": 0.41,
    "L": 0.835,
    "A": 2.50,     # overall height
    "A1": 0.175,   # standoff
    "dims_source": "text",
}


class TestBuildSpec:
    def test_soic16_maps_dims_and_disambiguates_wide_body(self):
        from src.model3d.spec import build_spec

        spec = build_spec(
            package_type="SOIC-16",
            pin_count=16,
            component_name="SN74HC595",
            extracted_dims=SOIC16_DIMS,
        )

        assert spec.component_name == "SN74HC595"
        assert spec.lead_style == "gullwing"
        assert spec.pin_count == 16
        assert spec.pins_per_side == [8, 8, 0, 0]

        assert spec.body_length_D == pytest.approx(9.90, abs=1e-6)
        assert spec.lead_span_E == pytest.approx(10.325, abs=1e-6)
        assert spec.body_height_A == pytest.approx(2.50, abs=1e-6)
        assert spec.standoff_A1 == pytest.approx(0.175, abs=1e-6)
        assert spec.lead_pitch_e == pytest.approx(1.27, abs=1e-6)
        assert spec.lead_width_b == pytest.approx(0.41, abs=1e-6)
        assert spec.lead_foot_L == pytest.approx(0.835, abs=1e-6)

        # E1 is not extracted here; a 16-pin SOIC is ambiguous (narrow D vs wide
        # DW). The extracted span (10.325) matches the WIDE JEDEC body, so the
        # spec must resolve body width to ~7.5mm, not the narrow default 3.9mm.
        assert spec.body_width_E1 == pytest.approx(7.5, abs=0.6)

        assert spec.dims_source == "text"
        assert spec.confidence == "verified"

    def test_missing_height_falls_back_and_flags_unverified(self):
        from src.model3d.spec import build_spec

        dims = {k: v for k, v in SOIC16_DIMS.items() if k not in ("A", "A1")}
        spec = build_spec(
            package_type="SOIC-16",
            pin_count=16,
            component_name="X",
            extracted_dims=dims,
        )
        # Height must still be a positive number (JEDEC-default fallback)...
        assert spec.body_height_A > 0
        assert spec.standoff_A1 >= 0
        # ...but the model must be flagged as not fully verified.
        assert spec.confidence == "unverified"


def _spec():
    from src.model3d.spec import build_spec
    return build_spec("SOIC-16", 16, "SN74HC595", SOIC16_DIMS)


class TestGullwingTemplate:
    def test_bbox_matches_span_length_height_and_seats_at_z0(self):
        from src.model3d.registry import select_template

        spec = _spec()
        asm = select_template(spec).build(spec)
        bb = asm.toCompound().BoundingBox()

        # X = lead span E (tip-to-tip), Y = body length D, Z = overall height A.
        assert bb.xlen == pytest.approx(10.325, abs=0.20)
        assert bb.ylen == pytest.approx(9.90, abs=0.30)
        assert bb.zlen == pytest.approx(2.50, abs=0.05)
        # Seating plane at Z=0; top of body at A.
        assert bb.zmin == pytest.approx(0.0, abs=0.02)
        assert bb.zmax == pytest.approx(2.50, abs=0.05)

    def test_has_body_and_one_node_per_lead(self):
        from src.model3d.registry import select_template

        spec = _spec()
        asm = select_template(spec).build(spec)
        names = [child.name for child in asm.children]
        assert "Body" in names
        lead_names = [n for n in names if n.startswith("Lead_")]
        assert len(lead_names) == 16

    def test_unsupported_lead_style_fails_closed(self):
        import dataclasses
        from src.model3d.registry import select_template

        spec = dataclasses.replace(_spec(), lead_style="leadless")
        with pytest.raises(Exception):
            select_template(spec)


class TestExporter:
    def test_writes_nonempty_step_and_glb(self, tmp_path):
        from src.model3d.registry import select_template
        from src.model3d.exporter import export_model

        spec = _spec()
        asm = select_template(spec).build(spec)

        paths = export_model(asm, str(tmp_path / "body"))

        step, glb = paths["step"], paths["glb"]
        assert step.endswith(".step") and glb.endswith(".glb")
        import os
        assert os.path.getsize(step) > 0
        assert os.path.getsize(glb) > 0

    def test_step_reimports_with_expected_span(self, tmp_path):
        import cadquery as cq
        from src.model3d.registry import select_template
        from src.model3d.exporter import export_model

        spec = _spec()
        asm = select_template(spec).build(spec)
        paths = export_model(asm, str(tmp_path / "body"))

        solid = cq.importers.importStep(paths["step"])
        bb = solid.val().BoundingBox()
        assert bb.xlen == pytest.approx(10.325, abs=0.20)  # lead span survives round-trip


class TestValidator:
    def _built(self):
        from src.model3d.registry import select_template
        spec = _spec()
        return select_template(spec).build(spec), spec

    def test_passes_for_matching_body(self):
        from src.model3d.validator import validate_body

        asm, spec = self._built()
        result = validate_body(asm, spec)
        assert result.ok is True
        assert result.issues == []
        assert result.metrics["lead_count"] == 16

    def test_flags_wrong_lead_count(self):
        import dataclasses
        from src.model3d.validator import validate_body

        asm, spec = self._built()
        wrong = dataclasses.replace(spec, pin_count=20)
        result = validate_body(asm, wrong)
        assert result.ok is False
        assert any("lead count" in i.lower() for i in result.issues)

    def test_flags_wrong_height(self):
        import dataclasses
        from src.model3d.validator import validate_body

        asm, spec = self._built()
        wrong = dataclasses.replace(spec, body_height_A=5.0)
        result = validate_body(asm, wrong)
        assert result.ok is False
        assert any("height" in i.lower() for i in result.issues)


class TestBuildBodyModel:
    def test_end_to_end_soic16(self, tmp_path):
        import os
        from src.model3d.builder import build_body_model

        result = build_body_model(
            package_type="SOIC-16",
            pin_count=16,
            component_name="SN74HC595",
            extracted_dims=SOIC16_DIMS,
            output_base=str(tmp_path / "hc595_body"),
        )

        assert result.success is True
        assert result.validated is True
        assert result.confidence == "verified"
        assert result.issues == []
        assert os.path.getsize(result.step_path) > 0
        assert os.path.getsize(result.glb_path) > 0

    def test_unsupported_family_skips_gracefully(self, tmp_path):
        from src.model3d.builder import build_body_model

        result = build_body_model(
            package_type="QFN-32",
            pin_count=32,
            component_name="X",
            extracted_dims={"package_type": "QFN-32", "e": 0.5, "dims_source": "text"},
            output_base=str(tmp_path / "qfn_body"),
        )

        assert result.success is False
        assert result.reason  # explains why the body was skipped
        assert result.step_path is None


@pytest.mark.integration
class TestPipelineHook:
    def test_process_both_emits_body_when_enabled(self, tmp_path):
        from src.main import process_datasheet_both
        from src.models.pin_data import PinData, PackageInfo, Pin

        pin_data = PinData(
            component_name="SN74HC595",
            package=PackageInfo(type="SOIC-16", pin_count=16, width=7.5, height=9.9),
            pins=[Pin(number=i, name=f"P{i}") for i in range(1, 17)],
            extraction_method="Table",
        )
        out = tmp_path / "hc595.glb"

        ok = process_datasheet_both(
            pin_data, out, extracted_dims=SOIC16_DIMS, emit_body_3d=True,
        )

        assert ok is True
        assert (tmp_path / "hc595_body.step").exists()
        assert (tmp_path / "hc595_body.glb").exists()

    def test_body_not_emitted_without_flag(self, tmp_path):
        from src.main import process_datasheet_both
        from src.models.pin_data import PinData, PackageInfo, Pin

        pin_data = PinData(
            component_name="SN74HC595",
            package=PackageInfo(type="SOIC-16", pin_count=16, width=7.5, height=9.9),
            pins=[Pin(number=i, name=f"P{i}") for i in range(1, 17)],
            extraction_method="Table",
        )
        out = tmp_path / "hc595.glb"

        process_datasheet_both(pin_data, out, extracted_dims=SOIC16_DIMS)

        assert not (tmp_path / "hc595_body.step").exists()
