# 3D Package Model Generation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a third pipeline output — a simplified 3D model of the physical component (body + leads) — so one run can produce schematic → footprint → 3D (`*_schematic.glb`, `*_footprint.glb`, `*_3d.glb`).

**Architecture:** A new `Package3DBuilder` (mirroring `PcbFootprintBuilder`) reuses the existing pin-layout and dims pipeline: planar dims (D/E/E1/b/L/e) already flow into the footprint; the height dims `A` (package height) and `A1` (standoff) are already *extracted* by `DimensionExtractor` but currently discarded — this plan threads them through, adds per-family JEDEC height defaults as fallback, and extrudes an IPC-style simplified body with family-specific leads (gull-wing / through-hole / leadless terminals). The 3D model shares the footprint's coordinate system (XY = board plane, Z up, same origin, same pin-1 corner) so `*_footprint.glb` and `*_3d.glb` overlay exactly.

**Tech Stack:** Python 3, cadquery 2.5.2 (solid modeling → GLB), pygltflib (extras injection + hierarchy validation), trimesh (geometry verification in tools/tests), pytest.

---

## Context for an engineer with zero repo knowledge

### The existing pipeline (do not rebuild this)

`python -m src.main <input.pdf> <output.glb> [--both|--pcb-2d] [--part-number X]`

1. **Page detection** → `src/pdf_extractor/page_detector.py`
2. **Content extraction** → `src/pdf_extractor/content_extractor.py`
3. **Pin extraction** → deterministic table parser, LLM fallback (`src/llm/client.py`), validated
4. **Package gate** → `enforce_known_package_type` (`src/main.py:611`) fails closed on unknown families
5. **Dimension extraction** → `DimensionExtractor().extract(...)` (`src/pdf_extractor/dimension_extractor.py:66`) returns a flat dict like `{"e": 1.27, "E": 10.3, "D": 9.9, "b": 0.41, "L": 0.84, "A": 1.75, "dims_source": "text", ...}`
6. **Builders:**
   - `build_schematic_from_pin_data` (`src/schematic_generator/adapter.py:89`) → `*_schematic.glb` (a pinout *diagram*, confusingly called "3D schematic" in old comments — it is NOT the 3D model this plan adds)
   - `build_pcb_footprint` (`src/schematic_generator/pcb_footprint_builder.py:861`) → `*_footprint.glb`

`--both` mode (`src/main.py:1098-1175`) runs extraction once, then both builders via `process_datasheet_both` (`src/main.py:874`).

### Key facts this plan relies on (verified 2026-07-19)

- `A` is extracted from drawing text (`src/pdf_extractor/text_dimensions.py:135`, plausibility 0.3–6.0 mm at `:217`) and requested from vision (`dimension_extractor.py:625,650-651` also requests `A1`). **Neither reaches any builder**: `PcbFootprintBuilder._apply_extracted_dims` (`pcb_footprint_builder.py:216`) only consumes `e, E, D, b, L, E1, D1`.
- Lead thickness `c` is not extracted anywhere; the footprint hardcodes `LEAD_THICKNESS = 0.25`.
- JEDEC planar defaults live in `get_footprint_defaults` (`src/package_types/footprint_defaults.py:67`), keyed by family string; extracted dims override defaults via dict-merge semantics. **No A/A1/c there yet.**
- Pin XY positions come from `layout_pins` (`src/schematic_generator/pin_layout.py`) + per-side recentering (`PcbFootprintBuilder._recenter_pins`, `pcb_footprint_builder.py:192`). The footprint then applies an IPC-7351 half-lead inset to pad centers (`:170-184`) — the 3D lead must NOT apply that inset (lead tip sits at the lead span E/2, the pad center does not).
- Fail-closed precedent: BGA/LCCC raise `SchematicGenerationError` with `ErrorCodes.PACKAGE_UNKNOWN` in the footprint builder constructor (`pcb_footprint_builder.py:115-123`). The 3D builder refuses the same families.
- GLB toolchain: `cq.Assembly(...).save(path)` → `optimize_glb_hierarchy` → extras injection with pygltflib → hierarchy validation. See `PcbFootprintBuilder.save_glb` (`pcb_footprint_builder.py:755`) for the full pattern.
- Watermarking: `mark_glb_unvalidated` (`src/core/validation_marker.py:16`) writes `validated=false` into scene extras when `--force-best-effort` pushed bad data through.
- All tests live in **one file**: `tests/test_suite.py` (pytest). Follow that convention — append a new section, don't create new test files.
- Project principles (from memory / ARCH docs): **general parser, never corpus-tuned** — fixes must be family-level principles with fail-closed behavior; the eval corpus validates, it never drives special cases. **Never add `Co-Authored-By` trailers to commits in this repo.**

### Design decisions (settled with the user, 2026-07-19)

1. **What the 3D output is:** a simplified IPC-style model of the component itself — extruded body at height `A`, standoff `A1`, family-specific leads. Standalone `*_3d.glb` aligned to the footprint origin. (Not a combined board scene, not a photorealistic model.)
2. **Missing height dims:** JEDEC per-family defaults (same override-with-provenance pattern as the footprint; `dims_source` recorded in GLB extras). Fail closed only when the family has no defaults AND nothing was extracted.

### Geometry model (simplified IPC level)

All Z coordinates in mm, Z=0 is the board surface.

