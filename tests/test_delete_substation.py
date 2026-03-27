from database import init_db
from DBrun import SubstationApp


def test_delete_substation_cascades():
    conn = init_db(":memory:")
    c = conn.cursor()

    # Create substation, elements, maintenance and related rows
    c.execute("INSERT INTO substations (id, name) VALUES (?,?)", (1, "S1"))
    c.execute(
        (
            "INSERT INTO elements (id, substation_id, element_type, name) "
            "VALUES (?,?,?,?)"
        ),
        (1, 1, "Transformer", "T1"),
    )
    c.execute(
        (
            "INSERT INTO elements (id, substation_id, element_type, name) "
            "VALUES (?,?,?,?)"
        ),
        (2, 1, "Breaker", "B1"),
    )

    c.execute(
        (
            "INSERT INTO maintenance (id, substation_id, name, date_time) "
            "VALUES (?,?,?,?)"
        ),
        (10, 1, "M1", "2020-01-01"),
    )
    c.execute(
        (
            "INSERT INTO maintenance_elements (id, maintenance_id, element_id, "
            "element_comments) "
            "VALUES (?,?,?,?)"
        ),
        (100, 10, 1, "ok"),
    )
    c.execute(
        ("INSERT INTO people (id, name, role) VALUES (?,?,?)"),
        (200, "P1", "tech"),
    )
    c.execute(
        (
            "INSERT INTO maintenance_people (id, maintenance_id, person_id, role) "
            "VALUES (?,?,?,?)"
        ),
        (300, 10, 200, "crew"),
    )

    conn.commit()

    app = SubstationApp()
    app.conn = conn
    # Avoid UI work in the test by stubbing the display refresh
    app._display_substations = lambda *a, **k: None
    # Call the deletion method under test
    app.delete_substation(1, None)

    def count(q):
        return c.execute(q).fetchone()[0]

    assert count("SELECT COUNT(*) FROM substations") == 0
    assert count("SELECT COUNT(*) FROM elements") == 0
    assert count("SELECT COUNT(*) FROM maintenance") == 0
    assert count("SELECT COUNT(*) FROM maintenance_elements") == 0
    assert count("SELECT COUNT(*) FROM maintenance_people") == 0
