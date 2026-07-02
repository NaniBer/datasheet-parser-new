#!/usr/bin/env python3
"""Test script to check what content is sent to LLM."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.pdf_extractor import PageDetector, ContentExtractor
from src.chat_bot import build_pin_extraction_prompt

# Test what text is being sent to LLM
with PageDetector('pdfs/74HC595_TI.pdf') as detector:
    candidates = detector.detect_relevant_pages(min_confidence=3)

# Extract content
with ContentExtractor('pdfs/74HC595_TI.pdf') as extractor:
    content = extractor.extract_content(candidates)

# Build LLM prompt
prompt = build_pin_extraction_prompt(content.text_content)

# Check what's in the prompt
user_content = prompt[1]['content']

print('=== LLM PROMPT INSPECTION ===')
print(f'Content length: {len(user_content)} chars')

# Check for actual pin names
actual_names = ['QA', 'QB', 'QC', 'QD', 'QE', 'QF', 'QG', 'QH', 'QH\'']
sequential_names = ['Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6', 'Q7', 'Q8', 'Q9']

print('\n=== PIN NAME DETECTION ===')
print('Checking for correct names (QA, QB, QC...):')
has_correct = any(name in user_content for name in actual_names)
print(f'  Found: {has_correct}')

print('\nChecking for hallucinated names (Q1, Q2, Q3...):')
has_sequential = any(name in user_content for name in sequential_names)
print(f'  Found: {has_sequential}')

# Check if QA is present
qa_count = user_content.count('QA')
q1_count = user_content.count('Q1')
print(f'\nQA appears {qa_count} times')
print(f'Q1 appears {q1_count} times')

# Show a snippet of the text around where pins are mentioned
import re
matches = list(re.finditer(r'Pin \d+:\s*\w+', user_content))
if matches:
    print('\n=== EXTRACTED PIN SNIPPETS (first 10) ===')
    for i, match in enumerate(matches[:10]):
        pin_line = match.group()
        # Find line in text
        line_start = user_content.rfind('\n', 0, match.start()) + 1
        line_end = user_content.find('\n', match.start())
        if line_end == -1:
            line_end = match.start()
        line_content = user_content[line_start:line_end]
        print(f'{i+1}. {line_content}')

print('\n=== CONCLUSION ===')
if has_correct and not has_sequential:
    print('SUCCESS: Correct pin names are present in prompt!')
elif has_sequential and not has_correct:
    print('FAILURE: LLM hallucinating sequential names (Q1, Q2, Q3...)')
else:
    print('MIXED: Both correct and sequential names found - check manually')