- **Body:** box `E1 × D1` (fallbacks: extracted → JEDEC → lead-span-derived outline, exactly like the footprint's `fab_outline_*` properties) spanning Z from `A1` to `A`. Plus a small pin-1 indicator disc on the top face near pin 1.
- **Gull-wing leads** (SOIC/SOP/TSSOP/SSOP/MSOP/SOT-23/QFP/LQFP/TQFP): an orthogonal S-profile drawn in a vertical plane and extruded to lead width `b` — foot on the board (Z 0→c), vertical riser at the heel, shoulder entering the body at mid-height. Simple, robust, no lofts/sweeps.
- **Through-hole pins** (DIP/PDIP/CDIP): rectangular pins `b × c` cross-section from body mid-height down to Z = −1.5 (protruding through the board), at each pad position; body floats at `A1` (seating plane standoff).
- **Leadless terminals** (QFN/DFN/WSON/SON): body sits nearly flush (`A1` ≈ 0.02); terminals rendered as thin `b × L` plates (0.05 thick) at each pad position on the bottom perimeter.
- **Refused:** BGA, LCCC (same fail-closed rationale as the footprint: we'd be inventing geometry).

GLB hierarchy (validated, like the footprint's):

```
Package3D
├── Body
│   ├── BodyBlock
│   └── Pin1Marker
└── Leads
    ├── 1
    ├── 2
    └── ... (one child per pin, named by pin number)
```

Colors: body dark epoxy gray `(0.15, 0.15, 0.15)`, leads tin silver `(0.75, 0.77, 0.8)`, pin-1 marker light gray `(0.55, 0.55, 0.55)`.

### How to run things

```bash
# Tests (from repo root; use the interpreter the project uses — cadquery must import)
python3 -m pytest tests/test_suite.py -v            # full suite
python3 -m pytest tests/test_suite.py -k package_3d -v   # just the new section

# End-to-end smoke (needs a datasheet PDF; corpus lives in pdfs/ and datasheets/)
python3 -m src.main pdfs/<some>.pdf output/dev/NE555.glb --all --verbose
```

If `import cadquery` fails, you're in the wrong interpreter/venv — check how the existing footprint tests pass in CI/locally before "fixing" anything (`pip install -r requirements.txt` into a venv if truly missing).

---

## Task 1: Share the pin-recentering helper (small refactor, no behavior change)

The 3D builder needs the same recentered pin positions the footprint uses. `_recenter_pins` is currently a private method mutating `self.pin_positions`. Extract it to `pin_layout.py` so both builders call one implementation.

**Files:**
- Modify: `src/schematic_generator/pin_layout.py` (add free function at module end)
- Modify: `src/schematic_generator/pcb_footprint_builder.py:163,192-214` (delegate)
- Test: `tests/test_suite.py`

**Step 1: Write the failing test**

Append to `tests/test_suite.py`:

```python
# ============================================================
# Package 3D model generation
# ============================================================

def test_recenter_pins_centers_each_side_independently():
    from src.schematic_generator.pin_layout import PinPosition, recenter_pins

    def pp(num, x, y, side):
        return PinPosition(pin_index=0, pin_number=num, x=x, y=y, side=side,
                           rotation=0.0, text_x=x, text_y=y, text_halign="left",
                           num_x=x, num_y=y, num_halign="left")

    pins = [pp("1", -3.0, 1.0, "left"), pp("2", -3.0, 3.0, "left"),
            pp("3", 3.0, 1.0, "right"), pp("4", 3.0, 3.0, "right")]
    recenter_pins(pins)
    assert [p.y for p in pins] == [-1.0, 1.0, -1.0, 1.0]
    assert [p.x for p in pins] == [-3.0, -3.0, 3.0, 3.0]
```

**Step 2: Run it — expect FAIL** (`ImportError: cannot import name 'recenter_pins'`)

```bash
python3 -m pytest tests/test_suite.py::test_recenter_pins_centers_each_side_independently -v
```

**Step 3: Implement**

Add to the end of `src/schematic_generator/pin_layout.py` (move the body of `PcbFootprintBuilder._recenter_pins` verbatim, generalized to a parameter):

```python
def recenter_pins(pin_positions: List[PinPosition]) -> None:
    """Center each side's column (Y) or row (X) on the origin, in place.

    Per side, not jointly: on quad packages the top and bottom rows are
    offset in opposite directions, so their union looks symmetric and a
    joint shift would leave both rows off-center.
    """
    for side in ("left", "right"):
        column = [p for p in pin_positions if p.side == side]
        if column:
            dy = (max(p.y for p in column) + min(p.y for p in column)) / 2.0
            for p in column:
                p.y -= dy
                p.text_y -= dy
                p.num_y -= dy
    for side in ("top", "bottom"):
        row = [p for p in pin_positions if p.side == side]
        if row:
            dx = (max(p.x for p in row) + min(p.x for p in row)) / 2.0
            for p in row:
                p.x -= dx
                p.text_x -= dx
                p.num_x -= dx
```

In `pcb_footprint_builder.py`, replace the body of `_recenter_pins` with a delegation (keep the method so nothing else breaks):

```python
    def _recenter_pins(self) -> None:
        recenter_pins(self.pin_positions)
```

and extend the import at `pcb_footprint_builder.py:37`:

```python
from .pin_layout import PinPosition, layout_pins, recenter_pins
```

Delete the now-duplicated loop bodies and keep the original docstring on the free function only.

**Step 4: Run the new test AND the footprint regression tests — expect PASS**

```bash
python3 -m pytest tests/test_suite.py -k "recenter or footprint or reference_glb" -v
```

**Step 5: Commit**

```bash
git add src/schematic_generator/pin_layout.py src/schematic_generator/pcb_footprint_builder.py tests/test_suite.py
git commit -m "refactor: extract recenter_pins into pin_layout for reuse"
```

---

## Task 2: Add JEDEC height defaults (A, A1, c) to the package defaults table

**Files:**
- Modify: `src/package_types/footprint_defaults.py` (each family dict + docstring)
- Test: `tests/test_suite.py`

**Step 1: Write the failing test**

```python
def test_footprint_defaults_include_height_keys():
    from src.package_types.footprint_defaults import get_footprint_defaults

    for pkg, pins in [("SOIC-8", 8), ("TSSOP-16", 16), ("QFN-24", 24),
                      ("DIP-8", 8), ("SOT-23-5", 5), ("LQFP-48", 48),
                      ("SSOP-20", 20), ("MSOP-8", 8), ("DFN-8", 8)]:
        d = get_footprint_defaults(pkg, pins)
        assert d is not None, pkg
        for key in ("A", "A1", "c"):
            assert key in d, f"{pkg} missing {key}"
        assert 0.0 <= d["A1"] < d["A"] <= 6.0, pkg


def test_footprint_defaults_heights_are_plausible_per_family():
    from src.package_types.footprint_defaults import get_footprint_defaults

    assert get_footprint_defaults("TSSOP-16", 16)["A"] <= 1.2   # MO-153 "thin"
    assert get_footprint_defaults("QFN-24", 24)["A"] <= 1.0     # MO-220
    assert get_footprint_defaults("DIP-8", 8)["A"] >= 3.0       # MS-001 molded body
```

**Step 2: Run — expect FAIL** (`KeyError`/assert on missing `A`)

```bash
python3 -m pytest tests/test_suite.py -k footprint_defaults_include -v
```

**Step 3: Implement**

Extend each family dict in `get_footprint_defaults`. Values are JEDEC nominal/max package heights (`A` = max overall height, `A1` = typical standoff, `c` = lead/terminal thickness). Update the module docstring key list (`A — overall height`, `A1 — standoff`, `c — lead thickness`) and the sources line.

```python
    # DIP family entry gains:
    "b": 0.46, "A": 3.81, "A1": 0.51, "c": 0.25,
    # (MS-001: body ~3.3 molded + seating standoff; b was previously absent
    #  for DIP — 0.46mm is the MS-001 nominal lead width and is needed for
    #  3D pin cross-sections; _compute_pad_spec already tolerates it.)

    # SOT23:    "A": 1.30, "A1": 0.10, "c": 0.15,   (MO-178)
    # SOIC/SOP: "A": 2.65 if wide else 1.75, "A1": 0.15, "c": 0.23,  (MS-012/013)
    # TSSOP:    "A": 1.20, "A1": 0.10, "c": 0.15,   (MO-153)
    # SSOP:     "A": 2.00, "A1": 0.10, "c": 0.20,   (MO-150)
    # MSOP:     "A": 1.10, "A1": 0.10, "c": 0.15,   (MO-187)
    # QFN:      "A": 0.90, "A1": 0.02, "c": 0.20,   (MO-220)
    # DFN/WSON: "A": 0.80, "A1": 0.02, "c": 0.20,
    # QFP/LQFP/TQFP: "A": 1.60, "A1": 0.10, "c": 0.15,  (MS-026)
```

Write them as literal keys inside each existing `return {...}` dict — do NOT post-process the dict (keep the function a flat table an engineer can diff against JEDEC sheets).

**Step 4: Run — expect PASS; also re-run the whole suite** (footprint `_apply_extracted_dims` ignores unknown keys and `_compute_pad_spec` merges dicts, so the extra keys must not break anything — verify, don't assume):

```bash
python3 -m pytest tests/test_suite.py -v
```

**Step 5: Commit**

```bash
git add src/package_types/footprint_defaults.py tests/test_suite.py
git commit -m "feat: JEDEC height defaults (A, A1, c) per package family"
```

---

## Task 3: Height-dims plausibility in extraction validation

`text_dimensions.py` already bounds `A` (0.3–6.0). Add `A1` bounds and the `A1 < A` cross-check so a garbage vision read can't produce a floating or inverted body.

**Files:**
- Modify: `src/pdf_extractor/text_dimensions.py` (the validation function containing line ~217)
- Test: `tests/test_suite.py`

**Step 1: Write the failing test**

Find the existing plausibility/validation function name first (it's the one with `a = dims.get("A")` at `text_dimensions.py:217`; import it the same way existing dim tests do — check `tests/test_suite.py` for prior usage, e.g. via `grep -n text_dimensions tests/test_suite.py`).

```python
def test_dims_plausibility_rejects_bad_standoff():
    from src.pdf_extractor.text_dimensions import _plausible  # adjust to actual name

    good = {"e": 1.27, "E": 6.0, "D": 4.9, "b": 0.41, "A": 1.75, "A1": 0.15}
    assert _plausible(good, pin_count=8)  # match the real signature

    bad_inverted = dict(good, A1=2.0)     # standoff above total height
    assert not _plausible(bad_inverted, pin_count=8)

    bad_range = dict(good, A1=1.2)        # > 1.0mm standoff is not a real IC
    assert not _plausible(bad_range, pin_count=8)
```

**Step 2: Run — expect FAIL** (A1 currently unchecked → both "bad" dicts pass)

**Step 3: Implement** — next to the existing `A` check in `text_dimensions.py`:

```python
    a1 = dims.get("A1")
    if a1 is not None:
        if not 0.0 <= a1 <= 1.0:
            return False
        if a is not None and a1 >= a:
            return False
```

**Step 4: Run — expect PASS**

**Step 5: Commit**

```bash
git add src/pdf_extractor/text_dimensions.py tests/test_suite.py
git commit -m "feat: plausibility bounds for extracted standoff (A1)"
```

---

## Task 4: `Package3DBuilder` skeleton — dims resolution + fail-closed gates

**Files:**
- Create: `src/schematic_generator/package_3d_builder.py`
- Test: `tests/test_suite.py`

**Step 1: Write the failing tests**

```python
def test_package_3d_fails_closed_on_grid_array():
    import pytest
    from src.exceptions import SchematicGenerationError
    from src.schematic_generator.package_3d_builder import Package3DBuilder

    with pytest.raises(SchematicGenerationError):
        Package3DBuilder("BGA-64", 64, "TEST")


def test_package_3d_fails_closed_without_any_height_source():
    import pytest
    from src.exceptions import SchematicGenerationError
    from src.schematic_generator.package_3d_builder import Package3DBuilder

    # TSOP has no JEDEC defaults table entry and we pass no extracted dims:
    # the builder must refuse rather than invent a height.
    with pytest.raises(SchematicGenerationError):
        Package3DBuilder("TSOP-32", 32, "TEST")


def test_package_3d_dims_resolution_prefers_extracted():
    from src.schematic_generator.package_3d_builder import Package3DBuilder

    b = Package3DBuilder("SOIC-8", 8, "TEST",
                         extracted_dims={"A": 1.6, "dims_source": "text"})
    assert b.dims["A"] == 1.6                 # extracted wins
    assert b.dims["A1"] == 0.15               # JEDEC fallback fills the rest
    assert b.dims_source == "text"

    b2 = Package3DBuilder("SOIC-8", 8, "TEST")
    assert b2.dims["A"] == 1.75               # pure JEDEC
    assert b2.dims_source == "jedec_default"


def test_package_3d_rejects_implausible_extracted_height():
    from src.schematic_generator.package_3d_builder import Package3DBuilder

    # A=87.5 (the SN6501 vision-glitch class) must not survive into geometry:
    # implausible extracted heights fall back to JEDEC, provenance says so.
    b = Package3DBuilder("SOIC-8", 8, "TEST", extracted_dims={"A": 87.5})
    assert b.dims["A"] == 1.75
    assert b.dims_source == "jedec_default"
```

**Step 2: Run — expect FAIL** (`ModuleNotFoundError`)

```bash
python3 -m pytest tests/test_suite.py -k package_3d -v
```

**Step 3: Implement** — create `src/schematic_generator/package_3d_builder.py`:

```python
"""
Package 3D Model Builder - simplified IPC-style component bodies.

Third pipeline output alongside the pinout diagram (schematic) and the PCB
footprint. Produces a *_3d.glb containing the physical package: extruded
body at overall height A, standoff A1, and family-specific leads
(gull-wing, through-hole pins, or leadless terminals).

Shares the footprint's coordinate system: XY is the board plane, Z is up,
origin at package center, pin 1 in the same corner — so *_footprint.glb
and *_3d.glb overlay exactly.

Hierarchy documented in docs/PACKAGE_3D_HIERARCHY.md.
"""

import logging
import os
from typing import Any, Dict, List, Optional

import cadquery as cq

from ..core import inject_package_3d_extras, optimize_glb_hierarchy, validate_package_3d_glb
from ..exceptions import ErrorCodes, SchematicGenerationError
from ..package_types import PackageType, get_footprint_defaults, get_schematic_parameters
from .pin_layout import PinPosition, layout_pins, recenter_pins

logger = logging.getLogger(__name__)

# Families rendered with leadless bottom terminals instead of protruding leads
_LEADLESS = (PackageType.QFN, PackageType.DFN, PackageType.WSON, PackageType.SON)

# Sanity bounds for the resolved heights (fail toward JEDEC, never invent)
_A_BOUNDS = (0.3, 6.0)
_A1_BOUNDS = (0.0, 1.0)


class Package3DBuilder:
    """Build simplified 3D package models using cadquery."""

    BODY_COLOR = cq.Color(0.15, 0.15, 0.15, 1.0)
    LEAD_COLOR = cq.Color(0.75, 0.77, 0.80, 1.0)
    MARKER_COLOR = cq.Color(0.55, 0.55, 0.55, 1.0)

    PIN1_MARKER_RADIUS = 0.15   # mm
    PIN1_MARKER_HEIGHT = 0.02   # mm, sits proud of the body top
    THROUGH_HOLE_DEPTH = 1.5    # mm pin protrusion below the board
    LEADLESS_TERMINAL_T = 0.05  # mm terminal plate thickness
    SHOULDER_INSET = 0.10       # mm gull-wing shoulder tuck into the body

    def __init__(self, package_type: str, pin_count: int, component_name: str = "IC",
                 custom_layout: Optional[Dict[str, List[int]]] = None,
                 extracted_dims: Optional[Dict[str, Any]] = None):
        self.package_type = package_type
        self.pin_count = pin_count
        self.component_name = component_name

        self.params = get_schematic_parameters(package_type, pin_count)

        if self.params.package_type in (PackageType.BGA, PackageType.LCCC):
            raise SchematicGenerationError(
                f"Package '{package_type}' is a grid-array/leadless-ceramic "
                "type with no modeled 3D geometry; refusing to invent a body.",
                error_code=ErrorCodes.PACKAGE_UNKNOWN,
                details={"package_type": package_type, "pin_count": pin_count},
            )

        # Resolve dims: JEDEC family defaults, overridden by plausible
        # extracted values. Same pattern as the footprint builder, plus the
        # height keys (A, A1, c) the footprint ignores.
        jedec = get_footprint_defaults(package_type, pin_count) or {}
        self.dims: Dict[str, float] = dict(jedec)
        used_extracted = False
        for key in ("e", "E", "E1", "D", "D1", "b", "L", "A", "A1", "c"):
            value = (extracted_dims or {}).get(key)
            if value is None:
                continue
            if key == "A" and not _A_BOUNDS[0] <= float(value) <= _A_BOUNDS[1]:
                logger.warning("Rejecting implausible extracted A=%s", value)
                continue
            if key == "A1" and not _A1_BOUNDS[0] <= float(value) <= _A1_BOUNDS[1]:
                logger.warning("Rejecting implausible extracted A1=%s", value)
                continue
            self.dims[key] = float(value)
            used_extracted = True

        # A 3D body without a real height is an invention; refuse (ARCH-006).
        if not self.dims.get("A"):
            raise SchematicGenerationError(
                f"No package height (A) available for '{package_type}': not in "
                "JEDEC defaults and not extracted from the datasheet.",
                error_code=ErrorCodes.PACKAGE_UNKNOWN,
                details={"package_type": package_type, "pin_count": pin_count},
            )
        self.dims.setdefault("A1", 0.1)
        self.dims.setdefault("c", 0.2)
        if self.dims["A1"] >= self.dims["A"]:
            self.dims["A1"] = 0.1

        if used_extracted:
            self.dims_source = (extracted_dims or {}).get("dims_source") or "extracted"
        elif jedec:
            self.dims_source = "jedec_default"
        else:
            self.dims_source = "extracted"  # only possible via extracted A

        # Planar layout: identical to the footprint (layout + recenter),
        # WITHOUT the IPC pad inset — leads tip at the lead span, pads don't.
        self._apply_planar_dims()
        self.pin_positions = layout_pins(self.params, custom_layout)
        recenter_pins(self.pin_positions)

        logger.info("Initialized 3D package builder for %s (%d pins)",
                    package_type, pin_count)

    # ---- dims helpers -----------------------------------------------------

    def _apply_planar_dims(self) -> None:
        """Feed resolved planar dims into SchematicParameters (as the
        footprint builder does) so layout_pins spaces rows/pitch correctly."""
        if self.dims.get("e"):
            self.params.pin_pitch = self.dims["e"]
        if self.dims.get("E"):
            self.params.body_width = self.dims["E"]
        if self.dims.get("D"):
            self.params.body_height = self.dims["D"]
        if self.dims.get("b"):
            self.params.pin_geometry.leg_width = self.dims["b"]
        if self.dims.get("L"):
            self.params.pin_geometry.leg_length = self.dims["L"]

    @property
    def body_w(self) -> float:
        """Plastic body width (X): E1 when known, else derived from span."""
        if self.dims.get("E1"):
            return self.dims["E1"]
        span = self.dims.get("E") or self.params.body_width
        lead = self.dims.get("L") or 0.6
        return max(span - 2 * (lead + 0.4), 1.0)

    @property
    def body_l(self) -> float:
        """Plastic body length (Y): D1 (quad) or D (dual-row)."""
        return self.dims.get("D1") or self.dims.get("D") or self.params.body_height

    def is_through_hole(self) -> bool:
        return self.package_type.upper().startswith(("DIP", "PDIP", "CDIP"))

    def is_leadless(self) -> bool:
        return self.params.package_type in _LEADLESS
```

(Geometry and `save_glb` come in Tasks 5–9; for this task the file ends here. The `from ..core import ...` line will fail until Task 8 — for now import only what exists: start with `from ..exceptions import ...` etc. and add the core imports in Task 8. Keep the module importable at every commit.)

**Step 4: Run — expect the 4 new tests PASS**

```bash
python3 -m pytest tests/test_suite.py -k package_3d -v
```

**Step 5: Commit**

```bash
git add src/schematic_generator/package_3d_builder.py tests/test_suite.py
git commit -m "feat: Package3DBuilder skeleton with height resolution and fail-closed gates"
```

---

## Task 5: Body + pin-1 marker geometry

**Files:**
- Modify: `src/schematic_generator/package_3d_builder.py`
- Test: `tests/test_suite.py`

**Step 1: Write the failing test**

```python
def test_package_3d_body_spans_a1_to_a():
    from src.schematic_generator.package_3d_builder import Package3DBuilder

    b = Package3DBuilder("SOIC-8", 8, "TEST")
    body = b.build_body()
    solid = body.children[0].obj  # BodyBlock workplane
    bb = solid.val().BoundingBox()
    assert abs(bb.zmin - b.dims["A1"]) < 1e-6
    assert abs(bb.zmax - b.dims["A"]) < 1e-6
    assert abs(bb.xlen - b.body_w) < 1e-6
    assert abs(bb.ylen - b.body_l) < 1e-6
```

**Step 2: Run — expect FAIL** (`AttributeError: build_body`)

**Step 3: Implement** — add to `Package3DBuilder`:

```python
    # ---- geometry ---------------------------------------------------------

    def build_body(self) -> cq.Assembly:
        """Body assembly: epoxy block from A1 to A, plus pin-1 marker disc."""
        a, a1 = self.dims["A"], self.dims["A1"]
        body_assy = cq.Assembly(name="Body")

        block = (
            cq.Workplane("XY").workplane(offset=a1)
            .rect(self.body_w, self.body_l).extrude(a - a1)
        )
        body_assy.add(block, name="BodyBlock", color=self.BODY_COLOR)

        marker = self._build_pin1_marker(a)
        if marker is not None:
            body_assy.add(marker, name="Pin1Marker", color=self.MARKER_COLOR)
        return body_assy

    def _build_pin1_marker(self, top_z: float) -> Optional[cq.Workplane]:
        """Small disc on the body top, pulled toward pin 1's corner."""
        pin1 = next((p for p in self.pin_positions if p.pin_number == "1"), None)
        if pin1 is None:
            return None
        margin = self.PIN1_MARKER_RADIUS + 0.25
        mx = max(-(self.body_w / 2 - margin), min(self.body_w / 2 - margin, pin1.x))
        my = max(-(self.body_l / 2 - margin), min(self.body_l / 2 - margin, pin1.y))
        return (
            cq.Workplane("XY").workplane(offset=top_z)
            .center(mx, my).circle(self.PIN1_MARKER_RADIUS)
            .extrude(self.PIN1_MARKER_HEIGHT)
        )
```

**Step 4: Run — expect PASS.** If the `children[0].obj` access pattern fails, inspect how the existing footprint tests read assemblies and adapt the *test* (not the builder).

**Step 5: Commit**

```bash
git add src/schematic_generator/package_3d_builder.py tests/test_suite.py
git commit -m "feat: 3D body block and pin-1 marker"
```

---

## Task 6: Gull-wing leads (SMD dual-row and quad families)

**Files:**
- Modify: `src/schematic_generator/package_3d_builder.py`
- Test: `tests/test_suite.py`

**Step 1: Write the failing test**

```python
def test_package_3d_gull_wing_lead_reaches_span_and_board():
    from src.schematic_generator.package_3d_builder import Package3DBuilder

    b = Package3DBuilder("SOIC-8", 8, "TEST")
    leads = b.build_leads()
    assert len(leads.children) == 8
    # Every lead touches the board (z=0) and the outermost tip sits at E/2
    span = b.dims["E"] / 2
    for child in leads.children:
        bb = child.obj.val().BoundingBox()
        assert abs(bb.zmin) < 1e-6
        assert max(abs(bb.xmin), abs(bb.xmax)) <= span + 1e-6
    tips = [max(abs(c.obj.val().BoundingBox().xmin),
                abs(c.obj.val().BoundingBox().xmax)) for c in leads.children]
    assert abs(max(tips) - span) < 1e-6


def test_package_3d_quad_leads_on_all_four_sides():
    from src.schematic_generator.package_3d_builder import Package3DBuilder

    b = Package3DBuilder("LQFP-48", 48, "TEST")
    leads = b.build_leads()
    assert len(leads.children) == 48
```

**Step 2: Run — expect FAIL** (`AttributeError: build_leads`)

**Step 3: Implement** — add to `Package3DBuilder`:

```python
    def _gull_wing_profile(self) -> cq.Workplane:
        """Orthogonal S-profile in the XZ plane for a +X-pointing lead,
        extruded to lead width; local origin = package center."""
        a, a1, c = self.dims["A"], self.dims["A1"], self.dims["c"]
        b_w = self.dims.get("b") or self.params.pin_geometry.leg_width
        lead_l = self.dims.get("L") or 0.6
        x_tip = (self.dims.get("E") or self.params.body_width) / 2
        x_heel = x_tip - lead_l
        x_in = self.body_w / 2 - self.SHOULDER_INSET
        # Shoulder enters the body at mid-height of the epoxy block
        h = a1 + (a - a1) / 2 - c / 2
        pts = [
            (x_in, h + c), (x_heel + c, h + c), (x_heel + c, c), (x_tip, c),
            (x_tip, 0.0), (x_heel, 0.0), (x_heel, h), (x_in, h),
        ]
        return (
            cq.Workplane("XZ").polyline(pts).close()
            .extrude(b_w / 2, both=True)
        )

    def _lead_location(self, pos: PinPosition) -> cq.Location:
        """Rotate the canonical +X lead to the pin's side, shift along the row."""
        z = cq.Vector(0, 0, 1)
        if pos.side == "right":
            return cq.Location(cq.Vector(0, pos.y, 0), z, 0)
        if pos.side == "left":
            return cq.Location(cq.Vector(0, pos.y, 0), z, 180)
        if pos.side == "top":
            return cq.Location(cq.Vector(pos.x, 0, 0), z, 90)
        return cq.Location(cq.Vector(pos.x, 0, 0), z, -90)  # bottom

    def build_leads(self) -> cq.Assembly:
        leads_assy = cq.Assembly(name="Leads")
        for pos in self.pin_positions:
            leads_assy.add(self._build_one_lead(pos),
                           name=pos.pin_number, color=self.LEAD_COLOR,
                           loc=self._lead_location(pos))
        return leads_assy

    def _build_one_lead(self, pos: PinPosition) -> cq.Workplane:
        # Gull-wing for all leaded SMD families (through-hole and leadless
        # variants override in Tasks 7-8).
        return self._gull_wing_profile()
```

Watch out: quad packages have different spans per axis (`E` for left/right, `D` for top/bottom). Extend `_gull_wing_profile` to take the span/body half-extent as parameters and pass per-side values from `_build_one_lead`:

```python
    def _build_one_lead(self, pos: PinPosition) -> cq.Workplane:
        if pos.side in ("top", "bottom"):
            span = (self.dims.get("D") or self.params.body_height) / 2
            body_half = self.body_l / 2
        else:
            span = (self.dims.get("E") or self.params.body_width) / 2
            body_half = self.body_w / 2
        return self._gull_wing_profile(span, body_half)
```

(and change `_gull_wing_profile(self, x_tip, body_half)` accordingly — `x_in = body_half - self.SHOULDER_INSET`).

**Step 4: Run — expect PASS**

```bash
python3 -m pytest tests/test_suite.py -k "gull_wing or quad_leads" -v
```

**Step 5: Commit**

```bash
git add src/schematic_generator/package_3d_builder.py tests/test_suite.py
git commit -m "feat: gull-wing 3D leads for dual-row and quad SMD families"
```

---

## Task 7: Through-hole pins (DIP)

**Files:**
- Modify: `src/schematic_generator/package_3d_builder.py`
- Test: `tests/test_suite.py`

**Step 1: Write the failing test**

```python
def test_package_3d_dip_pins_protrude_below_board():
    from src.schematic_generator.package_3d_builder import Package3DBuilder

    b = Package3DBuilder("DIP-8", 8, "TEST")
    leads = b.build_leads()
    assert len(leads.children) == 8
    for child in leads.children:
        bb = child.obj.val().BoundingBox()
        assert bb.zmin < -1.0          # goes through the board
        assert bb.zmax > b.dims["A1"]  # reaches into the body
```

**Step 2: Run — expect FAIL** (DIP currently gets a gull-wing whose zmin is 0)

**Step 3: Implement** — in `_build_one_lead`, branch first:

```python
    def _build_one_lead(self, pos: PinPosition) -> cq.Workplane:
        if self.is_through_hole():
            return self._through_hole_pin()
        ...

    def _through_hole_pin(self) -> cq.Workplane:
        """Rectangular pin at the row position, from body mid-height down
        through the board. Canonical +X frame: pin centered at x = E/2."""
        a, a1, c = self.dims["A"], self.dims["A1"], self.dims["c"]
        b_w = self.dims.get("b") or 0.46
        x_row = (self.dims.get("E") or self.params.body_width) / 2
        top = a1 + (a - a1) / 2
        return (
            cq.Workplane("XY").workplane(offset=-self.THROUGH_HOLE_DEPTH)
            .center(x_row, 0).rect(c, b_w)
            .extrude(top + self.THROUGH_HOLE_DEPTH)
        )
```

Note the pin is built in the canonical +X frame (centered at `x_row`, y=0) so the same `_lead_location` placement used for gull-wings positions it — do not double-apply `pos.x/pos.y`.

**Step 4: Run — expect PASS; re-run the SOIC/LQFP lead tests too** (regression on the branch refactor)

**Step 5: Commit**

```bash
git add src/schematic_generator/package_3d_builder.py tests/test_suite.py
git commit -m "feat: through-hole 3D pins for DIP families"
```

---

## Task 8: Leadless terminals (QFN/DFN/WSON/SON)

**Files:**
- Modify: `src/schematic_generator/package_3d_builder.py`
- Test: `tests/test_suite.py`

**Step 1: Write the failing test**

```python
def test_package_3d_qfn_terminals_are_flush_plates():
    from src.schematic_generator.package_3d_builder import Package3DBuilder

    b = Package3DBuilder("QFN-24", 24, "TEST")
    assert b.is_leadless()
    leads = b.build_leads()
    assert len(leads.children) == 24
    for child in leads.children:
        bb = child.obj.val().BoundingBox()
        assert abs(bb.zmin) < 1e-6
        assert bb.zmax <= 0.06 + 1e-6   # thin plate, no protruding lead
```

**Step 2: Run — expect FAIL**

**Step 3: Implement** — add the second branch in `_build_one_lead` and:

```python
    def _leadless_terminal(self, span_half: float) -> cq.Workplane:
        """Thin terminal plate on the bottom edge, tip at the body edge."""
        b_w = self.dims.get("b") or 0.25
        lead_l = self.dims.get("L") or 0.4
        return (
            cq.Workplane("XY")
            .center(span_half - lead_l / 2, 0).rect(lead_l, b_w)
            .extrude(self.LEADLESS_TERMINAL_T)
        )
```

with `_build_one_lead` selecting `self._leadless_terminal(span)` when `self.is_leadless()` (per-side span exactly as in Task 6). For leadless bodies the standoff must not leave a visible air gap: in `__init__`, after resolving dims, clamp `A1` to ≤ `LEADLESS_TERMINAL_T` for leadless families.

**Step 4: Run — expect PASS** (`python3 -m pytest tests/test_suite.py -k package_3d -v`)

**Step 5: Commit**

```bash
git add src/schematic_generator/package_3d_builder.py tests/test_suite.py
git commit -m "feat: leadless terminal geometry for QFN/DFN families"
```

---

## Task 9: GLB export — extras injection, hierarchy validation, `save_glb`, public wrapper

**Files:**
- Create: `src/core/package_3d_extras.py`
- Create: `src/core/package_3d_hierarchy.py`
- Modify: `src/core/__init__.py` (export the two new functions)
- Modify: `src/schematic_generator/package_3d_builder.py` (`build_model`, `save_glb`, `build_package_3d`)
- Modify: `src/schematic_generator/__init__.py` (export `build_package_3d` — mirror how `build_pcb_footprint` is exported; check that file first)
- Test: `tests/test_suite.py`

**Step 1: Write the failing tests**

```python
def test_package_3d_glb_roundtrip_and_extras(tmp_path):
    from pygltflib import GLTF2
    from src.schematic_generator.package_3d_builder import build_package_3d

    out = str(tmp_path / "soic8_3d.glb")
    pins = [{"number": str(i), "name": f"P{i}"} for i in range(1, 9)]
    assert build_package_3d("SOIC-8", 8, "TEST", pins, out)
    gltf = GLTF2().load_binary(out)
    scene = gltf.scenes[gltf.scene or 0]
    extras = scene.extras or {}
    assert extras["dims_source"] == "jedec_default"
    assert abs(extras["dims"]["A"] - 1.75) < 1e-6
    assert extras["package_type"] == "SOIC-8"
    names = {n.name for n in gltf.nodes}
    assert "Body" in names and "Leads" in names


def test_package_3d_hierarchy_validation_counts_leads(tmp_path):
    from src.core import validate_package_3d_glb
    from src.schematic_generator.package_3d_builder import build_package_3d

    out = str(tmp_path / "dip8_3d.glb")
    pins = [{"number": str(i), "name": f"P{i}"} for i in range(1, 9)]
    assert build_package_3d("DIP-8", 8, "TEST", pins, out)
    ok, errors = validate_package_3d_glb(out, pin_count=8)
    assert ok, errors
```

**Step 2: Run — expect FAIL** (`ImportError`)

**Step 3: Implement**

`src/core/package_3d_extras.py` (scene-level extras only — the 3D model needs no per-node platform metadata yet; YAGNI):

```python
"""Inject provenance and dimension metadata into package 3D GLBs."""

from pathlib import Path
from typing import Dict, Optional

try:
    from pygltflib import GLTF2
except ImportError:
    GLTF2 = None


def inject_package_3d_extras(
    glb_path: str,
    component_name: str,
    package_type: str,
    dims: Dict[str, float],
    dims_source: Optional[str] = None,
) -> None:
    """Write component identity, resolved dims (mm) and provenance into
    scene extras, mirroring the footprint's dims_source contract."""
    if GLTF2 is None:
        raise ImportError("pygltflib is required for extras injection")

    gltf = GLTF2().load_binary(str(Path(glb_path)))
    scene = gltf.scenes[gltf.scene if gltf.scene is not None else 0]
    extras = dict(scene.extras or {})
    extras.update({
        "component_name": component_name,
        "package_type": package_type,
        "unit": "mm",
        "dims": {k: v for k, v in dims.items() if isinstance(v, (int, float))},
        "dims_source": dims_source or "unverified",
    })
    scene.extras = extras
    gltf.save_binary(str(Path(glb_path)))
```

`src/core/package_3d_hierarchy.py`:

```python
"""Structural validation for package 3D GLBs (Package3D/Body/Leads)."""

from pathlib import Path
from typing import List, Tuple

try:
    from pygltflib import GLTF2
except ImportError:
    GLTF2 = None


def validate_package_3d_glb(glb_path: str, pin_count: int) -> Tuple[bool, List[str]]:
    """Check the exported hierarchy: a Body node, a Leads node whose child
    count equals pin_count. Runs after optimize_glb_hierarchy."""
    if GLTF2 is None:
        raise ImportError("pygltflib is required for GLB validation")

    gltf = GLTF2().load_binary(str(Path(glb_path)))
    errors: List[str] = []
    by_name = {}
    for idx, node in enumerate(gltf.nodes or []):
        by_name.setdefault(node.name, idx)

    if "Body" not in by_name:
        errors.append("missing Body node")
    if "Leads" not in by_name:
        errors.append("missing Leads node")
    else:
        leads = gltf.nodes[by_name["Leads"]]
        n = len(leads.children or [])
        if n != pin_count:
            errors.append(f"Leads has {n} children, expected {pin_count}")
    return (not errors), errors
```

Add both to `src/core/__init__.py` imports and `__all__`.

`save_glb` + module-level wrapper in `package_3d_builder.py` (same shape as the footprint's `save_glb` at `pcb_footprint_builder.py:755` — build, save, optimize, inject, validate, return bool):

```python
    def build_model(self, pin_data: List[Dict[str, Any]]) -> cq.Assembly:
        """Complete Package3D assembly: Body + Leads.

        pin_data is accepted for interface symmetry with the other builders
        and to keep lead naming honest: only pins present in the extraction
        are emitted (matches the footprint's behavior for skipped pins).
        """
        wanted = {str(p.get("number", p.get("pin_num", ""))) for p in pin_data}
        assy = cq.Assembly(name="Package3D")
        assy.add(self.build_body(), name="Body")
        leads_assy = cq.Assembly(name="Leads")
        for pos in self.pin_positions:
            if wanted and pos.pin_number not in wanted:
                continue
            leads_assy.add(self._build_one_lead(pos), name=pos.pin_number,
                           color=self.LEAD_COLOR, loc=self._lead_location(pos))
        assy.add(leads_assy, name="Leads")
        return assy

    def save_glb(self, output_path: str, pin_data: List[Dict[str, Any]]) -> bool:
        try:
            assembly = self.build_model(pin_data)
            assembly.save(output_path)
            try:
                original, simplified = optimize_glb_hierarchy(output_path)
                logger.info("Optimized 3D GLB hierarchy: %d -> %d nodes",
                            original, simplified)
                inject_package_3d_extras(
                    output_path,
                    component_name=self.component_name,
                    package_type=self.package_type,
                    dims=self.dims,
                    dims_source=self.dims_source,
                )
            except Exception as exc:
                logger.warning("Skipping 3D GLB post-processing: %s", exc)

            emitted = len({str(p.get("number", p.get("pin_num", "")))
                           for p in pin_data} or []) or self.pin_count
            is_valid, errors = validate_package_3d_glb(output_path, pin_count=emitted)
            if not is_valid:
                logger.error("3D GLB hierarchy validation failed: %s",
                             "; ".join(errors))
                return False
            return os.path.exists(output_path)
        except SchematicGenerationError:
            raise
        except Exception as e:
            logger.error("Error saving 3D GLB: %s", e)
            import traceback
            traceback.print_exc()
            return False


def build_package_3d(
    package_type: str,
    pin_count: int,
    component_name: str,
    pin_data: List[Dict[str, Any]],
    output_path: str,
    custom_layout: Optional[Dict[str, List[int]]] = None,
    extracted_dims: Optional[Dict[str, Any]] = None,
) -> bool:
    """Build and export a simplified 3D package model (mirror of
    build_pcb_footprint's signature so main.py wires it identically)."""
    builder = Package3DBuilder(
        package_type, pin_count, component_name, custom_layout, extracted_dims
    )
    return builder.save_glb(output_path, pin_data)
```

Refactor note: Task 6's `build_leads()` and `build_model`'s inline loop must not diverge — have `build_leads(wanted=None)` take the optional pin filter and let `build_model` call it. Update the Task 6/7/8 tests if the signature changes (they pass no filter).

**Step 4: Run the whole new section AND the full suite — expect PASS**

```bash
python3 -m pytest tests/test_suite.py -v
```

**Step 5: Commit**

```bash
git add src/core/package_3d_extras.py src/core/package_3d_hierarchy.py src/core/__init__.py \
        src/schematic_generator/package_3d_builder.py src/schematic_generator/__init__.py tests/test_suite.py
git commit -m "feat: 3D GLB export with extras provenance and hierarchy validation"
```

---

## Task 10: CLI integration — `--all` produces schematic + footprint + 3D

**Files:**
- Modify: `src/main.py` (`_both_output_paths` → add `_3d` variant; `process_datasheet_both` gains `include_3d`; `parse_arguments` + `_run_cli` get `--all`)
- Test: `tests/test_suite.py`

**Step 1: Write the failing tests**

```python
def test_all_output_paths_derives_three_siblings():
    from src.main import _all_output_paths

    s, f, t = _all_output_paths("output/NE555.glb")
    assert s == "output/NE555_schematic.glb"
    assert f == "output/NE555_footprint.glb"
    assert t == "output/NE555_3d.glb"
```

**Step 2: Run — expect FAIL** (`ImportError: _all_output_paths`)

**Step 3: Implement**

In `src/main.py` next to `_both_output_paths` (`src/main.py:88`):

```python
def _all_output_paths(output: str) -> tuple:
    """Schematic, footprint and 3D-model GLB paths from a base output arg."""
    p = Path(output)
    schematic, footprint = _both_output_paths(output)
    return schematic, footprint, str(p.parent / f"{p.stem}_3d.glb")
```

Extend `process_datasheet_both(...)` (`src/main.py:874`) with `include_3d: bool = False` and add a third block after the footprint block, using the identical shape (this is the established per-artifact fail-closed pattern — a refused 3D model must not kill the other outputs):

```python
    # --- 3D package model ---
    model3d_ok = True
    if include_3d:
        model3d_ok = False
        _, _, model3d_str = _all_output_paths(str(output_path))
        setup_output_path(Path(model3d_str))
        try:
            from .schematic_generator.package_3d_builder import build_package_3d
            package_type, pin_count, _, pin_data_list = pin_data_to_builder_format(
                pin_data, part_number=part_number, package_index=package_index,
            )
            model3d_ok = bool(build_package_3d(
                package_type=package_type,
                pin_count=pin_count,
                component_name=pin_data.component_name,
                pin_data=pin_data_list,
                output_path=model3d_str,
                custom_layout=custom_layout,
                extracted_dims=extracted_dims,
            ))
            if verbose:
                print(f"3D model: {model3d_str}")
        except DatasheetParserError as e:
            print(f"Failed to generate 3D model: {e}")
        if not model3d_ok:
            print(f"Failed to generate 3D model: {model3d_str}")

    return schematic_ok and footprint_ok and model3d_ok
```

(The footprint block already computes `pin_data_to_builder_format`; hoist that call above both blocks instead of calling it twice.)

In `parse_arguments` add:

```python
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate schematic, PCB footprint and 3D package model GLBs. "
             "Output argument is used as base name: NE555.glb -> "
             "NE555_schematic.glb + NE555_footprint.glb + NE555_3d.glb. "
             "Cannot be combined with --pcb-2d or --both.",
    )
```

In `_run_cli` (`src/main.py:1081`):
- mutual-exclusion check: any two of `--all`, `--both`, `--pcb-2d` together → error exit 1 (extend the existing check at `:1085`).
- the `if args.both:` branch becomes `if args.both or args.all:` and passes `include_3d=args.all` to `process_datasheet_both`.
- the unvalidated-watermark loop (`:1170-1175`) iterates `_all_output_paths(...)` when `args.all` (existing `_both_output_paths` otherwise) so the 3D output is watermarked too.
- update the argparse epilog examples with an `--all` line.

**Step 4: Run the unit test, then an end-to-end smoke run**

```bash
python3 -m pytest tests/test_suite.py -k all_output_paths -v
python3 -m src.main pdfs/<known-good-datasheet>.pdf output/dev/SMOKE.glb --all --verbose
```

Pick whichever PDF the existing eval corpus treats as reliably passing (see `tools/run_full_flow_eval.py` EXPECTED_PINS for candidates). Expected: three GLBs exist; open `SMOKE_3d.glb` in any glTF viewer and eyeball body/lead sanity. Verify exit code 0 (`echo $?`) — the exit-code contract (0/1/2) must hold for `--all`.

**Step 5: Commit**

```bash
git add src/main.py tests/test_suite.py
git commit -m "feat: --all flag emits schematic, footprint and 3D model in one run"
```

---

## Task 11: Geometry verification tool (trimesh-based, like `verify_glb_dims.py`)

**Files:**
- Create: `tools/verify_glb_3d_dims.py` (pattern: `tools/verify_glb_dims.py`)

**Step 1: Write the tool** (it *is* the test — the existing verify tools are standalone scripts, not pytest):

```python
"""
Verify that resolved heights land in the exported 3D GLB geometry.

Builds a SOIC-16 3D model twice (JEDEC defaults vs. 74HC595 extracted dims),
loads each GLB with trimesh, and measures:
  - overall model height       -> expected A (leads never exceed the body top)
  - body bottom Z              -> expected A1
  - lead tip span on X         -> expected E
  - body extents on X x Y      -> expected E1(derived) x D
Usage: python3 -u tools/verify_glb_3d_dims.py
"""
import sys

import trimesh

sys.path.insert(0, ".")

from src.schematic_generator.package_3d_builder import build_package_3d

PIN_DATA = [{"number": i, "name": f"P{i}"} for i in range(1, 17)]
EXTRACTED = {"e": 1.27, "E": 10.325, "D": 9.90, "b": 0.41, "L": 0.835,
             "A": 1.75, "A1": 0.15, "dims_source": "text"}


def measure(glb_path):
    scene = trimesh.load(glb_path)
    lo, hi = scene.bounds
    return {"height": hi[2], "span_x": hi[0] - lo[0], "zmin": lo[2]}


def check(label, got, expected, tol=0.05):
    ok = abs(got - expected) <= tol
    print(f"  {label:12s} got={got:7.3f} expected={expected:7.3f} {'OK' if ok else 'MISMATCH'}")
    return ok


def run(tag, dims):
    out = f"/tmp/verify_3d_{tag}.glb"
    assert build_package_3d("SOIC-16", 16, "74HC595", PIN_DATA, out,
                            extracted_dims=dims)
    m = measure(out)
    print(f"{tag}:")
    ok = check("height A", m["height"], dims["A"] if dims else 1.75)
    ok &= check("lead span E", m["span_x"], dims["E"] if dims else 6.0)
    ok &= check("min Z", m["zmin"], 0.0)
    return ok


if __name__ == "__main__":
    ok = run("jedec", None) & run("extracted", EXTRACTED)
    sys.exit(0 if ok else 1)
```

**Step 2: Run — expect exit 0 with all `OK` lines**

```bash
python3 -u tools/verify_glb_3d_dims.py; echo "exit=$?"
```

If a MISMATCH appears, that's a real geometry bug from Tasks 5–8 — debug the builder, don't loosen the tolerance.

**Step 3: Commit**

```bash
git add tools/verify_glb_3d_dims.py
git commit -m "feat: trimesh verification of 3D model heights and spans"
```

---

## Task 12: Eval harness — corpus runs exercise `--all` and record 3D status

**Files:**
- Modify: `tools/run_full_flow_eval.py`

**Step 1: Read the harness first.** Note: `git status` showed `tools/run_full_flow_eval.py` has uncommitted local modifications in the user's checkout — this worktree branched from origin/main, so diff your version against the user's before assuming line numbers; coordinate/rebase rather than clobbering their edits.

**Step 2: Extend it minimally:**
- Where it invokes `--both`, switch to `--all`.
- Record per-part `model3d_ok` (file exists + `validate_package_3d_glb` passes + height within `_A_BOUNDS`) into the JSON report next to the existing schematic/footprint status fields.
- Do NOT add per-part expected heights for the corpus (that's corpus-tuning — memory: the corpus validates principles, it never drives them). Family-level sanity only.

**Step 3: Run the eval on 2–3 corpus parts** (whatever invocation the harness header documents) and confirm the report gains the new field and previously-passing parts still pass.

**Step 4: Commit**

```bash
git add tools/run_full_flow_eval.py
git commit -m "feat: eval harness runs --all and reports 3D model status"
```

---

## Task 13: Documentation

**Files:**
- Create: `docs/PACKAGE_3D_HIERARCHY.md` — the Package3D/Body/Leads node contract, coordinate system (Z=0 board plane, footprint-aligned origin), extras schema (`dims`, `dims_source`, `unit`), per-family lead style table, and the fail-closed rules (BGA/LCCC refuse; no-height refuse). Pattern: `docs/PCB_FOOTPRINT_HIERARCHY.md`.
- Modify: `README.md` — add `--all` to the usage examples; one paragraph distinguishing the three artifacts (schematic = pinout diagram, footprint = land pattern, 3D = package model). Also fix the stale `--verify-ambiguity` / `--format step` examples at README lines ~86-89 if still present (those flags don't exist in `parse_arguments`).
- Modify: `daily_log.md` — append the day's entry per project convention. **Careful:** `daily_log.md` has uncommitted local changes in the user's main checkout; append, never rewrite, and expect to resolve a trivial conflict on merge.

**Commit:**

```bash
git add docs/PACKAGE_3D_HIERARCHY.md README.md daily_log.md
git commit -m "docs: package 3D model hierarchy, --all usage, daily log"
```

---

## Task 14: Final verification gate

1. Full suite: `python3 -m pytest tests/test_suite.py -v` — zero failures.
2. `python3 -u tools/verify_glb_dims.py` (footprint regression) and `python3 -u tools/verify_glb_3d_dims.py` — both exit 0.
3. End-to-end on three families: one DIP, one SOIC/TSSOP, one QFN from the corpus with `--all --verbose`; confirm three GLBs each, exit code 0, and visually inspect one `_3d.glb` in a glTF viewer.
4. Fail-closed spot checks: a BGA part with `--all` must still emit schematic (footprint + 3D refuse, exit code 1, no invented geometry files left behind — check no partial `_3d.glb` exists after a refusal).
5. `--force-best-effort` path: confirm the `_3d.glb` carries `validated=false` in scene extras when validation errors were forced through.

Only after all five: the work is done. Use superpowers:verification-before-completion before claiming success, and superpowers:requesting-code-review before merge.

---

## Explicitly out of scope (YAGNI — do not build these now)

- STEP/other CAD export formats (GLB only, matching the pipeline).
- Detailed cosmetic modeling (chamfers, curved lead bends, laser markings).
- BGA/LCCC 3D geometry (fail closed, same as footprint).
- QFN thermal pad (EPAD) in the 3D model — blocked on P2.2 (EPAD extraction) in the current backlog; add the terminal plate then.
- Extracting lead thickness `c` from drawings (JEDEC defaults suffice for simplified models; revisit if eval shows visible errors).
- A dedicated single-output `--3d-only` CLI mode (use `--all` and ignore the siblings; add the flag only when someone actually needs it).

## Risks / gotchas for the implementer

- **cadquery `Location` rotation signature** varies between versions — `cq.Location(vector, axis, angle_degrees)` is correct for 2.5.x; if placement looks wrong, test rotation on a single lead in isolation first.
- **`optimize_glb_hierarchy` collapses wrapper nodes** — the Body/Leads names must survive it. If validation fails on missing names, check what the optimizer collapsed (the footprint builder had the same issue; see `normalize_pcb_footprint_bodyline_names` for the precedent of post-export renaming).
- **Quad packages**: E spans left/right, D spans top/bottom; body extents are E1 × D1. Mixing these up produces leads floating in air on two sides — the LQFP-48 test in Task 6 exists to catch exactly this.
- **`pin_positions` include pins the extraction may not have** (and vice versa): `build_model` filters by extracted pin numbers, mirroring `build_all_pins`' skip-with-warning behavior in the footprint builder.
- **Wrong-variant upstream bugs (P1.x backlog)** flow into 3D: a wrong package family gives a confidently wrong body. That's upstream's job to fix — do not add corpus-specific workarounds here.
