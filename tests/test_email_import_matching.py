import sqlite3

from database import init_db
from email_text_utils import tokens_match
from maintenance import open_maintenance_from_email_payload
from maintenance_email_importer import (
    find_matching_isolation_request_id,
    infer_substation_from_email,
    resolve_linked_isolation_request_id,
)


def test_tokens_match_avoids_short_prefix_false_positive():
    assert tokens_match(["στα"], ["σταγειρα"]) is False


def test_infer_substation_from_email_prefers_same_day_isolation_candidate():
    conn = init_db(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.executemany(
        "INSERT INTO substations (id, name) VALUES (?, ?)",
        [
            (16, "ΒΑΒΔΟΣ"),
            (12, "ΕΔΕΣΣΑΙΟΣ"),
            (38, "ΣΕΡΡΕΣ"),
            (53, "ΣΤΑΓΕΙΡΑ"),
        ],
    )
    cur.executemany(
        "INSERT INTO elements (id, substation_id, element_type, name, gate, breaker_category) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (138, 16, "Διακόπτης ΜΤ", "Ρ-230", "ΠΥΛΗ 2", "Κενού"),
            (139, 16, "Διακόπτης ΜΤ", "Ρ-240", "ΠΥΛΗ 2", "Κενού"),
            (144, 16, "Διακόπτης ΜΤ", "Ρ-325", "ΠΥΛΗ 2", "Κενού"),
            (338, 12, "Διακόπτης ΜΤ", "Ρ-230", "ΠΥΛΗ 1", "Κενού"),
            (339, 12, "Διακόπτης ΜΤ", "Ρ-230 (ΠΑΛΙΟΣ)", "ΠΥΛΗ 1", "Κενού"),
            (340, 12, "Διακόπτης ΜΤ", "Ρ-240", "ΠΥΛΗ 1", "Κενού"),
            (341, 12, "Διακόπτης ΜΤ", "Ρ-240 (ΠΑΛΙΟΣ)", "ΠΥΛΗ 1", "Κενού"),
            (342, 12, "Διακόπτης ΜΤ", "Ρ-250", "ΠΥΛΗ 1", "Κενού"),
            (343, 12, "Διακόπτης ΜΤ", "Ρ-250 (ΠΑΛΙΟΣ)", "ΠΥΛΗ 1", "Κενού"),
            (1302, 38, "Διακόπτης ΜΤ", "Ρ-230", "ΠΥΛΗ 2", "Κενού"),
            (1304, 38, "Διακόπτης ΜΤ", "Ρ-240", "ΠΥΛΗ 2", "Κενού"),
            (1306, 38, "Διακόπτης ΜΤ", "Ρ-250", "ΠΥΛΗ 2", "Κενού"),
            (1317, 38, "Διακόπτης ΜΤ", "Ρ-325", "ΠΥΛΗ 2", "Κενού"),
            (1408, 53, "Διακόπτης ΜΤ", "Ρ-230", "ΠΥΛΗ 2", "Κενού"),
            (1411, 53, "Διακόπτης ΜΤ", "Ρ-250", "ΠΥΛΗ 2", "Κενού"),
            (1412, 53, "Διακόπτης ΜΤ", "Ρ-250", "ΠΥΛΗ 3", "Κενού"),
            (1416, 53, "Διακόπτης ΜΤ", "Ρ-325", "ΠΥΛΗ 2", "Κενού"),
        ],
    )
    cur.executemany(
        "INSERT INTO isolation_requests (id, substation_id, start_datetime, end_datetime, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                19,
                16,
                "2026-04-27 10:00",
                "2026-04-30 09:30",
                "Accepted",
                "2026-04-26",
                "2026-04-26",
            ),
            (
                20,
                38,
                "2026-04-27 09:00",
                "2026-04-28 14:00",
                "Accepted",
                "2026-04-26",
                "2026-04-26",
            ),
            (
                12,
                53,
                "2026-04-17 09:00",
                "2026-04-17 14:00",
                "Accepted",
                "2026-04-16",
                "2026-04-16",
            ),
        ],
    )
    conn.commit()

    body = (
        "Καλησπέρα, σήμερα μετά την απομόνωση του ημιζυγου έγιναν οι εξής εργασίες: "
        "Συντήρηση Ρ250, Ρ230, Ρ240, Ρ325."
    )
    matched = infer_substation_from_email(
        conn,
        subject="Συντήρηση ΔΙ και ημιζυγου 2α 27.04.2026",
        body=body,
        date_time_value="2026-04-27 11:27:30",
    )

    assert matched is not None
    assert matched["id"] == 38
    assert matched["name"] == "ΣΕΡΡΕΣ"


