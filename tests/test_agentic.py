"""Agentic repair layer: pure-function tests plus the POST /agentic route with the
runner and the repair step both faked (no LLM, no PDF parsing)."""

from concurrent.futures import Future

import pytest
from fastapi.testclient import TestClient

from src.agentic import expand_groups_deterministic, expand_numeric, is_group, is_suspicious
from src.api.app import create_app
from src.api.jobs import FAILED, SUCCEEDED

PDF_BYTES = b"%PDF-1.4\n%fake datasheet\n"


class SyncExecutor:
    def submit(self, fn, *args, **kwargs):
        fut: Future = Future()
        fut.set_result(fn(*args, **kwargs))
        return fut


# --- classification --------------------------------------------------------------------------
@pytest.mark.parametrize("label", ["D0-D4", "D5-D7", "P7 to P2", "DIG0:DIG7", "CSA, CSB", "P7 to P2, P1, P0", "GPO0 to GPO3"])
def test_group_labels_detected(label):
    assert is_group(label)


@pytest.mark.parametrize("name", ["SCLK", "IOUTP4", "VS/FIELD", "SDO/SDI2/DOUT", "CS_N", "X1/CLK", "n.c."])
def test_real_names_not_groups(name):
    assert not is_group(name)


@pytest.mark.parametrize("name", ["DIP/ LAP/ SOIC", "V + D", "V – A", "V R IN", "V L OUT", "V CC"])
def test_extraction_damage_flagged(name):
    assert is_suspicious(name)


@pytest.mark.parametrize("name", ["VD+", "VINR", "VCC", "RESET/OE", "IOUTN3"])
def test_clean_names_not_suspicious(name):
    assert not is_suspicious(name)


def test_tidy_collapses_ocr_spacing_only_in_short_caps_tokens():
    from src.agentic.repair import _tidy

    assert _tidy("SEG E") == "SEGE"
    assert _tidy("VS/FIELD") == "VS/FIELD"
    assert _tidy("Line In/Out") == "Line In/Out"


def test_rebuild_subscript_names_deterministically():
    from src.agentic.repair import _rebuild_subscript_name

    assert _rebuild_subscript_name("V R IN") == "VINR"
    assert _rebuild_subscript_name("V L OUT") == "VOUTL"
    assert _rebuild_subscript_name("V + D") == "VD+"
    assert _rebuild_subscript_name("V – A") == "VA-"
    assert _rebuild_subscript_name("V CC") == "VCC"
    assert _rebuild_subscript_name("SCLK") is None
    assert _rebuild_subscript_name("DIP/ LAP/ SOIC") is None


def test_parse_json_tolerates_fences_and_prose():
    from src.agentic.repair import _parse_json

    assert _parse_json('Sure. ```json\n{"15": "SEGA", "17": "SEGB"}\n```') == {"15": "SEGA", "17": "SEGB"}
    assert _parse_json("no json here") == {}


def test_expand_numeric_forward_backward_and_colon():
    assert expand_numeric("D0-D4") == ["D0", "D1", "D2", "D3", "D4"]
    assert expand_numeric("P7 to P2") == ["P7", "P6", "P5", "P4", "P3", "P2"]
    assert expand_numeric("DIG0:DIG7") == [f"DIG{i}" for i in range(8)]
    assert expand_numeric("CSA, CSB") is None
    assert expand_numeric("SEGA:SEGG") is None


# --- deterministic expansion ---------------------------------------------------------------
def test_expand_groups_maps_range_onto_ascending_pins():
    pins = {1: "D5-D7", 2: "D5-D7", 3: "D5-D7", 4: "RXB", 44: "D0-D4", 45: "D0-D4", 46: "D0-D4", 47: "D0-D4", 48: "D0-D4"}
    out, log = expand_groups_deterministic(pins)
    assert (out[1], out[2], out[3]) == ("D5", "D6", "D7")
    assert [out[n] for n in range(44, 49)] == ["D0", "D1", "D2", "D3", "D4"]
    assert out[4] == "RXB"
    assert len(log) == 2


