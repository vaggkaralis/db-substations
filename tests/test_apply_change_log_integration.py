import json
import sqlite3

from DBrun import apply_change_log_to_db


def test_apply_change_log_maintenance_inserts(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    # Minimal schema
    cur.executescript("""
        CREATE TABLE elements (id INTEGER PRIMARY KEY, substation_id INTEGER, name TEXT, maintenance_date TEXT);
        CREATE TABLE maintenance (id INTEGER PRIMARY KEY, substation_id INTEGER, date_time TEXT, overall_comments TEXT, maintenance_type TEXT, user_name TEXT);
        CREATE TABLE maintenance_elements (maintenance_id INTEGER, element_id INTEGER, element_comments TEXT);
        CREATE TABLE substations (id INTEGER PRIMARY KEY, name TEXT, location TEXT, adoption_date TEXT);
        """)
    conn.commit()

    # Prepare change-log JSONL
    log_path = tmp_path / "change_log.jsonl"
    entries = []
    # Insert an element with id=1
    entries.append(
        {"operation": "insert", "table": "elements", "data": {"id": 1, "name": "E1"}}
    )
    # Insert a maintenance that references element id 1
    entries.append(
        {
            "operation": "insert",
            "table": "maintenance",
            "data": {
                "substation_id": 1,
                "date_time": "2020-01-01",
                "overall_comments": "ok",
                "elements": [{"element_id": 1, "element_comments": "checked"}],
            },
        }
    )

    with open(log_path, "w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")

    # Apply
    apply_change_log_to_db(conn, str(log_path))

    # Assertions
    r = cur.execute(
        "SELECT id, name, maintenance_date FROM elements WHERE id=1"
    ).fetchone()
    assert r is not None and r[0] == 1

    m = cur.execute(
        "SELECT id, overall_comments, date_time FROM maintenance"
    ).fetchone()
    assert m is not None and m[1] == "ok"

    me = cur.execute(
        "SELECT maintenance_id, element_id, element_comments FROM maintenance_elements"
    ).fetchone()
    assert me is not None and me[1] == 1 and me[2] == "checked"

    conn.close()
