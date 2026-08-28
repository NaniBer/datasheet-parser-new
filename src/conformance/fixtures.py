"""Known-good, per-family generation fixtures.

To grade *generation* conformance we must feed the builders correct inputs — not
run the PDF -> LLM extraction, whose errors would masquerade as generation
defects. Each fixture is a hand-verified, spec-correct component: real package
type, pin count and 1..N pins. Dimensions are left to the JEDEC family defaults
(``get_footprint_defaults`` / ``build_spec``), which are themselves correct
nominal values — so every fixture is a "the inputs are right; is the geometry
right?" test, one per supported package family.

Extend by adding a ``FamilyFixture`` row; the driver in
``tools/gen_conformance.py`` builds all three artifacts and grades them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class FamilyFixture:
    key: str                       # short label / output stem, e.g. "soic8"
    package_type: str              # e.g. "SOIC-8"
    pin_count: int
    component_name: str
    lead_style: str                # informational: expected body template
    pins: List[Dict[str, str]] = field(default_factory=list)


def _pins(n: int) -> List[Dict[str, str]]:
    """Generic 1..N pins. Names don't affect geometry checks; numbering does."""
    return [{"number": str(i), "name": f"P{i}"} for i in range(1, n + 1)]


# A functional fixture carries explicit roles so it clears the SYM-04 gate
# (concrete supply + ground, >= 50% concrete roles) and the symbol is laid out
# by function. Names/roles are hand-set so grading is deterministic and needs no
# LLM. Generic ``_pins`` fixtures stay role-less and SKIP SYM-04 (below gate),
# which is exactly how the harness should treat an unclassified part.
_FUNC8_PINS: List[Dict[str, str]] = [
    {"number": "1", "name": "CLK",  "role": "clock"},
    {"number": "2", "name": "RST",  "role": "reset"},
    {"number": "3", "name": "IN0",  "role": "input"},
    {"number": "4", "name": "GND",  "role": "ground"},
    {"number": "5", "name": "OUT0", "role": "output"},
    {"number": "6", "name": "OUT1", "role": "output"},
    {"number": "7", "name": "IO0",  "role": "io"},
    {"number": "8", "name": "VCC",  "role": "supply"},
]


# One representative per supported family. Numbering is a complete 1..N set so
# the pin/pad-mapping and numbering checks exercise the real path.
FIXTURES: List[FamilyFixture] = [
    FamilyFixture("dip8",    "DIP-8",     8,  "GEN_DIP8",    "through_hole", _pins(8)),
    FamilyFixture("soic8",   "SOIC-8",    8,  "GEN_SOIC8",   "gullwing",     _pins(8)),
    # Functional-grouping fixture (SYM-04): explicit roles => clears the gate,
    # symbol is laid out by function. Same SOIC-8 geometry as soic8 otherwise.
    FamilyFixture("func8",   "SOIC-8",    8,  "GEN_FUNC8",   "gullwing",     _FUNC8_PINS),
    FamilyFixture("soic16",  "SOIC-16",   16, "GEN_SOIC16",  "gullwing",     _pins(16)),
    FamilyFixture("sop16",   "SOP-16",    16, "GEN_SOP16",   "gullwing",     _pins(16)),
    FamilyFixture("ssop20",  "SSOP-20",   20, "GEN_SSOP20",  "gullwing",     _pins(20)),
    FamilyFixture("tssop20", "TSSOP-20",  20, "GEN_TSSOP20", "gullwing",     _pins(20)),
    FamilyFixture("msop10",  "MSOP-10",   10, "GEN_MSOP10",  "gullwing",     _pins(10)),
    FamilyFixture("qfn32",   "QFN-32",    32, "GEN_QFN32",   "leadless",     _pins(32)),
    FamilyFixture("dfn8",    "DFN-8",     8,  "GEN_DFN8",    "leadless",     _pins(8)),
    FamilyFixture("son8",    "WSON-8",    8,  "GEN_WSON8",   "leadless",     _pins(8)),
    FamilyFixture("lqfp48",  "LQFP-48",   48, "GEN_LQFP48",  "quad_gullwing", _pins(48)),
    FamilyFixture("tqfp44",  "TQFP-44",   44, "GEN_TQFP44",  "quad_gullwing", _pins(44)),
    # Families whose footprint/body is expected to refuse (fail-closed) today —
    # included so the map shows them explicitly rather than hiding the gap.
    FamilyFixture("bga64",   "BGA-64",    64, "GEN_BGA64",   "bga",          _pins(64)),
    FamilyFixture("to220",   "TO-220-3",  3,  "GEN_TO220",   "power_tab",    _pins(3)),
]