def test_expand_groups_leaves_mismatched_counts_alone():
    # 5-name range on 3 pins: ambiguous, must not be touched
    pins = {10: "D0-D4", 11: "D0-D4", 12: "D0-D4"}
    out, log = expand_groups_deterministic(pins)
    assert out == pins and log == []


def test_expand_groups_partial_fills_only_the_missing_names():
    pins = {44: "D0", 45: "D1", 46: "D0-D4", 47: "D0-D4", 48: "D4"}
    out, log = expand_groups_deterministic(pins)
    assert (out[46], out[47]) == ("D2", "D3") and log and "expand-partial" in log[0]


def test_expand_groups_skips_non_contiguous_pins():
    # GPO0 to GPO3 on scattered pins 5, 6, 41, 42: the pin order does NOT encode
    # which pin holds which name (datasheet maps 5=GPO1, 6=GPO0, 41=GPO3, 42=GPO2).
    # A deterministic ascending zip would emit the wrong order, so the label must
    # be left in place for the drawing/vision step instead.
    pins = {5: "GPO0 to GPO3", 6: "GPO0 to GPO3", 41: "GPO0 to GPO3", 42: "GPO0 to GPO3"}
    out, log = expand_groups_deterministic(pins)
    assert out == pins, "non-contiguous group must not be expanded deterministically"
    assert log and "non-contiguous" in log[0]
    # A contiguous run of the same range still expands (pin order is reliable).
    cont = {5: "GPO0 to GPO3", 6: "GPO0 to GPO3", 7: "GPO0 to GPO3", 8: "GPO0 to GPO3"}
    out2, log2 = expand_groups_deterministic(cont)
    assert [out2[n] for n in (5, 6, 7, 8)] == ["GPO0", "GPO1", "GPO2", "GPO3"]


def test_lost_subscript_range_is_not_expanded_blindly():
    from src.agentic.repair import _lost_subscript, range_numbers, _series_ok

    assert _lost_subscript("A 1 to A 6") and not _lost_subscript("D0-D4")
    out, log = expand_groups_deterministic({26: "A 1 to A 6", 27: "A 1 to A 6"})
    assert out[26] == "A 1 to A 6" and log == []
    assert range_numbers("A 1 to A 6") == [1, 2, 3, 4, 5, 6]
    assert _series_ok({26: "AIN1", 27: "AIN2"}, [1, 2])
    assert not _series_ok({26: "NC", 27: "TEST_0"}, [1, 2])
    assert not _series_ok({26: "AIN1", 27: "GPO2"}, [1, 2])


def test_letter_range_tokens():
    from src.agentic.repair import letter_range_tokens

    assert letter_range_tokens("SEGA:SEGG, SEGDP") == ["SEGA", "SEGB", "SEGC", "SEGD", "SEGE", "SEGF", "SEGG", "SEGDP"]
    assert letter_range_tokens("SEGA:SEGG") == ["SEGA", "SEGB", "SEGC", "SEGD", "SEGE", "SEGF", "SEGG"]
    assert letter_range_tokens("D0-D4") == []
    assert letter_range_tokens("CSA, CSB") == []


def test_page_scoring_prefers_the_ordered_variants_table():
    from src.agentic.repair import _score_pages

    texts = [
        (12, "PIN CONFIGURATIONS AND FUNCTION DESCRIPTIONS\n32-LEAD LFCSP\n1 HS O\n27 SDATA\n34 x\n"),
        (14, "PIN CONFIGURATIONS AND FUNCTION DESCRIPTIONS\n64-LEAD LQFP\n27, 28, 33 NC\n34 TEST_0\n"),
        (15, "PIN CONFIGURATIONS AND FUNCTION DESCRIPTIONS\n48-LEAD LQFP\n26, 27, 33 to 36 AIN1 to AIN6\n34 AIN4\n"),
        (81, "REGISTER MAP\nAddress 0x27 0x34 ...\n"),
    ]
    ranked = _score_pages(texts, [27, 34], package="LQFP", pin_count=48)
    assert ranked[0] == 15
    assert 81 not in ranked[:3]


