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
            operating_status TEXT,
            element_model_id INTEGER,
            split_mv_gates INTEGER DEFAULT 0
        );
        CREATE TABLE element_models (
            id INTEGER PRIMARY KEY,
            model_name TEXT,
            manual_pdf TEXT,
            onedrive_manual_link TEXT
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


def test_gate_main_mv_count_ignores_inactive_main_breakers():
    conn = sqlite3.connect(":memory:")
    _create_schema(conn)
    conn.execute("INSERT INTO substations VALUES (1, 'Υποσταθμός 1')")
    conn.executemany(
        "INSERT INTO elements "
        "(id,substation_id,element_type,name,serial_number,gate,hemizygos,is_main_switch,operating_status) "
        "VALUES (?,1,?,?,?,?,?,?,?)",
        [
            (1, "Διακόπτης ΜΤ", "MV1", "S1", "ΠΥΛΗ 1", "", 1, "Ενεργή"),
            (2, "Διακόπτης ΜΤ", "MV2", "S2", "ΠΥΛΗ 1", "", 1, "Ανενεργή"),
            (3, "Διακόπτης ΥΤ", "HV1", "S3", "ΠΥΛΗ 1", "", 1, "Ενεργή"),
            (4, "Μετασχηματιστής 150/20KV", "T1", "S4", "ΠΥΛΗ 1", "", 0, "Ενεργή"),
        ],
    )
    conn.commit()

    issues = detect_substation_conflicts(conn, 1)
    types = {issue["type"] for issue in issues}

    assert "gate_main_mv_breaker" not in types


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


def test_split_mv_transformer_gate_allows_parent_hv_and_child_mv_gates():
    conn = sqlite3.connect(":memory:")
    _create_schema(conn)
    conn.execute("INSERT INTO substations VALUES (1, 'Υποσταθμός 1')")
    conn.executemany(
        "INSERT INTO elements "
        "(id,substation_id,element_type,name,serial_number,gate,hemizygos,is_main_switch,operating_status,split_mv_gates) "
        "VALUES (?,1,?,?,?,?,?,?,?,?)",
        [
            (
                1,
                "Μετασχηματιστής 150/20KV",
                "T3",
                "ST3",
                "ΠΥΛΗ 3",
                "",
                0,
                "Ενεργή",
                1,
            ),
            (2, "Διακόπτης ΥΤ", "HV3", "SHV3", "ΠΥΛΗ 3", "", 1, "Ενεργή", 0),
            (3, "Διακόπτης ΜΤ", "MV31", "SM31", "ΠΥΛΗ 3.1", "", 1, "Ενεργή", 0),
            (4, "Διακόπτης ΜΤ", "MV32", "SM32", "ΠΥΛΗ 3.2", "", 1, "Ενεργή", 0),
        ],
    )
    conn.commit()

    issues = detect_substation_conflicts(conn, 1)
    types = {issue["type"] for issue in issues}

    assert "gate_transformer_count" not in types
    assert "gate_hv_breaker_count" not in types
    assert "gate_main_mv_breaker" not in types


def test_existing_conflict_checks_are_problems_by_default():
    conn = sqlite3.connect(":memory:")
    _create_schema(conn)
    conn.execute("INSERT INTO substations VALUES (1, 'Υποσταθμός 1')")
    conn.execute(
        "INSERT INTO elements "
        "(id,substation_id,element_type,name,serial_number,gate,hemizygos,is_main_switch) "
        "VALUES (1,1,'Μετασχηματιστής','T1','S1','','',0)"
    )
    conn.commit()

    issues = detect_substation_conflicts(conn, 1)
    assert any(issue["severity"] == "problem" for issue in issues)
    assert all(
        issue["severity"] == "problem"
        for issue in issues
        if issue["type"] != "missing_manual"
    )


def test_missing_manual_is_warning():
    conn = sqlite3.connect(":memory:")
    _create_schema(conn)
    conn.execute("INSERT INTO substations VALUES (1, 'Υποσταθμός 1')")
    conn.executemany(
        "INSERT INTO element_models (id, model_name, manual_pdf, onedrive_manual_link) VALUES (?, ?, ?, ?)",
        [
            (10, "Model with manual", "", "https://example.com/manual"),
            (11, "Model missing manual", "", ""),
        ],
    )
    conn.executemany(
        "INSERT INTO elements "
        "(id,substation_id,element_type,name,serial_number,gate,hemizygos,is_main_switch,operating_status,element_model_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            (1, 1, "Μετασχηματιστής", "T1", "S1", "ΠΥΛΗ 1", "", 0, "Ενεργή", 10),
            (2, 1, "Διακόπτης ΥΤ", "HV1", "S2", "ΠΥΛΗ 1", "", 1, "Ενεργή", 11),
            (3, 1, "Διακόπτης ΜΤ", "MV1", "S3", "ΠΥΛΗ 1", "", 1, "Ενεργή", 10),
        ],
    )
    conn.commit()

    issues = detect_substation_conflicts(conn, 1)
    missing_manual = [issue for issue in issues if issue["type"] == "missing_manual"]
    assert len(missing_manual) == 1
    assert missing_manual[0]["severity"] == "warning"
