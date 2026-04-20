from database import init_db


def test_hv_sf6_leakage_persistence(tmp_path):
    db_path = tmp_path / "test.db"
    conn = init_db(str(db_path))
    cur = conn.cursor()

    # create minimal substation and element (HV breaker)
    cur.execute("INSERT INTO substations (id, name) VALUES (?, ?)", (1, "Test Sub"))
    conn.commit()

    cur.execute(
        "INSERT INTO elements (id, substation_id, element_type, name, breaker_category) VALUES (?, ?, ?, ?, ?)",
        (766, 1, "Διακόπτης ΥΤ", "Ρ-200", "SF6"),
    )
    conn.commit()

    # Insert maintenance record
    cur.execute(
        "INSERT INTO maintenance (id, substation_id, name, date_time) VALUES (?, ?, ?, ?)",
        (2912, 1, "Test Maint", "2026-01-05"),
    )
    conn.commit()

    # Insert maintenance_elements with SF6 leakage and methodology
    cur.execute(
        (
            "INSERT INTO maintenance_elements (maintenance_id, element_id, element_comments, sf6_leakage_kg, sf6_leak_methodology)"
            " VALUES (?, ?, ?, ?, ?)"
        ),
        (2912, 766, "Imported SF6", 0.5, "Πλήρωση"),
    )
    conn.commit()

    # Read back and assert
    cur.execute(
        "SELECT sf6_leakage_kg, sf6_leak_methodology FROM maintenance_elements WHERE maintenance_id=? AND element_id=?",
        (2912, 766),
    )
    row = cur.fetchone()
    assert row is not None
    assert row[0] == 0.5
    assert row[1] == "Πλήρωση"

    conn.close()
