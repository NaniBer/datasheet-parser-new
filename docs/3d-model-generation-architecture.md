# 3D Component Model Generation — Architecture & Implementation Plan

**Date:** 2026-08-03
**Status:** Proposal (research synthesis, no code changed)
**Scope:** Extend the existing `component → schematic → footprint` pipeline with a `→ 3D body model` stage, reusing what the system already produces. This is an *extension*, not a new datasheet pipeline.

This document synthesizes a multi-track investigation of (a) the existing codebase, (b) the physical/mechanical data it already extracts, (c) its current cadquery/GLB generation, (d) open-source CAD tool options, (e) electronics-package modeling conventions and reusable OSS generators, and (f) validation strategy. File/line citations point at the current tree.

---

## 1. How the current system works today (unchanged — do not rebuild)

Entry is the CLI `main()` → `_run_cli()` (`src/main.py:1589,1610`). **Input is always a local PDF path**, never a bare part number; the component is identified by the datasheet itself (`--part-number` is optional steering context only, inferred otherwise via `infer_part_number_hint`, `src/pdf_extractor/part_number_hint.py:125`).

Pipeline stages, in order (single-output path `process_datasheet`, `src/main.py:1146`):

1. `get_dynamic_min_confidence` — auto-tune page-detection threshold by doc size (`main.py:1191`).
2. `detect_relevant_pages` — hybrid page detection: deterministic scoring (`PageDetector`, `page_detector.py:98`) with an **LLM fallback that fails closed** (`_verify_pin_page_fallback`, `main.py:191`; exits rather than fabricate).
3. `extract_content` → `ExtractedContent` (`content_extractor.py:22`).
4. `infer_part_number_hint` (if no `--part-number`).
5. `extract_pin_data` → `PinData` — deterministic table parse first, LLM fallback with a ≤3-attempt validation-retry loop, then `normalize_package`, `drop_ungrounded_pins`, `validate_pin_data_extraction` (`main.py:1205`, `342-448`).
6. `apply_ordering_ground_truth` — reconcile pin count/family against the datasheet's ordering table (`main.py:1215`).
7. `flag_module_footprint` — mark modules/SiP as footprint-unsupported (`main.py:1225`).
8. `extract_layout_with_vision` — optional Vision-API side→pin layout (`main.py:1230`).
9. `enforce_known_package_type` — fail-closed on unknown geometry (`main.py:1264`).
10. **Generate output**: `DimensionExtractor().extract()` then a builder — `build_pcb_2d_schematic` (footprint) or `build_schematic_from_pin_data` (schematic) (`main.py:1271-1338`).
11. `mark_glb_unvalidated` watermark if `validation_errors` present (`main.py:1349`).

**External services:** a text LLM (`https://fastchat.ideeza.com/v1`, `src/chat_bot.py:17`, model default `llama-3`, temp 0, non-deterministic — backend ignores `seed`) for pin/page/ordering extraction, and a Vision/OCR API (`https://qwen1.ideeza.com/describe_image_llm`, `image_ocr_client.py:54`) used for layout **and dimension extraction**. No web datasheet fetching.

**CAD engine already present:** cadquery **2.5.2** (OCP 7.7 / OpenCASCADE), plus trimesh + pygltflib. CadQuery genuinely builds B-rep solids and exports GLB via `Assembly.save()`; trimesh is used only in a verification tool; pygltflib post-processes the GLB (renames nodes, fixes materials, injects glTF `extras`).

---

## 2. What the system already produces (available to a 3D stage)

**Final artifacts today = GLB files only** (no STEP/STL, no JSON product):
- 3D/default → `output.glb` = the **schematic/pinout symbol** (`pinout_diagram_builder.py:506`).
- `--pcb-2d` → `output.glb` = the **PCB footprint** (`pcb_footprint_builder.py:796`).
- `--both` → `<stem>_schematic.glb` + `<stem>_footprint.glb` (`main.py:146`).

