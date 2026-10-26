"""Shared pytest configuration.

1. Hermetic LLM environment. ``src.chat_bot`` calls ``load_dotenv()`` at import
   time, and ``find_dotenv`` walks up from the source file, so a developer's real
   ``.env`` (with a real API key / OpenRouter base URL) would leak into the test
   process. That made the API-key tests environment-dependent and risked a test
   reaching a real endpoint. Tests must never depend on (or use) real
   credentials, so we disable dotenv loading and strip the LLM-related variables
   *before* any ``src`` module is imported. Individual tests still set what they
   need with ``monkeypatch.setenv``.

2. ``slow`` marker. Whole test modules that build GLBs / run CadQuery / load
   real PDFs are tagged ``slow`` here (by file, from ``--durations`` timings) so
   ``pytest -m "not slow"`` gives a fast everyday subset without hundreds of
   per-test edits. Tests already marked ``integration`` are also treated as slow.
"""

from __future__ import annotations

import os

import dotenv
import pytest

# --- 1. hermetic env --------------------------------------------------------

_LLM_ENV_VARS = (
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "FASTCHAT_API_KEY",
    "AGENTIC_ESCALATION_MODEL",
    "IMAGE_AI_URL",
)


def _no_dotenv(*_args, **_kwargs):  # pragma: no cover - trivial
    return False


# Patch before src.chat_bot does ``from dotenv import load_dotenv``.
dotenv.load_dotenv = _no_dotenv
for _var in _LLM_ENV_VARS:
    os.environ.pop(_var, None)


# --- 2. slow marker -----------------------------------------------------------

# Whole modules dominated by GLB generation / CadQuery solids / real-PDF parsing
# (measured with ``--durations``: most of their tests take seconds each).
SLOW_MODULES = frozenset(
    {
        "test_conformance_sym04_fixture.py",
        "test_end_to_end_body3d.py",
        "test_f04_provenance.py",
        "test_f3_pin1_marker.py",
        "test_fp17_component_height.py",
        "test_fp18_zero_orientation.py",
        "test_h3_pin_name_inside_body.py",
        "test_lay02_layer_id.py",
        "test_model3d.py",
        "test_model3d_quad_gullwing.py",
        "test_paste_mask_layer.py",
        "test_pipeline_deterministic_repair.py",
        "test_slice_c_sym01.py",
        "test_slice_c_sym04.py",
        "test_slice_c_sym05.py",
        "test_slice_c_sym07.py",
        "test_slice_c_sym08.py",
        "test_slice_c_sym11.py",
        "test_sym10_refdes_prefix.py",
        "test_ui01_not_rotatable.py",
        "test_v02_footprint_dims.py",
    }
)

