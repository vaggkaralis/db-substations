import os

import DBrun


def test_finish_build_shows_setup_before_integrity(monkeypatch):
    app = DBrun.SubstationApp()
    calls = []

    monkeypatch.setattr(app, "_needs_first_time_setup", lambda: True)
    monkeypatch.setattr(
        app,
        "_show_first_use_setup_wizard",
        lambda on_complete=None: calls.append("wizard"),
    )
    monkeypatch.setattr(
        app,
        "_check_db_compatibility",
        lambda: calls.append("compatibility") or True,
    )
    monkeypatch.setattr(
        app,
        "_check_db_integrity",
        lambda: calls.append("integrity") or True,
    )
    monkeypatch.setattr(
        app,
        "show_login_popup",
        lambda on_login_success=None: calls.append("login"),
    )

    app._finish_build()

    assert calls == ["wizard"]


def test_check_db_integrity_skips_when_db_missing(monkeypatch, tmp_path):
    app = DBrun.SubstationApp()
    missing_db = tmp_path / "substations.db"

    monkeypatch.setattr(app, "_resolve_startup_db_path", lambda: str(missing_db))

    def _unexpected_check(_db_path, quick_check=False):
        raise AssertionError("Integrity check should not run for missing database path")

    monkeypatch.setattr(DBrun, "check_database_integrity", _unexpected_check)

    assert app._check_db_integrity() is True


def test_resolve_startup_db_path_falls_back_to_runtime_default(monkeypatch, tmp_path):
    app = DBrun.SubstationApp()

    runtime_default = tmp_path / "substations.db"
    runtime_default.write_text("sqlite", encoding="utf-8")

    configured_missing = tmp_path / "other-machine" / "substations.db"

    monkeypatch.setattr(DBrun, "DB_PATH", str(runtime_default))
    monkeypatch.setattr(DBrun, "get_db_path", lambda: str(configured_missing))

    saved_paths = []
    monkeypatch.setattr(DBrun, "set_db_path", lambda value: saved_paths.append(value))

    resolved = app._resolve_startup_db_path()

    assert resolved == os.path.abspath(str(runtime_default))
    assert saved_paths == [os.path.abspath(str(runtime_default))]
