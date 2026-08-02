"""Tests for pin_grounding: catching LLM-fabricated pins by grounding their
NUMBER against the numbers that actually appear in the datasheet's parsed
pin-table rows.
"""

import copy

import pytest

try:
    from src.pdf_extractor.pin_grounding import (
        build_pin_number_index,
        drop_ungrounded_pins,
    )
    from src.models.pin_data import Pin, PinData, PackageInfo
except ImportError:  # pragma: no cover - compatibility for top-level imports
    from pdf_extractor.pin_grounding import (
        build_pin_number_index,
        drop_ungrounded_pins,
    )
    from models.pin_data import Pin, PinData, PackageInfo


HEADER_ROW = ["PIN", "NAME", "TYPE", "DESCRIPTION"]


def _clean_ten_pin_table():
    names = {
        1: "VCC",
        2: "GND",
        3: "D0",
        4: "D1",
        5: "D2",
        6: "D3",
        7: "D4",
        8: "D5",
        9: "D6",
        10: "D7",
    }
    rows = [HEADER_ROW]
    for number, name in names.items():
        rows.append([str(number), name, "I/O", f"Data line {number}"])
    return rows, names


# ---------------------------------------------------------------------------
# build_pin_number_index
# ---------------------------------------------------------------------------


def test_build_index_clean_ten_row_table():
    table, names = _clean_ten_pin_table()
    tables = [(1, table)]

    index = build_pin_number_index(tables)

    assert set(index.keys()) == set(range(1, 11))
    for number, name in names.items():
        assert index[number] == {name.upper()}


def test_build_index_empty_tables_returns_empty_dict():
    assert build_pin_number_index([]) == {}


def test_build_index_na_only_table_returns_empty_dict():
    tables = [(1, [["N/A", "N/A", "N/A"]])]
    assert build_pin_number_index(tables) == {}


def test_build_index_handles_range_row():
    table = [
        HEADER_ROW,
        ["1-4", "NC", "-", "No connect"],
    ]
    tables = [(1, table)]

    index = build_pin_number_index(tables)

    assert set(index.keys()) == {1, 2, 3, 4}
    for number in (1, 2, 3, 4):
        assert index[number] == {"NC"}


# ---------------------------------------------------------------------------
# Safety invariant: only NO-CONNECT pins are ever dropped. Real signal pins
# whose numbers are absent from the index (noisy/incomplete indices from
# multi-package STM32/AVR pin tables or register bit-field tables) must NEVER
# be dropped (regression: false-positive drops found by the de-risking pass).
# ---------------------------------------------------------------------------


def test_drop_never_removes_ungrounded_signal_pins():
    # Real signal pins numbered past the index (as when a multi-package table
    # only yields one variant's column). None are NC, so none may be dropped
    # even though 11-16 are absent from the index.
    pins = [{"number": n, "name": f"PA{n}", "function": None} for n in range(1, 17)]
    pin_data = PinData(
        component_name="STM32-LIKE",
        packages=[{"type": "LQFP-16", "pin_count": 16, "pins": pins}],
    )
    index = {n: set() for n in range(1, 11)}  # only 1-10 grounded

    dropped = drop_ungrounded_pins(pin_data, index)

    assert dropped == 0
    assert pin_data.packages[0]["pin_count"] == 16
    assert [p["number"] for p in pin_data.packages[0]["pins"]] == list(range(1, 17))


def test_drop_removes_only_ungrounded_nc_from_noisy_index():
    # A noisy index (spurious numbers from spec/register tables) must not drop
    # real signals; only the ungrounded NC padding goes.
    pins = [{"number": n, "name": f"IO{n}", "function": None} for n in range(1, 11)]
    pins += [{"number": n, "name": "NC", "function": "none"} for n in range(11, 15)]
    pin_data = PinData(
        component_name="NOISY",
        packages=[{"type": "QFN-14", "pin_count": 14, "pins": pins}],
    )
    index = {n: set() for n in range(1, 11)}
    index[40] = set()   # spec-table noise
    index[600] = set()  # spec-table noise

    dropped = drop_ungrounded_pins(pin_data, index)

    assert dropped == 4
    package = pin_data.packages[0]
    assert package["pin_count"] == 10
    assert [p["number"] for p in package["pins"]] == list(range(1, 11))


# ---------------------------------------------------------------------------
# drop_ungrounded_pins - multi-package ("packages" of dicts) shape
# ---------------------------------------------------------------------------


def _fabricated_multi_package_pin_data():
    pins = []
    for number in range(1, 11):
        pins.append({"number": number, "name": f"D{number}", "function": None})
    for number in range(11, 21):
        pins.append({"number": number, "name": "NC", "function": "none"})

    return PinData(
        component_name="FAKE-PART",
        packages=[
            {
                "type": "QFN-20",
                "pin_count": 20,
                "pins": pins,
            }
        ],
    )


def test_drop_ungrounded_pins_multi_package_fabrication():
    pin_data = _fabricated_multi_package_pin_data()
    index = {number: set() for number in range(1, 11)}

    dropped = drop_ungrounded_pins(pin_data, index)

    assert dropped == 10
    package = pin_data.packages[0]
    assert package["pin_count"] == 10
    assert package["type"] == "QFN-10"
    assert [pin["number"] for pin in package["pins"]] == list(range(1, 11))
    assert all(pin["number"] <= 10 for pin in package["pins"])


