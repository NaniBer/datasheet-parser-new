"""Detect modules / system-in-package / grid-array parts whose PCB footprint
this pipeline should not build.

Modules (castellated Wi-Fi/BLE modules, LGA SiPs, power modules/IPMs) have a
land pattern that is nothing like the chip package their pin table resembles —
an ESP32 module reads as a QFN and once shipped a QFN-32 footprint for an
18-castellation part at exit 0. There is no generic land pattern for these, so
the correct outcome is schematic-only: emit the schematic, refuse the footprint.

The signals are document-level and kept conservative — a keyword in the title
or right next to a package/pinout term, not anywhere in prose — so a normal
chip that merely mentions "module" in a sentence is not misclassified.
"""

from __future__ import annotations

import re
from typing import Optional

# Grid-array families have no perimeter land pattern; a chip-style footprint is
# always wrong for them. (These also fail closed in the builder; flagging here
# yields a clearer schematic-only outcome instead of a footprint build error.)
_GRID_ARRAY_FAMILIES = {"LGA", "BGA"}

# Words that essentially only appear for modules/SiPs, safe to match anywhere.
_STRONG_ANYWHERE = re.compile(
    r"\bcastellated\b|\bland[\s-]*grid[\s-]*array\b", re.IGNORECASE
)

# Module indicators that are only trusted in the title / first-page region,
# where they describe the part itself rather than appearing in body prose.
# NB: deliberately excludes "reference design" — vendors (e.g. TI) print it as
# a boilerplate header/navigation link on ordinary chip datasheets, so it is a
# false-positive magnet. Non-datasheet reference-design docs are intake's job.
_TITLE_SIGNALS = re.compile(
    r"\bmodule\b|\bsystem[\s-]*in[\s-]*package\b|\bSiP\b|\bIPM\b|"
    r"\bintelligent\s+power\s+module\b",
    re.IGNORECASE,
)

# How much of the document counts as "title / first-page region".
_TITLE_WINDOW = 800


def module_footprint_reason(
    doc_text: Optional[str],
    component_name: Optional[str] = None,
    package_family: Optional[str] = None,
) -> Optional[str]:
    """Return a reason string when the part is a module/grid-array whose
    footprint we won't build, else None.

    Args:
        doc_text: Full datasheet text (title first).
        component_name: Resolved component/part name, if known.
        package_family: Normalized package family (e.g. from PackageDetector),
            if known.
    """
    if package_family and package_family.strip().upper() in _GRID_ARRAY_FAMILIES:
        return (
            f"Package family {package_family.upper()} is a grid-array part with "
            "no perimeter land pattern; emitting schematic only."
        )

    text = doc_text or ""
    strong = _STRONG_ANYWHERE.search(text)
    if strong:
        return (
            f"Datasheet describes a {strong.group(0).lower()} part (module/SiP); "
            "its land pattern is not a chip footprint — emitting schematic only."
        )

    # Title-region module wording, or a module signal in the component name.
    head = text[:_TITLE_WINDOW]
    title_hit = _TITLE_SIGNALS.search(head) or (
        component_name and _TITLE_SIGNALS.search(component_name)
    )
    if title_hit:
        return (
            f"Datasheet titled/identified as a module ('{title_hit.group(0)}'); "
            "its land pattern is not a chip footprint — emitting schematic only."
        )

    return None
