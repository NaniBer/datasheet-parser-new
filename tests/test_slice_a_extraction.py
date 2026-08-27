"""Slice A: the parser maps the new prompt fields onto the contract (offline).

Exercises LLMClient._parse_llm_response with fixture JSON (no network): the new
per-pin fields are parsed + normalized, deterministic backstops fill active_low
and nc, and the values flow into the ComponentRecord. Also proves legacy
function-only responses still parse.
"""
import json

from src.llm.client import LLMClient
from src.models import ComponentRecord


def _parse(payload: dict):
    return LLMClient()._parse_llm_response(json.dumps(payload))


def test_multi_package_semantics_parsed_and_normalized():
    pd = _parse({
        "component_name": "TESTIC",
        "packages": [{"type": "SOIC-8", "pin_count": 8, "pins": [
            {"number": 1, "name": "VCC", "electrical_type": "power_in", "role": "supply"},
            {"number": 2, "name": "/RESET", "electrical_type": "input", "role": "reset"},   # active_low omitted
            {"number": 3, "name": "OUT", "electrical_type": "open_drain", "role": "output"},  # alias
            {"number": 4, "name": "NC"},                                                       # nc backstop
        ]}],
        "selected_package_index": 0,
        "extraction_method": "Table",
    })
    pins = {p["number"]: p for p in pd.packages[0]["pins"]}
    assert pins[1]["electrical_type"] == "power_in" and pins[1]["role"] == "supply"
    assert pins[2]["active_low"] is True                      # backstop from "/RESET"
    assert pins[3]["electrical_type"] == "open_collector"     # open_drain normalized
    assert pins[4]["nc"] is True and pins[4]["electrical_type"] == "no_connect"

    # ...and the values flow into the ComponentRecord
    rec = ComponentRecord.from_pin_data(pd)
    rpins = {p.number: p for p in rec.selected().pins}
    assert rpins["1"].electrical_type == "power_in" and rpins["1"].role == "supply"
    assert rpins["2"].active_low is True
    assert rpins["4"].nc is True


def test_single_package_semantics_parsed():
    pd = _parse({
        "component_name": "LM358",
        "package": {"type": "DIP-8", "pin_count": 8},
        "pins": [
            {"number": 1, "name": "OUT1", "electrical_type": "output", "role": "output"},
            {"number": 4, "name": "GND", "electrical_type": "power_in", "role": "ground"},
        ],
        "extraction_method": "Table",
    })
    assert pd.pins[0].electrical_type == "output" and pd.pins[0].role == "output"
    assert pd.pins[1].role == "ground"
    assert pd.pins[0].active_low is False and pd.pins[0].nc is False


def test_off_contract_values_normalize_to_none_not_guessed():
    pd = _parse({
        "component_name": "X",
        "package": {"type": "DIP-8", "pin_count": 8},
        "pins": [{"number": 1, "name": "P1", "electrical_type": "wibble", "role": "bus"}],
        "extraction_method": "Table",
    })
    # unknown values -> None (never coerced to a wrong concrete value)
    assert pd.pins[0].electrical_type is None
    assert pd.pins[0].role is None


def test_legacy_function_only_response_still_parses():
    pd = _parse({
        "component_name": "OLD",
        "package": {"type": "DIP-8", "pin_count": 8},
        "pins": [{"number": 1, "name": "VCC", "function": "power"}],
        "extraction_method": "Table",
    })
    # role back-derived from legacy function via alias (power -> supply)
    assert pd.pins[0].role == "supply"
    assert pd.pins[0].electrical_type is None
