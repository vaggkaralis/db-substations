import sys
import types
import builtins
import sqlite3
import re

import android_app
import ui.shared as shared_ui


def _collect_widget_texts(widget):
    texts = []
    if hasattr(widget, "text"):
        texts.append(widget.text)
    for child in getattr(widget, "children", []):
        texts.extend(_collect_widget_texts(child))
    return texts


def _find_widget_by_text(widget, target_text):
    if getattr(widget, "text", None) == target_text:
        return widget
    for child in getattr(widget, "children", []):
        found = _find_widget_by_text(child, target_text)
        if found is not None:
            return found
    return None


def _collect_widgets_by_class_name(widget, class_name):
    matches = []
    if widget.__class__.__name__ == class_name:
        matches.append(widget)
    for child in getattr(widget, "children", []):
        matches.extend(_collect_widgets_by_class_name(child, class_name))
    return matches


def test_open_local_db_picker_uses_android_document_picker(monkeypatch):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")
    monkeypatch.setattr(
        android_app,
        "Clock",
        types.SimpleNamespace(schedule_once=lambda callback, _dt=0: callback(0)),
    )
    monkeypatch.setattr(
        app,
        "_request_android_storage_permissions",
        lambda callback=None: (callback() if callback else None) or False,
    )

    opened = []
    monkeypatch.setattr(
        app, "_open_android_local_db_picker", lambda: opened.append(True)
    )

    app.open_local_db_picker()

    assert opened == [True]


def test_open_local_db_picker_waits_for_android_permission(monkeypatch):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")
    monkeypatch.setattr(
        android_app,
        "Clock",
        types.SimpleNamespace(schedule_once=lambda callback, _dt=0: callback(0)),
    )

    monkeypatch.setattr(
        app, "_request_android_storage_permissions", lambda *_args: False
    )

    opened = []
    monkeypatch.setattr(
        app, "_open_android_local_db_picker", lambda: opened.append(True)
    )

    app.open_local_db_picker()

    assert opened == []


def test_open_local_db_picker_uses_desktop_prompt(monkeypatch):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "win")

    opened = []
    monkeypatch.setattr(app, "_prompt_local_db_path", lambda: opened.append(True))

    app.open_local_db_picker()

    assert opened == [True]


def test_handle_local_db_selection_uses_local_mode(monkeypatch):
    app = android_app.SubstationAndroidApp()

    selected = []
    monkeypatch.setattr(app, "use_local_mode", lambda path: selected.append(path))

    app._handle_local_db_selection(["content://picked/db.sqlite"])

    assert selected == ["content://picked/db.sqlite"]


def test_build_uses_local_database_button_label(monkeypatch):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(app, "load_substations", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app, "_run_startup_sync", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app, "_auto_load_saved_db", lambda: False)

    root = app.build()

    button_label = android_app.S.get("MESSAGES", {}).get(
        "LOCAL_DB_BUTTON", "Βάση Δεδομένων"
    )
    mode_label = android_app.S.get("MESSAGES", {}).get(
        "MODE_LABEL_LOCAL", "Πηγή: Τοπική Βάση"
    )
    assert app.local_db_btn.text == button_label

    texts = _collect_widget_texts(root)
    assert button_label in texts
    assert mode_label in texts


def test_build_hides_sync_button_on_android(monkeypatch):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")
    monkeypatch.setattr(app, "load_substations", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app, "_auto_load_saved_db", lambda: False)
    monkeypatch.setattr(
        android_app,
        "Clock",
        types.SimpleNamespace(schedule_once=lambda callback, _dt=0: None),
    )

    root = app.build()

    assert root is not None
    assert app.sync_btn is None


def test_build_hides_sync_button_in_desktop_preview(monkeypatch):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "win")
    monkeypatch.setattr(app, "load_substations", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app, "_auto_load_saved_db", lambda: False)
    monkeypatch.setattr(
        android_app,
        "Clock",
        types.SimpleNamespace(schedule_once=lambda callback, _dt=0: None),
    )

    root = app.build()

    assert root is not None
    assert app.sync_btn is None


def test_build_uses_vector_settings_button_on_android(monkeypatch):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")
    monkeypatch.setattr(shared_ui.Window, "bind", lambda **_kwargs: None, raising=False)
    monkeypatch.setattr(app, "load_substations", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app, "_auto_load_saved_db", lambda: False)
    monkeypatch.setattr(
        android_app,
        "Clock",
        types.SimpleNamespace(schedule_once=lambda callback, _dt=0: None),
    )

    app.build()

    assert getattr(app.settings_btn, "text", None) != "SET"
    assert (
        len(getattr(app.settings_btn, "children", [])) == 1
        or getattr(app.settings_btn, "text", None) == "S"
    )


def test_build_uses_vector_settings_button_when_window_bind_fails(monkeypatch):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")
    monkeypatch.setattr(
        shared_ui.Window,
        "bind",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("no mouse binding")),
        raising=False,
    )
    monkeypatch.setattr(app, "load_substations", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app, "_auto_load_saved_db", lambda: False)
    monkeypatch.setattr(
        android_app,
        "Clock",
        types.SimpleNamespace(schedule_once=lambda callback, _dt=0: None),
    )

    app.build()

    assert getattr(app.settings_btn, "text", None) != "SET"
    assert (
        len(getattr(app.settings_btn, "children", [])) == 1
        or getattr(app.settings_btn, "text", None) == "S"
    )


