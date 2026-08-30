"""Conformance harness: enforce the IDEEZA Component Generation Spec in code.

The harness turns the spec's ``must`` rules into automated checks that run over
generated artifacts (schematic GLB, footprint GLB, 3D body GLB/STEP) and emit a
machine-readable pass/fail report per part (spec rule ``V-05``). A corpus runner
aggregates those reports into one pass-rate plus a per-rule failure count, so
defects are fixed by *class* across the whole corpus rather than one part at a
time.

See docs/IDEEZA_Component_Generation_Spec.html for the rules and
docs/conformance-harness.md for how coverage maps onto them.
"""
from .model import CheckResult, CheckStatus, PartReport
from .rules import RULES, Rule
from .runner import evaluate_part

__all__ = [
    "CheckResult",
    "CheckStatus",
    "PartReport",
    "RULES",
    "Rule",
    "evaluate_part",
]
