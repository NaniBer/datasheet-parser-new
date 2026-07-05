"""
Dimension extractor — 3-phase vision API flow.

Phase 1: Scan all PDF pages to find mechanical package dimension drawings.
Phase 2: Extract labeled dimensions from those pages using package-aware prompts.
Phase 3: Deduplicate, score, and pick the best result.

Returns a flat dict of float values (midpoints of min/max ranges) suitable for
overriding hardcoded package geometry in PcbFootprintBuilder.
"""

import io
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF
import requests

logger = logging.getLogger(__name__)

SCAN_PROMPT = """Look at this page and classify it. Answer ONLY with JSON, no other text.

If it contains an IC package dimension drawing (body outline + lead dimensions like A, A1, b, D, E, e, L):
{"has_dimensions": true, "page_type": "package_drawing", "package_type": "SOIC-16"}

If it contains a tape/reel or carrier drawing (reel dimensions like A0, B0, K0, P1, W, feed hole pitch):
{"has_dimensions": true, "page_type": "tape_reel", "package_type": "SOIC-16"}

If it contains something else (electrical specs, pinout table, ordering info, text, etc.):
{"has_dimensions": false, "page_type": "other"}

Only classify as "package_drawing" if you can see a mechanical outline of the IC package with labeled lead/body dimensions."""


