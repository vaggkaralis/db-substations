import json
import sqlite3

from DBrun import apply_change_log_to_db


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
    changelog.write_text("".join(json.dumps(l) + "\n" for l in lines), encoding="utf-8")

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
        "CREATE TABLE maintenance_elements (id INTEGER PRIMARY KEY, maintenance_id INTEGER, element_id INTEGER, element_comments TEXT)"
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
