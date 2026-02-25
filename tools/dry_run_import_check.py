import os
import sys

import pandas as pd

# Ensure project root is on sys.path so importers can be imported when running from tools/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from importers import _map_columns


def analyze(file_path: str):
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return 2
    try:
        all_sheets = pd.read_excel(file_path, sheet_name=None)
    except Exception as e:
        print(f"Error reading Excel: {e}")
        return 2
    # prefer Elements sheet
    df = None
    if "Elements" in all_sheets:
        df = all_sheets["Elements"]
        sheet = "Elements"
    else:
        # pick first sheet that looks like elements (has Name and Element Type / Substation Name)
        sheet = None
        for name, s in all_sheets.items():
            cols = [str(c).lower().strip() for c in s.columns]
            if "name" in cols and ("element type" in cols or "τύπος" in cols or "element" in cols):
                df = s
                sheet = name
                break
        if df is None:
            # fallback to first sheet
            sheet = list(all_sheets.keys())[0]
            df = all_sheets[sheet]

    df = _map_columns(df)

    # Determine canonical breaker and model columns
    breaker_col = None
    model_col = None
    for c in df.columns:
        if str(c).strip() == 'Τύπος Διακόπτη':
            breaker_col = c
        if str(c).strip() == 'Model Name':
            model_col = c
    # fallback heuristics
    if not breaker_col:
        for c in df.columns:
            lc = str(c).lower()
            if 'breaker' in lc or 'τύπος' in lc or 'type' in lc:
                breaker_col = c
                break
    if not model_col:
        for c in df.columns:
            lc = str(c).lower()
            if 'model' in lc or 'μοντέλο' in lc or 'μοντελο' in lc:
                model_col = c
                break

    missing_breaker_rows = []
    missing_model_rows = []
    total = 0
    # determine element type column (after mapping)
    element_col = None
    for c in df.columns:
        if str(c).strip() == 'Element Type':
            element_col = c
            break
    if not element_col:
        for c in df.columns:
            lc = str(c).lower()
            if 'element' in lc or 'τύπος' in lc or 'type' in lc:
                element_col = c
                break

    for idx, row in df.iterrows():
        total += 1
        br = None
        if breaker_col and pd.notna(row.get(breaker_col, None)):
            br = str(row.get(breaker_col)).strip()
        # Only count missing breaker-type when the row represents a breaker
        is_breaker = False
        if element_col and pd.notna(row.get(element_col, None)):
            elem_val = str(row.get(element_col)).lower()
            if 'διακόπτης' in elem_val or 'υτ' in elem_val or 'μτ' in elem_val or 'breaker' in elem_val:
                is_breaker = True
        # fallback: if breaker column exists and other heuristics fail, assume non-breaker
        if is_breaker and not br:
            missing_breaker_rows.append((idx + 2, row.to_dict()))
        mn = None
        if model_col and pd.notna(row.get(model_col, None)):
            mn = str(row.get(model_col)).strip()
        if not mn:
            missing_model_rows.append((idx + 2, row.to_dict()))

    print(f"Sheet checked: {sheet}")
    print(f"Total rows: {total}")
    print(f"Rows missing breaker type: {len(missing_breaker_rows)}")
    print(f"Rows missing model name: {len(missing_model_rows)}")

    # Show first 10 examples of rows missing breaker type
    if missing_breaker_rows:
        print('\nExamples of rows missing breaker type (row index, snippet):')
        for r, rowdict in missing_breaker_rows[:10]:
            name = rowdict.get('Name') or rowdict.get('Όνομα') or rowdict.get('name')
            model = rowdict.get('Model Name') or rowdict.get('Model') or ''
            print(f" - Excel row ~{r}: Name={name} Model={model}")

    return 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python tools/dry_run_import_check.py <excel-file-path>")
        sys.exit(2)
    path = sys.argv[1]
    rc = analyze(path)
    sys.exit(rc)
