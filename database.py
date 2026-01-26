import sqlite3


def init_db(db_path: str = 'substations.db') -> sqlite3.Connection:
    """Initialize SQLite connection, ensure tables exist, and apply lightweight migrations."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        'CREATE TABLE IF NOT EXISTS substations (id INTEGER PRIMARY KEY, name TEXT, location TEXT, adoption_date TEXT)'
    )
    cursor.execute(
        'CREATE TABLE IF NOT EXISTS elements (id INTEGER PRIMARY KEY, substation_id INTEGER, element_type TEXT, name TEXT, serial_number TEXT, maintenance_date TEXT, voltage_level TEXT, manufacturer TEXT, type TEXT, FOREIGN KEY(substation_id) REFERENCES substations(id))'
    )

    cursor.execute('PRAGMA table_info(substations)')
    sub_columns = [column[1] for column in cursor.fetchall()]
    if 'location' not in sub_columns:
        try:
            cursor.execute('ALTER TABLE substations ADD COLUMN location TEXT DEFAULT ""')
        except Exception:
            pass
    if 'adoption_date' not in sub_columns:
        try:
            cursor.execute('ALTER TABLE substations ADD COLUMN adoption_date TEXT DEFAULT ""')
        except Exception:
            pass

    cursor.execute('PRAGMA table_info(elements)')
    elem_columns = [column[1] for column in cursor.fetchall()]
    if elem_columns and 'serial_number' not in elem_columns:
        try:
            cursor.execute('ALTER TABLE elements ADD COLUMN serial_number TEXT DEFAULT ""')
        except Exception:
            pass
    if elem_columns and 'maintenance_date' not in elem_columns:
        try:
            cursor.execute('ALTER TABLE elements ADD COLUMN maintenance_date TEXT DEFAULT ""')
        except Exception:
            pass
    if elem_columns and 'voltage_level' not in elem_columns:
        try:
            cursor.execute('ALTER TABLE elements ADD COLUMN voltage_level TEXT DEFAULT ""')
        except Exception:
            pass
    if elem_columns and 'manufacturer' not in elem_columns:
        try:
            cursor.execute('ALTER TABLE elements ADD COLUMN manufacturer TEXT DEFAULT ""')
        except Exception:
            pass
    if elem_columns and 'type' not in elem_columns:
        try:
            cursor.execute('ALTER TABLE elements ADD COLUMN type TEXT DEFAULT ""')
        except Exception:
            pass

    conn.commit()
    return conn
