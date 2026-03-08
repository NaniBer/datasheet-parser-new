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
- ✅ Text-based layout extraction for standard packages - Complete and verified

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
┌─────────────────────────────────────────────┐
│ 4. Layout Generation (Text-Based)                 │
│    - Package type detection (DIP, SOIC, QFP, QFN)  │
│    - Apply standard layout rules                     │
│    - Custom layouts for special cases                 │
└─────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────┐
│ 5. Schematic Generation                            │
│    - CadQuery geometry building                     │
│    - GLB export                                     │
└─────────────────────────────────────────────┘
  ↓
PinData Output (JSON) + GLB Schematic
```

### Module Structure

```
src/
├── chat_bot.py              # FastChat API client, prompt building
├── llm/
│   ├── client.py            # LLMClient for pin extraction
│   ├── image_ocr_client.py # Vision API for layout extraction (experimental)
│   └── page_verifier.py    # LLM fallback for ambiguous pages
├── models/
│   └── pin_data.py        # Pin, PackageInfo, PinData models
├── pdf_extractor/
│   ├── page_detector.py     # Hybrid page detection
│   ├── content_extractor.py # Text/table/image extraction
│   ├── pinout_filter.py   # Filter content to pinout-relevant information
│   └── image_detector.py  # Image detection for Vision API
├── utils/
│   └── package_detector.py # Package type normalization
├── main.py                  # CLI entry point
├── main_layout.py           # Alternative CLI with Vision API layout mode (experimental)
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
| **Text-based layout extraction** | ✅ Complete - Standard package layouts work perfectly |

### Schematic Generator

**`src/schematic_generator/`** - Complete schematic generation module
- `package_geometry.py` - Geometry parameters for each package type
- `pin_layout.py` - Pin layout algorithms for each package type
- `schematic_builder.py` - CadQuery builder with GLB export
- **Text Rendering:** Character stacking for vertical text on top/bottom pins (no rotation)

**Text Orientation Notes:**
- Left/Right pins: Horizontal text, readable from side
- Top/Bottom pins: Characters stacked vertically (upright), readable from top/down
- Top pins: Characters stack downward (away from body)
- Bottom pins: Characters stack upward (away from body)
- Pin numbers on top/bottom: Positioned OUTSIDE (further from body)
- Pin names on top/bottom: Positioned INSIDE (closer to body)

#### Supported Package Types

| Package | Body Width | Pin Pitch | Pin Layout | Example |
|---------|------------|-----------|----------|----------|
| **DIP** | 20.0mm | 3.80mm | Counter-clockwise (left down, right up) | NE555 (8 pins) |
| **SOIC** | 5.0mm | 1.27mm | Counter-clockwise on 2 sides | 74HC595 (16 pins) |
| **TQFP** | 13.5mm | 0.5mm | Counter-clockwise on all 4 sides | ATmega164A (44 pins) |
| **LQFP** | 16.0mm | 0.5mm | Counter-clockwise on all 4 sides | STM32 (64 pins) |
| **QFN** | 6.0mm | 0.5mm | Counter-clockwise on all 4 sides | Small surface-mount |

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

## VISION API INTEGRATION (EXPERIMENTAL)

### Background

The Vision API (`https://qwen.ideeza.com/describe_image/`) was investigated for extracting layout information from pinout diagrams in datasheets.

### Testing Results

| Approach | Result |
|----------|--------|
| Simple prompt (ask for left/right/bottom sides) | ❌ Failed - Only saw 27 pins on left side |
| General prompt with datasheet conventions | ❌ Failed - Interpreted as table, not physical layout |
| Two-step (describe structure, then extract) | ❌ Failed - Still saw 27 pins on left side |
| Pin-by-pin questions | ❌ Failed - 54 total pins with duplicates |
| Expected layout template | ✅ Works (but not generalizable) |

### Conclusion

**The Vision API is NOT suitable for extracting layout from electronic component pinout diagrams.**

The API consistently:
- Interprets pinout diagrams as tables/lists rather than physical component layouts
- Fails to distinguish pins on different sides of the component
- Produces incorrect layouts even when given detailed instructions

### Recommendation

**Use text-based layout extraction with standard package layouts:**
1. Detect package type from text (DIP, SOIC, TQFP, QFN, BGA)
2. Apply standard layout rules for that package type
3. For special cases (ESP32-WROOM-32E), use pre-defined custom layouts

The Vision API approach has been **abandoned** for layout extraction due to unreliability.

---

## TEXT-BASED LAYOUT EXTRACTION

### Approach

```
Text Extraction
    ↓
Pin Data (pin numbers, names, functions)
    ↓
Package Type Detection (DIP, SOIC, TQFP, QFN, BGA)
    ↓
Standard Layout Application
    ↓
Generate Schematic
```

### Standard Package Layouts

| Package | Pin Distribution | Count Rule |
|---------|----------------|-------------|
| **DIP** | Left side (1 to N/2), Right side (N/2+1 to N) | Even pin count |
| **SOIC** | Left side (1 to N/2), Right side (N/2+1 to N) | Even pin count |
| **TQFP/LQFP** | All 4 sides evenly distributed | Divisible by 4 |
| **QFN** | All 4 sides evenly distributed | Any pin count |
| **BGA** | Perimeter or grid layout | Any pin count |

### Special Cases

Some components have non-standard layouts that require custom handling:

| Component | Package | Pin Count | Custom Layout |
|-----------|----------|-----------|----------------|
| **ESP32-WROOM-32E** | QFN | 38 | Left: 1-14, Bottom: 15-24, Right: 25-38, Top: none |

---

## TEST RESULTS (TEXT-BASED LAYOUT)

