#!/usr/bin/env python3
"""Test chat_bot.py LLM integration with detailed output."""

import sys
sys.path.insert(0, '/Users/mac/Documents/Projects/datasheet-parser-new')

from src.chat_bot import get_completion_from_messages


def main():
    print("=" * 70)
    print("TEST: chat_bot.py LLM Integration - Detailed Output")
    print("=" * 70)

    # Test API call with correct message format
    messages = [{"role": "user", "content": """Analyze the following pin layout description. For each pin, extract its name, primary function, and precise location within the grid. Define a conceptual Cartesian coordinate system where the center of the component body is (0,0). Each step in the grid (between adjacent rows or adjacent columns) is considered 1 unit. Assign a conceptual (X,Y) coordinate to each pin. When assigning row numbers, refer to the provided '14 rows' list, where the first item is 'Row 1', the second is 'Row 2', and so on. Resolve any potential ambiguities by prioritizing explicit row/column numbers where provided. Explicitly describe the arrangement's directionality and any special features.
Format the output as follows:
Conceptual Coordinate System:
Origin (0,0): Center of the component body.
Unit: Each step in the grid (between adjacent rows or columns) is 1 unit.
X-axis: Positive X to the right. Column 1 would be at the leftmost side.
Y-axis: Positive Y upwards. Row 1 would be at the topmost side.
Extracted Pin List (detailed and uniquely located):
Pin Name: [Name]
Function: [Primary function, e.g., Ground, Power Supply, Input/Output, Not Connected]
Row Location: [Specific row number, e.g., "Row 1", "Row 2", "Distributed across multiple rows"]
Column Location: [Specific column number, e.g., "Column 1", "Column 2", "Distributed across multiple columns"]
Conceptual (X,Y) Coordinate: (X, Y) [Provide a numerical conceptual coordinate based on the defined system, using '1' as the step unit.]
Additional Notes: [Any specific details like "at beginning/end of row", "first pin in column list", "part of a group of IO pins", "Keepout Zone implication"]
... (repeat for all unique pin names mentioned in the row and column lists)
Directionality and Grid Layout:
Total Rows: [Number] (e.g., "14 rows")
Row Direction: [e.g., "top-to-bottom"]
Row Pin Sequence: [List all pin names defining the start of each row, in order, explicitly indicating row number, e.g., "Row 1: GND, Row 2: 3V3, ..."]
Total Columns: [Number] (e.g., "24 columns")
Column Direction: [e.g., "left-to-right"]
Column Pin Sequence: [List all pin names defining each column, in order, explicitly indicating column number, e.g., "Column 1: GND, Column 2: IO23, ..."]
Specific Orientations/Zones:
Keepout Zone: [Description of location and purpose]
Ground (GND) Pin Placement: [Detailed description of where GND pins are found]
Power Supply Pin Placement: [Detailed description for 3V3, EN]
Input/Output (IO) Pin Distribution: [General description of IO pin spread]
Not Connected (NC) Pin Usage: [Description of NC pin locations and meaning]
The pin layout in the provided image is arranged in a grid-like pattern, which is typical for many electronic modules and boards. Here's a breakdown of how the pins are arranged:\n\n1. **Rows and Columns**: The pins are organized into rows and columns.\n   - There are 14 rows (from top to bottom: GND, 3V3, EN, SENSOR_VP, SENSOR_VN, IO34, IO35, IO32, IO33, IO25, IO26, IO27, IO14, IO12).\n   - There are 24 columns (from left to right: GND, IO23, IO22, TXD0, RXD0, NC, NC, NC, NC, NC, NC, NC, NC, NC, NC, NC, NC, NC, NC, NC, NC, NC, NC, NC).\n\n2. **Keepout Zone**: There is a marked \"Keepout Zone\" at the top of the diagram, indicated by a dashed red box. This zone is important for antenna placement and should be avoided.\n\n3. **Ground (GND)**: The ground pins (GND) are located at the beginning and end of each row, except for the last row where there are no additional GND pins.\n\n4. **Power Supply Pins**: The power supply pins (3V3 and EN) are located in the second row from the top.\n\n5. **Input/Output Pins**: The input/output pins (IO) are distributed across the remaining rows, with some rows having multiple IO pins and others having none.\n\n6. **Not Connected (NC)**: Some columns have \"NC\" (Not Connected) labels, indicating that these pins are not used or are reserved for future use.\n\nThis arrangement helps in easily identifying and accessing specific pins when working with the module."""}]
    print("\nCalling LLM with model: llama-3")
    print("Prompt: What is 2 + 2?")
    try:
        result = get_completion_from_messages(messages, model="llama-3")
        print(f"\nResult: {result}")
    except Exception as e:
        print(f"\nError: {type(e).__name__}: {e}")

    # # Test 1: Check if chat_bot module can be imported
    # print("\n[1] Checking chat_bot module...")
    # try:
    #     from src import chat_bot
    #     print("  ✅ Module import successful")
    # except ImportError as e:
    #     print(f"  ❌ Import failed: {e}")

    # # Test 2: Check if FASTCHAT_API_KEY is set
    # import os
    # print("\n[2] Checking API key...")
    # api_key = os.getenv("FASTCHAT_API_KEY", "NOT_SET")
    # if api_key and api_key != "NOT_SET":
    #     print(f"  ✅ API key is set: {api_key[:20]}...")
    # else:
    #     print(f"  ⚠️ API key is NOT set (value: '{api_key}')")
    #     print("   Set it with: export FASTCHAT_API_KEY='your-key-here'")

    # # Test 3: Test call_llm function signature
    # print("\n[3] Testing call_llm function signature...")
    # import inspect
    # sig = inspect.signature(call_llm)
    # print(f"  Function signature: {sig}")
    # print(f"  Parameters: {sig.parameters}")
    # print("  ✅ Function signature is correct")

    # # Test 4: Test get_completion_from_messages signature
    # print("\n[4] Testing get_completion_from_messages function signature...")
    # sig = inspect.signature(get_completion_from_messages)
    # print(f"  Function signature: {sig}")
    # print(f"  Parameters: {sig.parameters}")
    # print("  ✅ Function signature is correct")

    # # Test 5: Test actual API call (will fail without API key)
    # print("\n[5] Testing API call (will fail without API key)...")
    # try:
    #     result = call_llm(user_prompt="What is 2 + 2?")
    #     print(f"Prompt: What is 2 + 2?")
    #     print(f"Result: {result}")
    #     print("  ⚠️  Expected: Connection error (no API key)")
    # except Exception as e:
    #     print(f" ❌ Unexpected error: {type(e).__name__}: {e}")

    # print()
    # print("NOTE: To test with real API, set FASTCHAT_API_KEY environment variable")
    # print("=" * 70)
    # print("TEST COMPLETE")


if __name__ == "__main__":
    main()
