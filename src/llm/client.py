"""LLM API Client for pin data extraction using FastChat."""

from typing import Dict, List, Optional
import json
import re

try:
    from ..models.pin_data import PinData, Pin, PackageInfo
    from ..pdf_extractor.non_pin_features import is_non_pin_feature_name
    from ..chat_bot import get_completion_from_messages, build_pin_extraction_prompt
    from ..exceptions import LLMExtractionError, ValidationError, APICredentialsError, ErrorCodes
except ImportError:  # pragma: no cover - compatibility for top-level imports in legacy scripts
    from src.models.pin_data import PinData, Pin, PackageInfo
    from src.pdf_extractor.non_pin_features import is_non_pin_feature_name
    from src.chat_bot import get_completion_from_messages, build_pin_extraction_prompt
    from src.exceptions import LLMExtractionError, ValidationError, APICredentialsError, ErrorCodes


def _coerce_pin_number(value) -> int:
    """Convert a pin number field to an integer, defaulting to 0."""
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        return int(match.group(0)) if match else 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


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
        tables_only_mode: bool = False,
        validation_feedback: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        **kwargs
    ) -> PinData:
        """
        Extract pin data from datasheet content.

        Args:
            content: Text content extracted from datasheet
            images: Optional list of image data (for multimodal models)
                    Currently not used but kept for interface compatibility
            part_number: Optional specific part number to match (e.g., "STM32F103RBT7")
            tables_only_mode: If True, content is ONLY table data (use specialized table prompt)
            validation_feedback: Optional corrective feedback from a previous failed extraction
            max_retries: Maximum number of retry attempts for LLM API calls (default: 3)
            retry_delay: Initial delay between retries in seconds (default: 1)
            **kwargs: Additional parameters

        Returns:
            PinData object with extracted information

        Raises:
            ValueError: If LLM response cannot be parsed
            Exception: If LLM API call fails after all retries
        """
        # Build messages for pin extraction
        # Use specialized table prompt for table-only mode
        if tables_only_mode:
            from ..chat_bot import build_table_extraction_prompt
            messages = build_table_extraction_prompt(
                content,
                part_number=part_number,
                validation_feedback=validation_feedback,
            )
        else:
            messages = build_pin_extraction_prompt(
                content,
                part_number=part_number,
                table_only_mode=tables_only_mode,
                validation_feedback=validation_feedback,
            )

        # Call LLM with retry logic
        response = get_completion_from_messages(
            messages,
            model=self.model,
            max_retries=max_retries,
            retry_delay=retry_delay
        )

        # Parse response into PinData
        return self._parse_llm_response(response)

    def _parse_llm_response(self, response: str) -> PinData:
        """
        Parse LLM response into PinData object.

        Handles both legacy single-package format and new multi-package format:
        - Legacy: {"package": {...}, "pins": [...]}
        - New: {"packages": [{"type": "...", "pin_count": N, "pins": [...]}, ...]}

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
            selected_package_index = data.get("selected_package_index")
            if isinstance(selected_package_index, str):
                match = re.search(r"\d+", selected_package_index)
                selected_package_index = int(match.group(0)) if match else None
            elif selected_package_index is not None:
                try:
                    selected_package_index = int(selected_package_index)
                except (TypeError, ValueError):
                    selected_package_index = None

            selected_package_type = data.get("selected_package_type") or data.get("selected_variant")
            selection_reason = data.get("selection_reason") or data.get("selected_reason")

            # Handle new multi-package format
            if "packages" in data and data["packages"]:
                packages = data["packages"]

                # Convert packages to the format expected by adapter
                packages = data["packages"]

                # Convert packages to the format expected by adapter
                packages_list = []
                for pkg_data in packages:
                    # Get values with defaults for missing fields
                    width_val = pkg_data.get("width")
                    height_val = pkg_data.get("height")
                    pitch_val = pkg_data.get("pitch")
                    thickness_val = pkg_data.get("thickness")

                    pkg_info = {
                        "type": pkg_data.get("type", "Unknown"),
                        "pin_count": pkg_data.get("pin_count", 0),
                        "width": float(width_val) if width_val is not None else 0,
                        "height": float(height_val) if height_val is not None else 0,
                        "pitch": pitch_val,
                        "thickness": thickness_val,
                        "pins": []
                    }

                    # Parse pins for this package
                    pins_data = pkg_data.get("pins", [])
                    for pin_data in pins_data:
                        pin_name = str(pin_data.get("name", "") or "").strip()
                        if is_non_pin_feature_name(pin_name):
                            # Only skip if no explicit pin number is assigned.
                            # Thermal/exposed pads with a real number (e.g. EP=25)
                            # are legitimate electrical connections.
                            raw_number = _coerce_pin_number(pin_data.get("number"))
                            if raw_number is None or raw_number <= 0:
                                continue

                        pin_number = _coerce_pin_number(pin_data.get("number"))

                        pkg_info["pins"].append({
                            "number": pin_number,
                            "name": pin_name,
                            "function": pin_data.get("function")
                        })

                    packages_list.append(pkg_info)

                # Create PinData with new multi-package format
                pin_data = PinData(
                    component_name=data.get("component_name", "Unknown"),
                    packages=packages_list,
                    selected_package_index=selected_package_index,
                    selected_package_type=selected_package_type,
                    selection_reason=selection_reason,
                    extraction_method=data.get("extraction_method", "Unknown"),
                )

            else:
                # Handle legacy single-package format
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
                    pin_name = str(pin_data.get("name", "") or "").strip()
                    if is_non_pin_feature_name(pin_name):
                        raw_number = _coerce_pin_number(pin_data.get("number"))
                        if raw_number is None or raw_number <= 0:
                            continue

                    pin_number = _coerce_pin_number(pin_data.get("number"))

                    pins.append(
                        Pin(
                            number=pin_number,
                            name=pin_name,
                            function=pin_data.get("function"),
                        )
                    )

                # Create PinData with legacy single-package format
                pin_data = PinData(
                    component_name=data.get("component_name", "Unknown"),
                    package=package,
                    pins=pins,
                    selected_package_index=selected_package_index if selected_package_index is not None else 0,
                    selected_package_type=selected_package_type,
                    selection_reason=selection_reason,
                    extraction_method=data.get("extraction_method", "Unknown"),
                )

            return pin_data

        except json.JSONDecodeError as e:
            # Show a snippet of the response for debugging
            response_preview = clean_response[:200] if len(clean_response) > 200 else clean_response
            raise LLMExtractionError(
                message=f"Failed to parse LLM response as JSON: {e}",
                error_code=ErrorCodes.LLM_PARSE_ERROR,
                details={
                    "error_type": "JSONDecodeError",
                    "error_message": str(e),
                    "response_preview": response_preview
                }
            )
        except Exception as e:
            # Show more detail about the error
            import traceback
            error_details = f"{e}\n{traceback.format_exc()}"
            raise LLMExtractionError(
                message=f"Failed to parse PinData from LLM response: {error_details}",
                error_code=ErrorCodes.LLM_PARSE_ERROR,
                details={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "traceback": traceback.format_exc()
                }
            )

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
