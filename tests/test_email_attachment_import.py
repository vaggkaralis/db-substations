import sqlite3

from database import init_db
import maintenance
import maintenance_email_importer


def test_open_maintenance_from_email_payload_keeps_attachment_paths(monkeypatch):
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
            captured["args"] = args
            captured["kwargs"] = kwargs

    payload = {
        "subject": "S1 2026-04-27",
        "body": "maintenance body",
        "sender_name": "Tester",
        "received_at": "2026-04-27T10:00:00",
        "attachment_paths": [r"C:\temp\photo1.jpg", r"C:\temp\video1.mp4"],
    }

    maintenance.open_maintenance_from_email_payload(FakeApp(), {}, payload)

    prefill = captured["kwargs"]["prefill_data"]
    assert prefill["attachment_paths"] == payload["attachment_paths"]


def test_create_maintenance_from_email_forwards_attachment_paths_to_folder_creation(
    monkeypatch,
):
    conn = init_db(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("INSERT INTO substations (id, name) VALUES (?, ?)", (1, "S1"))
    cur.execute(
        "INSERT INTO elements (id, substation_id, element_type, name, gate, breaker_category) VALUES (?, ?, ?, ?, ?, ?)",
        (10, 1, "Διακόπτης ΜΤ", "Ρ-1", "ΠΥΛΗ 1", "Κενού"),
    )
    conn.commit()

    captured = {}

    monkeypatch.setattr(
        maintenance_email_importer,
        "_parse_subject_for_substation_and_date",
        lambda _subject: ("S1", "2026-04-27"),
    )
    monkeypatch.setattr(
        maintenance_email_importer,
        "_match_substation_by_name",
        lambda _conn, _name: {"id": 1, "name": "S1"},
    )
    monkeypatch.setattr(
        maintenance_email_importer,
        "_match_substation_in_text",
        lambda _conn, _text: None,
    )
    monkeypatch.setattr(
        maintenance_email_importer,
        "_match_person_by_sender",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        maintenance_email_importer,
        "_find_people_in_body",
        lambda *_args, **_kwargs: set(),
    )
    monkeypatch.setattr(
        maintenance_email_importer,
        "_find_elements_in_body",
        lambda *_args, **_kwargs: {10},
    )

    def fake_ensure_maintenance_folders(*args, **kwargs):
        captured["attachment_paths"] = list(kwargs.get("attachment_paths") or [])
        return {"primary_media_folder": r"C:\media", "folders": []}

    monkeypatch.setattr(
        maintenance_email_importer,
        "ensure_maintenance_folders",
        fake_ensure_maintenance_folders,
    )

    attachment_paths = [r"C:\temp\photo1.jpg", r"C:\temp\video1.mp4"]
    success, maintenance_id = maintenance_email_importer.create_maintenance_from_email(
        subject="S1 2026-04-27",
        body="maintenance body",
        sender_email="",
        sender_name="",
        received_at="2026-04-27T10:00:00",
        attachment_paths=attachment_paths,
        conn=conn,
    )

    assert success is True
    assert maintenance_id
    assert captured["attachment_paths"] == attachment_paths
