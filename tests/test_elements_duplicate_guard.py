import sqlite3

from elements import (
    _find_duplicate_element_id,
    _find_duplicate_element_rows,
    _normalize_element_name,
)


def _build_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE elements ("
        "id INTEGER PRIMARY KEY, substation_id INTEGER, name TEXT)"
    )
    return conn


def test_normalize_element_name_collapses_whitespace_and_nbsp():
    assert _normalize_element_name("  ΜΣ\u00a0  2  ") == "ΜΣ 2"


def test_find_duplicate_element_id_matches_normalized_names():
    conn = _build_conn()
    conn.execute(
        "INSERT INTO elements (id, substation_id, name) VALUES (?, ?, ?)",
        (10, 44, "ΜΣ 2"),
    )

    duplicate_id = _find_duplicate_element_id(conn, 44, "  ΜΣ\u00a0  2 ")

    assert duplicate_id == 10


def test_find_duplicate_element_id_respects_excluded_id():
    conn = _build_conn()
    conn.execute(
        "INSERT INTO elements (id, substation_id, name) VALUES (?, ?, ?)",
        (10, 44, "ΜΣ 2"),
    )

    duplicate_id = _find_duplicate_element_id(conn, 44, "ΜΣ 2", exclude_id=10)

    assert duplicate_id is None


def test_find_duplicate_element_rows_groups_same_name_and_ids():
    conn = _build_conn()
    conn.execute(
        "INSERT INTO elements (id, substation_id, name) VALUES (?, ?, ?)",
        (11, 44, "ΜΣ 1"),
    )
    conn.execute(
        "INSERT INTO elements (id, substation_id, name) VALUES (?, ?, ?)",
        (12, 44, "  ΜΣ\u00a0 1  "),
    )

    duplicates = _find_duplicate_element_rows(conn, 44)

    assert len(duplicates) == 1
    assert duplicates[0]["display_name"] == "ΜΣ 1"
    assert sorted(element_id for element_id, _ in duplicates[0]["rows"]) == [11, 12]
