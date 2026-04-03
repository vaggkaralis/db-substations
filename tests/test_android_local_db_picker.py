import sys
import types

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
