"""Hybrid page detection using rules-based patterns with LLM fallback for edge cases."""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from collections import Counter

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


@dataclass
class PageCandidate:
    """A candidate page that may contain pinout information."""

    page_number: int
    confidence_score: int
    reasons: List[str] = field(default_factory=list)
    text: str = ""
    has_table: bool = False
    has_diagram: bool = False
    needs_verification: bool = False


class PageDetector:
    """
    Hybrid page detection system.

    Phase 1: Rules-based candidate detection with confidence scoring
    Phase 2: LLM fallback for ambiguous/edge cases
    """

    # Section heading patterns that indicate pinout information
    PINOUT_HEADING_PATTERNS = [
        r"pin\s*(?:configuration|out|description|mapping|definition)s?\b",
        r"pinout\b",
        r"pin\s*assignments?\b",
        r"mechanical\s*data\b",
        r"package\s*(?:information|drawing|specification)s?\b",
        r"pin\s*functions?\b",
    ]

    # Table column patterns for pinout tables
    PINOUT_TABLE_PATTERNS = [
        r"pin\s*\.?\s*(no\.|number|#)",
        r"pin\s*\.?\s*name",
        r"function",
        r"description",
        # Microchip-style headers ("MCP3204 | MCP3208 | Symbol | Definition")
        r"definition",
        r"signal\s*name",
        r"symbol",
        # NEW: Handle I/O columns and multi-row headers
        r"i/o",
        r"input/output",
    ]

    # Keywords that indicate pinout content
    PINOUT_KEYWORDS = [
        "pin", "vcc", "vdd", "gnd", "gpio", "pwm", "i2c", "spi", "uart",
        "rx", "tx", "adc", "dac", "reset", "enable", "clock", "oscillator",
        "input", "output", "power", "ground", "analog", "digital", "interrupt",
        "nc", "no\s*connect", "vss", "vee",
    ]

    # Caption patterns for diagrams
    DIAGRAM_CAPTION_PATTERNS = [
        r"pinout",
        r"pin\s*configuration",
        r"pin\s*diagram",
        r"package\s*drawing",
        r"mechanical\s*drawing",
    ]

    def __init__(self, pdf_path: str):
        """
        Initialize the page detector.

        Args:
            pdf_path: Path to the PDF datasheet
        """
        self.pdf_path = pdf_path
        self.pdf = None
        self.total_pages = 0
        self._open_pdf()

    def _open_pdf(self) -> None:
        """Open the PDF file."""
        if pdfplumber is None:
            raise ImportError(
                "pdfplumber is required. Install with: pip install pdfplumber"
            )
        self.pdf = pdfplumber.open(self.pdf_path)
        self.total_pages = len(self.pdf.pages)

    def detect_relevant_pages(
        self, min_confidence: int = 5, require_verification_threshold: int = 3
    ) -> List[PageCandidate]:
        """
        Detect pages that likely contain pinout information.

        Args:
            min_confidence: Minimum confidence score to consider a page relevant
            require_verification_threshold: Score below which pages require LLM verification

        Returns:
            List of PageCandidate objects sorted by confidence score
        """
        candidates = []

        for page_num, page in enumerate(self.pdf.pages, start=1):
            text = page.extract_text() or ""
            candidate = self._analyze_page(page_num, page, text)
            candidates.append(candidate)

        # Filter and sort
        relevant_pages = [
            c for c in candidates if c.confidence_score >= min_confidence
        ]
        # Mark pages that need LLM verification
        for c in candidates:
            if c.needs_verification or (
                require_verification_threshold
                <= c.confidence_score
                < min_confidence
            ):
                c.needs_verification = True

        # Sort by confidence score
        relevant_pages.sort(key=lambda x: x.confidence_score, reverse=True)

        return relevant_pages

    def _analyze_page(
        self, page_num: int, page, text: str
    ) -> PageCandidate:
        """
        Analyze a single page and calculate confidence score.

        Args:
            page_num: Page number (1-indexed)
            page: pdfplumber Page object
            text: Extracted text from the page

        Returns:
            PageCandidate object with analysis results
        """
        candidate = PageCandidate(
            page_number=page_num,
            confidence_score=0,
            text=text,
        )

        # 1. Check for pinout section headings (+3)
        heading_score, heading_reason = self._check_pinout_heading(text)
        if heading_score > 0:
            candidate.confidence_score += heading_score
            candidate.reasons.append(heading_reason)

        # 2. Check for pinout tables (+4)
        table_score, has_table, table_reason = self._check_pinout_table(page)
        candidate.has_table = has_table
        if table_score > 0:
            candidate.confidence_score += table_score
            candidate.reasons.append(table_reason)

        # 3. Check for diagrams with captions (+2)
        diagram_score, has_diagram, diagram_reason = self._check_diagram(page)
        candidate.has_diagram = has_diagram
        if diagram_score > 0:
            candidate.confidence_score += diagram_score
            candidate.reasons.append(diagram_reason)

        # 4. Check keyword density (+2)
        keyword_score, keyword_reason = self._check_keyword_density(text)
        if keyword_score > 0:
            candidate.confidence_score += keyword_score
            candidate.reasons.append(keyword_reason)

        # 5. Page position heuristics (+1)
        position_score, position_reason = self._check_page_position(page_num)
        if position_score > 0:
            candidate.confidence_score += position_score
            candidate.reasons.append(position_reason)

        # Mark for verification if unusual structure
        if self._has_unusual_structure(candidate):
            candidate.needs_verification = True

        return candidate

    # A table of contents lists section titles with dot leaders and page
    # numbers ("5 Pin Configuration ......... 4"); those lines would collect
    # the heading bonus meant for the real section page.
    _TOC_LINE_PATTERN = re.compile(r"\.{4,}\s*\d{1,3}\s*$")

    def _check_pinout_heading(self, text: str) -> Tuple[int, str]:
        """Check if page contains a pinout section heading."""
        if self._looks_like_toc(text):
            return 0, ""

        text_lower = text.lower()

        for pattern in self.PINOUT_HEADING_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                # Check if it's likely a heading (at start of page or after newlines)
                if self._is_likely_heading(text, pattern):
                    return 3, f"Contains pinout heading pattern: '{pattern}'"

        return 0, ""

    def _looks_like_toc(self, text: str) -> bool:
        """Detect table-of-contents / index pages by their dot-leader lines."""
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        leader_lines = sum(1 for line in lines if self._TOC_LINE_PATTERN.search(line))
        if leader_lines >= 4:
            return True
        return any("table of contents" in line.lower() for line in lines[:5])

    def _is_likely_heading(self, text: str, pattern: str) -> bool:
        """Check if matched pattern starts a line anywhere on the page.

        Vendor boilerplate (part title, URLs, document ids) routinely pushes
        the section heading well past the top of the page, so the whole page
        is scanned rather than only its first lines.
        """
        for line in text.split("\n"):
            if re.search(pattern, line.lower(), re.IGNORECASE):
                return True
        return False

    def _check_pinout_table(self, page) -> Tuple[int, bool, str]:
        """Check if page contains a pinout table."""
        tables = page.extract_tables()

        if not tables:
            return 0, False, ""

        for table in tables:
            if not table or len(table) < 2:  # Need at least header + 1 row
                continue

            # Check multiple rows (rows 0-2) for pinout column patterns
            # Some tables have multi-row headers
            pattern_matches = 0
            header_text_all = ""

            # Check first 3 rows for patterns
            for row_idx in [0, 1, 2]:
                if row_idx >= len(table):
                    break

                row = table[row_idx]
                header = [str(cell or "").lower() for cell in row]
                header_text = " ".join(header)
                header_text_all += header_text + " "

                for pattern in self.PINOUT_TABLE_PATTERNS:
                    if re.search(pattern, header_text, re.IGNORECASE):
                        pattern_matches += 1

            if pattern_matches >= 2:  # At least 2 pattern matches
                return 4, True, f"Contains pinout table with {pattern_matches} matching columns"

        return 0, False, ""

    def _check_diagram(self, page) -> Tuple[int, bool, str]:
        """Check if page contains a diagram with pinout caption."""
        images = page.images

        if not images:
            return 0, False, ""

        # Check if page has significant image content
        image_area = sum(img["width"] * img["height"] for img in images)
        page_area = page.width * page.height

        if image_area / page_area < 0.2:  # Less than 20% image content
            return 0, False, ""

        # Look for captions in text
        text = page.extract_text() or ""
        text_lower = text.lower()

        for pattern in self.DIAGRAM_CAPTION_PATTERNS:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return 2, True, f"Contains diagram with caption matching: '{pattern}'"

        return 0, False, ""

    def _check_keyword_density(self, text: str) -> Tuple[int, str]:
        """Check keyword density to detect pinout content."""
        if not text:
            return 0, ""

        text_lower = text.lower()
        words = text_lower.split()

        # Count keyword matches
        keyword_count = 0
        for keyword in self.PINOUT_KEYWORDS:
            keyword_count += text_lower.count(keyword.lower())

        # Calculate density (matches per 100 words)
        if len(words) > 0:
            density = (keyword_count / len(words)) * 100
            if density >= 2:  # At least 2 keywords per 100 words
                return 2, f"High keyword density: {keyword_count} pinout keywords in {len(words)} words"

        return 0, ""

    def _check_page_position(self, page_num: int) -> Tuple[int, str]:
        """Check if page is in a plausible pinout position.

        Long datasheets routinely put the pin table right after the cover
        (page 3 of 40+ is common), so only the cover page and the legal/
        ordering tail are treated as unlikely. Position carries no signal
        at all in very short sheets.
        """
        if self.total_pages == 0:
            return 0, ""

        if self.total_pages <= 4:
            return 1, "Short datasheet: any page is a plausible pinout position"

        position_pct = page_num / self.total_pages

        if page_num >= 2 and position_pct <= 0.85:
            return 1, "Page in plausible pinout position (past cover, before tail)"

        return 0, ""

    def _has_unusual_structure(self, candidate: PageCandidate) -> bool:
        """Check if page has unusual structure that needs verification."""
        # Unusual: has keywords but no table or diagram
        if (
            candidate.confidence_score >= 2
            and not candidate.has_table
            and not candidate.has_diagram
        ):
            return True

        # Unusual: low text content with only image
        if len(candidate.text.strip()) < 100 and candidate.has_diagram:
            return True

        return False

    def get_low_confidence_pages(
        self, threshold: int = 4
    ) -> List[PageCandidate]:
        """
        Get pages with medium confidence that may need LLM verification.

        Args:
            threshold: Maximum confidence score to consider

        Returns:
            List of PageCandidate objects with low confidence
        """
        candidates = []
        for page_num, page in enumerate(self.pdf.pages, start=1):
            text = page.extract_text() or ""
            candidate = self._analyze_page(page_num, page, text)
            if threshold <= candidate.confidence_score < 5:
                candidates.append(candidate)

        return candidates

    def close(self) -> None:
        """Close the PDF file."""
        if self.pdf:
            self.pdf.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
