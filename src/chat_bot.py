"""Chat bot for LLM interactions - FastChat API client."""

from openai import OpenAI
import os
import time
from dotenv import load_dotenv

from .exceptions import LLMExtractionError, APICredentialsError, ErrorCodes

load_dotenv()

import nest_asyncio

nest_asyncio.apply()


BASE_URL = "https://fastchat.ideeza.com/v1"
#BASE_URL = "https://fastchattest.ideeza.com/v1"

_client = None


def _part_number_hint(part_number, prefix="Target part number"):
    """Prompt line for the target part, including the pin count its order
    code implies (STM32F103RBT7 -> 64), so the model reads the right
    variant column instead of guessing among them."""
    if not part_number:
        return ""
    hint = f"{prefix}: {part_number}\n"
    try:
        from .pdf_extractor.variant_selection import expected_pin_count_from_part_number
    except ImportError:  # pragma: no cover - legacy top-level imports
        from src.pdf_extractor.variant_selection import expected_pin_count_from_part_number
    implied = expected_pin_count_from_part_number(part_number)
    if implied:
        hint += (
            f"IMPORTANT: this order code implies a {implied}-pin package. "
            f"Extract the {implied}-pin variant's pin-number column; do not "
            f"use pin numbers from other variants' columns.\n"
        )
    return hint


def _get_client() -> OpenAI:
    """Return the FastChat client, creating it on first use.

    The client is constructed lazily so FASTCHAT_API_KEY is read at call
    time rather than import time (BUG-001), and a missing key fails with a
    clear error instead of an opaque authentication failure.
    """
    global _client
    if _client is None:
        api_key = os.getenv("FASTCHAT_API_KEY")
        if not api_key:
            raise APICredentialsError(
                message=(
                    "FASTCHAT_API_KEY is not set. Add it to your .env file "
                    "or export it in the environment before running."
                ),
                error_code=ErrorCodes.MISSING_API_KEY,
                details={"env_var": "FASTCHAT_API_KEY"},
            )
        _client = OpenAI(api_key=api_key, base_url=BASE_URL)
    return _client


def get_completion_from_messages(messages, model="llama-3", temperature=0, max_retries=3, retry_delay=1):
    """
    Get completion from LLM with retry logic.

    Args:
        messages: List of message dictionaries
        model: Model name to use
        temperature: Temperature for sampling
        max_retries: Maximum number of retry attempts (default: 3)
        retry_delay: Initial delay between retries in seconds (default: 1)

    Returns:
        Message content string

    Raises:
        LLMExtractionError: If all retries fail
    """
    last_exception = None

    # Resolve the client before the retry loop so a missing API key raises
    # APICredentialsError directly instead of being wrapped as an LLM error.
    client = _get_client()

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=8192,
                timeout=120  # 2 minute timeout
            )
            return response.choices[0].message.content

        except Exception as e:
            last_exception = e

            # Create LLMExtractionError with retry information
            llm_error = LLMExtractionError(
                message=f"LLM API call failed on attempt {attempt + 1}: {e}",
                error_code=ErrorCodes.LLM_API_ERROR,
                details={
                    "attempt": attempt + 1,
                    "max_retries": max_retries,
                    "exception_type": type(e).__name__,
                    "exception_message": str(e)
                }
            )

            # Check if this is a retryable error
            if not llm_error.is_retryable:
                raise llm_error

            # Exponential backoff: delay doubles each attempt
            delay = retry_delay * (2 ** attempt)
            print(f"LLM API call failed (attempt {attempt + 1}/{max_retries}): {e}")
            print(f"Retrying in {delay:.1f} seconds...")
            time.sleep(delay)

    # All retries failed
    raise LLMExtractionError(
        message=f"LLM API call failed after {max_retries} attempts. Last error: {last_exception}",
        error_code=ErrorCodes.LLM_API_ERROR,
        details={
            "max_retries": max_retries,
            "final_exception_type": type(last_exception).__name__ if last_exception else None,
            "final_exception_message": str(last_exception) if last_exception else None
        }
    )


