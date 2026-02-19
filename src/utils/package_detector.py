"""
Detect package type from extracted pin data.

This module helps identify and validate package types
from the pin data extracted from datasheets.
"""

import re
from typing import Optional, Tuple, Dict, List

from ..models.pin_data import PinData, PackageInfo


class PackageDetector:
    """Detect and validate package types from pin data."""

    # Common package patterns in datasheets
    PACKAGE_PATTERNS = {
        "DIP": [
            r"dip\s*\d*",
            r"dual\s*in\s*line",
            r"pdip",
            r"cerdip",
            r"spdip",
        ],
        "QFN": [
            r"qfn",
            r"quad\s*flat\s*no[-\s]?lead",
            r"vqfn",
            r"uqfn",
            r"dfn",
        ],
        "SOIC": [
            r"soic",
            r"small\s*outline[-\s]?ic",
            r"sop",
            r"ssop",
            r"msop",
        ],
        "TSSOP": [
            r"tssop",
            r"thin\s*shrink\s*small\s*outline",
        ],
        "BGA": [
            r"bga",
            r"ball\s*grid\s*array",
            r"lfbga",
            r"fbga",
        ],
        "LGA": [
            r"lga",
            r"land\s*grid\s*array",
        ],
        "TQFP": [
            r"tqfp",
            r"thin\s*quad\s*flat\s*pack",
        ],
    }

    # Typical dimensions by package type and pin count (in mm)
    # Format: (min_width, max_width, min_height, max_height)
    TYPICAL_DIMENSIONS: Dict[str, List[Tuple[float, float, float, float]]] = {
        "DIP": [
            (4.0, 10.0, 6.0, 10.0),   # 4-14 pins
            (8.0, 12.0, 10.0, 18.0),  # 16-28 pins
            (10.0, 15.0, 18.0, 30.0), # 32-64 pins
        ],
        "QFN": [
            (3.0, 6.0, 3.0, 6.0),     # 8-20 pins
            (4.0, 8.0, 4.0, 8.0),     # 24-48 pins
            (6.0, 12.0, 6.0, 12.0),   # 56+ pins
        ],
        "SOIC": [
            (4.0, 7.0, 6.0, 10.0),    # 8-16 pins
            (5.0, 8.0, 8.0, 15.0),    # 20-28 pins
        ],
        "TSSOP": [
            (3.0, 5.0, 4.0, 8.0),     # 8-20 pins
            (4.0, 6.5, 6.0, 12.0),    # 24-48 pins
        ],
    }

    def __init__(self):
        """Initialize the package detector."""
        self.pattern_cache = {}

    def detect_package_type(
        self,
        pin_data: PinData,
        hint: Optional[str] = None
    ) -> str:
        """
        Detect package type from pin data.

        Args:
            pin_data: PinData object with extracted information
            hint: Optional hint text (e.g., from datasheet section heading)

        Returns:
            Detected package type string
        """
        # First, check if package type is already specified
        specified_type = pin_data.package.type.upper()
        if specified_type and specified_type != "UNKNOWN":
            # Validate the specified type
            if self._validate_package_type(specified_type, pin_data):
                return specified_type

        # Try to detect from hint
        if hint:
            detected = self._detect_from_text(hint)
            if detected and self._validate_package_type(detected, pin_data):
                return detected

        # Try to detect from pin count and layout
        detected = self._detect_from_pin_layout(pin_data)
        if detected:
            return detected

        # Default to generic based on pin count
        return self._get_default_package(pin_data.package.pin_count)

    def _detect_from_text(self, text: str) -> Optional[str]:
        """
        Detect package type from text content.

        Args:
            text: Text to search for package patterns

        Returns:
            Detected package type or None
        """
        text_lower = text.lower()

        for pkg_type, patterns in self.PACKAGE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    return pkg_type

        return None

    def _detect_from_pin_layout(self, pin_data: PinData) -> Optional[str]:
        """
        Detect package type from pin count and layout.

        Args:
            pin_data: PinData object

        Returns:
            Detected package type or None
        """
        pin_count = pin_data.package.pin_count
        package = pin_data.package

        # Check dimensions
        width = package.width
        height = package.height

        # QFN: Square-ish, pins on all 4 sides
        if self._is_quasi_square(width, height, tolerance=0.3):
            if pin_count in [8, 16, 20, 24, 32, 48, 64]:
                return "QFN"

        # DIP: Rectangular, width >> height, even pin count, divisible by 2
        if pin_count % 2 == 0 and width > height * 1.5:
            if pin_count in [4, 6, 8, 14, 16, 18, 20, 24, 28, 40, 64]:
                return "DIP"

        # SOIC: Rectangular, smaller dimensions
        if width > height:
            if pin_count in [8, 14, 16, 20, 24, 28]:
                if width < 10 and height < 20:
                    return "SOIC"

        # TSSOP: Similar to SOIC but thinner
        if width > height:
            if pin_count in [8, 14, 16, 20, 24, 28, 32, 48]:
                if width < 8 and height < 15:
                    return "TSSOP"

        return None

    def _is_quasi_square(self, width: float, height: float, tolerance: float = 0.3) -> bool:
        """
        Check if dimensions are approximately square.

        Args:
            width: Width dimension
            height: Height dimension
            tolerance: Relative tolerance for aspect ratio

        Returns:
            True if dimensions are approximately square
        """
        if width == 0 or height == 0:
            return False

        ratio = max(width, height) / min(width, height)
        return ratio <= (1.0 + tolerance)

    def _validate_package_type(self, pkg_type: str, pin_data: PinData) -> bool:
        """
        Validate that the package type matches pin count and dimensions.

        Args:
            pkg_type: Package type to validate
            pin_data: PinData object

        Returns:
            True if package type is valid for the data
        """
        pin_count = pin_data.package.pin_count
        pkg_type_upper = pkg_type.upper()

        # Get expected dimensions
        expected_dims = self._get_expected_dimensions(pkg_type_upper, pin_count)
        if not expected_dims:
            return True  # No validation data available

        min_w, max_w, min_h, max_h = expected_dims
        actual_w = pin_data.package.width
        actual_h = pin_data.package.height

        # Check if dimensions are within expected range
        width_ok = min_w <= actual_w <= max_w
        height_ok = min_h <= actual_h <= max_h

        return width_ok and height_ok

    def _get_expected_dimensions(
        self, pkg_type: str, pin_count: int
    ) -> Optional[Tuple[float, float, float, float]]:
        """
        Get expected dimensions for a package type and pin count.

        Args:
            pkg_type: Package type
            pin_count: Number of pins

        Returns:
            Tuple of (min_width, max_width, min_height, max_height) or None
        """
        if pkg_type not in self.TYPICAL_DIMENSIONS:
            return None

        dims = self.TYPICAL_DIMENSIONS[pkg_type]

        # Select appropriate range based on pin count
        if pin_count <= 20:
            return dims[0]
        elif pin_count <= 48:
            return dims[1] if len(dims) > 1 else dims[0]
        else:
            return dims[2] if len(dims) > 2 else dims[-1]

    def _get_default_package(self, pin_count: int) -> str:
        """
        Get default package type based on pin count.

        Args:
            pin_count: Number of pins

        Returns:
            Default package type
        """
        if pin_count <= 8:
            return "SOIC"
        elif pin_count <= 20:
            return "SOIC"
        elif pin_count <= 28:
            if pin_count % 2 == 0:
                return "DIP"
            return "SOIC"
        elif pin_count <= 48:
            return "QFN"
        else:
            return "QFN"

    def estimate_dimensions(
        self,
        pkg_type: str,
        pin_count: int
    ) -> Tuple[float, float]:
        """
        Estimate package dimensions from type and pin count.

        Args:
            pkg_type: Package type
            pin_count: Number of pins

        Returns:
            Tuple of (width, height) in mm
        """
        expected = self._get_expected_dimensions(pkg_type.upper(), pin_count)

        if expected:
            min_w, max_w, min_h, max_h = expected
            # Return average of range
            return ((min_w + max_w) / 2, (min_h + max_h) / 2)

        # Default estimates if no data available
        if pkg_type.upper() == "DIP":
            base_width = 5.0 + pin_count * 0.1
            base_height = 10.0 + pin_count * 0.2
        elif pkg_type.upper() == "QFN":
            side = 3.0 + pin_count * 0.1
            base_width = side
            base_height = side
        elif pkg_type.upper() in ("SOIC", "TSSOP"):
            base_width = 5.0 + pin_count * 0.05
            base_height = 8.0 + pin_count * 0.15
        else:
            # Generic estimate
            base_width = 5.0 + pin_count * 0.05
            base_height = 8.0 + pin_count * 0.05

        return (base_width, base_height)

    def normalize_package_name(self, pkg_name: str) -> str:
        """
        Normalize a package name to standard format.

        Args:
            pkg_name: Raw package name string

        Returns:
            Normalized package name
        """
        pkg_upper = pkg_name.upper().strip()

        # Common aliases mapping
        aliases = {
            "DIL": "DIP",
            "DUAL INLINE": "DIP",
            "PDIP": "DIP",
            "VQFN": "QFN",
            "UQFN": "QFN",
            "DFN": "QFN",
            "SOP": "SOIC",
            "SSOP": "SOIC",
            "MSOP": "SOIC",
            "TQFP": "QFP",
            "LFBGA": "BGA",
        }

        # Check for exact match in aliases
        for alias, standard in aliases.items():
            if alias in pkg_upper:
                return standard

        # Check for pattern match
        detected = self._detect_from_text(pkg_name)
        if detected:
            return detected

        return pkg_upper
