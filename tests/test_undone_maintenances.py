import importlib
import database
import DBrun


def test_show_undone_maintenances_smoke():
    # create in-memory DB and a maintenance with pending tasks
    conn = database.init_db(':memory:')
    c = conn.cursor()
    c.execute("INSERT INTO substations (name) VALUES (?)", ("S1",))
    sub_id = c.lastrowid
    c.execute("INSERT INTO maintenance (substation_id, name, date_time) VALUES (?, ?, datetime('now'))", (sub_id, "M1"))
    mid = c.lastrowid
    c.execute("INSERT INTO maintenance_pending_tasks (maintenance_id, tasks_text, created_at) VALUES (?, ?, datetime('now'))", (mid, "Task A"))
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