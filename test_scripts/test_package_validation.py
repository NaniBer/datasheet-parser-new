#!/usr/bin/env python3
"""Check if we have package definitions for returned packages."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.schematic_generator.package_geometry import PackageType, get_schematic_parameters, parse_package_type

SUPPORTED_PACKAGES = {
    PackageType.DIP,
    PackageType.SOIC,
    PackageType.TQFP,
    PackageType.LQFP,
    PackageType.QFN,
    PackageType.BGA,
    PackageType.LCCC,
    PackageType.CDIP,
}

PACKAGE_ALIASES = {
    # LCCC aliases
    "LCCC": PackageType.LCCC,
    "LGA": PackageType.LCCC,
    "CDIP": PackageType.CDIP,

    # Add other aliases as needed
}

def has_package_definition(package_type_str: str) -> tuple[bool, str]:
    """
    Check if we have a package definition for the returned package type.

    Args:
        package_type_str: Package type string from LLM (e.g., "SOIC-16", "LCCC-20")

    Returns:
        (has_definition, standardized_name) where:
        - has_definition: True if we have parameters for this package
        - standardized_name: The standardized package type name
    """
    # Clean up the package string
    pkg_str = package_type_str.upper().strip()

    # Remove pin count from package type (e.g., "SOIC-16" -> "SOIC")
    # Split on numbers/dashes
    import re
    pkg_base = re.sub(r'[-_].*\d+', '', pkg_str).strip()

    # Map aliases to standard types
    for alias, std_type in PACKAGE_ALIASES.items():
        if pkg_base == alias or pkg_str.startswith(alias):
            # Check if we have definition for this type
            if std_type in SUPPORTED_PACKAGES:
                return (True, std_type.value)
            else:
                return (False, std_type.value)

    # Try direct match
    for supported_type in SUPPORTED_PACKAGES:
        if pkg_base == supported_type.value or pkg_str.startswith(supported_type.value):
            return (True, supported_type.value)

    # Not found in supported list
    return (False, pkg_str)

def validate_packages(packages_list: list) -> dict:
    """
    Validate all packages returned by LLM.

    Args:
        packages_list: List of package dicts from LLM response

    Returns:
        Dict with validation results for each package
    """
    results = {}

    for pkg in packages_list:
        pkg_type = pkg.get('type', 'Unknown')
        has_def, std_name = has_package_definition(pkg_type)

        results[pkg_type] = {
            'has_definition': has_def,
            'standardized_name': std_name,
            'pin_count': pkg.get('pin_count', 0),
            'is_supported': has_def
        }

    return results

# Test with different package types
print("=" * 80)
print("Testing Package Definition Checking")
print("=" * 80)

test_packages = [
    "SOIC-16",
    "DIP-8",
    "QFN-24",
    "LCCC-20",
    "TQFP-32",
    "LGA-64",
    "BGA-100",
    "UNKNOWN-20",
]

for pkg_type in test_packages:
    has_def, std_name = has_package_definition(pkg_type)

    status = "✅ Supported" if has_def else "❌ Not supported"
    print(f"{pkg_type:15s} -> {std_name:15s} : {status}")

# Test with actual package data
print("\n" + "=" * 80)
print("Testing with Simulated LLM Response")
print("=" * 80)

simulated_response = {
    "component_name": "74HC595",
    "packages": [
        {
            "type": "SOIC-16",
            "pin_count": 16,
            "pins": [...]
        },
        {
            "type": "LCCC-20",
            "pin_count": 20,
            "pins": [...]
        },
        {
            "type": "QFN-24",
            "pin_count": 24,
            "pins": [...]
        }
    ]
}

results = validate_packages(simulated_response['packages'])

print("\nValidation Results:")
for pkg_type, result in results.items():
    status = "✅" if result['is_supported'] else "❌"
    print(f"  {pkg_type:15s}: {status}")
    print(f"    Standardized: {result['standardized_name']}")
    print(f"    Pin count: {result['pin_count']}")
    print(f"    Has definition: {result['has_definition']}")
    print()
