import os
import sys
from unittest.mock import patch

# Ensure project root is on sys.path when running from tests/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from android_app import (  # noqa: E402
    SubstationAndroidApp,
    _build_inspection_fields,
    _configure_kivy_environment,
)
from strings_proxy import STRINGS as S  # noqa: E402


def test_copy_success():
    app = SubstationAndroidApp()
    # Replace methods to avoid Kivy UI interactions
    app._set_saved_db_path = lambda p: print("_set_saved_db_path called with", p)
    called = {"loaded": False}

    def fake_load_substations(_):
        print("fake_load_substations called")
        called["loaded"] = True

    app.load_substations = fake_load_substations

    # Monkeypatch async copy to immediately succeed
    def fake_async(uri, on_result):
        print("fake_async called with", uri)
        on_result(True, "/tmp/copied.db")

    app._copy_content_uri_to_file_async = fake_async

    # Call use_local_mode with content:// URI
    app.use_local_mode("content://com.android.providers.documents/document/1")

    assert called["loaded"]


def test_copy_failure():
    app = SubstationAndroidApp()
    errors = []
    app.show_error = lambda msg: errors.append(msg)

    # Monkeypatch async copy to immediately fail
    def fake_async(uri, on_result):
        print("fake_async called with", uri)
        on_result(False, "simulated copy error")

    app._copy_content_uri_to_file_async = fake_async

    app.use_local_mode("content://com.android.providers.documents/document/1")

    assert any(
        "Αποτυχία ανοίγματος βάσης" in e or "simulated copy error" in e for e in errors
    )


def test_maybe_copy_android_sqlite_sidecars_from_content_uri(monkeypatch, tmp_path):
    app = SubstationAndroidApp()

    source_db = tmp_path / "substations.db"
    source_wal = tmp_path / "substations.db-wal"
    target_db = tmp_path / "copied.db"
    source_db.write_bytes(b"db")
    source_wal.write_bytes(b"wal")
    target_db.write_bytes(b"copy")

    monkeypatch.setattr("android_app.platform", "android")
    monkeypatch.setattr(
        app,
        "_resolve_android_content_uri_to_raw_path",
        lambda _uri: str(source_db),
    )

    copied = app._maybe_copy_android_sqlite_sidecars(
        "content://picked/substations.db", str(target_db)
    )

    assert copied == ["-wal"]
    assert (tmp_path / "copied.db-wal").read_bytes() == b"wal"


def test_maybe_copy_android_sqlite_sidecars_from_document_uri(monkeypatch, tmp_path):
    app = SubstationAndroidApp()
    target_db = tmp_path / "copied.db"
    target_db.write_bytes(b"db")

    monkeypatch.setattr("android_app.platform", "android")
    monkeypatch.setattr(
        app, "_resolve_android_content_uri_to_raw_path", lambda _uri: None
    )

    sidecar_bytes = {
        "content://docs/document/primary:Download/substations.db-wal": b"wal-data",
        "content://docs/document/primary:Download/substations.db-shm": b"shm-data",
    }

    class FakeUri:
        def __init__(self, value):
            self._value = value

        def toString(self):
            return self._value

        def getAuthority(self):
            return "docs"

    class FakeInputStream:
        def __init__(self, payload):
            self._payload = payload
            self._offset = 0

        def read(self, buffer=None):
            if buffer is None:
                if self._offset >= len(self._payload):
                    return -1
                value = self._payload[self._offset]
                self._offset += 1
                return value
            if self._offset >= len(self._payload):
                return -1
            chunk = self._payload[self._offset : self._offset + len(buffer)]
            buffer[: len(chunk)] = chunk
            self._offset += len(chunk)
            return len(chunk)

        def close(self):
            return None

    class FakeResolver:
        def openInputStream(self, uri_obj):
            uri_string = uri_obj.toString()
            if uri_string not in sidecar_bytes:
                raise FileNotFoundError(uri_string)
            return FakeInputStream(sidecar_bytes[uri_string])

    class FakeActivity:
        def getContentResolver(self):
            return FakeResolver()

    class FakePythonActivity:
        mActivity = FakeActivity()

    class FakeDocumentsContract:
        @staticmethod
        def getDocumentId(uri_obj):
            return uri_obj.toString().split("/document/", 1)[1]

        @staticmethod
        def buildDocumentUri(authority, document_id):
            return FakeUri(f"content://{authority}/document/{document_id}")

    class FakeUriClass:
        @staticmethod
        def parse(value):
            return FakeUri(value)

    def fake_autoclass(name):
        mapping = {
            "android.provider.DocumentsContract": FakeDocumentsContract,
            "android.net.Uri": FakeUriClass,
            "org.kivy.android.PythonActivity": FakePythonActivity,
        }
        return mapping[name]

    monkeypatch.setitem(
        sys.modules,
        "jnius",
        type("Jnius", (), {"autoclass": staticmethod(fake_autoclass)}),
    )

    copied = app._maybe_copy_android_sqlite_sidecars(
        "content://docs/document/primary:Download/substations.db", str(target_db)
    )

    assert copied == ["-wal", "-shm"]
    assert (tmp_path / "copied.db-wal").read_bytes() == b"wal-data"
    assert (tmp_path / "copied.db-shm").read_bytes() == b"shm-data"


