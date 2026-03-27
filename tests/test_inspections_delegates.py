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
