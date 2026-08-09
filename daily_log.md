# Daily Progress Log

## Format
Each day should follow this structure:
```markdown
## YYYY-MM-DD

### What We Did
- [ ] Task 1
- [ ] Task 2

### Issues Encountered
- Issue 1
- Issue 2

### What We Learned
- Key insight 1
- Key insight 2

### Tomorrow's Plan
- [ ] Task 1
- [ ] Task 2
```

---

## 2026-04-20 - Day 1

### What We Did
- ✅ Installed OpenDataLoader (opendataloader-pdf) for accurate table extraction
- ✅ Installed OpenJDK 17 (required dependency for OpenDataLoader)
- ✅ Integrated OpenDataLoader into ContentExtractor (hybrid mode: pdfplumber + OpenDataLoader)
- ✅ Created table-only mode that sends ONLY table data to LLM (eliminates diagram distractions)
- ✅ Built specialized table prompt (`build_table_extraction_prompt()`) that:
  - Intelligently analyzes table structure (1-3 header rows)
  - Detects multiple package variants in same table
  - Chooses ONE variant (prefers SOIC/PDIP)
  - Verifies pin count matches package type
  - Enforces exact pin names (QA, QB, QC - not Q1, Q2, Q3)
- ✅ Updated LLM client to use specialized prompt in table-only mode
- ✅ Updated main.py to auto-detect and enable table-only mode
- ✅ Tested on 5 PDFs (80% success rate):
  - 74HC595_TI.pdf: ✅ 20 pins (no duplicates!)
  - ESP32-C3: ✅ 34 pins
  - MAX1487-MAX491: ✅ 8 pins
  - MPU-6000: ✅ 24 pins
  - AMS1117: ❌ No table (simple 3-pin regulator)
- ✅ Renamed CLAUDE.md → plan.md and documented architecture
- ✅ Created clean commit with all OpenDataLoader changes
- ✅ Updated .gitignore with new patterns

### Issues Encountered
- **Issue 1**: pdfplumber struggled with multi-row header tables
  - **Solution**: Integrated OpenDataLoader which preserves multi-row header structure
- **Issue 2**: LLM hallucinated pin names (Q1, Q2, Q3...) when tables had exact names (QA, QB, QC...)
  - **Solution**: Created specialized table prompt that enforces exact names
- **Issue 3**: Multi-variant tables caused duplicate pin extraction (QA, SER, OE appeared twice)
  - **Solution**: Specialized prompt now chooses ONE variant and extracts only that
- **Issue 4**: Wrong pin count (20 pins for SOIC-16)
  - **Solution**: Specialized prompt verifies pin count matches package type
- **Issue 5**: Component name detection returns "Unknown"
  - **Status**: Pending fix
- **Issue 6**: Package format has duplicate pin count (SOIC-20-20 instead of SOIC-20)
  - **Status**: Pending fix

