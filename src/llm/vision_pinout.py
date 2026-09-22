"""Vision-based pinout extraction: read the pin number->name mapping from a
rendered image of the pinout page.

This is the fix for graphical/analog/discrete parts whose connection diagram is
vector art with a garbled text layer — the class the identity audit found the
parser hallucinates on. We render the page (see pdf_extractor.page_render) and
ask the vision endpoint for the pinout as printed.

De-risk finding (AD536): the endpoint reads the signal names correctly, but a
page showing several package variants returns them concatenated (1..14 then
1..20). So we split the flat result at pin-number resets and select the variant
that matches the expected pin count.
"""

from __future__ import annotations

import re
from typing import List, Dict, Optional

try:
    from ..pdf_extractor.page_render import render_page_png
    from .image_ocr_client import ImageOCRClient
except ImportError:  # pragma: no cover - top-level import compatibility
    from src.pdf_extractor.page_render import render_page_png
    from src.llm.image_ocr_client import ImageOCRClient


_VISION_PROMPT = (
    "Read the pin configuration / connection diagram in this datasheet page and "
    "return the pin number -> signal-name mapping EXACTLY as printed, as JSON: "
    '{"pins":[{"number":1,"name":"..."}, ...]}.\n'
    "Rules:\n"
    "- List EVERY pin in order, from 1 to the last pin. Do not stop early or "
    "skip pins; if the package has 16 pins, return all 16.\n"
    "- Use the name printed next to each pin number. Do not infer from a typical "
    "part or from memory.\n"
    "- Interpret drawn symbols as names: a diode's triangle/bar => \"Anode\" / "
    "\"Cathode\"; a bridge rectifier's \"~\" => \"AC\", \"+\"/\"-\" => the DC "
    "output; a transistor's leads => \"Base\"/\"Collector\"/\"Emitter\".\n"
    "- If several package variants are shown, list each variant's pins in order "
    "(number restarts at 1 for each variant)."
)


def _coerce_int(value) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


# Matches {"number": 1, "name": "EN1"} tolerating quoting/whitespace/markdown —
# robust to multi-variant and code-fenced responses that break strict json.loads.
_PIN_RE = re.compile(
    r'"number"\s*:\s*"?(\d+)"?\s*,\s*"name"\s*:\s*"([^"]*)"',
    re.IGNORECASE,
)


def parse_pins_from_text(text: str) -> List[Dict]:
    """Extract every {number, name} pin from raw model text, in order.

    Order is preserved so split_variant_groups can still detect variant resets.
    """
    pins = []
    for num, name in _PIN_RE.findall(text or ""):
        pins.append({"number": int(num), "name": name.strip()})
    return pins


def split_variant_groups(pins: List[Dict]) -> List[List[Dict]]:
    """Split a flat pin list into per-variant groups at pin-number resets.

    A multi-package page yields e.g. 1..14 then 1..20 concatenated; each reset
    (a number <= the previous number) starts a new group.
    """
    groups: List[List[Dict]] = []
    current: List[Dict] = []
    prev = None
    for pin in pins:
        num = _coerce_int(pin.get("number"))
        if num is None:
            continue
        if prev is not None and num <= prev:
            if current:
                groups.append(current)
            current = []
        current.append({"number": num, "name": pin.get("name")})
        prev = num
    if current:
        groups.append(current)
    return groups


def select_variant(
    groups: List[List[Dict]], expected_pin_count: Optional[int] = None
) -> List[Dict]:
    """Pick the variant group that best matches the expected pin count.

    Exact-count match wins; otherwise the largest group (most complete diagram).
    """
    if not groups:
        return []
    if expected_pin_count:
        exact = [g for g in groups if len(g) == expected_pin_count]
        if exact:
            return exact[0]
    return max(groups, key=len)


def extract_pinout_via_vision(
    pdf_path: str,
    page_number: int,
    part_number: Optional[str] = None,
    expected_pin_count: Optional[int] = None,
    dpi: int = 200,
    verbose: bool = False,
) -> List[Dict]:
    """Render one pinout page and read its number->name pinout via vision.

    Returns a list of ``{"number": int, "name": str}`` for the selected package
    variant, or ``[]`` on any failure (caller falls back to the text result).
    """
    try:
        png = render_page_png(pdf_path, page_number, dpi=dpi)
    except Exception as e:
        if verbose:
            print(f"  Vision: could not render page {page_number}: {e}")
        return []

    try:
        client = ImageOCRClient()
        raw = client.describe_raw(
            image_data=png, prompt=_VISION_PROMPT, part_number=part_number
        )
    except Exception as e:
        if verbose:
            print(f"  Vision: endpoint call failed: {e}")
        return []

    pins = parse_pins_from_text(raw)
    groups = split_variant_groups(pins)
    selected = select_variant(groups, expected_pin_count)
    if verbose:
        print(
            f"  Vision p{page_number}: read {len(pins)} pins across {len(groups)} "
            f"variant(s); selected {len(selected)}-pin variant"
            + (f" (expected {expected_pin_count})" if expected_pin_count else "")
        )
    return selected


def extract_pinout_best_page(
    pdf_path: str,
    page_numbers: List[int],
    part_number: Optional[str] = None,
    expected_pin_count: Optional[int] = None,
    max_pages: int = 4,
    dpi: int = 200,
    verbose: bool = False,
) -> List[Dict]:
    """Try several candidate pages and return the best vision pinout.

    The top-scored detection page is often NOT the connection diagram, so we try
    up to ``max_pages`` candidates and pick the best result: an exact
    expected-pin-count match short-circuits; otherwise the most complete pinout
    whose names aren't just the pin numbers.
    """
    best: List[Dict] = []
    for page in list(page_numbers)[:max_pages]:
        selected = extract_pinout_via_vision(
            pdf_path, page, part_number, expected_pin_count, dpi, verbose
        )
        if not selected:
            continue
        # Reject pages where the model just echoed pin numbers as names.
        named = [p for p in selected if str(p.get("name")).strip() not in ("", str(p.get("number")))]
        if len(named) < max(1, len(selected) // 2):
            continue
        if expected_pin_count and len(selected) == expected_pin_count:
            return selected  # exact match — done
        if len(selected) > len(best):
            best = selected
    return best
