def test_inspection_delegates_call_app_methods(monkeypatch):
    calls = {}

    class DummyApp:
        def show_inspection_menu_popup(self, instance=None):
            calls["menu"] = instance

        def _create_file_import_dialog(self, title, cb):
            calls["import_dialog"] = title
            # simulate calling the callback with a fake path
            cb("/tmp/fake.xlsx")

        def show_inspection_history(self, instance=None):
            calls["history"] = instance

        def show_substation_inspection_history(self, sub_id, sub_name, parent=None):
            calls["sub_history"] = (sub_id, sub_name)

        def show_inspection_details(self, inspection_id):
            calls["details"] = inspection_id

    app = DummyApp()

    from inspections import (
        show_import_inspections_dialog_delegate,
        show_inspection_details_delegate,
        show_inspection_history_delegate,
        show_inspection_menu_popup_delegate,
        show_substation_inspection_history_delegate,
    )

    # Call delegates
    show_inspection_menu_popup_delegate(app, "inst")
    show_import_inspections_dialog_delegate(app, None)
    show_inspection_history_delegate(app, "hinst")
    show_substation_inspection_history_delegate(app, 123, "SubName", None)
    show_inspection_details_delegate(app, 555)

    assert calls["menu"] == "inst"
    assert "import_dialog" in calls
    assert calls["history"] == "hinst"
    assert calls["sub_history"] == (123, "SubName")
    assert calls["details"] == 555


def test_handle_inspection_menu_entry_uses_substation_chooser(monkeypatch):
    import inspections
    import kivy.uix.boxlayout as kivy_boxlayout
    import kivy.uix.button as kivy_button
    import kivy.uix.popup as kivy_popup

    captured = {}

    class DummyButton:
        def __init__(self, text="", **_kwargs):
            self.text = text
            self._callbacks = {}

        def bind(self, **kwargs):
            self._callbacks.update(kwargs)

        def trigger(self, event_name):
            callback = self._callbacks.get(event_name)
            if callback:
                callback(self)

    class DummyBoxLayout:
        def __init__(self, *args, **kwargs):
            self.children = []

        def add_widget(self, widget):
            self.children.append(widget)

    class DummyPopup:
        def __init__(self, title=None, size_hint=None):
            self.title = title
            self.size_hint = size_hint
            self.content = None
            captured["popup"] = self

        def open(self):
            pass

        def dismiss(self):
            captured["dismissed"] = True

    monkeypatch.setattr(kivy_boxlayout, "BoxLayout", DummyBoxLayout)
    monkeypatch.setattr(kivy_button, "Button", DummyButton)
    monkeypatch.setattr(kivy_popup, "Popup", DummyPopup)

    class DummyCursor:
        def execute(self, query):
            captured["query"] = query

        def fetchall(self):
            return [(1, "S1"), (2, "S2")]

    class DummyConn:
        def cursor(self):
            return DummyCursor()

    class DummyApp:
        def __init__(self):
            self.conn = DummyConn()

        def _show_substation_selection_window_with_callback(
            self, parent_popup, substations, on_select, title=""
        ):
            captured["chooser_parent_popup"] = parent_popup
            captured["chooser_substations"] = substations
            captured["chooser_title"] = title
            on_select("S2")

        def show_inspection_entry_popup(
            self,
            instance=None,
            preselected_substation_name=None,
            parent_popup=None,
            prefill_data=None,
        ):
            captured["inspection_args"] = {
                "instance": instance,
                "preselected_substation_name": preselected_substation_name,
                "parent_popup": parent_popup,
                "prefill_data": prefill_data,
            }

        def show_inspection_history(self, instance=None):
            captured["history"] = instance

    app = DummyApp()

    inspections.handle_inspection_menu(app)

    popup = captured["popup"]
    entry_button = None
    for child in popup.content.children:
        for grandchild in getattr(child, "children", []):
            if getattr(grandchild, "text", "") == inspections.S.get("TITLES", {}).get(
                "INSPECTION_ENTRY", "Καταχώρηση Επιθεώρησης"
            ):
                entry_button = grandchild
                break
        if entry_button is not None:
            break

    assert entry_button is not None
    entry_button.trigger("on_press")

    assert captured["chooser_parent_popup"] is None
    assert captured["chooser_substations"] == [(1, "S1"), (2, "S2")]
    assert captured["inspection_args"]["preselected_substation_name"] == "S2"
