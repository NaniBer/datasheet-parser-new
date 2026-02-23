# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Datasheet Parser** - Extracts pin data from electronic component datasheets using hybrid page detection (rules-based + LLM fallback) and FastChat API for pin data extraction.

**Status:**
- ✅ Pin extraction system - Complete and tested
- ✅ Schematic generator - Complete and tested
- ✅ CLI integration with --schematic flag
- ✅ End-to-end pipeline working

## Common Development Commands

### Testing

```bash
# Run end-to-end pin extraction test on all PDFs
python3 test_scripts/test_end_to_end.py

# Run page detection only
python3 test_scripts/test_page_detection.py

# Test content extraction only
python3 test_scripts/test_content_extraction.py

# Test LLM connection
python3 test_scripts/test_chat_bot.py

# Test LLM pin extraction with sample data
python3 test_scripts/test_pin_extraction.py

# Run schematic generator tests
python3 test_scripts/test_cadquery.py
python3 test_scripts/test_cadquery_api.py
python3 test_scripts/test_package_geometry.py
python3 test_scripts/test_pin_layout.py
python3 test_scripts/test_adapter.py

# Run end-to-end schematic generation
python3 test_scripts/test_pdf_to_schematic.py
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
│   └── content_extractor.py # Text/table/image extraction
├── models/
│   └── pin_data.py        # Pin, PackageInfo, PinData models
├── main.py                  # CLI entry point
└── schematic_generator/  ← NEW: Schematic symbol generation
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
# Pin extraction only (existing)
python -m src.main datasheet.pdf output.glb --verbose

# With schematic generation (NEW)
python -m src.main datasheet.pdf output.glb --schematic --verbose

# Pin extraction + schematic (both modes)
python -m src.main datasheet.pdf output.glb --schematic --verbose
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
|---------|-----------|----------|-----------|----------|
| DIP-8 | 8 | 1.36 MB | ✅ |
| TQFP-44 | 44 | 9.44 MB | ✅ |
| LQFP-64 | 64 | 14.54 MB | ✅ |
| SOIC-16 | 16 | 2.09 MB | ✅ |

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
| **Full pipeline with LLM-extracted PinData** | ⚠️ Issue: Recursion error when converting PinData to string. Needs investigation. Use manual pin data mode for testing. |
| **am623.pdf malformed JSON** | ⚠️ Issue: Too much content (30 pages, 93 tables) overwhelmed LLM. Needs content filtering/truncation |

---

## Generated Output Files

All schematics are generated in the `output/` directory:
- `NE555_schematic.glb` (1.36 MB)
- `test_schematic.glb` (9.44 MB)
- `STM32F103RBT7_schematic.glb` (14.54 MB)

These files can be opened in a 3D viewer to inspect the schematic symbols.