Both GLBs are thin "2.5D" extrusions (pads/lines/text), **not a solid package body**. Coordinate convention: **millimeters, `Workplane("XY")` drawn and extruded along +Z, origin at the component center (0,0)** — pins are explicitly recentered on the origin (`pcb_footprint_builder.py:233-256`).

Data available in-memory by the time footprint generation completes:

- **`PinData`** (`src/models/pin_data.py:28`) — `component_name`, single or multi-`packages[]` with `pin_count` and per-pin `{number,name,function}`, `selected_package_type`, `ordered_pin_count`/`ordered_package_type` (ground truth), `validation_errors`, `footprint_unsupported_reason`.
- **`extracted_dims`** flat dict from `DimensionExtractor.extract()` (`dimension_extractor.py:66`): `package_type, unit(mm), e, E, D, E1, D1, b, L, A, b_max/b_min, L_max/L_min, dims_source(text|vision|text+vision)`. Min/max collapsed to nominal midpoints; pad-critical `b`/`L` extremes preserved. Passes plausibility/family gates (`text_dimensions.py:198`).
- **Pad map** — `PcbFootprintBuilder.pin_positions` (list of `PinPosition{pin_number,x,y,side,rotation}`, `pin_layout.py:15`) and a `pin_position_map = {pin_number:(x,y)}` (`pcb_footprint_builder.py:835`), plus `pad_spec` (IPC-7351 pad shape/size, `_compute_pad_spec`, `:284-329`) — all in the same mm / origin-centered / +Z-up frame.
- **JEDEC defaults** — `get_footprint_defaults()` (`footprint_defaults.py:68`) returns real `{e,E,E1,D,D1,b,L}` per family for 12 package families when extraction is thin.
- **Package family classification** — `PackageType` enum (12 families: DIP, SOIC, TSSOP, DFN, WSON, SON, TQFP, QFN, LQFP, BGA, LCCC, CDIP), aliases, and detectors.

**Key finding:** the extractor already reads package **height `A` and standoff `A1`**, but the footprint builder discards them (`_apply_extracted_dims` applies only `e,E,D,b,L,E1,D1`, `pcb_footprint_builder.py:257-272`). The vertical profile is currently thrown away — wiring it in is a transform on already-available data, not new extraction.

---

## 3. Where 3D generation is added

```
                       CURRENT SYSTEM  (unchanged)
  Component (PDF) ─► page detect ─► content ─► pin extract ─► ordering
        ground truth ─► package-type enforce ─► DimensionExtractor.extract()
                 │
        ┌────────┴──────────────┐
        ▼                        ▼
  Schematic GLB            Footprint GLB  (PcbFootprintBuilder)
  (pinout symbol)          + pin_position_map + pad_spec + extracted_dims
                                 │
                                 ▼   ◄── integration hook (see §9)
                        ┌───────────────────────────────────────────┐
                        │                NEW 3D LAYER                │
                        │  extracted_dims + pad map + family + pins   │
                        │        ▼                                    │
                        │  Body3DSpec  (normalize/derive, fill A/A1)  │
                        │        ▼                                    │
                        │  PackageTemplateRegistry.select(family)     │
                        │        ▼                                    │
                        │  Parametric cadquery template → cq.Assembly │
                        │        ▼                                    │
                        │  Exporter → STEP (B-rep) + GLB (web)        │
                        │        ▼                                    │
                        │  Body3DValidator (dims + pad alignment)     │
                        │        ▼                                    │
                        │  <stem>_body.step / <stem>_body.glb         │
                        └───────────────────────────────────────────┘
```

The 3D body is aligned to the **same origin the footprint already uses** (component center, mm, +Z-up, seating plane at Z=0). See §5 on the KiCad-convention nuance.

---

## 4. Gap analysis

