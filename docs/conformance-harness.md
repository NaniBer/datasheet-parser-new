# Conformance harness

Turns the IDEEZA Component Generation Spec (`docs/IDEEZA_Component_Generation_Spec.html`)
into automated checks, so "correct" is enforced by code instead of eyeballed
per part. This is the exit from the find-a-defect / fix-a-defect loop: defects
are found by *class* across the whole corpus, and a part is "done" only when it
passes every applicable MUST rule.

## Layout (`src/conformance/`)

| File | Role |
|---|---|
| `rules.py` | **Phase 0 inventory** — every MUST rule as a row; `check=None` = inventoried but not yet automated (reports `UNRUN`). |
| `checks.py` | Concrete checks + a registry. Read the GLBs the pipeline already emits (no re-generation). |
| `model.py` | `CheckResult` / `PartReport` — the machine-readable report (spec `V-05`). |
| `runner.py` | Grade parts, write `conformance.json`, print the corpus roll-up. |

## Usage

```bash
# grade already-generated artifacts
python -m src.conformance generated_output/LM358 generated_output/74HC595

# grade every part folder under a root, writing conformance.json per part
python -m src.conformance --corpus generated_output --json

# also list the inventoried-but-unautomated rules
python -m src.conformance --corpus generated_output --show-unrun
```

A part directory holds the CLI's artifacts (`<base>_schematic.glb`,
`<base>_footprint.glb`, `<base>_body.glb`, `<base>_body.step`); `<base>` defaults
to the folder name, then `output` (the API job layout).

## Status contract

- `PASS` / `FAIL` — rule checked, satisfied / violated.
- `SKIP` — rule not applicable to this part (e.g. no 3D body for the family).
- `UNRUN` — rule inventoried but no check yet. **An UNRUN MUST rule blocks the
  pass** — an unverified part is not a passing part.

`passes_all_must` is true only when every MUST rule is `PASS` or `SKIP`.

## Per-family generation map

To grade *generation* in isolation from LLM extraction, drive the builders with
known-good per-family fixtures (`src/conformance/fixtures.py`):

```bash
python tools/gen_conformance.py            # all families, prints a family x rule map
python tools/gen_conformance.py soic8 qfn32 --out gen_out   # subset, keep artifacts
```

Any failure here is a generator defect, not an extraction one. Exit code is
non-zero if any family fails a MUST (usable as a CI gate).

## Currently automated (MUST) — 15/34

`V-01` pin/pad set · `V-05` report emitted · `SYM-02` 2.54 mm grid ·
`SYM-12` no duplicate/skipped pins · `FP-03` origin at centroid ·
`FP-04` perimeter numbering (monotonic sweep; absolute CW/CCW not asserted) ·
`FP-06`/`LAY-01` layer tree present · `FP-07`/`LAY-06` silk-to-pad ≥ 0.20 mm ·
`FP-08` pin-1 marker present · `FP-14` pad-to-pad ≥ 0.15 mm ·
`3D-01` STEP present · `3D-02` seating plane at Z=0 (THT-aware, read from the
footprint's plated holes) · `3D-11` body envelope ⊆ courtyard.

Geometry checks read each mesh's world-space AABB (POSITION accessor min/max ×
accumulated node transform) and reason in the **board plane**, auto-detected as
the two largest-extent axes — the exporter can leave a flat footprint in X-Y or
X-Z (Z-up→Y-up baked on the root). AABB clearance is conservative: it can
under-report a gap for curved art but never misses a real overlap.

## Growing coverage

Turn a `check=None` row in `rules.py` into a real check and register it in
`checks.py`. High-value next targets (all in the REMARKS): `SYM-04` group by
function, `SYM-02` grid snap, `FP-03` origin at centroid, `FP-04` CCW numbering,
`V-02` footprint dims vs datasheet. Rules needing data we don't yet capture
(per-pin electrical type, tolerances, provenance) stay `UNRUN` until the
extraction contract carries them — the report makes that gap visible rather than
hiding it.
