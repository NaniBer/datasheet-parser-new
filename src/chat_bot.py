"""Chat bot for LLM interactions - FastChat API client."""

from openai import OpenAI
import os
from dotenv import load_dotenv

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


def get_completion_from_messages(messages, model="llama-3", temperature=0):
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=8192
    )

    return response.choices[0].message.content


def build_pin_extraction_prompt(datasheet_content: str, part_number: str = None) -> list:
    """
    Build messages for PinData extraction from datasheet content.

    Args:
        datasheet_content: The extracted text/content from relevant datasheet pages
        part_number: Optional specific part number to match (e.g., "STM32F103RBT7")

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

    if part_number:
        extraction_tasks += (
            f"\n"
            f"CRITICAL: This datasheet contains multiple package variants. "
            f"You MUST match the specific part number '{part_number}' to its corresponding package variant.\n\n"
            f"COMMON PACKAGE VARIANTS AND PART NUMBERS:\n"
            f"- ATmega164A: Available in PDIP-40, TQFP-44, MLF-44, VFBGA-32\n"
            f"- If no suffix specified, PDIP-40 is the DEFAULT variant\n"
            f"- Look for 'Ordering Code' or 'Package Option' sections\n"
            f"- Look for package mapping tables that list available variants\n"
            f"- Match the part number suffix to the package (e.g., if 'PDIP' is in datasheet and part has no suffix, use PDIP variant)\n"
            f"- Extract pins ONLY for the package variant that matches '{part_number}'\n"
            f"- Do NOT extract pins for other package variants\n"
            f"- If PDIP-40 is the expected package, IGNORE TQFP/QFN variants even if they appear first\n"
        )

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