# --- comma-list groups: row-order resolution + permutation constraint ------------------------
def test_comma_tokens():
    from src.agentic.repair import comma_tokens

    assert comma_tokens("CDA, CDB") == ["CDA", "CDB"]
    assert comma_tokens("P7 to P2, P1, P0") == []  # a range list, not a plain comma list
    assert comma_tokens("SEGA:SEGG, SEGDP") == []
    assert comma_tokens("SCLK") == []


def test_resolve_from_row_uses_the_number_list_matching_the_pins():
    from src.agentic.repair import resolve_from_row

    texts = [(4, "PIN FUNCTIONS\nCDA,CDB 40,16 42,21 – I indicates that a carrier\nTXRDYA,TXRDYB 43,6 1,12 – O ready\n"
                 "INTA,INTB 30,29 33.32 21.22 O\n")]
    assert resolve_from_row(texts, ["CDA", "CDB"], [16, 40]) == {40: "CDA", 16: "CDB"}
    assert resolve_from_row(texts, ["TXRDYA", "TXRDYB"], [6, 43]) == {43: "TXRDYA", 6: "TXRDYB"}
    assert resolve_from_row(texts, ["INTA", "INTB"], [29, 30]) == {30: "INTA", 29: "INTB"}
    assert resolve_from_row(texts, ["CDA", "CDB"], [1, 2]) == {}  # no list with those numbers


def test_llm_fix_must_be_a_permutation_of_the_group_tokens():
    from src.agentic.repair import _fix_matches_tokens

    assert _fix_matches_tokens({9: "OPB", 32: "OPA"}, ["OPA", "OPB"])
    assert not _fix_matches_tokens({9: "D7", 32: "INTB"}, ["OPA", "OPB"])
    assert not _fix_matches_tokens({22: "INTA", 33: "INTA"}, ["RTSA", "RTSB"])


def test_letter_range_answers_only_need_the_prefix_and_distinctness():
    from src.agentic.repair import _fix_matches_tokens

    toks = ["SEGA", "SEGB", "SEGC", "SEGD", "SEGE", "SEGF", "SEGG"]
    # the drawing may include SEGDP even though the label "SEGA:SEGG" omitted it
    assert _fix_matches_tokens({15: "SEGA", 17: "SEGB", 22: "SEGDP"}, toks, prefix="SEG")
    assert not _fix_matches_tokens({15: "SEGA", 17: "VDD"}, toks, prefix="SEG")
    assert not _fix_matches_tokens({15: "SEGA", 17: "SEGA"}, toks, prefix="SEG")


# --- POST /agentic ---------------------------------------------------------------------------
def _client(tmp_path, monkeypatch, extract_status=SUCCEEDED, repair=None):
    import src.api.app as appmod

    fake = {
        "component": "X", "part_number": "TL16C2550PFBR", "package": "LQFP", "pin_count": 3,
        "model": "openai/gpt-6-luna", "validated": True,
        "pins": [{"number": 1, "name": "D5-D7", "type": "io", "nc": False},
                 {"number": 2, "name": "D5-D7", "type": "io", "nc": False},
                 {"number": 3, "name": "D5-D7", "type": "io", "nc": False}],
        "usage": {"model": "openai/gpt-6-luna", "calls": 2, "prompt_tokens": 10, "completion_tokens": 5,
                  "total_tokens": 15, "cost_usd": 0.001},
    }
    monkeypatch.setattr(appmod, "run_extract",
                        lambda job, **kw: (extract_status, fake if extract_status == SUCCEEDED else None,
                                           None if extract_status == SUCCEEDED else "unparseable"))
    if repair is not None:
        monkeypatch.setattr(appmod, "repair_pins", repair)
    app = create_app(jobs_dir=tmp_path, executor=SyncExecutor())
    return TestClient(app)


