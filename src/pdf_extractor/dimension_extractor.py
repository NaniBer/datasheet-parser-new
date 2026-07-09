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

from .text_dimensions import extract_text_dimensions, plausible_dims

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
        self,
        pdf_path: str,
        target_package_type: Optional[str] = None,
        hint_pages: Optional[List] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Run 3-phase extraction: scan → extract → pick best.

        Args:
            pdf_path: Path to the PDF file.
            target_package_type: If provided (e.g. "SOIC-16"), prefer candidates
                whose package type matches. Returns None if no candidate matches.
            hint_pages: Optional list of PageCandidate objects already detected by
                the pipeline. If provided, the expensive full-page scan is skipped
                and only pages flagged as mechanical/package drawings are used.

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
        doc = None
        try:
            # Open the document once and share the handle; per-render opens
            # leaked one file handle and re-parsed the PDF for every page.
            doc = fitz.open(pdf_path)

            # Phase 0: text-based extraction. Most vector-drawn datasheets
            # carry dimensions as real text; this is free (no API calls),
            # deterministic, and scans page content only — never the PDF
            # table of contents, which many datasheets lack.
            text_result = extract_text_dimensions(doc, target_package_type)
            if text_result:
                logger.debug(
                    "DimensionExtractor: text-based extraction succeeded: %s",
                    text_result,
                )
                return text_result

            if hint_pages is not None:
                dimension_pages = self._pages_from_hints(hint_pages, target_package_type)
            else:
                dimension_pages = self._scan_pages(doc)

            if not dimension_pages:
                logger.debug("DimensionExtractor: no dimension pages found")
                return None

            candidates = []
            for entry in dimension_pages:
                data = self._extract_page(doc, entry["page"], entry["package_type"])
                if data:
                    candidates.append({"page": entry["page"], "data": data})

            if not candidates:
                logger.debug("DimensionExtractor: extraction yielded no usable data")
                return None

            # Filter to candidates matching the target package type
            if target_package_type:
                filtered = [
                    c for c in candidates
                    if self._matches_target(
                        c["data"].get("package_type", ""), target_package_type
                    )
                ]
                if not filtered:
                    # No match — using dims from a different package family would
                    # produce wrong pitch/body size, so skip the override entirely.
                    logger.debug(
                        "DimensionExtractor: no candidates match target '%s', skipping override",
                        target_package_type,
                    )
                    return None
                candidates = filtered

            best = self._pick_best(candidates)
            if not best:
                return None

            flat = self._flatten(best)
            if flat and not plausible_dims(flat):
                # Vision models sometimes read real numbers off the drawing
                # but assign them to the wrong dimension letters; feeding
                # those into the footprint is worse than using defaults.
                logger.debug(
                    "DimensionExtractor: vision result failed plausibility gate: %s",
                    flat,
                )
                return None
            return flat

        except Exception as exc:
            logger.debug("DimensionExtractor: failed with %s", exc)
            return None
        finally:
            if doc is not None:
                doc.close()

    # -------------------------------------------------------------------------
    # Internal phases
    # -------------------------------------------------------------------------

    def _scan_pages(self, doc: "fitz.Document", dpi: int = 120) -> List[Dict]:
        """Phase 1: scan all pages and return list of {page, package_type} for dimension drawings."""
        found = []
        for i in range(len(doc)):
            image_bytes = self._render_page(doc, i, dpi=dpi)
            raw = self._call_api(image_bytes, SCAN_PROMPT)
            parsed = self._parse_json(raw)

            if parsed and parsed.get("has_dimensions"):
                if parsed.get("page_type") == "package_drawing":
                    pkg = parsed.get("package_type", "unknown")
                    logger.debug("DimensionExtractor: page %d — package drawing (%s)", i + 1, pkg)
                    found.append({"page": i, "package_type": pkg})

            time.sleep(0.3)

        return found

    def _pages_from_hints(self, hint_pages: List, target_package_type: Optional[str] = None) -> List[Dict]:
        """
        Convert PageCandidate hint pages to dimension page entries.

        Filters to pages whose reasons indicate a mechanical/package drawing.
        PageCandidate.page_number is 1-indexed; converts to 0-indexed for fitz.
        """
        pkg = target_package_type or "?"
        result = []
        for candidate in hint_pages:
            reasons = getattr(candidate, "reasons", [])
            reason_text = " ".join(reasons).lower()
            is_mechanical = "mechanical" in reason_text
            is_pkg_drawing = bool(re.search(r"package.*(drawing|information|specification)", reason_text))
            if is_mechanical or is_pkg_drawing:
                page_0indexed = candidate.page_number - 1
                result.append({"page": page_0indexed, "package_type": pkg})
        return result

    def _extract_page(self, doc: "fitz.Document", page: int, package_type: str) -> Optional[Dict]:
        """Phase 2: extract dimensions from a single dimension page."""
        is_fine = self._is_fine_pitch(package_type)
        dpi = 300 if is_fine else 200
        prompt = self._build_extract_prompt(package_type)

        image_bytes = self._render_page(doc, page, dpi=dpi)
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

    def _render_page(self, doc: "fitz.Document", page_number: int, dpi: int = 150) -> bytes:
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
        """
        Check if extracted package type is compatible with the target.

        Two levels of matching:
        1. Name match — exact, or one is a prefix of the other (e.g. "SOIC" matches "SOIC-16")
        2. Structural match — same pin count AND same mounting technology (SMT vs THT).
           Catches LLM misidentifications like "SOIC-28" when the part is SSOP-28.
        """
        e = extracted_pkg.lower().replace("-", "").replace(" ", "")
        t = target.lower().replace("-", "").replace(" ", "")

        # Level 1: name match
        if e == t or e.startswith(t) or t.startswith(e):
            return True

        # Level 2: same pin count + same mounting technology
        THT_PREFIXES = ("dip", "pdip", "sip", "zip", "cdip")
        e_is_tht = any(e.startswith(p) for p in THT_PREFIXES)
        t_is_tht = any(t.startswith(p) for p in THT_PREFIXES)
        if e_is_tht != t_is_tht:
            return False  # one THT, one SMT — never compatible

        e_pins = re.search(r"\d+", e)
        t_pins = re.search(r"\d+", t)
        if e_pins and t_pins and e_pins.group() == t_pins.group():
            return True  # same pin count, same mounting family

        return False

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
        """Convert a value to float, stripping non-numeric suffixes like 'BSC', 'REF', 'TYP'."""
        try:
            # Strip common datasheet annotation suffixes before parsing
            s = re.sub(r"\s*(BSC|REF|TYP|NOM|MIN|MAX)\s*$", "", str(v).strip(), flags=re.IGNORECASE)
            return float(s)
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