| Area | Current implementation | Available data | 3D requirement | Gap | Recommended addition |
|---|---|---|---|---|---|
| Component identification | PDF-driven pipeline | `component_name`, part-number hint | Required | **None** | Reuse `PinData.component_name` |
| Package-type classification | `PackageType` enum + detectors | family string (12 families) | Required (selects template) | **None** | Reuse; map family→template |
| Footprint / pad map | `PcbFootprintBuilder` | `pin_position_map`, `pad_spec`, `pin_positions` | Required for alignment | **None** | Reuse directly for alignment |
| Body length `D` | Applied to footprint | `extracted_dims["D"]` + defaults | Required | **None** | Reuse |
| Body width `E1`/`D1` | Applied to footprint | `E1`/`D1` (+ defaults) | Required | Partial (QFN uses `E`; `E`=lead span not body) | Family-aware: use `E1` for body, `E` for span |
| Lead pitch `e`, count `N`, per-side | Applied / in `PinData` | `e`, `pin_count`, `pins_per_side` | Required | **None** | Reuse |
| Lead width `b`, foot `L` | Applied to pads | `b/b_max`, `L/L_max` | Required | **None** | Reuse |
| **Body height `A`, standoff `A1`** | **Extracted but discarded** | in `extracted_dims` (unused) | Required (Z extrusion) | **Transform** (just wire it) | Consume `A`→body height, `A1`→standoff |
| Lead thickness `c` | Not extracted | — | Needed for gull-wing solids | **Missing** | Add `c` to `DimensionExtractor` |
| Exposed/thermal pad `D2×E2` | Only as numbered pin | — | Needed for QFN/DFN/DPAK | **Missing** | Add `D2/E2` to extractor + template |
| Lead form (gull-wing/J/no-lead) | Not modeled | family implies it | Required | **Missing** | Encode per-template by family |
| Pin-1 physical marker | Synthetic (convention) | numbering side/order | Required (orientation) | Partial | Derive marker from layout convention |
| 3D geometry | Not implemented | none | Required | **Full** | New parametric templates |
| 3D format (STEP/GLB) | GLB export exists; **STEP never invoked** | cadquery can do both | Required | Partial (capability present) | New exporter calling `Assembly.save(".step")` + GLB |
| Footprint↔model alignment | N/A | pad map + shared origin | Required | Partial | New alignment/validation logic |
| Validation | Extraction + hierarchy + `verify_glb_dims.py` | measure→compare pattern exists | Required | Partial | New `Body3DValidator` (§11) |
| BGA/LGA/LCCC/TSOP geometry | `footprint_defaults` returns None; grid arrays routed to schematic-only | none | Required (later phase) | **Full** | Phase-2 templates + ball-map param |

---

## 5. CAD technology recommendation

**Stay on CadQuery (already installed). Do not add a second CAD kernel.**

- CadQuery is a pure headless Python library on the OCCT kernel — ideal for server/batch. It already builds the B-rep solids in this repo.
- **STEP export is essentially free:** the existing assemblies can be saved as STEP today — `assembly.save(path, exportType="STEP")` or `cq.exporters.export(shape, "part.step")`. STEP is simply never invoked in the current code.
- **GLB for web preview** comes from the same kernel: native `Assembly.save(..., "GLB")`, or tessellate → `trimesh.Scene.export(".glb")` (already a dependency; gives Draco compression + material control). Tune `tolerance`/`angularTolerance` to control GLB size.
- **build123d** (same OCP kernel, same Apache-2.0 license, objects interchangeable) is a *low-risk optional* upgrade for authoring ergonomics on complex templates — adopt additively for new modules only, do not migrate the working pipeline.
- **Rejected:** OpenSCAD (no STEP, GPL, non-Python DSL); Blender/bpy (no STEP, no B-rep, GPL — only viable as an isolated subprocess for rendering thumbnails); FreeCAD (works headless via `freecadcmd` but means shipping/driving a whole app — unnecessary when OCP is in-process).

**Licensing:** CadQuery/build123d are Apache-2.0; OCP/OpenCASCADE is LGPL-2.1-with-exception (royalty-free commercial use; obligations satisfied because OCP is a swappable pip wheel). trimesh/pygltflib permissive. **No GPL contamination** on this stack — the commercially safe path. (Engineering guidance, not legal advice.)

**Server gotcha:** use the `cadquery-ocp` **novtk** wheel headless, and pin the Python version (OCP ships wheels for a bounded range).

---

## 6. Recommended architecture for the new 3D layer

