import android_app


def _collect_widget_texts(widget):
    texts = []
    if hasattr(widget, "text"):
        texts.append(widget.text)
    for child in getattr(widget, "children", []):
        texts.extend(_collect_widget_texts(child))
    return texts


def test_open_local_db_picker_uses_android_direct_flow(monkeypatch):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")

    opened = []
    monkeypatch.setattr(
        app, "_open_android_local_db_picker", lambda: opened.append(True)
    )
    monkeypatch.setattr(
        app,
        "_prompt_local_db_path",
        lambda: (_ for _ in ()).throw(
            AssertionError("desktop popup should not open on android")
        ),
    )

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

    expected = android_app.S.get("MESSAGES", {}).get("MODE_LABEL_LOCAL", "Τοπική Βάση")
    assert app.local_db_btn.text == expected

    texts = _collect_widget_texts(root)
    assert expected in texts
