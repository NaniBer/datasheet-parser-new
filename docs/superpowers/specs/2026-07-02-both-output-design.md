# Design: `--both` Flag — Single Command, Two GLB Outputs

**Date:** 2026-07-02
**Status:** Approved

---

## Problem

Producing both a schematic GLB and a PCB footprint GLB currently requires running the CLI twice, processing the PDF twice (page detection, content extraction, pin extraction).

## Goal

A single command that runs the pipeline once and writes both output files.

---

## CLI Interface

```bash
python3 -m src.main <input.pdf> <output.glb> --both
```

**Output naming:** strip the `.glb` extension (or append if missing) and add suffixes:

| Argument | Schematic output | Footprint output |
|---|---|---|
| `NE555.glb` | `NE555_schematic.glb` | `NE555_footprint.glb` |
| `output/NE555.glb` | `output/NE555_schematic.glb` | `output/NE555_footprint.glb` |
| `NE555` | `NE555_schematic.glb` | `NE555_footprint.glb` |

**Mutual exclusion:** `--both` and `--pcb-2d` cannot be used together. The CLI exits with an error if both are supplied.

---

## Internal Flow

The pipeline runs **once**. Both builders receive the same `pin_data` object.

```
PDF
 └─ detect_relevant_pages()
     └─ extract_content()
         └─ extract_pin_data()
             └─ select_package_variant()
                 ├─ build_pinout_diagram()  →  <base>_schematic.glb
                 └─ build_pcb_footprint()   →  <base>_footprint.glb
```

---

## Error Handling

- If one builder fails, the other still runs.
- Both results (success or error) are reported at the end.
- Exit code is non-zero if either output failed.

---

## Changes Required

### `src/main.py`

1. Add `--both` argument to the `argparse` parser.
2. Add mutual exclusion check: error if `--both` and `--pcb-2d` are both set.
3. Add helper `_both_output_paths(output: str) -> tuple[str, str]` that derives `_schematic.glb` and `_footprint.glb` paths from the base output argument.
4. Add `run_both_outputs()` function (or inline in `main()`) that calls both builders after pin extraction and reports results.

No changes needed to any other module.

---

## Tests

Add one integration test to `tests/test_suite.py`:

```
test_both_flag_produces_schematic_and_footprint_glb(monkeypatch, tmp_path)
```

- Input: `pdfs/DFN.pdf`
- Mock LLM (deterministic parser handles this PDF)
- Assert both `*_schematic.glb` and `*_footprint.glb` exist and are non-empty
