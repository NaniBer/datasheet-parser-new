"""Tests for package detector."""

import pytest

from src.utils.package_detector import PackageDetector
from src.models.pin_data import PackageInfo, PinData


def test_normalize_package_name():
    """Test normalizing package names."""
    detector = PackageDetector()

    assert detector.normalize_package_name("DIP-8") == "DIP"
    assert detector.normalize_package_name("soic-16") == "SOIC"
    assert detector.normalize_package_name("QFN-24") == "QFN"
    assert detector.normalize_package_name("VQFN") == "QFN"
    assert detector.normalize_package_name("DIL") == "DIP"


def test_detect_from_text():
    """Test detecting package type from text."""
    detector = PackageDetector()

    assert detector._detect_from_text("DIP-28 package") == "DIP"
    assert detector._detect_from_text("QFN-24 pin configuration") == "QFN"
    assert detector._detect_from_text("SOIC-8 small outline") == "SOIC"
    assert detector._detect_from_text("TSSOP-20 thin shrink") == "TSSOP"
    assert detector._detect_from_text("BGA ball grid array") == "BGA"


def test_is_quasi_square():
    """Test quasi-square detection."""
    detector = PackageDetector()

    # Square-ish dimensions
    assert detector._is_quasi_square(5.0, 5.0) is True
    assert detector._is_quasi_square(5.0, 5.5) is True
    assert detector._is_quasi_square(5.0, 6.0) is True

    # Not square
    assert detector._is_quasi_square(5.0, 8.0) is False
    assert detector._is_quasi_square(10.0, 5.0) is False


def test_estimate_dimensions_dip():
    """Test estimating DIP dimensions."""
    detector = PackageDetector()

    width, height = detector.estimate_dimensions("DIP", 28)
    assert width > 5.0
    assert height > 10.0


def test_estimate_dimensions_qfn():
    """Test estimating QFN dimensions."""
    detector = PackageDetector()

    width, height = detector.estimate_dimensions("QFN", 24)
    # QFN should be square-ish
    assert abs(width - height) < 2.0


def test_get_default_package():
    """Test getting default package based on pin count."""
    detector = PackageDetector()

    assert detector._get_default_package(4) in ["SOIC", "DIP"]
    assert detector._get_default_package(8) == "SOIC"
    assert detector._get_default_package(28) in ["DIP", "SOIC"]
    assert detector._get_default_package(32) == "QFN"
    assert detector._get_default_package(64) == "QFN"