def test_drop_ungrounded_pins_guard_empty_index_no_op():
    pin_data = _fabricated_multi_package_pin_data()
    before = copy.deepcopy(pin_data)

    dropped = drop_ungrounded_pins(pin_data, {})

    assert dropped == 0
    assert pin_data == before


def test_drop_ungrounded_pins_guard_all_absent_no_op():
    pin_data = _fabricated_multi_package_pin_data()
    before = copy.deepcopy(pin_data)
    # Index built from a wholly different table - none of these numbers
    # appear in the extracted pin_data at all.
    index = {101: set(), 102: set()}

    dropped = drop_ungrounded_pins(pin_data, index)

    assert dropped == 0
    assert pin_data == before


def test_drop_ungrounded_pins_keeps_real_pin_named_nc_when_grounded():
    pins = []
    for number in range(1, 11):
        pins.append({"number": number, "name": f"D{number}", "function": None})
    # A genuine pin 11 named "NC" - the datasheet's own table lists it, so
    # the index contains 11 too. This must NOT be dropped.
    pins.append({"number": 11, "name": "NC", "function": "none"})

    pin_data = PinData(
        component_name="REAL-PART",
        packages=[
            {
                "type": "QFN-11",
                "pin_count": 11,
                "pins": pins,
            }
        ],
    )
    index = {number: set() for number in range(1, 12)}

    dropped = drop_ungrounded_pins(pin_data, index)

    assert dropped == 0
    package = pin_data.packages[0]
    assert package["pin_count"] == 11
    assert package["type"] == "QFN-11"
    assert [pin["number"] for pin in package["pins"]] == list(range(1, 12))


# ---------------------------------------------------------------------------
# drop_ungrounded_pins - single-package legacy shape (PinData.package + .pins)
# ---------------------------------------------------------------------------


def _fabricated_legacy_pin_data():
    pins = [Pin(number=n, name=f"D{n}", function=None) for n in range(1, 11)]
    pins += [Pin(number=n, name="NC", function="none") for n in range(11, 21)]

    return PinData(
        component_name="FAKE-PART-LEGACY",
        package=PackageInfo(type="QFN-20", pin_count=20, width=5.0, height=5.0),
        pins=pins,
    )


def test_drop_ungrounded_pins_legacy_single_package_fabrication():
    pin_data = _fabricated_legacy_pin_data()
    index = {number: set() for number in range(1, 11)}

    dropped = drop_ungrounded_pins(pin_data, index)

    assert dropped == 10
    assert pin_data.package.pin_count == 10
    assert pin_data.package.type == "QFN-10"
    assert [pin.number for pin in pin_data.pins] == list(range(1, 11))


def test_drop_ungrounded_pins_legacy_guard_empty_index_no_op():
    pin_data = _fabricated_legacy_pin_data()
    before = copy.deepcopy(pin_data)

    dropped = drop_ungrounded_pins(pin_data, {})

    assert dropped == 0
    assert pin_data == before


def test_drop_ungrounded_pins_legacy_guard_all_absent_no_op():
    pin_data = _fabricated_legacy_pin_data()
    before = copy.deepcopy(pin_data)
    index = {101: set(), 102: set()}

    dropped = drop_ungrounded_pins(pin_data, index)

    assert dropped == 0
    assert pin_data == before


# ---------------------------------------------------------------------------
# Type re-suffix behavior
# ---------------------------------------------------------------------------


def test_type_without_numeric_suffix_left_unchanged_multi_package():
    pins = []
    for number in range(1, 11):
        pins.append({"number": number, "name": f"D{number}", "function": None})
    for number in range(11, 21):
        pins.append({"number": number, "name": "NC", "function": "none"})

    pin_data = PinData(
        component_name="FAKE-SOIC",
        packages=[
            {
                "type": "SOIC",
                "pin_count": 20,
                "pins": pins,
            }
        ],
    )
    index = {number: set() for number in range(1, 11)}

    dropped = drop_ungrounded_pins(pin_data, index)

    assert dropped == 10
    package = pin_data.packages[0]
    assert package["type"] == "SOIC"
    assert package["pin_count"] == 10


def test_type_without_numeric_suffix_left_unchanged_legacy():
    pins = [Pin(number=n, name=f"D{n}", function=None) for n in range(1, 11)]
    pins += [Pin(number=n, name="NC", function="none") for n in range(11, 21)]

    pin_data = PinData(
        component_name="FAKE-SOIC-LEGACY",
        package=PackageInfo(type="SOIC", pin_count=20, width=5.0, height=5.0),
        pins=pins,
    )
    index = {number: set() for number in range(1, 11)}

    dropped = drop_ungrounded_pins(pin_data, index)

    assert dropped == 10
    assert pin_data.package.type == "SOIC"
    assert pin_data.package.pin_count == 10


# ---------------------------------------------------------------------------
# Missing / empty pins should be left alone
# ---------------------------------------------------------------------------


def test_drop_ungrounded_pins_missing_pins_list_is_a_no_op():
    pin_data = PinData(
        component_name="NO-PINS",
        packages=[{"type": "QFN-20", "pin_count": 20}],
    )
    index = {number: set() for number in range(1, 11)}

    dropped = drop_ungrounded_pins(pin_data, index)

    assert dropped == 0
    assert pin_data.packages[0]["pin_count"] == 20
    assert pin_data.packages[0]["type"] == "QFN-20"
