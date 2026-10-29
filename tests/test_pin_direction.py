"""QC re-check B1: pin direction read from the datasheet pin table, so the
symbol puts outputs on the right and inputs on the left (SnapEDA guideline).

Before, roles came from the pin name alone; VOUTL / IOUTP1 / SDO / VINR got none
and every such pin fell to the left (AD9106: 24 left / 9 right).
"""
from pathlib import Path

import pytest

from src.models.component_record import ComponentRecord, role_side
from src.models.pin_classifier import classify_pin_name
from src.models.pin_data import PackageInfo, Pin, PinData
from src.pdf_extractor.pin_direction import (
    apply_pin_directions,
    description_direction,
    read_pin_direction,
    table_directions,
)


@pytest.mark.parametrize("text, expected", [
    ("Serial Data Output", ("output", None)),
    ("DAC4 Current Output, Positive Side.", ("output", None)),
    ("Analog Input, Right Channel", ("input", None)),
    ("Serial Data Input/Output", ("bidirectional", None)),
    ("Analog Power Supply, -5V", ("power_in", "supply")),
    ("1.8 V to 3.3 V Power Supply Input for DAC1 and DAC2.", ("power_in", "supply")),
    ("Analog Ground, Right Channel", ("power_in", "ground")),
    ("Signalandpowerground.", ("power_in", "ground")),        # TI text, spaces lost
    ("Digital LDO Output", ("power_out", "supply")),
    ("External Full-Scale Current Output Adjust for DAC1", ("passive", None)),
    ("output enable input OE (active LOW)", ("input", "control")),
    ("Mute Control Input (Active LOW)", ("input", "control")),
    ("Power-down input", ("input", None)),                   # power-down is not a rail
    ("SPI Port Chip Select, Active Low.", None),              # no direction stated
])
def test_description_direction(text, expected):
    assert description_direction(text) == expected


def test_text_rows_in_both_column_orders():
    lines = [
        "7 SDO Serial Data Output",                  # number, name, description
        "XTAL1 13 18 10 I",                          # name, package numbers, I/O code
        "18 PVDD P PLL Supply Voltage (1.8 V).",     # number, name, type code
        "13 VA– Analog Power Supply, –5V",           # printed en-dash name
        "TXA 7 30 INTA",                             # pinout drawing: no direction
        "SCLK Falling to SDO Data Valid tCFDO 60 ns",  # prose
    ]
    assert read_pin_direction("SDO", 7, lines) == ("output", None)
    assert read_pin_direction("XTAL1", 13, lines) == ("input", None)
    assert read_pin_direction("PVDD", 25, lines) == ("power_in", None)  # other package's row
    assert read_pin_direction("VA-", 13, lines) == ("power_in", "supply")
    assert read_pin_direction("TXA", 7, lines) is None


def test_table_type_column_and_grouped_names():
    table = [
        ["TERMINAL", "", "I/O", "DESCRIPTION"],
        ["NAME", "PFB NO.", "", ""],
        ["CDA, CDB", "40, 16", "I", "Carrier detect"],
        ["D0-D4\nD5-D7", "44-48\n1-3", "I/O", "Data bus"],
        ["RTSA, RTSB", "33, 22", "O", "Request to send"],
    ]
    got = table_directions([(4, table)])
    assert got["CDB"] == ("input", None)
    assert got["D6"] == ("bidirectional", None)
    assert got["RTSA"] == ("output", None)


def test_collapsed_table_column_is_not_smeared():
    # PGA2311P: the whole table lands in one row (one cell per column); the
    # first description must not be applied to every pin.
    table = [
        ["PIN", "NAME", "FUNCTION"],
        ["1\n2\n3", "ZCEN\nCS\nSDO",
         "Zero Crossing Enable Input (Active HIGH)\nChip Select\nSerial Data\nOutput"],
    ]
    assert table_directions([(4, table)]) == {}


def test_power_code_lets_the_name_pick_supply_or_ground():
    pins = [Pin(number=1, name="AGND"), Pin(number=2, name="PVDD")]
    apply_pin_directions(pins, "1 AGND P Analog\n2 PVDD P PLL\n")
    assert [(p.electrical_type, p.role) for p in pins] == [
        ("power_in", "ground"), ("power_in", "supply")]


@pytest.mark.parametrize("name, etype, role", [
    ("CLKVDD", "power_in", "supply"),   # was claimed by the CLK rule
    ("PVDD", "power_in", "supply"),
    ("CLKGND", "power_in", "ground"),
    ("VOUTL", "output", "output"),
    ("IOUTP1", "output", "output"),
    ("SDO", "output", "output"),
    ("VINR", "input", "input"),
    ("AIN3", "input", "input"),
    ("SDI", "input", "input"),
])
def test_name_classifier_additions(name, etype, role):
    assert classify_pin_name(name)[:2] == (etype, role)


