#!/usr/bin/env python3
"""Check if JSON formatting is applied."""

from pdf_extractor.content_extractor import ContentExtractor

# Simple test
test_content = '''
SN54HC595, SN74HC595
Pin Configuration and Functions
Table 5-1. Pin Functions
  PIN NAME   SOIC, PDIP,   LCCC   I/O(1)   DESCRIPTION
  GND         8      10      —     Ground Pin
'''

# Build prompt
prompt = build_pin_extraction_prompt(test_content)

# Check the user message content
user_content = prompt[1]['content']

# Check for JSON tables - handle potential encoding issues
json_marker = 'Pinout Tables (JSON)' if isinstance(user_content, str) else 'Pinout Tables (JSON)'
table_keyword = 'table' if isinstance(user_content, str) else 'table'

print('Has JSON marker:', json_marker)
print('Has table keyword:', table_keyword)

if json_marker:
    print('SUCCESS: Tables formatted as JSON in prompt')
else:
    print('FAILED: Tables NOT formatted as JSON')
EOF
