"""Slice C sub-step 0: inert semantics plumbing into the schematic builder.

The adapter attaches per-pin contract semantics onto the builder pin dicts,
matched by number, without touching number/name/order. The builder ignores
these keys today, so output stays byte-identical (verified separately by
generating GLBs with/without the record). These tests lock the enrichment shape.
"""
from src.schematic_generator.adapter import _enrich_builder_pins
from src.models import ComponentRecord
from src.models.pin_data import PinData, PackageInfo, Pin

_SEM = {"electrical_type", "role", "active_low", "nc", "nc_instruction"}


def _record():
    pd = PinData(
        component_name="X",
        package=PackageInfo(type="SOIC-8", pin_count=8, width=0, height=0),
        pins=[
            Pin(1, "VCC", electrical_type="power_in", role="supply"),
            Pin(2, "OUT", electrical_type="output", role="output", active_low=True),
            Pin(3, "NC", nc=True, nc_instruction="no connect"),
        ],
    )
    return ComponentRecord.from_pin_data(pd)


def test_enrich_attaches_semantics_by_number_preserving_order_and_name():
    pins = [{"number": "1", "name": "VCC"},
            {"number": "2", "name": "OUT"},
            {"number": "3", "name": "NC"}]
    out = _enrich_builder_pins([dict(p) for p in pins], _record())

    # number / name / order untouched
    assert [(p["number"], p["name"]) for p in out] == [("1", "VCC"), ("2", "OUT"), ("3", "NC")]
    # semantics attached, matched by number
    assert out[0]["electrical_type"] == "power_in" and out[0]["role"] == "supply"
    assert out[1]["active_low"] is True and out[1]["role"] == "output"
    assert out[2]["nc"] is True and out[2]["nc_instruction"] == "no connect"
    # every pin dict gained exactly the semantic keys (plus number/name)
    for p in out:
        assert _SEM.issubset(p.keys())


def test_enrich_is_noop_without_record():
    pins = [{"number": "1", "name": "A"}]
    assert _enrich_builder_pins(pins, None) is pins


def test_enrich_does_not_override_preexisting_keys():
    pins = [{"number": "1", "name": "VCC", "role": "manual"}]
    out = _enrich_builder_pins(pins, _record())
    assert out[0]["role"] == "manual"      # setdefault: pre-existing value wins