def test_agentic_returns_repaired_pins_and_usage(tmp_path, monkeypatch):
    seen = {}

    def fake_repair(pins, pdf_path, part_number, repair_model=None, escalation_model=None, **kw):
        seen.update(part_number=part_number, repair_model=repair_model, escalation_model=escalation_model, **kw)
        fixed = [dict(p, name=n) for p, n in zip(pins, ["D5", "D6", "D7"])]
        return {"pins": fixed, "changed": 3, "repairs": ["expand 'D5-D7'"], "flags": {"duplicates": [], "unresolved": [], "pin_count": 3},
                "usage": {"repair_model": "openai/gpt-6-luna", "escalation_model": "anthropic/claude-opus-4.8", "calls": 0,
                          "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost_usd": 0.0}}

    client = _client(tmp_path, monkeypatch, repair=fake_repair)
    resp = client.post("/agentic", files={"file": ("x.pdf", PDF_BYTES, "application/pdf")},
                       data={"part_number": "TL16C2550PFBR", "escalation_model": "anthropic/claude-opus-4.8"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [p["name"] for p in body["pins"]] == ["D5", "D6", "D7"]
    assert body["agentic"]["changed"] == 3
    assert body["agentic"]["repairs"] == ["expand 'D5-D7'"]
    assert body["usage"]["calls"] == 2  # extraction usage untouched
    assert body["usage_total"]["cost_usd"] == pytest.approx(0.001)
    assert seen["part_number"] == "TL16C2550PFBR" and seen["escalation_model"] == "anthropic/claude-opus-4.8"
    assert seen["package"] == "LQFP" and seen["pin_count"] == 3  # taken from the extraction when the caller sends none


def test_agentic_without_llm_still_expands_ranges(tmp_path, monkeypatch):
    """Real repair_pins on a fake PDF: no page text, so only the deterministic step runs."""
    client = _client(tmp_path, monkeypatch)
    resp = client.post("/agentic", files={"file": ("x.pdf", PDF_BYTES, "application/pdf")}, data={"part_number": "TL16C2550PFBR"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [p["name"] for p in body["pins"]] == ["D5", "D6", "D7"]
    assert body["agentic"]["usage"]["calls"] == 0


def test_agentic_maps_domain_failure(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, extract_status=FAILED)
    resp = client.post("/agentic", files={"file": ("x.pdf", PDF_BYTES, "application/pdf")})
    assert resp.status_code == 422


def test_agentic_requires_pdf(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.post("/agentic").status_code == 400


# --- deterministic variant-column read (Option A) ---------------------------------------------
from src.agentic.repair import read_variant_column

_PIN_DESC = "\n".join([
    "Table 3.", "Pin description", "Symbol", "Pin", "Description",
    "SOT505-2 and", "SOT833-1", "SOT902-1",
    "OE", "1", "7", "output enable input OE (active LOW)",
    "A", "2", "6", "data input",
    "B", "3", "5", "data input",
    "GND", "4", "4", "ground (0 V)",
    "C", "5", "3", "data input",
    "D", "6", "2", "data input",
    "Y", "7", "1", "data output",
    "VCC", "8", "8", "supply voltage",
])
# What extraction actually produced for 74LVC1G99GT: correct names, WRONG (SOT902-1) numbers.
_EXTRACTED = {1: "Y", 2: "D", 3: "C", 4: "GND", 5: "B", 6: "A", 7: "OE", 8: "VCC"}


def test_read_variant_column_picks_ordered_version():
    got = read_variant_column([(3, _PIN_DESC)], _EXTRACTED, "SOT833-1", pin_count=8)
    assert got == {1: "OE", 2: "A", 3: "B", 4: "GND", 5: "C", 6: "D", 7: "Y", 8: "VCC"}


def test_read_variant_column_other_version_is_the_other_column():
    got = read_variant_column([(3, _PIN_DESC)], _EXTRACTED, "SOT902-1", pin_count=8)
    assert got == {1: "Y", 2: "D", 3: "C", 4: "GND", 5: "B", 6: "A", 7: "OE", 8: "VCC"}


def test_read_variant_column_fails_closed():
    # version absent from the table
    assert read_variant_column([(3, _PIN_DESC)], _EXTRACTED, "SOT999-9", pin_count=8) is None
    # name-set mismatch (extraction carries a name the table lacks)
    bad = dict(_EXTRACTED); bad[1] = "ZZZ"
    assert read_variant_column([(3, _PIN_DESC)], bad, "SOT833-1", pin_count=8) is None
    # no parseable table
    assert read_variant_column([(1, "just prose mentioning SOIC pins")], _EXTRACTED, "SOT833-1") is None
    # pin-count guard
    assert read_variant_column([(3, _PIN_DESC)], _EXTRACTED, "SOT833-1", pin_count=16) is None


# The newer NXP datasheet (Rev.13, 2024) consolidated the per-variant number
# columns into a SINGLE "Symbol / Pin / Description" pin-description table; the
# ordered variant (SOT833-1) numbering is the one printed column.
_PIN_DESC_SINGLE = "\n".join([
    "Table 3.", "Pin description", "Symbol", "Pin", "Description",
    "OE", "1", "output enable input OE (active LOW)",
    "A", "2", "data input",
    "B", "3", "data input",
    "GND", "4", "ground (0 V)",
    "C", "5", "data input",
    "D", "6", "data input",
    "Y", "7", "data output",
    "VCC", "8", "supply voltage",
])


def test_read_variant_column_reads_single_column_table():
    # Rev.13: only one pin-number column, no per-variant header -> read it straight.
    got = read_variant_column([(3, _PIN_DESC_SINGLE)], _EXTRACTED, "SOT833-1", pin_count=8)
    assert got == {1: "OE", 2: "A", 3: "B", 4: "GND", 5: "C", 6: "D", 7: "Y", 8: "VCC"}


def test_read_variant_column_single_column_fails_closed():
    # name-set mismatch
    bad = dict(_EXTRACTED); bad[1] = "ZZZ"
    assert read_variant_column([(3, _PIN_DESC_SINGLE)], bad, "SOT833-1", pin_count=8) is None
    # pin-count guard
    assert read_variant_column([(3, _PIN_DESC_SINGLE)], _EXTRACTED, "SOT833-1", pin_count=16) is None


def test_repair_fixes_rev13_single_column_datasheet():
    """End-to-end: the service's Rev.13 datasheet (single-column pin table) must
    correct the reversed extraction to the printed SOT833-1 numbering, no LLM."""
    from pathlib import Path
    from src.agentic.repair import repair_pins
    pdf = Path(__file__).parent / "ground_truth" / "74LVC1G99_rev13.pdf"
    assert pdf.is_file(), pdf
    raw = [{"number": n, "name": x} for n, x in _EXTRACTED.items()]
    rep = repair_pins(raw, pdf, "74LVC1G99GT", escalation_model="openai/gpt-6-luna")
    got = {int(p["number"]): p["name"] for p in rep["pins"]}
    assert got == {1: "OE", 2: "A", 3: "B", 4: "GND", 5: "C", 6: "D", 7: "Y", 8: "VCC"}


# --- deterministic grouped variant pin-function table (ADV7180-style, #52) --------------------
from src.agentic.repair import read_variant_pin_table

# A multi-variant "Pin No. | Mnemonic | Type | Description" document, one cell per
# line (as PyMuPDF extracts it). The decoy 64-lead table names pin 24 AGND; the
# ordered 48-lead table names it ELPF, so a correct read must SELECT the 48-lead
# table. A trailing register-map table (rows that look like "1 / RW") must not be
# scanned as pin rows. Names are the datasheet's, encoded here (the test) only --
# the parser in src/ hardcodes nothing.
def _row(pin_cell, mnemonic, typ, desc):
    return [pin_cell, mnemonic, typ, desc]


_ADV_LIKE = "\n".join(
    ["Table 11. 64-Lead LQFP Pin Function Descriptions", "Pin No.", "Mnemonic", "Type", "Description",
     *_row("24", "AGND", "G", "Analog Ground."),            # decoy: different name on pin 24
     *_row("30", "ELPF", "I", "External loop filter."),
     "Table 12. 48-Lead LQFP Pin Function Descriptions", "Pin No.", "Mnemonic", "Type", "Description",
     *_row("1, 13, 19, 43", "DGND", "G", "Digital Ground."),
     *_row("2, 4", "DVDDIO", "P", "Digital I/O Supply Voltage."),
     *_row("3", "SFL", "O", "Subcarrier Frequency Lock."),
     *_row("5, 6, 41, 42", "GPO0 to GPO3", "O", "General-Purpose Outputs."),
     *_row("7 to 12, 20, 22", "P7 to P2, P1, P0", "O", "Video Pixel Output Port."),
     *_row("14", "LLC", "O", "Line-locked output clock."),
     *_row("15, 48", "NC", "", "No Connect Pins."),
     *_row("16", "XTAL1", "O", "Crystal pin."),
     *_row("17", "XTAL", "I", "Crystal input pin."),
     *_row("18, 44", "DVDD", "P", "Digital Supply Voltage."),
     *_row("21", "PWRDWN", "I", "Power-down pin."),
     "Table 12. 48-Lead LQFP Pin Function Descriptions (Continued)", "Pin No.", "Mnemonic", "Type", "Description",
     *_row("23, 28, 32", "AGND", "G", "Analog Ground."),
     *_row("24", "ELPF", "I", "The recommended external loop filter must be connected here."),
     *_row("25", "PVDD", "P", "PLL Supply Voltage."),
     *_row("26, 27, 33 to 36", "AIN1 to AIN6", "I", "Analog Video Input Channels."),
     *_row("29", "VREFP", "O", "Internal Voltage Reference Output."),
     *_row("30", "VREFN", "O", "Internal Voltage Reference Output."),
     *_row("31", "AVDD", "P", "Analog Supply Voltage."),
     *_row("37", "RESET", "I", "System Reset Input."),
     *_row("38", "ALSB", "I", "I2C address select."),
     *_row("39", "SDATA", "I/O", "I2C Port Serial Data."),
     *_row("40", "SCLK", "I", "I2C Port Serial Clock."),
     *_row("45", "VS/FIELD", "O", "Vertical Sync Output Signal."),
     *_row("46", "INTRQ", "O", "Interrupt Request Output."),
     *_row("47", "HS", "O", "Horizontal Sync Output Signal."),
     "Table 13. Global Status Register", "Bit", "Access", "Description",
     "1", "RW", "status bit", "2", "RW", "status bit"]  # register rows must be ignored
)


def test_variant_pin_table_selects_ordered_variant_and_reads_single_names():
    got = read_variant_pin_table(_ADV_LIKE, 48, "LQFP")
    assert got is not None
    # #52: the 48-lead table's own names, NOT the decoy 64-lead table.
    assert got[24] == "ELPF" and got[25] == "PVDD"
    assert got[23] == got[28] == got[32] == "AGND"
    # full, unambiguous coverage of the whole variant
    assert set(got) == set(range(1, 49))


def test_variant_pin_table_leaves_scattered_range_as_group_for_the_drawing():
    got = read_variant_pin_table(_ADV_LIKE, 48, "LQFP")
    # #53: a numeric range on NON-contiguous pins is left as the GROUP LABEL so the
    # per-pin order is resolved from the drawing, never guessed from pin order.
    assert got[5] == got[6] == got[41] == got[42] == "GPO0 to GPO3"
    assert is_group(got[5])
    assert got[26] == got[36] == "AIN1 to AIN6" and is_group(got[26])


def test_variant_pin_table_fails_closed():
    # wrong ordered count: no 20-lead table in the document
    assert read_variant_pin_table(_ADV_LIKE, 20, "LQFP") is None
    # family mismatch: the 48-lead table is LQFP, not SOIC
    assert read_variant_pin_table(_ADV_LIKE, 48, "SOIC") is None
    # single-variant document: nothing to select, so this read does not act
    one = "\n".join(["Table 1. 8-Lead SOIC Pin Function Descriptions", "Pin No.", "Mnemonic",
                     "1", "A", "2", "B", "3", "C", "4", "D", "5", "E", "6", "F", "7", "G", "8", "H"])
    assert read_variant_pin_table(one, 8, "SOIC") is None
    # no pin count
    assert read_variant_pin_table(_ADV_LIKE, None, "LQFP") is None


# --- #53: non-contiguous numeric group order comes ONLY from the drawing (vision) -------------
def _drive_group_repair(tmp_path, monkeypatch, vision_reply):
    """Run real repair_pins on a scattered GPO group, faking page text / rendering
    and the single vision call. No deterministic table in the doc, so the group
    reaches the drawing/vision escalation."""
    import src.agentic.repair as R
    import src.chat_bot as chat_bot
    import src.pdf_extractor.ordering_table as ot

    pdf = tmp_path / "d.pdf"; pdf.write_bytes(PDF_BYTES)
    page = ("PIN CONFIGURATION\n48-LEAD LQFP\n5, 6, 41, 42 GPO0 to GPO3\n"
            "pins 5 6 41 42 shown in Figure 11\n")
    # _page_context indexes texts by page order (texts[pno-1]); page 1 keeps it simple.
    monkeypatch.setattr(R, "_page_texts", lambda p: [(1, page)])
    monkeypatch.setattr(R, "_render_page_b64", lambda *a, **k: "")
    monkeypatch.setattr(ot, "full_pdf_text", lambda p: "")          # no variant table -> det. read no-ops
    monkeypatch.setattr(ot, "find_ordering_match", lambda *a, **k: None)
    monkeypatch.setattr(chat_bot, "get_completion_from_messages",
                        lambda messages, *a, **k: vision_reply)

    pins = [{"number": n, "name": "GPO0 to GPO3", "type": "O", "nc": False} for n in (5, 6, 41, 42)]
    return R.repair_pins(pins, pdf, "ADV7180KST48Z", package="LQFP", pin_count=48)


def test_scattered_numeric_group_takes_the_drawing_order(tmp_path, monkeypatch):
    # The drawing (vision) reports the swapped order; it is accepted because it is a
    # clean permutation of GPO0..GPO3 -- the documented ground truth for this part.
    rep = _drive_group_repair(tmp_path, monkeypatch,
                              '{"5": "GPO1", "6": "GPO0", "41": "GPO3", "42": "GPO2"}')
    names = {p["number"]: p["name"] for p in rep["pins"]}
    assert (names[5], names[6], names[41], names[42]) == ("GPO1", "GPO0", "GPO3", "GPO2")
    assert rep["flags"]["unresolved"] == []
    # the per-pin order must have come from the drawing, never from a text guess
    assert any("escalating to vision" in r for r in rep["repairs"])
    assert not any(r.startswith("text(") for r in rep["repairs"])


def test_scattered_numeric_group_fails_closed_when_drawing_unreadable(tmp_path, monkeypatch):
    # Vision cannot read the figure: the group must stay a grouped label (fail closed),
    # never a guessed ascending order.
    rep = _drive_group_repair(tmp_path, monkeypatch,
                              '{"5": "?", "6": "?", "41": "?", "42": "?"}')
    names = {p["number"]: p["name"] for p in rep["pins"]}
    assert all(names[n] == "GPO0 to GPO3" for n in (5, 6, 41, 42))
    assert set(rep["flags"]["unresolved"]) == {5, 6, 41, 42}


# --- #54: the LLM package-column remap must never scatter a non-power signal name --------------
def _drive_column_remap(tmp_path, monkeypatch, remap_pins):
    """Run real repair_pins down the LLM package-column-check path (step 1): two
    package families on the pin page trigger the check, the deterministic reads
    no-op, and the stubbed model returns ``remap_pins`` as the "corrected" map.
    Returns (rep, names)."""
    import src.agentic.repair as R
    import src.chat_bot as chat_bot
    import src.pdf_extractor.ordering_table as ot
    import json as _json

    pdf = tmp_path / "d.pdf"; pdf.write_bytes(PDF_BYTES)
    # Two DISTINCT package families on the pin page -> column-check fires.
    page = ("PIN CONFIGURATION\n48-LEAD LQFP and 48-LEAD LFCSP\n"
            + " ".join(str(i) for i in range(1, 49)) + "\n")
    monkeypatch.setattr(R, "_page_texts", lambda p: [(1, page)])
    monkeypatch.setattr(R, "_render_page_b64", lambda *a, **k: "")
    monkeypatch.setattr(ot, "full_pdf_text", lambda p: "")
    monkeypatch.setattr(ot, "find_ordering_match", lambda *a, **k: None)
    monkeypatch.setattr(chat_bot, "get_completion_from_messages",
                        lambda messages, *a, **k: _json.dumps(
                            {"package": "LQFP", "column_ok": False, "pins": remap_pins}))

    # Extraction: a clean per-pin pinout whose pin 45 is the shared compound VS/FIELD.
    pins = [{"number": n, "name": ("VS/FIELD" if n == 45 else f"SIG{n}"), "type": "O", "nc": False}
            for n in range(1, 49)]
    rep = R.repair_pins(pins, pdf, "ADV7180KST48Z", repair_model="x", escalation_model="x",
                        package="LQFP", pin_count=48)
    return rep, {p["number"]: p["name"] for p in rep["pins"]}


def test_column_remap_rejected_when_it_scatters_a_signal_name(tmp_path, monkeypatch):
    # The model re-reads the WRONG column and confuses the shared VS/FIELD pin,
    # putting "FIELD" on two scattered pins (the ADV7180KST48Z production defect:
    # agentic flagged duplicates=['FIELD']). A real column fix only re-numbers; it
    # never duplicates a non-power signal. The remap must be rejected (fail closed),
    # VS/FIELD must stay one pin, and no "FIELD" scatter may reach the output.
    base = {n: f"SIG{n}" for n in range(1, 49)}; base[45] = "VS/FIELD"
    remap = {str(n): base[(n % 48) + 1] for n in range(1, 49)}   # rotate: many pins "move"
    remap["45"] = "FIELD"; remap["20"] = "FIELD"                  # ...but scatter FIELD
    rep, names = _drive_column_remap(tmp_path, monkeypatch, remap)

    assert names[45] == "VS/FIELD"                               # shared compound pin kept whole
    assert sum(1 for v in names.values() if v == "FIELD") == 0   # no scattered FIELD
    assert "FIELD" not in rep["flags"]["duplicates"]
    assert any("rejected" in r.lower() for r in rep["repairs"])


def test_column_remap_still_accepted_when_it_only_renumbers(tmp_path, monkeypatch):
    # A legitimate column fix (re-number the SAME distinct names, no new duplicates)
    # must still be applied -- the guard rejects only remaps that scatter a name.
    base = {n: f"SIG{n}" for n in range(1, 49)}; base[45] = "VS/FIELD"
    remap = {str(n): base[(n % 48) + 1] for n in range(1, 49)}   # pure re-numbering
    rep, names = _drive_column_remap(tmp_path, monkeypatch, remap)
    assert names[44] == "VS/FIELD"                               # VS/FIELD moved 45 -> 44
    assert rep["flags"]["duplicates"] == []
    assert any("re-mapped" in r for r in rep["repairs"])
