"""Deterministic parsing of grouped pin-table rows (TI multi-package tables).

TL16C2550 prints one row per signal group ("CTSA, CTSB | 38, 23",
"D0-D4 / D5-D7 | 44 - 48 / 1 - 3") with one pin-number column per package
(PFB / FN / RHB) and continues the table onto the next page.
"""
from dataclasses import dataclass, field
from typing import List

from src.pdf_extractor.deterministic_table_parser import (
    _extract_pin_numbers,
    parse_pin_data_from_tables,
)

HEADER = [["TERMINAL", "", "", "", "I/O", "DESCRIPTION"],
          ["NAME", "PFB NO.", "FN NO.", "RHB NO.", "", ""]]

PAGE4 = HEADER + [
    ["A0", "28", "31", "20", "I", "Address 0 select bit."],
    ["A1", "27", "30", "19", "I", "Address 1 select bit."],
    ["A2", "26", "29", "18", "I", "Address 2 select bit."],
    ["CDA, CDB", "40, 16", "42, 21", "–", "I", "Carrier detect (active low)."],
    ["CSA, CSB", "10, 11", "16, 17", "7, 8", "I", "Chip select A and B (active low)."],
    ["CTSA,\nCTSB", "38, 23", "40, 28", "25, 16", "I", "Clear to send (active low)."],
    ["D0-D4\nD5-D7", "44 - 48\n1 - 3", "2 - 6\n7 - 9", "27 - 31\n32, 1, 2", "I/O", "Data bus."],
    ["DSRA,\nDSRB", "39, 20", "41, 25", "–", "I", "Data set ready (active low)."],
    ["DTRA,\nDTRB", "34, 35", "37, 38", "–", "O", "Data terminal ready (active low)."],
    ["GND", "17", "22", "13", "", "Signal and power ground."],
    ["INTA,\nINTB", "30, 29", "33, 32", "22, 21", "O", "Interrupt A and B."],
    ["IOR", "19", "24", "14", "I", "Read input."],
    ["IOW", "15", "20", "12", "I", "Write input."],
    ["NC", "12, 24, 25,\n37", "–", "9, 17", "", "No internal connection"],
    ["OPA, OPB", "32, 9", "35, 15", "–", "O", "User defined outputs."],
    ["RESET", "36", "39", "24", "I", "Reset."],
]
PAGE5 = HEADER + [
    ["RIA, RIB", "41, 21", "43, 26", "–", "I", "Ring indicator (active low)."],
    ["RTSA,\nRTSB", "33, 22", "36, 27", "23, 15", "O", "Request to send (active low)."],
    ["RXA, RXB", "5, 4", "11, 10", "4, 3", "I", "Receive data input."],
    ["RXRDYA,\nRXRDYB", "31, 18", "34, 23", "–", "O", "Receive ready (active low)."],
    ["TXA, TXB", "7, 8", "13, 14", "5, 6", "O", "Transmit data."],
    ["TXRDYA,\nTXRDYB", "43, 6", "11, 12", "–", "O", "Transmit ready (active low)."],
    ["VCC", "42", "44", "26", "I", "Power supply inputs."],
    ["XTAL1", "13", "18", "10", "I", "Crystal input."],
    ["XTAL2", "14", "19", "11", "O", "Crystal output."],
]

TRUTH = {
    1: "D5", 2: "D6", 3: "D7", 4: "RXB", 5: "RXA", 6: "TXRDYB", 7: "TXA", 8: "TXB",
    9: "OPB", 10: "CSA", 11: "CSB", 12: "NC", 13: "XTAL1", 14: "XTAL2", 15: "IOW",
    16: "CDB", 17: "GND", 18: "RXRDYB", 19: "IOR", 20: "DSRB", 21: "RIB", 22: "RTSB",
    23: "CTSB", 24: "NC", 25: "NC", 26: "A2", 27: "A1", 28: "A0", 29: "INTB",
    30: "INTA", 31: "RXRDYA", 32: "OPA", 33: "RTSA", 34: "DTRA", 35: "DTRB",
    36: "RESET", 37: "NC", 38: "CTSA", 39: "DSRA", 40: "CDA", 41: "RIA", 42: "VCC",
    43: "TXRDYA", 44: "D0", 45: "D1", 46: "D2", 47: "D3", 48: "D4",
}

TEXT = "Available in 48-Pin TQFP (PFB), 44-Pin PLCC (FN), or 32-Pin QFN (RHB) Packages"


