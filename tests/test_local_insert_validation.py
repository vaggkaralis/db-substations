import sqlite3

from android_app import SubstationAndroidApp


def test_local_insert_filters_extra_columns(tmp_path):
    db_path = tmp_path / "local.db"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("CREATE TABLE testtable (id INTEGER PRIMARY KEY, a INTEGER, b TEXT)")
    conn.commit()
    conn.close()

    app = SubstationAndroidApp()
    app.local_db_path = str(db_path)

    new_id = app._local_insert("testtable", {"a": 5, "b": "ok", "extra": 999})

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    row = cur.execute("SELECT id, a, b FROM testtable WHERE id=?", (new_id,)).fetchone()
    assert row is not None
    assert row[1] == 5 and row[2] == "ok"
    conn.close()
