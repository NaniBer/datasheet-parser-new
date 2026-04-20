"""Chat bot for LLM interactions - FastChat API client."""

from openai import OpenAI
import os
import time
from dotenv import load_dotenv

from .exceptions import LLMExtractionError, ErrorCodes

load_dotenv()

import nest_asyncio

nest_asyncio.apply()


BASE_URL = "https://fastchat.ideeza.com/v1"
#BASE_URL = "https://fastchattest.ideeza.com/v1"
API_KEY = os.getenv("FASTCHAT_API_KEY")


#
client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL
)


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


def build_table_extraction_prompt(table_data: str) -> list:
    """
    Build specialized prompt for table-only extraction.

    Args:
        table_data: JSON-formatted table data

    Returns:
        List of message dictionaries for LLM API call
    """
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

                "VARIANT SELECTION (STEP 2):\n"
                "IF MULTIPLE VARIANTS DETECTED:\n"
                "- CHOOSE ONE variant (prefer SOIC or PDIP - most common)\n"
                "- Extract ONLY pins for that ONE variant\n"
                "- Example: If SOIC-16, extract exactly 16 pins using SOIC column numbers\n"
                "- DO NOT mix SOIC and LCCC pins together!\n\n"

                "IF SINGLE VARIANT:\n"
                "- Extract all pins from the table\n\n"

                "PIN EXTRACTION RULES (STEP 3):\n"
                "1. EXACT NAMES: Use pin names EXACTLY as shown (QA, QB, QC - NOT Q1, Q2, Q3)\n"
                "2. CORRECT NUMBERS: Use pin numbers from the CHOSEN variant column only\n"
                "3. VERIFY COUNT: Pin count must match package type (SOIC-16 = 16 pins)\n"
                "4. NO DUPLICATES: Each pin number should appear only once\n"
                "5. ALL PINS: Extract EVERY pin, not just a sample\n\n"

                "FUNCTION CLASSIFICATION:\n"
                "- power: VCC, VDD, AVCC, VEE\n"
                "- ground: GND, VSS, AGND, DGND\n"
                "- input: SER, DATA, DIN, CLK, RCLK, SRCLK\n"
                "- output: QA, QB, QC, QD, QE, QF, QG, QH, QH', QOUT\n"
                "- control: OE, ENABLE, RESET, CLEAR, SRCLR\n"
                "- none: NC (no connection)\n\n"

                "OUTPUT FORMAT (JSON ONLY):\n"
                "{\n"
                "  \"component_name\": \"Component name (e.g., 74HC595, STM32F103)\",\n"
                "  \"package\": {\n"
                "    \"type\": \"Package type with pin count (e.g., SOIC-16, PDIP-16)\",\n"
                "    \"pin_count\": exact_number_of_pins,\n"
                "    \"width\": null,\n"
                "    \"height\": null,\n"
                "    \"pitch\": null\n"
                "  },\n"
                "  \"pins\": [\n"
                "    {\"number\": 1, \"name\": \"VCC\", \"function\": \"power\"},\n"
                "    {\"number\": 2, \"name\": \"QA\", \"function\": \"output\"},\n"
                "    ...\n"
                "  ],\n"
                "  \"extraction_method\": \"Table\"\n"
                "}\n\n"

                "ABSOLUTE REQUIREMENTS:\n"
                "- Return ONLY raw JSON (no ```json, no explanations)\n"
                "- Extract pin names EXACTLY as in table\n"
                "- If multiple variants, choose ONE and extract ONLY that\n"
                "- Verify pin count matches package type\n"
                "- No duplicate pin numbers\n"
            )
        },
        {
            "role": "user",
            "content": (
                "Parse this pin configuration table and extract PinData.\n\n"
                "INSTRUCTIONS:\n"
                "1. Analyze table structure (header rows, columns, variants)\n"
                "2. If multiple package variants exist, choose ONE (prefer SOIC or PDIP)\n"
                "3. Extract pins for the chosen variant ONLY\n"
                "4. Verify pin count matches the package type\n"
                "5. Use exact pin names from the table\n\n"
                "--- TABLE DATA ---\n"
                f"{table_data}\n"
                "--- END TABLE DATA ---"
            )
        }
    ]
    return messages


def build_pin_extraction_prompt(datasheet_content: str, part_number: str = None, table_only_mode: bool = False) -> list:
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
    extraction_tasks = (
        "EXTRACTION TASKS:\n"
        "1. Identify the Component Name (full part number or family).\n"
        "2. Extract Package type, pin count, and physical dimensions (width, height, pitch).\n"
        "3. Map every physical pin to its name and function.\n"
        "4. Note the extraction method (Table, Diagram, or Mixed).\n"
    )

    # CRITICAL INSTRUCTION: Do not generate sequential pin names.
    # When pinout table data is present in text content, use exact names from table.
    # If table contains explicit pin names like QA, QB, QC, QH, use THOSE EXACTLY.
    # DO NOT create sequential names (Q1, Q2, Q3...) when table provides actual names.

    # Table-only mode: Use specialized table extraction prompt
    if table_only_mode:
        return build_table_extraction_prompt(datasheet_content)

    # Normal mode: Full prompt for diagrams + tables
    messages = [
        {
            "role": "system",
            "content": (
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
                "4. PACKAGE ACCURACY: Extract package type from headings (e.g., '8-Lead SOIC', '28-Pin DIP') "
                "and dimensions from mechanical drawings.\n"
                "5. PACKAGE VARIANT MATCHING: If the datasheet contains multiple package variants, "
                "match the part number to the correct variant by checking suffix codes (e.g., RBT6=64-pin, RBT8=48-pin, RCT6=144-pin). "
                "Extract pins ONLY for the matched variant.\n"
                "6. CROSS-VERIFICATION: After extraction, verify:\n"
                "   - Pin count matches package name (e.g., 'PDIP-40' should have exactly 40 pins)\n"
                "   - Power pins (VCC/VDD, GND/VSS) are present and in correct locations\n"
                "   - If verification fails, you have the wrong package variant!\n"
                "7. COMPLETE EXTRACTION: Include ALL pins for the matched variant, not just a sample. "
                "If pinout spans multiple pages, combine everything.\n"
                "8. FUNCTION CLASSIFICATION: Classify each pin's primary function: "
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
                "- If a specific part number is provided, extract ONLY pins for that package variant"
            )
        },
        {
            "role": "user",
            "content": (
                "Extract complete PinData from the datasheet content provided below. "
                "This data will be used to generate 3D CAD models.\n\n"
                f"{extraction_tasks}\n\n"
                "--- DATASHEET CONTENT START ---\n"
                f"{datasheet_content}\n"
                "--- DATASHEET CONTENT END ---"
            )
        }
    ]

    return messages