# Individual slow tests (>= ~1s: build a GLB or parse a real PDF) inside modules
# that are otherwise fast unit tests. Keyed "<file>::<test or class>"; all
# parametrizations of a listed test are included.
SLOW_TESTS = frozenset(
    {
        "test_ad9106_land_pattern.py::test_glb_ep_paste_windows_and_pin_data",
        "test_agentic.py::test_repair_fixes_rev13_single_column_datasheet",
        "test_footprint_land_pattern_qc.py::test_through_hole_pin1_pad_is_square",
        "test_footprint_silk_qfn.py::test_qfn48_footprint_glb_passes_hierarchy_validation",
        "test_fp19_fab_pad_clearance.py::test_fab_clears_pads_across_families",
        "test_fp19_fab_pad_clearance.py::test_fab_clears_pads_with_extracted_dims",
        "test_fp19_fab_pad_clearance.py::test_fp19_passes_through_hole_body_over_annuli_but_clear_of_holes",
        "test_fp19_fab_pad_clearance.py::test_leadless_fab_clears_pads_and_stays_off_lead_span",
        "test_model3d_dip.py::TestDIPTemplate",
        "test_pin_direction.py::test_pga2311p_sides_match_the_qc_expectation",
        "test_qc_fixed_acceptance.py::test_leadless_footprint_has_exposed_pad",
        "test_qc_fixed_acceptance.py::test_smd_families_have_no_drilled_holes",
        "test_qc_fixed_acceptance.py::test_smd_pads_carry_f_paste",
        "test_qc_fixed_acceptance.py::test_solder_mask_margin_per_side",
        "test_qc_fixed_acceptance.py::test_through_hole_dip_does_have_holes",
        "test_qc_fixed_acceptance.py::test_through_hole_pads_have_no_paste",
        "test_repair_drawing_series.py::test_adv7180_48_lead_drawing",
        "test_slice_c_sym04_geometry.py::test_gated_symbol_sides_match_roles_and_stay_conformant",
        "test_slice_c_sym04_geometry.py::test_nc_pins_drawn_and_grouped_left",
        "test_solder_mask_margin.py::test_rect_pad_mask_drawn_at_full_margin_per_side",
        "test_suite.py::test_aliased_package_families_generate_valid_footprints",
        "test_suite.py::test_both_flag_produces_schematic_and_footprint_glb",
        "test_suite.py::test_build_pcb_footprint_populates_degraded_out",
        "test_suite.py::test_cli_exit_code_contract",
        "test_suite.py::test_cli_exit_zero_on_success",
        "test_suite.py::test_dfn_pinout_uses_deterministic_table_parser",
        "test_suite.py::test_dip8_footprint_matches_documented_hierarchy",
        "test_suite.py::test_dip8_footprint_uses_jedec_row_spacing",
        "test_suite.py::test_extract_rejects_wrong_variant_from_codeless_page",
        "test_suite.py::test_extract_vision_path_respects_part_number_designator",
        "test_suite.py::test_extracted_dims_still_override_jedec_defaults",
        "test_suite.py::test_failed_validation_leaves_no_footprint_file",
        "test_suite.py::test_footprint_glb_records_dims_provenance",
        "test_suite.py::test_footprint_pad_columns_centered_on_body",
        "test_suite.py::test_full_pipeline_dfn_pdf_to_pcb_footprint_glb",
        "test_suite.py::test_generated_dip28_matches_reference_glb_structure",
        "test_suite.py::test_generated_dip8_similar_to_reference_glb",
        "test_suite.py::test_glb_pin_extras_match_pad_spec",
        "test_suite.py::test_glb_through_hole_extras_use_pad_spec",
        "test_suite.py::test_grid_array_footprints_fail_closed",
        "test_suite.py::test_leadless_symbol_has_epad_pin",
        "test_suite.py::test_mpu_pinout_uses_deterministic_table_parser",
        "test_suite.py::test_pdip_footprint_is_through_hole_at_drill_spacing",
        "test_suite.py::test_schematic_glb_carries_frontend_extras",
        "test_suite.py::test_schematic_quad_side_codes",
        "test_suite.py::test_soic16_footprint_uses_jedec_defaults",
        "test_suite.py::test_sot23_8_footprint_grid",
        "test_suite.py::test_text_dims_work_without_table_of_contents",
        "test_suite.py::test_tssop16_footprint_uses_jedec_defaults",
        "test_symbol_label_number_placement.py::test_designator_node_is_anchored_above_body_top_left",
        "test_symbol_label_number_placement.py::test_pin_number_sits_on_the_leg_not_past_the_connection_end",
        "test_v03_alignment.py::test_v03_graded_pass_through_driver",
    }
)


def _is_slow(item) -> bool:
    if item.path.name in SLOW_MODULES or item.get_closest_marker("integration"):
        return True
    parts = item.nodeid.split("::")
    return len(parts) > 1 and f"{item.path.name}::{parts[1].split('[')[0]}" in SLOW_TESTS


def pytest_collection_modifyitems(config, items):
    for item in items:
        if _is_slow(item):
            item.add_marker(pytest.mark.slow)
