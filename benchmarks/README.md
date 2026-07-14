# Extraction Benchmarks

This folder is an optional evaluation harness for the extraction pipeline.

It is intentionally separate from the runtime flow:
- user PDFs still go straight through `src/main.py`
- nothing in production imports this folder
- the files here are only for regression testing and score tracking

## Layout

- `benchmarks/manifest.json` lists the benchmark cases
- `benchmarks/cases/*.json` stores the expected answers for each case

## What A Case Contains

Each benchmark case records:
- source PDF path
- expected component name
- expected package family
- expected pin count
- expected variant, when relevant
- expected pinout pages
- expected pin map

## Current Seed Cases

- `ne555_soic8`
- `sn74hc595_soic16`
- `tps63060_wson10`

## How To Extend

To add a new benchmark:
1. Copy one of the case files in `benchmarks/cases/`
2. Replace the expected answers with the known-good output for the new PDF
3. Add the new case to `benchmarks/manifest.json`

Keep the benchmark set small and representative. The goal is regression detection, not exhaustive coverage.
