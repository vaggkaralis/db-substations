import importlib


def test_import_popups_and_has_dialogs():
    mod = importlib.import_module("popups")
    assert hasattr(mod, "show_message_popup")
    assert hasattr(mod, "ask_open_file")
    assert hasattr(mod, "ask_save_file")
