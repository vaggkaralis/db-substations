import importlib
import sys
import types


def test_import_model_management_and_has_api():
    mod = importlib.import_module("model_management")
    assert hasattr(mod, "show_models_management")
    assert hasattr(mod, "show_subelement_management_popup")


def test_active_model_usage_count_filters_inactive_rows():
    mod = importlib.import_module("model_management")

    class Cursor:
        def __init__(self):
            self.query = None

        def execute(self, query, params=None):
            self.query = query
            self.params = params
            return None

        def fetchone(self):
            return (2,) if "COUNT(*)" in self.query else (None,)

    cursor = Cursor()
    count = mod._count_active_model_usage(cursor, 123)

    assert count == 2
    assert "operating_status" in cursor.query
    assert "Ανενεργή" in cursor.query


def test_post_save_navigation_uses_subelement_menu_for_subelement_category(monkeypatch):
    mod = importlib.import_module("model_management")

    calls = []

    app = type(
        "App",
        (),
        {"TRANSFORMER_SUBELEMENT_TYPES": ["OLTC", "Bushing"]},
    )()

    monkeypatch.setattr(
        mod,
        "show_models_management",
        lambda app_instance, *args, **kwargs: calls.append(("models", app_instance)),
    )
    monkeypatch.setattr(
        mod,
        "show_subelement_management_popup",
        lambda app_instance, parent_popup=None: calls.append(
            ("subelements", app_instance, parent_popup)
        ),
    )

    callback = mod._get_post_save_model_management_callback(app, "OLTC", "parent")
    callback()

    assert calls == [("subelements", app, "parent")]


def test_delete_model_returns_to_subelement_menu_for_subelement_category(monkeypatch):
    mod = importlib.import_module("model_management")

    calls = []

    app = type(
        "App",
        (),
        {
            "TRANSFORMER_SUBELEMENT_TYPES": ["OLTC", "Bushing"],
            "conn": type(
                "Conn", (), {"cursor": lambda self: None, "commit": lambda self: None}
            )(),
        },
    )()

    class Cursor:
        def execute(self, query, params=None):
            self.query = query
            self.params = params
            return None

        def fetchone(self):
            if "element_model_id" in self.query and "operating_status" in self.query:
                return (0,)
            if "SELECT element_category FROM element_models WHERE id" in self.query:
                return ("OLTC",)
            return (None,)

    app.conn.cursor = lambda: Cursor()

    reports_stub = types.ModuleType("reports")
    reports_stub.show_confirm = lambda *args, **kwargs: kwargs["yes_callback"]()
    monkeypatch.setitem(sys.modules, "reports", reports_stub)

    popups_stub = types.ModuleType("popups")
    popups_stub.show_message_popup = lambda *args, **kwargs: calls.append(
        ("message", args, kwargs)
    )
    monkeypatch.setitem(sys.modules, "popups", popups_stub)

    parent_popup = type(
        "ParentPopup",
        (),
        {"dismiss": lambda self: calls.append(("dismiss", self))},
    )()

    monkeypatch.setattr(
        mod,
        "show_models_management",
        lambda app_instance, *args, **kwargs: calls.append(("models", app_instance)),
    )
    monkeypatch.setattr(
        mod,
        "show_subelement_management_popup",
        lambda app_instance, parent_popup=None: calls.append(
            ("subelements", app_instance, parent_popup)
        ),
    )

    mod.delete_model(app, 99, parent_popup)

    message_call = calls[-1]
    assert message_call[0] == "message"
    callback = message_call[2]["callback"]
    callback()
    assert calls[-1] == ("subelements", app, parent_popup)
