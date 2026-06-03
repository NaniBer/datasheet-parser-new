# Variant Selection Spec

## Goal

When a datasheet contains multiple package variants, the runtime should choose
the most likely single variant and generate one GLB by default.

The flow must work for arbitrary PDFs, not just benchmark files.

## Default Behavior

1. If the user supplies `--part-number`, use that as the primary target.
2. If no part number is supplied, infer a conservative hint from the filename
   and extracted text.
3. Score all candidate variants found in the datasheet.
4. Select the best-supported variant only if it is clearly better than the rest.
5. If no variant is clearly best, stop and ask for clarification instead of
   guessing.

## Why One Variant Per Run

A GLB represents one physical footprint, so the output should map to one
package variant.

Generating all variants by default would:

- create duplicate or ambiguous output files
- make validation harder
- increase the chance of quietly shipping the wrong footprint

## Selection Inputs

Variant scoring should use:

- explicit user part number
- filename hint
- extracted part numbers in text and tables
- package family names
- pin count consistency
- page confidence and table quality
- header/ordering-code matches

## Candidate Ranking Rules

The runtime should rank variants using a simple priority order:

1. Exact user-supplied part number match
2. Exact or near-exact match in extracted text
3. Package family match with pin-count agreement
4. Best table/header evidence
5. Best remaining confidence score

If two candidates are close, prefer not to guess. Ask for the specific target
variant or return an ambiguity error.

## Validation Rules After Selection

Before generating geometry, validate the chosen variant:

- package type is known and normalized
- pin count is positive
- pin numbers are unique
- pin numbering is a complete `1..N` sequence
- extracted pin map is internally consistent

If validation fails, retry once with corrective feedback. If the retry fails,
report the failure clearly.

## Runtime Contract

Normal CLI mode should return one selected package and one GLB.

Internal extraction may still discover multiple packages and keep them in
memory, but the geometry stage should only consume one selected variant.

## Optional Future Mode

A separate explicit batch mode may be added later, for example:

- `--all-variants`

In that mode, the workflow may generate one GLB per validated package variant.
This should remain opt-in only.

## Logging Expectations

When variant selection runs, the pipeline should log:

- all candidate variants considered
- the score for each candidate
- the selected variant
- why the selected variant won
- why any close candidates were rejected

This makes it easier to debug multi-variant datasheets without changing the
core runtime behavior.

