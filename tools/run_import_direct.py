import os
import shutil
import sqlite3
import sys
# ensure project root is importable when running from tools/
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)
from importers import import_substations_from_excel, import_elements_from_excel

TEST_DB = os.path.join(os.path.dirname(__file__), '..', 'substations_import_direct_test.db')

excel_path = None

# Accept path as env var or default to known test file
import sys
if len(sys.argv) > 1:
    excel_path = sys.argv[1]
else:
    excel_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'db2import_test.xlsx'))

# Remove existing test DB
if os.path.exists(TEST_DB):
    try:
        os.remove(TEST_DB)
    except Exception:
        pass

# Create a fresh DB by copying template if exists, otherwise create empty file
# Try to copy existing substations.db as base if available
base_db = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'substations.db'))
if os.path.exists(base_db):
    shutil.copy(base_db, TEST_DB)
else:
    open(TEST_DB, 'a').close()

conn = sqlite3.connect(TEST_DB)

# Callbacks

def on_success(msg):
    print('[IMPORT-DIRECT-SUCCESS]', msg)


def on_error(msg):
    print('[IMPORT-DIRECT-ERROR]', msg)

print('Using DB:', TEST_DB)
print('Using Excel:', excel_path)

print('\n-- Importing Substations --')
import_substations_from_excel(conn, excel_path, on_success, on_error)

print('\n-- Importing Elements --')
import_elements_from_excel(conn, excel_path, on_success, on_error)

# Show count of element_models
cur = conn.cursor()
try:
    cur.execute('SELECT COUNT(*), SUM(CASE WHEN breaker_category IS NULL OR TRIM(breaker_category) = "" THEN 1 ELSE 0 END) FROM element_models')
    row = cur.fetchone()
    print('\nElement models: total=%s null_or_empty=%s' % (row[0], row[1]))
except Exception as e:
    print('\nCould not query element_models:', e)

conn.close()
print('\nDone')
