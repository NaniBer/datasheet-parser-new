# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Datasheet Parser** - Extracts pin data from electronic component datasheets using hybrid page detection (rules-based + LLM fallback) and FastChat API for pin data extraction.

**Status:**
- ✅ Pin extraction system - Complete and tested
- 🚧 Model generation (3D CAD/GLB) - 12 tasks pending (see SCHEMATIC DESIGN TASK BREAKDOWN below)

---

## Common Development Commands

### Testing

```bash
# Run end-to-end pin extraction test on all PDFs
python3 test_scripts/test_end_to_end.py

# Test page detection only
python3 test_scripts/test_page_detection.py

# Test content extraction only
python3 test_scripts/test_content_extraction.py

# Test LLM connection
python3 test_scripts/test_chat_bot.py

# Test LLM pin extraction with sample data
python3 test_scripts/test_pin_extraction.py
```

### Running Tests

```bash
# Run a single test
python3 tests/test_models.py
python3 tests/test_package_detector.py
```

### Environment Setup

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
┌─────────────────────────────────────────────────────┐
│ 2. Content Extraction                             │
│    - Text with page markers                        │
│    - Tables (limited to 20 rows)                   │
│    - Images (bytes)                               │
└─────────────────────────────────────────────────────┘
  ↓
┌─────────────────────────────────────────────────────┐
│ 3. LLM Pin Extraction                             │
│    - Part number variant matching (e.g., RBT7→64)   │
│    - Extracts: component_name, package, pins       │
│    - Model: llama-3 (via FastChat)              │
└─────────────────────────────────────────────────────┘
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
└── utils/                   # (placeholder)

test_scripts/                 # Test scripts for each component
```

---

## Key Files and Their Purpose

### Core Data Models

**`src/models/pin_data.py`** - Pin data structures
- `Pin`: Individual pin (number, name, function)
- `PackageInfo`: Package (type, pin_count, width, height, pitch, thickness)
- `PinData`: Complete extraction result (component_name, package, pins, extraction_method)

### Page Detection

**`src/pdf_extractor/page_detector.py`** - Rules-based detection with LLM fallback
- `PageDetector.detect_relevant_pages(min_confidence=5)` → List[PageCandidate]
- Confidence scoring: Headings(+3), Tables(+4), Diagrams(+2), Keywords(+2), Position(+1)
- Threshold: `min_confidence=5` (default)
- Marks pages for LLM verification if score 3-4 or unusual structure

### Content Extraction

**`src/pdf_extractor/content_extractor.py`** - Extract text/tables/images
- `ContentExtractor.extract_content(candidates)` → ExtractedContent
- Formats text with page markers for context
- Limits table rows to 20 for LLM token limits
- Extracts images as bytes from PDF streams

### LLM Integration

**`src/chat_bot.py`** - FastChat API client
- `BASE_URL`: https://fastchat.ideeza.com/v1
- `DEFAULT_MODEL`: llama-3
- `get_completion_from_messages(messages, model, temperature)` - API call
- `build_pin_extraction_prompt(content, part_number)` - Builds extraction prompt

**Part Number Variant Matching:**
When `part_number` is provided, LLM is instructed to:
- Look for ordering/package mapping tables
- Match suffix codes to pin counts (RBT6=64, RBT8=48, RCT6=144)
- Extract pins ONLY for the specified variant

**`src/llm/client.py`** - LLMClient wrapper
- `extract_pin_data(content, images, part_number)` → PinData
- Handles markdown code blocks in LLM response
- Converts null dimensions to 0.0 (won't crash)
- Parses both string and int pin numbers
- Shows response preview on JSON parse failure

---

## Known Issues and Edge Cases

| Issue | Description | Current Status |
|--------|-------------|----------------|
| **am623.pdf malformed JSON** | Too much content (30 pages, 93 tables) overwhelmed LLM | Needs content filtering/truncation |
| **Visual-only pinouts** | Text extraction works but diagrams need OCR | Text extraction finds tables in most cases |
| **2-terminal devices** | TVS diodes, simple components | Correctly detected as no pinout pages |
| **Package variant confusion** | Multi-variant datasheets can extract wrong pins | **FIXED**: Part number matching now works |

---

## Test Results Summary

Tested on 8 PDFs with end-to-end pipeline:

| PDF | Status | Package | Pins | Notes |
|-----|--------|----------|-------|-------|
| NE555.PDF | ✅ | DIP-8 | 8 | Simple IC, perfect extraction |
| STM32F103RBT7.PDF | ✅ | LQFP64 | 64 | Multi-variant, correct variant matched |
| TPS63060.PDF | ✅ | DSC(SON)-10 | 10 | Power IC, good extraction |
| test.pdf (ATmega164A) | ✅ | TQFP-44 | 44 | Visual pinout handled |
| TVS-Diode-SMBJ-Datasheet.pdf | ⚠️ | - | - | 2-terminal device (no pinout) |
| foo.pdf | ⚠️ | - | - | Simple content (no pinout) |
| pages.pdf | ❌ | - | - | Fixed: null handling issue |
| am623.pdf | ❌ | - | - | Malformed JSON (too much content) |

---

## Important Implementation Details

### Part Number Extraction from Filenames

```python
# test_scripts/test_end_to_end.py
def extract_part_number(filename: str) -> str:
    # Extracts part number like "STM32F103RBT7" from "STM32F103RBT7.PDF"
    # Returns None if no match