def test_open_maintenance_from_email_payload_prefills_matching_isolation_id():
    conn = init_db(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("ALTER TABLE people ADD COLUMN surname TEXT")
    cur.execute("INSERT INTO substations (id, name) VALUES (?, ?)", (1, "S1"))
    cur.execute(
        "INSERT INTO elements (id, substation_id, element_type, name, breaker_category) VALUES (?, ?, ?, ?, ?)",
        (10, 1, "Διακόπτης ΜΤ", "Ρ-1", "Κενού"),
    )
    cur.execute(
        "INSERT INTO people (id, name, role, active) VALUES (?, ?, ?, ?)",
        (5, "Tester", "technician", 1),
    )
    cur.execute(
        "INSERT INTO isolation_requests (id, substation_id, start_datetime, end_datetime, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            7,
            1,
            "2026-04-27 09:00",
            "2026-04-27 14:00",
            "Accepted",
            "2026-04-26",
            "2026-04-26",
        ),
    )
    conn.commit()

    captured = {}

    class FakeApp:
        def __init__(self):
            self.conn = conn

        def _find_substation_in_text(self, *_args, **_kwargs):
            return (1, "S1")

        def _match_person_by_sender(self, *_args, **_kwargs):
            return 5

        def _find_people_in_body(self, *_args, **_kwargs):
            return set()

        def _find_elements_in_body(self, *_args, **_kwargs):
            return {10}

        def _prompt_substation_selection(self, *_args, **_kwargs):
            raise AssertionError("Unexpected substation prompt")

        def _prompt_add_elements_then_continue(self, *_args, **_kwargs):
            raise AssertionError("Unexpected add-elements prompt")

        def _prompt_responsible_selection(self, *_args, **_kwargs):
            raise AssertionError("Unexpected responsible prompt")

        def show_maintenance_menu(self, *args, **kwargs):
            captured["kwargs"] = kwargs

    payload = {
        "subject": "Συντήρηση 27.04.2026",
        "body": "maintenance body",
        "sender_name": "Tester",
        "received_at": "2026-04-27T11:27:30+00:00",
        "attachment_paths": [],
    }

    open_maintenance_from_email_payload(FakeApp(), {}, payload)

    prefill = captured["kwargs"]["prefill_data"]
    assert prefill["linked_isolation_request_id"] == 7