def test_maybe_copy_android_sqlite_sidecars_falls_back_when_raw_path_inaccessible(
    monkeypatch, tmp_path
):
    app = SubstationAndroidApp()
    target_db = tmp_path / "copied.db"
    target_db.write_bytes(b"db")

    monkeypatch.setattr("android_app.platform", "android")
    monkeypatch.setattr(
        app,
        "_resolve_android_content_uri_to_raw_path",
        lambda _uri: "/storage/emulated/0/Download/substations.db",
    )
    monkeypatch.setattr("android_app.os.path.exists", lambda _path: False)

    fallback_calls = []
    monkeypatch.setattr(
        app,
        "_maybe_copy_android_sqlite_sidecars_from_document_uri",
        lambda source, target: fallback_calls.append((source, target)) or ["-wal"],
    )

    copied = app._maybe_copy_android_sqlite_sidecars(
        "content://docs/document/primary:Download/substations.db", str(target_db)
    )

    assert copied == ["-wal"]
    assert fallback_calls == [
        ("content://docs/document/primary:Download/substations.db", str(target_db))
    ]


def test_clear_local_db_copy_targets_removes_stale_sidecars(tmp_path):
    app = SubstationAndroidApp()
    target_db = tmp_path / "copied.db"
    target_db.write_bytes(b"db")
    (tmp_path / "copied.db-wal").write_bytes(b"wal")
    (tmp_path / "copied.db-shm").write_bytes(b"shm")
    (tmp_path / "copied.db-journal").write_bytes(b"journal")

    app._clear_local_db_copy_targets(str(target_db))

    assert not target_db.exists()
    assert not (tmp_path / "copied.db-wal").exists()
    assert not (tmp_path / "copied.db-shm").exists()
    assert not (tmp_path / "copied.db-journal").exists()


def test_inspect_local_db_reports_substation_count(monkeypatch, tmp_path):
    import sqlite3

    app = SubstationAndroidApp()
    db_path = tmp_path / "substations.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE substations (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("INSERT INTO substations (name) VALUES ('Test')")
    conn.commit()
    conn.close()

    info = app._inspect_local_db(str(db_path))

    assert info["exists"] is True
    assert info["has_substations_table"] is True
    assert info["substations_count"] == 1


def test_auto_load_saved_content_uri_uses_local_mode():
    app = SubstationAndroidApp()
    loaded_paths = []
    app.local_db_path = None
    app._get_saved_db_path = lambda: (
        "content://com.android.providers.documents/document/1"
    )
    app.use_local_mode = lambda path: loaded_paths.append(path)

    assert app._auto_load_saved_db() is True
    assert loaded_paths == ["content://com.android.providers.documents/document/1"]


def test_auto_load_saved_internal_storage_path_normalizes_before_loading():
    app = SubstationAndroidApp()
    loaded_paths = []
    raw_path = "/Internal storage/Download/substations.db"
    normalized_path = "/storage/emulated/0/Download/substations.db"
    app.local_db_path = None
    app._get_saved_db_path = lambda: raw_path
    app.use_local_mode = lambda path: loaded_paths.append(path)

    with patch(
        "android_app.os.path.exists", side_effect=lambda path: path == normalized_path
    ):
        assert app._auto_load_saved_db() is True

    assert loaded_paths == [normalized_path]


def test_configure_kivy_environment_uses_android_private_dir(monkeypatch, tmp_path):
    android_private = tmp_path / "private"
    android_argument = android_private / "app"
    monkeypatch.setenv("ANDROID_PRIVATE", str(android_private))
    monkeypatch.setenv("ANDROID_ARGUMENT", str(android_argument))

    kivy_home = _configure_kivy_environment()

    assert kivy_home == str(android_private / ".kivy")
    assert os.environ["HOME"] == str(android_private)
    assert os.environ["KIVY_HOME"] == str(android_private / ".kivy")
    assert os.path.isdir(android_private / ".kivy" / "icon")
    assert os.path.isdir(android_private / ".kivy" / "logs")


def test_build_inspection_fields_tolerates_missing_rows():
    fields = _build_inspection_fields({"MESSAGES": {"INSPECTION_ROWS": []}})

    section_titles = [field["title"] for field in fields if isinstance(field, dict)]
    assert section_titles == [
        "1. Έλεγχος Χώρων ΥΣ",
        "2. Μ/Σ 150/20kV & Διακόπτες 150kV & 20kV",
        "3α. Υπαίθριες πύλες 20 kV",
        "3β. Πίνακες 20 kV",
        "4. Κτίριο χειρισμών & Τ.Α.Σ.",
        "5. Αποζεύκτες Γραμμών",
        "6. PC ΧΕΙΡΙΣΜΩΝ",
        "7. Απόψεις",
    ]


def test_build_inspection_fields_reads_rows_from_strings_proxy():
    fields = _build_inspection_fields(S)

    plain_fields = [field for field in fields if not isinstance(field, dict)]
    assert plain_fields
    assert len(plain_fields) > 20
    assert any("υποσταθμού" in str(field).lower() for field in plain_fields)


if __name__ == "__main__":
    print("Running content URI success test")
    test_copy_success()
    print("Running content URI failure test")
    test_copy_failure()
    print("Running content URI auto-load test")
    test_auto_load_saved_content_uri_uses_local_mode()
    print("Running internal storage auto-load normalization test")
    test_auto_load_saved_internal_storage_path_normalizes_before_loading()
    print("Done")
