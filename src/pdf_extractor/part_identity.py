"""Part identity metadata: manufacturer, one-line description, footprint name.

QC re-check C1: the platform's part record shipped with manufacturer "",
datasheet "", description "<MPN> (created from datasheet)" and the footprint
named after the part number. These fields come from the datasheet itself:

- manufacturer: the copyright line / PDF author / vendor domain (deterministic),
  mapped to the current owner (Linear/Maxim -> Analog Devices, NXP logic ->
  Nexperia ...). The LLM's answer is only used when the text names it too.
- description: one line from page 1, written by the LLM and accepted only if
  every number in it appears in the datasheet text; otherwise the page-1 title
  (largest-font line(s) in the header). The package is appended by us.
- footprint name: built from the package geometry the footprint builder uses.

Nothing here is allowed to fail a run: every step degrades to None.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

try:
    import pymupdf
except ImportError:  # pragma: no cover - older PyMuPDF
    import fitz as pymupdf  # type: ignore


# Canonical vendor name -> patterns that identify it (current owner first, so
# acquired brands resolve to the company that sells the part today).
_VENDORS: List[Tuple[str, List[str]]] = [
    ("Texas Instruments", [r"Texas\s+Instruments", r"\bti\.com\b", r"Burr-Brown"]),
    ("Analog Devices", [r"Analog\s+Devices", r"\banalog\.com\b", r"Linear\s+Technology",
                        r"Maxim\s+Integrated", r"\bmaximintegrated\.com\b"]),
    ("Nexperia", [r"Nexperia", r"\bnexperia\.com\b"]),
    ("NXP Semiconductors", [r"\bNXP\b", r"\bnxp\.com\b", r"Freescale"]),
    ("Microchip Technology", [r"Microchip\s+Technology", r"\bmicrochip\.com\b", r"\bAtmel\b"]),
    ("STMicroelectronics", [r"STMicroelectronics", r"\bst\.com\b"]),
    ("Infineon Technologies", [r"Infineon", r"Cypress\s+Semiconductor", r"International\s+Rectifier"]),
    ("onsemi", [r"ON\s+Semiconductor", r"\bonsemi\b", r"Fairchild\s+Semiconductor"]),
    ("Renesas Electronics", [r"Renesas", r"Intersil", r"Integrated\s+Device\s+Technology"]),
    ("ROHM Semiconductor", [r"\bROHM\b", r"\brohm\.com\b"]),
    ("Toshiba", [r"\bToshiba\b"]),
    ("Vishay", [r"\bVishay\b"]),
    ("Diodes Incorporated", [r"Diodes\s+Incorporated", r"\bdiodes\.com\b"]),
    ("Würth Elektronik", [r"W(?:ü|u|ue)rth\s+Elektronik", r"\bwe-online\b"]),
    ("Bridgetek", [r"Bridgetek", r"Future\s+Technology\s+Devices", r"\bFTDI\b"]),
    ("Silicon Labs", [r"Silicon\s+Lab"]),
    ("Nordic Semiconductor", [r"Nordic\s+Semiconductor"]),
    ("Espressif Systems", [r"Espressif"]),
    ("Monolithic Power Systems", [r"Monolithic\s+Power"]),
]

# NXP sold its standard-logic line to Nexperia (2017); old NXP datasheets for
# 74-series / HEF4000 logic still say NXP.
_NEXPERIA_LOGIC = re.compile(r"^(?:74|HEF4)", re.I)

# Datasheet mirror sites stamp their own name into the PDF properties.
_MIRROR_SITE = re.compile(r"alldatasheet|datasheet\s*(?:search|archive|catalog)|datasheet4u", re.I)

_COPYRIGHT = re.compile(r"(?:©|\(c\)|copyright)[^\n]{0,90}", re.I)

# Header lines that are never the title.
_NOT_TITLE = re.compile(
    r"^(?:\d+\.?\s*)?(?:general\s+description|description|features(?:\s+and\s+benefits)?|"
    r"applications|functional\s+block\s+diagram|product\s+preview|production\s+data|"
    r"data\s*sheet|product\s+data\s*sheet|preliminary.*|document\s+feedback|"
    r"technical\s+support)$|^rev\b|^revision\b",
    re.I,
)

_COMPANY = re.compile(r"\b(?:Pte|Ltd|Inc|GmbH|Corporation|Corp|B\.V|S\.A|AG)\b\.?\s*$", re.I)

_DESC_MAX = 100
_NUM = re.compile(r"\d+(?:\.\d+)?")


@dataclass
class PartIdentity:
    manufacturer: Optional[str] = None
    description: Optional[str] = None
    footprint_name: Optional[str] = None
    supplier_footprint: Optional[str] = None
    mpn: Optional[str] = None
    sources: Dict[str, str] = field(default_factory=dict)

    def to_extras(self) -> Dict[str, object]:
        """Package-node extras, under the platform's own property names."""
        out: Dict[str, object] = {}
        for key, value in (
            ("manufacturer", self.manufacturer),
            ("description", self.description),
            ("footprintName", self.footprint_name),
            ("supplierFootprint", self.supplier_footprint),
            ("manufacturerPartNumber", self.mpn),
        ):
            if value:
                out[key] = value
        if out and self.sources:
            out["identitySource"] = dict(self.sources)
        return out


