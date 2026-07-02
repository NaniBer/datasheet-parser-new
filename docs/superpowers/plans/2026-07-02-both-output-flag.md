# `--both` Output Flag Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `--both` flag to the CLI that runs the extraction pipeline once and writes both a schematic GLB and a PCB footprint GLB.

**Architecture:** Two changes to `src/main.py` only — a pure path-derivation helper and a `both_mode` branch inside `process_datasheet()`. The existing pipeline (detect → extract → pin extraction) is unchanged; only the final builder step diverges.

**Tech Stack:** Python 3.9, argparse, existing `build_schematic_from_pin_data` and `build_pcb_2d_schematic` builders already imported in `src/main.py`.

## Global Constraints

- Only `src/main.py` and `tests/test_suite.py` are modified.
- `--both` and `--pcb-2d` are mutually exclusive; the CLI must print an error and exit 1 if both are supplied.
- If one builder fails the other still runs; exit code is non-zero if either failed.
- Output naming: strip `.glb` suffix (or treat as stem if no suffix), append `_schematic.glb` / `_footprint.glb`.
- Run all tests with: `python3 -m pytest tests/test_suite.py -v`

---

### Task 1: Output path helper

**Files:**
- Modify: `src/main.py` — add `_both_output_paths()` after the `setup_output_path` function (~line 106)
- Modify: `tests/test_suite.py` — add unit tests in a new `# OUTPUT PATH HELPER` section before the existing sections

**Interfaces:**
- Produces: `_both_output_paths(output: str) -> tuple[str, str]`
  - Returns `(schematic_path, footprint_path)` as strings
  - Imported nowhere outside `main.py`; used in Task 2

- [ ] **Step 1: Write the failing tests**

Add this block to `tests/test_suite.py` after the imports at the top (after the `ROOT` / `MANIFEST_PATH` constants):

```python
# ===========================================================================
# 0. OUTPUT PATH HELPER
# ===========================================================================

from src.main import _both_output_paths


def test_both_output_paths_strips_glb_extension():
    schematic, footprint = _both_output_paths("NE555.glb")
    assert schematic == "NE555_schematic.glb"
    assert footprint == "NE555_footprint.glb"


def test_both_output_paths_preserves_directory():
    schematic, footprint = _both_output_paths("output/NE555.glb")
    assert schematic == "output/NE555_schematic.glb"
    assert footprint == "output/NE555_footprint.glb"


def test_both_output_paths_no_extension():
    schematic, footprint = _both_output_paths("NE555")
    assert schematic == "NE555_schematic.glb"
    assert footprint == "NE555_footprint.glb"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest tests/test_suite.py::test_both_output_paths_strips_glb_extension tests/test_suite.py::test_both_output_paths_preserves_directory tests/test_suite.py::test_both_output_paths_no_extension -v
```

Expected: `ImportError: cannot import name '_both_output_paths'`

- [ ] **Step 3: Implement `_both_output_paths` in `src/main.py`**

Add this function immediately after `setup_output_path` (~line 106), before the `# Pipeline Functions` section:

```python
def _both_output_paths(output: str) -> tuple:
    """Derive schematic and footprint GLB paths from a base output argument.

    Examples:
        "NE555.glb"        -> ("NE555_schematic.glb", "NE555_footprint.glb")
        "output/NE555.glb" -> ("output/NE555_schematic.glb", "output/NE555_footprint.glb")
        "NE555"            -> ("NE555_schematic.glb", "NE555_footprint.glb")
    """
    p = Path(output)
    stem = p.stem
    parent = p.parent
    return (
        str(parent / f"{stem}_schematic.glb"),
        str(parent / f"{stem}_footprint.glb"),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_suite.py::test_both_output_paths_strips_glb_extension tests/test_suite.py::test_both_output_paths_preserves_directory tests/test_suite.py::test_both_output_paths_no_extension -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add src/main.py tests/test_suite.py
git commit -m "feat: add _both_output_paths helper with tests"
```

---

### Task 2: `--both` flag, mutual exclusion, and dual-builder pipeline

