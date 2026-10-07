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


def test_maintenance_history_close_restores_parent_popup():
    mod = importlib.import_module("DBrun")

    popup = types.SimpleNamespace(dismissed=False)
    popup.dismiss = lambda: setattr(popup, "dismissed", True)
    parent = types.SimpleNamespace(opened=False)
    parent.open = lambda: setattr(parent, "opened", True)

    calls = {"child_close": 0}

    def fake_child_close(*args, **kwargs):
        calls["child_close"] += 1

    app = types.SimpleNamespace(
        _dismiss_popup_and_maybe_close_child_window=fake_child_close,
        _allow_exit_without_sync_prompt=False,
    )

    mod.SubstationApp._dismiss_popup_and_restore_parent(
        app,
        popup,
        parent_display_popup=parent,
        close_child_window=False,
    )

    assert popup.dismissed is True
    assert parent.opened is True
    assert calls["child_close"] == 0


def test_delete_maintenance_for_substation_reopens_history_view():
    mod = importlib.import_module("DBrun")

    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE substations (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE elements (id INTEGER PRIMARY KEY, substation_id INTEGER, name TEXT);
        CREATE TABLE maintenance (
            id INTEGER PRIMARY KEY,
            substation_id INTEGER,
            name TEXT,
            date_time TEXT,
            responsible_id INTEGER,
            overall_comments TEXT,
            maintenance_type TEXT,
            onedrive_media_folder_link TEXT,
            preparation_checklist_json TEXT,
            data_json TEXT
        );
        CREATE TABLE maintenance_elements (
            id INTEGER PRIMARY KEY,
            maintenance_id INTEGER,
            element_id INTEGER,
            element_comments TEXT,
            insulation_closed_fa_ground TEXT,
            insulation_closed_fb_ground TEXT,
            insulation_closed_fc_ground TEXT,
            contact_resistance_fa_fa TEXT,
            contact_resistance_fb_fb TEXT,
            contact_resistance_fc_fc TEXT,
            operations_count TEXT
        );
        CREATE TABLE maintenance_storage_paths (
            id INTEGER PRIMARY KEY,
            maintenance_id INTEGER,
            instance_folder TEXT
        );
        INSERT INTO substations (id, name) VALUES (1, 'S1');
        INSERT INTO maintenance (id, substation_id, name, date_time) VALUES (7, 1, 'T1', '2024-01-15');
        INSERT INTO maintenance_elements (maintenance_id, element_id) VALUES (7, 11);
        INSERT INTO elements (id, substation_id, name) VALUES (11, 1, 'Q1');
        """
    )

    history_events = []
    parent_popup = types.SimpleNamespace(
        dismiss=lambda: history_events.append("history_dismiss")
    )
    parent_display_popup = types.SimpleNamespace(
        open=lambda: history_events.append("parent_open"),
        dismiss=lambda: history_events.append("parent_dismiss"),
    )

    def fake_refresh(**kwargs):
        history_events.append("refresh")

    def fake_reopen(*args, **kwargs):
        history_events.append(
            f"reopen:{args[0]}:{args[1]}:{kwargs.get('parent_display_popup') is parent_display_popup}"
        )

    app = types.SimpleNamespace(
        conn=conn,
        _refresh_maintenance_dates_for_scope=fake_refresh,
        _append_change_log=lambda *args, **kwargs: history_events.append("log"),
        show_substation_maintenance_history=fake_reopen,
    )

    mod.SubstationApp.delete_maintenance_for_substation(
        app,
        7,
        parent_popup,
        1,
        "S1",
        parent_display_popup,
    )

    assert "history_dismiss" in history_events
    assert "parent_dismiss" not in history_events
    assert "reopen:1:S1:True" in history_events
    assert "refresh" in history_events

    conn.close()