# --------------------------------------------------------------------------- #
# PDF text
# --------------------------------------------------------------------------- #

def _clean(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").replace("−", "-")


def _read_pdf(pdf_path: str) -> Tuple[List[str], Dict[str, str], Optional[dict], float]:
    """(page texts, metadata, page-1 text dict, page-1 height)."""
    doc = pymupdf.open(pdf_path)
    try:
        texts = [_clean(p.get_text()) for p in doc]
        page1 = doc[0].get_text("dict") if len(doc) else None
        height = float(doc[0].rect.height) if len(doc) else 792.0
        return texts, dict(doc.metadata or {}), page1, height
    finally:
        doc.close()


# --------------------------------------------------------------------------- #
# Manufacturer
# --------------------------------------------------------------------------- #

def canonical_vendor(text: str) -> Optional[str]:
    """First vendor whose pattern occurs in *text* (current-owner name)."""
    for name, patterns in _VENDORS:
        if any(re.search(p, text or "", re.I) for p in patterns):
            return name
    return None


def _mentions(vendor: str, text: str) -> bool:
    patterns = dict(_VENDORS).get(vendor, [])
    return any(re.search(p, text or "", re.I) for p in patterns)


def _apply_ownership(vendor: Optional[str], part_number: Optional[str]) -> Optional[str]:
    if vendor == "NXP Semiconductors" and part_number and _NEXPERIA_LOGIC.match(part_number):
        return "Nexperia"
    return vendor


def detect_manufacturer(
    page_texts: List[str], metadata: Dict[str, str], part_number: Optional[str] = None
) -> Tuple[Optional[str], Optional[str]]:
    """(manufacturer, source) from copyright lines, PDF author, vendor mentions."""
    head = page_texts[:3] + page_texts[-3:]
    scores: Dict[str, int] = {}
    first_source: Dict[str, str] = {}

    def vote(vendor: Optional[str], weight: int, source: str) -> None:
        if vendor:
            scores[vendor] = scores.get(vendor, 0) + weight
            first_source.setdefault(vendor, source)

    for text in head:
        for m in _COPYRIGHT.finditer(text):
            vote(canonical_vendor(m.group(0)), 5, "copyright")
    author = metadata.get("author") or ""
    if author and not _MIRROR_SITE.search(author):
        vote(canonical_vendor(author), 3, "pdf_author")
    for text in page_texts[:3]:
        for name, patterns in _VENDORS:
            if any(re.search(p, text, re.I) for p in patterns):
                vote(name, 1, "text")

    if not scores:
        return None, None
    best = max(scores, key=lambda v: scores[v])
    return _apply_ownership(best, part_number), first_source[best]


# --------------------------------------------------------------------------- #
# Title (description fallback)
# --------------------------------------------------------------------------- #

def page1_title(page1: Optional[dict], page_height: float) -> Optional[str]:
    """Largest-font line(s) in the page-1 header, minus part numbers/headings."""
    if not page1:
        return None
    lines: List[Tuple[float, float, str]] = []
    for block in page1.get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = _clean("".join(s.get("text", "") for s in spans)).strip()
            if not text or not spans:
                continue
            y = float(line["bbox"][1])
            if y > 0.22 * page_height:
                continue
            # A single token (no space) is a part number / logo, not a title;
            # nor is a company name or a drawing label ("Dimensions: [mm]").
            if (" " not in text or _NOT_TITLE.search(text) or _COMPANY.search(text)
                    or ":" in text or not re.search(r"[A-Za-z]{3}", text)):
                continue
            lines.append((max(float(s.get("size", 0)) for s in spans), y, text))
    if not lines:
        return None
    top = max(size for size, _, _ in lines)
    chosen = sorted((ln for ln in lines if ln[0] >= 0.85 * top), key=lambda ln: ln[1])
    title = ""
    for _, _, text in chosen:
        if title.endswith("-"):
            title += text          # "Digital-to-" + "Analog Converter"
        else:
            title = f"{title} {text}".strip()
    return re.sub(r"\s+", " ", title).strip(" .;,()") or None


def metadata_title(metadata: Dict[str, str], part_number: Optional[str]) -> Optional[str]:
    """Vendor PDF subject/title with the part number and 'datasheet (Rev. X)' removed."""
    for key in ("subject", "title"):
        raw = _clean(metadata.get(key) or "")
        if not raw or _MIRROR_SITE.search(raw) or raw.lower() in ("data sheet", "datasheet"):
            continue
        text = re.sub(r"\bdata\s*sheet\b.*$", "", raw, flags=re.I)
        if part_number:
            base = re.escape(re.sub(r"[^A-Za-z0-9]", "", part_number)[:6])
            text = re.sub(rf"^\s*{base}\w*\s*", "", text, flags=re.I)
        text = re.sub(r"\s+", " ", text).strip(" -.,;")
        # Web/marketing blurbs ("Order free samples...") are not titles.
        if (" " in text and 10 <= len(text) <= _DESC_MAX
                and not re.search(r"\border|sample|quote|click|at a glance", text, re.I)):
            return text
    return None


# --------------------------------------------------------------------------- #
# LLM description (validated)
# --------------------------------------------------------------------------- #

def numbers_grounded(description: str, source_text: str) -> bool:
    """Every number in *description* occurs as a number in *source_text*."""
    for num in _NUM.findall(description):
        if not re.search(rf"(?<![\d.]){re.escape(num)}(?![\d])", source_text):
            return False
    return True


def _llm_messages(page1_text: str, part_number: Optional[str]) -> list:
    return [
        {"role": "system", "content": (
            "You write one-line descriptions for an electronic component library. "
            "Answer ONLY with JSON: {\"description\": \"...\", \"manufacturer\": \"...\"}."
        )},
        {"role": "user", "content": (
            f"Part number: {part_number or 'unknown'}\n\n"
            "From the datasheet first page below, write:\n"
            "- description: what the part is, at most 80 characters, e.g. "
            "\"Dual low-noise operational amplifier\". Only facts stated "
            "in the text; copy numbers and units exactly; no part number, no package, "
            "no marketing words, no trailing period.\n"
            "- manufacturer: the company that makes it, as written in the text "
            "(null if not stated).\n\n"
            "--- FIRST PAGE ---\n"
            f"{page1_text[:4000]}\n"
            "--- END ---"
        )},
    ]


def _parse_llm_json(raw: str) -> dict:
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    m = re.search(r"\{.*\}", raw, re.S)
    return json.loads(m.group(0)) if m else {}


def llm_description(
    page_texts: List[str], part_number: Optional[str],
    complete: Callable[[list], str],
) -> Tuple[Optional[str], Optional[str]]:
    """(description, manufacturer-as-written) from the LLM, or (None, None)."""
    if not page_texts:
        return None, None
    data = _parse_llm_json(complete(_llm_messages(page_texts[0], part_number)))
    desc = data.get("description") if isinstance(data, dict) else None
    mfr = data.get("manufacturer") if isinstance(data, dict) else None
    if isinstance(desc, str):
        desc = re.sub(r"\s+", " ", desc).strip(" .")
        source = " ".join(page_texts[:3])
        if (not desc or len(desc) > _DESC_MAX or re.search(r"datasheet|created from", desc, re.I)
                or (part_number and part_number.lower() in desc.lower())
                or not numbers_grounded(desc, source)):
            desc = None
    else:
        desc = None
    return desc, (mfr if isinstance(mfr, str) and mfr.strip() else None)


# --------------------------------------------------------------------------- #
# Footprint name
# --------------------------------------------------------------------------- #

def _fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def footprint_names(
    package_type: str, pin_count: int, *,
    body_w: Optional[float] = None, body_l: Optional[float] = None,
    pitch: Optional[float] = None, row_spacing: Optional[float] = None,
    epad: Optional[Tuple[float, float]] = None, through_hole: bool = False,
) -> Tuple[Optional[str], Optional[str]]:
    """(footprintName, supplierFootprint), KiCad-style, e.g.
    ``TQFP-48_7x7mm_P0.5mm`` / ``TQFP-48``, ``DIP-16_W7.62mm`` / ``DIP-16``."""
    if not package_type or not pin_count:
        return None, None
    pkg = package_type.strip().upper()
    family = re.sub(r"[-_\s]*\d+.*$", "", pkg) or pkg
    # SOT833-1 is the 8-pin XSON outline (same rule as footprint_defaults).
    outline = re.search(r"SOT\s*-?\s*833", pkg) or (family == "XSON" and pin_count == 8)
    if outline:
        family = "XSON"
    supplier = f"{family}-{pin_count}"
    name = supplier
    if through_hole and row_spacing:
        name += f"_W{_fmt(row_spacing)}mm"
    elif body_w and body_l:
        name += f"_{_fmt(body_w)}x{_fmt(body_l)}mm"
        if pitch:
            name += f"_P{_fmt(pitch)}mm"
        if epad and epad[0] and epad[1]:
            ew, el = epad
            name += f"_EP{_fmt(ew)}mm" if abs(ew - el) < 1e-6 else f"_EP{_fmt(ew)}x{_fmt(el)}mm"
    if outline:
        name += "_SOT833-1"
    return name, supplier


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def resolve_part_identity(
    pdf_path: str,
    part_number: Optional[str],
    *,
    complete: Optional[Callable[[list], str]] = None,
    footprint: Optional[Tuple[Optional[str], Optional[str]]] = None,
    package_label: Optional[str] = None,
) -> PartIdentity:
    """Best-effort identity; never raises.

    Args:
        pdf_path: datasheet PDF.
        part_number: orderable part number (becomes the MPN).
        complete: LLM call ``messages -> text``; None skips the LLM.
        footprint: (footprintName, supplierFootprint) from ``footprint_names``.
        package_label: appended to the description (e.g. "TQFP-48").
    """
    ident = PartIdentity(mpn=part_number or None)
    if footprint:
        ident.footprint_name, ident.supplier_footprint = footprint
        if ident.footprint_name:
            ident.sources["footprintName"] = "geometry"
    try:
        texts, metadata, page1, height = _read_pdf(pdf_path)
    except Exception:
        return ident

    mfr, src = detect_manufacturer(texts, metadata, part_number)

    desc, llm_mfr = None, None
    if complete is not None:
        try:
            desc, llm_mfr = llm_description(texts, part_number, complete)
        except Exception:
            desc, llm_mfr = None, None
    if desc:
        ident.sources["description"] = "llm"
    else:
        desc = page1_title(page1, height) or metadata_title(metadata, part_number)
        if desc:
            ident.sources["description"] = "title"

    # LLM manufacturer only when nothing deterministic was found AND the text
    # itself names that company.
    if not mfr and llm_mfr:
        vendor = canonical_vendor(llm_mfr)
        if vendor and _mentions(vendor, " ".join(texts[:3] + texts[-3:])):
            mfr, src = _apply_ownership(vendor, part_number), "llm"
    if mfr:
        ident.manufacturer = mfr
        ident.sources["manufacturer"] = src or "text"

    if desc:
        label = package_label or ident.supplier_footprint
        if label and label.split("-")[0].lower() not in desc.lower():
            desc = f"{desc}, {label}"
        ident.description = desc[:_DESC_MAX + 20]
    return ident
