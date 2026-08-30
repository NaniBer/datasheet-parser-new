"""Slice B: dimension tolerances + provenance captured, output-neutral.

Proves _flatten now preserves min/max for every field (was b/L only),
from_flat_dims builds Dimension{min,nom,max} + Provenance, and the flat dict the
builders consume is unchanged (to_flat_dims byte-identical round-trip).
"""
from src.pdf_extractor.dimension_extractor import DimensionExtractor
from src.models import Mechanical, ComponentRecord
from src.models.pin_data import PinData, PackageInfo, Pin


# --- _flatten preserves tolerances for every field ---------------------------
def test_flatten_emits_min_max_for_all_fields():
    raw = {
        "package_type": "SOIC-16", "unit": "mm",
        "dimensions": {
            "e": "1.27",                              # scalar -> nominal only
            "E": {"min": "3.80", "max": "4.00"},
            "A": {"min": "1.35", "max": "1.75"},
            "b": {"min": "0.31", "max": "0.51"},
        },
    }
    flat = DimensionExtractor()._flatten(raw)
    # nominal (midpoint) unchanged
    assert flat["E"] == (3.80 + 4.00) / 2
    assert flat["A"] == (1.35 + 1.75) / 2
    assert flat["e"] == 1.27 and "e_min" not in flat      # scalar -> no tolerance
    # tolerances now preserved for EVERY dict field (was b/L only)
    assert flat["E_min"] == 3.80 and flat["E_max"] == 4.00
    assert flat["A_min"] == 1.35 and flat["A_max"] == 1.75
    assert flat["b_min"] == 0.31 and flat["b_max"] == 0.51   # still there


# --- from_flat_dims builds Dimension{min,nom,max} + Provenance ----------------
def test_from_flat_dims_tolerances_and_provenance():
    dims = {
        "e": 1.27, "E": 6.0, "E_min": 5.8, "E_max": 6.2,
        "A": 1.5, "A_min": 1.35, "A_max": 1.75,
        "b": 0.41, "b_min": 0.31, "b_max": 0.51,
        "D2": 2.6, "D2_min": 2.5, "D2_max": 2.7,
        "dims_source": "vision", "_page": 30,
    }
    m = Mechanical.from_flat_dims(dims)
    assert (m.lead_span_E.min, m.lead_span_E.nom, m.lead_span_E.max) == (5.8, 6.0, 6.2)
    assert (m.body_height_A.min, m.body_height_A.max) == (1.35, 1.75)
    assert (m.lead_width_b.min, m.lead_width_b.max) == (0.31, 0.51)
    assert m.thermal_pad["D2"].nom == 2.6 and m.thermal_pad["D2"].min == 2.5
    # provenance built from the reserved keys and attached to the dimensions
    assert m.lead_span_E.provenance.page == 30
    assert m.lead_span_E.provenance.method == "vision"
    assert m.lead_pitch_e.provenance.page == 30


def test_no_provenance_keys_means_none():
    m = Mechanical.from_flat_dims({"e": 1.27, "E": 6.0})
    assert m.lead_span_E.provenance is None


# --- OUTPUT-NEUTRAL: the flat dict builders consume is byte-identical ---------
def test_to_flat_dims_round_trips_byte_identical():
    dims = {
        "e": 0.5, "E": 6.4, "E_min": 6.2, "E_max": 6.6,
        "b": 0.25, "b_min": 0.19, "b_max": 0.30,
        "D2": 2.6, "E2": 2.6, "A": 1.0, "A_min": 0.95, "A_max": 1.05,
        "c": 0.2, "D1": 4.8, "dims_source": "vision", "_page": 12,
    }
    assert Mechanical.from_flat_dims(dims).to_flat_dims() == dims


def test_builder_key_projection_unchanged():
    # The keys the footprint/body builders actually read are unchanged by the
    # added tolerance/provenance keys.
    dims = {"e": 1.27, "E": 6.0, "E_min": 5.8, "E_max": 6.2, "b": 0.41,
            "b_max": 0.51, "L": 0.84, "dims_source": "text", "_page": 5}
    out = Mechanical.from_flat_dims(dims).to_flat_dims()
    for k in ("e", "E", "D", "E1", "D1", "b", "L", "b_max", "L_max", "A", "A1",
              "D2", "E2", "dims_source"):
        assert out.get(k) == dims.get(k)     # every builder-read key identical


def test_record_carries_dims_through_pipeline_helper():
    pd = PinData(component_name="X",
                 package=PackageInfo(type="SOIC-8", pin_count=8, width=0, height=0),
                 pins=[Pin(1, "VCC"), Pin(2, "GND")])
    dims = {"e": 1.27, "E": 6.0, "E_min": 5.8, "E_max": 6.2, "dims_source": "vision", "_page": 9}
    rec = ComponentRecord.from_pin_data(pd, extracted_dims=dims)
    mech = rec.selected_mechanical()
    assert mech.lead_span_E.min == 5.8 and mech.lead_span_E.max == 6.2
    assert mech.lead_span_E.provenance.page == 9
    # still byte-identical for the builders
    assert mech.to_flat_dims() == dims