def build_table_extraction_prompt(
    table_data: str,
    part_number: str = None,
    validation_feedback: str = None,
) -> list:
    """
    Build specialized prompt for table-only extraction (ALL variants).

    Args:
        table_data: JSON-formatted table data

    Returns:
        List of message dictionaries for LLM API call
    """
    target_hint_text = (_part_number_hint(part_number) + "\n") if part_number else ""
    validation_hint_text = (
        f"Validation feedback from a previous attempt:\n{validation_feedback}\n\n"
        if validation_feedback
        else ""
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a specialized Table Parser for electronic component pinout data. "
                "Your ONLY job is to parse pin configuration tables accurately.\n\n"

                "TABLE STRUCTURE ANALYSIS (STEP 1 - CRITICAL):\n"
                "1. COUNT HEADER ROWS: Look at the first 2-3 rows to identify headers\n"
                "2. IDENTIFY COLUMNS: Determine what each column represents\n"
                "3. DETECT VARIANTS: Check if there are MULTIPLE PACKAGE TYPES in the table\n"
                "   - Look for 'SOIC', 'PDIP', 'LCCC', 'QFP', 'TQFP', 'QFN' in headers\n"
                "   - These indicate multiple pin number columns for different packages\n\n"

                "VARIANT EXTRACTION (STEP 2 - ALL VARIANTS):\n"
                "IF MULTIPLE VARIANTS DETECTED:\n"
                "- Extract ALL variants found in the table\n"
                "- For each variant, create a separate package entry\n"
                "- Use the pin number column corresponding to that variant\n"
                "- Example: If SOIC and LCCC columns exist, create both SOIC-16 and LCCC-20 entries\n\n"

                "IF SINGLE VARIANT:\n"
                "- Create single package entry and extract all pins\n\n"

                "PIN EXTRACTION RULES (STEP 3):\n"
                "1. EXACT NAMES: Use pin names EXACTLY as shown (QA, QB, QC - NOT Q1, Q2, Q3)\n"
                "2. CORRECT NUMBERS: Use pin numbers from the corresponding variant column\n"
                "3. VERIFY COUNT: Pin count must match package type (SOIC-16 = 16 pins, LCCC-20 = 20 pins)\n"
                "4. NO DUPLICATES: Each pin number within a variant should appear only once\n"
                "5. HANDLE SYMBOLS: Convert '—', '-', or empty to 'NC' (No Connection)\n"
                "6. PACKAGE FEATURES ARE NOT PINS: Exposed pads, thermal pads, die pads, center pads, and similar package-only features are not electrical pins. Do not include them in pins or pin_count UNLESS the datasheet explicitly assigns them a pin number (e.g. 'EP = 25' or 'Exposed Pad (Pin 25)'). In that case, include them as a normal pin with that number.\n"
                "7. BROKEN ROWS: Handle rows with incomplete data (e.g., ['16'], ['11']):\n"
                "   - These represent NC pins with just a pin number\n"
                "   - Use the pin number and set name='NC', function='none'\n"
                "   - Ensure no duplicate pin numbers\n"
                "8. PIN CONFLICTS: If multiple functions share same pin number in a variant:\n"
                "   - Choose the primary function (typically the one with clear I/O designation)\n"
                "   - Do NOT create duplicate entries with same pin number\n"
                "   - Example: If RCLK and SRCLK both show pin 14, choose ONE\n"
                "9. ALL PINS: Extract EVERY pin for EACH variant, not just a sample\n"
                "10. VARIANT SEPARATION: Keep pins from different variants in separate package entries\n"
                "11. MISSING PINS: If pin count doesn't match expected:\n"
                "    - First check for NC pins in broken rows\n"
                "    - If still missing, reasonable inference is acceptable (e.g., fill gap with NC)\n"
                "    - Priority: NO DUPLICATES > COMPLETE PIN COUNT > EXACT DATA\n\n"

                "FUNCTION CLASSIFICATION:\n"
                "- power: VCC, VDD, AVCC, VEE\n"
                "- ground: GND, VSS, AGND, DGND\n"
                "- input: SER, DATA, DIN, CLK, RCLK, SRCLK\n"
                "- output: QA, QB, QC, QD, QE, QF, QG, QH, QH', QOUT\n"
                "- control: OE, ENABLE, RESET, CLEAR, SRCLR\n"
                "- none: NC, '—', '-', or empty (no connection)\n\n"

                "OUTPUT FORMAT (JSON ONLY):\n"
                "{\n"
                "  \"component_name\": \"Component name (OPTIONAL - use 'Unknown' if not found in table)\",\n"
                "  \"packages\": [\n"
                "    {\n"
                "      \"type\": \"Package type with pin count (e.g., SOIC-16, PDIP-16)\",\n"
                "      \"pin_count\": exact_number_of_pins,\n"
                "      \"width\": null,\n"
                "      \"height\": null,\n"
                "      \"pitch\": null,\n"
                "      \"pins\": [\n"
                "        {\"number\": 1, \"name\": \"VCC\", \"function\": \"power\"},\n"
                "        {\"number\": 2, \"name\": \"QA\", \"function\": \"output\"},\n"
                "        ...\n"
                "      ]\n"
                "    },\n"
                "    {\n"
                "      \"type\": \"Another variant (e.g., LCCC-20)\",\n"
                "      \"pin_count\": exact_number_of_pins,\n"
                "      \"width\": null,\n"
                "      \"height\": null,\n"
                "      \"pitch\": null,\n"
                "      \"pins\": [\n"
                "        ...\n"
                "      ]\n"
                "    }\n"
                "  ],\n"
                "  \"selected_package_index\": 0,\n"
                "  \"selected_package_type\": \"SOIC-16\",\n"
                "  \"selection_reason\": \"Why this package was chosen\",\n"
                "  \"extraction_method\": \"Table\"\n"
                "}\n\n"

                "ABSOLUTE REQUIREMENTS:\n"
                "- Return ONLY raw JSON (no ```json, no explanations)\n"
                "- Extract pin names EXACTLY as in table\n"
                "- Extract ALL variants present in the table\n"
                "- If multiple variants are present: match the part number suffix to a specific variant first; if no suffix match, prefer SMD over through-hole (TQFP/QFP > QFN > SOIC > DIP)\n"
                "- selected_package_index is zero-based and refers to the packages array order\n"
                "- If no target part number is provided, prefer the SMD variant (TQFP/QFN/SOIC over DIP) and explain in selection_reason\n"
                "- Verify pin count matches package type for EACH variant\n"
                "- No duplicate pin numbers within a single variant\n"
                "- Convert '—' or '-' to 'NC'\n"
                "- If pin count doesn't match expected, check for missing pins in table\n"
                "- component_name is OPTIONAL: extract if present in headers, else use 'Unknown'\n"
                "- PRIORITIZE accurate pin extraction over component name\n"
                + (("\n" + _part_number_hint(part_number)) if part_number else "")
                + (f"\nValidation feedback:\n{validation_feedback}\n" if validation_feedback else "")
            )
        },
        {
            "role": "user",
            "content": (
                "Parse this pin configuration table and extract PinData for ALL variants.\n\n"
                f"{target_hint_text}"
                f"{validation_hint_text}"
                "INSTRUCTIONS:\n"
                "1. Analyze table structure (header rows, columns, variants)\n"
                "2. Identify ALL package variants in the table\n"
                "3. For EACH variant, extract its pins using the correct pin number column\n"
                "4. Verify pin count matches the package type for EACH variant\n"
                "5. Use exact pin names from the table\n"
                "6. Convert '—' or '-' to 'NC' (No Connection)\n"
                "7. Handle broken rows: rows with incomplete data (e.g., ['16'], ['11']) represent NC pins\n"
                "8. Handle pin conflicts: if same pin number has multiple functions, choose ONE primary function\n"
                "9. Create a separate package entry for each variant\n"
                "10. Extract component_name from table headers or data (OPTIONAL - use 'Unknown' if not found)\n"
                "11. ENSURE CORRECT PIN COUNT: If variant says '20-pin' but you only find 16 pins, look for missing NC pins in broken rows\n"
                "12. PRIORITIZE: Accurate pin extraction > Correct component name\n\n"
                "--- TABLE DATA ---\n"
                f"{table_data}\n"
                "--- END TABLE DATA ---"
            )
        }
    ]
    return messages


