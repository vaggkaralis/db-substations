import sys

from android_app import SubstationAndroidApp


def test_open_change_log_folder_fallback_copies_path(monkeypatch, tmp_path):
    app = SubstationAndroidApp()
    app.user_data_dir = str(tmp_path)
    app.change_log_path = None
    # create dummy change_log file
    app._ensure_change_log_path()
    path = app.change_log_path
    with open(path, "w", encoding="utf-8") as f:
        f.write("ok")

    # remove jnius to force fallback
    monkeypatch.setitem(sys.modules, "jnius", None)

    class DummyClipboard:
        copied = None

        @staticmethod
        def copy(v):
            DummyClipboard.copied = v

    monkeypatch.setitem(sys.modules, "kivy.core.clipboard", DummyClipboard)

    app._open_change_log_folder()
    assert DummyClipboard.copied == path
