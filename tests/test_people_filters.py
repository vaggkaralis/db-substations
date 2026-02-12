from validation import filter_people_for_maintenance


def make_person(pid, name, role):
    return (pid, name, role)


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