**Files:**
- Modify: `src/main.py`
  - `parse_arguments()` — add `--both` argument
  - `main()` — add mutual exclusion check
  - `process_datasheet()` — add `both_mode: bool = False` parameter and dual-builder branch
- Modify: `tests/test_suite.py` — add integration test at the end of section 17

**Interfaces:**
- Consumes: `_both_output_paths(output: str) -> tuple[str, str]` from Task 1
- Consumes: `build_schematic_from_pin_data(pin_data, output_path, custom_layout, part_number, package_index)` — already imported
- Consumes: `build_pcb_2d_schematic(package_type, pin_count, component_name, pin_data, output_path, custom_layout)` — already imported
- Consumes: `pin_data_to_builder_format(pin_data, part_number, package_index)` — already imported

- [ ] **Step 1: Write the failing integration test**

Add this test at the end of the `# FULL PIPELINE` section (section 17) in `tests/test_suite.py`:

```python
@pytest.mark.integration
def test_both_flag_produces_schematic_and_footprint_glb(monkeypatch, tmp_path):
    """--both mode should write *_schematic.glb and *_footprint.glb in one pipeline run."""
    monkeypatch.setattr("src.main.LLMClient.extract_pin_data", _no_llm_call)

    base = tmp_path / "dfn_both.glb"
    schematic_path = tmp_path / "dfn_both_schematic.glb"
    footprint_path = tmp_path / "dfn_both_footprint.glb"

    candidates = detect_relevant_pages("pdfs/DFN.pdf", min_confidence=3, verbose=False)
    content = extract_content("pdfs/DFN.pdf", candidates, verbose=False)
    pin_data = extract_pin_data(
        content, api_key="dummy", model="dummy",
        part_number="TPS62160DSG", verbose=False,
    )

    from src.main import process_datasheet_both
    result = process_datasheet_both(pin_data=pin_data, output_path=base)

    assert result is True
    assert schematic_path.exists(), "schematic GLB not created"
    assert footprint_path.exists(), "footprint GLB not created"
    assert schematic_path.stat().st_size > 0
    assert footprint_path.stat().st_size > 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/test_suite.py::test_both_flag_produces_schematic_and_footprint_glb -v
```

Expected: `ImportError: cannot import name 'process_datasheet_both'`

- [ ] **Step 3: Add `process_datasheet_both()` to `src/main.py`**

Add this function after `process_datasheet()` (~line 786), before the `# CLI Entry Point` section:

```python
def process_datasheet_both(pin_data: PinData, output_path: Path,
                            custom_layout=None, part_number: Optional[str] = None,
                            package_index: Optional[int] = None,
                            verbose: bool = False) -> bool:
    """Run both schematic and PCB footprint builders on already-extracted pin data.

    Args:
        pin_data: Extracted PinData (from extract_pin_data)
        output_path: Base output path — suffixes _schematic.glb / _footprint.glb are added
        custom_layout: Optional Vision API layout dict
        part_number: Optional part number for variant selection
        package_index: Optional zero-based package variant index
        verbose: Enable verbose output

    Returns:
        True if both outputs were generated successfully, False otherwise
    """
    schematic_str, footprint_str = _both_output_paths(str(output_path))
    schematic_path = Path(schematic_str)
    footprint_path = Path(footprint_str)

    setup_output_path(schematic_path)
    setup_output_path(footprint_path)

    # --- Schematic (3D pinout diagram) ---
    schematic_ok = False
    try:
        schematic_ok = bool(build_schematic_from_pin_data(
            pin_data=pin_data,
            output_path=schematic_str,
            custom_layout=custom_layout,
            part_number=part_number,
            package_index=package_index,
        ))
        if verbose:
            print(f"Schematic: {schematic_str}")
    except Exception as e:
        print(f"Error generating schematic: {e}")
        if verbose:
            import traceback
            traceback.print_exc()

    # --- PCB footprint (2D) ---
    footprint_ok = False
    try:
        package_type, pin_count, _, pin_data_list = pin_data_to_builder_format(
            pin_data,
            part_number=part_number,
            package_index=package_index,
        )
        footprint_ok = bool(build_pcb_2d_schematic(
            package_type=package_type,
            pin_count=pin_count,
            component_name=pin_data.component_name,
            pin_data=pin_data_list,
            output_path=footprint_str,
            custom_layout=custom_layout,
        ))
        if verbose:
            print(f"Footprint: {footprint_str}")
    except Exception as e:
        print(f"Error generating footprint: {e}")
        if verbose:
            import traceback
            traceback.print_exc()

    if not schematic_ok:
        print(f"Failed to generate schematic: {schematic_str}")
    if not footprint_ok:
        print(f"Failed to generate footprint: {footprint_str}")

    return schematic_ok and footprint_ok
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/test_suite.py::test_both_flag_produces_schematic_and_footprint_glb -v
```

