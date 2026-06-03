# Pin Extraction Root Cause and Test Plan

## Root Cause

The current extraction flow is too permissive when the source PDF is ambiguous.
Instead of treating ambiguity as a signal to validate or ask for help, the
pipeline often makes a quiet assumption and continues.

The main failure modes we have seen are:

- non-pin features being counted as pins, such as exposed thermal pads in DFN/QFN-style parts
- the wrong package variant being chosen when a datasheet contains multiple variants
- pin orientation being hard-coded in layout code instead of driven by explicit package metadata
- unknown package names falling back to generic geometry that is valid enough to render, but not always physically correct

The shared underlying issue is that the pipeline does not yet enforce a strict
contract between extraction, variant selection, and geometry. Each stage can
make assumptions for the next stage, which produces GLBs that look valid but are
semantically wrong.

## Fix Strategy

The fix should be applied in the shared pipeline, not as one-off handling for a
single PDF family.

1. Only count numbered electrical pins as pins.
2. Treat exposed pads, thermal pads, and similar package features as non-pin geometry unless explicitly numbered as a real pin.
3. Require explicit variant selection when the datasheet contains multiple valid packages.
4. Drive pin orientation from package metadata instead of hard-coded assumptions.
5. Validate the extracted package before geometry generation and fail closed when the data does not make sense.

## Test Plan

Run these checks after making extraction or layout changes.

### Fast Unit Tests

```bash
python3 -m pytest -q tests/test_content_extractor.py tests/test_pinout_filter.py tests/test_extraction_hardening.py
python3 -m pytest -q tests/test_variant_selection.py tests/test_unknown_package_fallback.py tests/test_benchmark_manifest.py
python3 -m pytest -q tests/test_glb_optimizer.py tests/test_pcb_footprint_hierarchy.py tests/test_reference_glb_hierarchy.py
```

### Targeted Smoke Tests

Use these to verify the exact failure modes we have already seen:

```bash
python3 -m src.main pdfs/DFN.pdf output/dfn_smoke.glb --pcb-2d --verbose
python3 -m src.main pdfs/MPU-6000-Datasheet1.pdf output/mpu_smoke.glb --pcb-2d --part-number MPU-6000 --verbose
python3 -m src.main pdfs/NE555.PDF output/ne555_smoke.glb --pcb-2d --part-number NE555 --verbose
python3 -m src.main pdfs/74HC595_TI.pdf output/hc595_smoke.glb --pcb-2d --part-number SN74HC595DR --verbose
```

### What To Check In Each Smoke Test

- pin count matches the datasheet
- no extra thermal-pad-style features are counted as pins
- the selected package variant matches the requested part number, when one is provided
- pin numbering is complete and unique
- the generated GLB hierarchy passes validation
- the package orientation looks correct for the family

### Pass Criteria

Treat the change as successful only if:

- the unit tests pass
- the smoke tests generate GLBs successfully
- the extracted pin counts match the expected package counts
- no known ambiguous package is silently mis-selected
- the output geometry looks correct for the target package family