def test_open_maintenance_from_email_payload_uses_shared_matching_helpers():
    conn = init_db(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("ALTER TABLE people ADD COLUMN surname TEXT")
    cur.execute("INSERT INTO substations (id, name) VALUES (?, ?)", (1, "S1"))
    cur.execute(
        "INSERT INTO elements (id, substation_id, element_type, name, breaker_category) VALUES (?, ?, ?, ?, ?)",
        (10, 1, "Μετασχηματιστής 150/20KV", "ΜΣ1", ""),
    )
    cur.executemany(
        "INSERT INTO people (id, name, role, active, email) VALUES (?, ?, ?, ?, ?)",
        [
            (5, "Tester", "technician", 1, "tester@example.com"),
            (6, "Μουτσέλος Ιωάννης", "technician", 1, None),
        ],
    )
    conn.commit()

    captured = {}

    class FakeApp:
        def __init__(self):
            self.conn = conn

        def _find_substation_in_text(self, *_args, **_kwargs):
            return (1, "S1")

        def _match_person_by_sender(self, *_args, **_kwargs):
            raise AssertionError("Should use shared sender matcher")

        def _find_people_in_body(self, *_args, **_kwargs):
            raise AssertionError("Should use shared people matcher")

        def _find_elements_in_body(self, *_args, **_kwargs):
            raise AssertionError("Should use shared element matcher")

        def _prompt_substation_selection(self, *_args, **_kwargs):
            raise AssertionError("Unexpected substation prompt")

        def _prompt_add_elements_then_continue(self, *_args, **_kwargs):
            raise AssertionError("Unexpected add-elements prompt")

        def _prompt_responsible_selection(self, *_args, **_kwargs):
            raise AssertionError("Unexpected responsible prompt")

        def show_maintenance_menu(self, *args, **kwargs):
            captured["kwargs"] = kwargs

    payload = {
        "subject": "Συντήρηση 27.04.2026",
        "body": "Συντήρηση στον ΜΣ1. Παρόντες στο συνεργείο: Μουτσέλος.",
        "sender_name": "Tester",
        "sender_email": "tester@example.com",
        "received_at": "2026-04-27T11:27:30+00:00",
        "attachment_paths": [],
    }

    open_maintenance_from_email_payload(FakeApp(), {}, payload)

    prefill = captured["kwargs"]["prefill_data"]
    assert prefill["responsible_id"] == 5
    assert prefill["crew_ids"] == {6}
    assert prefill["element_ids"] == {10}


def test_find_matching_isolation_request_id_prefers_exact_overlap():
    conn = init_db(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("INSERT INTO substations (id, name) VALUES (?, ?)", (1, "S1"))
    cur.executemany(
        "INSERT INTO isolation_requests (id, substation_id, start_datetime, end_datetime, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                7,
                1,
                "2026-04-27 09:00",
                "2026-04-27 14:00",
                "Accepted",
                "2026-04-26",
                "2026-04-26",
            ),
            (
                8,
                1,
                "2026-04-27 08:00",
                "2026-04-27 18:00",
                "Requested",
                "2026-04-26",
                "2026-04-26",
            ),
        ],
    )
    conn.commit()

    matched = find_matching_isolation_request_id(conn, 1, "2026-04-27 11:27:30")

    assert matched == 7


def test_resolve_linked_isolation_request_id_uses_matching_date_for_new_records():
    conn = init_db(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("INSERT INTO substations (id, name) VALUES (?, ?)", (1, "S1"))
    cur.executemany(
        "INSERT INTO isolation_requests (id, substation_id, start_datetime, end_datetime, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                2,
                1,
                "2026-05-10 08:00",
                "2026-05-10 16:00",
                "Accepted",
                "2026-05-09",
                "2026-05-09",
            ),
            (
                3,
                1,
                "2026-04-27 09:00",
                "2026-04-27 14:00",
                "Accepted",
                "2026-04-26",
                "2026-04-26",
            ),
        ],
    )
    conn.commit()

    matched = resolve_linked_isolation_request_id(
        conn,
        1,
        date_time_value="2026-04-27 11:27:30",
        auto_select_by_date=True,
    )

    assert matched == 3


def test_resolve_linked_isolation_request_id_keeps_old_edit_unlinked():
    conn = init_db(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("INSERT INTO substations (id, name) VALUES (?, ?)", (1, "S1"))
    cur.executemany(
        "INSERT INTO isolation_requests (id, substation_id, start_datetime, end_datetime, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                2,
                1,
                "2026-05-10 08:00",
                "2026-05-10 16:00",
                "Accepted",
                "2026-05-09",
                "2026-05-09",
            ),
            (
                3,
                1,
                "2026-04-27 09:00",
                "2026-04-27 14:00",
                "Accepted",
                "2026-04-26",
                "2026-04-26",
            ),
        ],
    )
    conn.commit()

    matched = resolve_linked_isolation_request_id(
        conn,
        1,
        date_time_value="2026-04-27 11:27:30",
        linked_request_id=None,
        auto_select_by_date=False,
    )

    assert matched is None
