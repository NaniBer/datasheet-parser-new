# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Datasheet Parser** - Extracts pin data from electronic component datasheets using hybrid page detection (rules-based + LLM fallback) and FastChat API for pin data extraction. Generates schematic symbols in GLB format.

**Status:**
- ✅ Pin extraction system - Complete and tested
- ✅ Schematic generator - Complete and tested
- ✅ CLI integration - Complete and tested
- ✅ End-to-end pipeline working
- ✅ Multi-page pinout table support - Complete

## Common Development Commands

### Testing

```bash
# Run end-to-end test
python3 test_scripts/test_end_to_end.py

# Run page detection test
python3 test_scripts/test_page_detection.py

# Test content extraction
python3 test_scripts/test_content_extraction.py

# Test LLM connection
python3 test_scripts/test_chat_bot.py

# Test LLM pin extraction
python3 test_scripts/test_pin_extraction.py

# Test package geometry
python3 test_scripts/test_package_geometry.py

# Test pin layout
python3 test_scripts/test_pin_layout.py

# Test pin mapping
python3 test_scripts/test_pin_mapping.py

# Test end-to-end schematic generation
python3 test_scripts/test_end_to_end_schematic.py
```

### Running Tests

```bash
# Activate virtual environment
source datasheet/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set API key (required for LLM)
export FASTCHAT_API_KEY='your-key-here'

# Or use .env file (already configured)
# FASTCHAT_API_KEY is set in .env
```

---

## Architecture

### Pin Extraction Pipeline

```
PDF Input
  ↓
┌─────────────────────────────────────────────────────┐
│ 1. Page Detection (Rules-based)                 │
│    - Heading patterns (Pin Configuration, etc.)    │
│    - Table detection (Pin No., Name, Function)    │
│    - Diagram detection with captions                 │
│    - Keyword density (pin, vcc, gnd, gpio...)   │
│    - Page position heuristics (20-70%)          │
│    → Confidence scoring (0-10+)                  │
└─────────────────────────────────────────────────────┘
  ↓ (pages with confidence ≥5)
┌─────────────────────────────────────────────┐
│ 2. Content Extraction                             │
│    - Text with page markers                        │
│    - Tables (limited to 20 rows)                   │
│    - Images (bytes)                               │
└─────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────┐
│ 3. LLM Pin Extraction                             │
│    - Part number variant matching (e.g., RBT7→64)   │
│    - Extracts: component_name, package, pins       │
│    - Model: llama-3 (via FastChat)              │
└─────────────────────────────────────────────┘
  ↓
PinData Output (JSON)
```

### Module Structure

```
src/
├── chat_bot.py              # FastChat API client, prompt building
├── llm/
│   ├── client.py            # LLMClient for pin extraction
│   └── page_verifier.py    # LLM fallback for ambiguous pages
├── pdf_extractor/
│   ├── page_detector.py     # Hybrid page detection
│   ├── content_extractor.py # Text/table/image extraction
│   └── pinout_filter.py   # Filter content to pinout-relevant information
├── models/
│   └── pin_data.py        # Pin, PackageInfo, PinData models
├── utils/
│   └── package_detector.py # Package type normalization
├── main.py                  # CLI entry point
└── schematic_generator/      # Schematic symbol generation
    ├── package_geometry.py   # Geometry parameters for each package type
    ├── pin_layout.py        # Pin layout algorithms
    ├── schematic_builder.py  # Cadquery builder with GLB export
    └── adapter.py          # PinData to SchematicBuilder format conversion
```