def build_pin_extraction_prompt(
    datasheet_content: str,
    part_number: str = None,
    table_only_mode: bool = False,
    validation_feedback: str = None,
) -> list:
    """
    Build messages for PinData extraction from datasheet content.

    Args:
        datasheet_content: The extracted text/content from relevant datasheet pages
        part_number: Optional specific part number to match (e.g., "STM32F103RBT7")
        table_only_mode: If True, content is ONLY table data (simplified prompt)

    Returns:
        List of message dictionaries for LLM API call
    """
    # Build the extraction tasks with part number matching
    target_part_text = _part_number_hint(part_number, prefix="TARGET PART NUMBER") if part_number else ""
    validation_text = (
        f"VALIDATION FEEDBACK:\n{validation_feedback}\n" if validation_feedback else ""
    )

    extraction_tasks = (
        "EXTRACTION TASKS:\n"
        "1. Identify the Component Name (full part number or family).\n"
        "2. Extract Package type, pin count, and physical dimensions (width, height, pitch).\n"
        "3. Map every physical pin to its name and function.\n"
        "4. Note the extraction method (Table, Diagram, or Mixed).\n"
        "5. If multiple package variants are present, select the package as follows:\n"
        "   a. If the target part number has a package-specific suffix (e.g. '-AU'=TQFP, '-PU'=DIP, 'RBT7'=LQFP-64), match to that variant.\n"
        "   b. Otherwise prefer the surface-mount (SMD) variant in this order: TQFP/LQFP/QFP > QFN > SOIC/TSSOP > DIP.\n"
        "   c. Record the zero-based index in selected_package_index and explain in selection_reason.\n"
        "6. Do not count exposed pads, thermal pads, die pads, center pads, or similar package-only features as pins, unless the datasheet explicitly assigns them a pin number (e.g. 'EP = 25'). In that case, include them as a normal pin with that number.\n"
    )

    # CRITICAL INSTRUCTION: Do not generate sequential pin names.
    # When pinout table data is present in text content, use exact names from table.
    # If table contains explicit pin names like QA, QB, QC, QH, use THOSE EXACTLY.
    # DO NOT create sequential names (Q1, Q2, Q3...) when table provides actual names.

    # Table-only mode: Use specialized table extraction prompt
    if table_only_mode:
        return build_table_extraction_prompt(
            datasheet_content,
            part_number=part_number,
            validation_feedback=validation_feedback,
        )

    system_content = (
        "You are a Senior EDA (Electronic Design Automation) Technical Data Compiler. "
        "Your task is to extract structured pin data from electronic component datasheets. "
        "This data will be used to generate 3D CAD models.\n\n"

        "DEFINITIONS:\n"
        "1. COMPONENT_NAME: The full part number or name (e.g., ATmega164A, ESP32-WROOM-32, NE555).\n"
        "2. PACKAGE: Physical package information including type (DIP, QFN, SOIC, TQFP, VFBGA, etc.), "
        "pin count, dimensions, and pitch.\n"
        "3. PIN: Individual pin with number, name, and function (power, ground, input, output, etc.).\n\n"

        "STRICT MAPPING RULES:\n"
        "1. PRIORITY: Look for PINOUT DIAGRAM or PACKAGE DIAGRAM sections first. "
        "These diagrams show the correct pin numbering and are more reliable than tables. "
        "Only use tables to supplement missing information from diagrams.\n"
        "2. PHYSICAL FIDELITY: Extract ALL physical pins with their correct numbers. "
        "Never assume Pin 1 is the first signal mentioned - use package diagrams.\n"
        "3. PIN NUMBERING CONVENTIONS - Follow these exactly:\n"
        "   - DIP packages: Pin 1 is top-left corner. Numbering goes DOWN left side, then UP right side.\n"
        "   - SOIC packages: Pin 1 is top-left corner. Numbering is counter-clockwise.\n"
        "   - TQFP/LQFP packages: Pin 1 is top-left corner. Numbering is counter-clockwise.\n"
        "   - QFN packages: Pin 1 is top-left corner. Numbering is counter-clockwise.\n"
        "4. PACKAGE FEATURES ARE NOT PINS: Exposed pads, thermal pads, die pads, center pads, and similar package-only features are not electrical pins. Do not include them in pins or pin_count UNLESS the datasheet explicitly assigns them a pin number (e.g. 'EP = 25' or 'Exposed Pad (Pin 25)'). In that case, include them as a normal pin with that number.\n"
        "5. PACKAGE ACCURACY: Extract package type from headings (e.g., '8-Lead SOIC', '28-Pin DIP') "
        "and dimensions from mechanical drawings.\n"
        "6. PACKAGE VARIANT MATCHING: If the datasheet contains multiple package variants:\n"
        "   a. Match the part number suffix to the correct variant (e.g. '-AU'=TQFP-32, '-PU'=DIP-28 for ATmega; 'RBT7'=LQFP-64 for STM32).\n"
        "   b. If the suffix does not clearly identify a variant, prefer SMD over through-hole: TQFP/LQFP/QFP > QFN > SOIC/TSSOP > DIP.\n"
        "   c. Extract pins ONLY for the selected variant.\n"
        "7. CROSS-VERIFICATION: After extraction, verify:\n"
        "   - Pin count matches package name (e.g., 'PDIP-40' should have exactly 40 pins)\n"
        "   - Power pins (VCC/VDD, GND/VSS) are present and in correct locations\n"
        "   - If verification fails, you have the wrong package variant!\n"
        "8. COMPLETE EXTRACTION: Include ALL pins for the matched variant, not just a sample. "
        "If pinout spans multiple pages, combine everything.\n"
        "9. FUNCTION CLASSIFICATION: Classify each pin's primary function: "
        "'power' (VCC, VDD, AVCC), 'ground' (GND, VSS), 'input' (GPIO, data in), "
        "'output' (data out), 'analog' (ADC, DAC), or other relevant categories.\n\n"

        "OUTPUT FORMAT:\n"
        "Return ONLY valid JSON with this exact structure:\n"
        "{\n"
        "  \"component_name\": \"Component name\",\n"
        "  \"package\": {\n"
        "    \"type\": \"Package type\",\n"
        "    \"pin_count\": number,\n"
        "    \"width\": width_in_mm,\n"
        "    \"height\": height_in_mm,\n"
        "    \"pitch\": pin_spacing_mm_or_null\n"
        "  },\n"
        "  \"selected_package_index\": 0,\n"
        "  \"selected_package_type\": \"Package type chosen for geometry\",\n"
        "  \"selection_reason\": \"Why this package was chosen\",\n"
        "  \"pins\": [\n"
        "    {\"number\": 1, \"name\": \"VCC\", \"function\": \"power\"},\n"
        "    {\"number\": 2, \"name\": \"GND\", \"function\": \"ground\"},\n"
        "    ...\n"
        "  ],\n"
        "  \"extraction_method\": \"Table|Diagram|Mixed\"\n"
        "}\n\n"

        "IMPORTANT:\n"
        "- Return ONLY raw valid JSON - do NOT wrap in markdown code blocks (no ```json or ```)\n"
        "- Do NOT include any additional text, explanations, or commentary\n"
        "- If information is missing, use null or reasonable defaults\n"
        "- For pitch: use pin spacing if specified (e.g., 0.5mm, 1.27mm), otherwise null\n"
        "- For extraction_method: specify 'Table' if from table, 'Diagram' if from diagram, 'Mixed' if both\n"
        "- If a specific part number is provided, extract ONLY pins for that package variant\n"
        "- If multiple variants are present and the part number suffix does not identify one, prefer SMD (TQFP/QFN/SOIC) over DIP; set selected_package_index and explain in selection_reason\n"
        "- selected_package_index is zero-based and refers to the packages array order\n"
    )

    # Normal mode: Full prompt for diagrams + tables
    messages = [
        {
            "role": "system",
            "content": system_content + (("\n" + _part_number_hint(part_number)) if part_number else "") + (f"\nValidation feedback:\n{validation_feedback}\n" if validation_feedback else "")
        },
        {
            "role": "user",
            "content": (
                "Extract complete PinData from the datasheet content provided below. "
                "This data will be used to generate 3D CAD models.\n\n"
                f"{target_part_text}"
                f"{validation_text}"
                f"{extraction_tasks}\n\n"
                "--- DATASHEET CONTENT START ---\n"
                f"{datasheet_content}\n"
                "--- DATASHEET CONTENT END ---"
            )
        }
    ]

    return messages
