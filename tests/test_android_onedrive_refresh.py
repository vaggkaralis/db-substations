import android_app


def test_refresh_from_onedrive_skips_copy_when_source_is_same_path(monkeypatch):
    app = android_app.SubstationAndroidApp()
    app.local_db_path = (
        "/data/user/0/org.dbsubstations.dbsubstations/files/substations.db"
    )

    monkeypatch.setattr(app, "_get_onedrive_source_path", lambda: app.local_db_path)
    monkeypatch.setattr(android_app.os.path, "exists", lambda _path: True)
    monkeypatch.setattr(app, "_normalize_android_storage_path", lambda value: value)
    monkeypatch.setattr(app, "_paths_point_to_same_file", lambda *_args: True)

    monkeypatch.setattr(
        app,
        "_clear_local_db_copy_targets",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("copy targets should not be cleared for same-file refresh")
        ),
    )
    monkeypatch.setattr(
        app,
        "_maybe_copy_android_sqlite_sidecars",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("sidecar copy should not run for same-file refresh")
        ),
    )

    finalized = []
    monkeypatch.setattr(
        app,
        "_finalize_refreshed_local_db",
        lambda target, source: finalized.append((target, source)),
    )

    app._refresh_db_from_onedrive_source()

    assert finalized == [(app.local_db_path, app.local_db_path)]


def test_refresh_from_onedrive_content_uri_skips_replace_when_async_copy_matches_target(
    monkeypatch,
):
    app = android_app.SubstationAndroidApp()
    app.local_db_path = (
        "/data/user/0/org.dbsubstations.dbsubstations/files/substations.db"
    )
    source_uri = "content://onedrive/substations.db"

    monkeypatch.setattr(app, "_paths_point_to_same_file", lambda *_args: True)

    monkeypatch.setattr(
        app,
        "_clear_local_db_copy_targets",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("copy targets should not be cleared for same-file refresh")
        ),
    )

    finalized = []
    monkeypatch.setattr(
        app,
        "_finalize_refreshed_local_db",
        lambda target, source: finalized.append((target, source)),
    )

    monkeypatch.setattr(
        app,
        "_copy_content_uri_to_file_async",
        lambda _uri, callback: callback(True, app.local_db_path),
    )

    app._refresh_db_from_onedrive_source(source_uri)

    assert finalized == [(app.local_db_path, source_uri)]