A single new package `src/model3d/` that mirrors the existing `schematic_generator/` conventions and consumes the same builder-format tuple + `extracted_dims`:

```
Existing:  PinData + extracted_dims + PcbFootprintBuilder (pad map, pad_spec)
              │
   ┌──────────┴─────────────────────────────────────────────────────────┐
   │ src/model3d/                                                          │
   │   spec.py            Body3DSpec dataclass + build_spec(...)           │
   │   registry.py        PackageTemplateRegistry: family → template       │
   │   templates/         parametric cadquery generators per family        │
   │       base.py        PackageTemplate ABC (build() -> cq.Assembly)      │
   │       gullwing.py    SOIC/SOP/SSOP/TSSOP/QFP/TQFP/LQFP/SOT             │
   │       leadless.py    QFN/DFN/LGA (+ exposed pad)                       │
   │       through_hole.py DIP                                              │
   │       chip.py        chip R/C/L (2-terminal box)                       │
   │       bga.py         BGA/LGA grid (phase 2)                            │
   │   exporter.py        cq.Assembly → STEP + GLB                          │
   │   alignment.py       datum/seating-plane/pin-1 registration to pads    │
   │   validator.py       Body3DValidator (dims + alignment, §11)           │
   │   builder.py         build_body_model(...) orchestrator (public API)   │
   └───────────────────────────────────────────────────────────────────────┘
              │
   Output:  <stem>_body.step  +  <stem>_body.glb  (+ watermark if low-confidence)
```

**Origin/datum decision (resolved cross-agent tension):** KiCad convention anchors SMD footprints at the body centroid and THT at pin 1, with the seating plane at Z=0. The existing footprint builder recenters *everything* on the component center (0,0). Since **this system controls both the footprint and the 3D body**, the governing requirement is internal consistency: **align the 3D body to the same origin the footprint already uses (component center), seating plane at Z=0, +Z up, mm.** If/when models are exported for KiCad interoperability, apply the KiCad datum + the WRL 1/2.54 scale in the exporter as a separate concern — not in the geometry templates.

---

## 7. 3D specification model (derived from existing outputs)

`Body3DSpec` is built entirely from data the system already has (plus the two dims to add). Proposed dataclass:

```python
@dataclass
class Body3DSpec:
    component_name: str
    package_family: str          # from PackageType enum / detector
    lead_style: str              # "gullwing" | "leadless" | "jlead" | "through_hole" | "chip" | "bga"
    pin_count: int
    pins_per_side: list[int]     # [L,R,T,B] from SchematicParameters / layout
    # body (mm)
    body_length_D: float
    body_width_E1: float         # E1/D1 (body), NOT E (lead span) for gull-wing families
    body_height_A: float         # from extracted_dims["A"]  (currently discarded)
    standoff_A1: float           # from extracted_dims["A1"] (currently discarded)
    # leads (mm)
    lead_span_E: float           # tip-to-tip
    lead_pitch_e: float
    lead_width_b: float
    lead_foot_L: float
    lead_thickness_c: float | None   # NEW extractor field
    exposed_pad: tuple[float,float] | None  # (D2,E2) NEW, QFN/DFN/DPAK
    # registration
    pad_map: dict[int, tuple[float,float]]  # reuse pin_position_map
    pin1_side: str
    dims_source: str             # text|vision|text+vision|jedec_default
    confidence: str              # "verified" | "unverified"
```

`build_spec()` fills each field from `extracted_dims` first, `get_footprint_defaults()` as fallback, and tags `dims_source`/`confidence` accordingly (fail-open watermarking, consistent with the existing contract).

---

## 8. Package-template strategy

**Reuse the parameter model, clean-room the code.** The official KiCad **kicad-packages3D-generator** (GitLab, being migrated to cadquery 2.x) and the older **easyw/kicad-3d-models-in-freecad** scripts already parameterize every high-volume family with dictionaries that map almost 1:1 onto our JEDEC dims (e.g. QFN `Params(c,L,D,E,A2,b,e,npx,npy,epad,...)`). **But those generators are GPL-3.0 / LGPL-2.1** — importing/adapting their *code* into a commercial product imposes copyleft. **KiCad StepUp is AGPL + trademarked — do not embed it.**