```

### Page Detection Thresholds

| Score | Meaning |
|-------|---------|
| 0-4 | Not relevant / needs verification |
| 5 | Minimum confidence (default threshold) |
| 6-7 | High confidence - relevant pages |
| 8-10 | Very high confidence - definitive pinout pages |

### LLM Error Handling

The `_parse_llm_response()` method in `src/llm/client.py` handles:
1. Markdown code blocks: Removes ```json and ```
2. Null values: Converts to 0.0 instead of raising TypeError
3. Flexible pin numbers: Handles "1" and 1
4. Debug info: Shows response preview on failure

---

## Environment Variables

- `FASTCHAT_API_KEY` - Required for LLM extraction (set in .env)
- `FASTCHAT_MODEL` - Optional model override (default: llama-3)

---

## Dependencies

- `pdfplumber` - PDF parsing and extraction
- `openai` - FastChat API client (OpenAI-compatible)
- `python-dotenv` - Environment variable loading
- `nest_asyncio` - Async support for FastChat

---

## Notes for Future Development

### Model Generation (Not Implemented)
The `src/model_generator/` directory contains placeholder code for:
- `cadquery_builder.py` - Generate cadquery code from PinData
- `glb_exporter.py` - Export 3D models to GLB format

These are not integrated or tested yet.

---

## SCHEMATIC DESIGN TASK BREAKDOWN

**Status:** 🚧 Not Started

### Phase 1: Cadquery Integration (Foundation)

| Task | Description | Status |
|-------|-------------|--------|
| 1.1 | Install and verify cadquery works in the environment | ⏸️ Pending |
| 1.2 | Test basic cadquery code - create a simple box/cylinder | ⏸️ Pending |
| 1.3 | Understand cadquery API - workplane, cq, shapes | ⏸️ Pending |

### Phase 2: Pin Data to 3D Model (Core)

| Task | Description | Status |
|-------|-------------|--------|
| 2.1 | Design package geometry for each type (DIP, QFN, SOIC, TQFP, BGA) | ⏸️ Pending |
| 2.2 | Create pin cylinders/boxes positioned correctly for each package | ⏸️ Pending |
| 2.3 | Generate cadquery code from PinData object | ⏸️ Pending |
| 2.4 | Test with simple IC - NE555 (DIP-8) | ⏸️ Pending |

### Phase 3: GLB Export

| Task | Description | Status |
|-------|-------------|--------|
| 3.1 | Export cadquery model to GLB format | ⏸️ Pending |
| 3.2 | Verify GLB file is valid | ⏸️ Pending |
| 3.3 | Test with a 3D viewer to confirm pins are visible | ⏸️ Pending |

### Phase 4: Integration with CLI

| Task | Description | Status |
|-------|-------------|--------|
| 4.1 | Connect pin extraction → model generation → GLB export in main.py | ⏸️ Pending |
| 4.2 | Test end-to-end: PDF → PinData → GLB file | ⏸️ Pending |
| 4.3 | Clean up unused code (placeholder files) | ⏸️ Pending |

**Total: 12 Tasks**

### LLM Prompt Improvements
Consider these when improving extraction:
- Add more suffix code patterns for other manufacturers
- Implement content summarization for large datasheets (am623.pdf issue)
- Add multimodal support for diagram images

### Page Detection Enhancements
- Add BGA-specific patterns (ball maps, grid arrays)
- Improve diagram detection using image analysis
- Add package ordering information extraction

---

## CLI Usage

```bash
# Pin extraction only (currently working)
python -m src.main datasheet.pdf output.glb --verbose

# Model generation (not yet implemented - see SCHEMATIC DESIGN TASK BREAKDOWN)
# Full pipeline will be available after Phase 4 completion
python -m src.main datasheet.pdf output.glb
```