class DimensionExtractor:
    """Extract real package dimensions from datasheet PDFs via a 3-phase vision API flow."""

    API_URL = "https://qwen.ideeza.com/describe_image/"
    FINE_PITCH_KEYWORDS = ["tssop", "ssop", "qfn", "qfp", "lqfp", "tqfp", "vssop", "msop"]

    def extract(
        self, pdf_path: str, target_package_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Run 3-phase extraction: scan → extract → pick best.

        Args:
            pdf_path: Path to the PDF file.
            target_package_type: If provided (e.g. "SOIC-16"), prefer candidates
                whose package type matches. Falls back to best overall if no match.

        Returns:
            Flat dict with float dimension values, or None if extraction fails.

            Example:
            {
              "package_type": "SOIC-16",
              "unit": "mm",
              "e": 1.27,    # pitch
              "E": 10.32,   # body width (midpoint of min/max)
              "D": 9.90,    # body length
              "b": 0.41,    # pad width
              "L": 0.84,    # pad length
              "A": 2.50,    # total height
            }
        """
        try:
            dimension_pages = self._scan_pages(pdf_path)
            if not dimension_pages:
                logger.debug("DimensionExtractor: no dimension pages found")
                return None

            candidates = []
            for entry in dimension_pages:
                data = self._extract_page(pdf_path, entry["page"], entry["package_type"])
                if data:
                    candidates.append({"page": entry["page"], "data": data})

            if not candidates:
                logger.debug("DimensionExtractor: extraction yielded no usable data")
                return None

            # Prefer candidates matching the target package type
            if target_package_type:
                filtered = [
                    c for c in candidates
                    if self._matches_target(
                        c["data"].get("package_type", ""), target_package_type
                    )
                ]
                if filtered:
                    candidates = filtered

            best = self._pick_best(candidates)
            if not best:
                return None

            return self._flatten(best)

        except Exception as exc:
            logger.debug("DimensionExtractor: failed with %s", exc)
            return None

    # -------------------------------------------------------------------------
    # Internal phases
    # -------------------------------------------------------------------------

    def _scan_pages(self, pdf_path: str, dpi: int = 120) -> List[Dict]:
        """Phase 1: scan all pages and return list of {page, package_type} for dimension drawings."""
        doc = fitz.open(pdf_path)
        page_count = len(doc)
        doc.close()

        found = []
        for i in range(page_count):
            image_bytes = self._render_page(pdf_path, i, dpi=dpi)
            raw = self._call_api(image_bytes, SCAN_PROMPT)
            parsed = self._parse_json(raw)

            if parsed and parsed.get("has_dimensions"):
                if parsed.get("page_type") == "package_drawing":
                    pkg = parsed.get("package_type", "unknown")
                    logger.debug("DimensionExtractor: page %d — package drawing (%s)", i + 1, pkg)
                    found.append({"page": i, "package_type": pkg})

            time.sleep(0.3)

        return found

    def _extract_page(self, pdf_path: str, page: int, package_type: str) -> Optional[Dict]:
        """Phase 2: extract dimensions from a single dimension page."""
        is_fine = self._is_fine_pitch(package_type)
        dpi = 300 if is_fine else 200
        prompt = self._build_extract_prompt(package_type)

        image_bytes = self._render_page(pdf_path, page, dpi=dpi)
        raw = self._call_api(image_bytes, prompt)
        parsed = self._parse_json(raw)

        time.sleep(0.5)
        return parsed

    def _pick_best(self, candidates: List[Dict]) -> Optional[Dict]:
        """Phase 3: deduplicate and return the highest-scoring candidate's data dict."""
        if not candidates:
            return None

        seen: set = set()
        unique = []
        for entry in candidates:
            data = entry.get("data", {})
            fp = json.dumps(data.get("dimensions", {}), sort_keys=True)
            if fp not in seen:
                seen.add(fp)
                unique.append(entry)

        best = max(unique, key=lambda e: self._completeness_score(e.get("data", {})))
        return best.get("data")

    def _flatten(self, raw: Dict) -> Optional[Dict[str, Any]]:
        """
        Convert raw API response to a flat dict of float values.

        min/max dicts are collapsed to their midpoint.
        Returns None if no numeric dimensions could be extracted.
        """
        dims = raw.get("dimensions", {})
        result: Dict[str, Any] = {
            "package_type": raw.get("package_type", ""),
            "unit": raw.get("unit", "mm"),
        }

        for key, val in dims.items():
            if isinstance(val, dict):
                mn = self._to_float(val.get("min"))
                mx = self._to_float(val.get("max"))
                if mn is not None and mx is not None:
                    result[key] = (mn + mx) / 2.0
                elif mn is not None:
                    result[key] = mn
                elif mx is not None:
                    result[key] = mx
            else:
                f = self._to_float(val)
                if f is not None:
                    result[key] = f

        # Only return if we got at least one numeric dimension
        if len(result) <= 2:
            return None
        return result

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _render_page(self, pdf_path: str, page_number: int, dpi: int = 150) -> bytes:
        doc = fitz.open(pdf_path)
        page = doc[page_number]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        return pix.tobytes("png")

    def _call_api(self, image_bytes: bytes, prompt: str) -> str:
        """POST image to API and return the description string."""
        files = {"file": ("page.png", io.BytesIO(image_bytes), "image/png")}
        data = {"text": prompt}
        response = requests.post(self.API_URL, files=files, data=data, timeout=120)
        response.raise_for_status()
        raw = response.json()
        return raw.get("description", str(raw))

    def _parse_json(self, text: str) -> Optional[Dict]:
        """Extract JSON from a string that may contain markdown fences."""
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
        except (json.JSONDecodeError, TypeError):
            return None

    def _is_fine_pitch(self, package_type: str) -> bool:
        key = package_type.lower()
        return any(kw in key for kw in self.FINE_PITCH_KEYWORDS)

    def _matches_target(self, extracted_pkg: str, target: str) -> bool:
        """Check if extracted package type loosely matches target (case-insensitive)."""
        e = extracted_pkg.lower().replace("-", "").replace(" ", "")
        t = target.lower().replace("-", "").replace(" ", "")
        return e == t or e.startswith(t) or t.startswith(e)

    def _completeness_score(self, extracted: Dict) -> float:
        """Score completeness: min+max pair = 1.0, single value = 0.5, missing = 0."""
        dims = extracted.get("dimensions", {})
        if not dims:
            return 0.0
        total = 0.0
        for v in dims.values():
            if isinstance(v, dict):
                has_min = bool(v.get("min") and str(v.get("min")).strip() not in ("", "-", "- "))
                has_max = bool(v.get("max") and str(v.get("max")).strip() not in ("", "-", "- "))
                if has_min and has_max:
                    total += 1.0
                elif has_min or has_max:
                    total += 0.5
            elif v:
                total += 0.5
        return total

    def _to_float(self, v: Any) -> Optional[float]:
        try:
            return float(str(v).strip())
        except (ValueError, TypeError):
            return None

    def _build_extract_prompt(self, package_type: str) -> str:
        """Build a package-aware extraction prompt."""
        if self._is_fine_pitch(package_type):
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