Recommendation: **write our own cadquery templates (Apache-safe), using the generators' parameter tables and JEDEC outlines (MO-220 QFN, MS-026 QFP, MS-012/013 SOIC, etc.) as factual references** (dimensions/parameter names are facts, not copyrightable). Keep the KiCad model library and `easyeda2kicad.py` (LCSC→STEP) as *manual fallbacks* for long-tail/branded parts, checking per-part licensing before redistribution. `cq_warehouse` (Apache-2.0) is a source of reusable fillet/chamfer/thread helper patterns.

Template families are template-able when body+leads reduce to extrusion/array driven by scalars — which is exactly the group whose dims we extract:

**Phase 1 (cleanly parametric, highest coverage):**
1. Chip passives R/C/L (0201–1206) — trivial box + 2 terminals; highest part-count ROI.
2. SOIC/SOP/SSOP/TSSOP/MSOP — 2-sided gull-wing.
3. QFP/TQFP/LQFP — 4-sided gull-wing.
4. QFN/DFN/LGA — leadless box + bottom lands + exposed pad.
5. SOT-23/223/SC-70 — small gull-wing.
6. DIP — through-hole.

**Phase 2 (parametric with a family body):**
7. BGA/LGA-grid — body + ball array + depopulation mask.
8. TO-220/DPAK(TO-252)/D2PAK(TO-263)/TO-247 — body + tab + mounting hole + bent leads.

**Phase 3 (semi-custom bodies scaled by size, as needed):**
9. Crystals/oscillators (HC-49, SMD cans), electrolytic/tantalum caps, SMD LEDs/diodes.
10. Connectors — headers/sockets parametric; branded (JST/Molex/USB/RJ45/D-sub) as per-family bodies or `easyeda2kicad` fallback.

Extractor additions needed for faithful Phase-1 bodies: **`c`** (lead thickness) and **`D2×E2`** (exposed pad).

---

## 9. Exact new modules/classes to add

**New package `src/model3d/`** (all new; nothing existing is modified except two small hooks):

- `spec.py` — `Body3DSpec` dataclass + `build_spec(pin_data, extracted_dims, pad_map, family) -> Body3DSpec`.
- `registry.py` — `PackageTemplateRegistry` mapping `PackageType`/family → `PackageTemplate`; fail-closed on unknown family (mirrors `enforce_known_package_type`).
- `templates/base.py` — `PackageTemplate` ABC: `build(spec) -> cq.Assembly` with named sub-nodes (`Body`, `Lead_<n>`, `ExposedPad`, `Pin1Marker`).
- `templates/gullwing.py`, `leadless.py`, `through_hole.py`, `chip.py`, `bga.py` — the parametric generators.
- `exporter.py` — `export_step(assembly, path)` + `export_glb(assembly, path)` (native or via trimesh; tolerance-tuned); optional KiCad-mode (datum shift + WRL 1/2.54 scale).
- `alignment.py` — registers body to the footprint datum (component-center, Z=0), pin-1 orientation from layout.
- `validator.py` — `Body3DValidator` (see §11), returns metrics + `issues[]` + `ok`, reusing the `verify_glb_dims.py` measure pattern.
- `builder.py` — `build_body_model(pin_data, extracted_dims, footprint_builder, output_path, *, kicad=False) -> Body3DResult` (public entry, mirrors `build_pcb_2d_schematic`).

**Extractor additions (small, in existing files):**
- `src/pdf_extractor/dimension_extractor.py` — extract `c` (lead thickness) and `D2`/`E2` (exposed pad); add to the flat dict + plausibility gates.
- Start *consuming* `A`/`A1` (already extracted) — read in `build_spec`, no new extraction.

