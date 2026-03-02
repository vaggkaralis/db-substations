#!/usr/bin/env python3
"""Test that Greek inspection strings are properly loaded."""

from strings import STRINGS_EL, STRINGS_EN

print("Testing Greek inspection strings...")
print()

# Test 1: Basic checks
has_rows_el = "INSPECTION_ROWS" in STRINGS_EL.get("MESSAGES", {})
has_rows_en = "INSPECTION_ROWS" in STRINGS_EN.get("MESSAGES", {})
has_vidar_el = "VIDAR_VACUUM_CHECK_LABEL" in STRINGS_EL.get("MESSAGES", {})
has_section_el = "INSPECTION_SECTION_2" in STRINGS_EL.get("MESSAGES", {})

print(f"INSPECTION_ROWS in STRINGS_EL: {has_rows_el}")
print(f"INSPECTION_ROWS in STRINGS_EN: {has_rows_en}")
print(f"VIDAR_VACUUM_CHECK_LABEL in STRINGS_EL: {has_vidar_el}")
print(f"INSPECTION_SECTION_2 in STRINGS_EL: {has_section_el}")
print()

# Test 2: Count of items
if has_rows_el:
    el_rows = STRINGS_EL["MESSAGES"]["INSPECTION_ROWS"]
    en_rows = STRINGS_EN["MESSAGES"]["INSPECTION_ROWS"]
    print(f"Greek INSPECTION_ROWS count: {len(el_rows)}")
    print(f"English INSPECTION_ROWS count: {len(en_rows)}")
    print(f"First Greek item: {el_rows[0]}")
    print(f"First English item: {en_rows[0]}")
    print()

# Test 3: Test the proxy system
print("Testing proxy system...")
try:
    from strings_proxy import STRINGS
    from config_manager import get_current_language
    
    current_lang = get_current_language()
    print(f"Current language: {current_lang}")
    
    # Access through proxy
    messages = STRINGS["MESSAGES"]
    proxy_rows = messages.get("INSPECTION_ROWS", [])
    print(f"Rows via proxy: {len(proxy_rows)} items")
    if proxy_rows:
        print(f"Via proxy (first item): {proxy_rows[0]}")
    
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")

print("\nTest complete!")
