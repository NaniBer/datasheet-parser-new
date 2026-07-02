#!/usr/bin/env python3
"""Test script to see EXACT prompt content sent to LLM."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pdf_extractor import PageDetector, ContentExtractor
from src.chat_bot import build_pin_extraction_prompt
from src.llm import LLMClient
import os

# Extract content
with PageDetector('pdfs/74HC595_TI.pdf') as detector:
    candidates = detector.detect_relevant_pages(min_confidence=3)
    
with ContentExtractor('pdfs/74HC595_TI.pdf') as extractor:
    content = extractor.extract_content(candidates)

# Build LLM prompt (this is exactly what gets sent to LLM)
prompt = build_pin_extraction_prompt(content.text_content)

# Get the exact user message content
user_message = prompt[1]['content']

print('=' * 60)
print('EXACT LLM PROMPT CONTENT (what gets sent to LLM):')
print('=' * 60)
print()
print(f'Total length: {len(user_message)} characters')
print()

# Show first 200 chars
print('First 200 characters:')
print(user_message[:200])
print()

# Search for table indicators
print()
print('=== TABLE INDICATORS IN PROMPT ===')
print('Checking for "Pinout Tables":', 'Pinout Tables' in user_message)
print('Checking for "table":', 'table' in user_message.lower())
print('Checking for "QA" (exact):', 'QA' in user_message)
print('Checking for "QB" (exact):', 'QB' in user_message)
print('Checking for "QC" (exact):', 'QC' in user_message)
print('Checking for "QH" (exact):', 'QH' in user_message or 'QH\x27' in user_message)
print()

# Search for sequential indicators (Q1, Q2, Q3)
print()
print('=== SEQUENTIAL NAME CHECK ===')
print('Checking for "Q1":', 'Q1' in user_message)
print('Checking for "Q2":', 'Q2' in user_message)
print('Checking for "Q3":', 'Q3' in user_message)
print()

print('=' * 60)