**Integration hooks (two small call sites):**
- `process_datasheet_both` (`src/main.py:1382`), right after footprint success (~`main.py:1441-1452`, before return `:1465`) — call `build_body_model(...)`; extend `_both_output_paths` (`main.py:146`) to add `<stem>_body.{step,glb}`.
- `process_datasheet` single path (`main.py:1329-1338`, before the watermark `:1347`) — parallel hook for `--pcb-2d`.
- Add a CLI flag (e.g. `--body-3d` / include in `--both`) and reuse `mark_glb_unvalidated`/`validation_marker` for low-confidence gating.

**Data structures reused unchanged:** `PinData`, `extracted_dims` dict, `PinPosition`/`pin_position_map`, `pad_spec`, `PackageType` enum, `pin_data_to_builder_format` (`adapter.py:14`).

---

## 10. End-to-end workflow for one component

```
PDF ─► [existing pipeline stages 1–9] ─► PinData + extracted_dims
     ─► PcbFootprintBuilder ─► footprint GLB + pin_position_map + pad_spec
     ─► build_body_model():
          1. build_spec()        : Body3DSpec (fills A/A1; family→lead_style; dims_source/confidence)
          2. registry.select()   : PackageTemplate for family (fail-closed if unknown)
          3. template.build(spec): cq.Assembly (body + leads + exposed pad + pin-1 marker)
          4. alignment.register(): datum = footprint origin, seating plane Z=0, pin-1 orientation
          5. validator.validate(): dims vs extracted_dims; lead tips vs pad_map (§11)
          6. exporter.export()   : <stem>_body.step + <stem>_body.glb
          7. gate               : if any check fails or dims_source=jedec_default/unverified
                                   → mark_glb_unvalidated + flag for human review
```

---

## 11. Validation strategy (reuses existing eval infra)

The repo already validates three orthogonal axes: extraction accuracy (`extraction_validator.py:314`), GLB node-hierarchy (`pcb_footprint_hierarchy.py:88`, `reference_glb_hierarchy.py:187`), and — the reusable pattern — **dimensional GLB measurement** (`tools/verify_glb_dims.py`: trimesh load → per-node world-space AABB → reduce to package metrics → compare within tolerance). The vendor-footprint regression (`tools/run_ground_truth_eval.py`, 5/5 matching) contributes the centroid-normalization + tolerance approach. Current accuracy context: pin-count 78/111 = 70%, coverage 91%, but only ~18/127 fully validated ("confidence, not coverage").

`Body3DValidator` should:

1. **Dimension check** — measure the generated solid. Prefer exact **B-rep measurement in cadquery** (`Workplane.val().BoundingBox()`, per-sub-solid boxes, `Solid.isValid()`, `Volume`); fall back to the trimesh AABB path for GLB. Assert bounding footprint X≈`E` (span), Y≈`D`, Z≤`A`+tol (A is max-only); molded sub-box ≈ `E1×D×A2`; standoff ≈ `A1`; **lead count = N (exact)**, pitch ≈ `e`, width ≈ `b`, thickness ≈ `c`, foot ≈ `L`. Guard lead count + pitch first (dominant corpus failure mode).
2. **Footprint↔model alignment** — for each pin, project the 3D lead-foot centroid to the board plane; assert it lands within the pad extent from `pad_spec`/`pin_position_map`. Report worst-pin delta (as the vendor regression does).
3. **Coordinate/origin/seating** — `min(Z)` of lead feet ≈ 0; body underside ≈ `A1`; pin-1 in the expected quadrant vs the `FirstPinMarker`.
4. **Clearance/fit** — body+lead AABB fits inside the courtyard; `isValid()`/watertight; standoff `A1>0`; coplanarity ≤ `ccc`.
5. **Human-review gating** — reuse `mark_glb_unvalidated` (`validation_marker.py:16`): flag when any check exceeds tolerance, dims fell back to JEDEC defaults, or extraction was already watermarked. Never ship an unverified model as clean.

**Recommended tolerances** (two-tier: tight when checking our own build fidelity, loose when checking against extracted/vendor dims):

