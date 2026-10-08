"""Tests for the Slice A.2 fill-only pin-name classifier."""
import pytest

from src.models import classify_pin_name, ComponentRecord
from src.models.pin_data import PinData, PackageInfo, Pin


@pytest.mark.parametrize("name, etype, role", [
    ("VCC", "power_in", "supply"),
    ("VDD5", "power_in", "supply"),
    ("V+", "power_in", "supply"),
    ("GND", "power_in", "ground"),
    ("VSSA", "power_in", "ground"),
    ("V-", "power_in", "ground"),
    ("V–", "power_in", "ground"),          # en-dash minus (LM358 style)
    ("NC", "no_connect", "nc"),
    ("DNC", "no_connect", "nc"),
    ("EP", "passive", "thermal"),
    ("RESET", "input", "reset"),
    ("NRST", "input", "reset"),
    ("SRCLR", "input", "reset"),
    ("CLK", "input", "clock"),
    ("SRCLK", "input", "clock"),
    ("OSC_IN", "input", "oscillator"),
    ("OSC_OUT", "output", "oscillator"),
    ("OE", "input", "control"),
    ("CS", "input", "control"),
    ("EN", "input", "enable"),
    ("QA", "output", "data"),
    ("QH", "output", "data"),
    ("OUT1", "output", "output"),
    ("A5", "input", "address"),
    ("D3", "input", "data"),
    ("PA5", "bidirectional", "io"),
    ("PD13", "bidirectional", "io"),
    # regulator / LDO outputs the part sources -> power_out (AD9106 CLDO/DLDOx)
    ("CLDO", "power_out", "supply"),
    ("DLDO1", "power_out", "supply"),
    ("DLDO2", "power_out", "supply"),
    # adjust/set and sense pins -> passive/analog (AD9106 FSADJ2/CAL_SENSE)
    ("FSADJ2", "passive", "analog"),
    ("CAL_SENSE", "passive", "analog"),
    ("VADJ", "passive", "analog"),
    ("ISENSE", "passive", "analog"),
    # analog/digital supply rails with domain tags / +- (PGA2311 VD+/VA+/VA-)
    ("VD+", "power_in", "supply"),
    ("VA+", "power_in", "supply"),
    ("VA-", "power_in", "ground"),
    ("AVDD", "power_in", "supply"),
    ("DVDD", "power_in", "supply"),
    ("VDDIO", "power_in", "supply"),
    # ground rails with channel suffix (PGA2311 AGNDR/AGNDL)
    ("AGNDR", "power_in", "ground"),
    ("AGNDL", "power_in", "ground"),
    ("DGND", "power_in", "ground"),
    # SD/MMC data + command lines are bidirectional (693072010801)
    ("DAT0", "bidirectional", "data"),
    ("DAT2", "bidirectional", "data"),
    ("CD/DAT3", "bidirectional", "data"),
    ("CMD", "bidirectional", "data"),
])
def test_classify_known_names(name, etype, role):
    t, r, _ = classify_pin_name(name)
    assert (t, r) == (etype, role)


@pytest.mark.parametrize("name", ["IN1+", "IN2-", "PG", "PS/SYNC", "VAUX", "L1", "FB", "TRIGGER", "FOO", ""])
def test_ambiguous_names_stay_unknown(name):
    t, r, _ = classify_pin_name(name)
    assert t is None and r is None          # never guessed


# --- conservative active_low: markers only, never conventions -----------------
@pytest.mark.parametrize("name, expected", [
    ("OE#", True), ("/CS", True), ("RESET_N", True), ("W̅E̅", True),
    ("OE", False),        # convention-only inversion is NOT inferred
    ("RESET", False),
    ("NRST", False),
    ("VCC", False),
])
def test_active_low_conservative(name, expected):
    _, _, active_low = classify_pin_name(name)
    assert active_low is expected


# --- fill-only integration in from_pin_data -----------------------------------
def test_classifier_fills_blanks_only():
    pd = PinData(
        component_name="X",
        package=PackageInfo(type="DIP-8", pin_count=8, width=0, height=0),
        pins=[
            Pin(1, "VCC"),                                   # no semantics -> classifier fills
            Pin(2, "OUT1", electrical_type="input", role="clock"),  # already set -> must NOT override
        ],
    )
    rec = ComponentRecord.from_pin_data(pd)
    pins = {p.number: p for p in rec.selected().pins}
    # blank pin filled from the name
    assert pins["1"].electrical_type == "power_in" and pins["1"].role == "supply"
    # pre-set pin preserved (fill-only never overrides, even if "wrong")
    assert pins["2"].electrical_type == "input" and pins["2"].role == "clock"


def test_classifier_only_adds_active_low_never_removes():
    pd = PinData(
        component_name="X",
        package=PackageInfo(type="DIP-8", pin_count=8, width=0, height=0),
        pins=[
            Pin(1, "VCC", active_low=True),   # existing True must survive (no marker on VCC)
            Pin(2, "/CS"),                    # marker -> classifier adds True
        ],
    )
    pins = {p.number: p for p in ComponentRecord.from_pin_data(pd).selected().pins}
    assert pins["1"].active_low is True
    assert pins["2"].active_low is True
