import importlib
import sqlite3
import types


def test_import_elements_module_and_delegate_exists():
    mod = importlib.import_module("elements")
    # Ensure at least one safe delegate exists (doesn't require an app instance)
    assert hasattr(mod, "show_add_element_popup_delegate")
    assert hasattr(mod, "show_add_subelement_entry_popup")


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


def test_show_element_history_includes_cross_substation_linked_maintenances():
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
        INSERT INTO substations (id, name) VALUES (2, 'S2');
        INSERT INTO elements (id, substation_id, name) VALUES (1296, 1, 'T1');
        INSERT INTO maintenance (id, substation_id, date_time) VALUES (10, 2, '2024-04-15');
        INSERT INTO maintenance (id, substation_id, date_time) VALUES (11, 1, '2023-08-10');
        INSERT INTO maintenance_elements (maintenance_id, element_id) VALUES (10, 1296);
        INSERT INTO maintenance_elements (maintenance_id, element_id) VALUES (11, 1296);
        """
    )

    captured = {}

    def _show_history(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

    app = types.SimpleNamespace(
        conn=conn, show_substation_maintenance_history=_show_history
    )

    mod.show_element_maintenance_history(app, 1296, "T1", None)

    assert captured["args"][:2] == (1, "S1")
    assert captured["kwargs"]["preselected_element_id"] == 1296
    assert captured["kwargs"]["include_maintenance_ids"] == [10, 11]

    conn.close()


def test_show_substation_history_does_not_warn_for_assigned_gate_values(monkeypatch):
    mod = importlib.import_module("DBrun")

    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE substations (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE elements (
            id INTEGER PRIMARY KEY,
            substation_id INTEGER,
            name TEXT,
            gate TEXT,
            element_type TEXT,
            is_main_switch INTEGER
        );
        INSERT INTO substations (id, name) VALUES (1, 'ΣΙΝΔΟΣ (Β.Π.ΘΕΣΣΑΛΟΝΙΚΗΣ)');
        INSERT INTO elements (id, substation_id, name, gate, element_type, is_main_switch)
        VALUES (10, 1, 'Q1', 'ΠΥΛΗ 9', 'Διακόπτης ΥΤ', 1);
        INSERT INTO elements (id, substation_id, name, gate, element_type, is_main_switch)
        VALUES (11, 1, 'Q2', NULL, 'Διακόπτης ΥΤ', 1);
        """
    )

    rows = mod._elements_missing_gate_warning_rows(conn, 1)

    assert [row[0] for row in rows] == [11]

    conn.close()
