"""Tests for the extraction output-contract vocabularies + validation helpers.

Covers alias normalization, the unknown-member fallback (no forced guessing),
role->side and device-class->refdes mappings, and the non-raising pin validator.
No extraction/generation behaviour is exercised.
"""
import pytest

from src.models import (
    ELECTRICAL_TYPES, PIN_ROLES, DEVICE_CLASSES, RecordPin,
    normalize_electrical_type, normalize_role, role_side, refdes_prefix,
    validate_pin_semantics,
)


# --- electrical_type normalization -------------------------------------------
@pytest.mark.parametrize("raw, expected", [
    ("input", "input"),                       # canonical passthrough
    ("INPUT", "input"),                        # case-insensitive
    (" power_in ", "power_in"),                # whitespace
    ("open_drain", "open_collector"),          # alias: drain == collector (ERC)
    ("tristate", "tri_state"),                 # alias spelling
    ("tri-state", "tri_state"),
    ("analog", "passive"),                     # analog is not an ERC type
    ("power", "power_in"),                     # alias
    ("nc", "no_connect"),                      # alias
    ("", "unspecified"),                       # unknown member, not a guess
    ("unknown", "unspecified"),
    ("free", "unspecified"),
    ("wibble", None),                          # off-contract -> None
    (None, None),
])
def test_normalize_electrical_type(raw, expected):
    assert normalize_electrical_type(raw) == expected


def test_all_canonical_electrical_types_normalize_to_themselves():
    for t in ELECTRICAL_TYPES:
        assert normalize_electrical_type(t) == t


# --- role normalization + side mapping ---------------------------------------
@pytest.mark.parametrize("raw, expected", [
    ("supply", "supply"),
    ("VCC", "supply"), ("gnd", "ground"),
    ("analog_io", "analog"),
    ("dnc", "nc"), ("reserved", "nc"),
    ("", "other"),
    ("nonsense", None),
    (None, None),
])
def test_normalize_role(raw, expected):
    assert normalize_role(raw) == expected


# SnapEDA convention (QC S1): right = power/outputs/ground/thermal; left = the
# rest (control, inputs, io, data/analog, other).
@pytest.mark.parametrize("role, side", [
    ("supply", "right"), ("ground", "right"), ("thermal", "right"),
    ("input", "left"), ("clock", "left"), ("control", "left"),
    ("output", "right"), ("io", "left"), ("data", "left"), ("analog", "left"),
    ("nc", "unplaced"),
    ("other", "left"), (None, "left"),        # unknown defaults left
])
def test_role_side(role, side):
    assert role_side(role) == side


def test_every_role_has_a_side():
    for r in PIN_ROLES:
        assert role_side(r) in {"top", "bottom", "left", "right", "unplaced"}


# --- device_class -> refdes prefix (SYM-10) ----------------------------------
@pytest.mark.parametrize("cls, prefix", [
    ("resistor", "R"), ("capacitor", "C"), ("inductor", "L"),
    ("diode", "D"), ("led", "D"), ("transistor", "Q"),
    ("ic", "U"), ("connector", "J"), ("crystal", "Y"), ("test_point", "TP"),
    ("IC", "U"),                               # case-insensitive
    ("other", "U"), ("garbage", "U"), (None, "U"),   # unknown -> U
])
def test_refdes_prefix(cls, prefix):
    assert refdes_prefix(cls) == prefix


def test_every_device_class_maps_to_a_prefix():
    for c in DEVICE_CLASSES:
        assert refdes_prefix(c) != "" and refdes_prefix(c) is not None


# --- validate_pin_semantics (non-raising) ------------------------------------
def test_validate_pin_in_contract_is_clean():
    p = RecordPin(number="1", name="VCC", electrical_type="power_in", role="supply")
    assert validate_pin_semantics(p) == []


def test_validate_pin_unknown_fields_allowed():
    # None/unspecified must NOT be reported — the extractor may not know.
    p = RecordPin(number="1", name="X")
    assert validate_pin_semantics(p) == []
    p2 = RecordPin(number="1", name="X", electrical_type="unspecified", role="other")
    assert validate_pin_semantics(p2) == []


def test_validate_pin_off_contract_values_reported():
    p = RecordPin(number="7", name="D0", electrical_type="analog", role="bus")
    issues = validate_pin_semantics(p)
    assert len(issues) == 2
    assert any("electrical_type" in m and "analog" in m for m in issues)
    assert any("role" in m and "bus" in m for m in issues)


def test_validator_does_not_raise_on_odd_input():
    # Must never throw — it's a reporting helper, not a gate.
    p = RecordPin(number="", name="", electrical_type="", role="")
    assert isinstance(validate_pin_semantics(p), list)
