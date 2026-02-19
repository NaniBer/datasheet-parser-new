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
