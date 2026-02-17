import os
import shutil
import sqlite3
import sys

# ensure project root is importable when running from tools/
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if proj_root not in sys.path:
    sys.path.insert(0, proj_root)

from DBrun import SubstationApp

TEST_DB = os.path.join(os.path.dirname(__file__), '..', 'substations_dbrun_precheck_test.db')

# Accept path as arg or default to known test file
excel_path = None
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
base_db = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'substations.db'))
if os.path.exists(base_db):
    shutil.copy(base_db, TEST_DB)
else:
    open(TEST_DB, 'a').close()

print('Using DB:', TEST_DB)
print('Using Excel:', excel_path)

# Instantiate app and attach test DB connection
app = SubstationApp()
# Close any default connection and replace
try:
    if getattr(app, 'conn', None):
        try:
            app.conn.close()
        except Exception:
            pass
except Exception:
    pass

app.conn = sqlite3.connect(TEST_DB)

# Monkeypatch the model-check popup to auto-apply changes (update_conflicts=True)
# Provide a dummy prompt object with dismiss()
class _DummyPopup:
    def dismiss(self):
        return None


def _auto_apply(fp, new_models, conflicting_models):
    try:
        app._apply_models_and_continue(fp, new_models, conflicting_models, True, _DummyPopup())
    except Exception as e:
        print('Error applying models:', e)

# Replace the method
app._show_model_check_popup = _auto_apply

# Run the duplicate & model check (this will auto-apply models)
app._check_duplicates_and_import(excel_path)

# Report element_models stats
cur = app.conn.cursor()
try:
    cur.execute('SELECT COUNT(*), SUM(CASE WHEN breaker_category IS NULL OR TRIM(breaker_category) = "" THEN 1 ELSE 0 END) FROM element_models')
    row = cur.fetchone()
    print('\nElement models: total=%s null_or_empty=%s' % (row[0], row[1]))
except Exception as e:
    print('\nCould not query element_models:', e)

app.conn.close()
print('\nDone')
