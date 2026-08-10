# Production-readiness plan — datasheet → schematic / footprint / 3D

**Date:** 2026-08-09
**Purpose:** the path from *assisted generator* (human reviews the watermark) to
*autonomous production* (outputs trustworthy enough to wire in unreviewed).

## Where we are (honest)

The pipeline generates all three outputs end-to-end from a PDF:
- **Schematic** (pinout symbol GLB) — hierarchy clean.
- **Footprint** (2D PCB GLB) — ~9 families, hierarchy clean; simplified pad math
  (not yet IPC-7351B RLP).
- **3D body** (STEP + GLB) — 7 package templates; **`verified` bodies now emit
  end-to-end** (e.g. ATmega TQFP-32, dims from text). Vision endpoint
  (`qwen.ideeza.com/describe_image/`) is live.

**Accuracy (pin count, the gating metric), 2026-08-09 baseline:**
- Overall: 66% (84/127) — dragged down by modules that fail by design.
- **In-scope IC-only: ~75%** (modules excluded as footprint-unsupported).
- Confidence: only a minority come out fully `validated` — "confidence, not
  coverage" is the real story.

Measurement gate: `tools/run_full_flow_eval.py` (parallel + watchdog) — the
repeatable validation harness. Re-run it to confirm every fix; trust it, not
single noisy runs (the LLM ignores `seed`, ±~6 noise).

## Phases (by leverage)

### Phase 1 — Correctness: pin accuracy 75% → ~90% (IC scope)
The in-scope IC failures cluster into a few systematic classes:
- **C+D wrong-variant (~10 parts, the dominant lever)** — one root cause:
  the ordered part-number package suffix isn't used to select the variant /
  ground the pin count. Design: `docs/variant-grounding-design.md`.
  - Done: reject package labels as part-number candidates (commit 6f05821).
  - Remaining: per-vendor suffix→pin-count decode + reconcile (Microchip, ADI,
    Winbond, ST, TI-sibling). Core-path change → build per vendor, gate re-run
    each step.
- **E tab / exposed-pad off-by-one (~4)** — thermal tab counted as a signal pin
  (or missed): ADXRS645 15↔16, BD9778 7↔8, TDA7850, BQ25570 20↔16.
- **F big-MCU under-read / timeout (~5)** — MKL/dsPIC/AVR: large docs, vision or
  table-parse gaps; some legitimately slow (watchdog handles the hang).
- Data bug: `52_PIC16F1512` corpus PDF is actually an MCP9701 — replace it.

### Phase 2 — Autonomy: no manual steering
- Auto package-variant selection (no `--part-number`) — falls out of Phase-1 C.
- Dimension confidence: make `verified` the majority (fix vision page-matching
  so graphical-outline parts like TI SOICs get verified dims, not text-only).

### Phase 3 — Coverage & reachability
- Power-tab / BGA end-to-end (footprint path or body-without-footprint; templates
  + family recognition already done).
- Broken-font PDFs (MCP101, MCP3208 dim page) — OCR fallback or clean refusal.
- Discretes track (diodes/transistors/bridges/crystals) — dedicated 2–3-terminal
  modeling with polarity markings; currently ~67% and out of the IC target.

### Phase 4 — Validation gate (the actual "production" bar)
- Agree the acceptance set (original 158-part set, or formalize the 148 corpus).
- In-pipeline deterministic verify gate (not just batch eval).
- Optional vision-verify loop: render the generated body, compare to the
  datasheet drawing (confidence signal beyond dimensional checks).
- CI accuracy threshold.

### Phase 5 — Hardening & ops
- IPC-7351B-faithful footprint math (if standards compliance required).
- Model caching/versioning; headless `cadquery-ocp` novtk wheel; GLB payload
  tuning. Determinism: deterministic LLM backend or majority-voting.

## Cross-cutting risk
The text LLM ignores `seed` (±~6 run-to-run noise). Autonomous production needs
either a deterministic backend or majority-voting; until then, every accuracy
claim must come from the gate (multi-run), not a single run.

## Suggested sequence
Phase 1 (C+D variant grounding → E → F) → Phase 2 → Phase 4 acceptance gate.
Phases 3 and 5 in parallel as capacity allows.