@pytest.mark.parametrize("name", ["VIN", "IN", "INTA", "INTRQ"])
def test_supply_and_interrupt_names_are_not_signal_inputs(name):
    assert classify_pin_name(name)[1] != "input"


def test_role_falls_back_to_the_direction():
    pins = [Pin(number=1, name="TXA", electrical_type="output"),
            Pin(number=2, name="RXA", electrical_type="input"),
            Pin(number=3, name="VCC"), Pin(number=4, name="GND")]
    pd = PinData(component_name="X", pins=pins,
                 package=PackageInfo(type="SOIC-4", pin_count=4, width=0.0, height=0.0))
    sides = {p.name: role_side(p.role) for p in ComponentRecord.from_pin_data(pd).selected().pins}
    assert sides == {"TXA": "right", "RXA": "left", "VCC": "right", "GND": "right"}


PGA = Path.home() / "Downloads/datasheets/PGA2311P.pdf"


@pytest.mark.skipif(not PGA.exists(), reason="PGA2311P datasheet not available")
def test_pga2311p_sides_match_the_qc_expectation():
    # QC PGA SCH-08 (SnapEDA): controls + inputs left; supplies, outputs and
    # grounds right — including VA- (the datasheet calls it a supply).
    import pdfplumber
    with pdfplumber.open(str(PGA)) as pdf:
        text = "\n".join(pg.extract_text() or "" for pg in pdf.pages[:6])
    names = ["ZCEN", "CS", "SDI", "VD+", "DGND", "SCLK", "SDO", "MUTE", "VINR",
             "AGNDR", "VOUTR", "VA+", "VA-", "VOUTL", "AGNDL", "VINL"]
    pins = [Pin(number=i, name=n) for i, n in enumerate(names, 1)]
    apply_pin_directions(pins, text)
    pd = PinData(component_name="PGA2311P", pins=pins,
                 package=PackageInfo(type="PDIP-16", pin_count=16, width=0.0, height=0.0))
    rec = ComponentRecord.from_pin_data(pd, part_number="PGA2311P").selected()
    right = {p.name for p in rec.pins if role_side(p.role) == "right"}
    assert right == {"VA+", "VA-", "VD+", "VOUTL", "VOUTR", "SDO", "AGNDL", "AGNDR", "DGND"}
    roles = {p.name: p.role for p in rec.pins}
    assert roles["ZCEN"] == roles["MUTE"] == roles["CS"] == "control"


def test_grouped_rows_give_every_listed_signal_the_row_direction():
    # ADV7180: one row per signal group; the direction applies to all of them,
    # so no name has to be paired with a pin number (cf. the GPO order, QC A2).
    lines = [
        "5, 6, 41, 42 GPO0 to GPO3 O General-Purpose Outputs.",
        "7 to 12, 20, 22 P7 to P2, P1, P0 O Video Pixel Output Port.",
        "P7 14 35 AIN1",   # pinout drawing beside it: no direction
    ]
    for name, number in (("GPO2", 42), ("P4", 10), ("P1", 20), ("P0", 22)):
        assert read_pin_direction(name, number, lines) == ("output", None), name
    assert read_pin_direction("AIN1", 35, lines) is None


def test_name_first_comma_group_row():
    assert read_pin_direction("CDB", 16, ["CDA, CDB 40, 16 42, 21 – I Carrier"]) == ("input", None)


def test_functional_symbol_puts_epad_with_the_grounds():
    # QC AD9106: the EPAD pin sat at the bottom of the LEFT column; SnapEDA puts
    # the exposed (ground) pad at the lower right with the grounds.
    from src.schematic_generator.pinout_diagram_builder import PinoutDiagramBuilder
    names = ["SCLK", "CS", "RESET", "AVDD", "DVDD", "AGND", "DGND", "OUT1"]
    roles = ["clock", "control", "reset", "supply", "supply", "ground", "ground", "output"]
    pins = [{"number": str(i), "name": n, "role": r}
            for i, (n, r) in enumerate(zip(names, roles), 1)]
    b = PinoutDiagramBuilder("LFCSP-8", 8, "X", pin_data=pins)
    epad = next(p for p in b.pin_positions if p.pin_number == "9")
    right = [p for p in b.pin_positions if p.side == "right"]
    assert epad.side == "right" and epad.y == min(p.y for p in right)
    bottom = b._body_center()[1] - b.params.body_height / 2
    assert epad.y - bottom == pytest.approx(b.params.pin_pitch)


def test_ldo_supply_output_is_power_out_even_over_an_llm_guess():
    # QC AD9106 SCH-05: CLDO "Clock Power Supply Output (Internal Regulator in
    # Use)" shipped as bidirectional; it is a power output like DLDO1/DLDO2.
    assert description_direction("Clock Power Supply Output (Internal Regulator") == (
        "power_out", "supply")
    pins = [Pin(number=22, name="CLDO", electrical_type="bidirectional"),
            Pin(number=7, name="SDO", electrical_type="bidirectional")]
    apply_pin_directions(pins, "22 CLDO Clock Power Supply Output (Internal Regulator\n"
                               "7 SDO Serial Data Output\n")
    assert [p.electrical_type for p in pins] == ["power_out", "bidirectional"]