### What We Learned
- **OpenDataLoader is excellent for table extraction** - Preserves multi-row headers, outputs clean JSON, no pipe formatting issues
- **Table-only mode significantly improves LLM accuracy** - Sending clean 1432 chars vs 2323 chars, eliminates diagram distractions
- **Specialized prompts for different use cases** work much better than one-size-fits-all prompts
- **Hybrid mode is powerful** - Use pdfplumber for text/images (fast) + OpenDataLoader for tables (accurate)
- **Multi-variant tables are common** - Need to handle them intelligently (choose ONE variant, don't mix)

### Tomorrow's Plan
- [ ] Fix component name detection (currently returns "Unknown")
  - Extract from table headers or document title
  - Look for common patterns: "74HC595", "SN74HC595", "STM32F103", etc.
- [ ] Fix package format (SOIC-20-20 → SOIC-20)
  - Remove duplicate pin count from package type string
  - Clean up post-processing in LLM client or add validation
- [ ] Handle missing tables (AMS1117 case)
  - Detect when no table found (simple 3-pin regulators, etc.)
  - Fallback to diagram-based extraction or text-based extraction
  - Add warning message when table extraction fails
- [ ] Test on more PDFs to validate robustness
  - Try different component types: voltage regulators, connectors, displays
  - Test edge cases: single-pin components, no-pin components
- [ ] Consider adding variant selection flag
  - Allow users to specify: `--variant SOIC-16`
  - Useful when user wants specific package variant
- [ ] Document setup instructions for OpenDataLoader
  - Add to README.md or separate setup guide
  - Include Java installation steps
  - Include opendataloader-pdf installation

---

## 2026-04-23

### What We Did
- ✅ Fixed test script to handle both LLM extraction formats (multi-package and single-package)
  - Updated `test_all_pdfs_pin_layout.py` to detect and handle both formats
  - Added fallback to text-based extraction when no tables found
  - Lowered default min_confidence from 5 to 2 for simple components
- ✅ Tested all 6 PDFs successfully (100% success rate):
  - 74HC595_TI.pdf: ✅ 2 variants (SOIC-16, LCCC-20) - 36 total pins
  - ESP32-C3: ✅ 1 variant (QFN-32) - 32 pins
  - MAX1487-MAX491.pdf: ✅ 4 variants (DIP-8, SO-8, uMAX-8, DIP/SO-14) - 38 total pins
  - MPU-6000: ✅ 1 variant (QFN-24) - 24 pins
  - NE555.PDF: ✅ 1 variant (DIP-8) - 8 pins (text-based extraction)
  - AMS1117.pdf: ✅ 1 variant (SO-8) - 8 pins (text-based extraction)
- ✅ Integrated fixes into main.py with smart adaptive logic:
  - Added `get_dynamic_min_confidence()` function - auto-adjusts based on PDF page count:
    - Small PDFs (< 10 pages): min_confidence = 2 (NE555, AMS1117)
    - Medium PDFs (10-50 pages): min_confidence = 3 (MAX1487, ESP32-C3)
    - Large PDFs (> 50 pages): min_confidence = 4 (74HC595, MPU-6000)
  - Updated `extract_pin_data()` to handle both formats with enhanced verbose output
  - Updated `normalize_package()` to normalize package types for multi-package format
  - Fixed 2D PCB schematic generation to handle both formats
  - Added `DatasheetParserError` import to fix exception handling
- ✅ Created comprehensive test showing full 74HC595 extraction:
  - Extracted both SOIC-16 (16 pins) and LCCC-20 (20 pins) variants
  - All pins correctly identified with exact names (QA, QB, QC... not Q1, Q2, Q3...)
  - Generated 3D schematic successfully (2.2 MB GLB file)
  - Total processing time: ~40 seconds
- ✅ Updated daily_log.md (removed day numbers from format)

### Issues Encountered
- **Issue 1**: Test script failed on PDFs without tables (NE555, AMS1117)
  - **Root cause**: Script required tables, but some PDFs use text-based pinout diagrams
  - **Solution**: Added text-based extraction fallback and lower min_confidence threshold
- **Issue 2**: main.py crashed on multi-package format with AttributeError on pin_data.package
  - **Root cause**: `normalize_package()` only handled single-package format
  - **Solution**: Updated to handle both multi-package and single-package formats
- **Issue 3**: NameError: DatasheetParserError not defined in main.py exception handler
  - **Root cause**: Missing import for new exception class
  - **Solution**: Added DatasheetParserError to imports from .exceptions

### What We Learned
- **Text-based pinout extraction works well** for simple components (NE555, AMS1117)
- **Dynamic min_confidence adjustment is essential** - single threshold doesn't work for all PDF types
- **Multi-format support is critical** - LLM returns different formats for tables vs diagrams
- **100% success rate achieved** across diverse component types:
  - Shift registers (74HC595, MAX1487)
  - MCUs (ESP32-C3)
  - Sensors (MPU-6000)
  - Timers (NE555)
  - Voltage regulators (AMS1117)
- **Package types supported**: DIP, SOIC, QFN, LCCC, uMAX, LGA
- **Extraction methods**: Table-based (most accurate), Diagram/text-based (fallback)

### Tomorrow's Plan
- [ ] Add variant selection feature (allow users to choose specific package)
  - Add `--variant` CLI argument
  - Update schematic generation to use selected variant
  - Show available variants when multi-package detected
- [ ] Improve component name detection from table headers
  - Extract from document title or table captions
  - Look for common part number patterns
- [ ] Fix package format to remove duplicate pin counts (SOIC-20-20 → SOIC-20)
  - Add post-processing cleanup in normalize_package()
- [ ] Add more PDFs to test suite for better coverage
  - BGA packages
  - QFP/LQFP packages
  - Connectors
  - Displays

---

## Notes

### Current Status
- **Branch**: main
- **Status**: Ready to commit and push
- **Test Success Rate**: 100% (6/6 PDFs)
- **Total Package Variants Extracted**: 10
- **Processing Time**: 7-40s per PDF (average: ~21s)

### Key Files Modified
- `src/main.py` - Added dynamic min_confidence, dual format support, enhanced output
- `test_scripts/test_all_pdfs_pin_layout.py` - Handle both formats, text extraction fallback
- `daily_log.md` - Updated format and added today's progress
- `MAIN_PY_UPDATES.md` - Documentation of main.py integration changes

### Test Results Summary
| PDF | Pages | Variants | Total Pins | Method | Status |
|-----|-------|----------|------------|--------|--------|
| 74HC595_TI.pdf | 41 | 2 | 36 | Table | ✅ |
| ESP32-C3 | 76 | 1 | 32 | Table | ✅ |
| MAX1487-MAX491.pdf | 17 | 4 | 38 | Table | ✅ |
| MPU-6000 | 52 | 1 | 24 | Table | ✅ |
| NE555.PDF | 7 | 1 | 8 | Text | ✅ |
| AMS1117.pdf | 8 | 1 | 8 | Text | ✅ |

### 74HC595 Full Extraction Results
**Variant 1 - SOIC-16**: 16 pins (QB-QH, QH', SRCLR, SRCLK, RCLK, OE, SER, QA, NC, GND)
**Variant 2 - LCCC-20**: 20 pins (multiple NC pins, VCC, all signal pins)
**Generated Schematic**: 2.2 MB GLB file using SOIC variant

### Known Issues (Low Priority)
1. Component name detection (sometimes returns "Unknown")
2. Package format has duplicate pin counts (SOIC-20-20 → SOIC-20)
3. No variant selection UI for multi-package results

### Future Enhancements
- Variant selection flag (--variant SOIC-16)
- Component name detection improvement
- Package format cleanup
- More package types support (BGA, QFP, etc.)
- Cache page detection results
- Table visualization for debugging

### What We Did
- ✅ Modified table extraction prompt to extract ALL variants (not just one)
- ✅ Updated output structure to use packages array instead of single package object
- ✅ Changed JSON format from `{package, pins}` to `{packages: [{type, pins}]}`
- ✅ Updated PinData model to support both single-package (legacy) and multi-package (new) formats
- ✅ Updated adapter to handle both formats with package_index parameter
- ✅ Updated LLM client parser to detect and handle both formats
- ✅ Tested all-variants extraction on multiple PDFs (MAX1487, MPU-6000, NE555)
- ✅ Made component_name extraction optional (not required for PCB generation)
- ✅ Updated plan.md to reflect new all-variants extraction behavior

### Issues Encountered
- **Issue 1**: 74HC595 table is messy (broken rows, pin conflicts)
  - **Status**: Identified as edge case, not a prompt issue
  - **Resolution**: All-variants approach works perfectly on clean tables
- **Issue 2**: Component name extraction failing
  - **Resolution**: Made optional - not required for PCB/schematic generation

### What We Learned
- All-variant extraction provides more comprehensive pin data
- Users can access all package types from single table extraction
- Component name is optional for PCB generation (package type, pins, pin counts are critical)
- Clean tables work flawlessly with new all-variants approach
- Messy tables (like 74HC595) are edge cases that may need post-processing

### Tomorrow's Plan
- Test the new all-variants extraction on 74HC595 PDF
- Verify that both SOIC-16 and LCCC-20 variants are extracted correctly
- Update any code that expects single package structure
- Add option to select which package variant to use for schematic generation
- Document the new all-variants behavior in plan.md
- Test pin position calculation with real PDF workflows
- Validate that SOIC and LCCC position calculations are correct

### Completed Today
- ✅ Full end-to-end workflow tested successfully on 74HC595
- ✅ 3D model generated (test_74hc595_full_workflow.glb)
- ✅ PDF extraction → LLM → Package validation → 3D generation works end-to-end
- ✅ Total workflow time: ~39 seconds (9s detection + 8s extraction + 21s LLM + 1s 3D gen)
- ✅ Fixed LLM client parser bug (None value handling)
- ✅ Added environment setup script (setup_env.sh)
- ✅ Java environment working (OpenDataLoader functional)
- ✅ Refactored package definitions to src/package_types/
  - Cleaner module structure
  - Easier to maintain and extend
  - Centralized package type management
  - Won't get "weird" as it grows
- ✅ All imports updated and tested

### Tomorrow's Plan
- [ ]
- [ ]
```

---

## 2026-06-03

### What We Did
- ✅ Fixed the extraction flow so clean pin tables can bypass the LLM through a deterministic parser.
- ✅ Tightened package handling so DFN/WSON/SON-style parts stay dual-row, while true QFN packages stay quad-side.
- ✅ Corrected quad-package pin ordering to match top-view counter-clockwise numbering.
- ✅ Added and updated tests for package detection, package family matching, deterministic parsing, and pin layout.
- ✅ Generated and validated fresh GLBs for DFN, MPU-6000, and QFN-24.
- ✅ Ran a clean batch rerun over all PDFs in `pdfs/` and stored the outputs in `output/batch_pcb2d/`.
- ✅ Confirmed all PDFs were readable; the batch failures were LLM connection issues, not corrupted files.

### Issues Encountered
- OpenDataLoader still fails in this environment because Java is unavailable.
- The harder PDFs still depend on the LLM fallback, so they fail when the API connection is unavailable.
- Some package labels were being flattened too aggressively, which caused incorrect side placement.

### What We Learned
- The main bug was in layout classification, not pin extraction.
- DFN/WSON/SON should be treated as dual-row no-lead packages, not as quad packages.
- QFN-24 top-view counter-clockwise numbering is:
  - 1-6 left
  - 7-12 bottom
  - 13-18 right
  - 19-24 top
- The deterministic parser is strong enough for cleaner tables and should be the first choice before the LLM.

### Tomorrow's Plan
- [ ] Improve offline coverage for more package families so fewer PDFs depend on the LLM.
- [ ] Tighten fallbacks for the PDFs that still need model assistance.
- [ ] Add a few more regression cases for package layout orientation.

## Notes

### Dependencies Installed
- `opendataloader-pdf` (v1.8.1) - Table extraction
- `openjdk@17` - Required by OpenDataLoader

### Current Status
- **Branch**: main
- **Latest Commit**: dc50018 - "feat: Integrate OpenDataLoader for accurate table extraction"
- **Status**: Ready to push
- **Test Success Rate**: 80% (4/5 PDFs)

### Key Files Modified
- `src/chat_bot.py` - Added specialized table extraction prompt
- `src/llm/client.py` - Use table prompt in table-only mode
- `src/main.py` - Auto-detect and enable table-only mode
- `src/pdf_extractor/content_extractor.py` - OpenDataLoader integration
- `.gitignore` - Updated with new patterns
- `plan.md` - Renamed from CLAUDE.md + documented architecture

### Known Issues (Low Priority)
1. Component name detection (returns "Unknown")
2. Package format (SOIC-20-20 → SOIC-20)
3. AMS1117 fails (no table detected)

### Future Enhancements
- Variant selection flag (--variant SOIC-16)
- Table validation warnings
- Cache OpenDataLoader results
- Add table visualization
- Support custom table prompts

## 2026-07-09 — Catch-up (covers 2026-06-04 → 2026-07-09)

The log was not maintained for five weeks; this entry is reconstructed from git history.

### What We Did

**GLB output fidelity (mid/late June)**
- Fixed schematic GLB hierarchy to match the reference `schematic.glb` (ccfbb76) and PCB hierarchy to match the `2d.glb` reference (d3f2e9c, 917888b, d59a139).
- Fixed `boundingBox` to cover the leg area instead of the pin-number text (8d2e892).
- Added per-layer spacing between fab / silk / courtyard body outlines and used `LINE_THICKNESS` for PCB body lines (05188a1, f305f27).
- Added page detector unit tests + benchmarks (5b067a6) and a 9-component schematic test suite with pipeline fixes (dbfac11); test GLBs live in `compare/` and `schematic_tests/noTOC/`.

**Architecture change: dropped OpenDataLoader (2026-07-02)**
- Replaced OpenDataLoader with PyMuPDF for table extraction and added an LLM validation retry loop (765bd64). No more Java dependency — the "Notes" section above and `plan.md` describe the old architecture.
- Consolidated 14 test files into a single `test_suite.py`, all 60 passing (8169801).
- Added `--both` flag to generate schematic and footprint in one pass (a77cdff, 103af4a).
- Added GitHub Actions CI workflow (316040b).

**Dimension extraction from mechanical drawings (2026-07-05/06)**
- Integrated dimension extraction into the footprint builder so real datasheet dimensions (pitch, body size, pad size) override hardcoded JEDEC defaults (996980a).
- Return None when the extracted package type doesn't match the target; skip full page scan when pipeline candidates exist; improved cross-package and legacy-format dimension matching (f276d71, b87af66, 5d68faf).
- Exploration scripts (untracked): `test_dimension_api.py`, `test_tssop_investigation.py`, `compare_dims.py` — testing the Qwen vision endpoint against known JEDEC reference specs.

**Code review remediation (2026-07-07 →)**
- Working through `datasheet-parser-new_review.md`: fail-closed validation + lazy API-key client (ARCH-005, BUG-001), `json_str` init fix (BUG-002), pyproject as single dependency source (CFG-001), `.env.example` template (SEC-003 partial), open PDF once per dimension run (BUG-003).
- **In progress (uncommitted)**: ARCH-006 — `parse_package_type()` now raises `SchematicGenerationError` for unknown packages instead of silently defaulting to DIP; `--force-best-effort` makes the DIP substitution explicit and records it in `validation_errors`.

### Current Status
- **Branch**: main at 1727ef5, with ARCH-006 changes uncommitted in `src/main.py` and `src/package_types/package_geometry.py`.
- Table extraction: PyMuPDF + deterministic parser first, LLM fallback second. OpenDataLoader/Java no longer required.
- Remaining review items: rest of ARCH-001..004, ARCH-007, BUG-004+, SEC items.

---

## 2026-07-10 — Footprint dimension verification against official footprints; pad geometry + extraction fixes

### What We Did

**Verified dimension translation into GLBs**
- Built a measurement flow (trimesh world-space checks, `verify_glb_dims.py`) proving extracted dims do reach GLB geometry: pitch `e`, lead span `E` (with IPC-7351 inset), body length `D` all translate correctly.
- Compared generated footprints per-pin against 6 official footprints (Ultra Librarian `ul_74HC595/`, SnapEDA `ATMEGA328P-PU/`, `MCP3208-CI_P/`, `MM74HC594M/`, `TLO62CDR/`, `ESP32-C3-WROOM-02-N4/` — untracked, third-party): pin grids match exactly (0.000mm on DIP-16s, exact pitch everywhere); remaining deltas are IPC density-level style choices.

**Fixed in `pcb_footprint_builder.py` / `footprint_defaults.py`**
- Pads recentered on the body: `layout_pins()` uses schematic top-margin placement, which mis-centered pad columns by ~4.5mm once real body dims replaced display proportions (`_recenter_pins()`).
- Real pad geometry via `pad_spec`: through-hole = drill + 2×0.35 annular ring (Ø1.53 vs official 1.524); SMD = IPC-7351 rects from b/L with ≥0.2mm clearance clamp. Fixes TSSOP 0.65mm-pitch pads that previously overlapped (fixed 1.25mm circles).
- Fab outline now drawn at plastic body width E1 (new per-family E1/D1 in JEDEC defaults), not lead span E; courtyard computed to enclose body or pads, whichever is larger.

**Fixed dimension extraction short-circuit (74HC595 regression)**
- Root cause: partial text-phase result ({A,e,b} only) ended extraction; vision (which reads the full page-23 table) never ran.
- `extract()` now requires all critical keys (e,E,D,b,L) from text to short-circuit; otherwise vision runs and merges, text values winning conflicts. `_pick_best` → `_merge_candidates` (key-by-key merge across pages, min/max pairs beat singles, foreign package families excluded). Vision failure returns the partial text result instead of None.
- Live result on 74HC595: complete dim set {A,A1,b,D,E,e,L}. Note: extractor found the wide-body (DW) SOIC drawing; D-vs-DW disambiguation needs part-number-aware variant matching (open item).

### Current Status
- Test suite: 104 passing (was 93 at session start); new regression tests include a per-pin comparison against the official `DIP16_300_TEX.kicad_mod` (skips if fixture absent).
- Open items: pad sizing from b_max/L_min (needs min/max preserved through `_flatten`), drill from lead width, targeted retry for missing keys, provenance tagging + extraction eval harness, module packages (ESP32-style) unsupported by design.

---

## 2026-07-12 — Part-number-aware package variant disambiguation

### What We Did
- Fixed the wide-vs-narrow SOIC trap: "SOIC-16" alone cannot distinguish TI's
  D (narrow, 6.0mm span) from DW (wide, 10.3mm span) drawings; the extractor
  previously returned whichever drawing the datasheet had (74HC595: DW only).
- `package_designator_from_part_number()` (part_number_hint.py): derives the
  designator from the orderable suffix (SN74HC595DWR → DW; strips R/T/E4/G4).
- Page filtering by TI drawing code (`DW0016A` → prefix DW) in both the text
  phase and the vision candidate list; codeless pages always pass.
- Lead-span consistency gate (`DESIGNATOR_LEAD_SPAN`): codeless old-style
  "MECHANICAL DATA" pages can still leak the wrong variant, so extracted E
  must match the designator's expected span (±0.8mm) or the override is
  dropped in favor of text/JEDEC defaults. Found via live run: designator D
  initially still received wide dims from a codeless page.
- main.py passes resolved_part_number into DimensionExtractor at both sites.
- Live: DWR → wide dims; D → no override (correct narrow JEDEC defaults);
  no part number → unchanged. Tests 104 → 108.

### Open items
- Pad sizing from b_max/L_min (preserve min/max through _flatten), drill from
  lead width, extraction eval harness + provenance, module packages.

## 2026-07-12 (second session)

### What We Did
- Full-flow verification on 74HC595_TI.pdf (--both, part SN74HC595DWR):
  pin extraction recovered via LLM corrective retry, wide-SOIC dims extracted
  (e=1.27, E=10.325, D=9.9, b=0.41, L=0.835), GLB geometry measured correct
  (pitch 1.270, row span 9.490 = E−L, pads 1.535×0.470, columns centered).
- Found and fixed stale pin metadata: `_build_pin_extras` in
  src/core/pcb_footprint_extras.py hardcoded every SMD pin as a 1.25mm circle
  and every through-hole drill as 0.83, ignoring the computed pad_spec — so
  any viewer reading pinData (not the meshes) showed the old fixed pads.
- inject_pcb_footprint_extras now takes pad_spec + pin_side_map: SMD rect
  pads write pinShape "rectangle" with length/width as X/Y extents (oriented
  by pin side), through-hole pins carry the annular-ring pad diameter and the
  real drill from pad_spec ("drill" added to the through-hole spec), and the
  CopperCirclePad outline "points" trace the real pad shape.
- Live re-run confirmed pinData now matches geometry. Tests 118 → 120.

### Open items
- Unchanged: pad sizing from b_max/L_min, drill derived from lead width,
  extraction eval harness + provenance, module packages.

## 2026-07-12 (third session — batch flow eval)

### What We Did
- Built run_full_flow_eval.py: runs every PDF through `--both`, measures the
  footprint GLB pin grid (count/span/pitch/centering), writes a JSON report.
- Ran it on pdfs/ (31 files) and pdfs/noTOC/ (19 files):
  27/31 and 16/19 produced GLBs; results identical with and without TOC —
  page detection is fully content-based and deterministic.
- 17 datasheets verified correct (all DIPs incl. wide DIP-40, both SOIC
  widths, SSOP, TSSOP, 4 QFNs). Reports: flow_eval_report.json,
  flow_eval_notoc_report.json.
- Diagnosed TPS63060: alphabetical pin table mangled the parse (9 pins),
  "DSC PACKAGE" not in vocabulary so package_detector invented "SOIC" from
  pin count; validation rejected it but the leftover GLB fooled the eval —
  eval now requires validation success, not file existence.
- Fixed + committed (7449a3e): SO-8 -> SOIC alias (longest-prefix +
  letter-guard so SOT-23 stays fail-closed) and explicit pin-count suffix
  in SOT23-8 beating the SOT-23=3 family default. Tests 120 -> 122.

### Open items (priority order)
1. INA219: SOT23 footprint geometry family missing entirely (exposed once
   the validator fix let extraction pass).
2. AMS1117: LLM selected_package_index out of range — weak validation path.
3. Wrong-variant class: lm358 (nondeterministic pin count), NRF24L01 (wrong
   pitch), STM32F103 x2 (wrong spans), ULN2001A (8.5 vs 7.62 span) — variant
   selection needs generalizing beyond TI drawing codes.
4. package_detector._get_default_package invents SOIC from pin count —
   should fail closed (TPS63060 root cause).
5. Backlog: pad sizing from b_max/L_min, drill from lead width, modules.

---

## 2026-07-12 (fourth session — variant selection fixes + lm358)

### What We Did
- ✅ TI designator vocabulary: "DSC PACKAGE" headers name the family
  (DSC/DSG/DRC=WSON, DBV/DCN/DDC=SOT23, ...); ambiguous multi-designator
  headers resolve via the part-number suffix (3000078)
- ✅ Fused "NAME NO." pin-table cells ("L2 10") parse correctly (3000078)
- ✅ Family-consistency gate: extracted dims must match the target family's
  JEDEC geometry (pitch ±25%, span ±40%); catches vision parroting (63e2541)
- ✅ Quad-package centering: top/bottom rows recenter per side — every
  QFN/LQFP footprint previously had ~4mm offset rows (63e2541)
- ✅ Through-hole DIP spans snap to the JEDEC 300/600-mil grid (b0cc2ef)
- ✅ lm358 multi-package pin table: pin numbers now read from the column
  whose header matches the inferred family, not the first numeric cell
  (the LCCC column gave 16-20 pins for an 8-pin part); V+/V– recognized
  as rail labels with power/ground functions (5e448eb)
- ✅ Full batch re-eval (flow_eval_v2_report.json): 28/31 PASS, suite at 134

### Issues Encountered
- The batch eval processed lm358 before the fix landed; re-ran it and
  patched the report entry (verified deterministic: 8 pins, 7.62/2.54)
- src.main's positional `output` is a file prefix, not a directory

### What We Learned
- Multi-package datasheets print one pin-number column per package group;
  "first cell with numbers" is wrong whenever LCCC/CDIP variants exist
- ADXL345 classifies as BGA-14 (correct 3x5mm body) but the builder has no
  real LGA/BGA pad grid — generic two-row fallback invents the pitch

### Tomorrow's Plan
- [ ] Remaining FAIL is TVS diode (SMB package) — fails closed by design;
      decide whether discrete 2-terminal packages are in scope
- [ ] LGA/BGA pad-grid support (ADXL345)
- [ ] Backlog: pad sizing from b_max/L_min, drill from lead width,
      dims provenance tagging, SnapEDA regression for remaining downloads

---

## 2026-07-13 — Schematic flow verification + production gates

### What We Did
- ✅ Schematic flow audit: generated GLBs had ZERO frontend extras — the
  platform reference carries id/side/pinLength/pinName per pin group,
  pinNumber on text, name on pinName, BodyLine points, label values.
  New src/core/schematic_extras.py injects all of it post-export (75711df)
- ✅ Eval now validates schematic CONTENT (pin count, names, contiguous
  numbering, sides, bodyline, labels), not just file existence
- ✅ Production gate 1: BGA/LGA/LCCC footprints fail closed instead of
  rendering invented perimeter geometry; schematic stays valid (ff7bb16)
- ✅ Production gate 3: dimension provenance — dims_source tag from the
  extractor ("text"/"vision"/"text+vision"), resolved by the builder
  ("jedec_default"/"unverified"), written as dimsSource on the footprint
  Package root (b837997)
- ✅ v3 full-corpus eval: 28 PASS + ADXL345 correctly refusing footprint
  + TVS fail-closed + 2 junk fixtures = 31/31 expected outcomes; all 29
  schematics pass content checks. Suite at 138 tests

### What We Learned
- Side codes in the platform reference: 0=left, 1=top, 2=right, 3=bottom;
  quad pins number counterclockwise from top-left
- The reference merges same-name rails into one leg (GND id ["8","22"]);
  we emit them separately — cosmetic gap, wires still attach
- src.main's positional output arg is a file prefix, not a directory

### Remaining production gates
- [ ] Gate 2: ground-truth regression vs official SnapEDA footprints
- [ ] Gate 4: pad sizing from b_max/L_min (IPC-7351), not nominals
- [ ] Then: wider corpus (100+ datasheets, more vendors), service wrapper,
      LLM version pinning + telemetry (platform side)

---

## 2026-07-13 (second session — gates 2 & 4, ground truth, drill sizing)

### What We Did
- ✅ Gate 2: run_ground_truth_eval.py — generated footprints vs official
  SnapEDA/UltraLibrarian .kicad_mod references (per-pin deltas, pitch,
  row spacing, drill, pad size). 5/5 MATCH, worst pin delta 0.15mm (e08783f)
- ✅ Fixes it surfaced: impossible lead spans dropped ((E−E1)/2 > 2.2mm —
  TL072's narrow body merged with a wide-body span); wide-SOIC span only
  for ≥14 pins (JEDEC MS-013); MCP3204/3208 device-column selection by
  part number; page detector knows Microchip "Definition" headers
- ✅ MCP3208 nondeterminism (14 vs 16 pins) root-caused: pin table never
  reached the deterministic parser (detector missed the header), LLM
  improvised from prose. Now 16 pins/7.62mm on 3 consecutive runs
- ✅ Gate 4: pads sized from IPC tolerance extremes — _flatten preserves
  b/L min/max; pad width from b_max, length from L_max (baca653)
- ✅ Drill from lead width per IPC-2222 (lead diagonal + 0.25 clearance,
  floored at 0.83mm); drawn hole uses computed drill (6faef51)
- ✅ v4 full-corpus eval: 27 PASS, ADXL345 expected-refusal, TVS
  fail-closed, 2 junk fixtures; all 29 schematics pass content checks.
  Suite at 143 tests

### Issues Encountered
- ⚠️ OPEN REGRESSION: STM32F103X6 footprint now refused. The new
  "definition" detector pattern exposed STM32's pin table (BGA100 |
  LQFP48 | LQFP64 | LQFP100 columns) to the deterministic parser; with
  no resolvable column it mixed numbering schemes into "BGA-25".
  Fix half-applied: _has_multiple_package_columns() added to
  deterministic_table_parser.py — still needs wiring into
  _parse_table_rows (return None when ambiguous), tests, STM32 rerun

### What We Learned
- Vendor references anchor footprints differently (origin vs pin 1):
  ground-truth comparison must centroid-normalize both pad sets
- Through-hole pin 1 pinData has rect keys (pin-1 marking), classify
  through-hole by innerDiameter, not outerDiameter
- Every detector-vocabulary change can expose new tables to the
  deterministic parser — always rerun the full corpus after

### Next
- [ ] Finish STM32 ambiguous-column fix + suite + corpus rerun
- [ ] Then: rail merging (GND id ["8","22"]), discrete-package scope
      decision, platform-side service wrapper / LLM pinning

---

## 2026-07-14 — Engineering review + production task list execution

### What We Did
- ✅ Full two-phase engineering review → datasheet-parser-new_review_2026-07-14.md
  (1,115 lines, 10 sections, 7 diagrams, 45 issues: 8 High / 19 Medium /
  18 Low; overall 6/10 "strong core, unhardened shell"). Key finds:
  PyMuPDF AGPL vs MIT (CFG-002), EOL Python 3.9 (CFG-001), untested
  LLM/vision layer (COV-001), unauthenticated vision endpoints (SEC-004).
  API-key finding withdrawn per Nani.
- ✅ Created 14-task production list (scope: no service wrapper, no
  external-call work, no licensing/docs — per Nani's deferrals)
- ✅ Task 1: wired _has_multiple_package_columns guard — unresolvable
  multi-package tables yield no deterministic candidate (dbcc142);
  STM32F103X6 recovered (48 pins, 8.9mm ring); lm358/MCP3208 unaffected
- ✅ Task 2: pushed all 36 local commits to origin (now current)
- ✅ Task 3: deleted dead code — main.py.backup, schematic_builder.py.bak,
  main_layout.py (508-LOC duplicate CLI; --layout-mode lives in main.py)
- ✅ Task 4: removed ~1.8GB working-tree clutter (two venvs, 16 loose
  GLB/STL, stale output dirs). Kept 2d.glb + schematic.glb (load-bearing
  references). Benchmark fixtures were untracked and lost in the sweep —
  reconstructed from documented schema, now git-tracked (353e7c1)
- ✅ Task 14: STM32 wrong-variant fix — ST order codes decode pin count
  (STM32F103[R]BT7→64); wired into prompt hint, validator hard error,
  and variant-selection priority (0391c9b). RBT7 3/3 runs at 64 pins
  (was 100 in v5); X6 pinned to STM32F103C6 in eval, 2/2 at 48.
  Eval gained per-PDF EXPECTED_PINS so wrong variants FAIL.
- ✅ Task 5: tools/ dir for the 4 real harnesses; deleted test_scripts/
  (26 files) + 4 superseded ad-hoc scripts + setup_env.sh (0daea90)
- 🔄 Task 6 (in progress): eval reports + dimension caches → eval_output/,
  6 vendor footprint folders + compare/ → tests/ground_truth/; paths
  updated in tools/run_ground_truth_eval.py; verification rerun pending
  (4/4 MATCH before interruption; TL072 pad size now EXACT vs SnapEDA)

### Issues Encountered
- v5 corpus eval: X6 failed in-eval but passed direct runs — exposed
  LLM-path variant nondeterminism (root-caused and fixed in task 14)
- Eval blind spot found: RBT7 shipped a 100-pin footprint marked PASS
  (grid-consistency checks can't see wrong variants) → EXPECTED_PINS
- rm -rf of "clutter" destroyed untracked benchmark fixtures → rule:
  NEVER delete output folders; move only (saved to memory per Nani)

### Suite / eval state
- 147 tests passing; corpus eval v5: 27 PASS + expected outcomes;
  ground-truth: 5/5 MATCH (TL072 pad geometry now exact)

### Remaining tasks (7-13)
- [ ] Error/exit-code contract in main.py; print→logging
- [ ] LLM/vision layer mock tests; CI hardening; nightly eval smoke
- [ ] Python 3.11/3.12 migration; Dockerfile

## 2026-07-19

### What We Did
- ✅ Reran the 3 repaired corpus files: DF10S now correct (4/4, both GLBs),
  BQ25570RGRT correct (20/20), MB6S correctly fails closed (no pin table).
- ✅ Round-2 fixes implemented via TDD in worktree `fixes-round2`
  (branch `worktree-fixes-round2`, draft PR #1, 2 commits):
  1. filename hint survives underscores (4_MB6S-E3-80 → whole token, not "E3-80")
  2. F1 pin-name grounding: extracted names must exist in source text/tables;
     fabrications become retryable validation errors
  3. F2 sibling-device gate: extracting AB1233 when target is AB1234 = error
  4. F3 family/grid: designators are ground truth (PWP/RGR/RGZ/RHA/RHB/RHL/RTE
     added); MSOP/SSOP labels survive normalization (0.65mm grids); µMAX→MSOP;
     dual-row families refuse 4-sided vision layouts
  5. F4 page detector: whole-page heading scan, TOC de-scored via dot-leaders,
     position bonus excludes only cover/tail; fixed wrong benchmark ground
     truth (sn74hc595 expected page was the TOC)
  6. F7 root cause: odd pin counts split ceil/floor (SOT-23-5 = 3+2);
     symmetric n//2 was silently dropping the last pin
  7. F8: footprint GLBs validated at temp path, promoted only on success
  8. eval: 20 corpus stems in EXPECTED_PINS + expected-refusal set
- ✅ Suite: 172 passed, 1 skipped (25 new tests, all watched RED first)
- ✅ Corpus 1–20 rerun twice: 9→11 PASS + 5 correct refusals = 16/20;
  zero silently-wrong outputs (was ~4). New passes: SN6501 (5-pin),
  TPS2514 (6-pin SOT-23), MMBD3004CA (3-pin); MAX845 grid 1.27→0.65.
- ✅ Boss directive mid-session: NO code changes, tests only. Ran the 20 new
  PDFs (stems 21–40) added to datasheets/: 21–30 = 5/10 correct;
  31–40 = 2/10 correct. All verdicts document-verified.
  Full report: eval_output/datasheets_run_report.md (committed on the branch).

### Issues Encountered
- TPS23751×2 + SN65LVDS104: correct family/grid now but read the 20-pin
  column instead of 16 (TI multi-package column anchoring gap).
- SN6505A: page detection still feeds wrong pages; grounding blocks the
  resulting hallucination → fails closed.
- 21–40 exposed three systematic gaps: (a) order-code decoding is TI/STM32
  only (Atmel MMU, ON DMTT, NXP CAL/VMP/VMC, even TI's DRB missing);
  (b) big-MCU pinouts are figures → LLM recites from memory, grounding
  provably catches it (blocked pins don't exist on the devices) but no
  output; (c) NO module detector: ESP32-C3-WROOM shipped a 20-pin QFN-style
  footprint for an 18-pin castellated module with exit 0 — the only silent
  error of the day.
- Corpus intake: 31 and 32 are byte-identical files.
- Flagged tech debt: hardcoded "6050" branch in
  deterministic_table_parser.py:506 violates the general-parser rule.

### What We Learned
- The grounding gate catches real hallucinations verifiably: every blocked
  pin name on 29–32 was provably absent from the device (e.g. 'VCC' on an
  AVR-Dx, RC5 on MC710A).
- Wrong ground truth exists in benchmarks too — the old TOC bias had been
  recorded as an expected pinout page.

### Tomorrow's Plan
- Round 3 candidates (pending Nani/boss approval): module/out-of-scope
  detector; vendor order-code decoding (NXP/Microchip/ON + TI DRB);
  TI multi-package column anchoring; diagram-aware extraction for big MCUs;
  remove the 6050 hack; SN6505A page detection.

---

## 2026-07-19 — New datasheets/ batch: full-flow eval + content-level quality analysis (covers 2026-07-17 sessions too)

### What We Did
- ✅ Ran the full flow (`--both`) over a new `datasheets/` folder supplied by
  Nani. The folder was swapped mid-day on 07-17: first set of 5 (Quectel
  UC200A-GL, BAS4002A, BQ25570, LPS4018, W25Q128JV → 2 PASS / 3 fail-closed
  on unsupported packages LCC/SOT143/SMD), then the current set of 10
  (LS7641, CDBHM1100L, MB10S, MB6S, SN6501-Q1, SN6505A, TPS2514, BQ25570,
  BQ500211, BQ500511A). Harness result on set 2: 6 PASS / 4 FAIL
  (eval_output/flow_eval_datasheets2_report.json); GLBs persisted to
  output/datasheets_run_2026-07-17/
- ✅ 9_BQ25570RGRT.pdf was a truncated download (exactly 1840 KiB, 0 readable
  pages) — replaced with a clean TI copy (original kept as *.pdf.corrupt),
  re-ran fine
- ✅ Content-level quality analysis: dumped all pin names/numbers/sides/pad
  positions from the 16 GLBs and compared pin-by-pin against the datasheet
  pin-configuration + mechanical pages →
  **eval_output/quality_analysis_2026-07-19.md** (scoreboard + findings
  F1–F9 + prioritized recommendations)
- ✅ Root-caused all four failures/miss-classes via verbose re-runs

### Key results
- Fully correct schematic pins: 4/8 (LS7641 14/14, bq25570 20/20,
  bq500211 48/48, bq500511A 40/40 — big QFNs flawless incl. multi-pin rows)
- Fully correct footprints: 1/8 (LS7641). QFN trio correct grids but no
  thermal pad; MB10S/TPS2514 got SOIC-default grids (wrong pitch);
  2 of the harness's 6 PASSes are content-level failures it cannot see

### Issues Encountered (root causes confirmed)
- **MB6S fabrication (worst)**: only detected page is the land-pattern page
  (no pin table exists on a 4-terminal bridge); LLM sent mechanical text
  fabricated a self-consistent 64-pin device that passed all structural
  checks; identical re-run refused instead → nondeterministic garbage-PASS.
  Also: filename hint parser turned MB6S-E3-80 into bogus part hint "E3-80"
- **TPS2514 wrong variant**: extracted the TPS2513 table (pins 3/4 DP2/DM2
  vs real N/C); order-code pin-count anchoring (0391c9b) can't disambiguate
  two 6-pin variants — needs part-number match on table captions
- **SN6505A refusal = page-detection miss**: real pin page (p3) never a
  candidate — `_is_likely_heading` scans only first 10 lines and p3 opens
  with revision-history spillover; position score 0 (p3/43 < 20%); the TOC
  page scored 3 instead (its "Pin Configuration…" entry is in the first 10
  lines) and the content filter fed the LLM 6 KB of TOC. Same family as the
  July-14 noTOC work
- **SN6501**: `GND | 4,5` table row not expanded (pin 5 dropped) + vision
  dims returned pads at ±87.5 mm; leg-count validator correctly rejected the
  footprint but the invalid GLB was still written first (known
  write-before-validate issue)
- **MB10S vs CDBHM1100L inconsistency**: same physical MBS bridge package —
  onsemi's "SOIC4 W" alias slipped through as SOIC (wrong 1.27 grid, real
  is 2.54 pitch / ~6.5 span per CASE 751EP), Comchip's "MBS" failed closed

### Recommendations filed in the report (priority order)
1. Ground extracted pin names against source-page text (kills fabrication)
2. Variant selection by part-number match on table captions
3. Expand comma/range pin-number lists in table rows
4. Package-family gate before applying JEDEC default grids
5. QFN thermal-pad support; 6. filename part number as component-name prior;
7. vision-dims sanity bounds + don't write GLB pre-validation;
8. add the 10 new stems to EXPECTED_PINS in run_full_flow_eval.py

### Next
- [ ] Continue running tests on further datasheet batches (per Nani)
- [ ] Pick up recommendations above as fix tasks

---

## 2026-07-19 (second session) — Batch 3 (10 new PDFs), 20-part corpus report, unknown-package LLM probe

### What We Did
- ✅ Verified the 10 new PDFs (#8, #12–20) against Nani's DigiKey line-item
  list. Caught: 17_DF10S is a **wrong document** (scanned TUK keystone-panel
  brochure, no text layer); 8_MMBD3004CA is the Diodes Inc datasheet for a
  Taiwan-Semi orderable; 14/16 TPS23751PWP(R) are byte-identical
- ✅ Ran batch 3 through the full flow: 5 PASS / 5 fail-closed
  (eval_output/flow_eval_datasheets3_report.json; GLBs in
  output/datasheets_run_2026-07-19/)
- ✅ Pin-by-pin verification of the 5 passes → consolidated 20-part corpus
  report: **eval_output/quality_report_all20_2026-07-19.md** (supersedes the
  batch-1 analysis as corpus summary)
- ✅ Temporary unknown-package experiment (NOT implemented; /tmp only):
  asked the integrated LLM to classify unknown package "MBS" and supply
  build geometry. Result: family+pin-count mapping reliable (6/6 trials
  → SOP/TO-269AA, 4 pins) but dimensions unreliable BOTH from world
  knowledge (generic SOIC numbers) and from datasheet text (3 trials,
  3 different wrong dim sets, one self-labeled "high confidence").
  DimensionExtractor returned None on the same PDF (vision scan probe
  paused). Conclusion: LLM may be used for family mapping only; numbers
  must come from the vision/text dims path
- ✅ Determinism data point: byte-identical inputs #14/#16 → pin-for-pin
  identical outputs (weakens the MB6S "nondeterminism" theory; that file
  was externally swapped after the eval — noted as caveat in the report)

### Key corpus numbers (details in the report)
- Schematics fully correct: 8/12 parts with output (the 5 TI QFN/PMIC parts
  148/148 pins); footprints fully correct: 1/12 (LS7641)
- 6 of 8 refusals were correct fail-closed; harness scored 3 wrong-content
  parts as PASS (MB10S, TPS2514, TPS23751×2 — structural checks can't see
  wrong names/columns/grids)

### PRIORITIZED FIX LIST (agreed basis for upcoming work)

**P0 — quick wins (minutes–1h each)**
- [x] P0.1 Add all 20 corpus stems to EXPECTED_PINS in
      tools/run_full_flow_eval.py (values in report §4.7) so wrong-variant/
      wrong-count outputs FAIL instead of PASS — DONE 07-19, verified:
      14_TPS23751PWP re-run now FAILs with "expected 16 pins, got 20"
      (3rd identical extraction — wrong-column bug is deterministic)
- [ ] P0.2 Corpus intake check in the eval harness: warn when the filename
      part number does not appear in the PDF text, when a file is a byte-
      duplicate, or when a PDF has no text layer (catches DF10S/MB6S-class
      wrong files before burning LLM runs)
- [ ] P0.3 Component-name prior: use CLI --part-number / filename stem as
      PackageValue fallback instead of "Unknown"/app-figure names
      (fixes 5×Unknown, MSP430G2001, PWM1, TPS23752 labels)

**P1 — top wrong-output causes (each verified against named parts)**
- [ ] P1.1 Pin-name grounding gate: every extracted pin name must occur in
      the source page text, else refuse (kills MB6S-class fabrication and
      wrong-file extraction; ~src/llm/client.py validation +
      content pass-through). Acceptance: DF10S-style wrong file refuses
      with a grounding error, not "no relevant pages" luck
- [ ] P1.2 Part-number-driven column/variant/drawing selection: match part
      number against pin-table column headers (TPS23751 vs TPS23752,
      TPS2513x vs TPS2514x, LVDS104 vs 105) and package-drawing codes
      before pin-count heuristics; also fix the filename hint parser that
      turned "MB6S-E3-80" into bogus hint "E3-80".
      Acceptance: 7_TPS2514 pins 3/4 = N/C; 14_TPS23751 = 16 pins;
      15_SN65LVDS104 footprint from PW/TSSOP drawing
- [ ] P1.3 Family/grid consistency gate at build time: layout family must
      match the package string (TSSOP can never be quad), and JEDEC default
      grids keyed by family+pin count with mismatch → refuse.
      Acceptance: 13_MAX845 gets MSOP 0.65 grid or refuses (never SOIC
      1.27); 14_TPS23751 never gets a QFN grid; 3_MB10S refuses or 2.54

**P2 — high-value correctness**
- [ ] P2.1 Page detector: scan headings beyond the first 10 lines,
      de-score TOC/revision-history pages, soften the 20–70% position
      window. Acceptance: 6_SN6505A extracts its 6 pins
- [ ] P2.2 QFN thermal pad (EPAD) generation from pin-table PAD row +
      package code. Acceptance: bq25570/bq500211/bq500511A/bq51050B
      footprints include the exposed pad (bq500211 lists it as pin 49)
- [ ] P2.3 Rectangular QFN bodies: RHL (3.5×4.5) must not get the square
      default grid. Acceptance: 12_BQ51050B pad grid matches RHL
- [ ] P2.4 Multi-pin table rows expanded consistently ("GND | 4,5").
      Acceptance: 5_SN6501 schematic has 5/5 pins

**P3 — robustness / hygiene**
- [ ] P3.1 Vision dims sanity bounds (body 1–60mm, pads within body+margin)
      + never write GLB before hierarchy validation (SN6501 ±87.5mm,
      leftover invalid file)
- [ ] P3.2 Discrete/bridge policy: either dedicated terminal-marking
      extraction (+ , − , ~) with MBS/MBF/DFS/HD package geometries, or an
      explicit documented out-of-scope refusal like modules. Candidate
      assist: LLM family-mapping fallback (probe showed mapping reliable,
      dims not) feeding the existing dims path — decision needed
- [ ] P3.3 Bridge-name semantics guard (3_MB10S "A1,A2,K,K") — subsumed by
      P3.2 if discretes go in scope
- [ ] P3.4 Re-download correct 17_DF10S (onsemi) and optionally the TSC
      MMBD3004CA-RFG datasheet; re-run both

### Next
- [ ] Execute P0 batch, then P1.1 → P1.2 → P1.3 with corpus re-runs after each

---

## 2026-07-29 — Fail-open flip, full ground-truth answer key, first accuracy number + GLB hierarchy audit

### What We Did
- ✅ **Fail-open flip (PR #13, merged to main).** Inverted the validation policy: gates
  now emit a watermarked best-effort GLB (exit 3) instead of refusing (exit 1) when pin
  data exists. exit 1 is now reserved for genuinely no-extractable-pins inputs.
  - Added `--strict` flag (default off) + `_resolve_best_effort(force, strict) = force or not strict`
    in `src/main.py`; replaced all 4 `args.force_best_effort` call sites with the effective value.
  - **GLB coverage jumped 38/122 (31%) → 116/127 (91%).** Full suite green (~241 tests).
- ✅ **PR cleanup.** Determined only #12 (reference-design pattern removal) needed merging;
  closed stale #5/#3/#2 (would have reverted Fixes 4/5/9/10/11). Merged #12. main now has
  all fixes + fail-open.
- ✅ **Built a complete, independent ground-truth answer key** (5 parallel worktree subagents).
  `EXPECTED_PINS` in `tools/run_full_flow_eval.py` grew 20 → 174 entries (27 pdfs/ fixtures +
  147 corpus parts; 144 high-conf + 3 med). Method: derive true pin count from the ORDERED
  part's package (suffix + ordering table) + printed "N-lead" wording — deliberately NOT by
  counting pinout rows (keeps it independent of the parser). Zero conflicts with all 30
  earlier hand-verified values. Committed on branch `ground-truth-answer-key` → **PR #14 (open)**.
- ✅ **First real accuracy measurement:** 78 correct / 33 wrong / 16 no-GLB →
  **70% (78/111) among gradable GLBs, 61% (78/127) of all scored.** Coverage is great but
  ~30% of produced GLBs have the wrong pin count. Wrote `docs/pin-count-accuracy-bugs.md`
  (33 defects in 5 classes A–E).
- ✅ **GLB hierarchy audit (today's session close).** Ran the repo's own
  `validate_pcb_footprint_hierarchy` over every produced GLB, ignoring pin count (graded
  separately) to isolate tree SHAPE:
  - Footprint GLBs: **105/105 PASS** (68 TH / 37 SMD, correct per-pin node sets, sequential legs).
  - Schematic GLBs: **116/116 PASS** structural (all pins `[leg, pinPoint, text, boundingBox, pinName]`).
  - 116 schematics vs 105 footprints is **by design**: `flag_module_footprint` suppresses the
    footprint for 11 module/grid-array parts (ESP32, MKL, MAX-M10S, UC200, LSM6DSO32…) because
    a chip-package footprint built from a module pin table is silent-wrong.

### Issues Encountered
- **Spurious bg "exit 0":** early background full-suite runs reported success with empty output;
  synchronous re-run revealed `test_cli_exit_code_contract` actually failed (foo.pdf now exit 3,
  not 1). Fixed the test to reflect the new contract. Lesson: verify by real re-run, not bg rc.
- **AVR128 subagent stall** during corpus run (child 0% CPU 8+ min, hung LLM call). Killed just
  the child → parent harness auto-advanced (recorded exit -15). Built a watchdog to auto-kill
  stalls (0% CPU >180s). PC also slept mid-run; process resumed. 5 network-flaky parts recovered.
- **git cherry false-positives:** flagged stale PR branches as "not in main" though content was
  already merged under different SHAs; confirmed via actual diffs + grep of main.
- **Data-quality bug:** `52_PIC16F1512` corpus PDF is the WRONG document (an LCD-clock demo guide).

### What We Learned
- Coverage and accuracy are separate axes: fail-open fixed coverage (31→91%) but exposed that
  ~30% of GLBs carry the wrong pin count. Hierarchy is a THIRD axis — and it's 100% clean, so
  a wrong part (e.g. INA228 with 16 legs instead of 10) is still a well-formed 16-leg tree.
- The 33 accuracy defects cluster into systematic bugs, not noise: Class B small-IC over-count
  (10→16 on INA228/238, L4984D, L6564T — likely ONE root cause), D wrong-variant, C diode/tab
  off-by-one, A big diagram-only MCUs (need vision path), E modules/near-miss.
- Projected trajectory: B → ~79%, +C+D → ~86%, +A(vision) → ~93%+.

### Tomorrow's Plan
- [ ] Merge PR #14 (ground-truth answer key).
- [ ] **Class B** — diagnose the `10→16` small-IC over-count (highest-volume, likely one root
      cause, low risk); come back with a diagnosis + plan before touching parser src/.
- [ ] Then Class D (ordered-suffix → variant), Class C (tab/pad not a signal pin).
- [ ] Fix corpus data bug: replace the wrong `52_PIC16F1512` PDF.
- [ ] Class A vision path (Fix 8 / Option D) — also unblocks the ~11 no-GLB parts.

## 2026-08-02 — Two pin-count accuracy fixes (NC-padding trim + revision-history TOC) → PR #15

### What We Did
- ✅ **Corpus re-run diff (07-30 → 07-31): 75 → 81 PASS (+6), but mostly NOISE.**
  Only 18 of 81 passes are fully validated; the other 63 are correct-count-but-watermarked
  (fail-open). 12 parts flipped, in BOTH directions — the signature of LLM run-to-run variance,
  not a code effect. Lesson: **a single corpus run's score can't confirm a fix** (±6 noise ≈ the
  "gain"). Trust deterministic unit + end-to-end tests, not one run.
- ✅ **Investigated the 3 PASS→FAIL regressions by re-running each 3×.** Result was
  DETERMINISTIC, not noise: `TPS51100` → 20 (should be 10) ×3, `MCP101-460` → 8 (should be 3) ×3,
  `NCP5623` → 12 (correct) ×3. So NCP5623 was the noisy one (now fine); the other two are real,
  repeatable bugs. Corrected my earlier "it's all noise" claim.
- ✅ **Root-caused both real failures (systematic-debugging) — THREE different causes, not one:**
  - **TPS51100** — the system *had the right answer and threw it away*. Deterministic table parser
    returned `None` (pinout filter stripped `MSOP`/`HVSSOP` so `_infer_family` failed; also its
    pin-label regex caps names at 6 chars, dropping 7-char `VDDQSNS`), so it fell to the LLM. The
    LLM read the 10 real pins correctly, then **fabricated 10 `NC` pins (11-20)** and invented a
    `QFN-20`. The grounding gate missed it because `NC` appears in the text. The ordering table
    correctly grounded `HVSSOP, 10 pins` and reconciliation DETECTED the 20≠10 mismatch — but
    fail-open shipped the wrong 20-pin model anyway.
  - **MCP101-460** — **unreadable PDF**: both pdfplumber AND PyMuPDF return garbage (embedded
    fonts have no Unicode/ToUnicode map). The consistent "8" is a guess off unreadable input, not
    a real read. Separate, harder track (needs OCR/vision fallback or garbled-text refusal).
  - **NCP5623** — genuine run-to-run noise; no action.
- ✅ **Fixed TPS51100 (defense-in-depth at the reconciliation layer), `src/main.py`.**
  `_reconcile_ordered_nc_padding`: when the ordering table grounds a smaller authoritative pin
  count and the *excess* pins are all NC, drop the surplus padding (highest-numbered NC first) to
  match ground truth; also re-suffix the type (`QFN-20`→`QFN-10`). Conservative — only removes
  no-connect pins, only when they reconcile EXACTLY; real signal pins still fail closed. Wired
  into `_enforce_ordered_pin_count`. **General, not corpus-tuned** (trusts the datasheet's own
  ordering table; NC-padding is a common LLM fabrication mode).
- ✅ **Also landed the earlier SN6505A page-detector fix** (`page_detector.py`): revision-history
  dot-leader lines no longer trip the TOC veto that stole the real "Pin Configuration" heading
  bonus. Only an explicit "Table of Contents" title page is vetoed now.
- ✅ **Verified:** 3 new regression tests (NC-trim + guard against trimming real pins + revision-
  history heading bonus) RED→GREEN; full suite green; **end-to-end** TPS51100 through the real
  ordering-table grounding trims 20 → 10 correct pins (all NC padding removed).
- ✅ **Committed `c09c40a` on `fix/pin-count-nc-padding-and-revision-toc`; opened PR #15 → main.**
  main untouched, still in sync with origin.

### What We Learned
- **Result: TPS51100 goes FAIL → PASS-degraded** — correct 10-pin count, but still watermarked
  because the LLM's package *shape* (QFN vs real HVSSOP/SOIC) is wrong. Geometry family was
  deliberately NOT faked; turning degraded→validated (family→geometry) is a separate step.
- **The dominant refusal/accuracy story is confidence, not coverage:** only 18/127 come out fully
  validated. Many "passes" are correct-but-unverified because the system detects its own error
  (ordering-table reconciliation) but fail-open ships it anyway. Acting on that ground truth
  (like this NC-trim) is the lever to convert degraded → correct.

### Tomorrow's / Next Plan
- [ ] Get PR #15 reviewed/merged.
- [ ] TPS51100 family→geometry (QFN→HVSSOP) to move it from degraded → validated.
- [ ] MCP101 broken-font track: detect garbled text (both extractors fail) → OCR/vision or clean refusal.
- [ ] Consider pinning extraction to temperature 0 so before/after corpus diffs reflect code, not noise.

## 2026-08-02 (second session) — pin-number grounding (PR #16), seed dead-end, Class B split

### What We Did
- ✅ **Merged PR #15** (NC-trim + SN6505A) to main.
- ✅ **Built pin-number grounding — PR #16, merged.** New `src/pdf_extractor/pin_grounding.py`:
  `build_pin_number_index(content.tables)` (the pin NUMBERS the datasheet's own table rows print,
  reusing deterministic_table_parser helpers) + `drop_ungrounded_pins(pin_data, index)`. Wired into
  `main.extract_pin_data` after normalize, before validation. Catches NC-padding fabrication
  **without needing an ordering table** — grounds against the pin table itself.
- ✅ **Parallel-agent workflow (dispatching-parallel-agents skill).** Split the feature into
  non-conflicting streams: Agent A built the module + tests (new files only), Agent B did read-only
  false-positive de-risking, I integrated (main.py wiring). **Agent B caught a real bug pre-commit:**
  the first number-only rule would have dropped **16/48 real pins on STM32L031** and **23/48 on
  AVR128DA48** (multi-package tables → incomplete index). Hardened the rule in response:
  **only ever drop a pin that is BOTH no-connect (NC/DNC) AND absent from any table row** — so index
  noise can only MISS a fabrication, never drop a real signal pin. Verified: STM32/AVR/INA228 drop 0
  real pins; TPS51100 still caught (20→10). 17 new unit tests; full suite green.
- ✅ **Seed experiment (determinism) — DEAD END.** Temperature is already 0 (Fix 10). Tested the
  backend directly: same extraction request x3 with `seed=42` produced 3 DIFFERENT outputs;
  `system_fingerprint=None`. `fastchat.ideeza.com` does NOT honor `seed`. Conclusion: stop chasing
  API-level determinism; rely on grounding (correctness despite wobble) + multi-run majority for
  measurement.
- 🔎 **Class B (10→16 over-count) diagnosis — it's TWO bugs, not one:**
  - **INA228/INA238:** deterministic ordering table DOES match → VSSOP, 10 pins. INA228 now reads 10
    (5 signals VCC/SCL/SDA/ALERT/GND + 5 NC). INA238 read **8** (under-count). Our NC-trim only trims
    DOWN, so it can't fix an under-count; the pipeline already DETECTS 8≠10 via
    `_enforce_ordered_pin_count` but fail-open ships the 8. Fix = honor the grounded count (pad up
    to the provably-NC pads).
  - **L4984D/L6564T:** NO deterministic ordering match; number-grounding actively over-trims them
    (index incomplete → 6/5). These need the LLM ordering fallback / suffix decoding + the guard below.

### Issues Encountered / Open
- ⚠️ **Grounding false-drop on INCOMPLETE index (found via Class B diag).** When the table parser
  captures only part of the pin table (L4984D index `[3-8]`, L6564T `[6-10]`), real NC pins outside
  that range get dropped (→ 6/5, should be 10). These parts were already wrong (16), so not a fresh
  eval regression on them — but it could hit a previously-correct part. Planned guard: **only drop an
  ungrounded NC pin whose number is GREATER than max(index)** (true trailing padding).
- ✅ **Blast-radius sweep DONE (read-only, 148 parts): PR #16 did NOT regress live main.**
  Index classification: 95 SAFE-empty, 39 SAFE-covers, 14 AT-RISK. Of the 14, **13 were already
  FAIL/DUP** (big multi-package/module parts: dsPIC×3, MKL×3, AVR, ESP32, NRF9160×2, PIC16F871) —
  no fresh regression, and they're signal-pin-heavy so grounding barely touches them. Only ONE
  was-correct part flagged at-risk (`85_IS82C59AZX96`, prev PASS/28, index only `[14,28]`) — and a
  real run confirmed it has **0 NC pins → grounding drops nothing → stays 28**. So the guard is a
  calm FOLLOW-UP, not a hotfix. (Sweeping first was the right call.)

### Next Plan
- [ ] Add the trailing-NC guard (drop ungrounded NC only when number > max(index)) as a follow-up;
      TDD + verify vs TPS51100 (still caught) and L4984D/L6564T (no over-trim). Not urgent.
- [ ] Class B, INA-type: enforce the grounded ordering count (pad up missing NC to reach 10).
- [ ] Class B, L-type + TPS51100 family→geometry; MCP101 broken-font track (unchanged).

## 2026-08-03 — 3D component-body model layer (research → Milestone 1, Milestone 2 start)

### What We Did
- ✅ **Multi-agent research → architecture doc.** Ran 6 parallel subagents (pipeline audit,
  physical-package data model, current 3D/GLB generation, OSS CAD-tool selection, package-modeling
  conventions & reusable libraries, validation strategy), reconciled the two real tensions
  (origin convention; generator licensing), and wrote **`docs/3d-model-generation-architecture.md`**
  (full 12-part plan). Key findings: the system is already a cadquery/OCCT B-rep pipeline extracting
  the JEDEC dims a body needs (A, A1, b, D, E, E1, e, L) in mm/+Z-up/origin-at-centre; **STEP export
  is basically free** (`Assembly.export`); **`A`/`A1` were extracted but discarded** by the footprint
  path; **stay on CadQuery** (Apache/LGPL-with-exception, no GPL); clean-room our own templates using
  KiCad generator params as reference (their code is GPL/LGPL/AGPL).
- ✅ **Milestone 1 — SOIC gull-wing vertical slice, committed (`fd31bf9`, branch
  `feat/3d-body-model-milestone-1`).** New `src/model3d/` package, all test-first (TDD):
  `spec.py` (Body3DSpec + build_spec — wires in the discarded A/A1, resolves SOIC narrow-vs-wide
  D/DW by lead span), `templates/{base,gullwing}.py`, `registry.py` (fail-closed on unsupported
  styles), `exporter.py` (STEP+GLB via `Assembly.export`), `validator.py` (measures in-memory B-rep
  vs spec — lead count exact, span/length/height, seating plane), `builder.py` (`build_body_model`).
  `main.py`: opt-in `--body-3d` flag (requires `--both`), best-effort hook after footprint success
  that can never fail a run. **Verified on SN74HC595 SOIC-16:** STEP/GLB match the datasheet exactly
  (span 10.325, length 9.90, height 2.50 mm, seated Z=0, 16 leads).
- ✅ **Milestone 2 (start) — footprint↔body alignment + gull-wing breadth (uncommitted).**
  - **Alignment check:** `validator.validate_alignment(assembly, pad_map)` compares each lead's foot
    (`faces("<Z").val().Center()`) to the **real** footprint pad centres
    (`PcbFootprintBuilder.pin_positions`). SOIC-16 worst-pin delta = **~1e-15 mm** (two independent
    computations agree perfectly, incl. pin-1/CCW numbering). Wired an optional `footprint_pad_map`
    into `build_body_model` (folds into `validated`) and into the `main.py` hook (reconstructs the
    pad map cheaply — heavy work is in `save_glb`, not the ctor).
  - **Breadth:** proved the gull-wing template generalizes with **zero new geometry** — TSSOP-20,
    SSOP-16, MSOP-8 all build + validate end-to-end (guards the "general parser, not corpus-tuned"
    principle).
- ✅ **Tests:** 19 new tests in `tests/test_model3d.py` (spec, template, exporter, validator,
  alignment, breadth, builder, pipeline hook). Full suite green (exit 0), no regressions.

### Notes / Decisions
- **Origin:** align the body to the footprint's own origin (component centre, Z=0) for internal
  consistency; KiCad datum + WRL 1/2.54 scale is a separate optional export mode, not baked into
  templates.
- **Validation is two-tier:** tight (±0.02–0.05 mm) for our own build fidelity; loose
  (±0.35 placement) for alignment. `A` is treated as one-sided max.
- Demo artifacts (gitignored) in `eval_output/body3d_demo_2026-08-03/`.

### Next Plan
- [ ] Commit the Milestone-2 increment (alignment + breadth) on the feature branch.
- [ ] Milestone 2 breadth — new templates: **leadless** (QFN/DFN/WSON/SON, + exposed pad D2/E2),
      **quad gull-wing** (QFP/TQFP/LQFP), **chip** passives (R/C/L), **through-hole** DIP.
- [ ] Add a small 3D ground-truth gate: compare generated bodies' bounding boxes to official KiCad
      STEP models, centroid-normalized, within tolerance.
- [ ] Extractor: add **`c`** (lead thickness) and **`D2/E2`** (exposed pad) — needed for faithful
      leadless/gull-wing bodies (currently defaulted).
- [ ] Real CLI run `--both --body-3d` on an actual SOIC datasheet PDF (needs LLM/vision endpoints).

## 2026-08-05 — Milestone 2 breadth: four package-body templates (parallel build)

### What We Did
- ✅ **Committed the Milestone-2 start increment (`cf23c4d`)** — footprint↔body alignment check
  + gull-wing breadth (TSSOP-20/SSOP-16/MSOP-8), the work left uncommitted on 08-03.
- ✅ **Built the four remaining core body templates in parallel**, one background subagent each,
  under strict guardrails (each creates ONLY its own template + test file; do NOT touch the shared
  registry/spec/validator; strict TDD). This kept them collision-free — all four landed green with
  no merge conflicts. Committed together as **`11309f9`** on branch
  `feat/3d-body-model-milestone-1`:
  - `templates/quad_gullwing.py` — **QuadGullwingTemplate** (QFP/TQFP/LQFP). 4-sided gull-wing;
    derives the Y-axis body edge as `D − (E − E1)` (same overhang as the E axis). 4 tests.
  - `templates/leadless.py` — **LeadlessTemplate** (QFN/DFN/WSON/SON). Flush bottom terminals on
    the seating plane; handles dual-row (DFN/SON) and quad (QFN) off `pins_per_side`. Exposed
    thermal pad D2/E2 **deferred** (extractor doesn't emit it yet). 3 tests.
  - `templates/chip.py` — **ChipTemplate** (R/C/L, 0201–1206). Two wrap-around end caps; band
    width = `L` or default `0.25·D`. 5 tests.
  - `templates/dip.py` — **DIPTemplate** (DIP/PDIP/CDIP). Straight through-hole leads running
    **below the board** to Z=−3.0; body sits above on its standoff. 5 tests.
- ✅ **Integration pass (parent, after all four landed):**
  - `spec.py`: `_LEAD_STYLE` remaps QFP-family → `"quad_gullwing"`, adds chip families
    (R/C/L/RES/CAP/IND → `"chip"`) and `BGA/LGA → "bga"` (no template ⇒ **fail closed**). New
    `_pins_per_side()` computes a quad `[L,R,T,B]` split for QFP/QFN (remainder onto first sides).
  - `registry.py` + `templates/__init__.py`: registered all four.
  - `validator.py`: `validate_body` is now **through-hole-aware** — for `lead_style=="through_hole"`
    it measures the lead-**foot** span (blades overshoot the bbox) and validates the Body child's
    top (A) + underside standoff (A1), instead of demanding the whole assembly seat at Z=0.
  - Repointed two existing fail-closed assertions from QFN/leadless (now supported) → BGA.
- ✅ **Tests:** +17 across 4 standalone template suites. **Full suite 297 passed, 1 skipped**
  (was 280), exit 0, no regressions.

### Notes / Decisions
- **Template coverage now 5 of ~7 core styles** (dual + quad gull-wing, leadless, chip, DIP) —
  covers the large majority of real parts. Left for Milestone 4 long tail: BGA/grid, power-tab
  (TO-220/DPAK). BGA deliberately skips (fail-closed) rather than emit a wrong shape.
- **Parallel-subagent pattern worked:** geometry files are independent; the ONLY collision risk was
  the shared wiring (registry/spec/validator/shared test), so that was reserved for the parent. Good
  template for future fan-out work.
- **Still validated against own dimensional spec only** (bbox + seating), NOT yet against official
  KiCad reference STEP models — the 3D ground-truth gate remains open.

### Next Plan
- [ ] 3D ground-truth gate: compare generated bodies' bounding boxes to official KiCad STEP models,
      centroid-normalized, within tolerance.
- [ ] Extractor: add **`c`** (lead thickness) and **`D2/E2`** (exposed pad) → then add the QFN/DFN
      center thermal pad to LeadlessTemplate.
- [ ] Real CLI run `--both --body-3d` on an actual datasheet PDF (needs LLM/vision endpoints).
- [ ] Milestone 4 long tail: BGA/grid-array + power-tab (TO-220/DPAK) templates.
- [ ] Consider merging `feat/3d-body-model-milestone-1` to main once ground-truth gate lands.

## 2026-08-06 — 3D "finish" push: full-completeness (A+B+C+D+E), parallel build

### What We Did
- ✅ **End-to-end proof (`--both --body-3d` on real PDFs).** Ran the FULL pipeline
  (fastchat text LLM up; qwen vision 502/down, so vision-fallback dims degrade) across
  five families: **TL072 (SOIC-8), SN74HC595 (SOIC-16), ATmega328p (DIP-28), DFN.pdf
  (leadless), cd74hc4017**. All emit `<stem>_body.step` + `.glb`. Measured the STEP:
  **TL072 body = span 6.000 / len 4.905 / height 1.750 / seated Z=0 — exact vs datasheet.**
  Bodies come out `UNVALIDATED (unverified)` when A/A1 fell back to defaults — the honest
  fail-open watermark, geometry still correct. (The integration hook in `main.py:1474` had
  never actually run on real extracted dims before tonight — now it has.)
- ✅ **3D ground-truth gate vs official STEP models** (`tools/run_body3d_ground_truth_eval.py`
  + test). Centroid-normalised, sorted-extent comparison (rotation/axis-invariant) against
  `tests/ground_truth/*/*.step`. Results: **TL072 SOIC-8 and MM74HC594M SOIC-16 match vendor
  geometry within 0.01 mm; ATMEGA328P DIP-28 passes.** Honest FAIL: **MCP3208 PDIP-16** — the
  SnapEDA reference keeps full **splayed uncut leads** (~10.9 mm cross-section) while our
  `DIPTemplate` uses a fixed 3 mm stub + no splay (~7.3 mm). Real convention difference,
  surfaced not hidden (didn't loosen tol to force a pass). Gotcha found: `BoundingBox()` on an
  imported STEP compound returns ∞ in this OCC build — aggregate over `.solids()` instead.
- ✅ **Extractor fidelity: `c`, `D2`, `E2`** (`text_dimensions.py`, `dimension_extractor.py`).
  Lead thickness `c` (0.05–0.60 mm gate), exposed-pad `D2/E2` (positive, < body) added to the
  vision prompts + text parsers + `plausible_dims`. **Optional** — not in `CRITICAL_KEYS`, so
  absence changes nothing (regression-checked). `Body3DSpec` now carries `lead_thickness_c` +
  `exposed_pad`; **`LeadlessTemplate` emits an `ExposedPad` node** on the underside centre when
  D2/E2 are present.
- ✅ **Two new templates → 5 of 7 core styles becomes 7 of 7 core + grid.**
  - `BgaTemplate` (BGA/LGA): near-square solder-ball grid from `pin_count`+pitch, balls seat at
    Z=0. **BGA/LGA now build instead of failing closed.**
  - `PowerTabTemplate` (TO-220/DPAK/D2PAK): body + heat-sink tab w/ mounting hole + through-hole
    leads. Routed from the raw package-type string (`_is_power_tab`) because the footprint-family
    detector returns None for TO packages.
- ✅ **Parent wiring + fail-closed preserved.** Registered both templates; `_LEAD_STYLE` maps
  power-tab families and **`LCCC → "jlead"` (unmodelled) so J-lead carriers still refuse** rather
  than emit a wrong gull-wing body. `validator` treats `power_tab` like `through_hole`. Repointed
  the two "BGA fails closed" tests → LCCC/jlead (a real still-unsupported case).
- ✅ **Parallel-subagent build again worked cleanly.** 4 background agents, each owning ONLY its
  own new files (BGA template, power-tab template, extractor+tests, ground-truth harness); parent
  did all shared wiring (registry/spec/validator/leadless) after they landed — zero collisions.
- ✅ **Tests: +40 new** (bga 7, powertab 9, extractor c/D2/E2 12, ground-truth 4, integration 8).
  **Full suite 337 passed, 1 skipped, exit 0.** Committed `8f97cf4` on
  `feat/3d-body-model-milestone-1`.

### Notes / Decisions
- **Reachability vs capability.** Power-tab and BGA are built + registered + reachable via
  `build_spec` and unit-tested, but full PDF→body reachability is gated UPSTREAM: `_family()`
  doesn't recognise TO-220/DPAK and `enforce_known_package_type` would refuse them before the body
  stage; BGA footprints are suppressed for module/grid parts. Wiring upstream package recognition
  is the remaining Milestone-4 step — the templates are ready for it.
- **DIP splayed-lead finding left as-is.** Chasing the MCP3208 cross-section to match SnapEDA's
  splayed leads risks regressing ATMEGA328 (trimmed-lead reference). The gate's job is to surface
  the difference; it does. Decide the lead-form convention before "fixing".
- **qwen vision down (502) all session** — text-first dim extraction carried the end-to-end runs.

### Next Plan
- [ ] Merge `feat/3d-body-model-milestone-1` → main (branch is green; ground-truth gate landed).
- [ ] Upstream package recognition for TO-220/DPAK (family detector + footprint defaults) so
      power-tab is reachable end-to-end; unblock BGA footprint for grid parts.
- [ ] DIP lead-form convention decision (splayed vs stub) informed by the ground-truth gate.
- [ ] Re-run ground-truth gate when qwen vision is back (verified-confidence bodies, not just default-dim).

## 2026-08-08 — 3D follow-ups: automated e2e test, text-A1 extraction, corpus report, ST parse fix

### What We Did
- ✅ **Deterministic PDF→body end-to-end test** (`tests/test_end_to_end_body3d.py`). Drives the
  real `--both --body-3d` pipeline on checked-in PDFs (lm358 DIP-8, MCP3208 DIP-16) with every
  network LLM/vision seam patched to RAISE, so it passes only through the deterministic
  table-parser + text-dimension paths — reproducible in CI despite the LLM ignoring `seed`.
  Asserts the emitted body STEP reimports with the expected DIP geometry (leads below Z=0, span,
  height). Committed `15c38eb`.
- ✅ **Text extraction of standoff A1 / body A2** (`feat` `34c8826`). Root cause of "every body is
  UNVALIDATED": the `verified` gate needs A **and** A1, but the text parser read A only — A1's
  label lives in the drawing graphic, not the text layer, so A1 only ever came from vision.
  Added `parse_dimension_table()`: reads A/A1/A2 from lettered "Dimension Limits" / "COMMON
  DIMENSIONS" tables (Microchip/Atmel/ST). Proven on ATmega328P TQFP (A=1.2, A1=0.1, A2=1.0).
  Additive + plausibility-gated; absence changes nothing.
- ✅ **Corpus extraction report** (`tools/run_extraction_report.py`, `fix` `9cbf0d8`). Runs the
  REAL pipeline (package + pins + dims, NO 3D build) over all 148 datasheets in isolated per-part
  subprocesses (timeout + worker pool), fast-failing the down vision endpoint. Findings:
  - **Package/pins: 134/148 OK (90%).** 14 fail (bridge-rectifier/discrete parts w/ no pins;
    4 timeouts on big multi-package parts: AVR128DA48, NRF9160×2, BQ500211).
  - **Dimensions: crippled without vision — 24/134 got any dim, 1 verified-capable.** Footprint
    dims (e,b,D,E,L) are ~0 from text; they come almost entirely from the vision path.
  - **75/134 are unsupported discretes** (TO-92/diodes/bridges/crystals) — no footprint/3D anyway;
    only ~59 are supported IC families.
  - **Conclusion: the dimension half of the pipeline is gated on the vision endpoint (qwen, 502).**
- ✅ **ST dual-unit parse bug fix** (surfaced by the report; `9cbf0d8`). STM32L031 came back
  `A = A1 = 0.30985` — the parser walked one fixed direction (grabbing a neighbour symbol's
  numbers) and averaged min+max across mixed mm/inch columns ((0.0197 in + 0.600 mm)/2). Fix:
  detect table orientation once (values-before vs symbol-then-values), drop inch-duplicate values
  (~other/25.4), mean of in-band values (not min+max), tighten A1 cap to 0.35mm, and drop A1/A2
  that violate the A1<A2<=A stack-up. STM32 now yields sane dims or nothing; ATmega unchanged.
  +2 regression tests.

### Notes / Decisions
- **Vision (qwen1.ideeza.com) has been 502 the whole time**; fastchat (text) is up. No `verified`
  body could be demonstrated end-to-end — not a code gap, an external outage. The A1 text-parser
  reduces (does not remove) that dependence: it fires only where a lettered dimension TABLE exists.
- **Deferred (need vision or bigger scope):** extend text extraction to the full footprint dim set
  (e/b/D/E/L from lettered tables); upstream package recognition so TO-220/DPAK/BGA reach their
  templates end-to-end; DIP splayed-lead fidelity (the one ground-truth-gate mismatch).

### Next Plan
- [ ] Re-run `tools/run_extraction_report.py` once qwen is back — dims columns should fill in.
- [ ] Merge PR #17 (3D body layer) to main.
- [ ] Optional: harvest e/b/D/E/L from lettered tables to cut vision dependence further.

## 2026-08-09 — Vision endpoint fix + text-dim breadth → FIRST verified 3D body

### What We Did
- ✅ **Root-caused the vision outage: wrong host.** The layout OCR client
  (`image_ocr_client.py`) pointed at `qwen1.ideeza.com/describe_image_llm` — **502 (dead)** —
  while the dimension extractor already used `qwen.ideeza.com/describe_image/`, which is **UP**.
  Direct probe of the live endpoint returned a full dim set for the ATmega TQFP page (incl.
  A1=0.05–0.15). So "vision down" all along was partly a stale endpoint in one client.
- ✅ **Fixed `image_ocr_client.py`** → `https://qwen.ideeza.com/describe_image/`, and switched its
  payload from `{system_prompt,user_prompt}` to the endpoint's `{file, text}` contract (matching
  the working dimension_extractor call). No old-URL references remain.
- ✅ **Extended the lettered-table text parser** (`parse_dimension_table`, parallel agent) to
  harvest the FULL footprint set — e/b/D/E/E1/L (+ combined D/E, D1/E1 tokens) — not just A/A1/A2.
  Reuses the orientation + inch-drop + in-band-mean machinery; snaps `e` to STANDARD_PITCHES.
  ATmega TQFP now yields a complete dim set **from text alone**.
- ✅ **🎉 FIRST `[verified]` 3D body, end-to-end.** `ATmega328P --both --body-3d
  --part-number ATMEGA328P-AU` → TQFP-32 body tagged **verified** (dims_source=text: A=1.2 A1=0.1
  A2=1.0 e=0.8 b=0.375 L=0.6 D=9.0 E1=7.0). STEP measures X=9.00 Y=9.00 Z=1.20, seated Z=0 — exact.
  Notably this needed **no vision** — the lettered-table text parse now covers it.
- ✅ **Upstream power-tab recognition** (parallel agent): `_family()` now classifies
  TO-220→TO220, TO-252/DPAK→DPAK, TO-263/D2PAK→D2PAK, TO-247→TO247; `get_footprint_defaults`
  still returns None for them (no fabricated footprint). **Parent wiring:** added those tokens to
  `spec.py::_LEAD_STYLE → power_tab` (the agent's integration note — the old `_is_power_tab`
  fallback stopped firing once `_family` returned non-None). All TO/DPAK now route to power_tab
  and build (Tab + leads).
- ✅ **DIP splayed-lead fidelity** (parallel agent): `DIPTemplate` leads now exit at the body wall
  (E1), step outward through a shoulder to the seated row spacing (E), and drop below-board by the
  datasheet `L` when plausible (else 3.0mm default). Feet still land exactly at `lead_span_E` so
  `validate_body` passes; ATmega DIP-28 still passes (height delta improved 0.33→0.03). Honest
  note kept: MCP3208's vendor STEP is in an over-splayed manufactured state (rows 9.14 > E) —
  matching that would violate the seated-row contract / overfit, so left as a documented
  convention difference.

### Notes / Decisions
- **Parallel-agent pattern again clean:** 3 agents on separate files (text_dimensions /
  footprint_defaults / dip.py + their tests); parent kept the shared spec.py wiring and the
  live end-to-end verification. Only real integration seam was spec.py `_LEAD_STYLE`.
- **Verified bodies no longer strictly require vision** for datasheets with a lettered dimension
  table (Microchip/Atmel/ST). Vision remains the path for graphical-only outlines (TI etc.).
- Full suite green (exit 0). Tests: +stream1 (13), +power_tab_family (24), +dip splay tests.

### Next Plan
- [ ] Extractor page-matching: graphical-outline parts (tl072 SOIC) still fall back to text-only
      (D/E1) — vision candidates get filtered by the family/designator/plausibility chain on
      messy multi-package datasheets. Worth a focused look for verified bodies on TI-style parts.
- [ ] Pin extraction still misidentifies multi-package parts (ATmega needed --part-number to pick
      TQFP over DIP) — package-selection accuracy is the next lever for hands-free verified bodies.
- [ ] PR this branch; re-run the corpus extraction report (dims columns should fill in now).

## 2026-08-09 (later) — Parallelized the accuracy harness + full 148 baseline

### What We Did
- ✅ **Hardened `tools/run_full_flow_eval.py`**: capped parallel workers
  (`FLOW_EVAL_WORKERS`, default 4) via a ThreadPoolExecutor + a tighter per-part
  watchdog (`FLOW_EVAL_TIMEOUT`, default 360s, was a flat 900s). Report is written
  incrementally under a lock and sorted deterministically at the end. Grading logic
  (`run_one`) unchanged. Cuts a full-corpus run from ~stall/60-90min sequential to
  ~20-30min, and a hung LLM call (AVR128DA48/NRF9160) no longer blocks the run.
- ✅ **First complete pin-count baseline over the whole `datasheets/` corpus (127 scored,
  21 dup + 1 non-datasheet excluded):** **66% (84/127) PASS**, 41 FAIL, 2 TIMEOUT.
  Report at `eval_output/flow_eval_148_report.json` (gitignored).

### Failure taxonomy (Phase-1 work queue)
- **A. Discretes/diodes/bridges/transistors/crystals (~14)** — VS-KBPC, DB102, BD135,
  BD441, MJL3281, 1N4001/1N4148/STTH (off-by-one 2→3), MA-506, ACS773, BSD235, PB86.
  Arguably out of core IC scope.
- **B. Modules/SiP/ref-design (~8)** — UC200, MAXREFDES117, ESP32-WROOM×2, MAX-M10S,
  CAM-M8Q, NRF9160. System already flags these footprint-unsupported.
- **C. Wrong package variant (~6, cleanest fix)** — MCP1700 3→6, W25Q128 8→16,
  TPS23751 reads TPS23752 (16→20), STM32L031 25→20, PIC16F871 reads PIC16F870;
  **PIC16F1512 = wrong PDF in corpus (actually MCP9701) — data bug**.
- **D. Small-IC over-count 10→14 (~4, likely one root cause)** — AD636, AD537, LM2673, INA238.
- **E. Tab/exposed-pad off-by-one (~4)** — ADXRS645 15→16, BD9778 7→8, TDA7850 25→20,
  BQ25570 20→16.
- **F. Big MCUs under-read / timeout (~5)** — AVR128DA48 & dsPIC33 timeouts, MKL17/43/46
  badly under-read (64→13, 121→13), ATTINY13A 10→8.

### Notes / Decisions
- **~22 of 43 failures (A+B) are discretes/modules** — arguably outside the core IC
  footprint/3D use case; excluding them lifts core-IC accuracy well above 66%. Scope
  (in/out for discretes+modules) is an open product decision that reframes the target.
- This harness is now the repeatable **Phase-4 validation gate**: re-run it to confirm
  every Phase-1 fix against the full corpus (trust multi-run, not single noisy runs).

### Next Plan
- [ ] Confirm scope (discretes/modules in or out) → sets the accuracy target.
- [ ] Phase 1: start with class C (wrong-variant, suffix→variant selection), then D, then E.
- [ ] Replace the wrong `52_PIC16F1512` corpus PDF (it's an MCP9701 datasheet).
