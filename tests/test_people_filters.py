from database import init_db
from DBrun import SubstationApp
from validation import filter_people_for_maintenance


def make_person(pid, name, role, active=1):
    return (pid, name, role, active)


def test_filter_people_basic():
    people = [
        make_person(1, "Alice", "Μηχανικός"),
        make_person(2, "Bob", "Τεχνίτης"),
        make_person(3, "Carol", "Υποστήριξη"),
        make_person(4, "Dave", "Τομεάρχης ΤΕΙ"),
    ]
    responsible, crew = filter_people_for_maintenance(people)
    # Responsible should include only allowed roles
    assert any(p[1] == "Alice" for p in responsible)
    assert any(p[1] == "Dave" for p in responsible)
    assert all(p[2] != "Υποστήριξη" for p in crew)


def test_inactive_responsible_remains_selectable_but_not_in_crew():
    people = [
        make_person(1, "Alice", "Μηχανικός", active=0),
        make_person(2, "Bob", "Τεχνίτης", active=1),
    ]

    responsible, crew = filter_people_for_maintenance(people)

    assert any(p[0] == 1 for p in responsible)
    assert all(p[0] != 1 for p in crew)


def test_existing_responsible_included_when_not_allowed():
    # person 99 is current responsible but not in allowed roles
    people = [
        make_person(99, "Eve", "Τεχνίτης"),
        make_person(2, "Bob", "Τεχνίτης"),
    ]
    responsible, crew = filter_people_for_maintenance(people, responsible_person_id=99)
    # Eve should be inserted into responsible list so selection remains possible
    assert responsible[0][0] == 99
    # crew excludes Υποστήριξη (none here)
    assert all(p[2] != "Υποστήριξη" for p in crew)


def test_existing_inactive_crew_is_preserved_for_old_maintenance_only():
    people = [
        make_person(1, "Alice", "Μηχανικός", active=1),
        make_person(2, "Bob", "Τεχνίτης", active=0),
    ]

    responsible, crew = filter_people_for_maintenance(people, crew_person_ids={2})

    assert any(p[0] == 1 for p in responsible)
    assert any(p[0] == 2 for p in crew)


def test_no_allowed_responsible():
    people = [
        make_person(1, "Alice", "Τεχνίτης"),
        make_person(2, "Bob", "Αρχιτεχνίτης"),
    ]
    responsible, crew = filter_people_for_maintenance(people)
    # No allowed responsible roles present
    assert responsible == []
    # Crew should include both (since none are 'Υποστήριξη')
    assert len(crew) == 2


def test_get_maintenance_people_keeps_links_after_person_becomes_inactive():
    conn = init_db(":memory:")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO substations (id, name) VALUES (?, ?)", (1, "S1"))
    cursor.execute(
        "INSERT INTO maintenance (id, substation_id, name, date_time) VALUES (?, ?, ?, ?)",
        (10, 1, "M1", "2026-04-24"),
    )
    cursor.execute(
        "INSERT INTO people (id, name, role, active) VALUES (?, ?, ?, ?)",
        (100, "Engineer", "Μηχανικός", 0),
    )
    cursor.execute(
        "INSERT INTO maintenance_people (maintenance_id, person_id, role) VALUES (?, ?, ?)",
        (10, 100, "responsible"),
    )
    conn.commit()

    app = SubstationApp()
    app.conn = conn

    responsible, crew = app._get_maintenance_people(10)

    assert responsible == "Engineer"
    assert crew == []
