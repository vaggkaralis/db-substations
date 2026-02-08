import android_app


def test_show_change_log_menu_popup(monkeypatch, tmp_path):
    captured = {}

    class DummyPopup:
        def __init__(self, title=None, size_hint=None):
            self.title = title
            self.size_hint = size_hint
            self.content = None
            captured["instance"] = self

        def open(self):
            pass

    # monkeypatch Popup used inside android_app module
    monkeypatch.setattr(android_app, "Popup", DummyPopup)

    app = android_app.SubstationAndroidApp()
    app.user_data_dir = str(tmp_path)
    app.change_log_path = None
    app._ensure_change_log_path()

    app.show_change_log_menu()
    popup = captured.get("instance")
    assert popup is not None
    # popup.content should be a layout with a child BoxLayout containing two Buttons
    children = getattr(popup.content, "children", [])
    assert len(children) >= 1
    btns = []
    for c in children:
        for g in getattr(c, "children", []):
            if hasattr(g, "text"):
                btns.append(g.text)
    assert any("Κοινοποίηση" in t for t in btns)
    assert any("Άνοιγμα" in t for t in btns)
