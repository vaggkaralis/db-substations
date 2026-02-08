import sys
import os

# Ensure project root is on sys.path when running from tests/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from android_app import SubstationAndroidApp


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


if __name__ == "__main__":
    print("Running content URI success test")
    test_copy_success()
    print("Running content URI failure test")
    test_copy_failure()
    print("Done")
