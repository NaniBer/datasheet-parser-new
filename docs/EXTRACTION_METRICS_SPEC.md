# Extraction Metrics Spec

## Goal
Define a small, objective scorecard for the pin extraction pipeline so we can measure improvements across different component families.

This spec applies to the extraction stages only:
- PDF page detection
- table/text/image extraction
- LLM pin parsing
- package normalization

It does not score GLB geometry generation.

## Core Metrics

### 1. Package Type Accuracy
Checks whether the extracted package family matches the expected family.

- Example: `DIP`, `SOIC`, `TSSOP`, `QFN`, `QFP`, `BGA`
- Score: `1` if the normalized package family is correct, otherwise `0`

### 2. Pin Count Accuracy
Checks whether the extracted pin count matches the expected pin count for the target variant.

- Example: `8`, `16`, `28`, `32`, `64`
- Score: `1` if exact, otherwise `0`

### 3. Variant Selection Accuracy
Checks whether the extractor selected the correct package variant when a datasheet contains multiple variants.

- Example: `SN74HC595DR` vs `SN74HC595PWR`
- Score: `1` if the chosen variant matches the benchmark target, otherwise `0`

### 4. Pin Map Accuracy
Measures how correctly pin numbers were mapped to pin names/functions.

Use set-based comparison over the expected and extracted pin pairs.

- Precision = correct extracted pin pairs / extracted pin pairs
- Recall = correct extracted pin pairs / expected pin pairs
- F1 = harmonic mean of precision and recall

Minimum recommended reporting:
- exact pin map match rate
- pin map F1

### 5. Table Extraction Success
Checks whether the pipeline extracted the pin table from pages that contain a clear pin table.

- Score: `1` if at least one expected pin table is extracted, otherwise `0`
- Also record whether extraction came from `OpenDataLoader` or `pdfplumber`

### 6. Noise Leakage Rate
Measures how much irrelevant content is reaching the LLM prompt.

Track:
- number of pages sent to the LLM
- number of pages that are actually pinout-relevant
- count of clearly irrelevant pages included

Recommended report:
- `irrelevant_page_count`
- `irrelevant_page_rate`

## Suggested Pass Criteria

An extraction run should be considered a pass when:
- package type is correct
- pin count is correct
- variant selection is correct, when applicable
- pin map F1 is at least `0.95`
- no clearly irrelevant pages are included in the prompt

## Benchmark Record Shape

Each benchmark case should store:

```json
{
  "pdf": "pdfs/74HC595_TI.pdf",
  "component_name": "SN74HC595DR",
  "expected_package_family": "SOIC",
  "expected_pin_count": 16,
  "expected_variant": "SN74HC595DR",
  "expected_pin_map": [
    {"number": 1, "name": "QH'"},
    {"number": 2, "name": "QG"},
    {"number": 3, "name": "QF"}
  ],
  "expected_pinout_pages": [3],
  "notes": "Multi-variant datasheet with a shared pinout table."
}
```

## Reporting Format

For each benchmark case, report:
- `package_type_accuracy`
- `pin_count_accuracy`
- `variant_accuracy`
- `pin_map_precision`
- `pin_map_recall`
- `pin_map_f1`
- `table_extraction_success`
- `irrelevant_page_count`
- `irrelevant_page_rate`

Also report an overall pass/fail using the pass criteria above.

## Implementation Note

The benchmark runner should score extraction output before geometry generation.
That keeps extraction regressions visible even if the GLB export still succeeds.
