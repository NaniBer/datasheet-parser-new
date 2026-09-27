"""Agentic repair layer: post-process an extracted pinout with cheap, targeted
LLM/vision calls so a low-cost extraction model reaches frontier-model accuracy.

See :mod:`src.agentic.repair` for the steps and :func:`repair_pins` for the entry point.
"""

from .repair import repair_pins, expand_groups_deterministic, is_group, is_suspicious, expand_numeric

__all__ = ["repair_pins", "expand_groups_deterministic", "is_group", "is_suspicious", "expand_numeric"]
