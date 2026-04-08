#!/usr/bin/env python3
import os
import shutil
import sqlite3
import datetime
import sys

# Import DB path from settings if available
try:
    import settings

    DB_PATH = settings.DB_PATH
except Exception:
    DB_PATH = os.path.join(os.getcwd(), "substations.db")

if not os.path.exists(DB_PATH):
    print("ERROR: DB not found at", DB_PATH)
    sys.exit(2)

# create timestamped backup
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup_path = DB_PATH.replace(".db", f"_before_normalize_{ts}.db")
shutil.copy2(DB_PATH, backup_path)
print("Backup created:", backup_path)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Run normalization: convert any maintenance_date with time component to date-only
# Also convert empty-string maintenance_date to NULL
try:
    conn.execute("BEGIN")

    # Convert empty strings to NULL
    cur.execute(
        "UPDATE elements SET maintenance_date = NULL WHERE trim(maintenance_date) = ''"
    )
    empty_converted = cur.rowcount

    # Convert values with time to date-only
    cur.execute(
        "UPDATE elements SET maintenance_date = date(maintenance_date) WHERE maintenance_date IS NOT NULL AND maintenance_date != date(maintenance_date)"
    )
    time_converted = cur.rowcount

    # Create triggers to enforce date-only on future INSERT/UPDATE
    cur.executescript(r"""
    CREATE TABLE IF NOT EXISTS _trigger_marker_normalize_maintenance_date(marked INTEGER);

    CREATE TRIGGER IF NOT EXISTS normalize_maintenance_date_after_insert
    AFTER INSERT ON elements
    BEGIN
      UPDATE elements SET maintenance_date = NULL WHERE rowid = NEW.rowid AND (NEW.maintenance_date IS NULL OR trim(NEW.maintenance_date) = '');
      UPDATE elements SET maintenance_date = date(NEW.maintenance_date) WHERE rowid = NEW.rowid AND NEW.maintenance_date IS NOT NULL AND trim(NEW.maintenance_date) != '' AND NEW.maintenance_date <> date(NEW.maintenance_date);
    END;

    CREATE TRIGGER IF NOT EXISTS normalize_maintenance_date_after_update
    AFTER UPDATE ON elements
    BEGIN
      UPDATE elements SET maintenance_date = NULL WHERE rowid = NEW.rowid AND (NEW.maintenance_date IS NULL OR trim(NEW.maintenance_date) = '');
      UPDATE elements SET maintenance_date = date(NEW.maintenance_date) WHERE rowid = NEW.rowid AND NEW.maintenance_date IS NOT NULL AND trim(NEW.maintenance_date) != '' AND NEW.maintenance_date <> date(NEW.maintenance_date);
    END;
    """)

    conn.commit()
except Exception as e:
    conn.rollback()
    print("ERROR during DB operations:", e)
    sys.exit(3)

# Verification: count rows that still contain time component (space or colon)
cur = conn.cursor()
cur.execute(
    "SELECT COUNT(*) FROM elements WHERE maintenance_date LIKE '% %' OR maintenance_date LIKE '%:%'"
)
remaining_with_time = cur.fetchone()[0]

cur.execute(
    "SELECT COUNT(*) FROM elements WHERE maintenance_date IS NOT NULL AND trim(maintenance_date) != ''"
)
total_nonnull = cur.fetchone()[0]

print(f"Empty-string -> NULL conversions: {empty_converted}")
print(f"Time-containing maintenance_date -> date-only conversions: {time_converted}")
print(f"Remaining rows with time-like content: {remaining_with_time}")
print(f"Total elements with maintenance_date set (non-null): {total_nonnull}")
print("Done.")
conn.close()
