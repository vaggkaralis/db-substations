import os
import shutil
import sqlite3
import sys

# ensure project root on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from importers import import_elements_from_excel

DB_SRC = os.path.join(os.path.dirname(__file__), '..', 'substations.db')
DB_COPY = os.path.join(os.path.dirname(__file__), '..', 'substations_import_test.db')
EXCEL = os.path.join(os.path.dirname(__file__), '..', 'db2import_test.xlsx')

import argparse
parser = argparse.ArgumentParser()
parser.add_argument('excel', nargs='?', help='Path to excel file to import')
parser.add_argument('--clean', action='store_true', help='Create a clean DB with schema and import into it')
args = parser.parse_args()
if args.excel:
    EXCEL = args.excel
USE_CLEAN = args.clean

if __name__ == '__main__':
    if not os.path.exists(DB_SRC):
        print('Source DB not found:', DB_SRC)
        sys.exit(2)
    if not os.path.exists(EXCEL):
        print('Excel file not found:', EXCEL)
        sys.exit(2)

    # prepare test DB (copy existing or create clean)
    DB_CLEAN = os.path.join(os.path.dirname(__file__), '..', 'substations_import_test_clean.db')
    if USE_CLEAN:
        if os.path.exists(DB_CLEAN):
            os.remove(DB_CLEAN)
        conn = sqlite3.connect(DB_CLEAN)
        cur = conn.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS substations (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, location TEXT, adoption_date TEXT, is_thessaloniki INTEGER DEFAULT 0)')
        cur.execute('CREATE TABLE IF NOT EXISTS element_models (id INTEGER PRIMARY KEY AUTOINCREMENT, element_category TEXT, model_name TEXT, manufacturer TEXT, maintenance_cycle INTEGER, installation_space TEXT, breaker_category TEXT)')
        cur.execute('CREATE TABLE IF NOT EXISTS elements (id INTEGER PRIMARY KEY AUTOINCREMENT, substation_id INTEGER, element_type TEXT, name TEXT, serial_number TEXT, maintenance_date TEXT, voltage_level TEXT, power_mva TEXT, manufacturer TEXT, manufacture_year TEXT, gate TEXT, is_main_switch INTEGER, breaker_category TEXT, maintenance_cycle INTEGER, element_model_id INTEGER, operating_status TEXT)')
        conn.commit()
        print('Created clean test DB:', DB_CLEAN)
    else:
        if os.path.exists(DB_COPY):
            os.remove(DB_COPY)
        shutil.copy(DB_SRC, DB_COPY)
        print('Created test DB:', DB_COPY)
        conn = sqlite3.connect(DB_COPY)
    cursor = conn.cursor()

    # snapshot existing models
    cursor.execute('SELECT id FROM element_models')
    before_ids = {row[0] for row in cursor.fetchall()}
    print('Existing element_models before import:', len(before_ids))

    # run import
    success_msgs = []
    error_msgs = []

    def on_success(msg):
        success_msgs.append(msg)
        print('IMPORT SUCCESS:', msg)

    def on_error(msg):
        error_msgs.append(msg)
        print('IMPORT ERROR:', msg)

    # First import substations into clean DB (so elements can reference them)
    try:
        from importers import import_substations_from_excel
        import_substations_from_excel(conn, EXCEL, on_success, on_error)
    except Exception:
        pass

    # Import elements (no on_duplicate handler -> default skip)
    import_elements_from_excel(conn, EXCEL, on_success, on_error, None)

    # snapshot after
    cursor.execute('SELECT id, model_name, element_category, breaker_category FROM element_models')
    rows = cursor.fetchall()
    total_models = len(rows)
    null_breaker = [r for r in rows if r[3] is None or (isinstance(r[3], str) and r[3].strip()=='')]
    print('\nTotal element_models after import:', total_models)
    print('element_models with NULL/empty breaker_category:', len(null_breaker))

    # new models created by import
    cursor.execute('SELECT id, model_name, element_category, breaker_category FROM element_models')
    new_models = [r for r in cursor.fetchall() if r[0] not in before_ids]
    print('New models created by import:', len(new_models))
    for r in new_models[:50]:
        print('NEW MODEL:', r)

    # group counts by breaker_category
    cursor.execute("SELECT COALESCE(breaker_category,'(NULL)') as cat, COUNT(*) as cnt FROM element_models GROUP BY cat ORDER BY cnt DESC")
    for cat, cnt in cursor.fetchall():
        print('MODEL BREAKER CATEGORY:', cat, cnt)

    # elements with missing breaker_category for breaker types
    cursor.execute("SELECT COUNT(*) FROM elements WHERE (element_type LIKE '%Διακόπτης%' OR element_type LIKE '%Breaker%') AND (breaker_category IS NULL OR TRIM(breaker_category)='')")
    cnt_missing_elem = cursor.fetchone()[0]
    print('\nElements (breakers) with missing breaker_category:', cnt_missing_elem)

    # distinct element breaker categories
    cursor.execute("SELECT COALESCE(breaker_category,'(NULL)') as cat, COUNT(*) as cnt FROM elements GROUP BY cat ORDER BY cnt DESC")
    for cat, cnt in cursor.fetchall():
        print('ELEMENT BREAKER CATEGORY:', cat, cnt)

    conn.commit()
    conn.close()
    print('\nDone')