def test_build_falls_back_to_vector_settings_button_when_icon_widget_fails(monkeypatch):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")
    monkeypatch.setattr(app, "load_substations", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app, "_auto_load_saved_db", lambda: False)
    monkeypatch.setattr(
        android_app,
        "Clock",
        types.SimpleNamespace(schedule_once=lambda callback, _dt=0: None),
    )

    class BrokenIconOnlyButton:
        def __init__(self, **_kwargs):
            raise RuntimeError("broken icon widget")

    shared_module = sys.modules.get("ui.shared")
    original_icon_button = getattr(shared_module, "IconOnlyButton", None)
    monkeypatch.setattr(shared_module, "IconOnlyButton", BrokenIconOnlyButton)

    app.build()

    assert getattr(app.settings_btn, "text", None) != "SET"
    assert (
        len(getattr(app.settings_btn, "children", [])) == 1
        or getattr(app.settings_btn, "text", None) == "S"
    )

    if original_icon_button is not None:
        monkeypatch.setattr(shared_module, "IconOnlyButton", original_icon_button)


def test_load_substation_elements_uses_icon_only_android_action_buttons(monkeypatch):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")
    app.data_mode = "local"
    app._local_fetch_elements = lambda _substation_id: [
        {
            "id": 7,
            "name": "Breaker A",
            "element_type": "Διακόπτης ΜΤ",
            "breaker_category": "Vacuum",
            "serial_number": "SN-1",
            "model_manufacturer": "ABB",
            "model_name": "Model X",
            "voltage_level": "20kV",
            "manufacture_year": "2020",
            "operating_status": "Ενεργή",
            "onedrive_manual_link": "https://example/manual",
            "manual_pdf": "",
        }
    ]
    app._has_element_maintenance_history = lambda _element_id: True

    created_buttons = []

    class DummyIconButton(android_app.BoxLayout):
        def __init__(self, icon_type):
            super().__init__()
            self.icon_type = icon_type
            self.bind_calls = 0

        def bind(self, **_kwargs):
            self.bind_calls += 1
            return None

    def _fake_build_vector_icon_button(
        icon_type, on_press, icon_color=None, size=(34, 34)
    ):
        button = DummyIconButton(icon_type)
        created_buttons.append(button)
        return button

    monkeypatch.setattr(
        app, "_build_vector_icon_button", _fake_build_vector_icon_button
    )

    grid = android_app.GridLayout(cols=1)

    app._load_substation_elements(1, grid)

    assert [button.icon_type for button in created_buttons] == ["book", "maintenance"]
    assert all(button.bind_calls == 0 for button in created_buttons)
    assert len(_collect_widgets_by_class_name(grid, "DummyIconButton")) == 2


def test_show_maintenance_menu_uses_save_and_cancel_text_fallback(monkeypatch):
    captured = {}

    class DummyPopup:
        def __init__(self, title=None, size_hint=None):
            self.title = title
            self.size_hint = size_hint
            self.content = None
            captured["instance"] = self

        def open(self):
            pass

        def dismiss(self):
            pass

    monkeypatch.setattr(android_app, "Popup", DummyPopup)
    monkeypatch.setattr(
        android_app,
        "S",
        {
            "BUTTONS": {},
            "MESSAGES": {},
            "TITLES": {},
        },
    )
    monkeypatch.setattr(
        android_app,
        "Clock",
        types.SimpleNamespace(schedule_once=lambda callback, _dt=0: callback(0)),
    )

    app = android_app.SubstationAndroidApp()
    app.data_mode = "local"
    app._local_fetch_elements = lambda _substation_id: [
        {
            "id": 1,
            "name": "Breaker A",
            "element_type": "Διακόπτης ΜΤ",
            "breaker_category": "Vacuum",
            "serial_number": "SN-1",
            "model_manufacturer": "ABB",
            "model_name": "Model X",
            "voltage_level": "20kV",
            "manufacture_year": "2020",
            "operating_status": "Ενεργή",
        }
    ]

    app.show_maintenance_menu(1, {"name": "S1"})

    texts = _collect_widget_texts(captured["instance"].content)
    assert "Αποθήκευση" in texts
    assert "Άκυρο" in texts


def test_show_inspection_entry_popup_uses_save_and_cancel_text_fallback(monkeypatch):
    captured = {}

    class DummyPopup:
        def __init__(self, title=None, size_hint=None):
            self.title = title
            self.size_hint = size_hint
            self.content = None
            captured["instance"] = self

        def open(self):
            pass

        def dismiss(self):
            pass

    monkeypatch.setattr(android_app, "Popup", DummyPopup)
    monkeypatch.setattr(
        android_app,
        "S",
        {
            "BUTTONS": {},
            "MESSAGES": {},
            "TITLES": {},
        },
    )

    app = android_app.SubstationAndroidApp()

    app.show_inspection_entry_popup(1, {"name": "S1"})

    texts = _collect_widget_texts(captured["instance"].content)
    assert "Αποθήκευση" in texts
    assert "Άκυρο" in texts


