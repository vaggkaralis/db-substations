import json
import sqlite3
import tempfile

from DBrun import apply_change_log_to_db


def make_temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os_path = path
    conn = sqlite3.connect(os_path)
    cur = conn.cursor()
    # minimal tables used by importer
    cur.execute("""
    CREATE TABLE IF NOT EXISTS maintenance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS maintenance_elements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        maintenance_id INTEGER,
        element_id TEXT,
        element_comments TEXT
    )
    """)
    conn.commit()
    return conn, os_path


def test_apply_change_log_inserts_with_unknown_fields(tmp_path):
    conn, db_path = make_temp_db()
    try:
        # create a change-log JSONL where payload has extra unknown keys
        changelog = tmp_path / "cl.jsonl"
        entry = {
            "operation": "insert",
            "table": "maintenance",
            "data": {"title": "M1", "unknown": "x"},
        }
        changelog.write_text(json.dumps(entry) + "\n")

        apply_change_log_to_db(conn, str(changelog))

        cur = conn.cursor()
        cur.execute("SELECT id, title FROM maintenance WHERE title = ?", ("M1",))
        row = cur.fetchone()
        assert row is not None
        assert row[1] == "M1"
    finally:
        conn.close()


def test_maintenance_with_elements_creates_links(tmp_path):
    conn, db_path = make_temp_db()
    try:
        changelog = tmp_path / "cl2.jsonl"
        entry = {
            "operation": "insert",
            "table": "maintenance",
            "data": {
                "title": "M2",
                "elements": [{"id": "e1"}, {"id": "e2"}],
            },
        }
        changelog.write_text(json.dumps(entry) + "\n")

        apply_change_log_to_db(conn, str(changelog))

        cur = conn.cursor()
        # maintenance_id is the autoincrement id; find maintenance row
        cur.execute("SELECT id FROM maintenance WHERE title = ?", ("M2",))
        mrow = cur.fetchone()
        assert mrow is not None
        mid = mrow[0]
        cur.execute(
            "SELECT COUNT(*) FROM maintenance_elements WHERE maintenance_id = ?", (mid,)
        )
        cnt = cur.fetchone()[0]
        assert cnt == 2
    finally:
        conn.close()
