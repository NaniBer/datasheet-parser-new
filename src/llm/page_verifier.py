"""
LLM Page Verifier - Fallback for ambiguous pages.

Uses LLM to verify if pages contain pinout information when
rules-based detection has medium confidence or encounters unusual structure.
"""

from typing import List, Optional
from ..chat_bot import get_completion_from_messages


class PageVerifier:
    """
    Verify pages using LLM for ambiguous cases.

    Use when:
    - Page has medium confidence (3-4 score)
    - Unusual structure detected
    - Low overall pattern matches across datasheet
    """

    def __init__(self, llm_client):
        """
        Initialize page verifier.

        Args:
            llm_client: LLMClient instance for making API calls
        """
        self.llm_client = llm_client
        self.model = llm_client.model if llm_client else "llama-3"

    def verify_pages(
        self,
        candidates: List,
        content_extractor
    ) -> List:
        """
        Verify if ambiguous pages contain pinout information.

        Args:
            candidates: List of PageCandidate objects to verify
            content_extractor: ContentExtractor instance for getting page content

        Returns:
            Updated list of PageCandidate objects with verification results
        """
        verified_candidates = []

        for candidate in candidates:
            if hasattr(candidate, 'needs_verification') and candidate.needs_verification:
                # Get page content
                page_content = content_extractor.extract_single_page(
                    candidate.page_number
                )

                # Use LLM to verify
                is_relevant = self._ask_llm_about_page(page_content)

                # Update candidate based on LLM judgment
                if is_relevant:
                    # Boost confidence for pages confirmed relevant
                    candidate.confidence_score = 5
                    candidate.reasons.append("LLM verified as containing pinout info")
                    verified_candidates.append(candidate)
                # If not relevant, don't include
            else:
                verified_candidates.append(candidate)

        return verified_candidates

    def locate_pin_assignment_page(self, page_index: List) -> Optional[int]:
        """Ask the LLM which page holds the pin-assignment table.

        This is the deep-document fallback: when the deterministic detector
        surfaces no confident candidate, the LLM is shown a compact index of
        page headings for the whole document and asked to name the single page
        that carries the pin-assignment / pinout table.

        Args:
            page_index: list of ``(page_number, heading_text)`` tuples, one per
                page, where ``page_number`` is 1-indexed. ``heading_text`` is a
                short snippet (first non-empty line(s) of the page).

        Returns:
            The 1-indexed page number the LLM identifies, or ``None`` when it
            cannot confidently locate one. Returning ``None`` lets the caller
            fail closed rather than fabricate a page.
        """
        if not page_index:
            return None

        valid_pages = {int(pn) for pn, _ in page_index}

        messages = self._build_locate_messages(page_index)
        try:
            response = get_completion_from_messages(messages, model=self.model)
        except Exception as e:
            # Fail closed on any LLM/transport error: do not guess a page.
            print(f"Warning: LLM page location failed: {e}. Failing closed.")
            return None

        return self._parse_locate_response(response, valid_pages)

    def _build_locate_messages(self, page_index: List) -> list:
        """Build the messages that ask the LLM to locate the pin table."""
        index_lines = []
        for page_number, heading in page_index:
            snippet = " ".join(str(heading or "").split())
            if len(snippet) > 160:
                snippet = snippet[:157] + "..."
            index_lines.append(f"Page {page_number}: {snippet}")
        index_text = "\n".join(index_lines)

        system_prompt = (
            "You are locating the page of an electronic component datasheet "
            "that contains the pin-assignment / pinout table (pin numbers "
            "mapped to pin names and functions). You are given a compact index "
            "of page headings for the whole document."
        )

        user_prompt = f"""Document page index (one line per page):
{index_text}

Which single page most likely contains the pin-assignment / pinout table
(pin numbers with their names/functions)?

Answer with ONLY the page number (for example: 385). If none of the pages
clearly contains a pin-assignment table, answer with exactly NONE."""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _parse_locate_response(self, response: str, valid_pages) -> Optional[int]:
        """Parse the located page number, failing closed on anything unclear.

        Only a page number that actually appears in the supplied index is
        accepted; an explicit NONE, an out-of-range number, or an
        unparseable answer all return ``None``.
        """
        if not response:
            return None

        text = response.strip()
        if text.upper().startswith("NONE"):
            return None

        import re as _re
        match = _re.search(r"\d+", text)
        if not match:
            return None

        page_number = int(match.group())
        if page_number not in valid_pages:
            return None

        return page_number

    def verify_single_page(
        self,
        candidate,
        page_content: str
    ) -> bool:
        """
        Verify a single page contains pinout information.

        Args:
            candidate: PageCandidate object
            page_content: Text content from page

        Returns:
            True if page contains pinout information, False otherwise
        """
        return self._ask_llm_about_page(page_content)

    def _ask_llm_about_page(self, page_content: str) -> bool:
        """
        Ask LLM if page contains pinout information.

        Args:
            page_content: Text content from page

        Returns:
            True if LLM indicates page contains pinout info
        """
        messages = self._build_verification_messages(page_content)

        # Call LLM
        try:
            response = get_completion_from_messages(messages, model=self.model)
            return self._parse_verification_response(response)
        except Exception as e:
            # On error, conservatively include page
            print(f"Warning: LLM verification failed: {e}. Including page by default.")
            return True

    def _build_verification_messages(self, page_content: str) -> list:
        """
        Build messages for LLM page verification.

        Args:
            page_content: Text content from page

        Returns:
            List of message dictionaries
        """
        system_prompt = (
            "You are verifying if a page from an electronic component datasheet "
            "contains pinout/pin configuration information."
        )

        user_prompt = f"""Page content:
{page_content}

Does this page contain pinout information such as:
- Pin numbers and their names
- Pin descriptions or functions
- Package configuration diagrams
- Mechanical/pin drawing specifications

Answer with either "YES" or "NO" only, followed by a brief one-sentence explanation."""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

    def _parse_verification_response(self, response: str) -> bool:
        """
        Parse LLM verification response.

        Args:
            response: LLM response text

        Returns:
            True if LLM says YES, False otherwise
        """
        response_upper = response.strip().upper()

        if response_upper.startswith("YES"):
            return True
        elif response_upper.startswith("NO"):
            return False

        # If unclear, conservatively say yes
        return True

    def analyze_sample_pages(
        self,
        page_contents: List[str],
        page_numbers: List[int]
    ) -> dict:
        """
        Analyze sample pages to provide guidance for detection.

        Useful when overall pattern matches are low.

        Args:
            page_contents: List of page text contents
            page_numbers: Corresponding page numbers

        Returns:
            Dictionary with analysis results and recommendations
        """
        messages = self._build_sample_analysis_messages(page_contents, page_numbers)

        try:
            response = get_completion_from_messages(messages, model=self.model)
            return self._parse_sample_analysis(response)
        except Exception as e:
            print(f"Warning: Sample analysis failed: {e}")
            return {"recommendation": "use_all_candidates"}

    def _build_sample_analysis_messages(
        self,
        page_contents: List[str],
        page_numbers: List[int]
    ) -> list:
        """Build messages for analyzing sample pages."""
        samples = "\n\n".join(
            f"--- Page {num} ---\n{content}"
            for num, content in zip(page_numbers, page_contents)
        )

        system_prompt = "You are analyzing sample pages from an electronic component datasheet to understand pinout information location."

        user_prompt = f"""Sample pages:
{samples}

Based on these samples, provide:
1. What patterns indicate pinout pages?
2. What should we look for in other pages?
3. Are there any unusual characteristics?

Provide a brief analysis in 3-4 sentences."""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

    def _parse_sample_analysis(self, response: str) -> dict:
        """Parse LLM sample analysis response."""
        # For now, just return response
        return {
            "analysis": response,
            "recommendation": "use_all_candidates"
        }