def test_show_inspection_entry_popup_matches_desktop_form_structure(monkeypatch):
    captured = {}

    class DummyPopup:
        def __init__(self, title=None, size_hint=None):
            self.title = title
            self.size_hint = size_hint
            self.content = None
            captured["instance"] = self

        def open(self):
            pass

        def dismiss(self):
            pass

    monkeypatch.setattr(android_app, "Popup", DummyPopup)

    app = android_app.SubstationAndroidApp()
    app.substations = [{"id": 1, "name": "S1"}, {"id": 2, "name": "S2"}]

    app.show_inspection_entry_popup(1, {"id": 1, "name": "S1"})

    texts = _collect_widget_texts(captured["instance"].content)
    assert (
        android_app.S.get("MESSAGES", {}).get("SUBSTATION_LABEL", "Υποσταθμός:")
        in texts
    )
    assert android_app.S.get("MESSAGES", {}).get("FORM_NUMBER", "Αρ. Δελτίου:") in texts
    assert android_app.S.get("MESSAGES", {}).get("REGION_LABEL", "Περιοχή:") in texts
    assert (
        android_app.S.get("MESSAGES", {}).get("INSPECTOR_LABEL", "Ονομ. Επιθεωρητή:")
        in texts
    )
    assert android_app.S.get("MESSAGES", {}).get("MONTH_LABEL", "Μήνας:") in texts
    assert android_app.S.get("MESSAGES", {}).get("DAY_LABEL", "Ημέρα:") in texts
    assert android_app.S.get("MESSAGES", {}).get("YEAR_LABEL", "Έτος:") in texts
    assert (
        android_app.S.get("MESSAGES", {}).get(
            "INSPECTION_SECTION_2", "[b]Έλεγχος Χώρων ΥΣ[/b]"
        )
        in texts
    )
    assert (
        android_app.S.get("MESSAGES", {}).get("INSPECTION_SECTION_7", "[b]Απόψεις[/b]")
        in texts
    )
    assert "Ημερομηνία Επιθεώρησης:" not in texts


def test_show_inspection_entry_popup_expands_sections_and_uses_tall_mobile_inputs(
    monkeypatch,
):
    captured = {}

    class DummyPopup:
        def __init__(self, title=None, size_hint=None):
            self.title = title
            self.size_hint = size_hint
            self.content = None
            captured["instance"] = self

        def open(self):
            pass

        def dismiss(self):
            pass

    monkeypatch.setattr(android_app, "Popup", DummyPopup)

    app = android_app.SubstationAndroidApp()
    app.substations = [{"id": 1, "name": "S1"}]

    app.show_inspection_entry_popup(1, {"id": 1, "name": "S1"})

    popup_content = captured["instance"].content
    multiline_inputs = [
        widget
        for widget in _collect_widgets_by_class_name(popup_content, "TextInput")
        if getattr(widget, "multiline", False)
    ]
    assert multiline_inputs
    assert all(widget.height >= 88 for widget in multiline_inputs)

    messages = android_app.S.get("MESSAGES", {})
    first_title = re.sub(
        r"\[/?b\]",
        "",
        messages.get("INSPECTION_SECTION_2", "[b]Έλεγχος Περιοχών Υποσταθμού[/b]"),
    ).strip()
    second_title = re.sub(
        r"\[/?b\]",
        "",
        messages.get(
            "INSPECTION_SECTION_3",
            "[b]Μετασχηματιστής 150/20kV & Διακόπτες ΥΤ/20kV[/b]",
        ),
    ).strip()

    assert _find_widget_by_text(popup_content, f"[-] {first_title}") is not None
    second_header = _find_widget_by_text(popup_content, f"[+] {second_title}")
    assert second_header is not None

    first_section_first_row = messages.get("INSPECTION_ROWS", [])[0]
    assert first_section_first_row in _collect_widget_texts(popup_content)

    second_section_first_row = messages.get("INSPECTION_ROWS", [])[4]
    assert second_section_first_row not in _collect_widget_texts(popup_content)

    second_header.on_press(second_header)

    assert second_header.text == f"[-] {second_title}"
    assert second_section_first_row in _collect_widget_texts(popup_content)
    assert getattr(second_header.parent, "height", 0) > getattr(
        second_header, "height", 0
    )
    assert any(widget.height >= 88 for widget in multiline_inputs)


def test_show_inspection_entry_popup_uses_taller_android_field_heights(monkeypatch):
    captured = {}

    class DummyPopup:
        def __init__(self, title=None, size_hint=None):
            self.title = title
            self.size_hint = size_hint
            self.content = None
            captured["instance"] = self

        def open(self):
            pass

        def dismiss(self):
            pass

    monkeypatch.setattr(android_app, "Popup", DummyPopup)
    monkeypatch.setattr(android_app, "platform", "android")

    app = android_app.SubstationAndroidApp()
    app.substations = [{"id": 1, "name": "S1"}]

    app.show_inspection_entry_popup(1, {"id": 1, "name": "S1"})

    popup_content = captured["instance"].content
    multiline_inputs = [
        widget
        for widget in _collect_widgets_by_class_name(popup_content, "TextInput")
        if getattr(widget, "multiline", False)
    ]
    assert multiline_inputs
    assert all(widget.height >= 156 for widget in multiline_inputs)

    messages = android_app.S.get("MESSAGES", {})
    first_section_first_row = messages.get("INSPECTION_ROWS", [])[0]
    second_section_first_row = messages.get("INSPECTION_ROWS", [])[4]
    texts = _collect_widget_texts(popup_content)
    assert first_section_first_row in texts
    assert second_section_first_row in texts

    first_row_label = _find_widget_by_text(popup_content, first_section_first_row)
    second_row_label = _find_widget_by_text(popup_content, second_section_first_row)
    assert first_row_label is not None
    assert second_row_label is not None
    assert getattr(first_row_label.parent, "height", 0) >= 214
    assert getattr(second_row_label.parent, "height", 0) >= 214

    second_title = re.sub(
        r"\[/?b\]",
        "",
        messages.get(
            "INSPECTION_SECTION_3",
            "[b]Μετασχηματιστής 150/20kV & Διακόπτες ΥΤ/20kV[/b]",
        ),
    ).strip()
    assert any(second_title in str(text) for text in texts)
    assert _find_widget_by_text(popup_content, f"[+] {second_title}") is None
    assert _find_widget_by_text(popup_content, f"[-] {second_title}") is None