def test_exposed_pad_is_typed_as_power():
    # QC AD9106 SCH-05: SnapEDA types the grounded exposed pad as power.
    from src.schematic_generator.pinout_diagram_builder import PinoutDiagramBuilder
    pins = [{"number": str(i), "name": f"P{i}"} for i in range(1, 9)]
    b = PinoutDiagramBuilder("LFCSP-8", 8, "X", pin_data=pins)
    epad = b._augment_pin_data(pins)[-1]
    assert (epad["electrical_type"], epad["role"]) == ("power_in", "thermal")
    assert classify_pin_name("EPAD")[:2] == ("power_in", "thermal")


def test_output_pins_go_right_whatever_the_llm_role():
    # Real-pipeline run 26 Oct: the LLM's function roles ("analog", "data",
    # "clock", "oscillator") put output pins on the input side; on the deployed
    # run TL16C2550 RTSA/DTRA came as "control".
    pins = [Pin(number=1, name="VOUTL", electrical_type="output", role="analog"),
            Pin(number=2, name="P7", electrical_type="output", role="data"),
            Pin(number=3, name="XTAL2", electrical_type="output", role="oscillator"),
            Pin(number=4, name="SDO", electrical_type="tri_state", role="data"),
            Pin(number=5, name="D0", electrical_type="bidirectional", role="data"),
            Pin(number=6, name="VREFP", electrical_type="output", role="supply"),
            Pin(number=7, name="GND", electrical_type="power_in", role="ground"),
            Pin(number=8, name="RTSA", electrical_type="output", role="control"),
            Pin(number=9, name="RESET", electrical_type="input", role="reset")]
    pd = PinData(component_name="X", pins=pins,
                 package=PackageInfo(type="SOIC-8", pin_count=9, width=0.0, height=0.0))
    sides = {p.name: role_side(p.role) for p in ComponentRecord.from_pin_data(pd).selected().pins}
    assert sides == {"VOUTL": "right", "P7": "right", "XTAL2": "right", "SDO": "right",
                     "D0": "left", "VREFP": "right", "GND": "right",
                     "RTSA": "right", "RESET": "left"}


def test_channel_twin_fills_missing_direction_and_active_low():
    # Deployed run 29 Oct (TL16C2550): only the A-channel came back typed and
    # active-low, so RTSB/DTRB/CSB sat on the input side unmarked.
    from src.pdf_extractor.pin_direction import propagate_channel_siblings

    pins = [Pin(number=33, name="RTSA", electrical_type="output", role="output", active_low=True),
            Pin(number=22, name="RTSB"),
            Pin(number=7, name="TXA", electrical_type="output", role="output"),
            Pin(number=8, name="TXB", electrical_type="input", role="input"),   # never overwritten
            Pin(number=9, name="INTA", electrical_type="output", role="output"),
            Pin(number=10, name="INTB"),
            Pin(number=11, name="VCCA", electrical_type="power_in", role="supply"),
            Pin(number=12, name="A", electrical_type="input"),
            Pin(number=13, name="B")]                                          # one-letter names are not twins
    assert propagate_channel_siblings(pins) == 2
    by = {p.name: p for p in pins}
    assert (by["RTSB"].electrical_type, by["RTSB"].role, by["RTSB"].active_low) == ("output", "output", True)
    assert by["INTB"].electrical_type == "output" and not by["INTB"].active_low
    assert by["TXB"].electrical_type == "input"
    assert by["B"].electrical_type is None


def test_active_low_read_from_the_pin_row_description():
    # AD9106 (QC A5): CS / RESET / TRIGGER carry their overbar only as a glyph the
    # text loses, but the pin-table row says "Active Low".
    from src.pdf_extractor.pin_direction import apply_active_low_from_rows

    text = ("8 CS SPI Port Chip Select, Active Low.\n"
            "9 RESET Active Low Reset Pin. Resets registers to their defaults.\n"
            "32 TRIGGER Pattern Trigger Input, Active Low.\n"
            "7 SDIO SPI Port Data Input/Output.\n"
            "CS 8 17 FSADJ4 a drawing line that only names CS, Active Low\n")
    pins = [Pin(number=8, name="CS"), Pin(number=9, name="RESET"), Pin(number=32, name="TRIGGER"),
            Pin(number=7, name="SDIO"), Pin(number=17, name="FSADJ4")]
    assert apply_active_low_from_rows(pins, text) == 3
    assert {p.name for p in pins if p.active_low} == {"CS", "RESET", "TRIGGER"}
