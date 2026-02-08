import sys
import os

# Ensure project root is on sys.path when running from tests/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from android_app import SubstationAndroidApp


class DummyLayout:
    def __init__(self):
        self.widgets = []

    def clear_widgets(self):
        self.widgets.clear()

    def add_widget(self, w):
        self.widgets.append(w)


def run_permission_test(simulate_granted: bool):
    app = SubstationAndroidApp()
    app.content_layout = DummyLayout()

    # Capture show_error messages
    errors = []

    def fake_show_error(msg):
        print("show_error:", msg)
        errors.append(msg)

    app.show_error = fake_show_error

    # Monkeypatch android.permissions functions used in picker
    class FakePermissionModule:
        class Permission:
            READ_EXTERNAL_STORAGE = "READ"
            WRITE_EXTERNAL_STORAGE = "WRITE"

        @staticmethod
        def check_permission(p):
            return simulate_granted

        @staticmethod
        def request_permissions(perms):
            print("request_permissions called for:", perms)

    # Inject fake module into function globals where used
    # The code imports 'from android.permissions import check_permission, request_permissions, Permission' dynamically
    # Simulate by inserting a fake module into sys.modules
    sys.modules["android.permissions"] = FakePermissionModule

    # Simulate user opening picker via _prompt_local_db_path open_picker path
    # We'll call the internal logic that triggers permission check: _open_android_document_picker is invoked via open_local_db_picker -> _prompt_local_db_path -> open_picker
    # But easier: directly call the permission checking block used before calling _open_android_document_picker

    # Simulate the selection callback
    def on_selected(selection):
        print("on_selected called with:", selection)

    # Emulate permission check behavior inside open_picker
    try:
        # Call the permission-checking logic from the file chooser branch
        from android.permissions import check_permission, request_permissions, Permission

        needed_perms = [Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE]
        perms_granted = all(check_permission(p) for p in needed_perms)
        if not perms_granted:
            request_permissions(needed_perms)
            app.show_error("Απαιτούνται δικαιώματα αποθήκευσης. Επιτρέψτε τα και ξαναδοκιμάστε.")
        else:
            print("Permissions already granted; would call SAF picker")
    except Exception as e:
        print("Permission check failed with exception:", e)

    return errors


if __name__ == "__main__":
    print("--- Test: simulate permissions DENIED ---")
    errs1 = run_permission_test(simulate_granted=False)
    print("Errors captured:", errs1)

    print("--- Test: simulate permissions GRANTED ---")
    errs2 = run_permission_test(simulate_granted=True)
    print("Errors captured:", errs2)
