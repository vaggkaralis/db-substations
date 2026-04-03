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


def test_open_local_db_picker_uses_android_popup_flow(monkeypatch):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")

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


def test_use_local_mode_requests_permissions_for_android_storage_path(monkeypatch):
    app = android_app.SubstationAndroidApp()

    monkeypatch.setattr(android_app, "platform", "android")

    permission_requests = []
    prepared = []
    loaded = []

    monkeypatch.setattr(
        app,
        "_request_android_storage_permissions",
        lambda on_granted=None: permission_requests.append(on_granted) or False,
    )
    monkeypatch.setattr(
        app, "_prepare_local_db_path", lambda path: prepared.append(path) or path
    )
    monkeypatch.setattr(app, "_set_saved_db_path", lambda path: None)
    monkeypatch.setattr(app, "_ensure_change_log_path", lambda: None)
    monkeypatch.setattr(app, "load_substations", lambda *_args: loaded.append(True))

    app.use_local_mode("/storage/emulated/0/Download/substations.db")

    assert len(permission_requests) == 1
    assert prepared == []
    assert loaded == []

    permission_requests[0]()

    assert prepared == ["/storage/emulated/0/Download/substations.db"]
    assert loaded == [True]


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

    permission_state["granted"] = True

    assert app.on_resume() is True
    assert resumed == [True]
    assert len(infos) == 2
    assert app._pending_android_permission_action is None
