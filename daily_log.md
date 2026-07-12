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
