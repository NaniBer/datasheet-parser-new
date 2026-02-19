"""LLM API Client for pin data extraction using FastChat."""

from typing import Dict, List, Optional
import json

from ..models.pin_data import PinData, Pin, PackageInfo
from ..chat_bot import get_completion_from_messages, build_pin_extraction_prompt


class LLMClient:
    """
    LLM API client for extracting pin data from datasheet content using FastChat.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "llama-3",
        **kwargs
    ):
        """
        Initialize LLM client.

        Args:
            api_key: API key for LLM service (uses FASTCHAT_API_KEY env var if None)
            model: Model name to use (default: llama-3)
            **kwargs: Additional configuration options
        """
        # API key is handled by chat_bot.py via FASTCHAT_API_KEY env var
        # api_key parameter is kept for interface compatibility
        self.api_key = api_key
        self.model = model
        self.config = kwargs

    def extract_pin_data(
        self,
        content: str,
        images: Optional[List[bytes]] = None,
        part_number: Optional[str] = None,
        **kwargs
    ) -> PinData:
        """
        Extract pin data from datasheet content.

        Args:
            content: Text content extracted from datasheet
            images: Optional list of image data (for multimodal models)
                    Currently not used but kept for interface compatibility
            part_number: Optional specific part number to match package variant
            **kwargs: Additional parameters

        Returns:
            PinData object with extracted information

        Raises:
            ValueError: If LLM response cannot be parsed
        """
        # Build messages for pin extraction with part number if provided
        messages = build_pin_extraction_prompt(content, part_number=part_number)

        # Call LLM
        response = get_completion_from_messages(messages, model=self.model)

        # Parse response into PinData
        return self._parse_llm_response(response)

    def _parse_llm_response(self, response: str) -> PinData:
        """
        Parse LLM response into PinData object.

        Args:
            response: Raw response from LLM

        Returns:
            PinData object

        Raises:
            ValueError: If response cannot be parsed
        """
        try:
            # Remove markdown code blocks if present
            clean_response = response.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            if clean_response.startswith("```"):
                clean_response = clean_response[3:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()

            # Parse JSON
            data = json.loads(clean_response)

            # Parse package info - handle None values
            package_data = data.get("package", {})
            width = package_data.get("width")
            height = package_data.get("height")

            # Convert to float if not None, otherwise use 0
            width_val = float(width) if width is not None else 0.0
            height_val = float(height) if height is not None else 0.0

            package = PackageInfo(
                type=package_data.get("type", "Unknown"),
                pin_count=package_data.get("pin_count", 0),
                width=width_val,
                height=height_val,
                pitch=package_data.get("pitch"),
                thickness=package_data.get("thickness"),
            )

            # Parse pins
            pins_data = data.get("pins", [])
            pins = []
            for pin_data in pins_data:
                # Handle both string and int pin numbers
                pin_number = pin_data.get("number")
                if isinstance(pin_number, str):
                    # Try to extract number from string like "1" or "Pin 1"
                    import re
                    match = re.search(r'\d+', pin_number)
                    pin_number = int(match.group(0)) if match else 0
                else:
                    pin_number = int(pin_number)

                pins.append(
                    Pin(
                        number=pin_number,
                        name=pin_data.get("name", ""),
                        function=pin_data.get("function"),
                    )
                )

            # Create PinData
            pin_data = PinData(
                component_name=data.get("component_name", "Unknown"),
                package=package,
                pins=pins,
                extraction_method=data.get("extraction_method", "Unknown"),
            )

            return pin_data

        except json.JSONDecodeError as e:
            # Show a snippet of the response for debugging
            response_preview = clean_response[:200] if len(clean_response) > 200 else clean_response
            raise ValueError(f"Failed to parse LLM response as JSON: {e}\nResponse preview: {response_preview}")
        except Exception as e:
            # Show more detail about the error
            import traceback
            error_details = f"{e}\n{traceback.format_exc()}"
            raise ValueError(f"Failed to parse PinData from LLM response: {error_details}")

    def set_api_key(self, api_key: str) -> None:
        """
        Set or update API key.

        Note: API key is loaded from FASTCHAT_API_KEY env var in chat_bot.py.
        This method is kept for interface compatibility.
        """
        self.api_key = api_key
        import os
        os.environ["FASTCHAT_API_KEY"] = api_key

    def set_model(self, model: str) -> None:
        """Set or update model name."""
        self.model = model
