from database import init_db
from maintenance_email_importer import resolve_linked_isolation_request_id


def test_new_maintenance_defaults_to_matching_date_isolation(tmp_path):
    db_path = tmp_path / "test_db.sqlite"
    conn = init_db(str(db_path))
    cur = conn.cursor()
    cur.execute("INSERT INTO substations (id, name) VALUES (?, ?)", (1, "S1"))
    cur.executemany(
        (
            "INSERT INTO isolation_requests "
            "(id, substation_id, start_datetime, end_datetime, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        ),
        [
            (
                1,
                1,
                "2026-01-01 08:00",
                "2026-01-01 16:00",
                "Requested",
                "2026-01-01 00:00",
                "2026-01-01 00:00",
            ),
            (
                2,
                1,
                "2026-02-01 08:00",
                "2026-02-01 16:00",
                "Requested",
                "2026-02-01 00:00",
                "2026-02-01 00:00",
            ),
            (
                3,
                1,
                "2026-04-27 09:00",
                "2026-04-27 14:00",
                "Accepted",
                "2026-04-26 00:00",
                "2026-04-26 00:00",
            ),
        ],
    )
    conn.commit()

    target_id = resolve_linked_isolation_request_id(
        conn,
        1,
        date_time_value="2026-04-27 11:27:30",
        auto_select_by_date=True,
    )

    assert target_id == 3


def test_editing_unlinked_maintenance_keeps_empty_isolation(tmp_path):
    db_path = tmp_path / "test_db.sqlite"
    conn = init_db(str(db_path))
    cur = conn.cursor()
    cur.execute("INSERT INTO substations (id, name) VALUES (?, ?)", (1, "S1"))
    cur.executemany(
        (
            "INSERT INTO isolation_requests "
            "(id, substation_id, start_datetime, end_datetime, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        ),
        [
            (
                1,
                1,
                "2026-01-01 08:00",
                "2026-01-01 16:00",
                "Requested",
                "2026-01-01 00:00",
                "2026-01-01 00:00",
            ),
            (
                2,
                1,
                "2026-04-27 09:00",
                "2026-04-27 14:00",
                "Accepted",
                "2026-04-26 00:00",
                "2026-04-26 00:00",
            ),
        ],
    )
    conn.commit()

    target_id = resolve_linked_isolation_request_id(
        conn,
        1,
        date_time_value="2026-04-27 11:27:30",
        linked_request_id=None,
        auto_select_by_date=False,
    )

    assert target_id is None
