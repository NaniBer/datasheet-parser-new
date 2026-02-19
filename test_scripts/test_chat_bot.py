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
    messages = [{"role": "user", "content": "What is 2 + 2?"}]
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
