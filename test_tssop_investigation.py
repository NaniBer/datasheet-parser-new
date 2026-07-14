"""
Targeted investigation of the TSSOP extraction problem.

Tests 3 approaches on the same TSSOP page:
  1. Current approach (200 DPI, generic prompt)
  2. Higher DPI (300), generic prompt
  3. Higher DPI (300), package-aware prompt that names TSSOP
"""

import io
import json
import re

import fitz
import requests

API_URL = "https://qwen.ideeza.com/describe_image/"

# TSSOP page from 74HC595 (0-indexed page 29)
PDF_PATH = "pdfs/74HC595_TI.pdf"
TSSOP_PAGE = 29

# Known correct values from the actual drawing (read visually)
GROUND_TRUTH = {
    "e":  0.65,   # pitch
    "E":  6.40,   # body width (typ between 6.2 and 6.6)
    "D":  5.00,   # body length (typ between 4.9 and 5.1)
    "b":  0.23,   # lead width (typ between 0.17 and 0.30)
    "L":  0.63,   # lead length (typ between 0.50 and 0.75)
    "A":  1.20,   # max height
}

GENERIC_PROMPT = """You are an expert at reading mechanical package dimension drawings from electronic component datasheets.

Extract every labeled dimension from this drawing.

Return ONLY valid JSON:
{
  "package_type": "SOIC-16",
  "unit": "mm",
  "dimensions": {
    "A":  {"min": "2.35", "max": "2.65"},
    "e":  "1.27",
    "b":  {"min": "0.31", "max": "0.51"}
  },
  "notes": "any observations"
}

Rules:
- Use a single string value when only one value is shown
- Capture ALL labeled dimensions
- Return ONLY JSON"""

AWARE_PROMPT = """You are an expert at reading mechanical package dimension drawings from electronic component datasheets.

This page shows a TSSOP (Thin Shrink Small Outline Package) dimension drawing.
TSSOP packages have a fine pitch of 0.65mm and a narrow body (typically 4.4–6.6mm wide).
Do NOT confuse this with SOIC which has 1.27mm pitch and a wider body (~10mm).

Extract every labeled dimension exactly as shown in this drawing.

Return ONLY valid JSON:
{
  "package_type": "TSSOP-16",
  "unit": "mm",
  "dimensions": {
    "A":  {"min": "1.05", "max": "1.20"},
    "e":  "0.65",
    "b":  {"min": "0.19", "max": "0.30"},
    "D":  {"min": "4.90", "max": "5.10"},
    "E":  {"min": "6.20", "max": "6.60"}
  },
  "notes": "any observations"
}

Rules:
- Read the actual numbers from the drawing — do not use default or assumed values
- The pitch should be 0.65mm for TSSOP, not 1.27mm
- Capture ALL labeled dimensions
- Return ONLY JSON"""


def render_page(pdf_path, page_num, dpi):
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    return pix.tobytes("png")


def call_api(image_bytes, prompt):
    files = {"file": ("page.png", io.BytesIO(image_bytes), "image/png")}
    data = {"text": prompt}
    resp = requests.post(API_URL, files=files, data=data, timeout=120)
    resp.raise_for_status()
    return resp.json().get("description", "")


def parse_json(text):
    if isinstance(text, dict):
        return text
    match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
    if match:
        text = match.group(1)
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(text)
    except Exception:
        return None


def to_float(v):
    try:
        return float(str(v).strip().split()[0])
    except Exception:
        return None


def evaluate(extracted, ground_truth):
    """Compare extracted dims to ground truth. Returns (correct, total)."""
    dims = extracted.get("dimensions", {})
    rows = []
    for key, true_val in ground_truth.items():
        raw = dims.get(key) or dims.get(key.lower())
        if raw is None:
            rows.append((key, "MISSING", true_val, "✗"))
            continue
        if isinstance(raw, dict):
            # Use midpoint of min/max
            lo = to_float(raw.get("min"))
            hi = to_float(raw.get("max"))
            ext_val = ((lo or 0) + (hi or 0)) / 2 if (lo and hi) else (lo or hi)
            ext_str = f"{raw.get('min')}–{raw.get('max')}"
        else:
            ext_val = to_float(raw)
            ext_str = str(raw)

        if ext_val is not None and abs(ext_val - true_val) <= 0.15:
            status = "✓"
        else:
            status = "✗"
        rows.append((key, ext_str, true_val, status))
    return rows


def run_approach(label, dpi, prompt):
    print(f"\n{'='*60}")
    print(f"Approach: {label}  (DPI={dpi})")
    print("="*60)
    image_bytes = render_page(PDF_PATH, TSSOP_PAGE, dpi)
    print(f"Image: {len(image_bytes):,} bytes  ({dpi} DPI)")

    raw = call_api(image_bytes, prompt)
    parsed = parse_json(raw)

    if not parsed:
        print(f"Could not parse response:\n{raw[:400]}")
        return

    print(f"Package identified: {parsed.get('package_type', '?')}")
    print(f"Unit: {parsed.get('unit', '?')}")
    print(f"Notes: {parsed.get('notes', '')}")
    print()

    rows = evaluate(parsed, GROUND_TRUTH)
    correct = sum(1 for r in rows if r[3] == "✓")
    print(f"  {'Dim':<6} {'Extracted':<18} {'Expected (typ)':<18} {'OK?'}")
    print(f"  {'-'*55}")
    for dim, ext, exp, ok in rows:
        print(f"  {dim:<6} {ext:<18} {str(exp):<18} {ok}")
    print(f"\n  Score: {correct}/{len(rows)} correct")


# Run all 3 approaches
run_approach("Generic prompt, 200 DPI",  200, GENERIC_PROMPT)
run_approach("Generic prompt, 300 DPI",  300, GENERIC_PROMPT)
run_approach("Package-aware prompt, 300 DPI", 300, AWARE_PROMPT)
