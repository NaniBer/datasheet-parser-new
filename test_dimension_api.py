"""
Two-phase dimension extraction tester.

Phase 1: Scan all pages quickly to find which ones have dimension drawings.
Phase 2: Full extraction on dimension pages only.
Phase 3: Cross-check extracted values against known reference specs.

Usage:
    python3 test_dimension_api.py --pdf pdfs/74HC595_TI.pdf
    python3 test_dimension_api.py --pdf pdfs/FT232R.pdf
    python3 test_dimension_api.py --pdf pdfs/ATmega328p.pdf
"""

import argparse
import io
import json
import re
import sys
import time

import fitz  # PyMuPDF
import requests

API_URL = "https://qwen.ideeza.com/describe_image/"

# ---------------------------------------------------------------------------
# Known reference dimensions for cross-checking
# Source: manufacturer datasheets / JEDEC standards
# Format: {package_key: {dimension: (min, typ, max), ...}, unit: "mm"}
# ---------------------------------------------------------------------------
REFERENCE_SPECS = {
    "SOIC-16": {
        "unit": "mm",
        "dims": {
            "E":  (10.00, 10.30, 10.65),   # body width (wide SOIC)
            "e":  (1.27,  1.27,  1.27),    # pitch
            "D":  (9.80,  9.90,  10.00),   # body length
            "A":  (2.35,  2.50,  2.65),    # total height
            "A1": (0.10,  None,  0.25),    # standoff
            "b":  (0.31,  None,  0.51),    # pin width
            "L":  (0.40,  None,  1.27),    # pin length
        }
    },
    "TSSOP-16": {
        "unit": "mm",
        "dims": {
            "E":  (6.20,  6.40,  6.60),
            "e":  (0.65,  0.65,  0.65),
            "D":  (4.90,  5.00,  5.10),
            "A":  (1.05,  None,  1.20),
            "b":  (0.19,  None,  0.30),
            "L":  (0.45,  None,  0.75),
        }
    },
    "DIP-28": {
        "unit": "mm",
        "dims": {
            "e":  (2.54,  2.54,  2.54),
            "E":  (7.62,  7.62,  7.62),   # row spacing
            "D":  (34.54, None,  35.05),  # body length
            "b":  (0.36,  None,  0.56),
            "L":  (3.05,  None,  3.55),
        }
    },
    "SSOP-28": {
        "unit": "mm",
        "dims": {
            "e":  (0.65,  0.65,  0.65),
            "E":  (7.40,  7.80,  8.20),
            "D":  (9.70,  9.90,  10.10),
            "A":  (1.75,  None,  2.05),
            "b":  (0.22,  None,  0.38),
            "L":  (0.55,  None,  0.95),
        }
    },
    "QFN-32": {
        "unit": "mm",
        "dims": {
            "e":  (0.50,  0.50,  0.50),
            "D":  (4.90,  5.00,  5.10),
            "E":  (4.90,  5.00,  5.10),
            "A":  (0.80,  None,  1.00),
            "b":  (0.18,  None,  0.30),
        }
    },
}

# Aliases to normalise package names coming from the API
PACKAGE_ALIASES = {
    "soic16": "SOIC-16", "soic-16": "SOIC-16", "so16": "SOIC-16",
    "tssop16": "TSSOP-16", "tssop-16": "TSSOP-16",
    "dip28": "DIP-28", "pdip28": "DIP-28", "pdip-28": "DIP-28",
    "ssop28": "SSOP-28", "ssop-28": "SSOP-28",
    "qfn32": "QFN-32", "qfn-32": "QFN-32",
}

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

SCAN_PROMPT = """Look at this page and classify it. Answer ONLY with JSON, no other text.

If it contains an IC package dimension drawing (body outline + lead dimensions like A, A1, b, D, E, e, L):
{"has_dimensions": true, "page_type": "package_drawing", "package_type": "SOIC-16"}

If it contains a tape/reel or carrier drawing (reel dimensions like A0, B0, K0, P1, W, feed hole pitch):
{"has_dimensions": true, "page_type": "tape_reel", "package_type": "SOIC-16"}

If it contains something else (electrical specs, pinout table, ordering info, text, etc.):
{"has_dimensions": false, "page_type": "other"}

Only classify as "package_drawing" if you can see a mechanical outline of the IC package with labeled lead/body dimensions."""

