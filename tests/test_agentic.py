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
