"""
Solutions for fixing incorrect pin extraction from LLM

## Problem Analysis
The LLM extracts pins 1-8 incorrectly for ATmega164A (PDIP-40):
- Extracts PCINT8-15 instead of PA0-7/D0-7
- This suggests the LLM is reading from wrong package variant section

## Solutions

### Solution 1: Enhance Prompt with Pinout Diagram Emphasis (Recommended)
Modify the system message in src/chat_bot.py to add:

```python
"PRIORITY: Look for PINOUT DIAGRAM or PACKAGE DIAGRAM sections first. "
"These diagrams show the correct pin numbering and are more reliable than tables. "
"Only use tables to supplement missing information from diagrams.\n\n"

"PIN NUMBERING VERIFICATION: "
"- For DIP packages: Pin 1 is top-left, numbering goes down left side, then up right side "
"- For QFN/TQFP packages: Pin 1 is top-left, numbering goes counter-clockwise "
"- Cross-verify with package name (e.g., 'PDIP-40' = 40-pin DIP) "
"- If pin count doesn't match package name, you have the wrong variant!\n\n"
```

### Solution 2: Add Post-Extraction Validation
After LLM extraction, validate against known pinouts:

Create: src/llm/pinout_validator.py
```python
# Known pinouts for common components
KNOWN_PINOUTS = {
    "ATmega164A": {
        "pin_count": 40,
        "package_type": "PDIP",
        "power_pins": {"VCC": [10, 31], "GND": [11, 32]},
        "key_pins": {"RESET": 9, "XTAL1": 13, "XTAL2": 12},
    },
    "NE555": {
        "pin_count": 8,
        "package_type": "DIP",
        "power_pins": {"VCC": [8], "GND": [1]},
        "key_pins": {
            "TRIGGER": 2, "OUTPUT": 3, "RESET": 4,
            "CONTROL VOLTAGE": 5, "THRESHOLD": 6, "DISCHARGE": 7,
        },
    },
    # Add more known parts...
}

def validate_pinout(component_name: str, pin_data: PinData) -> Tuple[bool, List[str]]:
    """Validate extracted pinout against known pinouts."""
    issues = []

    # Try to find matching known pinout
    for known_name, known_data in KNOWN_PINOUTS.items():
        if known_name.lower() in component_name.lower():
            # Check pin count
            if pin_data.package.pin_count != known_data["pin_count"]:
                issues.append(f"Pin count mismatch: extracted {pin_data.package.pin_count}, expected {known_data['pin_count']}")

            # Check power pins exist
            extracted_names = {p.name: p.number for p in pin_data.pins}
            for pin_name, expected_nums in known_data["power_pins"].items():
                if pin_name not in extracted_names:
                    issues.append(f"Missing power pin: {pin_name} (expected at pins {expected_nums})")

            # Check key pins exist
            for pin_name, expected_num in known_data["key_pins"].items():
                if pin_name not in extracted_names:
                    issues.append(f"Missing key pin: {pin_name} (expected at pin {expected_num})")

            if not issues:
                return True, []
            else:
                return False, issues

    return None, ["No known pinout found for validation"]
```

Then in src/llm/client.py, after parsing LLM response:
```python
# After line 142: pin_data = PinData(...)
from .pinout_validator import validate_pinout

is_valid, issues = validate_pinout(pin_data.component_name, pin_data)
if not is_valid:
    logger.warning(f"Pinout validation failed for {pin_data.component_name}:")
    for issue in issues:
        logger.warning(f"  - {issue}")
    # Don't fail, just warn - user can decide what to do
```

### Solution 3: Better Content Filtering
Filter pages/tables more aggressively to only include relevant content:

In src/llm/client.py extract_pin_data():
```python
# Filter content by page confidence
if candidates:
    # Only use pages with confidence >= 8 for part numbers
    high_conf_pages = [c for c in candidates if c.confidence_score >= 8]
    if high_conf_pages:
        # Use only high-confidence pages for part number extraction
        pass

# Filter tables - look for pinout tables specifically
pinout_tables = []
for page_num, table_data in extracted.tables:
    # Check if table header contains pinout keywords
    if table_data and len(table_data) > 0:
        header = " ".join(str(cell).lower() for cell in table_data[0])
        if any(keyword in header for keyword in
               ["pin", "no.", "name", "function", "description"]):
            pinout_tables.append((page_num, table_data))

# Use pinout tables preferentially
if pinout_tables:
    # Only use pinout tables for extraction
    pass
```

### Solution 4: Two-Step Extraction
First extract package variant, then pins with explicit variant:

Modify prompt to:
```python
if part_number:
    extraction_tasks += (
        f"\nSTEP 1: Identify the exact package variant for '{part_number}'\n"
        f"- Look for '{part_number}' in package names, ordering codes, or pinout tables\n"
        f"- Return ONLY: package_type (e.g., 'PDIP-40'), pin_count\n"
        f"\nSTEP 2: Extract complete pinout for the identified package variant\n"
        f"- Use the package type and pin count to find the correct pinout table\n"
        f"- Extract ALL pins (count must match pin_count)\n"
        f"- Verify pin numbering follows standard for the package type\n"
    )
```

### Solution 5: Cache Known Good Extractions
Store successful extractions and reuse:

Create: src/llm/pinout_cache.py
```python
import json
from pathlib import Path

CACHE_FILE = Path("data/pinout_cache.json")

def load_cache() -> dict:
    """Load cached pinouts."""
    if CACHE_FILE.exists():
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {}

def save_cache(component_name: str, pin_data_dict: dict) -> None:
    """Save successful pinout to cache."""
    cache = load_cache()
    cache[component_name] = pin_data_dict

    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

def get_cached_pinout(component_name: str) -> Optional[dict]:
    """Get cached pinout if available."""
    cache = load_cache()
    return cache.get(component_name)
```

Then in extract_pin_data():
```python
# Try cache first
cached = get_cached_pinout(part_number) if part_number else None
if cached:
    logger.info(f"Using cached pinout for {part_number}")
    # Build PinData from cache
    return PinData(...)

# Otherwise call LLM
pin_data = client.extract_pin_data(...)

# If successful, cache it
save_cache(pin_data.component_name, pins_dict)
```

## Recommended Implementation Order

1. **Quick Win**: Implement Solution 1 (Enhanced Prompt) - Easy to add, immediate improvement
2. **Safety Net**: Implement Solution 2 (Validation) - Catches issues, provides feedback
3. **Quality**: Implement Solution 5 (Cache) - Reuses good extractions, faster
4. **Advanced**: Implement Solution 4 (Two-Step) - Better accuracy for complex datasheets

Would you like me to implement any of these solutions?
"""