@dataclass
class _Content:
    tables: List = field(default_factory=list)
    text_content: str = TEXT


def _names(pin_data):
    return {int(p.number): p.name for p in pin_data.pins}


def test_spaced_numeric_range_expands():
    assert _extract_pin_numbers("44 - 48") == [44, 45, 46, 47, 48]
    assert _extract_pin_numbers("44 – 48") == [44, 45, 46, 47, 48]
    assert _extract_pin_numbers("–") == []


def test_tl16c2550_grouped_multipage_table_parses_exactly():
    pd = parse_pin_data_from_tables(
        _Content(tables=[(4, PAGE4), (5, PAGE5)]), part_number="TL16C2550PFBR"
    )
    assert pd is not None
    assert pd.package.type == "TQFP-48"
    assert _names(pd) == TRUTH


def test_package_column_follows_part_number_designator():
    # Swap the PFB and RHB columns: numbers must still come from PFB.
    def swap(rows):
        return [[r[0], r[3], r[2], r[1]] + r[4:] for r in rows]
    pd = parse_pin_data_from_tables(
        _Content(tables=[(4, swap(PAGE4)), (5, swap(PAGE5))]),
        part_number="TL16C2550PFBR",
    )
    assert pd is not None and _names(pd) == TRUTH


def test_noncontiguous_range_label_is_not_paired_in_order():
    # ADV7180: "GPO0 to GPO3 | 5, 6, 41, 42" — pin 5 is GPO1, so pairing in
    # printed order would be wrong. The row must not be expanded in printed order.
    table = [
        ["Pin No.", "Mnemonic", "Type", "Description"],
        ["1, 13", "DGND", "G", "Ground."],
        ["5, 6, 41, 42", "GPO0 to GPO3", "O", "General-purpose outputs."],
        ["7", "P7", "O", "Pixel data."],
        ["8", "P6", "O", "Pixel data."],
    ]
    pd = parse_pin_data_from_tables(
        _Content(tables=[(10, table)], text_content="48-Lead LQFP"), part_number="ADV7180"
    )
    assert pd is not None
    names = _names(pd)
    assert [names.get(n) for n in (5, 6, 41, 42)] != ["GPO0", "GPO1", "GPO2", "GPO3"]


def test_same_header_tables_with_overlapping_pins_are_not_merged():
    # Two package variants on consecutive pages share a header; merging them
    # would mix variants. The larger table wins on its own, unchanged.
    hdr = [["PIN", "NAME", "DESCRIPTION"]]
    soic = hdr + [[str(n), f"S{n}", "x"] for n in range(1, 9)]
    qfn = hdr + [[str(n), f"Q{n}", "x"] for n in range(1, 17)]
    pd = parse_pin_data_from_tables(
        _Content(tables=[(4, soic), (5, qfn)], text_content="16-pin QFN"),
        part_number="X",
    )
    assert pd is not None
    assert _names(pd) == {n: f"Q{n}" for n in range(1, 17)}


def test_range_member_names_are_grounded():
    from src.pdf_extractor.extraction_validator import _ungrounded_pin_names

    # "D2"/"D6" are only printed inside the ranges "D0-D4" / "D5-D7".
    text = "D0-D4\nD5-D7 44 - 48 1 - 3 Data bus (bidirectional)."
    packages = [{"pins": [{"number": 46, "name": "D2"}, {"number": 2, "name": "D6"},
                          {"number": 9, "name": "D9"}]}]
    assert _ungrounded_pin_names(packages, text, allow_printed_ranges=True) == ["D9"]
    # Off by default: an LLM expanding a range is guessing, so stay strict.
    assert _ungrounded_pin_names(packages, text) == ["D2", "D6", "D9"]


def test_range_member_pins_ground_on_their_table_row():
    from src.models.pin_data import PinData, Pin
    from src.pdf_extractor.pin_grounding import assess_pin_grounding

    content = _Content(tables=[(4, [["D0-D4\nD5-D7", "44 - 48\n1 - 3", "I/O", "Data bus."]])],
                       text_content="")
    # D2 on the wrong pin (45 is D1) gets no credit from the range row.
    pd = PinData(component_name="X",
                 pins=[Pin(46, "D2"), Pin(2, "D6"), Pin(45, "D2"), Pin(9, "D9")])
    tally = assess_pin_grounding(pd, content)
    assert [p.grounding for p in pd.pins] == ["grounded", "grounded", "unsupported", "unsupported"]
    assert tally["unsupported"] == 2
