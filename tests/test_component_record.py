"""Phase 1 tests for Component Record v1 (data model + compatibility layer).

These prove the schema can represent everything the current pipeline extracts,
that pins and dimensions live in one record, that Dimension carries min/nom/max,
that provenance attaches, and that a BLOCKED status is representable. No
generation, prompt, or extraction behaviour is exercised here.
"""
from src.models import (
    ComponentRecord, Dimension, Identity, Mechanical, PackageVariant,
    Provenance, RecordPin,
)
from src.models.pin_data import PinData, PackageInfo, Pin


def _legacy_multi_package() -> PinData:
    """A PinData shaped like today's multi-variant LLM extraction output."""
    return PinData(
        component_name="SN74HC595",
        packages=[
            {"type": "SOIC-16", "pin_count": 16, "pins": [
                {"number": 1, "name": "QB", "function": "output"},
                {"number": 16, "name": "VCC", "function": "power"},
            ]},
            {"type": "TSSOP-16", "pin_count": 16, "pins": [
                {"number": 1, "name": "QB", "function": "output"},
            ]},
        ],
        selected_package_index=0,
        ordered_pin_count=16,
        ordered_package_type="SOIC-16",
    )


def _legacy_single_package() -> PinData:
    return PinData(
        component_name="LM358",
        package=PackageInfo(type="DIP-8", pin_count=8, width=0.0, height=0.0),
        pins=[Pin(number=1, name="OUT1", function="output"),
              Pin(number=4, name="GND", function="ground")],
    )


# 1. A ComponentRecord can represent the current extracted data (round-trips).
def test_represents_current_extracted_data_multi():
    pd = _legacy_multi_package()
    rec = ComponentRecord.from_pin_data(pd)
    assert rec.identity.description == "SN74HC595"
    assert len(rec.variants) == 2
    assert rec.selected().package_type == "SOIC-16"
    assert [p.name for p in rec.selected().pins] == ["QB", "VCC"]
    assert rec.ordered_pin_count == 16

    back = rec.to_pin_data()
    assert back.component_name == "SN74HC595"
    assert len(back.packages) == 2
    assert back.packages[0]["type"] == "SOIC-16"
    assert [p["name"] for p in back.packages[0]["pins"]] == ["QB", "VCC"]
    # legacy free-text function survives via role
    assert back.packages[0]["pins"][0]["function"] == "output"


def test_represents_current_extracted_data_single_roundtrip():
    pd = _legacy_single_package()
    back = ComponentRecord.from_pin_data(pd).to_pin_data()
    assert back.component_name == "LM358"
    assert back.package.type == "DIP-8"
    assert [(p.number, p.name, p.function) for p in back.pins] == \
           [(1, "OUT1", "output"), (4, "GND", "ground")]


# 2. Pins and dimensions live in the SAME record.
def test_pins_and_dimensions_same_record():
    dims = {"e": 1.27, "E": 6.0, "D": 9.9, "E1": 3.9,
            "b": 0.41, "b_min": 0.31, "b_max": 0.51, "L": 0.84, "A": 1.75}
    rec = ComponentRecord.from_pin_data(_legacy_single_package(), extracted_dims=dims)
    v = rec.selected()
    assert v.pins, "pins present on the variant"
    assert v.mechanical.lead_pitch_e.nominal() == 1.27, "dims present on the SAME variant"
    assert rec.selected_mechanical().body_height_A.nominal() == 1.75


# 3. Dimension supports min/nom/max.
def test_dimension_min_nom_max():
    d = Dimension(min=3.80, nom=3.90, max=4.00)
    assert (d.min, d.nom, d.max) == (3.80, 3.90, 4.00)
    assert d.nominal() == 3.90                     # nom wins
    assert Dimension(min=5.8, max=6.2).nominal() == 6.0   # midpoint when no nom
    assert Dimension(max=1.75).nominal() == 1.75
    assert Dimension().is_empty()


def test_dimension_tolerances_survive_flat_roundtrip():
    dims = {"e": 1.27, "b": 0.41, "b_min": 0.31, "b_max": 0.51, "A": 1.75}
    m = Mechanical.from_flat_dims(dims)
    assert m.lead_width_b.min == 0.31 and m.lead_width_b.max == 0.51
    out = m.to_flat_dims()
    assert out["b_min"] == 0.31 and out["b_max"] == 0.51 and out["e"] == 1.27


# 4. Provenance can be attached (record, dimension, pin).
def test_provenance_attachable_everywhere():
    prov = Provenance(datasheet_url="http://x", revision="A", page=30,
                      table="MECHANICAL DATA", method="text")
    rec = ComponentRecord(
        provenance=prov,
        variants=[PackageVariant(
            variant_id="v0", package_type="SOIC-16", pin_count=16,
            pins=[RecordPin(number="1", name="QB", provenance=prov)],
            mechanical=Mechanical(lead_span_E=Dimension(nom=6.0, provenance=prov)),
        )],
        selected_variant="v0",
    )
    assert rec.provenance.page == 30
    assert rec.selected().pins[0].provenance.table == "MECHANICAL DATA"
    assert rec.selected().mechanical.lead_span_E.provenance.method == "text"


# 5. status="blocked" and blocking=[] are representable.
def test_status_blocked_representable():
    ok = ComponentRecord()
    assert ok.status == "ok" and ok.blocking == [] and not ok.is_blocked()

    blk = ComponentRecord().block("lead_span_E", "body_height_A")
    assert blk.is_blocked() and blk.status == "blocked"
    assert blk.blocking == ["lead_span_E", "body_height_A"]

    # a part with no pins is auto-blocked by the compat layer
    empty = ComponentRecord.from_pin_data(PinData(component_name="X"))
    assert empty.is_blocked() and "pins" in empty.blocking


# electrical-semantics fields exist (unpopulated today, ready for Phase 2).
def test_pin_electrical_fields_present_and_default_safe():
    p = RecordPin(number="10", name="SRCLR")
    assert p.electrical_type is None and p.role is None
    assert p.active_low is False and p.nc is False and p.hidden is False
    p2 = RecordPin(number="13", name="OE", electrical_type="input",
                   role="enable", active_low=True)
    assert p2.electrical_type == "input" and p2.active_low is True
