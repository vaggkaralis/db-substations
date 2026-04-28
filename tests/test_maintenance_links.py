import sqlite3

import DBrun


def _build_test_app(conn):
    app = object.__new__(DBrun.SubstationApp)
    app.conn = conn
    app._refresh_maintenance_dates_for_scope = lambda *args, **kwargs: None
    app._append_change_log = lambda *args, **kwargs: None
    app._build_maintenance_change_log_elements = lambda maintenance_id: [
        {"element_id": row[0]}
        for row in conn.execute(
            "SELECT element_id FROM maintenance_elements WHERE maintenance_id = ? ORDER BY element_id",
            (maintenance_id,),
        ).fetchall()
    ]
    return app


def _create_link_schema(conn):
    conn.executescript(
        """
        CREATE TABLE maintenance (
            id INTEGER PRIMARY KEY,
            substation_id INTEGER
        );
        CREATE TABLE maintenance_elements (
            id INTEGER PRIMARY KEY,
            maintenance_id INTEGER,
            element_id INTEGER
        );
        """
    )


def test_sync_element_maintenance_links_blocks_last_link_removal():
    conn = sqlite3.connect(":memory:")
    _create_link_schema(conn)
    conn.execute("INSERT INTO maintenance (id, substation_id) VALUES (10, 1)")
    conn.execute(
        "INSERT INTO maintenance_elements (maintenance_id, element_id) VALUES (10, 1305)"
    )
    conn.commit()

    app = _build_test_app(conn)

    result = app._sync_element_maintenance_links(
        substation_id=1,
        element_id=1305,
        selected_maintenance_ids=set(),
    )

    remaining = conn.execute(
        "SELECT COUNT(*) FROM maintenance_elements WHERE maintenance_id = 10 AND element_id = 1305"
    ).fetchone()[0]

    assert result == {"added": 0, "removed": 0, "blocked": [10]}
    assert remaining == 1


def test_sync_element_maintenance_links_removes_link_when_maintenance_has_others():
    conn = sqlite3.connect(":memory:")
    _create_link_schema(conn)
    conn.execute("INSERT INTO maintenance (id, substation_id) VALUES (10, 1)")
    conn.executemany(
        "INSERT INTO maintenance_elements (maintenance_id, element_id) VALUES (10, ?)",
        [(1305,), (1401,)],
    )
    conn.commit()

    app = _build_test_app(conn)

    result = app._sync_element_maintenance_links(
        substation_id=1,
        element_id=1305,
        selected_maintenance_ids=set(),
    )

    remaining_for_removed = conn.execute(
        "SELECT COUNT(*) FROM maintenance_elements WHERE maintenance_id = 10 AND element_id = 1305"
    ).fetchone()[0]
    remaining_for_other = conn.execute(
        "SELECT COUNT(*) FROM maintenance_elements WHERE maintenance_id = 10 AND element_id = 1401"
    ).fetchone()[0]

    assert result == {"added": 0, "removed": 1, "blocked": []}
    assert remaining_for_removed == 0
    assert remaining_for_other == 1