def test_show_inspection_entry_popup_does_not_require_inspections_module(monkeypatch):
    captured = {}

    class DummyPopup:
        def __init__(self, title=None, size_hint=None):
            self.title = title
            self.size_hint = size_hint
            self.content = None
            captured["instance"] = self

        def open(self):
            pass

        def dismiss(self):
            pass

    monkeypatch.setattr(android_app, "Popup", DummyPopup)
    monkeypatch.setitem(sys.modules, "inspections", None)

    app = android_app.SubstationAndroidApp()
    app.substations = [{"id": 1, "name": "S1"}]

    app.show_inspection_entry_popup(1, {"id": 1, "name": "S1"})

    texts = _collect_widget_texts(captured["instance"].content)
    assert (
        android_app.S.get("MESSAGES", {}).get("SUBSTATION_LABEL", "Υποσταθμός:")
        in texts
    )


def test_has_element_maintenance_history_ignores_orphan_links(tmp_path):
    db_path = tmp_path / "android_history.db"
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE maintenance (id INTEGER PRIMARY KEY, substation_id INTEGER, date_time TEXT);
        CREATE TABLE maintenance_elements (
            id INTEGER PRIMARY KEY,
            maintenance_id INTEGER,
            element_id INTEGER
        );
        INSERT INTO maintenance_elements (maintenance_id, element_id) VALUES (58, 707);
        INSERT INTO maintenance (id, substation_id, date_time) VALUES (1, 56, '2024-01-01');
        INSERT INTO maintenance_elements (maintenance_id, element_id) VALUES (1, 708);
        """
    )
    conn.commit()
    conn.close()

    app = android_app.SubstationAndroidApp()
    app.local_db_path = str(db_path)

    assert app._has_element_maintenance_history(707) is False
    assert app._has_element_maintenance_history(708) is True


def test_show_substation_details_guards_maintenance_action_errors(monkeypatch):
    app = android_app.SubstationAndroidApp()

    app.substations = [{"id": 1, "name": "Alpha"}]
    app.content_layout = android_app.BoxLayout()

    errors = []
    monkeypatch.setattr(app, "show_error", lambda message: errors.append(message))
    monkeypatch.setattr(app, "_set_root_buttons_visible", lambda *_args: None)
    monkeypatch.setattr(app, "_load_substation_elements", lambda *_args: None)
    monkeypatch.setattr(
        app,
        "show_maintenance_menu",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("maintenance boom")),
    )

    app.show_substation_details(1)
    maint_btn = _find_widget_by_text(
        app.content_layout,
        android_app.S.get("BUTTONS", {}).get("MAINTENANCE", "Συντήρηση"),
    )

    maint_btn.on_press(None)

    assert errors == [
        f"{android_app.S.get('BUTTONS', {}).get('MAINTENANCE', 'Συντήρηση')}: maintenance boom"
    ]


def test_show_substation_details_guards_inspection_action_errors(monkeypatch):
    app = android_app.SubstationAndroidApp()

    app.substations = [{"id": 1, "name": "Alpha"}]
    app.content_layout = android_app.BoxLayout()

    errors = []
    monkeypatch.setattr(app, "show_error", lambda message: errors.append(message))
    monkeypatch.setattr(app, "_set_root_buttons_visible", lambda *_args: None)
    monkeypatch.setattr(app, "_load_substation_elements", lambda *_args: None)
    monkeypatch.setattr(
        app,
        "show_inspection_entry_popup",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("inspection boom")),
    )

    app.show_substation_details(1)
    inspect_btn = _find_widget_by_text(
        app.content_layout,
        android_app.S.get("BUTTONS", {}).get("INSPECT", "Επιθεώρηση"),
    )

    inspect_btn.on_press(None)

    assert errors == [
        f"{android_app.S.get('BUTTONS', {}).get('INSPECT', 'Επιθεώρηση')}: inspection boom"
    ]


def test_build_uses_logo_text_fallback_when_asset_unavailable(monkeypatch):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")
    monkeypatch.setattr(app, "load_substations", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app, "_auto_load_saved_db", lambda: False)
    monkeypatch.setattr(
        android_app,
        "Clock",
        types.SimpleNamespace(schedule_once=lambda callback, _dt=0: None),
    )

    original_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        module = original_import(name, globals, locals, fromlist, level)
        if name == "kivy.resources" and "resource_find" in fromlist:
            module.resource_find = lambda *_args, **_kwargs: None
        return module

    monkeypatch.setattr(android_app.os.path, "exists", lambda _path: False)
    monkeypatch.setattr("builtins.__import__", fake_import)

    root = app.build()

    assert root is not None
    texts = _collect_widget_texts(app.logo_area)
    assert "ΔΕΔΔΗΕ" in texts


def test_build_uses_proportional_main_menu_sections(monkeypatch):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")
    monkeypatch.setattr(app, "load_substations", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app, "_auto_load_saved_db", lambda: False)
    monkeypatch.setattr(
        android_app,
        "Clock",
        types.SimpleNamespace(schedule_once=lambda callback, _dt=0: None),
    )

    app.build()

    assert app.logo_area.size_hint_y == 0.10
    assert app.header_area.size_hint_y == 0.10
    assert app.db_bar.size_hint_y == 0.09
    assert app.content_layout.size_hint_y == 0.53
    assert app.refresh_area.size_hint_y == 0.08
    assert app.actions_area.size_hint_y == 0.10


def test_display_substations_renders_scrollview(monkeypatch):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")
    monkeypatch.setattr(app, "load_substations", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app, "_auto_load_saved_db", lambda: False)
    monkeypatch.setattr(
        android_app,
        "Clock",
        types.SimpleNamespace(schedule_once=lambda callback, _dt=0: None),
    )

    app.build()
    app.substations = [{"id": 1, "name": "TEST"}]

    app.display_substations()

    assert len(app.content_layout.children) == 1
    assert app.content_layout.children[0].__class__.__name__ == "ScrollView"


def test_show_error_uses_internal_popup_when_helper_unavailable(monkeypatch):
    app = android_app.SubstationAndroidApp()

    popup_opened = []
    monkeypatch.setattr(android_app, "show_message_popup", None)
    monkeypatch.setattr(
        android_app,
        "Clock",
        types.SimpleNamespace(schedule_once=lambda callback, _dt=0: callback(0)),
    )

    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "strings_proxy":
            raise ModuleNotFoundError("strings_proxy")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)
    monkeypatch.setattr(
        android_app.Popup,
        "open",
        lambda self: popup_opened.append(getattr(self, "title", None)),
        raising=False,
    )

    app.show_error("boom")

    assert popup_opened == [android_app.S["TITLES"].get("ERROR", "Σφάλμα")]


def test_open_android_document_picker_runs_on_ui_thread(monkeypatch):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")

    selected = []
    errors = []
    launch_calls = []
    bound_callbacks = []
    unbound_callbacks = []

    monkeypatch.setattr(app, "show_error", lambda message: errors.append(message))
    monkeypatch.setattr(
        android_app,
        "Clock",
        types.SimpleNamespace(schedule_once=lambda callback, _dt=0: callback(0)),
    )

    class FakeIntent:
        ACTION_OPEN_DOCUMENT = "ACTION_OPEN_DOCUMENT"
        CATEGORY_OPENABLE = "CATEGORY_OPENABLE"
        FLAG_GRANT_READ_URI_PERMISSION = 1
        FLAG_GRANT_PERSISTABLE_URI_PERMISSION = 2

        def __init__(self, action):
            self.action = action
            self.categories = []
            self.flags = []
            self.mime_type = None

        def addCategory(self, category):
            self.categories.append(category)

        def setType(self, mime_type):
            self.mime_type = mime_type

        def addFlags(self, flag):
            self.flags.append(flag)

    class FakeActivityClass:
        RESULT_OK = 1

    class FakeResolver:
        def __init__(self):
            self.persisted = []

        def takePersistableUriPermission(self, uri, flags):
            self.persisted.append((uri, flags))

    class FakeCurrentActivity:
        def __init__(self):
            self.resolver = FakeResolver()

        def startActivityForResult(self, intent, request_code):
            launch_calls.append((intent, request_code))

        def getContentResolver(self):
            return self.resolver

    current_activity = FakeCurrentActivity()

    class FakePythonActivity:
        mActivity = current_activity

    def fake_autoclass(name):
        mapping = {
            "android.content.Intent": FakeIntent,
            "android.app.Activity": FakeActivityClass,
            "org.kivy.android.PythonActivity": FakePythonActivity,
        }
        return mapping[name]

    android_module = types.ModuleType("android")
    activity_module = types.SimpleNamespace(
        bind=lambda **kwargs: bound_callbacks.append(kwargs["on_activity_result"]),
        unbind=lambda **kwargs: unbound_callbacks.append(kwargs["on_activity_result"]),
    )
    runnable_module = types.ModuleType("android.runnable")
    runnable_module.run_on_ui_thread = lambda func: func
    android_module.activity = activity_module

    monkeypatch.setitem(
        sys.modules, "jnius", types.SimpleNamespace(autoclass=fake_autoclass)
    )
    monkeypatch.setitem(sys.modules, "android", android_module)
    monkeypatch.setitem(sys.modules, "android.runnable", runnable_module)

    app._open_android_document_picker(lambda selection: selected.extend(selection))

    assert len(launch_calls) == 1
    assert launch_calls[0][1] == 61423
    assert app._android_picker_active is True
    assert len(bound_callbacks) == 1
    assert errors == []

    class FakeUri:
        def toString(self):
            return "content://picked/db.sqlite"

    class FakeData:
        def getData(self):
            return FakeUri()

    bound_callbacks[0](61423, FakeActivityClass.RESULT_OK, FakeData())

    assert selected == ["content://picked/db.sqlite"]
    assert unbound_callbacks == [bound_callbacks[0]]
    assert app._android_picker_active is False
    assert app._android_picker_callback is None


def test_open_android_document_picker_calls_cancel_callback(monkeypatch):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")

    canceled = []
    launch_calls = []
    bound_callbacks = []

    monkeypatch.setattr(
        android_app,
        "Clock",
        types.SimpleNamespace(schedule_once=lambda callback, _dt=0: callback(0)),
    )

    class FakeIntent:
        ACTION_OPEN_DOCUMENT = "ACTION_OPEN_DOCUMENT"
        CATEGORY_OPENABLE = "CATEGORY_OPENABLE"

        def __init__(self, action):
            self.action = action

        def addCategory(self, _category):
            return None

        def setType(self, _mime_type):
            return None

        def addFlags(self, _flag):
            return None

    class FakeActivityClass:
        RESULT_OK = 1

    class FakeCurrentActivity:
        def startActivityForResult(self, intent, request_code):
            launch_calls.append((intent, request_code))

    current_activity = FakeCurrentActivity()

    class FakePythonActivity:
        mActivity = current_activity

    def fake_autoclass(name):
        mapping = {
            "android.content.Intent": FakeIntent,
            "android.app.Activity": FakeActivityClass,
            "org.kivy.android.PythonActivity": FakePythonActivity,
        }
        return mapping[name]

    android_module = types.ModuleType("android")
    activity_module = types.SimpleNamespace(
        bind=lambda **kwargs: bound_callbacks.append(kwargs["on_activity_result"]),
        unbind=lambda **_kwargs: None,
    )
    runnable_module = types.ModuleType("android.runnable")
    runnable_module.run_on_ui_thread = lambda func: func
    android_module.activity = activity_module

    monkeypatch.setitem(
        sys.modules, "jnius", types.SimpleNamespace(autoclass=fake_autoclass)
    )
    monkeypatch.setitem(sys.modules, "android", android_module)
    monkeypatch.setitem(sys.modules, "android.runnable", runnable_module)

    app._open_android_document_picker(
        lambda _selection: None, on_cancel=lambda: canceled.append(True)
    )

    assert len(launch_calls) == 1
    bound_callbacks[0](61423, 0, None)

    assert canceled == [True]
    assert app._android_picker_active is False
    assert app._android_picker_callback is None


def test_use_local_mode_shows_error_and_reopens_picker_for_inaccessible_file(
    monkeypatch,
):
    """When a /storage/ file doesn't exist, show an error and reopen the
    Android picker instead of requesting
    permissions that can never be granted on targetSdk 34."""
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")
    monkeypatch.setattr(
        android_app,
        "Clock",
        types.SimpleNamespace(schedule_once=lambda callback, _dt=0: callback(0)),
    )

    prepared = []
    loaded = []
    errors = []
    picker_calls = []

    monkeypatch.setattr(android_app.os.path, "exists", lambda _p: False)
    monkeypatch.setattr(
        app, "_prepare_local_db_path", lambda path: prepared.append(path) or path
    )
    monkeypatch.setattr(app, "_set_saved_db_path", lambda path: None)
    monkeypatch.setattr(app, "_ensure_change_log_path", lambda: None)
    monkeypatch.setattr(app, "load_substations", lambda *_args: loaded.append(True))
    monkeypatch.setattr(
        app,
        "show_error",
        lambda msg, is_info=False: errors.append(msg),
    )
    monkeypatch.setattr(
        app,
        "_open_android_local_db_picker",
        lambda: picker_calls.append(True),
    )

    app.use_local_mode("/storage/emulated/0/Download/substations.db")

    assert prepared == []
    assert loaded == []
    assert len(errors) == 1
    assert picker_calls == [True]


def test_use_local_mode_allows_android_storage_path_with_permissions(monkeypatch):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")

    prepared = []
    loaded = []

    monkeypatch.setattr(app, "_android_storage_permissions_granted", lambda: True)
    monkeypatch.setattr(android_app.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(
        app, "_prepare_local_db_path", lambda path: prepared.append(path) or path
    )
    monkeypatch.setattr(app, "_set_saved_db_path", lambda path: None)
    monkeypatch.setattr(app, "_ensure_change_log_path", lambda: None)
    monkeypatch.setattr(app, "load_substations", lambda *_args: loaded.append(True))

    app.use_local_mode("/storage/emulated/0/Download/substations.db")

    assert prepared == ["/storage/emulated/0/Download/substations.db"]
    assert loaded == [True]


def test_use_local_mode_copies_raw_path_for_content_uri_when_permissions_exist(
    monkeypatch,
):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")

    loaded = []
    copied = []

    monkeypatch.setattr(app, "_android_storage_permissions_granted", lambda: True)
    monkeypatch.setattr(
        app,
        "_resolve_android_content_uri_to_raw_path",
        lambda _uri: "/storage/emulated/0/Download/substations.db",
    )
    monkeypatch.setattr(android_app.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(app, "_set_saved_db_path", lambda path: None)
    monkeypatch.setattr(app, "_ensure_change_log_path", lambda: None)
    monkeypatch.setattr(app, "load_substations", lambda *_args: loaded.append(True))
    monkeypatch.setattr(
        app,
        "_copy_local_db_file_to_private_storage_async",
        lambda path, callback: (
            copied.append(path)
            or callback(True, ("C:/temp/copied_substations.db", ["-wal", "-shm"]))
        ),
    )
    monkeypatch.setattr(
        app, "_copy_content_uri_to_file_async", lambda *_args, **_kwargs: None
    )

    app.use_local_mode("content://picked/substations.db")

    assert copied == ["/storage/emulated/0/Download/substations.db"]
    assert loaded == [True]


def test_use_local_mode_copies_resolved_raw_path_when_available(
    monkeypatch,
):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")

    loaded = []
    copied = []

    monkeypatch.setattr(app, "_android_storage_permissions_granted", lambda: True)
    monkeypatch.setattr(
        app,
        "_resolve_android_content_uri_to_raw_path",
        lambda _uri: "/storage/emulated/0/Download/substations.db",
    )
    monkeypatch.setattr(android_app.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(app, "_set_saved_db_path", lambda path: None)
    monkeypatch.setattr(app, "_ensure_change_log_path", lambda: None)
    monkeypatch.setattr(app, "load_substations", lambda *_args: loaded.append(True))

    def _fake_async_copy(path, on_result):
        copied.append(path)
        on_result(True, ("C:/temp/copied_substations.db", ["-wal"]))

    monkeypatch.setattr(
        app,
        "_copy_local_db_file_to_private_storage_async",
        _fake_async_copy,
    )
    monkeypatch.setattr(app, "_copy_content_uri_to_file_async", lambda *_args: None)

    app.use_local_mode("content://picked/substations.db")

    assert copied == ["/storage/emulated/0/Download/substations.db"]
    assert loaded == [True]


def test_prepare_local_db_path_copies_sidecars_when_raw_open_falls_back(monkeypatch):
    app = android_app.SubstationAndroidApp()

    source_path = "/storage/emulated/0/Download/substations.db"
    copied_sidecars = []
    copied_main = []

    monkeypatch.setattr(android_app.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(
        app, "_clear_local_db_copy_targets", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        android_app.shutil,
        "copy2",
        lambda src, dst: copied_main.append((src, dst)),
    )
    monkeypatch.setattr(
        app,
        "_maybe_copy_android_sqlite_sidecars",
        lambda src, dst: copied_sidecars.append((src, dst)) or ["-wal", "-shm"],
    )

    connect_calls = []

    class FakeConn:
        def close(self):
            return None

    def fake_connect(path, uri=False):
        connect_calls.append((path, uri))
        if len(connect_calls) == 1:
            raise android_app.sqlite3.OperationalError("unable to open database file")
        return FakeConn()

    monkeypatch.setattr(android_app.sqlite3, "connect", fake_connect)
    app.user_data_dir = "C:/temp/user_data"
    monkeypatch.setattr(android_app.os, "makedirs", lambda *_args, **_kwargs: None)

    result = app._prepare_local_db_path(source_path)

    assert result.endswith("substations.db")
    assert copied_main == [(source_path, result)]
    assert copied_sidecars == [(source_path, result)]


def test_on_resume_continues_pending_android_permission_action(monkeypatch):
    app = android_app.SubstationAndroidApp()

    resumed = []
    infos = []

    monkeypatch.setattr(
        android_app,
        "Clock",
        types.SimpleNamespace(schedule_once=lambda callback, _dt=0: callback(0)),
    )
    monkeypatch.setattr(app, "_android_storage_permissions_granted", lambda: True)
    monkeypatch.setattr(
        app, "_show_android_loader_info", lambda message: infos.append(message)
    )

    app._pending_android_permission_action = lambda: resumed.append(True)
    app._android_permission_request_in_flight = True

    assert app.on_resume() is True
    assert resumed == [True]
    assert len(infos) == 1
    assert app._pending_android_permission_action is None
    assert app._android_permission_request_in_flight is False


def test_request_android_storage_permissions_resumes_after_settings_return(monkeypatch):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")
    monkeypatch.setattr(
        android_app,
        "Clock",
        types.SimpleNamespace(schedule_once=lambda callback, _dt=0: callback(0)),
    )

    notices = []
    infos = []
    resumed = []
    permission_state = {"granted": False}
    settings_opened = []

    permissions_module = types.ModuleType("android.permissions")

    class FakePermission:
        READ_EXTERNAL_STORAGE = "read"
        WRITE_EXTERNAL_STORAGE = "write"

    def check_permission(_permission):
        return permission_state["granted"]

    def request_permissions(_permissions):
        return None

    permissions_module.Permission = FakePermission
    permissions_module.check_permission = check_permission
    permissions_module.request_permissions = request_permissions
    monkeypatch.setitem(sys.modules, "android.permissions", permissions_module)
    monkeypatch.setattr(
        app,
        "_request_android_storage_permissions",
        app._request_android_storage_permissions,
    )

    jnius_module = types.ModuleType("jnius")

    class FakeEnvironment:
        @staticmethod
        def isExternalStorageManager():
            return permission_state["granted"]

    class FakeIntent:
        def __init__(self, action):
            self.action = action
            self.data = None

        def setData(self, data):
            self.data = data

    class FakeSettings:
        ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION = "app-all-files"

    class FakeUri:
        @staticmethod
        def parse(value):
            return value

    class FakeActivity:
        def getPackageName(self):
            return "org.dbsubstations.dbsubstations"

        def startActivity(self, intent):
            settings_opened.append((intent.action, intent.data))

    class FakePythonActivity:
        mActivity = FakeActivity()

    def fake_autoclass(name):
        mapping = {
            "android.os.Environment": FakeEnvironment,
            "android.content.Intent": FakeIntent,
            "android.provider.Settings": FakeSettings,
            "android.net.Uri": FakeUri,
            "org.kivy.android.PythonActivity": FakePythonActivity,
        }
        return mapping[name]

    jnius_module.autoclass = fake_autoclass
    monkeypatch.setitem(sys.modules, "jnius", jnius_module)

    runnable_module = types.ModuleType("android.runnable")
    runnable_module.run_on_ui_thread = lambda func: func
    monkeypatch.setitem(sys.modules, "android.runnable", runnable_module)

    monkeypatch.setattr(
        app, "_show_permissions_requested_notice", lambda: notices.append(True)
    )
    monkeypatch.setattr(
        app, "_show_android_loader_info", lambda message: infos.append(message)
    )

    assert (
        app._request_android_storage_permissions(lambda: resumed.append(True)) is False
    )
    assert resumed == []
    assert notices == [True]
    assert len(infos) == 1
    assert app._pending_android_permission_action is not None
    assert app._android_permission_request_in_flight is False
    assert settings_opened == [
        (
            "app-all-files",
            "package:org.dbsubstations.dbsubstations",
        )
    ]

    permission_state["granted"] = True

    assert app.on_resume() is True
    assert resumed == [True]
    assert len(infos) == 2
    assert app._pending_android_permission_action is None


def test_request_android_storage_permissions_accepts_persisted_all_files_access(
    monkeypatch,
):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")
    monkeypatch.setattr(
        android_app,
        "Clock",
        types.SimpleNamespace(schedule_once=lambda callback, _dt=0: callback(0)),
    )

    permissions_module = types.ModuleType("android.permissions")

    class FakePermission:
        READ_EXTERNAL_STORAGE = "read"
        WRITE_EXTERNAL_STORAGE = "write"

    permissions_module.Permission = FakePermission
    permissions_module.check_permission = lambda _permission: False
    permissions_module.request_permissions = lambda _permissions, *_args: None
    monkeypatch.setitem(sys.modules, "android.permissions", permissions_module)

    jnius_module = types.ModuleType("jnius")

    class FakeEnvironment:
        @staticmethod
        def isExternalStorageManager():
            return True

    jnius_module.autoclass = lambda name: {
        "android.os.Environment": FakeEnvironment,
    }[name]
    monkeypatch.setitem(sys.modules, "jnius", jnius_module)

    resumed = []

    assert (
        app._request_android_storage_permissions(lambda: resumed.append(True)) is True
    )
    assert resumed == [True]


def test_on_start_shows_queued_uncaught_errors(monkeypatch):
    app = android_app.SubstationAndroidApp()

    shown = []
    monkeypatch.setattr(
        app,
        "show_error",
        lambda message, is_info=False: shown.append((message, is_info)),
    )

    android_app._PENDING_UNCAUGHT_ERROR_MESSAGES[:] = ["queued android error"]

    assert app.on_start() is True
    assert shown == [("queued android error", False)]
    assert android_app._PENDING_UNCAUGHT_ERROR_MESSAGES == []


def test_global_exception_handler_queues_popup_when_app_unavailable(monkeypatch):
    monkeypatch.setattr(
        android_app, "App", types.SimpleNamespace(get_running_app=lambda: None)
    )
    android_app._PENDING_UNCAUGHT_ERROR_MESSAGES[:] = []

    try:
        raise RuntimeError("boom")
    except RuntimeError:
        exc_type, exc_value, exc_traceback = sys.exc_info()

    android_app._global_exception_handler(exc_type, exc_value, exc_traceback)

    assert len(android_app._PENDING_UNCAUGHT_ERROR_MESSAGES) == 1
    assert "RuntimeError: boom" in android_app._PENDING_UNCAUGHT_ERROR_MESSAGES[0]
    android_app._PENDING_UNCAUGHT_ERROR_MESSAGES[:] = []


def test_get_auto_load_db_path_skips_android_storage_without_permissions(monkeypatch):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")
    monkeypatch.setattr(app, "_android_storage_permissions_granted", lambda: False)
    # File doesn't exist → should return None
    monkeypatch.setattr(android_app.os.path, "exists", lambda _p: False)

    result = app._get_auto_load_db_path("/storage/emulated/0/Download/substations.db")

    assert result is None


def test_get_auto_load_db_path_loads_accessible_file_without_broad_permission(
    monkeypatch,
):
    """If the file happens to exist even without MANAGE_EXTERNAL_STORAGE, load it."""
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")
    monkeypatch.setattr(app, "_android_storage_permissions_granted", lambda: False)
    monkeypatch.setattr(android_app.os.path, "exists", lambda _p: True)

    result = app._get_auto_load_db_path("/storage/emulated/0/Download/substations.db")

    assert result == "/storage/emulated/0/Download/substations.db"


def test_use_local_mode_loads_accessible_file_without_broad_permission(monkeypatch):
    """If the file exists on disk even without MANAGE_EXTERNAL_STORAGE, just load it."""
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")

    prepared = []
    loaded = []

    monkeypatch.setattr(app, "_android_storage_permissions_granted", lambda: False)
    # File IS accessible despite no broad permission
    monkeypatch.setattr(android_app.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(
        app, "_prepare_local_db_path", lambda path: prepared.append(path) or path
    )
    monkeypatch.setattr(app, "_set_saved_db_path", lambda path: None)
    monkeypatch.setattr(app, "_ensure_change_log_path", lambda: None)
    monkeypatch.setattr(app, "load_substations", lambda *_args: loaded.append(True))

    app.use_local_mode("/storage/emulated/0/Download/substations.db")

    assert prepared == ["/storage/emulated/0/Download/substations.db"]
    assert loaded == [True]


def test_on_resume_auto_loads_saved_db_after_permission_grant(monkeypatch):
    """After user grants All-Files-Access in Settings and returns,
    on_resume should try to auto-load the saved DB."""
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")
    monkeypatch.setattr(app, "_android_storage_permissions_granted", lambda: True)

    auto_loaded = []
    monkeypatch.setattr(
        app,
        "_auto_load_saved_db",
        lambda: auto_loaded.append(True) or True,
    )
    # No pending action, no local_db_path loaded yet
    app._pending_android_permission_action = None
    app._android_permission_request_in_flight = False
    app.local_db_path = None

    assert app.on_resume() is True
    assert auto_loaded == [True]
