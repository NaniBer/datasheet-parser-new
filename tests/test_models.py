"""Tests for data models."""

import pytest

from src.models.pin_data import Pin, PackageInfo, PinData


def test_pin_creation():
    """Test creating a Pin object."""
    pin = Pin(number=1, name="VCC", function="power")
    assert pin.number == 1
    assert pin.name == "VCC"
    assert pin.function == "power"


def test_pin_without_function():
    """Test creating a Pin without function."""
    pin = Pin(number=2, name="NC")
    assert pin.number == 2
    assert pin.name == "NC"
    assert pin.function is None


def test_package_info_creation():
    """Test creating a PackageInfo object."""
    package = PackageInfo(
        type="DIP",
        pin_count=28,
        width=7.5,
        height=15.0,
        pitch=2.54,
        thickness=3.0
    )
    assert package.type == "DIP"
    assert package.pin_count == 28
    assert package.width == 7.5
    assert package.height == 15.0
    assert package.pitch == 2.54
    assert package.thickness == 3.0


def test_package_info_minimal():
    """Test creating a PackageInfo with minimal required fields."""
    package = PackageInfo(type="QFN", pin_count=24, width=5.0, height=5.0)
    assert package.type == "QFN"
    assert package.pin_count == 24
    assert package.width == 5.0
    assert package.height == 5.0
    assert package.pitch is None
    assert package.thickness is None


def test_pin_data_creation():
    """Test creating a PinData object."""
    package = PackageInfo(type="DIP", pin_count=4, width=5.0, height=5.0)
    pins = [
        Pin(number=1, name="VCC", function="power"),
        Pin(number=2, name="OUT", function="output"),
        Pin(number=3, name="IN", function="input"),
        Pin(number=4, name="GND", function="ground"),
    ]
    pin_data = PinData(
        component_name="555 Timer",
        package=package,
        pins=pins,
        extraction_method="Table"
    )
    assert pin_data.component_name == "555 Timer"
    assert pin_data.package.type == "DIP"
    assert len(pin_data.pins) == 4
    assert pin_data.extraction_method == "Table"


def test_pin_data_empty_pins():
    """Test creating a PinData with empty pins list."""
    package = PackageInfo(type="QFN", pin_count=8, width=4.0, height=4.0)
    pin_data = PinData(
        component_name="Test IC",
        package=package,
        pins=[],
        extraction_method="Diagram"
    )
    assert pin_data.component_name == "Test IC"
    assert len(pin_data.pins) == 0
