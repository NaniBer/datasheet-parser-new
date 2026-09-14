"""Task 1 — stop & trace hallucinations: pin provenance + the abstention gate.

Covers two pieces:
  * assess_pin_grounding — tags each pin grounded/weak/unsupported/nc by
    checking whether its (number, name) pairing is evidenced in the datasheet.
  * _apply_grounding_gate — refuses a provably-hallucinated pinout (fail-closed
    by default), while NOT over-refusing graphical pinouts whose text layer is
    garbled (the measured MCP3208=100% / TL072=83% / AD712=25% reality).
"""

import pytest

from src.pdf_extractor.pin_grounding import assess_pin_grounding, pin_number_coverage
from src.main import _apply_grounding_gate
from src.models.pin_data import PinData, Pin
from src.exceptions import ValidationError


class _Content:
    """Minimal ExtractedContent stand-in (text + optional tables)."""

    def __init__(self, text, tables=None):
        self.text_content = text
        self.tables = tables or []


# A source shaped like a real pin table: number and name share a line.
TABLE_SRC = "--- Page 1 ---\n1 VDD\n2 CLK\n3 DOUT\n4 GND\nThe device also has an offset trim."


# --------------------------- grounding engine ---------------------------

def test_grounding_classifies_each_tier():
    pd = PinData(component_name="X", pins=[
        Pin(1, "VDD"),      # number + name on one line -> grounded
        Pin(4, "GND"),      # grounded
        Pin(5, "offset"),   # in prose, not beside a number -> weak
        Pin(6, "ZORP"),     # nowhere -> unsupported
        Pin(7, "NC"),       # no-connect -> nc
    ])
    tally = assess_pin_grounding(pd, _Content(TABLE_SRC))
    status = {p.number: p.grounding for p in pd.pins}
    assert status == {1: "grounded", 4: "grounded", 5: "weak", 6: "unsupported", 7: "nc"}
    assert tally == {"grounded": 2, "weak": 1, "unsupported": 1, "nc": 1, "total": 5}


def test_grounding_handles_short_symbolic_names():
    # "V-"/"V+" normalize to a single char; they must still ground by literal match.
    pd = PinData(component_name="X", pins=[Pin(4, "V-"), Pin(8, "V+")])
    assess_pin_grounding(pd, _Content("--- Page 1 ---\n4 V-\n8 V+"))
    assert [p.grounding for p in pd.pins] == ["grounded", "grounded"]


def test_grounding_records_evidence_and_page():
    pd = PinData(component_name="X", pins=[Pin(2, "CLK")])
    assess_pin_grounding(pd, _Content(TABLE_SRC))
    pin = pd.pins[0]
    assert pin.source_page == 1
    assert "CLK" in (pin.source_evidence or "")


# --------------------------- abstention gate ---------------------------

def test_gate_refuses_hallucinated_pin_amid_grounded():
    # 4 grounded + 1 invented name -> trustworthy context -> fail closed.
    pd = PinData(component_name="X", pins=[
        Pin(1, "VDD"), Pin(2, "CLK"), Pin(3, "DOUT"), Pin(4, "GND"), Pin(5, "ZORP")])
    with pytest.raises(ValidationError) as exc:
        _apply_grounding_gate(pd, _Content(TABLE_SRC), force_best_effort=False)
    assert "ZORP" in str(exc.value)


def test_gate_force_best_effort_downgrades_to_flag():
    pd = PinData(component_name="X", pins=[
        Pin(1, "VDD"), Pin(2, "CLK"), Pin(3, "DOUT"), Pin(4, "GND"), Pin(5, "ZORP")])
    _apply_grounding_gate(pd, _Content(TABLE_SRC), force_best_effort=True)  # no raise
    assert pd.validation_errors and any("ZORP" in e for e in pd.validation_errors)


def test_gate_does_not_refuse_low_grounding_graphical_pinout():
    # Simulates AD712: correct names, but garbled diagram text can't confirm them.
    # Must NOT refuse (that would reject every picture-based pinout); flag instead.
    garbled = "--- Page 1 ---\nINVER IN T P IN U G T 2 7 OUTPUT\nOUTPUT 1 8 V+"
    pd = PinData(component_name="AD712", pins=[
        Pin(1, "OUTPUT A"), Pin(2, "INVERTING INPUT"), Pin(3, "NONINVERTING INPUT"),
        Pin(4, "V-"), Pin(5, "NONINVERTING INPUT"), Pin(6, "INVERTING INPUT"),
        Pin(7, "OUTPUT B"), Pin(8, "V+")])
    _apply_grounding_gate(pd, _Content(garbled), force_best_effort=False)  # must not raise
    assert pd.validation_errors and any("unverified" in e for e in pd.validation_errors)


def test_gate_passes_clean_when_well_grounded():
    pd = PinData(component_name="X", pins=[
        Pin(1, "VDD"), Pin(2, "CLK"), Pin(3, "DOUT"), Pin(4, "GND")])
    _apply_grounding_gate(pd, _Content(TABLE_SRC), force_best_effort=False)  # no raise
    assert not pd.validation_errors  # nothing flagged


def test_gate_noop_when_no_signal_pins():
    pd = PinData(component_name="X", pins=[Pin(1, "NC"), Pin(2, "NC")])
    _apply_grounding_gate(pd, _Content(TABLE_SRC), force_best_effort=False)  # no raise
    assert not pd.validation_errors


# ------------------- coverage self-check (invention vs graphical) -------------------

def test_pin_number_coverage_separates_invention_from_graphical():
    # Invented pinout: the pins' numbers appear nowhere in the prose source.
    prose = "--- Page 1 ---\nThe ZXQ is a 14-pin quad op-amp with V+ and V- supplies."
    invented = PinData(component_name="ZXQ", pins=[Pin(i, f"IN{i}") for i in range(1, 15)])
    assert pin_number_coverage(invented, _Content(prose)) < 0.5

    # Real discrete: names don't ground, but the package drawing carries "1 2 3".
    drawing = "--- Page 1 ---\nPin 1 Pin 2 Pin 3   TO-92 package outline"
    real = PinData(component_name="REG", pins=[Pin(1, "VIN"), Pin(2, "GND"), Pin(3, "VOUT")])
    assert pin_number_coverage(real, _Content(drawing)) >= 0.5


def test_gate_refuses_invented_pinout_low_number_coverage():
    # Numbers absent from source -> invented -> refuse (this is the trap case).
    prose = "--- Page 1 ---\nThe ZXQ is a 14-pin quad op-amp with V+ and V- supplies."
    pd = PinData(component_name="ZXQ", pins=[Pin(i, f"IN{i}") for i in range(1, 15)])
    with pytest.raises(ValidationError) as exc:
        _apply_grounding_gate(pd, _Content(prose), force_best_effort=False)
    assert "not grounded" in str(exc.value)


def test_gate_keeps_graphical_discrete_when_numbers_present():
    # Names garbled/ungrounded, but pin numbers are in the drawing -> flag, not refuse.
    drawing = "--- Page 1 ---\n1 2 3 4   bridge rectifier package outline"
    pd = PinData(component_name="MB10F", pins=[
        Pin(1, "AC1"), Pin(2, "AC2"), Pin(3, "PLUS"), Pin(4, "MINUS")])
    _apply_grounding_gate(pd, _Content(drawing), force_best_effort=False)  # must NOT raise
    assert pd.validation_errors and any("unverified" in e for e in pd.validation_errors)
