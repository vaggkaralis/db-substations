import sqlite3

from substation_conflicts import (
    detect_substation_conflicts,
    set_substation_conflict_exception,
)


def _create_schema(conn):
    conn.executescript(
        """
        CREATE TABLE elements (
            id INTEGER PRIMARY KEY,
            substation_id INTEGER,
            parent_element_id INTEGER,
            element_type TEXT,
            name TEXT,
            serial_number TEXT,
            gate TEXT,
            hemizygos TEXT,
            is_main_switch INTEGER,
            operating_status TEXT
        );
        CREATE TABLE substations (
            id INTEGER PRIMARY KEY,
            name TEXT
        );
        CREATE TABLE maintenance (
            id INTEGER PRIMARY KEY,
            substation_id INTEGER,
            name TEXT,
            date_time TEXT
        );
        CREATE TABLE maintenance_elements (
            maintenance_id INTEGER,
            element_id INTEGER
        );
        """
    )


def test_detect_duplicate_name_serial_and_missing_gate():
    conn = sqlite3.connect(":memory:")
    _create_schema(conn)
    conn.execute("INSERT INTO substations VALUES (1, 'Υποσταθμός 1')")
    conn.executemany(
        "INSERT INTO elements "
        "(id,substation_id,element_type,name,serial_number,gate,hemizygos,is_main_switch) "
        "VALUES (?,1,?,?,?,?,?,?)",
        [
            (1, "Διακόπτης ΥΤ", "HV A", "SN-1", "ΠΥΛΗ 1", "Ημιζυγός 1", 1),
            (2, "Μετασχηματιστής 150/20KV", "HV A", "SN-1", "", "Ημιζυγός 1", 0),
            (3, "Διακόπτης ΜΤ", "MV A", "SN-3", "ΠΥΛΗ 1", "", 0),
        ],
    )
    conn.commit()

    issues = detect_substation_conflicts(conn, 1)
    types = {issue["type"] for issue in issues}

    assert "duplicate_name" in types
    assert "duplicate_serial" in types
    assert "missing_gate" in types
    assert "missing_hemizygos" in types


def test_detect_gate_transformer_hv_and_main_mv_counts():
    conn = sqlite3.connect(":memory:")
    _create_schema(conn)
    conn.execute("INSERT INTO substations VALUES (1, 'Υποσταθμός 1')")
    conn.executemany(
        "INSERT INTO elements "
        "(id,substation_id,element_type,name,serial_number,gate,hemizygos,is_main_switch) "
        "VALUES (?,1,?,?,?,?,?,?)",
        [
            (1, "Μετασχηματιστής 150/20KV", "T1", "S1", "ΠΥΛΗ 1", "Ημιζυγός 1", 0),
            (2, "Μετασχηματιστής 150/20KV", "T2", "S2", "ΠΥΛΗ 1", "Ημιζυγός 1", 0),
            (3, "Διακόπτης ΜΤ", "MV1", "S3", "ΠΥΛΗ 1", "Ημιζυγός 1", 1),
            (4, "Διακόπτης ΜΤ", "MV2", "S4", "ΠΥΛΗ 1", "Ημιζυγός 1", 1),
        ],
    )
    conn.commit()

    issues = detect_substation_conflicts(conn, 1)
    types = {issue["type"] for issue in issues}

    assert "gate_transformer_count" in types
    assert "gate_hv_breaker_count" in types
    assert "gate_main_mv_breaker_per_hemizygos" in types


def test_interconnection_gate_does_not_require_transformer_or_hv():
    conn = sqlite3.connect(":memory:")
    _create_schema(conn)
    conn.execute("INSERT INTO substations VALUES (1, 'Υποσταθμός 1')")
    conn.executemany(
        "INSERT INTO elements "
        "(id,substation_id,element_type,name,serial_number,gate,hemizygos,is_main_switch) "
        "VALUES (?,1,?,?,?,?,?,?)",
        [
            (1, "Διακόπτης ΜΤ", "MV1", "S1", "ΠΥΛΗ 1-2", "Ημιζυγός 1", 2),
            (2, "Διακόπτης ΜΤ", "MV2", "S2", "ΠΥΛΗ 1-2", "Ημιζυγός 2", 2),
        ],
    )
    conn.commit()

    issues = detect_substation_conflicts(conn, 1)
    types = {issue["type"] for issue in issues}

    assert "gate_transformer_count" not in types
    assert "gate_hv_breaker_count" not in types


def test_gate_transformer_and_hv_counts_ignore_inactive_elements():
    conn = sqlite3.connect(":memory:")
    _create_schema(conn)
    conn.execute("INSERT INTO substations VALUES (1, 'Υποσταθμός 1')")
    conn.executemany(
        "INSERT INTO elements "
        "(id,substation_id,element_type,name,serial_number,gate,hemizygos,is_main_switch,operating_status) "
        "VALUES (?,1,?,?,?,?,?,?,?)",
        [
            (1, "Μετασχηματιστής 150/20KV", "T1", "S1", "ΠΥΛΗ 1", "", 0, "Ενεργή"),
            (2, "Μετασχηματιστής 150/20KV", "T2", "S2", "ΠΥΛΗ 1", "", 0, "Ανενεργή"),
            (3, "Διακόπτης ΥΤ", "HV1", "S3", "ΠΥΛΗ 1", "", 1, "Ενεργή"),
            (4, "Διακόπτης ΥΤ", "HV2", "S4", "ΠΥΛΗ 1", "", 1, "Ανενεργή"),
            (5, "Διακόπτης ΜΤ", "MV1", "S5", "ΠΥΛΗ 1", "Ημιζυγός 1", 1, "Ενεργή"),
        ],
    )
    conn.commit()

    issues = detect_substation_conflicts(conn, 1)
    types = {issue["type"] for issue in issues}

    assert "gate_transformer_count" not in types
    assert "gate_hv_breaker_count" not in types


def test_detect_cross_substation_maintenance_links():
    conn = sqlite3.connect(":memory:")
    _create_schema(conn)
    conn.execute("INSERT INTO substations VALUES (1, 'Α')")
    conn.execute("INSERT INTO substations VALUES (2, 'Β')")
    conn.execute(
        "INSERT INTO elements "
        "(id,substation_id,element_type,name,serial_number,gate,hemizygos,is_main_switch) "
        "VALUES (10,2,'Μετασχηματιστής 150/20KV','X','S10','ΠΥΛΗ 1','',0)"
    )
    conn.execute(
        "INSERT INTO maintenance (id,substation_id,name,date_time) "
        "VALUES (20,1,'Συντήρηση','2026-01-01')"
    )
    conn.execute(
        "INSERT INTO maintenance_elements (maintenance_id,element_id) VALUES (20,10)"
    )
    conn.commit()

    issues = detect_substation_conflicts(conn, 1)
    assert any(issue["type"] == "cross_substation_maintenance" for issue in issues)


def test_conflict_exception_suppresses_issue():
    conn = sqlite3.connect(":memory:")
    _create_schema(conn)
    conn.execute("INSERT INTO substations VALUES (1, 'Α')")
    conn.execute(
        "INSERT INTO elements "
        "(id,substation_id,element_type,name,serial_number,gate,hemizygos,is_main_switch) "
        "VALUES (1,1,'Μετασχηματιστής','T1','S1','','',0)"
    )
    conn.commit()

    issue = detect_substation_conflicts(conn, 1)[0]
    set_substation_conflict_exception(
        conn, 1, issue["type"], issue["key"], issue["message"]
    )

    remaining = detect_substation_conflicts(conn, 1)
    assert all(item["key"] != issue["key"] for item in remaining)
