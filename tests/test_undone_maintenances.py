import database
import DBrun


def test_show_undone_maintenances_smoke():
    # create in-memory DB and a maintenance with pending tasks
    conn = database.init_db(":memory:")
    c = conn.cursor()
    c.execute("INSERT INTO substations (name) VALUES (?)", ("S1",))
    sub_id = c.lastrowid
    c.execute(
        "INSERT INTO maintenance (substation_id, name, date_time) "
        "VALUES (?, ?, datetime('now'))",
        (sub_id, "M1"),
    )
    mid = c.lastrowid
    c.execute(
        "INSERT INTO maintenance_pending_tasks "
        "(maintenance_id, tasks_text, created_at) "
        "VALUES (?, ?, datetime('now'))",
        (mid, "Task A"),
    )
    conn.commit()

    app = DBrun.SubstationApp()
    app.conn = conn

    # calling the view should not raise and should open the popup (shims return None)
    # monkeypatch ui.shared.IconOnlyButton to avoid Window.bind usage in tests
    import ui.shared as shared_mod

    class DummyIconOnlyButton:
        def __init__(self, *a, **k):
            pass

        def bind(self, *a, **k):
            return None

    shared_mod.IconOnlyButton = DummyIconOnlyButton

    app.show_undone_maintenances()


def test_incomplete_maintenance_reminder_lists_all_rows():
    conn = database.init_db(":memory:")
    c = conn.cursor()
    c.execute("INSERT INTO substations (name) VALUES (?)", ("S1",))
    sub_id = c.lastrowid
    c.execute(
        "INSERT INTO elements (substation_id, element_type, name) VALUES (?, ?, ?)",
        (sub_id, "Μετασχηματιστής 150/20", "Q1"),
    )
    elem1_id = c.lastrowid
    c.execute(
        "INSERT INTO elements (substation_id, element_type, name) VALUES (?, ?, ?)",
        (sub_id, "Μετασχηματιστής 150/20", "ΜΣ1"),
    )
    elem2_id = c.lastrowid
    c.execute(
        "INSERT INTO maintenance (substation_id, name, date_time) VALUES (?, ?, ?)",
        (sub_id, "M older", "2020-01-13"),
    )
    older_id = c.lastrowid
    c.execute(
        "INSERT INTO maintenance_pending_tasks (maintenance_id, tasks_text, created_at) VALUES (?, ?, datetime('now'))",
        (older_id, "Task A"),
    )
    c.execute(
        "INSERT INTO maintenance_elements (maintenance_id, element_id) VALUES (?, ?)",
        (older_id, elem1_id),
    )
    c.execute(
        "INSERT INTO maintenance (substation_id, name, date_time) VALUES (?, ?, ?)",
        (sub_id, "M newer", "2026-03-17"),
    )
    newer_id = c.lastrowid
    c.execute(
        "INSERT INTO maintenance_pending_tasks (maintenance_id, tasks_text, created_at) VALUES (?, ?, datetime('now'))",
        (newer_id, "Task B\nTask C"),
    )
    c.execute(
        "INSERT INTO maintenance_elements (maintenance_id, element_id) VALUES (?, ?)",
        (newer_id, elem2_id),
    )
    conn.commit()

    app = DBrun.SubstationApp()
    app.conn = conn

    rows = app._get_substation_incomplete_maintenances(sub_id)

    assert [row["name"] for row in rows] == ["M newer", "M older"]

    reminder_text = app._build_substation_incomplete_maintenance_reminder_text(
        "S1", rows
    )

    assert "S1" in reminder_text
    assert "M newer" in reminder_text
    assert "M older" in reminder_text
    assert "ΜΣ1" in reminder_text
    assert "Q1" in reminder_text
    assert "Task B" in reminder_text
    assert "Task A" in reminder_text


def test_show_maintenance_menu_for_substation_opens_form_when_no_pending(monkeypatch):
    conn = database.init_db(":memory:")
    c = conn.cursor()
    c.execute("INSERT INTO substations (name) VALUES (?)", ("S1",))
    sub_id = c.lastrowid
    conn.commit()

    app = DBrun.SubstationApp()
    app.conn = conn
    captured = {}

    def fake_show_maintenance_menu(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(app, "show_maintenance_menu", fake_show_maintenance_menu)

    app.show_maintenance_menu_for_substation(sub_id, "S1")

    assert captured["kwargs"]["preselected_substation_name"] == "S1"
    assert (
        captured["kwargs"]["maintenance_id"] is None
        if "maintenance_id" in captured["kwargs"]
        else True
    )


def test_generic_substation_selection_reminder_shows_once_per_substation(monkeypatch):
    conn = database.init_db(":memory:")
    c = conn.cursor()
    c.execute("INSERT INTO substations (name) VALUES (?)", ("S1",))
    sub_id = c.lastrowid
    conn.commit()

    app = DBrun.SubstationApp()
    app.conn = conn

    shown = []

    def fake_reminder(selected_substation_id, selected_name, on_close=None):
        shown.append((selected_substation_id, selected_name, on_close is not None))
        return True

    monkeypatch.setattr(
        app,
        "_show_substation_incomplete_maintenance_reminder",
        fake_reminder,
    )

    reminded_substation_ids = set()

    assert (
        app._maybe_show_incomplete_maintenance_reminder_for_substation_selection(
            "S1",
            {"S1": sub_id},
            reminded_substation_ids=reminded_substation_ids,
        )
        is True
    )
    assert shown == [(sub_id, "S1", False)]
    assert sub_id in reminded_substation_ids

    assert (
        app._maybe_show_incomplete_maintenance_reminder_for_substation_selection(
            "S1",
            {"S1": sub_id},
            reminded_substation_ids=reminded_substation_ids,
        )
        is False
    )
    assert shown == [(sub_id, "S1", False)]

    assert (
        app._maybe_show_incomplete_maintenance_reminder_for_substation_selection(
            "S1",
            {"S1": sub_id},
            maintenance_id=123,
            reminded_substation_ids=reminded_substation_ids,
        )
        is False
    )
