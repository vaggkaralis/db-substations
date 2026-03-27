import sqlite3

import pytest

from database import init_db


def test_elements_breaker_category_constraint(tmp_path):
    db_path = tmp_path / "test.db"
    conn = init_db(str(db_path))
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO substations (id, name) VALUES (?, ?)",
        (1, "Test Substation"),
    )
    conn.commit()

    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='elements'")
    sql = cur.fetchone()[0] or ""
    assert "CHECK" in sql or "TRIM(breaker_category" in sql

    # Inserting a circuit breaker without breaker_category should violate the constraint
    with pytest.raises(sqlite3.IntegrityError):
        cur.execute(
            (
                "INSERT INTO elements (substation_id, element_type, breaker_category) "
                "VALUES (?, ?, ?)"
            ),
            (1, "Διακόπτης ΜΤ", ""),
        )
        conn.commit()

    # Valid insert should work
    cur.execute(
        (
            "INSERT INTO elements (substation_id, element_type, breaker_category) "
            "VALUES (?, ?, ?)"
        ),
        (1, "Διακόπτης ΜΤ", "SF6"),
    )
    conn.commit()
