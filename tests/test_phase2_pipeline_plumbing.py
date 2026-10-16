"""Phase 2 tests: ComponentRecord plumbed through the pipeline, output unchanged.

The rigorous offline proof that "generated output is unchanged" is that the
inputs handed to the builders are byte-identical: the builders are deterministic,
so identical (package_type, pin_count, component_name, pins) + identical
extracted_dims => identical GLB/STEP. These tests assert that equivalence via
the actual builder-boundary helper used in main.py, plus that the record
survives the pipeline's enrichment with its seam identity intact.
"""
from src.main import _builder_inputs_from_record
from src.models import ComponentRecord
from src.models.pin_data import PinData, PackageInfo, Pin
from src.schematic_generator import pin_data_to_builder_format


def _enriched_multi() -> PinData:
    """A PinData as it looks after extraction + ordering ground truth."""
    return PinData(
        component_name="SN74HC595",
        packages=[
            {"type": "SOIC-16", "pin_count": 16, "width": 3.9, "height": 9.9,
             "pitch": 1.27, "pins": [
                 {"number": 1, "name": "QB", "function": "output"},
                 {"number": 16, "name": "VCC", "function": "power"}]},
            {"type": "TSSOP-16", "pin_count": 16, "pins": [
                {"number": 1, "name": "QB", "function": "output"}]},
        ],
        selected_package_index=0,
        ordered_pin_count=16,
        ordered_package_type="SOIC-16",
        validation_errors=["unit test flag"],
    )


def _enriched_single() -> PinData:
    return PinData(
        component_name="LM358",
        package=PackageInfo(type="DIP-8", pin_count=8, width=6.35, height=9.2),
        pins=[Pin(1, "OUT1", "output"), Pin(8, "VCC", "power")],
        footprint_unsupported_reason=None,
    )


# --- builder inputs are byte-identical (=> output unchanged) ------------------
def test_builder_inputs_identical_multi_with_dims():
    pd = _enriched_multi()
    dims = {"e": 1.27, "E": 6.0, "D": 9.9, "E1": 3.9, "b": 0.41,
            "b_max": 0.51, "L": 0.84, "dims_source": "text", "c": 0.2, "D1": 3.8}
    record = ComponentRecord.from_pin_data(pd, part_number="SN74HC595D")

    bpd, bdims = _builder_inputs_from_record(record, pd, dims)

    assert pin_data_to_builder_format(bpd, part_number="SN74HC595D") == \
           pin_data_to_builder_format(pd, part_number="SN74HC595D")
    # dims survive the round-trip byte-for-byte, incl. unmapped keys
    assert bdims == dims
    # legacy flags the pipeline reads are preserved
    assert bpd.validation_errors == ["unit test flag"]


def test_builder_inputs_identical_single_no_dims():
    pd = _enriched_single()
    record = ComponentRecord.from_pin_data(pd, part_number=None)
    bpd, bdims = _builder_inputs_from_record(record, pd, None)
    assert pin_data_to_builder_format(bpd) == pin_data_to_builder_format(pd)
    assert bdims is None


def test_dims_passthrough_lossless_for_unmapped_keys():
    from src.models import Mechanical
    dims = {"e": 0.5, "E": 6.4, "D2": 2.6, "E2": 2.6, "A": 1.0, "A1": 0.05,
            "c": 0.2, "D1": 4.8, "dims_source": "vision"}
    assert Mechanical.from_flat_dims(dims).to_flat_dims() == dims


# --- the record survives the pipeline with seam identity intact ---------------
def test_record_survives_enrichment_preserving_identity():
    pd = PinData(component_name="X",
                 package=PackageInfo(type="SOIC-8", pin_count=8, width=0, height=0),
                 pins=[Pin(1, "A"), Pin(2, "B")])
    rec = ComponentRecord.from_pin_data(pd, part_number="XPART")   # seam
    assert rec.identity.mpn == "XPART" and rec.component_id == "XPART"

    # enrichment mutates the legacy object after the seam
    pd.ordered_pin_count = 8
    pd.ordered_package_type = "SOIC-8"
    pd.footprint_unsupported_reason = "module: SiP"
    pd.validation_errors = ["ordering mismatch"]

    rec.update_from_pin_data(pd)                                    # builder boundary
    # geometry/flags reflect the enriched state...
    assert rec.ordered_pin_count == 8
    assert rec.ordered_package_type == "SOIC-8"
    assert rec.footprint_unsupported_reason == "module: SiP"
    assert rec.validation_errors == ["ordering mismatch"]
    # ...while the seam identity is preserved (not rebuilt away)
    assert rec.identity.mpn == "XPART" and rec.component_id == "XPART"
    assert rec.schema_version == "1.0" and rec.version == 1


def test_footprint_unsupported_flag_round_trips():
    pd = _enriched_single()
    pd.footprint_unsupported_reason = "module land pattern differs"
    rec = ComponentRecord.from_pin_data(pd)
    assert rec.to_pin_data().footprint_unsupported_reason == "module land pattern differs"


# --- caller package string -> ordered pin count (multi-variant disambiguation) ---
# Regression: ADV7180 ships both a 48- and a 64-lead LQFP pin table. A caller
# passing only package="LQFP-48" (no explicit pin count) must still select the
# 48-lead variant; before the fix, ordered_pin_count stayed None, the 64-lead
# table was read, and pins numbered past 48 (duplicate names) were emitted.
from src.main import _pin_count_from_package_string, _apply_caller_variant


def test_pin_count_derived_from_package_string():
    assert _pin_count_from_package_string("LQFP-48") == 48
    assert _pin_count_from_package_string("TQFP-48") == 48
    assert _pin_count_from_package_string("XSON-8") == 8
    assert _pin_count_from_package_string("LFCSP-32") == 32
    assert _pin_count_from_package_string("PDIP-16") == 16
    assert _pin_count_from_package_string("WLCSP-25") == 25


def test_pin_count_not_derived_for_case_code_families():
    # SOT/TO/SC suffixes are package case codes, NOT lead counts.
    for s in ("SOT-23", "SOT-89", "SOT-223", "TO-220", "TO-92", "SC-70", "SC70"):
        assert _pin_count_from_package_string(s) is None, s
    # No trailing number / bare family -> nothing derived.
    for s in ("microSD", "DIP", "LQFP", "", None):
        assert _pin_count_from_package_string(s) is None, s


def test_apply_caller_variant_seeds_count_from_package_only():
    pd = PinData(component_name="ADV7180")
    _apply_caller_variant(pd, package="LQFP-48", pin_count=None)
    assert pd.ordered_package_type == "LQFP-48"
    assert pd.ordered_pin_count == 48  # derived, enables 48- vs 64-lead selection


def test_explicit_pin_count_wins_over_package_string():
    pd = PinData(component_name="ADV7180")
    _apply_caller_variant(pd, package="LQFP-48", pin_count=64)
    assert pd.ordered_pin_count == 64  # explicit caller count is authoritative


def test_apply_caller_variant_no_count_for_sot():
    pd = PinData(component_name="BAV99")
    _apply_caller_variant(pd, package="SOT-23", pin_count=None)
    assert pd.ordered_package_type == "SOT-23"
    assert pd.ordered_pin_count is None  # case code must not become a pin count