test_scripts/                 # Test scripts for each component
```

---

## Key Files and Their Purpose

### Core Data Models

**`src/models/pin_data.py`** - Pin data structures
- `Pin`: Individual pin (number, name, function)
- `PackageInfo`: Package (type, pin_count, width, height, pitch, thickness)
- `PinData`: Complete extraction result

### Page Detection

**`src/pdf_extractor/page_detector.py`** - Rules-based detection with LLM fallback
- `PageDetector.detect_relevant_pages(min_confidence=5)` → List[PageCandidate]
- Confidence scoring: Headings(+3), Tables(+4), Diagrams(+2), Keywords(+2), Position(+1)
- `threshold: min_confidence=5` (default)

### Content Extraction

**`src/pdf_extractor/content_extractor.py`** - Text/table/image extraction
- `ContentExtractor.extract_content(candidates)` → ExtractedContent
- Applies PinoutFilter to reduce content to only pinout-relevant information
- Filter preserves content from pages with pinout tables

**`src/pdf_extractor/pinout_filter.py`** - Content filtering for LLM
- `is_pinout_table()` - Identifies pinout tables
- `is_pinout_section()` - Identifies pinout text sections
- `filter_content()` - Filters extracted content to only relevant information
- Preserves content from pages with pinout tables even if text doesn't match keywords

### LLM Integration

**`src/chat_bot.py`** - FastChat API client
- `BASE_URL`: https://fastchat.ideeza.com/v1
- `DEFAULT_MODEL`: llama-3
- `get_completion_from_messages(messages, model, temperature)` - API call
- `build_pin_extraction_prompt(content, part_number)` - Builds extraction prompt

---

## Pin Extraction Features

| Feature | Description | Status |
|---------|-------------|--------|
| **Hybrid page detection** | ✅ Complete - Rules-based with LLM fallback for confidence scoring |
| **Part number matching** | ✅ Working - Maps suffix codes to pin counts (RBT6=64, RBT8=48, RCT6=144) |
| **Package detection** | ✅ Complete - Identifies DIP, SOIC, TQFP, QFN, BGA |
| **Table detection** | ✅ Working - Detects Pin No., Name, Function columns |
| **Keyword detection** | ✅ Working - Detects pin, vcc, gnd, gpio keywords |
| **Diagram detection** | ✅ Working - Detects diagrams with captions |
| **Position heuristics** | ✅ Working - Validates pages are in correct 20-70% range |
| **Multi-page pinout tables** | ✅ Fixed - Preserves content across page continuations |

### Schematic Generator (NEW!)

**`src/schematic_generator/`** - NEW MODULE
- `package_geometry.py` - Geometry parameters for each package type
- `pin_layout.py` - Pin layout algorithms for each package type
- `schematic_builder.py` - Cadquery builder with GLB export
- `adapter.py` - PinData to SchematicBuilder format conversion

#### Supported Package Types

| Package | Body Width | Pin Pitch | Pin Layout | Example |
|---------|------------|-----------|----------|----------|
| **DIP** | 20.0mm | 3.80mm | Counter-clockwise | NE555 (8 pins) |
| **SOIC** | 5.0mm | 1.27mm | Counter-clockwise | Various ICs |
| **TQFP** | 13.5mm | 0.5mm | Counter-clockwise | ATmega164A (44 pins) |
| **LQFP** | 16.0mm | 0.5mm | Counter-clockwise | STM32 (64 pins) |
| **QFN** | 6.0mm | 0.5mm | Counter-clockwise | Small surface-mount |

#### Generated Schematic Symbol Structure

```
Package (main assembly)
├── BodyLine (wireframe border)
│   ├── BodyLine_Top
│   ├── BodyLine_Bottom
│   ├── BodyLine_Left
│   └── BodyLine_Right
├── Legs (all pins)
│   ├── pin1 (leg, text, num)
│   ├── pin2 (leg, text, num)
│   └── ...
├── DesignatorName ("U")
└── PackageValue (component name)
```

---

## CLI Usage

```bash
# Basic usage - PDF to schematic GLB
python -m src.main datasheet.pdf output.glb --verbose

# With custom API key
python -m src.main datasheet.pdf output.glb --api-key YOUR_API_KEY --verbose

# With custom model
python -m src.main datasheet.pdf output.glb --model gpt-4 --verbose

