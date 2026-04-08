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
    assert popup.size_hint == (0.95, 0.52)
    # popup.content should be a layout with a child BoxLayout containing two Buttons
    children = getattr(popup.content, "children", [])
    assert len(children) >= 1
    btns = []
    for c in children:
        for g in getattr(c, "children", []):
            if hasattr(g, "text"):
                btns.append(g.text)
    assert any("Κοινοποίηση" in t for t in btns)
    assert any("Αντιγραφή" in t for t in btns)
    assert any("Σύνοψη" in t for t in btns)
    assert any("Καθαρισμός" in t for t in btns)
    assert not any("Άνοιγμα" in t for t in btns)


def test_clear_change_log_empties_file(tmp_path):
    app = android_app.SubstationAndroidApp()
    app.user_data_dir = str(tmp_path)
    app.change_log_path = None
    app._ensure_change_log_path()

    with open(app.change_log_path, "w", encoding="utf-8") as handle:
        handle.write('{"operation": "insert"}\n')

    messages = []
    app.show_error = lambda text, is_info=False: messages.append((text, is_info))

    app._clear_change_log()

    with open(app.change_log_path, "r", encoding="utf-8") as handle:
        assert handle.read() == ""

    assert messages
    assert messages[-1][1] is True


def test_change_log_summary_ignores_short_ok_notes(tmp_path):
    app = android_app.SubstationAndroidApp()
    app.user_data_dir = str(tmp_path)
    app.change_log_path = None
    app._ensure_change_log_path()

    with open(app.change_log_path, "w", encoding="utf-8") as handle:
        handle.write(
            '{"operation": "insert", "table": "inspections", "data": {'
            '"substation_name": "Υ/Σ TEST", '
            '"inspection_date": "2026-04-08", '
            '"fields": {'
            '"Οπτικός έλεγχος": "ok", '
            '"Θερμοκρασία": "done", '
            '"Παρατήρηση": "Leak detected at MV panel and needs follow-up"'
            "}}}\n"
        )

    summary = app._build_change_log_summary_text()

    assert "Υ/Σ TEST" in summary
    assert "Leak detected" in summary
    assert "ok" not in summary.lower()
    assert "done" not in summary.lower()


def test_startup_change_log_review_wraps_clear_button(monkeypatch, tmp_path):
    captured = {}

    class DummyPopup:
        def __init__(self, title=None, size_hint=None, auto_dismiss=True):
            self.title = title
            self.size_hint = size_hint
            self.auto_dismiss = auto_dismiss
            self.content = None
            captured["instance"] = self

        def open(self):
            pass

        def dismiss(self):
            pass

    monkeypatch.setattr(android_app, "Popup", DummyPopup)

    app = android_app.SubstationAndroidApp()
    app.user_data_dir = str(tmp_path)
    app.change_log_path = None
    app._ensure_change_log_path()
    with open(app.change_log_path, "w", encoding="utf-8") as handle:
        handle.write(
            '{"operation": "insert", "table": "substations", "data": {"name": "S1"}}\n'
        )

    assert app._prompt_change_log_review_if_needed(trigger="startup") is True

    popup = captured["instance"]
    texts = []
    for child in getattr(popup.content, "children", []):
        for grand in getattr(child, "children", []):
            if hasattr(grand, "text"):
                texts.append(grand.text)

    assert any("Καθαρισμός\nchange log" in text for text in texts)
