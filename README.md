# Datasheet Parser

Extract pin data from electronic component datasheets and generate 3D CAD models (GLB format).

## Overview

This tool reads PDF datasheets for electronic components, identifies relevant pinout pages using a hybrid detection system (rules-based + LLM fallback), extracts pin information, and generates 3D CAD models using cadquery.

## Features

- **Hybrid Page Detection**: Fast rules-based detection with LLM fallback for edge cases
- **Multiple Package Support**: DIP, QFN, SOIC, TSSOP, and extensible for more
- **LLM Integration**: Placeholder for your chosen LLM API (OpenAI, Anthropic, etc.)
- **3D Model Generation**: Automatic cadquery code generation from pin data
- **Multiple Export Formats**: GLB, STEP, STL

## Installation

### Prerequisites

- Python 3.8 or higher
- Your chosen LLM API key (see below)

### Install Dependencies

```bash
pip install -r requirements.txt
```

For GLB export support:
```bash
pip install trimesh pygltflib
```

For LLM integration, install your chosen SDK:
```bash
# For OpenAI
pip install openai

# For Anthropic Claude
pip install anthropic
```

## Usage

### Basic Usage

```bash
python -m src.main datasheet.pdf output.glb
```

### With LLM API Key

```bash
# Using command-line argument
python -m src.main datasheet.pdf output.glb --api-key YOUR_API_KEY

# Using environment variable
export DATASHEET_PARSER_API_KEY=YOUR_API_KEY
python -m src.main datasheet.pdf output.glb
```

### Advanced Options

```bash
# Specify LLM model
python -m src.main datasheet.pdf output.glb --model gpt-4

# Lower confidence threshold for page detection
python -m src.main datasheet.pdf output.glb --min-confidence 3

# Verify ambiguous pages with LLM
python -m src.main datasheet.pdf output.glb --verify-ambiguity

# Export to different format
python -m src.main datasheet.pdf output.step --format step

# Verbose output
python -m src.main datasheet.pdf output.glb --verbose
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CLI Entry Point                           │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│       Hybrid Page Detection (pdf_extractor)                 │
│  Phase 1: Rules-Based Candidate Detection                    │
│  Phase 2: LLM Fallback for Edge Cases                        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│          Page Content Extractor                              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              LLM Pin Extractor (llm)                        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│          Model Generator (model_generator)                  │
└─────────────────────────────────────────────────────────────┘
```

## Project Structure

```
datasheet-parser-new/
├── src/
│   ├── main.py                 # CLI entry point
│   ├── models/
│   │   └── pin_data.py         # Data models
│   ├── pdf_extractor/
│   │   ├── page_detector.py    # Hybrid page detection
│   │   └── content_extractor.py # Content extraction
│   ├── llm/
│   │   ├── client.py           # LLM API client (you provide)
│   │   └── page_verifier.py    # LLM page verification
│   ├── model_generator/
│   │   ├── cadquery_builder.py # Generate cadquery code
│   │   └── glb_exporter.py     # Export to GLB/STEP/STL
│   └── utils/
│       └── package_detector.py # Detect package types
├── tests/                      # Tests
├── datasheet/                  # Sample datasheets
├── pyproject.toml
├── requirements.txt
└── README.md
```

## LLM Integration

The `src/llm/client.py` file contains a placeholder LLM client. You need to implement this with your chosen LLM API.

### Example Implementation (OpenAI)

```python
import openai
from ..models.pin_data import PinData, Pin, PackageInfo

class LLMClient:
    def __init__(self, api_key: str, model: str = "gpt-4"):
        openai.api_key = api_key
        self.model = model

    def extract_pin_data(self, content: str, images=None, **kwargs) -> PinData:
        prompt = self._build_extraction_prompt(content, images is not None)

        response = openai.ChatCompletion.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a technical data extractor."},
                {"role": "user", "content": prompt}
            ],
            temperature=0
        )

        return self._parse_llm_response(response.choices[0].message.content)
```

## Supported Package Types

- **DIP** (Dual Inline Package) - e.g., ATMEGA328P, 555 timer
- **QFN** (Quad Flat No-leads) - e.g., MPU6050, Bluetooth modules
- **SOIC** (Small Outline IC) - e.g., op-amps, regulators
- **TSSOP** (Thin Shrink Small Outline) - e.g., modern MCUs

## Extending the System

### Adding New Package Types

1. Add package detection to `src/utils/package_detector.py`
2. Add cadquery geometry to `src/model_generator/cadquery_builder.py`
3. Add page detection patterns to `src/pdf_extractor/page_detector.py`

### Improving Page Detection

Add new detection patterns in `page_detector.py`:
```python
PINOUT_HEADING_PATTERNS = [
    # Existing patterns...
    r"ball\s*map",  # For BGA packages
]
```

## License

MIT License

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.
