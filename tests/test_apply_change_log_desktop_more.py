import json
import sqlite3

from DBrun import apply_change_log_to_db
from DBrun import _refresh_stored_maintenance_dates


def test_ignores_unknown_columns(tmp_path):
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("CREATE TABLE foo (a TEXT, b TEXT)")
    conn.commit()

    changelog = tmp_path / "cl.jsonl"
    # include an unknown column 'c' which should be ignored
    obj = {
        "operation": "insert",
        "table": "foo",
        "data": {"a": "1", "b": "2", "c": "3"},
    }
    changelog.write_text(json.dumps(obj) + "\n", encoding="utf-8")

    apply_change_log_to_db(conn, str(changelog))

    cur.execute("SELECT a,b FROM foo")
    rows = cur.fetchall()
    assert rows == [("1", "2")]


def test_missing_table_line_is_ignored_and_others_apply(tmp_path):
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute("CREATE TABLE good (x TEXT)")
    conn.commit()

    changelog = tmp_path / "cl2.jsonl"
    # first line targets a non-existent table; second line is valid
    lines = [
        {"operation": "insert", "table": "nope", "data": {"z": "z"}},
        {"operation": "insert", "table": "good", "data": {"x": "y"}},
    ]
    changelog.write_text(
        "".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8"
    )

    # should not raise
    apply_change_log_to_db(conn, str(changelog))

    cur.execute("SELECT x FROM good")
    assert cur.fetchall() == [("y",)]


def test_maintenance_inserts_and_updates(tmp_path):
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    # minimal schema expected by apply_change_log_to_db
    cur.execute("CREATE TABLE elements (id INTEGER PRIMARY KEY, maintenance_date TEXT)")
    cur.execute("CREATE TABLE maintenance (id INTEGER PRIMARY KEY, date_time TEXT)")
    cur.execute(
        (
            "CREATE TABLE maintenance_elements ("
            "id INTEGER PRIMARY KEY, "
            "maintenance_id INTEGER, "
            "element_id INTEGER, "
            "element_comments TEXT)"
        )
    )
    conn.commit()

    # insert an element to reference
    cur.execute("INSERT INTO elements (maintenance_date) VALUES (?)", ("",))
    elem_id = cur.lastrowid
    conn.commit()

    changelog = tmp_path / "cl3.jsonl"
    maint = {
        "operation": "insert",
        "table": "maintenance",
        "data": {
            "date_time": "2026-02-08T10:00:00",
            "elements": [{"element_id": elem_id, "element_comments": "ok"}],
        },
    }
    changelog.write_text(json.dumps(maint) + "\n", encoding="utf-8")

    apply_change_log_to_db(conn, str(changelog))

    cur.execute("SELECT date_time FROM maintenance")
    rows = cur.fetchall()
    assert rows and rows[0][0] == "2026-02-08T10:00:00"

    cur.execute("SELECT element_id, element_comments FROM maintenance_elements")
    me = cur.fetchone()
    assert me == (elem_id, "ok")

    cur.execute("SELECT maintenance_date FROM elements WHERE id=?", (elem_id,))
    md = cur.fetchone()
    assert md and md[0] == "2026-02-08T10:00:00"


def test_motor_drive_inherits_transformer_maintenance_date_on_refresh():
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE elements (
            id INTEGER PRIMARY KEY,
            substation_id INTEGER,
            element_type TEXT,
            parent_element_id INTEGER,
            maintenance_date TEXT
        );
        CREATE TABLE maintenance (
            id INTEGER PRIMARY KEY,
            substation_id INTEGER,
            date_time TEXT
        );
        CREATE TABLE maintenance_elements (
            id INTEGER PRIMARY KEY,
            maintenance_id INTEGER,
            element_id INTEGER,
            element_comments TEXT
        );
        CREATE TABLE substations (
            id INTEGER PRIMARY KEY,
            last_maintenance TEXT
        );
        """
    )

    cur.execute(
        "INSERT INTO substations (id, last_maintenance) VALUES (?, ?)", (1, None)
    )
    cur.execute(
        "INSERT INTO elements (id, substation_id, element_type, parent_element_id, maintenance_date) VALUES (?, ?, ?, ?, ?)",
        (1, 1, "Transformer 150/20KV", None, None),
    )
    cur.execute(
        "INSERT INTO elements (id, substation_id, element_type, parent_element_id, maintenance_date) VALUES (?, ?, ?, ?, ?)",
        (2, 1, "Motor Drive", 1, "2001-01-01"),
    )
    cur.execute(
        "INSERT INTO maintenance (id, substation_id, date_time) VALUES (?, ?, ?)",
        (10, 1, "2026-09-13"),
    )
    cur.execute(
        "INSERT INTO maintenance_elements (maintenance_id, element_id, element_comments) VALUES (?, ?, ?)",
        (10, 1, "ok"),
    )

    _refresh_stored_maintenance_dates(cur, element_ids=[1, 2], substation_ids=[1])
    conn.commit()

    transformer_date = cur.execute(
        "SELECT maintenance_date FROM elements WHERE id=1"
    ).fetchone()[0]
    motor_drive_date = cur.execute(
        "SELECT maintenance_date FROM elements WHERE id=2"
    ).fetchone()[0]

    assert transformer_date == "2026-09-13"
    assert motor_drive_date == "2026-09-13"


def test_motor_drive_inherits_parent_date_retrospectively_when_stale():
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE elements (
            id INTEGER PRIMARY KEY,
            substation_id INTEGER,
            element_type TEXT,
            parent_element_id INTEGER,
            maintenance_date TEXT
        );
        CREATE TABLE maintenance (
            id INTEGER PRIMARY KEY,
            substation_id INTEGER,
            date_time TEXT
        );
        CREATE TABLE maintenance_elements (
            id INTEGER PRIMARY KEY,
            maintenance_id INTEGER,
            element_id INTEGER,
            element_comments TEXT
        );
        CREATE TABLE substations (
            id INTEGER PRIMARY KEY,
            last_maintenance TEXT
        );
        """
    )

    cur.execute(
        "INSERT INTO substations (id, last_maintenance) VALUES (?, ?)", (1, None)
    )
    cur.execute(
        "INSERT INTO elements (id, substation_id, element_type, parent_element_id, maintenance_date) VALUES (?, ?, ?, ?, ?)",
        (101, 1, "Transformer 150/20KV", None, None),
    )
    cur.execute(
        "INSERT INTO elements (id, substation_id, element_type, parent_element_id, maintenance_date) VALUES (?, ?, ?, ?, ?)",
        (102, 1, "Motor Drive", 101, "1999-12-31"),
    )
    cur.execute(
        "INSERT INTO maintenance (id, substation_id, date_time) VALUES (?, ?, ?)",
        (201, 1, "2025-05-10"),
    )
    cur.execute(
        "INSERT INTO maintenance_elements (maintenance_id, element_id, element_comments) VALUES (?, ?, ?)",
        (201, 101, "transformer"),
    )

    _refresh_stored_maintenance_dates(cur, element_ids=[101, 102], substation_ids=[1])
    conn.commit()

    md_date = cur.execute(
        "SELECT maintenance_date FROM elements WHERE id=102"
    ).fetchone()[0]
    assert md_date == "2025-05-10"
