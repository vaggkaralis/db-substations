import importlib


def test_import_popups_and_has_dialogs():
    mod = importlib.import_module("popups")
    assert hasattr(mod, "show_message_popup")
    assert hasattr(mod, "ask_open_file")
    assert hasattr(mod, "ask_save_file")


def test_custom_app_icon_resolution_is_disabled():
    mod = importlib.import_module("popups")
    assert mod._resolve_app_icon_path() == ""

    db_run = importlib.import_module("DBrun")
    app = db_run.SubstationApp()
    assert app._resolve_app_icon_path() == ""