| Check | Threshold |
|---|---|
| Lead count `N` | exact |
| Lead pitch `e` | ±0.05 mm (or exact vs standard pitch set) |
| Body `D`, `E1` | ±0.10 mm or ±2% (larger) |
| Lead span `E`/`HE` | ±0.15 mm |
| Lead `b`, `L`, `c` | ±0.05 mm |
| Overall height `A` | one-sided `measured ≤ A + 0.05` |
| Standoff `A1`, body `A2` | ±0.10 mm |
| Lead-tip-on-pad (worst pin) | ≤0.35 mm, must land within pad |
| Seating-plane Z / origin | ±0.02 mm (own geometry) |

**Note on the JEDEC `E` vs `HE` gotcha** (`docs/footprint-qc-dimensions.md`): JEDEC `E` = lead span tip-to-tip, `E1` = body width, but some vendors (NXP/Nexperia) print `HE` for span and `E` for body width. The extractor's `E` is the *span*; templates must use `E1` for the molded body — get this wrong and the body will be modeled the size of the lead span.

**Non-determinism caveat:** the LLM backend ignores `seed` (temp already 0), so a single corpus run's score has ±~6 noise — trust deterministic unit/end-to-end tests and multi-run majority, not one run.

---

## 12. Implementation roadmap (from the current codebase)

**Milestone 0 — prerequisites (small, in existing files):**
- Wire `A`/`A1` through `build_spec` (already extracted).
- Add `c` (lead thickness) and `D2/E2` (exposed pad) to `DimensionExtractor` + plausibility gates.
- Add a proof-of-concept `exporter.export_step()` calling `Assembly.save(".step")` on an existing footprint assembly (proves STEP works with zero new deps).

**Milestone 1 — vertical slice (one family end-to-end):**
- Scaffold `src/model3d/` with `spec.py`, `registry.py`, `templates/base.py`, `builder.py`, `exporter.py`.
- Implement **SOIC gull-wing** template first (best-covered dims; `74HC595` is the existing dimensional fixture in `verify_glb_dims.py`).
- Wire the `process_datasheet_both` hook behind a flag; emit `<stem>_body.step` + `.glb`.
- Implement `Body3DValidator` dimension + alignment checks; validate SOIC-16 against `74HC595` extracted dims.

**Milestone 2 — Phase-1 breadth:**
- Add chip passives, TSSOP/SSOP/MSOP, QFP/TQFP/LQFP, QFN/DFN (+ exposed pad), SOT, DIP templates.
- Build a small 3D ground-truth set (reuse the vendor-STEP idea: compare a few generated bodies' bounding boxes to official KiCad STEP models, centroid-normalized, within §11 tolerances).

**Milestone 3 — hardening & scale:**
- Fail-closed on unsupported families; watermark low-confidence; human-review queue via the existing watermark channel.
- Batch/caching by `(family, dims-hash)` so identical packages reuse a model; model versioning tag in STEP/GLB extras.
- Headless: switch server images to the `cadquery-ocp` novtk wheel; tune GLB `tolerance`/`angularTolerance` (optional Draco) for web payload size.

**Milestone 4 — Phase 2/3 (as needed):** BGA/LGA grid, TO/DPAK tab families, then semi-custom bodies (crystals, electrolytics, connectors) with `easyeda2kicad` as the long-tail fallback.

---

## Appendix — resolved cross-investigation tensions

1. **Origin convention.** KiCad anchors SMD at body centroid / THT at pin 1; the existing footprint builder recenters everything to component center. Resolution: align the 3D body to the footprint's own origin (component center, Z=0) for internal consistency; apply KiCad datum + WRL 1/2.54 scale only in an optional export mode.
2. **Generator licensing.** The ready-made KiCad generators are GPL-3.0/LGPL/AGPL. Resolution: reuse their *parameter tables and JEDEC outlines as factual references*, but write clean-room cadquery (Apache-safe) templates; keep the model libraries + `easyeda2kicad` as manual fallbacks only.
3. **"STEP not implemented" vs "STEP is free."** Both true: the *capability* is present (cadquery `Assembly.save(exportType="STEP")`) but the *call* is never made today. Milestone 0 proves it with zero new dependencies.
4. **`A`/`A1` "missing" vs "available."** They are extracted and validated but discarded by the footprint builder — a wiring transform, not new extraction.
```
