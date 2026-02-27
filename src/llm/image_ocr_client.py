"""
AI API client for image-based pinout extraction from datasheets.

This module integrates with the qwen.ideeza.com vision API to extract
pinout information from PDF page images.
"""

import base64
import io
import json
import mimetypes
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

try:
    import requests
except ImportError:
    requests = None


@dataclass
class PinoutExtractionResult:
    """Result of pinout extraction from an image."""
    component_name: str
    package_type: str
    pin_count: int
    pins: List[dict]  # List of {number, name} dicts
    confidence: float
    extraction_method: str = "image_ocr"
    notes: str = ""


class ImageOCRClient:
    """
    API client for image-based pinout extraction using qwen.ideeza.com.
    """

    # API configuration
    API_URL = "https://qwen.ideeza.com/describe_image/"
    DEFAULT_OUTPUT_TOKEN = 4096
    DEFAULT_TIMEOUT = 120

    # Default prompt for pinout extraction
    DEFAULT_PROMPT = """You are an expert at reading electronic component pinout diagrams from datasheet images.

Analyze the provided image and extract complete pinout information.

## Your Task:

1. **Identify the component** (e.g., ATmega164A, NE555, STM32F103, ESP32-WROOM-32)

2. **Determine the package type** (e.g., PDIP-40, DIP-8, TQFP-44, LQFP-64, SOIC-16, QFN-38)

3. **Extract ALL pins** with their numbers and names:
   - For DIP packages: Pin 1 is top-left, numbering goes DOWN left side, then UP right side
   - For SOIC/TQFP/LQFP: Pin 1 is top-left, numbering is counter-clockwise
   - For QFN: Pin 1 is top-left, numbering is counter-clockwise on all 4 sides
   - Include ALL pins (not just a sample)

4. **Verify key pins:**
   - Power pins: VCC/VDD, GND/VSS, AVCC, AREF, VBAT
   - Crystal pins: XTAL1, XTAL2, OSC_IN, OSC_OUT
   - Control pins: RESET, CS, EN, BOOT0
   - Communication pins: SCK, MISO, MOSI, TX, RX, SDA, SCL

5. **Port pin patterns:** Look for PA0-PA7, PB0-PB7, PC0-PC7, PD0-PD7, or IO0-IO39

## Output Format:

Return ONLY valid JSON (no markdown code blocks, no additional text):

{
  "component_name": "Component Name",
  "package_type": "Package Type",
  "pin_count": 40,
  "pins": [
    {"number": 1, "name": "PB0", "function": "Port B bit 0"},
    {"number": 2, "name": "PB1", "function": "Port B bit 1"},
    ...
  ],
  "extraction_confidence": 0.95,
  "notes": "Optional notes about extraction quality"
}

## Important Rules:

- Extract ALL pins for the package shown
- Verify pin count matches package type (e.g., DIP-8 must have exactly 8 pins)
- If pin names are abbreviated (e.g., "I/O01"), expand them (e.g., "IO1")
- If you can't read a pin number clearly, use the layout to infer it
- For pins with alternative names (e.g., "PD0/USART0_RX"), include the primary name
- Return ONLY JSON - no explanations or additional text"""

    def __init__(
        self,
        api_url: str = None,
        output_token: int = None,
        timeout: int = None
    ):
        """
        Initialize the OCR client.

        Args:
            api_url: Optional custom API URL
            output_token: Optional max output tokens
            timeout: Optional request timeout in seconds
        """
        if requests is None:
            raise ImportError(
                "requests library is required. Install with: pip install requests"
            )

        self.api_url = api_url or self.API_URL
        self.output_token = output_token or self.DEFAULT_OUTPUT_TOKEN
        self.timeout = timeout or self.DEFAULT_TIMEOUT

    def _build_prompt(self, part_number: str = None) -> str:
        """
        Build the prompt for pinout extraction.

        Args:
            part_number: Optional part number to match

        Returns:
            Prompt string
        """
        prompt = self.DEFAULT_PROMPT
        if part_number:
            prompt = prompt + f"\n\nTarget component: {part_number}"
        return prompt

    def extract_pinout_from_image(
        self,
        image_data: bytes,
        page_number: int = None,
        part_number: str = None,
        prompt: str = None
    ) -> PinoutExtractionResult:
        """
        Extract pinout information from a single page image.

        Args:
            image_data: Image data as bytes (PNG/JPEG)
            page_number: Optional page number for logging
            part_number: Optional part number to match (e.g., "ATmega164A")
            prompt: Optional custom prompt (uses default if not provided)

        Returns:
            PinoutExtractionResult with extracted pinout data
        """
        if page_number is not None:
            print(f"[ImageOCRClient] Processing page {page_number}...")
        print(f"[ImageOCRClient] Image size: {len(image_data)} bytes")

        # Build prompt
        prompt_text = prompt or self._build_prompt(part_number)

        # Create multipart form data
        # The API expects:
        # - file: image file upload
        # - text: prompt
        # - output_token: integer

        files = {
            "file": ("image.png", io.BytesIO(image_data), "image/png")
        }
        data = {
            "text": prompt_text,
            "output_token": str(self.output_token)
        }

        try:
            # Call API
            response = requests.post(
                self.api_url,
                headers={"accept": "application/json"},
                files=files,
                data=data,
                timeout=self.timeout
            )

            # Raise error on non-2xx
            response.raise_for_status()

            # Parse JSON response
            result = response.json()

            # Try to parse the response text for pinout data
            return self._parse_api_response(result)

        except requests.HTTPError as e:
            print(f"[ImageOCRClient] HTTP Error: {e}")
            # Try to get more info from response
            if hasattr(e, 'response') and e.response is not None:
                body_preview = e.response.text[:2000] if e.response.text else ""
                print(f"[ImageOCRClient] Response body: {body_preview}")
            return self._empty_result()
        except Exception as e:
            print(f"[ImageOCRClient] Error: {e}")
            import traceback
            traceback.print_exc()
            return self._empty_result()

    def _parse_api_response(self, response: Dict[str, Any]) -> PinoutExtractionResult:
        """
        Parse the API response and extract pinout data.

        Args:
            response: Raw API response as dict

        Returns:
            PinoutExtractionResult
        """
        # The API response can have different structures:
        # Format 1: {"description": {"component_name": "...", ...}}
        # Format 2: {"description": "```json\n{...}\n```"}
        # Format 3: {"raw_text": "..."}
        # Format 4: Direct JSON object

        import re

        # Try Format 1: description field is a dict with the actual data
        if "description" in response:
            description = response.get("description")

            # If description is already a dict, use it directly
            if isinstance(description, dict):
                return PinoutExtractionResult(
                    component_name=description.get("component_name", ""),
                    package_type=description.get("package_type", ""),
                    pin_count=description.get("pin_count", 0),
                    pins=description.get("pins", []),
                    confidence=description.get("extraction_confidence", 0.0),
                    notes=description.get("notes", "")
                )

            # If description is a string, look for JSON in markdown code blocks
            if isinstance(description, str):
                # Look for JSON in markdown code blocks
                json_match = re.search(r'```(?:json)?\s*\n?(\{.*?\})\n?```', description, re.DOTALL)
                if json_match:
                    json_str = json_match.group(1)
                else:
                    # Try to find JSON object directly
                    json_match = re.search(r'\{[\s\S]*\}', description)
                    if json_match:
                        json_str = json_match.group(0)

                if json_str:
                    try:
                        data = json.loads(json_str)
                        return PinoutExtractionResult(
                            component_name=data.get("component_name", ""),
                            package_type=data.get("package_type", ""),
                            pin_count=data.get("pin_count", 0),
                            pins=data.get("pins", []),
                            confidence=data.get("extraction_confidence", 0.0),
                            notes=data.get("notes", "")
                        )
                    except json.JSONDecodeError as e:
                        print(f"[ImageOCRClient] Failed to parse JSON: {e}")
                        print(f"[ImageOCRClient] JSON string: {json_str[:500]}...")

        # Try Format 3: raw_text field
        if "raw_text" in response:
            response_text = response.get("raw_text", "")
            json_match = re.search(r'```(?:json)?\s*\n?(\{.*?\})\n?```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_match = re.search(r'\{[\s\S]*\}', response_text)
                if json_match:
                    json_str = json_match.group(0)

            if json_str:
                try:
                    data = json.loads(json_str)
                    return PinoutExtractionResult(
                        component_name=data.get("component_name", ""),
                        package_type=data.get("package_type", ""),
                        pin_count=data.get("pin_count", 0),
                        pins=data.get("pins", []),
                        confidence=data.get("extraction_confidence", 0.0),
                        notes=data.get("notes", "")
                    )
                except json.JSONDecodeError as e:
                    print(f"[ImageOCRClient] Failed to parse JSON: {e}")
                    print(f"[ImageOCRClient] JSON string: {json_str[:500]}...")

        # Try Format 4: Direct JSON (entire response is the data)
        if "component_name" in response or "package_type" in response:
            return PinoutExtractionResult(
                component_name=response.get("component_name", ""),
                package_type=response.get("package_type", ""),
                pin_count=response.get("pin_count", 0),
                pins=response.get("pins", []),
                confidence=response.get("extraction_confidence", 0.0),
                notes=response.get("notes", "")
            )

        print(f"[ImageOCRClient] Could not extract valid JSON from response")
        return self._empty_result()

    def _empty_result(self) -> PinoutExtractionResult:
        """Return an empty result."""
        return PinoutExtractionResult(
            component_name="",
            package_type="",
            pin_count=0,
            pins=[],
            confidence=0.0,
            notes="Failed to extract data from API response"
        )

    def extract_pinout_from_images(
        self,
        images: List[tuple],
        part_number: str = None
    ) -> PinoutExtractionResult:
        """
        Extract pinout information from multiple page images.

        Args:
            images: List of (page_number, image_data) tuples
            part_number: Optional part number to match

        Returns:
            PinoutExtractionResult with best extraction from all images
        """
        print(f"[ImageOCRClient] Processing {len(images)} images...")

        # Process each image and return the best result
        best_result = None
        best_confidence = 0.0

        for page_num, img_data in images:
            result = self.extract_pinout_from_image(
                img_data,
                page_number=page_num,
                part_number=part_number
            )

            if result.confidence > best_confidence:
                best_result = result
                best_confidence = result.confidence

        return best_result or self._empty_result()

    def encode_image_base64(self, image_data: bytes) -> str:
        """
        Encode image data as base64 string.

        Args:
            image_data: Image data as bytes

        Returns:
            Base64 encoded string
        """
        return base64.b64encode(image_data).decode('utf-8')


# Backward compatibility alias
DummyImageOCRClient = ImageOCRClient
