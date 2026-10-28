"""The GLB pipeline runs the repair layer's deterministic steps (no LLM).

QC re-check ADV SCH-01/02: /jobs builds the symbol from the CLI pipeline, which
never ran the repair layer, so grouped labels ("GPO0 to GPO3") stayed grouped or
were spread in printed order. The deterministic repairs (ordered variant's pin
table, group expansion, pin-drawing read) cost nothing and now run there too.
"""
import json
from pathlib import Path

import pytest

PDF_BYTES = b"%PDF-1.4\n%fake datasheet\n"


def test_repair_without_llm_makes_no_calls_and_keeps_usage(tmp_path, monkeypatch):
    import src.agentic.repair as R
    import src.chat_bot as chat_bot

    def _no_llm(*a, **k):
        raise AssertionError("LLM called in deterministic-only repair")

    monkeypatch.setattr(chat_bot, "get_completion_from_messages", _no_llm)
    monkeypatch.setattr(R, "_page_texts", lambda p: [(1, "PIN CONFIGURATION\n5, 6, 41, 42 GPO0 to GPO3\n")])
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(PDF_BYTES)
    reset = {"n": 0}
    monkeypatch.setattr(chat_bot, "reset_usage", lambda: reset.__setitem__("n", reset["n"] + 1))

    pins = [{"number": n, "name": "GPO0 to GPO3"} for n in (5, 6, 41, 42)]
    pins += [{"number": n, "name": f"P{n}"} for n in (1, 2, 3, 4)]
    rep = R.repair_pins(pins, pdf, "X", use_llm=False)

    names = {p["number"]: p["name"] for p in rep["pins"]}
    assert all(names[n] == "GPO0 to GPO3" for n in (5, 6, 41, 42))  # fail closed
    assert reset["n"] == 0  # the pipeline's LLM usage counter is left alone


ADV7180 = Path.home() / "Downloads/datasheets/ADV7180KST48Z.pdf"
TRUTH = Path.home() / "Downloads/datasheets/truth_table.json"


@pytest.mark.skipif(not (ADV7180.exists() and TRUTH.exists()), reason="ADV7180 datasheet not available")
def test_pipeline_repair_fixes_adv7180_gpo_order():
    from src.main import _apply_deterministic_repair
    from src.models.pin_data import PackageInfo, Pin, PinData

    truth = next(p for p in json.load(open(TRUTH))["parts"] if p["part_number"] == "ADV7180KST48Z")
    gt = {int(k): v for k, v in truth["pinout"].items()}
    extracted = dict(gt)
    for n in (5, 6, 41, 42):
        extracted[n] = "GPO0 to GPO3"  # what the LLM extraction leaves behind
    extracted[24] = "AGND"            # QC run: pin 24 mis-read
    pd = PinData(
        component_name="ADV7180KST48Z",
        package=PackageInfo(type="LQFP-48", pin_count=48, width=0.0, height=0.0),
        pins=[Pin(number=n, name=v) for n, v in sorted(extracted.items())],
    )
    _apply_deterministic_repair(pd, ADV7180, "ADV7180KST48Z")
    got = {p.number: p.name for p in pd.pins}
    norm = lambda s: s.replace("_", "").upper()
    assert {n: norm(got[n]) for n in gt} == {n: norm(v) for n, v in gt.items()}


def test_renamed_pins_carry_their_type_and_role():
    # Deployed run 26 Oct (ADV7180): the variant pin table renamed pin 24
    # AGND -> ELPF and pin 25 ELPF -> PVDD, but each kept the old name's type
    # and role (ELPF drawn as ground, PVDD as an analog input).
    from src.agentic.repair import carry_pin_data
    from src.models.pin_data import Pin

    pins = {
        23: Pin(number=23, name="AGND", electrical_type="power_in", role="ground"),
        24: Pin(number=24, name="AGND", electrical_type="power_in", role="ground"),
        25: Pin(number=25, name="ELPF", electrical_type="input", role="analog"),
        26: Pin(number=26, name="V + D", electrical_type="power_in", role="supply"),
        46: Pin(number=46, name="RST", electrical_type="input", role="reset", active_low=True),
    }
    old = {n: p.name for n, p in pins.items()}
    new = {23: "AGND", 24: "ELPF", 25: "PVDD", 26: "VD+", 46: "RST"}
    assert carry_pin_data(pins, old, new) == 2

    # ELPF moved 25 -> 24: its data moved with it.
    assert (pins[24].electrical_type, pins[24].role) == ("input", "analog")
    # Pin 25's data belonged to ELPF, now elsewhere: re-derived from PVDD.
    assert (pins[25].electrical_type, pins[25].role) == ("power_in", "supply")
    # A cosmetic rename keeps the pin's own data; untouched pins stay as they were.
    assert (pins[26].electrical_type, pins[26].role) == ("power_in", "supply")
    assert pins[46].active_low and pins[23].role == "ground"


def test_renamed_pin_with_an_unknown_name_is_cleared_for_the_pin_table():
    # When the new name says nothing (and the old name moved away), the stale data
    # is cleared so the datasheet's I/O column can fill it afterwards.
    from src.agentic.repair import carry_pin_data

    pins = {1: {"number": 1, "name": "CLK", "type": "input", "active_low": True},
            2: {"number": 2, "name": "SDA", "type": "bidirectional"}}
    carry_pin_data(pins, {1: "CLK", 2: "SDA"}, {1: "XQ7", 2: "CLK"})
    assert pins[2]["type"] == "input" and pins[2]["active_low"] is True
    assert pins[1]["type"] is None and pins[1]["active_low"] is False


def test_group_label_split_keeps_the_members_data():
    # "GPO0 to GPO3" expanded into its members: the group's type belongs to every
    # member, so nothing is cleared.
    from src.agentic.repair import carry_pin_data

    pins = {n: {"number": n, "name": "GPO0 to GPO3", "type": "output"} for n in (5, 6)}
    carry_pin_data(pins, {5: "GPO0 to GPO3", 6: "GPO0 to GPO3"}, {5: "GPO1", 6: "GPO0"})
    assert pins[5]["type"] == pins[6]["type"] == "output"


def test_group_label_replaced_by_an_outside_name_is_re_derived():
    # ADV7180 old extraction: pin 28 "AIN1 to AIN6" -> AGND kept the analog-input type.
    from src.agentic.repair import carry_pin_data

    pins = {28: {"number": 28, "name": "AIN1 to AIN6", "type": "input"},
            33: {"number": 33, "name": "AIN1 to AIN6", "type": "input"}}
    carry_pin_data(pins, {28: "AIN1 to AIN6", 33: "AIN1 to AIN6"}, {28: "AGND", 33: "AIN3"})
    assert pins[28]["type"] == "power_in"
    assert pins[33]["type"] == "input"
