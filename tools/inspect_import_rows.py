import sys
import os
# ensure top-level project dir is on sys.path so imports like `importers` work
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)
from importers import _map_columns
try:
    import pandas as pd
except Exception:
    pd = None

try:
    from import_validator import validate_breaker_category
except Exception:
    validate_breaker_category = None

if len(sys.argv) < 2:
    print('Usage: inspect_import_rows.py <excel_path>')
    sys.exit(1)

path = sys.argv[1]

if pd is None:
    print('pandas missing')
    sys.exit(1)

try:
    df = pd.read_excel(path, sheet_name='Elements')
except Exception:
    df = pd.read_excel(path, sheet_name=None)
    # pick first sheet
    if isinstance(df, dict):
        # pick sheet with many rows
        chosen = list(df.keys())[0]
        df = df[chosen]

# map columns
try:
    df = _map_columns(df)
except Exception:
    pass

print('Columns:', list(df.columns))

for idx, row in df.head(40).iterrows():
    rownum = idx + 3
    model_name = row.get('Model Name', '') if pd.notna(row.get('Model Name', '')) else ''
    breaker_type = row.get('Τύπος Διακόπτη', '') if pd.notna(row.get('Τύπος Διακόπτη', '')) else ''
    # try fallback english header
    if not breaker_type and 'Breaker Type' in row.index:
        breaker_type = row.get('Breaker Type', '') if pd.notna(row.get('Breaker Type', '')) else ''
    norm = None
    if validate_breaker_category and breaker_type:
        try:
            res = validate_breaker_category(str(breaker_type))
            norm = res[0] if res and res[0] else None
        except Exception:
            norm = None
    print(f'row {rownum}: model_name={model_name!r}, breaker_type={breaker_type!r}, normalized={norm!r}')

print('Done')