| Datasheet | Component | Package Detected | Pin Count | Status |
|-----------|-----------|----------------|-----------|--------|
| **NE555.PDF** | NE555 Timer | DIP-8 | ✅ Success |
| **STM32F103RBT7.PDF** | STM32F103RBT7 | LQFP-64 | ✅ Success |
| **74HC595_TI.pdf** | SN74HC595 | SOIC-16 | ✅ Success |
| **MC74HC595A.PDF** | MC74HC595A | DIP-16 | ✅ Success |
| **ESP32-WROOM-32E (pages.pdf)** | ESP32-WROOM-32E | QFN-38 | ✅ All pins extracted (non-standard layout) |

---

## RECENT CHANGES (Mar 2026)

### Schematic Text Orientation Fix (Mar 2026)

**Goal:** Fix text readability on top/bottom pins of QFN/LQFP packages

**Problem:** Text rotated 90° for top/bottom pins caused characters to appear sideways/unreadable in 3D viewer

**Solution:** Character stacking instead of rotation
- For top/bottom pins, stack individual characters vertically without rotation
- Characters remain upright and readable from top-down view
- Top edge: Characters stack downward (away from body)
- Bottom edge: Characters stack upward (away from body)
- Adjusted text positions: pin numbers outside, pin names inside for top/bottom
- Added 0.5mm offset to left side text positions for better spacing

**Files Modified:**
- `src/schematic_generator/schematic_builder.py` - Character stacking for vertical text
- `src/schematic_generator/pin_layout.py` - Text position offsets

**Result:** Text on all 4 sides of quad packages is now readable and properly positioned

---

## RECENT CHANGES (Feb 2026)

### Vision API Testing (Feb 2026)

**Goal:** Test Vision API for extracting layout from pinout diagrams

**Testing Process:**
1. Created multiple test scripts with different prompt approaches
2. Tested on ESP32-WROOM-32E pinout diagram
3. Attempted 5 different prompt strategies

**Result:** Vision API consistently fails to understand physical layout of electronic component pinout diagrams

**Decision:** Abandon Vision API for layout extraction; use text-based approach instead

### Text-Based Layout Verification (Feb 2026)

**Goal:** Verify that text-based extraction with standard package layouts works

**Testing Process:**
1. Tested 74HC595_TI.pdf (SOIC-16 package)
2. Tested MC74HC595A.PDF (DIP-16 package)
3. Verified NE555.PDF (DIP-8 package)
4. Verified STM32F103RBT7.PDF (LQFP-64 package)

**Result:** All standard packages work perfectly with text-based layout extraction

**Conclusion:** Text-based approach is production-ready for standard package types

---

## GENERATED OUTPUT FILES

All schematics are generated in the `output/` directory:

### Standard Packages (Verified)
- `NE555_schematic.glb` (1.36 MB)
- `STM32_test.glb` (14.54 MB)
- `74HC595_schematic.glb` (2.09 MB)
- `MC74HC595A_schematic.glb` (~2 MB)

### ESP32 (Special Case)
- `ESP32-WROOM-32E schematic.glb` (7.70 MB) - All 38 pins extracted, uses default QFN layout

---

## WHAT'S MISSING

| Issue | Description | Impact |
|--------|-------------|---------|
| **ESP32-WROOM-32E correct layout** | Non-standard QFN layout (14-10-14-0) uses default layout (9-9-10-9) | Schematic has wrong pin positions |
| **Package type detection for ESP32** | LLM returns "Unknown-38" instead of "QFN-38" | May affect other ESP32 variants |
| **Other special case modules** | No framework for adding custom layouts for other non-standard components | Future modules may have incorrect layouts |

---

## NEXT STEPS

### High Priority

1. **Add ESP32-WROOM-32E custom layout**
   - Add ESP32-WROOM-32E to package_detector.py as known special case
   - Implement custom layout: left_side=[1-14], bottom_edge=[15-24], right_side=[25-38]
   - Test that schematic generates with correct pin positions

2. **Improve package type detection**
   - Update LLM prompt to better recognize QFN packages
   - Add ESP32 package patterns to package_detector.py

### Medium Priority

3. **Framework for special cases**
   - Create a database/module for custom layouts
   - Allow adding new special cases without modifying core code
   - Document special case format for future additions

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

---

## NOTES FOR FUTURE DEVELOPMENT

### LLM Prompt Improvements
- Add QFN-specific patterns to package detection
- Add ESP32 module recognition patterns
- Improve package type detection for non-standard packages

### Package Detection Enhancements
- Add framework for custom layouts
- Document special case format
- Add manufacturer-specific package patterns

### Schematic Enhancements
- Add better support for non-standard QFN layouts
- Add ball map support for BGA packages
- Add pin number markers (dots, notches)

---

## STATUS SUMMARY

### Complete ✅
- Pin extraction system (rules-based + LLM)
- Content extraction with filtering
- Multi-page pinout table support
- Schematic generator (DIP, SOIC, TQFP, LQFP, QFN)
- CLI integration
- Text-based layout extraction for standard packages
- Vision API testing (determined unsuitable)
- **Schematic text orientation fix** - Character stacking for vertical text on top/bottom pins

### In Progress 🚧
- None

### Pending ⏸️
- ESP32-WROOM-32E custom layout
- Framework for special case modules
- BGA grid layout support
- Pin number markers

---

## Generated Output Files

All schematics are generated in the `output/` directory:
- `NE555_schematic.glb` (1.36 MB)
- `STM32F103RBT7_schematic.glb` (6.4 MB) - LQFP48 with fixed text orientation
- `74HC595_schematic.glb` (2.09 MB)
- `MC74HC595A_schematic.glb` (~2 MB)
- `test_schematic.glb` (9.44 MB)
- `basic_test.glb` (8.12 MB)

These files can be opened in a 3D viewer to inspect the schematic symbols.