# Adjust page detection confidence
python -m src.main datasheet.pdf output.glb --min-confidence 3 --verbose
```

---

## SCHEMATIC DESIGN TASK BREAKDOWN

**Status:** 🚧 Not Started

### Phase 1: Cadquery Integration (Foundation)

| Task | Description | Status |
|-------|-------------|--------|
| 1.1 | Install and verify cadquery works in the environment | ✅ Done |
| 1.2 | Test basic cadquery code | ✅ Done |
| 1.3 | Understand cadquery 2D API for schematic symbols | ✅ Done |

### Phase 2: Pin Data to 3D Model (Core)

| Task | Description | Status |
|-------|-------------|--------|
| 2.1 | Design schematic symbol geometry parameters for each package type | ✅ Done |
| 2.2 | Create cadquery schematic builder module | ✅ Done |
| 2.3 | Implement pin layout algorithms for each package type | ✅ Done |
| 2.4 | Implement full schematic generation from PinData | ✅ Done |

### Phase 3: GLB Export

| Task | Description | Status |
|-------|-------------|--------|
| 3.1 | Research and implement text/label export for GLB | ✅ Done (cadquery has native `.text()`) |
| 3.2 | Implement GLB export function | ✅ Done (cadquery `assembly.save()`) |

### Phase 4: Integration with CLI

| Task | Description | Status |
|-------|-------------|--------|
| 4.1 | Connect pin extraction → model generation → GLB export in main.py | ✅ Done |
| 4.2 | Test end-to-end: PDF → PinData → GLB schematic | ✅ Done (manual test) |
| 4.3 | Clean up unused code (placeholder files) | ⏸️ Pending |

**Total: 8 Tasks Completed**

---

## Test Results Summary

| Package | Pin Count | GLB Size | Status |
|---------|-----------|----------|-----------|
| DIP-8 | 8 | 1.36 MB | ✅ |
| TQFP-44 | 44 | 9.44 MB | ✅ |
| LQFP-64 | 64 | 14.54 MB | ✅ |
| SOIC-16 | 16 | 2.09 MB | ✅ |
| ESP32-WROOM-32E (Unknown-38) | 38 | 7.70 MB | ✅ (all pins extracted) |

---

## Recent Changes

### Pin Extraction Fix (Feb 2026)

**Problem:** Multi-page pinout tables were being truncated. Pins 28-38 of ESP32-WROOM-32E were showing as "unknown" because the content from Page 12 was not being preserved by the PinoutFilter.

**Root Cause:**
1. `PinoutFilter.filter_content()` was splitting text by page markers and discarding blocks that didn't perfectly match pinout section keywords
2. Text blocks were losing their page markers during filtering
3. Pages with pinout tables but different text formatting were being filtered out

**Solution:**
1. Added more keywords to `PINOUT_SECTION_KEYWORDS` (including `'pindescription'`, `'pindefinitions'`, `'pin table'`)
2. Modified `filter_content()` to preserve content from pages that have pinout tables, even if text doesn't match keywords
3. Added page markers back to filtered text: `--- Page {page_num} ---`
4. Removed unused `filter_text_blocks()` method

**Result:** All 38 pins now correctly extracted for ESP32-WROOM-32E

### Code Cleanup (Feb 2026)

**Removed directories/files:**
- `src/model_generator/` - Unused 3D model generation code
- `src/llm/vision_client.py` - Vision API (not implemented)
- `src/pdf_extractor/image_pinout_extractor.py` - Unused image extractor
- 22+ obsolete test scripts (debug_*, inspect_*, test_*)
- `model (10).png` - Temporary image

**Simplified main.py:**
- Removed unused imports (ImagePinoutExtractor, PageVerifier, VisionAPIClient)
- Removed broken 3D model generation code
- Removed `--format`, `--schematic`, `--verify-ambiguity`, `--vision` arguments
- Updated verbose messages from [1/5] to [1/3]
- Schematic generation is now the default (no flag needed)

---

## What's Missing

| Issue | Description | Impact |
|--------|-------------|---------|
| **QFN package type detection** | LLM returns "Unknown-38" instead of recognizing QFN-38 | Schematic uses DIP layout (wrong for QFN) |
| **Package-specific pin recognition** | ESP32 pin naming (IOxx, GPIOxx) not fully recognized | Pins may have incorrect function classification |
| **BGA package support** | BGA schematic generator uses grid layout (simplified) | Limited BGA support |

## Next Steps

### High Priority
1. **Fix QFN package type detection**
   - Update LLM prompt to better recognize QFN packages
   - Add ESP32 package patterns to package_detector.py
   - Add QFN-38 specific parameters to package_geometry.py

2. **Add QFN perimeter distribution**
   - Implement true QFN layout with pins on all 4 sides
   - Add has_center_pad parameter for QFN thermal pad

### Medium Priority
3. **Improve package type normalization**
   - Add ESP32-WROOM-32 mapping to QFN-38
   - Add ESP32-WROOM-32D mapping to appropriate package
   - Add more manufacturer-specific package patterns

4. **Add BGA grid layout support**
   - Implement proper BGA pin layout (not just perimeter)
   - Add ball map support for BGA packages

### Low Priority
5. **Improve pin function classification**
   - Better detect GPIO, ADC, DAC, SPI, I2C, UART functions
   - Add clock, crystal, and reset pin recognition

6. **Add pin number markers**
   - Add pin 1 dot markers to schematic symbols
   - Add notch indicators for orientation

| ESP32-WROOM-32E (Unknown-38) | 38 | 7.70 MB | ✅ (all pins extracted) |

---

## Notes for Future Development

### LLM Prompt Improvements
- Add more suffix code patterns for other manufacturers
- Implement content summarization for large datasheets (am623.pdf issue)
- Add multimodal support for diagram images

### Page Detection Enhancements
- Add BGA-specific patterns (ball maps, grid arrays)
- Improve diagram detection using image analysis

### Schematic Enhancements
- Add BGA schematic symbol support (grid layout)
- Improve package ordering information extraction
- Add pin number markers (dots, notches)

---

## Known Issues

| Issue | Description | Status |
|--------|-------------|--------|
| **QFN package type detection** | LLM returns "Unknown-38" instead of recognizing QFN-38. Schematic defaults to DIP layout which is incorrect. | ⚠️ Needs improvement to LLM prompt or package_detector.py |
| **QFN perimeter distribution** | Current get_qfn_parameters() uses TQFP-style counter-clockwise on all 4 sides. Real QFN has different pin distribution. | ⚠️ Needs QFN-specific implementation |
| **Package type normalization** | "Unknown-38" defaults to DIP instead of QFN. | ⚠️ Add ESP32 package mapping to package_detector.py |

---

## Generated Output Files

All schematics are generated in the `output/` directory:
- `NE555_schematic.glb` (1.36 MB)
- `test_schematic.glb` (9.44 MB)
- `STM32F103RBT7_schematic.glb` (14.54 MB)

These files can be opened in a 3D viewer to inspect the schematic symbols.
