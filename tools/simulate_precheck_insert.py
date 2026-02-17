import os
import shutil
import sqlite3
import sys
import pandas as pd

# ensure project root is importable
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)

from import_validator import validate_breaker_category

TEST_DB = os.path.join(os.path.dirname(__file__), '..', 'substations_precheck_sim_test.db')

# Accept path as arg or default to known test file
if len(sys.argv) > 1:
    excel_path = sys.argv[1]
else:
    excel_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'db2import_test.xlsx'))

# Prepare test DB
base_db = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'substations.db'))
if os.path.exists(TEST_DB):
    try:
        os.remove(TEST_DB)
    except Exception:
        pass

if os.path.exists(base_db):
    shutil.copy(base_db, TEST_DB)

# Ensure DB schema exists by initializing via init_db
try:
    from database import init_db
    conn = init_db(TEST_DB)
except Exception:
    conn = sqlite3.connect(TEST_DB)
cur = conn.cursor()

print('Using DB:', TEST_DB)
print('Using Excel:', excel_path)

# Read Elements sheet
try:
    df = pd.read_excel(excel_path, sheet_name='Elements')
except Exception as e:
    print('Could not read Excel Elements sheet:', e)
    sys.exit(1)

# Build models_to_check
models_to_check = {}
for _, row in df.iterrows():
    element_type = str(row.get('Element Type', '')).strip() if pd.notna(row.get('Element Type', '')) else ''
    model_name = str(row.get('Model Name', '')).strip() if pd.notna(row.get('Model Name', '')) else ''
    model_manufacturer = str(row.get('Model Manufacturer', '')).strip() if pd.notna(row.get('Model Manufacturer', '')) else ''
    model_cycle = int(row.get('Model Maintenance Cycle', 0)) if pd.notna(row.get('Model Maintenance Cycle', '')) and str(row.get('Model Maintenance Cycle', '')).strip() != '' else 0
    model_space = str(row.get('Model Installation Space', '')).strip() if pd.notna(row.get('Model Installation Space', '')) else ''

    if not model_name:
        continue

    # Determine computed cycle using substation flag
    computed_cycle = None
    try:
        sub_name = str(row.get('Substation Name', '')).strip() if pd.notna(row.get('Substation Name', '')) else ''
        is_th = False
        if sub_name:
            cur.execute('SELECT is_thessaloniki FROM substations WHERE name=?', (sub_name,))
            r = cur.fetchone()
            is_th = bool(r[0]) if r and r[0] else False

        breaker_type = str(row.get('Τύπος Διακόπτη', '')).strip() if pd.notna(row.get('Τύπος Διακόπτη', '')) else ''
        et = str(element_type) if pd.notna(element_type) else ''
        if 'ΥΤ' in et or '150/20' in et or 'Transformer' in et:
            computed_cycle = 3 if is_th else 6
        elif 'ΜΤ' in et or '20/0.4' in et:
            bt = (breaker_type or '').strip().lower()
            if bt in ['πτωχού ελαίου', 'sf6', 'sf-6'] or 'sf6' in bt:
                computed_cycle = 1
            elif bt in ['κενού', 'ελαίου']:
                computed_cycle = 3
            else:
                computed_cycle = 3
        else:
            computed_cycle = 6
    except Exception:
        computed_cycle = None

    # Normalize breaker category
    breaker_type_raw = ''
    try:
        breaker_type_raw = str(row.get('Τύπος Διακόπτη', '')).strip() if pd.notna(row.get('Τύπος Διακόπτη', '')) else ''
    except Exception:
        breaker_type_raw = ''
    normalized_bc = None
    try:
        if breaker_type_raw:
            match = validate_breaker_category(breaker_type_raw)
            normalized_bc = match[0] if match and match[0] else None
    except Exception:
        normalized_bc = breaker_type_raw or None

    key = (element_type, model_name, model_manufacturer)
    if key not in models_to_check:
        models_to_check[key] = {
            'cycle': model_cycle,
            'space': model_space,
            'computed': computed_cycle,
            'breaker_category': normalized_bc,
        }

# Detect element_models columns
try:
    cur.execute("PRAGMA table_info(element_models)")
    em_cols = [r[1] for r in cur.fetchall()]
except Exception:
    em_cols = []

new_models = []
conflicting_models = []
for (elem_type, model_name, manufacturer), model_data in models_to_check.items():
    cur.execute('SELECT id, maintenance_cycle, installation_space, breaker_category FROM element_models WHERE element_category=? AND model_name=? AND manufacturer=?', (elem_type, model_name, manufacturer))
    existing = cur.fetchone()
    if existing:
        existing_id, existing_cycle, existing_space, existing_bc = existing
        # If cycle or space or breaker_category differs, mark as conflicting
        bc_diff = False
        try:
            # Normalize existing_bc for comparison
            existing_bc_norm = existing_bc if existing_bc is not None else None
            new_bc = model_data.get('breaker_category')
            if (existing_bc_norm or '') != (new_bc or ''):
                bc_diff = True
        except Exception:
            bc_diff = False

        if existing_cycle != model_data['cycle'] or (existing_space or '') != (model_data['space'] or '') or bc_diff:
            conflicting_models.append({
                'category': elem_type,
                'name': model_name,
                'manufacturer': manufacturer,
                'existing': {'cycle': existing_cycle, 'space': existing_space, 'breaker_category': existing_bc},
                'new': model_data,
            })
    else:
        new_models.append({'category': elem_type, 'name': model_name, 'manufacturer': manufacturer, 'data': model_data})

# Apply new models
for model in new_models:
    if 'breaker_category' in em_cols:
        try:
            cur.execute('INSERT INTO element_models (element_category, model_name, manufacturer, maintenance_cycle, installation_space, breaker_category) VALUES (?, ?, ?, ?, ?, ?)', (
                model['category'], model['name'], model['manufacturer'], model['data']['cycle'], model['data']['space'], model['data'].get('breaker_category') if model.get('data') else None
            ))
        except Exception as e:
            print('Insert error:', e)
    else:
        try:
            cur.execute('INSERT INTO element_models (element_category, model_name, manufacturer, maintenance_cycle, installation_space) VALUES (?, ?, ?, ?, ?)', (
                model['category'], model['name'], model['manufacturer'], model['data']['cycle'], model['data']['space']
            ))
        except Exception as e:
            print('Insert error:', e)

# Update conflicting models by overwriting with new values
for model in conflicting_models:
    if 'breaker_category' in em_cols:
        cur.execute('UPDATE element_models SET maintenance_cycle=?, installation_space=?, breaker_category=? WHERE element_category=? AND model_name=? AND manufacturer=?', (
            model['new']['cycle'], model['new']['space'], model['new'].get('breaker_category'), model['category'], model['name'], model['manufacturer']
        ))
    else:
        cur.execute('UPDATE element_models SET maintenance_cycle=?, installation_space=? WHERE element_category=? AND model_name=? AND manufacturer=?', (
            model['new']['cycle'], model['new']['space'], model['category'], model['name'], model['manufacturer']
        ))

conn.commit()

# Report stats
try:
    cur.execute('SELECT COUNT(*), SUM(CASE WHEN breaker_category IS NULL OR TRIM(breaker_category) = "" THEN 1 ELSE 0 END) FROM element_models')
    row = cur.fetchone()
    print('\nElement models: total=%s null_or_empty=%s' % (row[0], row[1]))
except Exception as e:
    print('\nCould not query element_models:', e)

conn.close()
print('\nDone')
