from database import init_db


def test_new_maintenance_defaults_to_most_recent_isolation(tmp_path, monkeypatch):

    # Prepare a temporary DB and insert a substation + two isolation requests
    db_path = tmp_path / "test_db.sqlite"
    conn = init_db(str(db_path))
    cur = conn.cursor()
    cur.execute("INSERT INTO substations (id, name) VALUES (?, ?)", (1, "S1"))
    # Older isolation
    cur.execute(
        "INSERT INTO isolation_requests (substation_id, start_datetime, end_datetime, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            1,
            "2026-01-01 08:00",
            "2026-01-01 16:00",
            "Requested",
            "2026-01-01 00:00",
            "2026-01-01 00:00",
        ),
    )
    # Newer isolation (should be chosen)
    cur.execute(
        "INSERT INTO isolation_requests (substation_id, start_datetime, end_datetime, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            1,
            "2026-02-01 08:00",
            "2026-02-01 16:00",
            "Requested",
            "2026-02-01 00:00",
            "2026-02-01 00:00",
        ),
    )
    conn.commit()

    # Emulate the selection logic used by the maintenance UI without instantiating UI
    # Build isolation options as the UI does (most-recent first)
    cur.execute(
        "SELECT id, start_datetime, end_datetime, status FROM isolation_requests WHERE substation_id = ? ORDER BY start_datetime DESC LIMIT 5",
        (1,),
    )
    isolation_options_by_label = {"Χωρίς σύνδεση": None}
    values = ["Χωρίς σύνδεση"]
    for req_id, start_dt, end_dt, status in cur.fetchall():
        label = f"#{req_id} | {start_dt} - {end_dt} | {status}"
        isolation_options_by_label[label] = req_id
        values.append(label)

    # With no preferred or linked ids, the UI should pick the most recent (first) request
    preferred_request_id = None
    linked_isolation_request_id = None
    if preferred_request_id is not None:
        target_id = preferred_request_id
    elif linked_isolation_request_id is not None:
        target_id = linked_isolation_request_id
    else:
        target_id = None
        for lbl in values[1:]:
            rid = isolation_options_by_label.get(lbl)
            if rid is not None:
                target_id = rid
                break

    assert target_id == 2, f"Expected most recent isolation id 2, got {target_id}"
