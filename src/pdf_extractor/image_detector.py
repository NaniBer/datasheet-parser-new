"""Detect and extract images from PDF pages for AI-based OCR processing."""

import io
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    from PIL import Image as PILImage
except ImportError:
    PILImage = None


@dataclass
class ImageInfo:
    """Information about an image on a PDF page."""
    page_number: int
    image_index: int
    width: float
    height: float
    area: float
    is_large: bool  # True if image covers >20% of page
    image_data: Optional[bytes] = None  # PIL image as bytes


@dataclass
class PageImageCandidate:
    """A page that likely contains a pinout diagram image."""

    page_number: int
    images: List[ImageInfo] = field(default_factory=list)
    confidence: float = 0.0
    reasons: List[str] = field(default_factory=list)


class ImageDetector:
    """
    Detect pages with images, especially pinout diagrams.

    Strategies:
    1. Large image area (>20% of page)
    2. Image with pinout-related caption in text
    3. Multiple images on one page (diagram + captions)
    """

    # Keywords that suggest image is a pinout diagram
    PINOUT_IMAGE_CAPTION_KEYWORDS = [
        'pinout', 'pin configuration', 'pin diagram',
        'package drawing', 'mechanical drawing',
        'package information'
    ]

    def __init__(self, pdf_path: str):
        """
        Initialize image detector.

        Args:
            pdf_path: Path to the PDF datasheet
        """
        self.pdf_path = pdf_path
        self.pdf = None
        self._open_pdf()

    def _open_pdf(self) -> None:
        """Open the PDF file."""
        if pdfplumber is None:
            raise ImportError(
                "pdfplumber is required. Install with: pip install pdfplumber"
            )
        self.pdf = pdfplumber.open(self.pdf_path)

    def find_pages_with_images(
        self,
        min_confidence: float = 0.3,
        require_large_image: bool = True
    ) -> List[PageImageCandidate]:
        """
        Find pages that likely contain pinout diagram images.

        Args:
            min_confidence: Minimum confidence score to consider
            require_large_image: Only include pages with large images (>20% area)

        Returns:
            List of PageImageCandidate objects sorted by confidence
        """
        candidates = []

        for page_num, page in enumerate(self.pdf.pages, start=1):
            candidate = self._analyze_page_for_images(page_num, page)

            # Apply filters
            if candidate.confidence < min_confidence:
                continue
            if require_large_image and not any(img.is_large for img in candidate.images):
                continue

            candidates.append(candidate)

        # Sort by confidence
        candidates.sort(key=lambda x: x.confidence, reverse=True)
        return candidates

    def _analyze_page_for_images(
        self,
        page_num: int,
        page
    ) -> PageImageCandidate:
        """
        Analyze a page for pinout diagram images.

        Args:
            page_num: Page number (1-indexed)
            page: pdfplumber Page object

        Returns:
            PageImageCandidate with analysis results
        """
        candidate = PageImageCandidate(page_number=page_num)

        # Get page dimensions
        page_area = page.width * page.height

        # Get images on this page
        images = page.images

        if not images:
            return candidate  # No images

        # Extract and analyze each image
        for img_index, img_obj in enumerate(images):
            img_width = img_obj.get('width', 0)
            img_height = img_obj.get('height', 0)
            img_area = img_width * img_height
            area_ratio = img_area / page_area if page_area > 0 else 0

            # Check if image is large (>20% of page)
            is_large = area_ratio > 0.2

            image_info = ImageInfo(
                page_number=page_num,
                image_index=img_index,
                width=img_width,
                height=img_height,
                area=img_area,
                is_large=is_large
            )

            # Try to extract actual image data
            if PILImage:
                image_data = self._extract_image_data(page, img_obj)
                image_info.image_data = image_data

            candidate.images.append(image_info)

        # Calculate confidence score
        candidate.confidence = self._calculate_image_confidence(page_num, page, candidate)

        return candidate

    def _calculate_image_confidence(
        self,
        page_num: int,
        page,
        candidate: PageImageCandidate
    ) -> float:
        """
        Calculate confidence that this page contains a pinout diagram.

        Scoring:
        - Large image present: +0.5
        - Multiple images: +0.2 each
        - Pinout keywords in text: +0.3
        - Image with caption: +0.2
        """
        score = 0.0

        # 1. Large image present
        if any(img.is_large for img in candidate.images):
            score += 0.5
            candidate.reasons.append("Large image present (>20% of page)")

        # 2. Multiple images (diagram + legend)
        if len(candidate.images) > 1:
            score += 0.2 * (len(candidate.images) - 1)
            candidate.reasons.append(f"Multiple images ({len(candidate.images)})")

        # 3. Pinout keywords in page text
        text = page.extract_text() or ""
        text_lower = text.lower()

        if any(kw in text_lower for kw in self.PINOUT_IMAGE_CAPTION_KEYWORDS):
            score += 0.3
            found_keywords = [kw for kw in self.PINOUT_IMAGE_CAPTION_KEYWORDS if kw in text_lower]
            candidate.reasons.append(f"Pinout keywords: {', '.join(found_keywords)}")

        # 4. Check for figure/caption pattern (Figure 1-1, etc.)
        import re
        if re.search(r'figure\s+\d+[\-\.]?\d*', text_lower):
            score += 0.2
            candidate.reasons.append("Contains figure number/caption")

        return score

    def _extract_image_data(self, page, img_obj) -> Optional[bytes]:
        """
        Extract PIL image from PDF page.

        Args:
            page: pdfplumber Page object
            img_obj: Image object from page.images

        Returns:
            Image data as bytes, or None if extraction fails
        """
        try:
            # Try to convert page to image
            pil_image = page.to_image()

            # Save to bytes
            img_bytes = io.BytesIO()
            pil_image.save(img_bytes, format="PNG")
            return img_bytes.getvalue()
        except Exception:
            return None

    def extract_all_images(
        self,
        page_numbers: List[int]
    ) -> List[Tuple[int, int, bytes]]:
        """
        Extract images from specific pages.

        Args:
            page_numbers: List of page numbers to extract from

        Returns:
            List of (page_number, image_index, image_data) tuples
        """
        extracted = []

        for page_num in page_numbers:
            if page_num < 1 or page_num > len(self.pdf.pages):
                continue

            page = self.pdf.pages[page_num - 1]
            images = page.images

            for img_index, img_obj in enumerate(images):
                image_data = self._extract_image_data(page, img_obj)
                if image_data:
                    extracted.append((page_num, img_index, image_data))

        return extracted

    def save_images_to_disk(
        self,
        output_dir: str,
        candidates: List[PageImageCandidate]
    ) -> None:
        """
        Save detected images to disk for debugging.

        Args:
            output_dir: Directory to save images to
            candidates: PageImageCandidate list with images
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        for candidate in candidates:
            for img_info in candidate.images:
                if img_info.image_data:
                    filename = output_path / f"page_{candidate.page_number}_img_{img_info.image_index}.png"
                    with open(filename, 'wb') as f:
                        f.write(img_info.image_data)

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
