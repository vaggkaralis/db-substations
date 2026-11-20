import gc
import importlib
import os
import time
import types


def test_import_popups_and_has_dialogs():
    mod = importlib.import_module("popups")
    assert hasattr(mod, "show_message_popup")
    assert hasattr(mod, "ask_open_file")
    assert hasattr(mod, "ask_save_file")


def test_custom_app_icon_resolution_is_canonical_ico():
    mod = importlib.import_module("popups")
    popup_icon = mod._resolve_app_icon_path()

    db_run = importlib.import_module("DBrun")
    app = db_run.SubstationApp()
    app_icon = app._resolve_app_icon_path()

    for icon_path in (popup_icon, app_icon):
        if not icon_path:
            continue
        assert icon_path.lower().endswith(".ico")
        assert os.path.isfile(icon_path)


def test_popup_content_detaches_before_deferred_cleanup(monkeypatch):
    db_run = importlib.import_module("DBrun")
    scheduled = []

    class _Clock:
        @staticmethod
        def schedule_once(callback, delay):
            scheduled.append((callback, delay))

    class _Content:
        def __init__(self):
            self.cleared = False

        def clear_widgets(self, do_unbind=False):
            self.cleared = True

    monkeypatch.setattr(db_run, "Clock", _Clock)
    app = db_run.SubstationApp.__new__(db_run.SubstationApp)
    app._last_popup_gc_ts = time.monotonic()
    content = _Content()
    popup = types.SimpleNamespace(content=content)

    app._release_popup_content(popup, deep=False, defer=True)

    assert popup.content is None
    assert content.cleared is False
    assert scheduled

    scheduled[0][0](0)
    assert content.cleared is True


def test_child_window_shutdown_skips_process_heavy_cleanup(monkeypatch):
    db_run = importlib.import_module("DBrun")
    popups = importlib.import_module("popups")
    events = []

    class _Connection:
        def close(self):
            events.append("db-close")

    class _Event:
        def cancel(self):
            events.append("cancel")

    app = db_run.SubstationApp.__new__(db_run.SubstationApp)
    app._launch_screen_name = "substations_view"
    app._issue_a_diag_enabled = False
    app._cleanup_completed = False
    app._periodic_sync_event = _Event()
    app._parent_watch_event = None
    app._window_icon_watch_event = None
    app.conn = _Connection()
    app._export_pending_changes = lambda *, show_popup: events.append(
        ("export", show_popup)
    )

    monkeypatch.setattr(
        popups,
        "terminate_launched_child_processes",
        lambda: events.append("terminate-children"),
    )
    monkeypatch.setattr(gc, "collect", lambda *args: events.append(("gc", args)))

    app._cleanup_before_exit()

    assert ("export", False) in events
    assert "db-close" in events
    assert "terminate-children" not in events
    assert not any(isinstance(event, tuple) and event[0] == "gc" for event in events)
