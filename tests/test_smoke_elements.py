import importlib
import sqlite3
import types


def test_import_elements_module_and_delegate_exists():
    mod = importlib.import_module("elements")
    # Ensure at least one safe delegate exists (doesn't require an app instance)
    assert hasattr(mod, "show_add_element_popup_delegate")


def test_show_element_history_ignores_orphan_links(monkeypatch):
    mod = importlib.import_module("elements")

    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE substations (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE elements (id INTEGER PRIMARY KEY, substation_id INTEGER, name TEXT);
        CREATE TABLE maintenance (id INTEGER PRIMARY KEY, substation_id INTEGER, date_time TEXT);
        CREATE TABLE maintenance_elements (
            id INTEGER PRIMARY KEY,
            maintenance_id INTEGER,
            element_id INTEGER
        );
        INSERT INTO substations (id, name) VALUES (1, 'S1');
        INSERT INTO elements (id, substation_id, name) VALUES (707, 1, 'Ρ-370');
        INSERT INTO maintenance_elements (maintenance_id, element_id) VALUES (58, 707);
        """
    )

    captured = {}

    def fake_show_no_history_popup(app, **kwargs):
        captured["app"] = app
        captured.update(kwargs)

    monkeypatch.setattr(
        mod, "_show_no_history_maintenance_options", fake_show_no_history_popup
    )

    app = types.SimpleNamespace(
        conn=conn,
        show_substation_maintenance_history=lambda *args, **kwargs: captured.setdefault(
            "history_called", True
        ),
    )

    mod.show_element_maintenance_history(app, 707, "Ρ-370", None)

    assert captured.get("history_called") is None
    assert captured["element_id"] == 707
    assert captured["element_name"] == "Ρ-370"
    assert captured["substation_id"] == 1
    assert captured["substation_name"] == "S1"

    conn.close()
