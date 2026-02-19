"""Output formatting utilities for pin data."""

from typing import Dict, List, Any


def format_pin_data(pin_data: Dict[str, Any]) -> str:
    """
    Format pin data for LLM processing or output.

    Args:
        pin_data: Dictionary containing extracted pin information

    Returns:
        Formatted string representation
    """
    component = pin_data.get('component_name', 'Unknown')
    package = pin_data.get('package', {})

    # Format header
    result = []
    result.append("=" * 70)
    result.append(f"Component: {component}")
    result.append(f"Package: {package.get('type', 'Unknown')}-{package.get('pin_count', 0)}")
    result.append(f"Dimensions: {package.get('width', 0)}mm x {package.get('height', 0)}mm")
    result.append(f"Pitch: {package.get('pitch', 'N/A')}")
    result.append("=" * 70)
    result.append("")

    # Format pins
    pins = pin_data.get('pins', [])
    result.append(f"Total Pins: {len(pins)}")
    result.append("")

    for pin in pins:
        pin_num = pin.get('number', '?')
        pin_name = pin.get('name', '')
        pin_func = pin.get('function', '')

        func_str = f" ({pin_func})" if pin_func else ""
        result.append(f"Pin {pin_num}: {pin_name}{func_str}")

    return "\n".join(result)