# Fine-pitch packages that need a package-aware prompt + higher DPI
FINE_PITCH_KEYWORDS = ["tssop", "ssop", "qfn", "qfp", "lqfp", "tqfp", "vssop", "msop"]


def is_fine_pitch(package_type: str) -> bool:
    key = package_type.lower()
    return any(kw in key for kw in FINE_PITCH_KEYWORDS)


def build_extract_prompt(package_type: str) -> str:
    """Build a generic or package-aware extraction prompt depending on package type."""
    if is_fine_pitch(package_type):
        return f"""You are an expert at reading mechanical package dimension drawings from electronic component datasheets.

This page shows a {package_type} dimension drawing.
{package_type} is a fine-pitch package — the lead pitch (e) is typically 0.65mm or less, NOT 1.27mm.
The body is narrow (typically 4–7mm wide), NOT ~10mm like SOIC.

Read the actual numbers from the drawing carefully. Do NOT substitute default SOIC values.

Extract every labeled dimension and return ONLY valid JSON:
{{
  "package_type": "{package_type}",
  "unit": "mm",
  "dimensions": {{
    "A":  {{"min": "1.05", "max": "1.20"}},
    "b":  {{"min": "0.19", "max": "0.30"}},
    "D":  {{"min": "4.90", "max": "5.10"}},
    "E":  {{"min": "6.20", "max": "6.60"}},
    "e":  "0.65",
    "L":  {{"min": "0.45", "max": "0.75"}}
  }},
  "notes": "any observations"
}}

Rules:
- Read values directly from the drawing — do not guess or use assumed values
- The pitch e should match what is printed on the drawing (likely 0.65mm)
- Use a single string value when only one value is shown
- Return ONLY JSON"""
    else:
        return """You are an expert at reading mechanical package dimension drawings from electronic component datasheets.

Extract every labeled dimension from this drawing.

Return ONLY valid JSON:
{
  "package_type": "SOIC-16",
  "unit": "mm",
  "dimensions": {
    "A":  {"min": "2.35", "max": "2.65"},
    "A1": {"min": "0.10", "max": "0.25"},
    "b":  {"min": "0.31", "max": "0.51"},
    "D":  {"min": "9.80", "max": "10.00"},
    "E":  {"min": "10.00", "max": "10.65"},
    "e":  "1.27",
    "L":  {"min": "0.40", "max": "1.27"}
  },
  "notes": "any observations"
}

Rules:
- Use a single string value (not min/max) when only one value is shown
- Capture ALL labeled dimensions in the drawing
- Return ONLY JSON"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def render_page(pdf_path: str, page_number: int, dpi: int = 150) -> bytes:
    doc = fitz.open(pdf_path)
    page = doc[page_number]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    return pix.tobytes("png")


def call_api(image_bytes: bytes, prompt: str) -> str:
    """POST image to API. Returns the raw description string."""
    files = {"file": ("page.png", io.BytesIO(image_bytes), "image/png")}
    data = {"text": prompt}
    response = requests.post(API_URL, files=files, data=data, timeout=120)
    response.raise_for_status()
    raw = response.json()
    # Response is {"description": "..."}
    return raw.get("description", str(raw))


def parse_json_from_text(text: str):
    """Extract JSON from a string that may contain markdown fences."""
    if isinstance(text, dict):
        return text
    # Strip markdown fences
    match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
    if match:
        text = match.group(1)
    # Try to find a JSON object
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    # Try direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def normalise_package(name: str):
    """Normalise a package name to a REFERENCE_SPECS key."""
    key = name.lower().replace(" ", "")
    return PACKAGE_ALIASES.get(key)


def to_float(v):
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Completeness scoring + deduplication
# ---------------------------------------------------------------------------

def completeness_score(extracted: dict) -> float:
    """
    Score an extracted dimension result by how complete it is.
    - dim with min+max pair  → 1.0 point
    - dim with single value  → 0.5 points (expected for fixed dims like pitch)
    - missing dim            → 0 points
    Higher is better.
    """
    dims = extracted.get("dimensions", {})
    if not dims:
        return 0.0
    total = 0.0
    for v in dims.values():
        if isinstance(v, dict):
            has_min = v.get("min") and str(v.get("min")).strip() not in ("", "-", "- ")
            has_max = v.get("max") and str(v.get("max")).strip() not in ("", "-", "- ")
            if has_min and has_max:
                total += 1.0
            elif has_min or has_max:
                total += 0.5
        elif v:
            total += 0.5
    return total


def dims_fingerprint(extracted: dict) -> str:
    """Stable string fingerprint of a dimension dict for deduplication."""
    dims = extracted.get("dimensions", {})
    return json.dumps(dims, sort_keys=True)


def pick_best_per_package(candidates: list[dict]) -> list[dict]:
    """
    Given a list of {page, data} extraction results:
    1. Group by package_type.
    2. Within each group, deduplicate identical results.
    3. Pick the highest completeness score.
    Returns one winner per package type.
    """
    groups = {}
    for entry in candidates:
        data = entry.get("data")
        if not data:
            continue
        pkg = data.get("package_type", "unknown").upper()
        groups.setdefault(pkg, []).append(entry)

    winners = []
    for pkg, entries in groups.items():
        # Deduplicate by fingerprint
        seen = set()
        unique = []
        for e in entries:
            fp = dims_fingerprint(e["data"])
            if fp not in seen:
                seen.add(fp)
                unique.append(e)

        # Pick highest completeness score
        best = max(unique, key=lambda e: completeness_score(e["data"]))
        score = completeness_score(best["data"])
        dupes = len(entries) - len(unique)
        print(f"  {pkg}: {len(entries)} page(s) found, "
              f"{dupes} duplicate(s) removed, "
              f"best is page {best['page'] + 1} (score {score:.1f})")
        winners.append(best)

    return winners


# ---------------------------------------------------------------------------
# Cross-check
# ---------------------------------------------------------------------------

def cross_check(extracted: dict) -> list[dict]:
    """
    Compare extracted dimensions against reference specs.
    Returns a list of result rows for display.
    """
    pkg_raw = extracted.get("package_type", "")
    pkg_key = normalise_package(pkg_raw)
    results = []

    if not pkg_key:
        results.append({
            "dimension": "—",
            "extracted": "—",
            "reference": "—",
            "status": f"No reference spec for '{pkg_raw}'"
        })
        return results

    ref = REFERENCE_SPECS[pkg_key]
    extracted_dims = extracted.get("dimensions", {})

    for dim_name, ref_range in ref["dims"].items():
        ref_min, ref_typ, ref_max = ref_range
        raw = extracted_dims.get(dim_name) or extracted_dims.get(dim_name.lower())

        if raw is None:
            results.append({
                "dimension": dim_name,
                "extracted": "MISSING",
                "reference": f"{ref_min}–{ref_max} mm",
                "status": "⚠ not extracted"
            })
            continue

        # Parse extracted value
        if isinstance(raw, dict):
            ext_min = to_float(raw.get("min"))
            ext_max = to_float(raw.get("max"))
            ext_str = f"{raw.get('min', '?')}–{raw.get('max', '?')}"
        else:
            ext_min = ext_max = to_float(raw)
            ext_str = str(raw)

        # Check if within reference range
        ok = True
        if ref_min is not None and ext_min is not None:
            if abs(ext_min - ref_min) > 0.15:
                ok = False
        if ref_max is not None and ext_max is not None:
            if abs(ext_max - ref_max) > 0.15:
                ok = False

        results.append({
            "dimension": dim_name,
            "extracted": ext_str,
            "reference": f"{ref_min}–{ref_max} mm",
            "status": "✓ OK" if ok else "✗ MISMATCH"
        })

    return results


# ---------------------------------------------------------------------------
# Main phases
# ---------------------------------------------------------------------------

def phase1_scan(pdf_path: str, dpi: int = 120) -> list[dict]:
    """Scan all pages and return list of {page, has_dimensions, package_type}."""
    doc = fitz.open(pdf_path)
    page_count = len(doc)
    doc.close()

    print(f"\nPhase 1: Scanning {page_count} pages for dimension drawings...")
    print("-" * 60)

    found = []
    for i in range(page_count):
        sys.stdout.write(f"\r  Page {i+1}/{page_count} ...")
        sys.stdout.flush()

        image_bytes = render_page(pdf_path, i, dpi=dpi)
        raw = call_api(image_bytes, SCAN_PROMPT)
        parsed = parse_json_from_text(raw)

        if parsed and parsed.get("has_dimensions"):
            page_type = parsed.get("page_type", "unknown")
            pkg = parsed.get("package_type", "unknown")
            if page_type == "package_drawing":
                print(f"\r  Page {i+1}: FOUND package drawing ({pkg})")
                found.append({"page": i, "package_type": pkg})
            else:
                print(f"\r  Page {i+1}: skipped ({page_type})")

        time.sleep(0.3)  # be gentle with the API

    print(f"\r  Scan complete. Found {len(found)} dimension page(s).{' ' * 20}")
    return found


def phase2_extract(pdf_path: str, dimension_pages: list[dict], dpi: int = 200) -> list[dict]:
    """Full extraction on each dimension page, then deduplicate and pick best per package."""
    print(f"\nPhase 2: Extracting dimensions from {len(dimension_pages)} page(s)...")
    print("-" * 60)

    all_candidates = []
    for entry in dimension_pages:
        page_num = entry["page"]
        pkg_type = entry["package_type"]
        effective_dpi = 300 if is_fine_pitch(pkg_type) else dpi
        prompt = build_extract_prompt(pkg_type)
        print(f"\n  Extracting page {page_num + 1} ({pkg_type}, {effective_dpi} DPI)...")

        image_bytes = render_page(pdf_path, page_num, dpi=effective_dpi)
        raw = call_api(image_bytes, prompt)
        parsed = parse_json_from_text(raw)

        if parsed:
            score = completeness_score(parsed)
            print(f"  Package: {parsed.get('package_type', '?')}  "
                  f"Unit: {parsed.get('unit', '?')}  "
                  f"Dims: {len(parsed.get('dimensions', {}))}  "
                  f"Score: {score:.1f}")
            all_candidates.append({"page": page_num, "data": parsed})
        else:
            print(f"  Could not parse response:\n  {raw[:300]}")

        time.sleep(0.5)

    print(f"\n  Deduplicating and picking best per package...")
    winners = pick_best_per_package(all_candidates)
    return winners


def phase3_verify(extraction_results: list[dict]):
    """Cross-check each extracted result against reference specs."""
    print(f"\nPhase 3: Cross-checking against reference specs...")
    print("-" * 60)

    for entry in extraction_results:
        page_num = entry["page"]
        data = entry.get("data")
        if not data:
            print(f"\n  Page {page_num + 1}: no data to verify")
            continue

        pkg = data.get("package_type", "?")
        print(f"\n  Page {page_num + 1} — {pkg}")

        rows = cross_check(data)
        col_w = [12, 20, 20, 25]
        header = f"  {'Dim':<{col_w[0]}} {'Extracted':<{col_w[1]}} {'Reference':<{col_w[2]}} {'Status'}"
        print(header)
        print("  " + "-" * (sum(col_w) + 3))
        for row in rows:
            print(
                f"  {row['dimension']:<{col_w[0]}} "
                f"{row['extracted']:<{col_w[1]}} "
                f"{row['reference']:<{col_w[2]}} "
                f"{row['status']}"
            )


def save_results(pdf_path: str, results: list[dict]):
    out_path = pdf_path.replace(".pdf", "_dimensions.json").replace(".PDF", "_dimensions.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {out_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Two-phase dimension extraction tester")
    parser.add_argument("--pdf", required=True, help="Path to PDF file")
    parser.add_argument("--scan-dpi", type=int, default=120, help="DPI for scan phase (default: 120)")
    parser.add_argument("--extract-dpi", type=int, default=200, help="DPI for extract phase (default: 200)")
    parser.add_argument("--skip-scan", type=int, nargs="+", metavar="PAGE",
                        help="Skip scan phase; test these 0-indexed page numbers directly")
    args = parser.parse_args()

    print(f"PDF: {args.pdf}")

    if args.skip_scan:
        dimension_pages = [{"page": p, "package_type": "?"} for p in args.skip_scan]
    else:
        dimension_pages = phase1_scan(args.pdf, dpi=args.scan_dpi)

    if not dimension_pages:
        print("\nNo dimension pages found. Exiting.")
        return

    extraction_results = phase2_extract(args.pdf, dimension_pages, dpi=args.extract_dpi)
    phase3_verify(extraction_results)
    save_results(args.pdf, extraction_results)


if __name__ == "__main__":
    main()
