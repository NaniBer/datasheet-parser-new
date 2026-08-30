# Requirements matrix — IDEEZA Component Generation Spec

Source of truth: `docs/IDEEZA_Component_Generation_Spec.html` (78 numbered requirements,
8 sections). Status assessed against the **source code**, not the example GLBs.
Machine-readable form: `docs/requirements-matrix.json`.

## Classification
- **extraction** — reading data from the datasheet
- **data-model** — how objects / IDs / layers / metadata are represented & governed
- **generation** — producing symbol / footprint / 3D geometry
- **export** — fabricator / CAD deliverable formats
- **validation** — QA gates & checks

## Status
`implemented` met · `partial` some sub-conditions met · `missing` not implemented ·
`impossible` cannot be satisfied/verified in the current architecture.

## Rollup (all 78)

| Status | Count |
|---|---|
| implemented | 20 |
| partial | 27 |
| missing | 30 |
| impossible | 1 |

MUST-only (72 of 78 are MUST): 17 implemented · 21 partial · 21 missing · 1 impossible.

### Status × classification

| | extraction | data-model | generation | export | validation |
|---|---|---|---|---|---|
| implemented | 0 | 1 | 15 | 2 | 2 |
| partial | 1 | 7 | 13 | 0 | 6 |
| missing | 6 | 9 | 13 | 0 | 2 |
| impossible | 0 | 0 | 0 | 1 | 0 |

## The structural story the matrix tells

1. **Generation is the strong half.** 15 of 41 generation requirements are implemented and
   another 13 partial — the geometry engine (footprint pads, silk clearance, symbol grid,
   3D body origin/standoff/materials, STEP) is the most complete part of the system.

2. **Extraction is the weak foundation, and it caps everything downstream.** 6 of 7 extraction
   requirements are missing. The data model carries only pin *number + name + one free-text
   function*; there is no electrical **type**, no per-pin side/length/active-low/hidden, no
   identification metadata, and dimensions are collapsed to a single **midpoint** (tolerances
   discarded). This directly blocks a cluster of generation/data-model rules that have no data
   to act on: SYM-04 (group by function), SYM-07 (pin types), SYM-08 (active-low),
   SYM-10 (ref-des class), SYM-11 (NC handling), F-03 (tolerance extremes).

3. **`F-01` is inverted.** The spec's highest-risk rule — *never invent a dimension; flag and
   stop* — is contradicted by the fail-open default (missing dims → JEDEC defaults / watermarked
   best-effort, never `BLOCKED`).

4. **Governance & data-model layer barely exists.** Link-by-ID (PL-02), staging before save
   (PL-03), review gate (F-05), versioning (F-07), provenance (F-04), IPC-class recording (F-08),
   layerId ownership (LAY-02), and the metadata fields (FP-17/18, SYM-14/16) are missing or
   partial. Artifacts are linked by *filename* — the exact anti-pattern PL-02 forbids.

5. **No manufacturing export exists.** There is no Gerber/ODB++/drill writer anywhere, so
   `LAY-07` (exclude courtyard/fab from fabrication output) is **impossible** to satisfy today,
   and the footprint stops at GLB/viewer geometry, not fabricator deliverables.

6. **Validation is real but not a gate.** V-05 (machine-readable report) is genuinely
   implemented and the conformance harness covers much of V-01/V-04 via granular checks; but
   V-02/V-03 batteries are UNRUN, and crucially the harness is an **offline grader** — nothing
   in the runtime pipeline (`main.py`/API) actually blocks output on it (PL-03 missing).

## Reading the JSON

Each entry in `requirements-matrix.json` → `requirements[]` has:
`id, section, tier, classification, status, requirement, evidence, notes`.
`evidence` cites the file/symbol that determined the status.