Expected: `1 passed`

- [ ] **Step 5: Add `--both` to `parse_arguments()` in `src/main.py`**

After the `--pcb-2d` argument block (~line 865), add:

```python
    parser.add_argument(
        "--both",
        action="store_true",
        help="Generate both schematic and PCB footprint GLB files. "
             "Output argument is used as base name: "
             "NE555.glb -> NE555_schematic.glb + NE555_footprint.glb. "
             "Cannot be combined with --pcb-2d."
    )
```

Also update the epilog examples string inside `parse_arguments()`. Find the `epilog="""` block and add before the closing `"""`:

```
  # Generate both schematic and footprint in one run
  python -m src.main datasheet.pdf NE555.glb --both
```

- [ ] **Step 6: Add mutual exclusion check and `--both` dispatch in `main()`**

Replace the current `main()` body in `src/main.py` with:

```python
def main():
    """Main CLI entry point."""
    args = parse_arguments()

    # Mutual exclusion: --both and --pcb-2d cannot be used together
    if args.both and args.pcb_2d:
        print("Error: --both and --pcb-2d are mutually exclusive. "
              "Use --both to generate both outputs, or --pcb-2d for footprint only.")
        sys.exit(1)

    # Validate input file
    input_path = Path(args.input)
    validate_input_file(input_path)

    # Get API key
    api_key = get_api_key(args)

    # Setup output path
    output_path = Path(args.output)
    setup_output_path(output_path)

    if args.both:
        # Run pipeline once, then call both builders
        adjusted_min_confidence = get_dynamic_min_confidence(input_path, args.min_confidence, args.verbose)
        candidates = detect_relevant_pages(str(input_path), adjusted_min_confidence, args.verbose)
        content = extract_content(str(input_path), candidates, args.verbose)

        resolved_part_number = args.part_number or infer_part_number_hint(
            content.text_content, source_name=input_path.name
        )

        pin_data = extract_pin_data(
            content, api_key, args.model, args.verbose,
            part_number=resolved_part_number,
        )

        success = process_datasheet_both(
            pin_data=pin_data,
            output_path=output_path,
            part_number=resolved_part_number,
            package_index=args.package_index,
            verbose=args.verbose,
        )
        if not success:
            sys.exit(1)
    else:
        # Single output mode (existing behaviour)
        process_datasheet(
            input_path=input_path,
            output_path=output_path,
            api_key=api_key,
            model=args.model,
            part_number=args.part_number,
            layout_mode=args.layout_mode,
            pcb_2d_mode=args.pcb_2d,
            min_confidence=args.min_confidence,
            verbose=args.verbose,
            package_index=args.package_index,
        )
```

- [ ] **Step 7: Run the full test suite to confirm nothing is broken**

```bash
python3 -m pytest tests/test_suite.py -v
```

Expected: `62 passed` (60 existing + 3 path helper + 1 integration — but benchmark parametrize adds more; total will be ≥ 62 with 0 failures)

- [ ] **Step 8: Smoke-test the CLI help to confirm `--both` appears**

```bash
python3 -m src.main --help
```

Expected output includes:
```
  --both        Generate both schematic and PCB footprint GLB files.
```

- [ ] **Step 9: Commit**

```bash
git add src/main.py tests/test_suite.py
git commit -m "feat: add --both flag to generate schematic and footprint in one pass"
```

- [ ] **Step 10: Push**

```bash
git push origin main
```
