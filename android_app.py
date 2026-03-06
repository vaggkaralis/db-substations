"""
Android Kivy App for DB Substations with OneDrive sync support.

Features:
- Local SQLite database management
- Auto-sync with OneDrive on app startup
- Manual sync button for on-demand synchronization
- Conflict resolution UI
- Backup management
"""

import json
import os
import shutil
import sqlite3
import sys
import threading
import traceback
from datetime import datetime

# Set up logging FIRST before any other imports
from kivy.logger import Logger

Logger.info("APP: ========== Starting DB Substations App ==========")
Logger.info(f"APP: Python version: {sys.version}")

try:
    from settings import ANDROID_DEFAULT_DB_PATH
except Exception:
    ANDROID_DEFAULT_DB_PATH = "/storage/emulated/0/Download/substations.db"

try:
    from strings_proxy import STRINGS as S
except Exception:
    S = {"BUTTONS": {}, "TITLES": {}, "MESSAGES": {}}


# Global exception handler to catch any uncaught exceptions
def _global_exception_handler(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    Logger.critical(f"APP: Uncaught exception: {exc_value}")
    Logger.critical(
        "APP: Traceback: "
        + "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    )
    try:
        from kivy.app import App

        app = App.get_running_app()
        if app and hasattr(app, "show_error"):
            app.show_error(f"Uncaught error: {exc_value}")
    except Exception:
        pass


sys.excepthook = _global_exception_handler

try:
    import importlib

    import kivy

    Logger.info(f"APP: Kivy version: {kivy.__version__}")
    kivy.require("2.3.0")  # Minimum version with Android Cython modules

    # Dynamic Kivy imports to avoid static imports after executable code
    App = importlib.import_module("kivy.app").App
    BoxLayout = importlib.import_module("kivy.uix.boxlayout").BoxLayout
    GridLayout = importlib.import_module("kivy.uix.gridlayout").GridLayout
    Button = importlib.import_module("kivy.uix.button").Button
    Label = importlib.import_module("kivy.uix.label").Label
    from popups import show_message_popup
    TextInput = importlib.import_module("kivy.uix.textinput").TextInput
    Popup = importlib.import_module("kivy.uix.popup").Popup
    ScrollView = importlib.import_module("kivy.uix.scrollview").ScrollView
    Spinner = importlib.import_module("kivy.uix.spinner").Spinner
    Clock = importlib.import_module("kivy.clock").Clock
    platform = importlib.import_module("kivy.utils").platform
except Exception as e:
    Logger.warning(f"APP: Kivy import failed: {str(e)}")
    platform = "unknown"

# Android-specific imports
filechooser = None
FileChooserListView = None
try:
    from plyer import filechooser
except Exception as e:
    Logger.warning(f"APP: plyer.filechooser import failed: {str(e)}")
    filechooser = None
try:
    from kivy.uix.filechooser import FileChooserListView
except Exception as e:
    Logger.warning(f"APP: FileChooserListView import failed: {str(e)}")
    FileChooserListView = None

Logger.info("APP: JSON import successful")

Logger.info("APP: Threading import successful")


class SubstationAndroidApp(App):
    # Use centralized lists from strings module; keep safe fallbacks
    ELEMENT_TYPES = S.get("MESSAGES", {}).get(
        "ELEMENT_TYPES",
        [
            "Διακόπτης ΥΤ",
            "Διακόπτης ΜΤ",
            "Μετασχηματιστής 150/20KV",
            "Motor Drive",
            "Μ/Σ Εγχύσεως",
            "Μ/Σ Έντασης",
            "Μ/Σ Τάσης",
            "Μ/Σ ΧΤ/ΜΤ (ΒΜΣ)",
            "Αποζεύκτης",
            "Ασφαλειοαποζεύκτης",
            "Γειωτής",
            "Συστοιχία Πυκνωτών",
            "Αντίσταση Κόμβου",
            "Αλεξικέραυνο",
            "Συστοιχία Συσσωρευτών",
        ],
    )

    VOLTAGE_LEVELS = S.get("MESSAGES", {}).get("VOLTAGE_LEVELS", ["20 KV", "150 KV", "20/150 KV"])
    OPERATING_STATUS = S.get("MESSAGES", {}).get("OPERATING_STATUS", ["Ενεργή", "Ανενεργή"])
    INSTALLATION_SPACE = S.get("MESSAGES", {}).get("INSTALLATION_SPACE", ["Εσωτερικός", "Εξωτερικός"])
    ELEMENT_FIELD_DEFS = [
        {
            "key": "name",
            "label": S.get("MESSAGES", {}).get("ELEMENT_NAME_LABEL", "Όνομα Στοιχείου"),
            "type": "text",
            "hint": S.get("MESSAGES", {}).get("ELEMENT_NAME_HINT", "Όνομα Στοιχείου"),
        },
        {
            "key": "serial_number",
            "label": S.get("MESSAGES", {}).get("SERIAL_NUMBER_LABEL", "Σειριακός Αριθμός"),
            "type": "text",
            "hint": S.get("MESSAGES", {}).get("SERIAL_NUMBER_HINT", "Σειριακός Αριθμός"),
        },
        {
            "key": "maintenance_date",
            "label": S.get("MESSAGES", {}).get("MAINTENANCE_DATE_LABEL", "Τελευταία Συντ."),
            "type": "text",
            "hint": S.get("MESSAGES", {}).get("MAINTENANCE_DATE_HINT", "YYYY-MM-DD"),
        },
        {
            "key": "voltage_level",
            "label": S.get("MESSAGES", {}).get("INSTALLATION_SPACE_LABEL", "Επίπεδο Τάσης"),
            "type": "text",
            "hint": S.get("MESSAGES", {}).get("VOLTAGE_LEVELS_HINT", "π.χ. 20 KV, 150 KV"),
        },
        {
            "key": "manufacturer",
            "label": S.get("MESSAGES", {}).get("MANUFACTURER_LABEL", "Κατασκευαστής"),
            "type": "text",
            "hint": S.get("MESSAGES", {}).get("MANUFACTURER_HINT", "Κατασκευαστής"),
        },
        {"key": "type", "label": S.get("MESSAGES", {}).get("TYPE_LABEL", "Τύπος"), "type": "text", "hint": S.get("MESSAGES", {}).get("TYPE_HINT", "Τύπος")},
        {
            "key": "manufacture_year",
            "label": S.get("MESSAGES", {}).get("ELEMENT_MANUFACTURE_YEAR_LABEL", "Έτος κατασκευής"),
            "type": "text",
            "hint": S.get("MESSAGES", {}).get("ELEMENT_MANUFACTURE_YEAR_HINT", "YYYY"),
        },
        {"key": "model", "label": S.get("MESSAGES", {}).get("MODEL_LABEL", "Μοντέλο"), "type": "text", "hint": S.get("MESSAGES", {}).get("MODEL_HINT", "Μοντέλο")},
        {
            "key": "model_version",
            "label": S.get("MESSAGES", {}).get("MODEL_VERSION_LABEL", "Έκδοση Μοντέλου"),
            "type": "text",
            "hint": S.get("MESSAGES", {}).get("MODEL_VERSION_HINT", "Έκδοση"),
        },
        {
            "key": "operating_status",
            "label": S.get("MESSAGES", {}).get("OPERATING_STATUS_LABEL", "Κατάσταση Λειτουργίας"),
            "type": "spinner",
            "values": OPERATING_STATUS,
        },
        {
            "key": "installation_space",
            "label": S.get("MESSAGES", {}).get("INSTALLATION_SPACE_LABEL", "Χώρος Εγκατάστασης"),
            "type": "spinner",
            "values": INSTALLATION_SPACE,
        },
        {
            "key": "maintenance_cycle",
            "label": S.get("MESSAGES", {}).get("MAINTENANCE_CYCLE_LABEL", "Κύκλος Συντήρησης (μήνες)"),
            "type": "text",
            "hint": S.get("MESSAGES", {}).get("MAINTENANCE_CYCLE_HINT", "π.χ. 12"),
        },
        {"key": "gate", "label": S.get("MESSAGES", {}).get("GATES", "Πύλη"), "type": "text", "hint": S.get("MESSAGES", {}).get("GATE_HINT", "π.χ. ΠΥΛΗ 1")},
    ]
    # Build INSPECTION_FIELDS from centralized strings to avoid duplication
    INSPECTION_FIELDS = []
    rows = S.get("MESSAGES", {}).get("INSPECTION_ROWS", [])
    # Section 1
    sec1 = S.get("MESSAGES", {}).get("INSPECTION_SECTION_2", "Έλεγχος Χώρων ΥΣ")
    INSPECTION_FIELDS.extend([
        {"type": "section", "title": f"1. {sec1}"},
        S.get("MESSAGES", {}).get("OBSERVATIONS_FMT", "Παρατηρήσεις ({n}. {sec})").format(n=1, sec=sec1),
    ])
    INSPECTION_FIELDS.extend(rows[0:4])
    # Section 2
    sec2 = S.get("MESSAGES", {}).get("INSPECTION_SECTION_3", "Μ/Σ 150/20kV & Διακόπτες 150kV & 20kV")
    INSPECTION_FIELDS.extend([
        {"type": "section", "title": f"2. {sec2}"},
        S.get("MESSAGES", {}).get("OBSERVATIONS_FMT", "Παρατηρήσεις ({n}. {sec})").format(n=2, sec=sec2),
    ])
    INSPECTION_FIELDS.extend(rows[4:12])
    # Section 3a
    sec3a = S.get("MESSAGES", {}).get("INSPECTION_SECTION_3A", "Υπαίθριες πύλες 20 kV")
    INSPECTION_FIELDS.extend([
        {"type": "section", "title": f"3α. {sec3a}"},
        S.get("MESSAGES", {}).get("OBSERVATIONS_FMT", "Παρατηρήσεις ({n}. {sec})").format(n="3α", sec=sec3a),
    ])
    INSPECTION_FIELDS.append(rows[12])
    # Section 3b
    sec3b = S.get("MESSAGES", {}).get("INSPECTION_SECTION_3B", "Πίνακες 20 kV")
    INSPECTION_FIELDS.extend([
        {"type": "section", "title": f"3β. {sec3b}"},
        S.get("MESSAGES", {}).get("OBSERVATIONS_FMT", "Παρατηρήσεις ({n}. {sec})").format(n="3β", sec=sec3b),
    ])
    INSPECTION_FIELDS.extend(rows[13:15])
    # Section 4
    sec4 = S.get("MESSAGES", {}).get("INSPECTION_SECTION_4", "Κτίριο χειρισμών & Τ.Α.Σ.")
    INSPECTION_FIELDS.extend([
        {"type": "section", "title": f"4. {sec4}"},
        S.get("MESSAGES", {}).get("OBSERVATIONS_FMT", "Παρατηρήσεις ({n}. {sec})").format(n=4, sec=sec4),
    ])
    INSPECTION_FIELDS.extend(rows[15:18])
    # Section 5
    sec5 = S.get("MESSAGES", {}).get("INSPECTION_SECTION_5", "Αποζεύκτες Γραμμών")
    INSPECTION_FIELDS.extend([
        {"type": "section", "title": f"5. {sec5}"},
        S.get("MESSAGES", {}).get("OBSERVATIONS_FMT", "Παρατηρήσεις ({n}. {sec})").format(n=5, sec=sec5),
    ])
    INSPECTION_FIELDS.append(rows[18])
    # Section 6
    sec6 = S.get("MESSAGES", {}).get("INSPECTION_SECTION_6", "PC ΧΕΙΡΙΣΜΩΝ")
    INSPECTION_FIELDS.extend([
        {"type": "section", "title": f"6. {sec6}"},
        S.get("MESSAGES", {}).get("OBSERVATIONS_FMT", "Παρατηρήσεις ({n}. {sec})").format(n=6, sec=sec6),
    ])
    INSPECTION_FIELDS.extend(rows[19:21])
    # Final section: opinions
    sec7 = S.get("MESSAGES", {}).get("INSPECTION_SECTION_7", "Απόψεις")
    INSPECTION_FIELDS.extend([
        {"type": "section", "title": f"7. {sec7}"},
        S.get("MESSAGES", {}).get("INSPECTION_OPINIONS", "Απόψεις - Προτάσεις"),
    ])

    def open_local_db_picker(self):
        # Last working version: prompt for DB path and allow file selection
        self._prompt_local_db_path()

    def _prompt_local_db_path(self):
        popup = Popup(title=S["MESSAGES"].get("OPEN_LOCAL_DB_TITLE", "Άνοιγμα Τοπικής Βάσης"), size_hint=(0.9, 0.4))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
        layout.add_widget(Label(text=S.get("MESSAGES", {}).get("ENTER_PATH", "Δώσε πλήρες path του αρχείου .db")))
        default_path = ANDROID_DEFAULT_DB_PATH
        path_input = TextInput(text=default_path, hint_text=ANDROID_DEFAULT_DB_PATH, multiline=False)
        layout.add_widget(path_input)

        chooser_layout = BoxLayout(size_hint_y=0.25, spacing=10)
        choose_btn = Button(text=S.get("BUTTONS", {}).get("BROWSE_FILE", "Αναζήτηση αρχείου"))
        choose_btn.disabled = not (filechooser or FileChooserListView)

        def open_picker():
            def _selected(selection):
                if not selection or len(selection) == 0:
                    self.show_error(S["MESSAGES"].get("PICKER_EMPTY_SELECTION", "Ο επιλογέας επέστρεψε κενή επιλογή (None)."))
                    return
                raw_value = selection[0]
                if raw_value is None:
                    self.show_error(S["MESSAGES"].get("PICKER_EMPTY_SELECTION", "Ο επιλογέας επέστρεψε κενή επιλογή (None)."))
                    return
                if isinstance(raw_value, bytes):
                    selected_path = raw_value.decode("utf-8", errors="ignore")
                else:
                    selected_path = str(raw_value)
                if selected_path.strip().lower() in ("", "none", "null"):
                    self.show_error(S["MESSAGES"].get("PICKER_EMPTY_SELECTION", "Ο επιλογέας επέστρεψε κενή επιλογή (None)."))
                    return
                Logger.info(f"APP: File chooser selected: {selected_path}")
                Clock.schedule_once(
                    lambda _dt: setattr(path_input, "text", selected_path), 0
                )

            try:
                if platform == "android":
                    # Ensure storage permissions are requested BEFORE opening SAF picker
                    try:
                        from android.permissions import (
                            Permission,
                            check_permission,
                            request_permissions,
                        )

                        needed_perms = [
                            Permission.READ_EXTERNAL_STORAGE,
                            Permission.WRITE_EXTERNAL_STORAGE,
                        ]
                        perms_granted = all(check_permission(p) for p in needed_perms)
                        if not perms_granted:
                            # Request permissions and return; DO NOT show an error popup
                            # immediately because the Android permission dialog is a
                            # system UI overlay. Showing our own popup at the same
                            # time leads to the UX problem where our popup appears
                            # behind the permission dialog. The app should wait for
                            # the system dialog to complete and the user to retry.
                            request_permissions(needed_perms)
                            Logger.info(
                                "APP: Requested storage permissions; waiting for user to grant them."
                            )
                            # Show an in-app non-modal notice asking the user to
                            # grant permissions and retry. We avoid showing an
                            # error popup here because the system permission
                            # dialog is a separate UI. The notice contains a
                            # retry button that re-opens the local DB picker.
                            try:
                                self._show_permissions_requested_notice()
                            except Exception:
                                Logger.info("APP: Could not show permission notice")
                            return
                    except Exception:
                        # Continue without explicit permission check if android.permissions not available
                        pass

                    # Use Android SAF picker
                    self._open_android_document_picker(_selected)
                    return

                # Non-Android flow: prefer filechooser if available, otherwise fall back to list view or show error
                if not filechooser:
                    if FileChooserListView:
                        self.show_error(
                            S["MESSAGES"].get(
                                "ANDROID_FILECHOOSER_FALLBACK",
                                "Ο επιλογέας αρχείων του Android δεν είναι διαθέσιμος. Χρησιμοποίησε τη λίστα αρχείων στο παράθυρο.",
                            )
                        )
                    else:
                        self.show_error(
                            S["MESSAGES"].get(
                                "FILECHOOSER_NOT_AVAILABLE",
                                "Ο επιλογέας αρχείων δεν είναι διαθέσιμος",
                            )
                        )
                    return

                # Use the available filechooser
                filechooser.open_file(on_selection=_selected)
            except Exception as e:
                Logger.error(f"APP: Exception in open_picker: {str(e)}")
                self.show_error(
                    S.get("MESSAGES", {}).get(
                        "PICKER_OPEN_ERROR",
                        "Σφάλμα ανοίγματος επιλογέα: {err}",
                    ).format(err=str(e))
                )

        choose_btn.bind(on_press=lambda _x: open_picker())
        chooser_layout.add_widget(choose_btn)
        layout.add_widget(chooser_layout)

        if FileChooserListView:
            chooser_path = (
                os.path.dirname(default_path) if default_path else "/storage/emulated/0"
            )
            file_chooser = FileChooserListView(
                filters=["*.db"], path=chooser_path, size_hint_y=0.6
            )

            def _file_list_selected(_instance, selection):
                if selection:
                    raw_value = selection[0]
                    if raw_value is None:
                        self.show_error(S["MESSAGES"].get("PICKER_EMPTY_SELECTION", "Ο επιλογέας επέστρεψε κενή επιλογή (None)."))
                        return
                    if isinstance(raw_value, bytes):
                        selected_path = raw_value.decode("utf-8", errors="ignore")
                    else:
                        selected_path = str(raw_value)
                    if selected_path.strip().lower() in ("", "none", "null"):
                        self.show_error(S["MESSAGES"].get("PICKER_EMPTY_SELECTION", "Ο επιλογέας επέστρεψε κενή επιλογή (None)."))
                        return
                    Logger.info(f"APP: File list selected: {selected_path}")
                    Clock.schedule_once(
                        lambda _dt: setattr(path_input, "text", selected_path), 0
                    )

            file_chooser.bind(selection=_file_list_selected)
            file_chooser.bind(
                on_submit=lambda _instance, selection, _touch: _file_list_selected(
                    _instance, selection
                )
            )
            layout.add_widget(file_chooser)

        buttons = BoxLayout(size_hint_y=0.3, spacing=10)
        open_btn = Button(text=S["BUTTONS"].get("OPEN", "Άνοιγμα"))
        open_btn.bind(
            on_press=lambda _x: (
                popup.dismiss(),
                self.use_local_mode(path_input.text.strip()),
            )
        )
        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
        cancel_btn.bind(on_press=popup.dismiss)
        buttons.add_widget(open_btn)
        buttons.add_widget(cancel_btn)
        layout.add_widget(buttons)
        popup.content = layout
        popup.open()

        # NOTE: the real Android SAF picker implementation lives as a class method
        # further down in the file (`def _open_android_document_picker(self, on_selected):`).
        # The local nested implementation was removed to ensure permission checks
        # from the top-level picker are always used.

    def _open_android_document_picker(self, on_selected):
        if platform != "android":
            Logger.warning("APP: SAF picker only available on Android platform")
            self.show_error(S["MESSAGES"].get("FILECHOOSER_ANDROID_ONLY", "Ο επιλογέας αρχείων είναι διαθέσιμος μόνο σε Android."))
            return
        # Request permissions before proceeding
        try:
            from android.permissions import (Permission, check_permission,
                                             request_permissions)

            needed_perms = [
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
            ]
            # Check if permissions are already granted
            perms_granted = all(check_permission(p) for p in needed_perms)
            if not perms_granted:
                # Request permissions and return, user must retry after granting
                request_permissions(needed_perms)
                self.show_error(
                    S["MESSAGES"]["STORAGE_PERMISSIONS_REQUIRED"]
                )
                return
        except Exception as perm_e:
            Logger.warning(f"APP: Permission check/request failed: {str(perm_e)}")
            # Continue, may work on older Android or if permissions not enforced

        try:
            from jnius import autoclass

            from android import activity
        except Exception as e:
            Logger.warning(f"APP: Android SAF picker not available: {str(e)}")
            self.show_error(S["MESSAGES"].get("FILECHOOSER_NOT_AVAILABLE", "Ο επιλογέας αρχείων δεν είναι διαθέσιμος"))
            return

        try:
            Intent = autoclass("android.content.Intent")
            Activity = autoclass("android.app.Activity")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")

            intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            intent.setType("*/*")

            request_code = 61423

            def _activity_result(req_code, result_code, data):
                if req_code != request_code:
                    Logger.warning("APP: Activity result request code mismatch.")
                    self.show_error(S["MESSAGES"].get("FILECHOOSER_INTERNAL_ERROR", "Εσωτερικό σφάλμα επιλογέα αρχείων."))
                    return
                activity.unbind(on_activity_result=_activity_result)
                if result_code != Activity.RESULT_OK or data is None:
                    Logger.warning("APP: Activity result not OK or data is None.")
                    self.show_error(S["MESSAGES"].get("FILECHOICE_CANCELLED", "Η επιλογή αρχείου απέτυχε ή ακυρώθηκε."))
                    return
                try:
                    uri = data.getData()
                    if uri is None:
                        Logger.warning("APP: SAF picker returned None URI.")
                        self.show_error(S["MESSAGES"].get("PICKER_EMPTY_SELECTION", "Ο επιλογέας επέστρεψε κενή επιλογή (None)."))
                        return
                    uri_str = uri.toString()
                    Logger.info(f"APP: SAF selected: {uri_str}")
                    on_selected([uri_str])
                except Exception as e:
                    Logger.warning(f"APP: SAF selection failed: {str(e)}")
                    self.show_error(S.get("MESSAGES", {}).get("FILECHOOSER_SELECT_ERROR", "Σφάλμα κατά την επιλογή αρχείου: {err}").format(err=str(e)))

            activity.bind(on_activity_result=_activity_result)
            current_activity = PythonActivity.mActivity
            current_activity.startActivityForResult(intent, request_code)
        except Exception as e:
            Logger.warning(f"APP: Failed to open SAF picker: {str(e)}")
            self.show_error(S.get("MESSAGES", {}).get("PICKER_OPEN_ERROR", "Αποτυχία ανοίγματος επιλογέα αρχείων: {err}").format(err=str(e)))

    def use_local_mode(self, db_path):
        if not db_path or str(db_path).strip().lower() in ("none", "null"):
            self.show_error(S.get("MESSAGES", {}).get("NO_DB_SELECTED", "Δεν επιλέχθηκε αρχείο βάσης"))
            return

        def _continue_with_path(resolved_path):
            self.local_db_path = resolved_path
            self._set_saved_db_path(resolved_path)
            self.data_mode = "local"
            self.change_log_path = None
            self._ensure_change_log_path()
            if hasattr(self, "mode_label"):
                self.mode_label.text = S["MESSAGES"].get("MODE_LABEL_LOCAL", "Πηγή: Τοπική Βάση")
            # Only load substations if DB is valid and loaded
            self.load_substations(None)

        try:
            if isinstance(db_path, str) and db_path.startswith("content://"):

                def _on_copy_done(success, val):
                    if not success:
                        self.show_error(S["MESSAGES"].get("IMPORT_FAILED", "Αποτυχία ανοίγματος βάσης:") + f" {val}")
                        return
                    _continue_with_path(val)

                self._copy_content_uri_to_file_async(db_path, _on_copy_done)
                return

            resolved = self._prepare_local_db_path(db_path)
        except FileNotFoundError:
            self.show_error("Το αρχείο βάσης δεν βρέθηκε")
            return
        except Exception as e:
            self.show_error(f"Αποτυχία ανοίγματος βάσης: {str(e)}")
            return

        _continue_with_path(resolved)

    def _normalize_android_storage_path(self, path_value: str) -> str:
        if not path_value:
            return path_value
        normalized = path_value.strip().replace("\\", "/")
        prefix_map = [
            "/Εσωτερικός χώρος αποθήκευσης",
            "/Internal storage",
        ]
        for prefix in prefix_map:
            if normalized.startswith(prefix):
                normalized = "/storage/emulated/0" + normalized[len(prefix) :]
                break
        return normalized

    def _prepare_local_db_path(self, path_value: str) -> str:
        normalized = self._normalize_android_storage_path(path_value)
        if normalized.startswith("content://"):
            return self._copy_content_uri_to_file(normalized)
        if not os.path.exists(normalized):
            raise FileNotFoundError(normalized)
        try:
            conn = sqlite3.connect(f"file:{normalized}?mode=ro", uri=True)
            conn.close()
            return normalized
        except sqlite3.OperationalError as e:
            if "unable to open database file" not in str(e).lower():
                raise
            # Set user_data_dir only if needed
            target_dir = getattr(self, "user_data_dir", None)
            if not target_dir:
                try:
                    from kivy.utils import platform as kivy_platform

                    if kivy_platform == "android":
                        from android.storage import app_storage_path

                        target_dir = app_storage_path()
                    else:
                        target_dir = os.path.join(os.getcwd(), "user_data")
                except Exception:
                    target_dir = os.path.join(os.getcwd(), "user_data")
                self.user_data_dir = target_dir
            os.makedirs(target_dir, exist_ok=True)
            try:
                target_path = os.path.join(target_dir, os.path.basename(normalized))
                shutil.copy2(normalized, target_path)
                conn = sqlite3.connect(f"file:{target_path}?mode=ro", uri=True)
                conn.close()
                return target_path
            except Exception as copy_err:
                raise RuntimeError(
                    f"Unable to open database file: {normalized}"
                ) from copy_err

    def __init__(self, **kwargs):
        Logger.info("APP: Initializing SubstationAndroidApp")
        try:
            super().__init__(**kwargs)
            self.substations = []
            self.elements = {}
            self.current_substation = None
            self.data_mode = "local"
            self.local_db_path = None
            self.change_log_path = None
            Logger.info("APP: SubstationAndroidApp initialized successfully")
        except Exception as e:
            Logger.critical(f"APP: Error in __init__: {str(e)}")
            Logger.critical(f"APP: Traceback: {traceback.format_exc()}")
            raise

    def _request_android_permissions(self):
        if platform != "android":
            Logger.info("APP: Android permissions only required on Android platform")
            return
        try:
            from android.permissions import Permission, request_permissions

            request_permissions(
                [
                    Permission.READ_EXTERNAL_STORAGE,
                    Permission.WRITE_EXTERNAL_STORAGE,
                ]
            )
        except Exception:
            Logger.info("APP: Android permissions not available or not required")

    def _show_permissions_requested_notice(self):
        """Display a small non-modal notice in the app asking the user to grant storage permissions and retry."""

        def _show(dt=None):
            try:
                notice = BoxLayout(size_hint_y=None, height=64, spacing=10, padding=8)
                label = Label(
                    text=(
                        S["MESSAGES"]["STORAGE_PERMISSIONS_REQUIRED"] + " "
                        "πατήστε 'Ξαναδοκίμασε' όταν τελειώσετε."
                    ),
                    halign="left",
                    valign="middle",
                )
                # Make label wrap its text to the available width and adjust
                # height to the rendered texture so text doesn't overflow.
                label.size_hint_y = None

                def _bind_width(instance, value):
                    instance.text_size = (value, None)

                label.bind(width=_bind_width)
                label.bind(
                    texture_size=lambda inst, val: setattr(inst, "height", val[1])
                )
                retry_btn = Button(text=S.get("MESSAGES", {}).get("RETRY", "Ξαναδοκίμασε"), size_hint_x=None, width=140)

                def _on_retry(_):
                    try:
                        # Re-open the local DB picker flow
                        self.open_local_db_picker()
                    except Exception as e:
                        Logger.warning(f"APP: Retry open_local_db_picker failed: {e}")
                    try:
                        if notice.parent:
                            notice.parent.remove_widget(notice)
                    except Exception:
                        pass

                retry_btn.bind(on_press=_on_retry)
                notice.add_widget(label)
                notice.add_widget(retry_btn)

                if (
                    hasattr(self, "content_layout")
                    and getattr(self, "content_layout") is not None
                ):
                    # insert at top of content_layout so it's visible without blocking
                    try:
                        self.content_layout.add_widget(notice, index=0)
                    except Exception:
                        self.content_layout.add_widget(notice)
                    # auto-remove after 30 seconds
                    Clock.schedule_once(
                        lambda _dt: (
                            notice.parent and notice.parent.remove_widget(notice)
                        ),
                        30,
                    )
                else:
                    # fallback: show as a temporary popup (non-modal)
                    p = Popup(
                        title="Δικαιώματα",
                        content=notice,
                        size_hint=(0.9, 0.12),
                        auto_dismiss=True,
                    )
                    p.open()
                    Clock.schedule_once(lambda _dt: p.dismiss(), 30)
            except Exception as e:
                Logger.warning(f"APP: Failed to show permission notice: {e}")

        Clock.schedule_once(_show, 0)

    def build(self):
        Logger.info("APP: ========== BUILD METHOD STARTING ==========")
        Logger.info("APP: Building UI")
        try:
            Logger.info("APP: Setting window title")
            self.title = "DB Substations"
            # Ensure spinner dropdowns are fully opaque
            from kivy.uix.spinner import SpinnerOption

            primary = (0.05, 0.18, 0.36, 1)
            text_on_primary = (1, 1, 1, 1)
            Spinner.background_normal = ""
            Spinner.background_down = ""
            Spinner.background_color = primary
            Spinner.color = text_on_primary
            SpinnerOption.background_normal = ""
            SpinnerOption.background_down = ""
            SpinnerOption.background_color = primary
            SpinnerOption.color = text_on_primary
            Logger.info("APP: Creating main_layout BoxLayout")
            main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
            Logger.info("APP: Main layout created successfully")

            # Header with app title and logo
            Logger.info("APP: Creating header with logo")
            header_box = BoxLayout(size_hint_y=0.06, spacing=10, padding=[10, 5])
            
            # Try to add logo if it exists with white background
            try:
                from kivy.uix.image import Image
                from kivy.graphics import Color, Rectangle
                logo_path = os.path.join(os.path.dirname(__file__), "logo_deddie.png")
                if os.path.exists(logo_path):
                    # Create container for logo with white background
                    logo_container = BoxLayout(size_hint_x=None, width=50, padding=3)
                    
                    def redraw_bg(inst, val):
                        logo_container.canvas.before.clear()
                        with logo_container.canvas.before:
                            Color(1, 1, 1, 1)  # White background
                            Rectangle(size=inst.size, pos=inst.pos)
                    
                    # Bind size and pos updates to redraw background rectangle
                    logo_container.bind(size=redraw_bg, pos=redraw_bg)
                    
                    logo = Image(
                        source=logo_path,
                        size_hint_x=1,
                        allow_stretch=True,
                        keep_ratio=True
                    )
                    logo_container.add_widget(logo)
                    redraw_bg(logo_container, None)  # Draw initial background
                    header_box.add_widget(logo_container)
            except Exception as e:
                Logger.warning(f"APP: Could not load logo: {e}")
            
            header_label = Label(
                text=S.get("MESSAGES", {}).get("APP_TITLE", "Υποσταθμοί ΔΕΔΔΗΕ"),
                bold=True,
                font_size='18sp',
                halign='left',
                valign='middle'
            )
            header_label.bind(size=header_label.setter('text_size'))
            header_box.add_widget(header_label)
            
            # Add spacer to push settings button to the right
            spacer = BoxLayout(size_hint_x=1)  # Takes up remaining space
            header_box.add_widget(spacer)
            
            # Settings button in header - use IconOnlyButton from desktop ui.shared
            try:
                from ui.shared import IconOnlyButton
                settings_btn = IconOnlyButton(
                    icon_type="settings",
                    icon_color=[0.05, 0.18, 0.36, 1],
                    size=(40, 40)
                )
            except Exception:
                # Fallback: use text button if IconOnlyButton not available
                settings_btn = Button(text="⚙", font_size='20sp', size_hint_x=None, width=40)
            
            settings_btn.bind(on_press=lambda x: self._show_sync_settings())
            header_box.add_widget(settings_btn)
            
            main_layout.add_widget(header_box)
            Logger.info("APP: Header added")

            # Database selection bar (cleaner, single row)
            self.db_bar = BoxLayout(size_hint_y=0.06, spacing=8, padding=[10, 0])
            
            self.mode_label = Label(
                text=S.get("MESSAGES", {}).get("MODE_LABEL_LOCAL", "Τοπική Βάση"),
                size_hint_x=0.65,
                font_size='14sp',
                halign='left'
            )
            self.mode_label.bind(size=self.mode_label.setter('text_size'))

            self.local_db_btn = Button(
                text=S.get("MESSAGES", {}).get("LOCAL_DB_BUTTON", "Επιλογή ΒΔ"),
                size_hint_x=0.35,
                font_size='13sp'
            )
            self.local_db_btn.bind(on_press=lambda _x: self.open_local_db_picker())

            self.db_bar.add_widget(self.mode_label)
            self.db_bar.add_widget(self.local_db_btn)
            main_layout.add_widget(self.db_bar)

            # Main content area
            self.content_layout = BoxLayout(orientation="vertical", size_hint_y=0.74)
            main_layout.add_widget(self.content_layout)
            Logger.info("APP: Content layout added")

            # Bottom button area - reorganized for better UX
            self.buttons_container = BoxLayout(
                orientation="vertical", size_hint_y=0.16, spacing=5, padding=[5, 0, 5, 5]
            )
            
            # PRIMARY ACTIONS ROW (larger, most common actions)
            primary_row = BoxLayout(size_hint_y=0.55, spacing=8)
            
            self.refresh_btn = Button(
                text=S.get("BUTTONS", {}).get("REFRESH", "Ανανέωση"),
                font_size='16sp',
                bold=True
            )
            self.refresh_btn.bind(on_press=self.load_substations)
            primary_row.add_widget(self.refresh_btn)
            
            self.buttons_container.add_widget(primary_row)
            
            # SECONDARY ACTIONS ROW (smaller, system functions)
            secondary_row = BoxLayout(size_hint_y=0.45, spacing=8)
            
            self.sync_btn = Button(
                text="Sync",
                font_size='16sp',
                bold=True
            )
            self.sync_btn.bind(on_press=self._on_sync_button_pressed)
            secondary_row.add_widget(self.sync_btn)

            self.change_log_btn = Button(
                text="Change Log",
                font_size='16sp',
                bold=True
            )
            self.change_log_btn.bind(on_press=lambda _x: self.show_change_log_menu())
            secondary_row.add_widget(self.change_log_btn)
            
            self.buttons_container.add_widget(secondary_row)

            main_layout.add_widget(self.buttons_container)
            Logger.info("APP: Buttons added (reorganized layout)")

            # Load data after UI is rendered (prevent ANR)
            Logger.info("APP: Scheduling load_substations and startup sync to run after UI renders")
            if not self._auto_load_saved_db():
                Clock.schedule_once(self.load_substations, 0.5)
                Clock.schedule_once(self._run_startup_sync, 1.0)
            else:
                Clock.schedule_once(self.load_substations, 0.5)
                Clock.schedule_once(self._run_startup_sync, 1.0)

            Logger.info("APP: UI build completed successfully")
            return main_layout

        except Exception as e:
            Logger.critical(f"APP: Error in build(): {str(e)}")
            Logger.critical(f"APP: Traceback: {traceback.format_exc()}")
            # Return a simple error display instead of crashing
            error_layout = BoxLayout(orientation="vertical", padding=20)
            error_layout.add_widget(Label(text=f"Error: {str(e)}"))
            return error_layout

    def _auto_load_saved_db(self):
        """Attempt to auto-load saved DB path if available. Returns True if loaded, False otherwise."""
        try:
            db_path = getattr(self, "local_db_path", None)
            if db_path and os.path.exists(db_path):
                self.use_local_mode(db_path)
                return True
            # Optionally, check for a saved DB path in persistent storage
            if hasattr(self, "_get_saved_db_path"):
                saved_path = self._get_saved_db_path()
                if saved_path and os.path.exists(saved_path):
                    self.use_local_mode(saved_path)
                    return True
        except Exception as e:
            self.show_error(f"Auto-load DB error: {str(e)}")
        return False

    def _local_fetch_substations(self):
        if not self.local_db_path or not os.path.exists(self.local_db_path):
            return []
        conn = sqlite3.connect(self.local_db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                s.id,
                s.name,
                s.location,
                s.adoption_date,
                COALESCE(
                    NULLIF(TRIM(s.last_maintenance), ''),
                    (
                        SELECT MAX(m.date_time)
                        FROM maintenance m
                        WHERE m.substation_id = s.id
                    ),
                    ''
                ) AS last_maintenance,
                s.monogram_pdf,
                (
                    SELECT COUNT(*)
                    FROM elements e
                    WHERE e.substation_id = s.id
                ) AS elements_count,
                (
                    SELECT COUNT(DISTINCT TRIM(e.gate))
                    FROM elements e
                    WHERE e.substation_id = s.id
                      AND TRIM(COALESCE(e.gate, '')) != ''
                ) AS gates_count,
                (
                    SELECT COUNT(*)
                    FROM elements e
                    WHERE e.substation_id = s.id
                      AND e.is_main_switch = 3
                ) AS capacitors_count,
                (
                    SELECT COUNT(*)
                    FROM maintenance m
                    WHERE m.substation_id = s.id
                ) AS maintenances_count
            FROM substations s
            ORDER BY s.name ASC
            """
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "id": r[0],
                "name": r[1],
                "location": r[2],
                "adoption_date": r[3],
                "last_maintenance": r[4],
                "monogram_pdf": r[5],
                "elements_count": r[6] or 0,
                "gates_count": r[7] or 0,
                "capacitors_count": r[8] or 0,
                "maintenances_count": r[9] or 0,
            }
            for r in rows
        ]

    def _local_fetch_elements(self, substation_id):
        if not self.local_db_path or not os.path.exists(self.local_db_path):
            return []
        conn = sqlite3.connect(self.local_db_path)
        cursor = conn.cursor()
        # Join with element_models to get model_name and model_manufacturer
        cursor.execute(
            """
            SELECT e.id, e.substation_id, e.element_type, e.name, e.serial_number,
                   e.maintenance_date, e.voltage_level, e.manufacturer, e.type,
                   e.manufacture_year, e.model, e.model_version, e.operating_status,
                   e.installation_space, e.maintenance_cycle, e.gate, e.is_main_switch,
                   e.element_model_id, em.breaker_category, em.model_name,
                   em.manufacturer as model_manufacturer
            FROM elements e
            LEFT JOIN element_models em ON e.element_model_id = em.id
            WHERE e.substation_id = ?
            ORDER BY e.gate
            """, (substation_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        columns = [
            "id",
            "substation_id",
            "element_type",
            "name",
            "serial_number",
            "maintenance_date",
            "voltage_level",
            "manufacturer",
            "type",
            "manufacture_year",
            "model",
            "model_version",
            "operating_status",
            "installation_space",
            "maintenance_cycle",
            "gate",
            "is_main_switch",
            "element_model_id",
            "breaker_category",
            "model_name",
            "model_manufacturer",
        ]
        return [dict(zip(columns, r)) for r in rows]

    def _local_insert(self, table, payload):
        if not self.local_db_path or not os.path.exists(self.local_db_path):
            raise Exception("No DB path")
        conn = sqlite3.connect(self.local_db_path)
        cursor = conn.cursor()
        # Filter payload keys to columns actually present in the table to avoid
        # SQLite errors when payload contains nested structures (e.g., 'elements').
        try:
            existing = {r[1] for r in cursor.execute(f"PRAGMA table_info({table})")}
        except Exception:
            existing = set()

        filtered_items = [(k, v) for k, v in payload.items() if k in existing]
        if not filtered_items:
            # Nothing to insert into this table schema; close and raise to surface
            conn.close()
            raise RuntimeError(f"No matching columns to insert into table '{table}'")

        columns = ", ".join(k for k, _ in filtered_items)
        placeholders = ", ".join("?" * len(filtered_items))
        cursor.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
            [v for _, v in filtered_items],
        )
        new_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return new_id

    def _set_saved_db_path(self, path):
        self.saved_db_path = path
        if hasattr(self, "user_data_dir") and self.user_data_dir:
            with open(os.path.join(self.user_data_dir, "saved_db.txt"), "w") as f:
                f.write(path)

    def _get_saved_db_path(self):
        if hasattr(self, "saved_db_path"):
            return self.saved_db_path
        if hasattr(self, "user_data_dir") and self.user_data_dir:
            try:
                with open(os.path.join(self.user_data_dir, "saved_db.txt"), "r") as f:
                    return f.read().strip()
            except Exception:
                pass
        return None

    def _append_change_log(self, operation, table, data):
        if not self.change_log_path:
            self._ensure_change_log_path()
        with open(self.change_log_path, "a") as f:
            import json

            f.write(
                json.dumps({"operation": operation, "table": table, "data": data})
                + "\n"
            )
        # Notify user where the change log was stored (non-modal)
        try:
            change_log_path = getattr(self, "change_log_path", "change_log.txt")

            def _show_notice(dt=None):
                try:
                    notice = BoxLayout(
                        size_hint_y=None, height=64, spacing=10, padding=8
                    )
                    label = Label(
                        text=f"Οι αλλαγές αποθηκεύτηκαν στο: {change_log_path}",
                        halign="left",
                        valign="middle",
                    )
                    # Ensure wrapping and auto-height so the label won't overflow
                    label.size_hint_y = None

                    def _bind_width2(instance, value):
                        instance.text_size = (value, None)

                    label.bind(width=_bind_width2)
                    label.bind(
                        texture_size=lambda inst, val: setattr(inst, "height", val[1])
                    )
                    copy_btn = Button(
                        text=S.get("MESSAGES", {}).get("COPY_PATH", "Αντιγραφή διαδρομής"), size_hint_x=None, width=180
                    )

                    def _copy_path(_):
                        try:
                            from kivy.core.clipboard import Clipboard

                            Clipboard.copy(change_log_path)
                        except Exception:
                            pass

                    copy_btn.bind(on_press=_copy_path)
                    # Open folder button (Android intent when available)
                    open_btn = Button(
                        text=S["MESSAGES"].get("OPEN_FOLDER", "Άνοιγμα φακέλου"), size_hint_x=None, width=140
                    )

                    def _open_folder(_):
                        try:
                            from jnius import autoclass

                            Intent = autoclass("android.content.Intent")
                            Uri = autoclass("android.net.Uri")
                            File = autoclass("java.io.File")
                            PythonActivity = autoclass(
                                "org.kivy.android.PythonActivity"
                            )
                            f = File(change_log_path)
                            uri = Uri.fromFile(f)
                            intent = Intent(Intent.ACTION_VIEW)
                            intent.setDataAndType(uri, "*/*")
                            current = PythonActivity.mActivity
                            current.startActivity(intent)
                        except Exception:
                            # Surface the error to the user so they know why opening failed
                            try:
                                import traceback as _tb

                                self.show_error(
                                    f"{S['MESSAGES'].get('OPEN_FOLDER', 'Άνοιγμα φακέλου')} απέτυχε: {_tb.format_exc()}"
                                )
                            except Exception:
                                pass
                            try:
                                from kivy.core.clipboard import Clipboard

                                Clipboard.copy(change_log_path)
                            except Exception:
                                pass

                    open_btn.bind(on_press=_open_folder)
                    notice.add_widget(open_btn)

                    # Share button (attempt Android share intent, fallback to copy path)
                    share_btn = Button(text=S.get("MESSAGES", {}).get("SHARE_BUTTON", "Κοινοποίηση"), size_hint_x=None, width=120)

                    def _share_file(_):
                        # Delegate to testable helper on the app instance
                        try:
                            self._launch_share_intent(change_log_path)
                        except Exception:
                            try:
                                from kivy.core.clipboard import Clipboard

                                Clipboard.copy(change_log_path)
                            except Exception:
                                pass

                    share_btn.bind(on_press=_share_file)
                    notice.add_widget(share_btn)
                    notice.add_widget(label)
                    notice.add_widget(copy_btn)

                    if (
                        hasattr(self, "content_layout")
                        and getattr(self, "content_layout") is not None
                    ):
                        try:
                            self.content_layout.add_widget(notice, index=0)
                        except Exception:
                            self.content_layout.add_widget(notice)
                        Clock.schedule_once(
                            lambda _dt: (
                                notice.parent and notice.parent.remove_widget(notice)
                            ),
                            20,
                        )
                    else:
                        p = Popup(
                            title="Change log saved",
                            content=notice,
                            size_hint=(0.9, 0.12),
                            auto_dismiss=True,
                        )
                        p.open()
                        Clock.schedule_once(lambda _dt: p.dismiss(), 20)
                except Exception:
                    pass

            # Prefer scheduling on the Kivy Clock when available; in headless
            # tests Clock may be a simple shim that executes immediately, but
            # be defensive and call directly if Clock is not present or does
            # not provide schedule_once.
            try:
                if "Clock" in globals() and hasattr(Clock, "schedule_once"):
                    Clock.schedule_once(_show_notice, 0)
                else:
                    _show_notice()
            except Exception:
                try:
                    _show_notice()
                except Exception:
                    pass

            # Defensive fallback for test environments where the full notice
            # creation may fail: ensure at least a minimal notice with a copy
            # button is added to `content_layout` so tests and users see a hint.
            try:
                if (
                    hasattr(self, "content_layout")
                    and getattr(self, "content_layout") is not None
                    and len(getattr(self.content_layout, "children", [])) == 0
                ):
                    try:
                        fb_notice = BoxLayout(
                            size_hint_y=None, height=64, spacing=10, padding=8
                        )
                        fb_copy = Button(
                            text=S.get("MESSAGES", {}).get("COPY_PATH", "Αντιγραφή διαδρομής"), size_hint_x=None, width=180
                        )
                        fb_notice.add_widget(fb_copy)
                        try:
                            self.content_layout.add_widget(fb_notice, index=0)
                        except Exception:
                            self.content_layout.add_widget(fb_notice)
                    except Exception:
                        pass
            except Exception:
                pass
        except Exception:
            pass

    def _ensure_change_log_path(self):
        if not self.change_log_path:
            if hasattr(self, "user_data_dir") and self.user_data_dir:
                self.change_log_path = os.path.join(
                    self.user_data_dir, "change_log.txt"
                )
            else:
                self.change_log_path = "change_log.txt"
        # Ensure parent directory exists and file is present so intents
        # and FileProvider can access it reliably.
        try:
            parent = os.path.dirname(self.change_log_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            # Ensure file exists
            with open(self.change_log_path, "a", encoding="utf-8"):
                pass
        except Exception:
            # If we cannot create the file, leave it as-is; callers will
            # handle failures and fallbacks (clipboard, popup)
            pass

    def _is_transformer(self, elem_type: str) -> bool:
        """Return True when an element type represents a transformer (150/20KV or similar)."""
        if not elem_type:
            return False
        transformer_indicators = [
            "ΥΤ",
            "150/20",
            "Transformer",
            "Μετασχηματιστής",
            "Μ/Σ",
        ]
        return any(indicator in elem_type for indicator in transformer_indicators)

    def _set_root_buttons_visible(self, visible: bool):
        """Show or hide main-menu-only controls when entering/leaving substation view."""
        try:
            if hasattr(self, "refresh_btn") and self.refresh_btn is not None:
                self.refresh_btn.disabled = not visible
                # keep widget in layout but hide visually when not visible
                self.refresh_btn.opacity = 1 if visible else 0

            if hasattr(self, "sync_btn") and self.sync_btn is not None:
                self.sync_btn.disabled = not visible
                self.sync_btn.opacity = 1 if visible else 0
            if hasattr(self, "change_log_btn") and self.change_log_btn is not None:
                self.change_log_btn.disabled = not visible
                self.change_log_btn.opacity = 1 if visible else 0
            if hasattr(self, "mode_label") and self.mode_label is not None:
                self.mode_label.opacity = 1 if visible else 0
            if hasattr(self, "local_db_btn") and self.local_db_btn is not None:
                self.local_db_btn.disabled = not visible
                self.local_db_btn.opacity = 1 if visible else 0
            if hasattr(self, "db_bar") and self.db_bar is not None:
                self.db_bar.opacity = 1 if visible else 0
                # Collapse the whole top bar in detail screens to reclaim space.
                self.db_bar.size_hint_y = 0.06 if visible else 0
                self.db_bar.height = 0 if not visible else self.db_bar.height
            if hasattr(self, "buttons_container") and self.buttons_container is not None:
                self.buttons_container.opacity = 1 if visible else 0
                # Collapse the whole bottom main-menu button area in detail screens.
                self.buttons_container.size_hint_y = 0.16 if visible else 0
                self.buttons_container.height = 0 if not visible else self.buttons_container.height
                self.buttons_container.spacing = 5 if visible else 0
                self.buttons_container.padding = [5, 0, 5, 5] if visible else [0, 0, 0, 0]
        except Exception:
            pass

    def _open_change_log_folder(self):
        """Attempt to open the change log folder on Android, fallback to copying path."""
        self._ensure_change_log_path()
        change_log_path = getattr(self, "change_log_path", "change_log.txt")
        try:
            from jnius import autoclass

            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            File = autoclass("java.io.File")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            current = PythonActivity.mActivity
            f = File(change_log_path)

            # Prefer FileProvider to generate a content:// URI which is
            # safe on modern Android versions.
            FileProvider = autoclass("androidx.core.content.FileProvider")
            authority = current.getPackageName() + ".provider"
            try:
                uri = FileProvider.getUriForFile(current, authority, f)
                # If FileProvider unexpectedly returns a file:// URI,
                # copy to external cache and retry to obtain a content:// URI.
                if uri is not None and str(uri.toString()).startswith("file://"):
                    try:
                        ext_cache = current.getExternalCacheDir()
                        if ext_cache is not None:
                            dest = File(ext_cache.getAbsolutePath() + "/" + f.getName())
                            shutil.copyfile(f.getAbsolutePath(), dest.getAbsolutePath())
                            uri = FileProvider.getUriForFile(current, authority, dest)
                    except Exception:
                        pass
            except Exception:
                # If provider isn't available, attempt to copy file to
                # external cache and use that path as a fallback URI.
                try:
                    ext_cache = current.getExternalCacheDir()
                    if ext_cache is not None:
                        dest = File(ext_cache.getAbsolutePath() + "/" + f.getName())
                        shutil.copyfile(f.getAbsolutePath(), dest.getAbsolutePath())
                        uri = Uri.fromFile(dest)
                    else:
                        uri = Uri.fromFile(f)
                except Exception:
                    uri = Uri.fromFile(f)

            intent = Intent(Intent.ACTION_VIEW)
            intent.setDataAndType(uri, "*/*")
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            # Ensure chooser title is a Java CharSequence to avoid jnius overload issues
            try:
                JavaString = autoclass("java.lang.String")
                title_obj = JavaString("Open folder")
            except Exception:
                title_obj = "Open folder"
            chooser = Intent.createChooser(intent, title_obj)
            current.startActivity(chooser)
        except Exception:
            try:
                # Surface error to the user so the stack/exception is visible in-app
                import traceback as _tb

                self.show_error(f"{S['MESSAGES'].get('OPEN_FOLDER', 'Άνοιγμα φακέλου')} απέτυχε: {_tb.format_exc()}")
            except Exception:
                pass
            try:
                # fallback: copy to clipboard so user can navigate manually
                import importlib

                clip = importlib.import_module("kivy.core.clipboard")
                if hasattr(clip, "copy"):
                    clip.copy(change_log_path)
                elif hasattr(clip, "Clipboard") and hasattr(clip.Clipboard, "copy"):
                    clip.Clipboard.copy(change_log_path)
            except Exception:
                pass

    def show_change_log_menu(self):
        """Show a popup that allows opening or sharing the change-log file."""
        self._ensure_change_log_path()
        change_log_path = getattr(self, "change_log_path", "change_log.txt")
        try:
            p = Popup(title="Change log actions", size_hint=(0.95, 0.28))
            layout = BoxLayout(orientation="vertical", padding=8, spacing=8)
            # Show file path and basic file info so users can debug missing files
            try:
                exists = os.path.exists(change_log_path)
                size = os.path.getsize(change_log_path) if exists else 0
            except Exception:
                exists = False
                size = 0
            label = Label(
                text=f"File: {change_log_path}\nExists: {exists}  Size: {size} bytes",
            )
            btns = BoxLayout(size_hint_y=None, height=48, spacing=8)
            open_btn = Button(text=S["MESSAGES"].get("OPEN_FOLDER", "Άνοιγμα φακέλου"))

            def _on_open(_):
                try:
                    self._open_change_log_folder()
                except Exception as e:
                    # Surface error to the user and then fallback to clipboard
                    try:
                        self.show_error(f"{S['MESSAGES'].get('OPEN_FOLDER', 'Άνοιγμα φακέλου')} απέτυχε: {e}")
                    except Exception:
                        pass
                    try:
                        import importlib

                        clip = importlib.import_module("kivy.core.clipboard")
                        if hasattr(clip, "copy"):
                            clip.copy(change_log_path)
                        elif hasattr(clip, "Clipboard") and hasattr(
                            clip.Clipboard, "copy"
                        ):
                            clip.Clipboard.copy(change_log_path)
                    except Exception:
                        pass

            open_btn.bind(on_press=_on_open)
            share_btn = Button(text=S.get("MESSAGES", {}).get("SHARE_BUTTON", "Κοινοποίηση"))

            def _on_share(_):
                try:
                    self._launch_share_intent(change_log_path)
                except Exception as e:
                    # Surface error to the user and then fallback to clipboard
                    try:
                        self.show_error(f"Κοινοποίηση απέτυχε: {e}")
                    except Exception:
                        pass
                    try:
                        import importlib

                        clip = importlib.import_module("kivy.core.clipboard")
                        if hasattr(clip, "copy"):
                            clip.copy(change_log_path)
                        elif hasattr(clip, "Clipboard") and hasattr(
                            clip.Clipboard, "copy"
                        ):
                            clip.Clipboard.copy(change_log_path)
                    except Exception:
                        pass

            share_btn.bind(on_press=_on_share)
            btns.add_widget(open_btn)
            btns.add_widget(share_btn)
            layout.add_widget(label)
            layout.add_widget(btns)
            p.content = layout
            p.open()
        except Exception:
            try:
                import importlib

                clip = importlib.import_module("kivy.core.clipboard")
                if hasattr(clip, "copy"):
                    clip.copy(change_log_path)
                elif hasattr(clip, "Clipboard") and hasattr(clip.Clipboard, "copy"):
                    clip.Clipboard.copy(change_log_path)
            except Exception:
                pass

    def _on_sync_button_pressed(self, instance):
        """Handle manual sync button press."""
        if not hasattr(self, "local_db_path") or not self.local_db_path:
            self.show_error(S.get("MESSAGES", {}).get("NO_DB", "Δεν φορτώθηκε βάση δεδομένων"))
            return
        
        # Disable button to prevent multiple clicks
        self.sync_btn.disabled = True
        self.sync_btn.text = S.get("MESSAGES", {}).get("SYNCING", "Συγχρονισμός...")
        
        def _sync_worker():
            try:
                result = self._perform_sync()
                Clock.schedule_once(lambda dt: self._on_sync_complete(result), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._on_sync_error(str(e)), 0)
        
        t = threading.Thread(target=_sync_worker, daemon=True)
        t.start()

    def _run_startup_sync(self, dt):
        """Run automatic sync on app startup if enabled."""
        try:
            if not hasattr(self, "local_db_path") or not self.local_db_path:
                Logger.info("SYNC: Skipping startup sync - no DB loaded yet")
                return
            
            # Check if sync is enabled
            from config_manager import get_app_setting
            sync_enabled = get_app_setting("sync_auto_cycle_enabled", True)
            if not sync_enabled:
                Logger.info("SYNC: Auto-sync disabled in settings")
                return
            
            Logger.info("SYNC: Starting startup sync cycle")
            result = self._perform_sync()
            
            # Show result if there were changes
            if result:
                sync_result = result.get("sync", {})
                accepted = sync_result.get("accepted", 0)
                conflicts = sync_result.get("conflicts", 0)
                if accepted > 0 or conflicts > 0:
                    msg = f"Εισήχθησαν {accepted} αλλαγές"
                    if conflicts > 0:
                        msg += f", {conflicts} συγκρούσεις"
                    Logger.info(f"SYNC: {msg}")
                    # Optionally show notification to user
        except Exception as e:
            Logger.warning(f"SYNC: Startup sync error: {e}")

    def _perform_sync(self):
        """Execute the sync cycle with the desktop sync_service."""
        try:
            from sync_service import run_sync_cycle
            from android_sync_utils import ensure_android_sync_tree, ensure_android_backup_tree, resolve_android_sync_root, resolve_android_backup_root
            from config_manager import get_app_setting
            
            Logger.info("SYNC: Initializing sync...")
            
            # Get database path
            db_path = getattr(self, "local_db_path", None)
            if not db_path or not os.path.exists(db_path):
                Logger.warning("SYNC: No valid database path available")
                raise RuntimeError("Δεν φορτώθηκε βάση δεδομένων")
            
            # Create database connection
            conn = sqlite3.connect(db_path)
            
            sync_root = resolve_android_sync_root(db_path)
            backup_root = resolve_android_backup_root(db_path)
            
            # Ensure directory trees exist
            ensure_android_sync_tree(sync_root)
            ensure_android_backup_tree(backup_root)
            
            Logger.info(f"SYNC: Using sync_root: {sync_root}")
            Logger.info(f"SYNC: Using backup_root: {backup_root}")
            
            # Run the sync cycle (same as desktop)
            result = run_sync_cycle(
                conn,
                db_path=db_path,
                sync_root=sync_root,
                backup_root=backup_root,
                actor="android_app",
                create_backup_on_change=bool(get_app_setting("sync_backup_on_change", True)),
                hot_keep=int(get_app_setting("backup_hot_keep", 3) or 3),
            )
            
            conn.close()
            Logger.info(f"SYNC: Sync cycle completed: {result}")
            return result
            
        except Exception as e:
            Logger.error(f"SYNC: Error during sync: {e}")
            raise

    def _on_sync_complete(self, result):
        """Handle successful sync completion."""
        self.sync_btn.disabled = False
        self.sync_btn.text = "Sync"
        
        if not result:
            self.show_error(S.get("MESSAGES", {}).get("SYNC_ERROR", "Σφάλμα κατά τον συγχρονισμό"))
            return
        
        # Show result summary
        sync_result = result.get("sync", {})
        accepted = sync_result.get("accepted", 0)
        already_applied = sync_result.get("already_applied", 0)
        conflicts = sync_result.get("conflicts", 0)
        
        if accepted > 0 or conflicts > 0:
            msg = f"Συγχρονισμός ολοκληρώθηκε\nΕισήχθησαν: {accepted}"
            if conflicts > 0:
                msg += f"\nΣυγκρούσεις: {conflicts}"
        elif already_applied > 0:
            msg = f"Συγχρονισμός ολοκληρώθηκε\nΌλες οι αλλαγές ήδη εφαρμοσμένες ({already_applied})"
        else:
            msg = f"Συγχρονισμός ολοκληρώθηκε\nΔεν βρέθηκαν νέες αλλαγές"
        
        self.show_error(msg, is_info=True)
        
        # Refresh display
        self.load_substations(None)

    def _on_sync_error(self, error_msg):
        """Handle sync error."""
        self.sync_btn.disabled = False
        self.sync_btn.text = "Sync"
        self.show_error(f"Σφάλμα συγχρονισμού:\n{error_msg}")

    def _show_sync_settings(self):
        """Show sync settings popup for configuring sync folder."""
        try:
            from config_manager import get_app_setting, set_app_setting
            
            p = Popup(
                title=S.get("MESSAGES", {}).get("SYNC_SETTINGS", "Ρυθμίσεις Συγχρονισμού"),
                size_hint=(0.95, 0.6)
            )
            layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
            
            # Sync enabled checkbox
            sync_enabled_row = BoxLayout(size_hint_y=None, height=40, spacing=10)
            sync_enabled_row.add_widget(Label(
                text=S.get("MESSAGES", {}).get("SYNC_AUTO_ENABLED_LABEL", "Αυτόματος συγχρονισμός:"),
                size_hint_x=0.7
            ))
            from kivy.uix.checkbox import CheckBox
            sync_chk = CheckBox(
                active=bool(get_app_setting("sync_auto_cycle_enabled", True)),
                size_hint_x=0.3
            )
            sync_enabled_row.add_widget(sync_chk)
            layout.add_widget(sync_enabled_row)
            
            # Sync root path display
            sync_root_path = get_app_setting("sync_root_path", "")
            path_row = BoxLayout(orientation="vertical", size_hint_y=None, height=80, spacing=5)
            path_row.add_widget(Label(
                text=S.get("MESSAGES", {}).get("SYNC_ROOT_PATH_LABEL", "Φάκελος Συγχρονισμού:"),
                size_hint_y=None,
                height=25
            ))
            
            from kivy.uix.textinput import TextInput
            path_input = TextInput(
                text=sync_root_path,
                multiline=False,
                size_hint_y=None,
                height=35
            )
            path_row.add_widget(path_input)
            
            path_row.add_widget(Label(
                text=S.get("MESSAGES", {}).get("SYNC_ROOT_PATH_HINT", "Ή αφήστε κενό για προεπιλογή (δίπλα στη ΒΔ)"),
                size_hint_y=None,
                height=20,
                color=(0.5, 0.5, 0.5, 1)
            ))
            layout.add_widget(path_row)
            
            # Buttons
            btn_layout = BoxLayout(size_hint_y=None, height=40, spacing=10)
            
            save_btn = Button(text=S.get("BUTTONS", {}).get("SAVE", "Αποθήκευση"))
            def _save(*_):
                set_app_setting("sync_auto_cycle_enabled", bool(sync_chk.active))
                if path_input.text.strip():
                    set_app_setting("sync_root_path", path_input.text.strip())
                else:
                    set_app_setting("sync_root_path", None)
                p.dismiss()
                self.show_error(S.get("MESSAGES", {}).get("SETTINGS_SAVED", "Ρυθμίσεις αποθηκεύτηκαν"), is_info=True)
            
            save_btn.bind(on_press=_save)
            btn_layout.add_widget(save_btn)
            
            close_btn = Button(text=S.get("BUTTONS", {}).get("CLOSE", "Κλείσιμο"))
            close_btn.bind(on_press=p.dismiss)
            btn_layout.add_widget(close_btn)
            
            layout.add_widget(btn_layout)
            p.content = layout
            p.open()
            
        except Exception as e:
            Logger.error(f"SYNC: Error showing sync settings: {e}")
            self.show_error(f"Σφάλμα: {str(e)}")

    def _copy_content_uri_to_file(self, uri):

        # Copy a content:// URI to a local file and return the path.
        # This attempts to use Android ContentResolver via pyjnius when running
        # on device. On other platforms it raises a RuntimeError.
        if not uri:
            raise RuntimeError("Empty URI")
        if not uri.startswith("content://"):
            raise RuntimeError("Not a content URI")
        try:
            from jnius import autoclass
        except Exception as e:
            raise RuntimeError(
                "Android pyjnius not available to copy content URI"
            ) from e

        try:
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Uri = autoclass("android.net.Uri")

            activity = PythonActivity.mActivity
            content_resolver = activity.getContentResolver()
            uri_obj = Uri.parse(uri)
            in_stream = content_resolver.openInputStream(uri_obj)

            # choose a local filename
            try:
                filename = os.path.basename(uri)
                if not filename or filename.strip() == "":
                    filename = "content_db.db"
            except Exception:
                filename = "content_db.db"

            target_dir = getattr(self, "user_data_dir", None) or os.path.join(
                os.getcwd(), "user_data"
            )
            os.makedirs(target_dir, exist_ok=True)
            target_path = os.path.join(target_dir, filename)

            # Write bytes from InputStream to local file (read one byte at a time)
            with open(target_path, "wb") as outp:
                while True:
                    b = in_stream.read()
                    if b == -1:
                        break
                    outp.write(bytes((b,)))
            try:
                in_stream.close()
            except Exception:
                pass
            return target_path
        except Exception as e:
            raise RuntimeError("Failed to copy content URI: " + str(e)) from e

    def _copy_content_uri_to_file_async(self, uri, on_result):
        """Copy content URI in background, show progress popup, then call on_result(success, value)."""
        popup = Popup(title="Αντιγραφή αρχείου...", size_hint=(0.9, 0.25))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        # Informational label with wrapping
        msg = Label(
            text=("Αντιγραφή αρχείου από το σύστημα αρχείων. Παρακαλώ περιμένετε..."),
            halign="left",
            valign="middle",
        )
        msg.size_hint_y = None

        def _bind_msg_width(instance, value):
            instance.text_size = (value, None)

        msg.bind(width=_bind_msg_width)
        msg.bind(texture_size=lambda inst, val: setattr(inst, "height", val[1]))

        # Add a ProgressBar when available; otherwise keep label only.
        progress = None
        try:
            from kivy.uix.progressbar import ProgressBar

            progress = ProgressBar(max=100, value=0)
            layout.add_widget(msg)
            layout.add_widget(progress)
        except Exception:
            layout.add_widget(msg)

        popup.content = layout
        popup.open()

        def finish(success, val):
            try:
                popup.dismiss()
            except Exception:
                pass
            try:
                on_result(success, val)
            except Exception as e:
                Logger.error(f"APP: Error in copy callback: {e}")

        def _worker():
            try:
                path = self._copy_content_uri_to_file(uri)
                # mark progress complete if progress bar is present
                try:
                    if progress is not None:
                        progress.value = getattr(progress, "max", 100)
                except Exception:
                    pass
                Clock.schedule_once(lambda _dt: finish(True, path), 0)
            except Exception as e:
                err = str(e)
                Clock.schedule_once(lambda _dt, _err=err: finish(False, _err), 0)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    def load_substations(self, instance):
        """Load substations from local database"""
        Logger.info("APP: ========== LOAD_SUBSTATIONS CALLED ==========")
        Logger.info(f"APP: Instance: {instance}")
        Logger.info(f"APP: Content layout exists: {hasattr(self, 'content_layout')}")
        # Ensure root buttons are visible when at root
        try:
            self._set_root_buttons_visible(True)
        except Exception:
            pass
        try:
            Logger.info("APP: Clearing content_layout widgets")
            self.content_layout.clear_widgets()
            Logger.info("APP: Creating loading label")
            loading_label = Label(text=S.get("MESSAGES", {}).get("LOADING", "Φόρτωση..."), size_hint_y=1)
            self.content_layout.add_widget(loading_label)
            Logger.info("APP: Loading label added")

            if not self.local_db_path:
                self.content_layout.clear_widgets()
                self.content_layout.add_widget(
                    Label(text=S.get("MESSAGES", {}).get("ENTER_PATH", "Επίλεξε αρχείο βάσης για να ξεκινήσεις."))
                )
                return

            try:
                self.substations = self._local_fetch_substations()
                Logger.info(f"APP: Loaded {len(self.substations)} local substations")
                # Only clear root.ids if the root widget exists (may be None during early startup)
                if getattr(self, "root", None) is not None:
                    try:
                        self.root.ids = {}
                    except Exception:
                        Logger.info("APP: Could not clear root.ids - skipping")
                self.display_substations()
            except Exception as e:
                Logger.error(f"APP: Local DB error: {str(e)}")
                self.show_error(f"Local DB error: {str(e)}")
            return

        except Exception as e:
            Logger.critical(f"APP: Error in load_substations: {str(e)}")
            Logger.critical(f"APP: Traceback: {traceback.format_exc()}")
            self.show_error(f"Error: {str(e)}")

    def display_substations(self):
        """Display substations in a large clickable matrix (name-only buttons)."""
        Logger.info("APP: ========== DISPLAY_SUBSTATIONS CALLED ==========")
        Logger.info(f"APP: Number of substations: {len(self.substations)}")
        self.content_layout.clear_widgets()
        Logger.info("APP: Content layout cleared")

        if not self.substations:
            Logger.info("APP: No substations found - showing message")
            self.content_layout.add_widget(Label(text=S.get("MESSAGES", {}).get("NO_SUBSTATIONS", "Κανένας υποσταθμός δεν βρέθηκε")))
            return

        scroll = ScrollView()
        grid = GridLayout(cols=2, spacing=12, size_hint_y=None, padding=10)
        grid.bind(minimum_height=grid.setter("height"))

        def _name_font_for_button(name_text):
            name_len = len((name_text or "").strip())
            if name_len >= 36:
                return 14
            if name_len >= 28:
                return 15
            if name_len >= 20:
                return 16
            return 18

        for substation in self.substations:
            name = substation.get("name", "-")
            name_font = _name_font_for_button(name)
            btn_text = f"[b][size={name_font}]{name}[/size][/b]"

            substation_btn = Button(
                text=btn_text,
                markup=True,
                size_hint_y=None,
                height=120,
                font_size='16sp',
                bold=True,
                halign='center',
                valign='middle',
                padding=[10, 8],
                background_color=(0.18, 0.34, 0.52, 1),
            )
            substation_btn.bind(
                size=lambda inst, _size: setattr(inst, "text_size", (inst.width - 20, inst.height - 12))
            )
            substation_btn.bind(
                on_press=lambda x, sid=substation["id"]: self.show_substation_details(sid)
            )
            grid.add_widget(substation_btn)

        scroll.add_widget(grid)
        self.content_layout.add_widget(scroll)

    def show_substation_details(self, substation_id):
        """Show details of a substation and its elements"""
        self.content_layout.clear_widgets()

        # Find substation
        substation = next(
            (s for s in self.substations if s["id"] == substation_id), None
        )
        if not substation:
            self.show_error(S.get("MESSAGES", {}).get("SUBSTATION_NOT_FOUND", "Substation not found"))
            return

        self.current_substation = substation

        # Hide root-level buttons when viewing a substation
        try:
            self._set_root_buttons_visible(False)
        except Exception:
            pass

        main_layout = BoxLayout(orientation="vertical", padding=10, spacing=15)

        # Substation header with desktop-like summary details
        header_layout = BoxLayout(orientation="vertical", size_hint_y=None, height=170, spacing=4)
        name_label = Label(
            text=substation["name"],
            bold=True,
            font_size="18sp",
            size_hint_y=None,
            height=30,
        )
        name_label.bind(size=lambda inst, _size: setattr(inst, "text_size", (inst.width, inst.height)))

        location = substation.get("location") or "-"
        location_text = (
            S.get("MESSAGES", {}).get("GOOGLE_MAPS_LINK", "Google Maps Link")
            if isinstance(location, str)
            and (location.startswith("http://") or location.startswith("https://"))
            else location
        )
        adoption_text = substation.get("adoption_date") or "-"
        elements_count = substation.get("elements_count", 0)
        gates_count = substation.get("gates_count", 0)
        capacitors_count = substation.get("capacitors_count", 0)
        maint_count = substation.get("maintenances_count", 0)
        last_maintenance = substation.get("last_maintenance") or "-"
        mono_status = "ΝΑΙ" if (substation.get("monogram_pdf") or "").strip() else "ΟΧΙ"

        location_label = Label(
            text=f"{S.get('MESSAGES', {}).get('LOC', 'Τοποθεσία')}: {location_text}",
            font_size="13sp",
            size_hint_y=None,
            height=25,
        )
        location_label.bind(size=lambda inst, _size: setattr(inst, "text_size", (inst.width, inst.height)))

        adoption_label = Label(
            text=f"{S.get('MESSAGES', {}).get('ADOPTION', 'Ανάληψη')}: {adoption_text}",
            font_size="13sp",
            size_hint_y=None,
            height=22,
        )
        adoption_label.bind(size=lambda inst, _size: setattr(inst, "text_size", (inst.width, inst.height)))

        counts_line_1 = Label(
            text=(
                f"{S.get('MESSAGES', {}).get('INFO', 'Στοιχεία')}: {elements_count}    "
                f"{S.get('MESSAGES', {}).get('GATES', 'Πύλες')}: {gates_count}    "
                f"{S.get('MESSAGES', {}).get('CAPACITORS', 'Πυκνωτές')}: {capacitors_count}"
            ),
            font_size="13sp",
            size_hint_y=None,
            height=22,
        )
        counts_line_1.bind(size=lambda inst, _size: setattr(inst, "text_size", (inst.width, inst.height)))

        counts_line_2 = Label(
            text=(
                f"{S.get('MESSAGES', {}).get('MAINTENANCES', 'Συντηρήσεις')}: {maint_count}    "
                f"{S.get('MESSAGES', {}).get('LAST', 'Τελευταία')}: {last_maintenance}    "
                f"{S.get('MESSAGES', {}).get('SINGLE_LINE', 'Μονογραμμικό')}: {mono_status}"
            ),
            font_size="13sp",
            size_hint_y=None,
            height=22,
        )
        counts_line_2.bind(size=lambda inst, _size: setattr(inst, "text_size", (inst.width, inst.height)))

        header_layout.add_widget(name_label)
        header_layout.add_widget(location_label)
        header_layout.add_widget(adoption_label)
        header_layout.add_widget(counts_line_1)
        header_layout.add_widget(counts_line_2)
        main_layout.add_widget(header_layout)

        # Load elements for this substation
        scroll = ScrollView()
        grid = GridLayout(cols=1, spacing=15, size_hint_y=None, padding=10)
        grid.bind(minimum_height=grid.setter("height"))

        self._load_substation_elements(substation_id, grid)

        scroll.add_widget(grid)
        main_layout.add_widget(scroll)

        # Fixed bottom action row to maximize list space and keep controls at the bottom.
        actions_container = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=74,
            spacing=8,
            padding=[0, 4, 0, 4],
        )

        maint_btn = Button(
            text=S.get("BUTTONS", {}).get("MAINTENANCE", "Συντήρηση"),
            font_size='16sp',
            bold=True,
            background_color=(0.2, 0.5, 0.7, 1)
        )
        maint_btn.bind(
            on_press=lambda x: self.show_maintenance_menu(substation_id, substation)
        )
        actions_container.add_widget(maint_btn)

        inspect_btn = Button(
            text=S.get("BUTTONS", {}).get("INSPECT", "Επιθεώρηση"),
            font_size='16sp',
            bold=True,
            background_color=(0.5, 0.5, 0.2, 1)
        )
        inspect_btn.bind(
            on_press=lambda x: self.show_inspection_entry_popup(substation_id, substation)
        )
        actions_container.add_widget(inspect_btn)

        back_btn = Button(
            text="< " + S.get("BUTTONS", {}).get("BACK", "Πίσω"),
            font_size='16sp',
            bold=True
        )
        back_btn.bind(on_press=lambda x: self.load_substations(None))
        actions_container.add_widget(back_btn)

        main_layout.add_widget(actions_container)
        self.content_layout.clear_widgets()
        self.content_layout.add_widget(main_layout)

    def _load_substation_elements(self, substation_id, grid):
        """Load and display elements for a substation"""
        grid.clear_widgets()
        loading_label = Label(text=S.get("MESSAGES", {}).get("LOADING_ELEMENTS", "Φόρτωση στοιχείων..."), size_hint_y=None, height=40)
        grid.add_widget(loading_label)

        if self.data_mode == "local":
            try:
                elements = self._local_fetch_elements(substation_id)
                if loading_label.parent:
                    grid.remove_widget(loading_label)
                if not elements:
                    grid.add_widget(
                        Label(text=S["MESSAGES"]["NO_ELEMENTS"], size_hint_y=None, height=40)
                    )
                    return
                for elem in elements:
                    # Compact card-style element display
                    elem_card = BoxLayout(
                        size_hint_y=None,
                        height=85,
                        spacing=5,
                        padding=[8, 5],
                        orientation="horizontal"
                    )

                    # Element info (main area)
                    info_layout = BoxLayout(orientation="vertical", size_hint_x=1, spacing=2)
                    
                    # Line 1: Type and name
                    elem_type_display = elem['element_type']
                    if elem.get("breaker_category"):
                        elem_type_display += f" ({elem['breaker_category']})"
                    
                    line1 = Label(
                        text=f"[b]{elem['name']}[/b] - {elem_type_display}",
                        markup=True,
                        font_size='15sp',
                        halign='left',
                        valign='middle',
                        size_hint_y=0.35
                    )
                    line1.bind(size=line1.setter('text_size'))
                    info_layout.add_widget(line1)
                    
                    # Line 2: S/N, manufacturer, model, ID (matching desktop format)
                    sn = elem.get('serial_number') or '-'
                    mfr = elem.get('model_manufacturer') or elem.get('manufacturer') or '-'
                    mdl = elem.get('model_name') or elem.get('model') or '-'
                    elem_id = elem.get('id', 'N/A')
                    line2 = Label(
                        text=f"S/N: {sn} | Κατ.: {mfr} | Μοντ.: {mdl} (id:{elem_id})",
                        font_size='12sp',
                        halign='left',
                        valign='middle',
                        color=(0.7, 0.7, 0.7, 1),
                        size_hint_y=0.3
                    )
                    line2.bind(size=line2.setter('text_size'))
                    info_layout.add_widget(line2)
                    
                    # Line 3: Voltage, year, status
                    voltage = elem.get('voltage_level', '-')
                    year = elem.get('manufacture_year', '')
                    status = elem.get('operating_status', '-')
                    
                    status_prefix = "[OK]" if status == "Ενεργή" else "[!]"
                    line3_text = f"{voltage}"
                    if year:
                        line3_text += f" | Έτος: {year}"
                    line3_text += f" | {status_prefix} {status}"
                    
                    line3 = Label(
                        text=line3_text,
                        font_size='12sp',
                        halign='left',
                        valign='top',
                        color=(0.6, 0.6, 0.6, 1),
                        size_hint_y=0.35
                    )
                    line3.bind(size=line3.setter('text_size'))
                    info_layout.add_widget(line3)
                    
                    elem_card.add_widget(info_layout)
                    
                    # Add maintenance history button on the right
                    try:
                        from ui.shared import IconOnlyButton
                        history_btn = IconOnlyButton(
                            icon_type="maintenance",
                            icon_color=(0.4, 0.6, 0.8, 1),
                            size=(50, 50)
                        )
                    except Exception:
                        # Fallback to text button if IconOnlyButton not available
                        history_btn = Button(
                            text="History",
                            font_size='12sp',
                            size_hint_x=None,
                            width=60,
                            background_color=(0.3, 0.6, 0.8, 1)
                        )
                    history_btn.bind(
                        on_press=lambda x, eid=elem.get('id'), ename=elem.get('name'): self.show_element_maintenance_history(eid, ename)
                    )
                    elem_card.add_widget(history_btn)
                    
                    grid.add_widget(elem_card)
            except Exception as e:
                if loading_label.parent:
                    grid.remove_widget(loading_label)
                grid.add_widget(
                    Label(text=f"Error: {str(e)}", size_hint_y=None, height=40)
                )
            return

    def show_add_substation_popup(self, instance):
        """Show popup to add a new substation"""
        popup = Popup(title=S["MESSAGES"].get("ADD_SUBSTATION_TITLE", "Προσθήκη Υποσταθμού"), size_hint=(0.95, 0.7))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        # Name input
        layout.add_widget(Label(text=S.get("MESSAGES", {}).get("SUBSTATION_NAME_LABEL", "Όνομα Υποσταθμού:"), size_hint_y=0.15))
        name_input = TextInput(hint_text=S.get("MESSAGES", {}).get("SUBSTATION_NAME_HINT", "Όνομα"), size_hint_y=0.15, multiline=False)
        layout.add_widget(name_input)

        # Location input
        layout.add_widget(Label(text=S.get("MESSAGES", {}).get("LOC", "Τοποθεσία:"), size_hint_y=0.15))
        location_input = TextInput(
            hint_text=S.get("MESSAGES", {}).get("LOC", "Τοποθεσία"), size_hint_y=0.15, multiline=False
        )
        layout.add_widget(location_input)

        # Adoption date input
        layout.add_widget(Label(text=S.get("MESSAGES", {}).get("ADOPTION_DATE_LABEL", "Ημερομηνία Υιοθέτησης:"), size_hint_y=0.15))
        date_input = TextInput(
            hint_text=S.get("MESSAGES", {}).get("DATE_HINT", "YYYY-MM-DD"), size_hint_y=0.15, multiline=False
        )
        layout.add_widget(date_input)

        # Buttons
        button_layout = BoxLayout(size_hint_y=0.2, spacing=10)

        def add_substation():
            if not name_input.text.strip():
                self.show_error(S.get("MESSAGES", {}).get("NAME_REQUIRED", "Το όνομα είναι υποχρεωτικό"))
                return

            try:
                payload = {
                    "name": name_input.text.strip(),
                    "location": location_input.text.strip(),
                    "adoption_date": date_input.text.strip(),
                    "division": "ΤΜΘ",
                }
                # Do not write to the main DB from Android; append to change log
                temp_id = f"android-{int(datetime.utcnow().timestamp() * 1000)}"
                self._append_change_log(
                    "insert", "substations", {**payload, "id": temp_id}
                )
                popup.dismiss()
                show_message_popup(S["TITLES"]["SUCCESS"], S.get("MESSAGES", {}).get("CHANGELOG_RECORDED", "Η αλλαγή καταγράφηκε στο change log."))
            except Exception as e:
                Logger.error(f"APP: Failed to append substation to change log: {e}")
                self.show_error(f"Local change log error: {str(e)}")

        add_btn = Button(text=S["BUTTONS"]["ADD"])
        add_btn.bind(on_press=lambda x: add_substation())
        button_layout.add_widget(add_btn)

        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
        cancel_btn.bind(on_press=popup.dismiss)
        button_layout.add_widget(cancel_btn)

        layout.add_widget(button_layout)
        popup.content = layout
        popup.open()

    def show_add_element_popup(self, substation_id):
        """Show popup to add a new element"""
        popup = Popup(title=S["MESSAGES"].get("ADD_ELEMENT_TITLE", "Προσθήκη Στοιχείου"), size_hint=(0.95, 0.9))
        main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        # Scrollable input area
        scroll = ScrollView()
        layout = BoxLayout(
            orientation="vertical", size_hint_y=None, padding=5, spacing=8
        )
        layout.bind(minimum_height=layout.setter("height"))

        def wrapped_label(text_value):
            label = Label(
                text=text_value, size_hint_y=None, halign="left", valign="middle"
            )
            label.bind(
                width=lambda instance, value: setattr(
                    instance, "text_size", (value, None)
                ),
                texture_size=lambda instance, value: setattr(
                    instance, "height", value[1] + 10
                ),
            )
            return label

        # Element type
        layout.add_widget(wrapped_label(S.get("MESSAGES", {}).get("ELEMENT_TYPE_LABEL", "Τύπος Στοιχείου:")))
        element_spinner = Spinner(
            text=self.ELEMENT_TYPES[0],
            values=self.ELEMENT_TYPES,
            size_hint_y=None,
            height=64,
        )
        layout.add_widget(element_spinner)

        # Dynamic fields
        field_inputs = {}
        for field in self.ELEMENT_FIELD_DEFS:
            layout.add_widget(wrapped_label(f"{field['label']}:"))
            if field.get("type") == "spinner":
                spinner = Spinner(
                    text=field["values"][0],
                    values=field["values"],
                    size_hint_y=None,
                    height=64,
                )
                field_inputs[field["key"]] = spinner
                layout.add_widget(spinner)
            else:
                ti = TextInput(
                    hint_text=field.get("hint", ""),
                    size_hint_y=None,
                    height=68,
                    multiline=False,
                    padding=[14, 14, 14, 14],
                )
                field_inputs[field["key"]] = ti
                layout.add_widget(ti)

        scroll.add_widget(layout)
        main_layout.add_widget(scroll)

        # Buttons
        button_layout = BoxLayout(size_hint_y=0.1, spacing=10)

        def add_element():
            if not field_inputs["name"].text.strip():
                self.show_error("Το όνομα είναι υποχρεωτικό")
                return

            # Get all field values, handling both text and spinner fields
            def get_field_value(key):
                field = field_inputs.get(key)
                if not field:
                    return ""
                return field.text.strip() if hasattr(field, "text") else ""

            payload = {
                "substation_id": substation_id,
                "element_type": element_spinner.text,
                "name": get_field_value("name"),
                "serial_number": get_field_value("serial_number"),
                "maintenance_date": get_field_value("maintenance_date"),
                "voltage_level": get_field_value("voltage_level"),
                "manufacturer": get_field_value("manufacturer"),
                "type": get_field_value("type"),
                "breaker_category": "",
                "manufacture_year": get_field_value("manufacture_year"),
                "model": get_field_value("model"),
                "model_version": get_field_value("model_version"),
                "operating_status": get_field_value("operating_status"),
                "installation_space": get_field_value("installation_space"),
                "maintenance_cycle": get_field_value("maintenance_cycle"),
                "gate": get_field_value("gate"),
                "is_main_switch": 0,
                "element_model_id": None,
            }

            try:
                # Do not write to the main DB from Android; append to change log
                temp_id = f"android-{int(datetime.utcnow().timestamp() * 1000)}"
                self._append_change_log(
                    "insert", "elements", {**payload, "id": temp_id}
                )
                popup.dismiss()
                show_message_popup(S["TITLES"]["SUCCESS"], "Η αλλαγή καταγράφηκε στο change log.")
            except Exception as e:
                Logger.error(f"APP: Failed to append element to change log: {e}")
                self.show_error(f"Local change log error: {str(e)}")

        add_btn = Button(text=S["BUTTONS"]["ADD"])
        add_btn.bind(on_press=lambda x: add_element())
        button_layout.add_widget(add_btn)

        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
        cancel_btn.bind(on_press=popup.dismiss)
        button_layout.add_widget(cancel_btn)

        main_layout.add_widget(button_layout)
        popup.content = main_layout
        popup.open()

    def delete_element(self, element_id):
        """Delete an element"""
        from reports import show_confirm

        def do_delete():
                try:
                    self._append_change_log("delete", "elements", {"id": element_id})
                    show_message_popup(S["TITLES"]["SUCCESS"], "Η αλλαγή καταγράφηκε στο change log.")
                except Exception as e:
                    self.show_error(f"Local DB error: {str(e)}")

        show_confirm(
            "Επιβεβαίωση Διαγραφής",
            "Είστε σίγουροι ότι θέλετε να διαγράψετε\nαυτό το στοιχείο;",
            yes_callback=do_delete,
            yes_color=(1, 0, 0, 1),
            yes_text=S.get("BUTTONS", {}).get("YES", "Ναι").upper(),
            no_text=S.get("BUTTONS", {}).get("NO", "Όχι").upper(),
        )

    def delete_substation(self, substation_id):
        """Delete a substation"""
        from reports import show_confirm

        def do_delete():
                try:
                    self._append_change_log("delete", "substations", {"id": substation_id})
                    show_message_popup(S["TITLES"]["SUCCESS"], "Η αλλαγή καταγράφηκε στο change log.")
                except Exception as e:
                    self.show_error(f"Local DB error: {str(e)}")

        show_confirm(
            "Επιβεβαίωση Διαγραφής",
            "Είστε σίγουροι ότι θέλετε να διαγράψετε\nαυτόν τον υποσταθμό και τα στοιχεία του;",
            yes_callback=do_delete,
            yes_color=(1, 0, 0, 1),
            yes_text=S.get("BUTTONS", {}).get("YES", "Ναι").upper(),
            no_text=S.get("BUTTONS", {}).get("NO", "Όχι").upper(),
        )

    def show_maintenance_menu(self, substation_id, substation):
        """Show maintenance recording interface"""
        from kivy.uix.checkbox import CheckBox
        from kivy.uix.spinner import Spinner
        from kivy.uix.widget import Widget

        popup = Popup(title=f"Συντήρηση - {substation['name']}", size_hint=(0.95, 0.95))
        main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        # Scrollable content area
        scroll = ScrollView(bar_width=10, size_hint=(1, 0.85))
        content_layout = BoxLayout(
            orientation="vertical", size_hint_y=None, padding=5, spacing=10
        )
        content_layout.bind(minimum_height=content_layout.setter("height"))

        def wrapped_label(text_value):
            label = Label(
                text=text_value, size_hint_y=None, halign="left", valign="middle"
            )
            label.bind(
                width=lambda instance, value: setattr(
                    instance, "text_size", (value, None)
                ),
                texture_size=lambda instance, value: setattr(
                    instance, "height", value[1] + 10
                ),
            )
            return label

        # Maintenance Type
        content_layout.add_widget(wrapped_label("Τύπος Συντήρησης:"))
        maint_type_spinner = Spinner(
            text=S.get("MESSAGES", {}).get("MAINT_TYPE_DEFAULT", "Επαναληπτική συντήρηση"),
            values=S.get("MESSAGES", {}).get("MAINTENANCE_TYPES", ["Επαναληπτική συντήρηση", "Βλάβη", "Οπτικός έλεγχος"]),
            size_hint_y=None,
            height=56,
        )
        content_layout.add_widget(maint_type_spinner)

        # Date/Time
        content_layout.add_widget(wrapped_label("Ημερομηνία & Ώρα:"))
        datetime_input = TextInput(
            text=datetime.now().strftime("%Y-%m-%d %H:%M"),
            hint_text="YYYY-MM-DD HH:MM",
            size_hint_y=None,
            height=60,
            multiline=False,
            padding=[12, 12, 12, 12],
        )
        content_layout.add_widget(datetime_input)

        # Overall comments (rendered outside the scrolling elements list
        # so it remains visible and cannot be overlapped while elements load)
        overall_comments = TextInput(
            hint_text=S.get("MESSAGES", {}).get("OVERALL_COMMENTS_HINT", "Γενικά σχόλια για την συντήρηση..."),
            size_hint_y=None,
            height=120,
            multiline=True,
            padding=[12, 12, 12, 12],
        )

        # Elements section
        content_layout.add_widget(
            Label(
                text=S.get("MESSAGES", {}).get("ELEMENTS_LIST_LABEL", "Στοιχεία που συντηρήθηκαν:"),
                size_hint_y=None,
                height=40,
                bold=True,
            )
        )
        loading_label = Label(text="Φόρτωση στοιχείων...", size_hint_y=None, height=40)
        content_layout.add_widget(loading_label)
        retry_btn = Button(
            text=S.get("MESSAGES", {}).get("RETRY_LOAD", "Επανάληψη φόρτωσης"),
            size_hint_y=None,
            height=40,
            disabled=True,
            opacity=0,
        )
        content_layout.add_widget(retry_btn)

        # Store element widgets
        element_widgets = {}

        def load_elements():
            """Load elements and create checkboxes with fields"""
            retry_btn.disabled = True
            retry_btn.opacity = 0
            if loading_label.parent is None:
                content_layout.add_widget(loading_label)

            if self.data_mode == "local":
                try:
                    elements = self._local_fetch_elements(substation_id)
                    if loading_label.parent:
                        content_layout.remove_widget(loading_label)
                    if not elements:
                        content_layout.add_widget(
                            Label(text=S["MESSAGES"]["NO_ELEMENTS"], size_hint_y=None, height=40)
                        )
                        return
                    for elem in elements:
                        # Element container
                        elem_box = BoxLayout(
                            orientation="vertical",
                            size_hint_y=None,
                            spacing=5,
                            padding=5,
                        )
                        elem_box.bind(minimum_height=elem_box.setter("height"))

                        elem_type_display = elem["element_type"]
                        if elem.get("breaker_category"):
                            elem_type_display += f" ({elem['breaker_category']})"

                        # Line 1: Name and type
                        elem_text = f"{elem['name']} - {elem_type_display}\n"
                        
                        # Line 2: S/N, manufacturer, model, ID (matching substation view format)
                        sn = elem.get('serial_number') or '-'
                        mfr = elem.get('model_manufacturer') or elem.get('manufacturer') or '-'
                        mdl = elem.get('model_name') or elem.get('model') or '-'
                        elem_id = elem.get('id', 'N/A')
                        elem_text += f"S/N: {sn} | Κατ.: {mfr} | Μοντ.: {mdl} (id:{elem_id})\n"
                        
                        # Line 3: Voltage, year, status
                        voltage = elem.get('voltage_level', '-')
                        year = elem.get('manufacture_year', '')
                        status = elem.get('operating_status', '-')
                        status_prefix = "[OK]" if status == "Ενεργή" else "[!]"
                        elem_text += f"{voltage}"
                        if year:
                            elem_text += f" | Έτος: {year}"
                        elem_text += f" | {status_prefix} {status}"

                        checkbox_layout = BoxLayout(
                            size_hint_y=None, spacing=10, padding=[0, 8, 0, 8]
                        )
                        checkbox_layout.bind(
                            minimum_height=checkbox_layout.setter("height")
                        )
                        # Larger checkboxes for easier tapping on Android
                        checkbox = CheckBox(size_hint=(None, None), size=(64, 64))
                        checkbox_layout.add_widget(checkbox)

                        elem_label = Label(
                            text=elem_text,
                            size_hint_x=1,
                            size_hint_y=None,
                            halign="left",
                            valign="top",
                        )
                        elem_label.bind(
                            width=lambda instance, value: setattr(
                                instance, "text_size", (value, None)
                            ),
                            texture_size=lambda instance, value: setattr(
                                instance, "height", max(80, value[1] + 16)
                            ),
                        )
                        checkbox_layout.add_widget(elem_label)
                        elem_box.add_widget(checkbox_layout)

                        details_container = BoxLayout(
                            orientation="vertical", size_hint_y=None, spacing=5
                        )
                        details_container.bind(
                            minimum_height=details_container.setter("height")
                        )

                        # Allow comments to expand vertically with content for better readability on mobile
                        elem_comments = TextInput(
                            hint_text=S.get("MESSAGES", {}).get("ELEM_COMMENTS_HINT", "Σχόλια για αυτό το στοιχείο..."),
                            size_hint_y=None,
                            height=56,
                            multiline=True,
                            padding=[12, 12, 12, 12],
                        )

                        def _adjust_comments_height(instance, value):
                            try:
                                lines = max(1, instance.text.count("\n") + 1)
                                # approximate line height multiplier
                                instance.height = max(56, min(300, lines * 28))
                            except Exception:
                                instance.height = 56

                        elem_comments.bind(text=_adjust_comments_height)
                        details_container.add_widget(elem_comments)

                        measurements = {}
                        measurements_toggle = None
                        measurements_fields_container = None
                        elem_type = elem["element_type"]
                        breaker_category = elem.get("breaker_category", "")
                        
                        is_breaker = elem_type in [
                            S.get("MESSAGES", {}).get("ELEMENT_BREAKER_YT", "Διακόπτης ΥΤ"),
                            S.get("MESSAGES", {}).get("ELEMENT_BREAKER_MT", "Διακόπτης ΜΤ"),
                        ]
                        is_transformer = self._is_transformer(elem_type) and not is_breaker
                        has_measurement_form = bool(is_breaker or is_transformer)
                        
                        is_sf6_breaker = is_breaker and breaker_category == "SF6"
                        is_hv_sf6 = elem_type == S.get("MESSAGES", {}).get("ELEMENT_BREAKER_YT", "Διακόπτης ΥΤ") and breaker_category == "SF6"
                        is_mv_sf6 = elem_type == S.get("MESSAGES", {}).get("ELEMENT_BREAKER_MT", "Διακόπτης ΜΤ") and breaker_category == "SF6"
                        is_vacuum_breaker = is_breaker and breaker_category in ["Κενού", "Vacuum"] and elem_type == S.get("MESSAGES", {}).get("ELEMENT_BREAKER_MT", "Διακόπτης ΜΤ")

                        # Add measurements toggle checkbox if element has measurement form
                        if has_measurement_form:
                            measurements_toggle_row = BoxLayout(
                                size_hint_y=None, height=50, spacing=10, padding=[5, 5]
                            )
                            measurements_toggle_row.add_widget(
                                Label(text="Στοιχεία Μετρήσεων:", size_hint_x=0.8)
                            )
                            measurements_toggle = CheckBox(
                                size_hint_x=0.2, size_hint_y=1
                            )
                            measurements_toggle_row.add_widget(measurements_toggle)
                            details_container.add_widget(measurements_toggle_row)

                            # Create measurements fields container (initially NOT added to parent)
                            measurements_fields_container = BoxLayout(
                                size_hint_y=None, spacing=5, orientation="vertical"
                            )
                            measurements_fields_container.bind(
                                minimum_height=measurements_fields_container.setter("height")
                            )

                        # Standard breaker measurements (exclude HV SF6 breakers - they have their own form)
                        if is_breaker and not is_hv_sf6 and measurements_fields_container:
                            measurements_fields_container.add_widget(
                                wrapped_label("Μονώσεις (Κλειστό):")
                            )
                            for phase in ["fa", "fb", "fc"]:
                                phase_label = {
                                    "fa": "Φάση A",
                                    "fb": "Φάση B",
                                    "fc": "Φάση C",
                                }[phase]
                                phase_layout = BoxLayout(
                                    size_hint_y=None, height=60, spacing=8
                                )
                                phase_layout.add_widget(
                                    Label(text=f"{phase_label}:", size_hint_x=0.25)
                                )
                                value_input = TextInput(
                                    hint_text="Τιμή",
                                    size_hint_x=0.5,
                                    multiline=False,
                                    height=50,
                                    padding=[10, 10, 10, 10],
                                )
                                phase_layout.add_widget(value_input)
                                unit_spinner = Spinner(
                                    text="GΩ",
                                    values=["GΩ", "MΩ", "kΩ"],
                                    size_hint_x=0.25,
                                )
                                phase_layout.add_widget(unit_spinner)
                                measurements_fields_container.add_widget(phase_layout)
                                measurements[f"ins_closed_{phase}"] = value_input
                                measurements[f"ins_closed_{phase}_unit"] = unit_spinner

                            measurements_fields_container.add_widget(
                                wrapped_label("Μονώσεις (Ανοιχτό):")
                            )
                            for phase in ["fa", "fb", "fc"]:
                                phase_label = {
                                    "fa": "Φάση A-A",
                                    "fb": "Φάση B-B",
                                    "fc": "Φάση C-C",
                                }[phase]
                                phase_layout = BoxLayout(
                                    size_hint_y=None, height=60, spacing=8
                                )
                                phase_layout.add_widget(
                                    Label(text=f"{phase_label}:", size_hint_x=0.25)
                                )
                                value_input = TextInput(
                                    hint_text="Τιμή",
                                    size_hint_x=0.5,
                                    multiline=False,
                                    height=50,
                                    padding=[10, 10, 10, 10],
                                )
                                phase_layout.add_widget(value_input)
                                unit_spinner = Spinner(
                                    text="GΩ",
                                    values=["GΩ", "MΩ", "kΩ"],
                                    size_hint_x=0.25,
                                )
                                phase_layout.add_widget(unit_spinner)
                                measurements_fields_container.add_widget(phase_layout)
                                measurements[f"ins_open_{phase}"] = value_input
                                measurements[f"ins_open_{phase}_unit"] = unit_spinner

                            measurements_fields_container.add_widget(
                                wrapped_label("Αντίσταση Επαφών (μΩ):")
                            )
                            for phase in ["fa", "fb", "fc"]:
                                phase_label = {
                                    "fa": "Φάση A",
                                    "fb": "Φάση B",
                                    "fc": "Φάση C",
                                }[phase]
                                phase_layout = BoxLayout(
                                    size_hint_y=None, height=60, spacing=8
                                )
                                phase_layout.add_widget(
                                    Label(text=f"{phase_label}:", size_hint_x=0.3)
                                )
                                value_input = TextInput(
                                    hint_text="Τιμή μΩ",
                                    size_hint_x=0.7,
                                    multiline=False,
                                    height=50,
                                    padding=[10, 10, 10, 10],
                                )
                                phase_layout.add_widget(value_input)
                                measurements_fields_container.add_widget(phase_layout)
                                measurements[f"cont_{phase}"] = value_input

                            # Operations counter for all breakers
                            measurements_fields_container.add_widget(
                                wrapped_label("Μετρητής Χειρισμών:")
                            )
                            ops_layout = BoxLayout(size_hint_y=None, height=60, spacing=8)
                            ops_layout.add_widget(
                                Label(text="Αριθμός Χειρισμών:", size_hint_x=0.4)
                            )
                            ops_input = TextInput(
                                hint_text="Τιμή",
                                size_hint_x=0.6,
                                multiline=False,
                                height=50,
                                padding=[10, 10, 10, 10],
                            )
                            ops_layout.add_widget(ops_input)
                            measurements_fields_container.add_widget(ops_layout)
                            measurements["operations_count"] = ops_input

                        # Medium voltage SF6-specific measurements (added to standard breaker form)
                        if is_mv_sf6 and measurements_fields_container:
                            # SF6 Leakage
                            leak_layout = BoxLayout(size_hint_y=None, height=60, spacing=8)
                            leak_layout.add_widget(
                                Label(text="Διαρροή SF6 (kg):", size_hint_x=0.5)
                            )
                            mv_sf6_leak_input = TextInput(
                                hint_text="kg",
                                size_hint_x=0.5,
                                multiline=False,
                                height=50,
                                padding=[10, 10, 10, 10],
                            )
                            leak_layout.add_widget(mv_sf6_leak_input)
                            measurements_fields_container.add_widget(leak_layout)
                            measurements["mv_sf6_leakage_kg"] = mv_sf6_leak_input
                            
                            # SF6 Leak Methodology
                            method_layout = BoxLayout(size_hint_y=None, height=60, spacing=8)
                            method_layout.add_widget(
                                Label(text="Πλήρωση/Αντικατάσταση (Μεθοδολογία):", size_hint_x=0.5)
                            )
                            mv_sf6_method_input = TextInput(
                                hint_text="Μεθοδολογία",
                                size_hint_x=0.5,
                                multiline=False,
                                height=50,
                                padding=[10, 10, 10, 10],
                            )
                            method_layout.add_widget(mv_sf6_method_input)
                            measurements_fields_container.add_widget(method_layout)
                            measurements["mv_sf6_leak_methodology"] = mv_sf6_method_input
                            
                            # Quality header
                            measurements_fields_container.add_widget(
                                wrapped_label("ΠΟΙΟΤΗΤΑ ΑΕΡΙΟΥ SF6:")
                            )
                            
                            # Table header row
                            quality_header = BoxLayout(size_hint_y=None, height=40, spacing=8)
                            quality_header.add_widget(Label(text="", size_hint_x=0.15))
                            quality_header.add_widget(Label(text="SF6/N2 (%)", size_hint_x=0.28, bold=True))
                            quality_header.add_widget(Label(text="H2O (°C atm)", size_hint_x=0.28, bold=True))
                            quality_header.add_widget(Label(text="SO2 (ppm)", size_hint_x=0.29, bold=True))
                            measurements_fields_container.add_widget(quality_header)
                            
                            # Phase rows
                            for phase, phase_label in [("fa", "ΦΑ"), ("fb", "ΦΒ"), ("fc", "ΦΓ")]:
                                phase_layout = BoxLayout(size_hint_y=None, height=50, spacing=8)
                                phase_layout.add_widget(
                                    Label(text=f"{phase_label}:", size_hint_x=0.15)
                                )
                                
                                # SF6/N2
                                sf6n2_input = TextInput(
                                    hint_text="0.0",
                                    size_hint_x=0.28,
                                    multiline=False,
                                    height=50,
                                    padding=[10, 10, 10, 10],
                                )
                                phase_layout.add_widget(sf6n2_input)
                                measurements[f"mv_sf6_n2_{phase}"] = sf6n2_input
                                
                                # H2O
                                h2o_input = TextInput(
                                    hint_text="0.0",
                                    size_hint_x=0.28,
                                    multiline=False,
                                    height=50,
                                    padding=[10, 10, 10, 10],
                                )
                                phase_layout.add_widget(h2o_input)
                                measurements[f"mv_h2o_{phase}"] = h2o_input
                                
                                # SO2
                                so2_input = TextInput(
                                    hint_text="0.0",
                                    size_hint_x=0.29,
                                    multiline=False,
                                    height=50,
                                    padding=[10, 10, 10, 10],
                                )
                                phase_layout.add_widget(so2_input)
                                measurements[f"mv_so2_{phase}"] = so2_input
                                
                                measurements_fields_container.add_widget(phase_layout)

                        # VIDAR measurements for vacuum breakers (single row layout matching desktop)
                        if is_vacuum_breaker and measurements_fields_container:
                            measurements_fields_container.add_widget(
                                wrapped_label("ΕΛΕΓΧΟΣ ΚΕΝΟΥ (VIDAR):")
                            )
                            
                            # Single row with all three phases
                            vidar_layout = BoxLayout(size_hint_y=None, height=50, spacing=4)
                            
                            # Phase A
                            vidar_layout.add_widget(Label(text="ΦΑ-ΦΑ:", size_hint_x=0.15))
                            vidar_fa_input = TextInput(
                                hint_text="0.0",
                                size_hint_x=0.25,
                                multiline=False,
                                height=50,
                                padding=[10, 10, 10, 10],
                            )
                            vidar_layout.add_widget(vidar_fa_input)
                            measurements["vidar_fa"] = vidar_fa_input
                            
                            # Phase B
                            vidar_layout.add_widget(Label(text="ΦΒ-ΦΒ:", size_hint_x=0.15))
                            vidar_fb_input = TextInput(
                                hint_text="0.0",
                                size_hint_x=0.25,
                                multiline=False,
                                height=50,
                                padding=[10, 10, 10, 10],
                            )
                            vidar_layout.add_widget(vidar_fb_input)
                            measurements["vidar_fb"] = vidar_fb_input
                            
                            # Phase C
                            vidar_layout.add_widget(Label(text="ΦΓ-ΦΓ:", size_hint_x=0.15))
                            vidar_fc_input = TextInput(
                                hint_text="0.0",
                                size_hint_x=0.05,
                                multiline=False,
                                height=50,
                                padding=[10, 10, 10, 10],
                            )
                            vidar_layout.add_widget(vidar_fc_input)
                            measurements["vidar_fc"] = vidar_fc_input
                            
                            measurements_fields_container.add_widget(vidar_layout)

                        # High-voltage SF6-specific form (only for ΥΤ & SF6)
                        if is_hv_sf6 and measurements_fields_container:
                            # Operations counter header
                            measurements_fields_container.add_widget(
                                wrapped_label("ΜΕΤΡΗΤΗΣ ΧΕΙΡΙΣΜΩΝ")
                            )
                            hv_ops_layout = BoxLayout(size_hint_y=None, height=60, spacing=8)
                            hv_ops_layout.add_widget(
                                Label(text="Αριθμός Χειρισμών:", size_hint_x=0.6)
                            )
                            hv_ops_input = TextInput(
                                hint_text="Τιμή",
                                size_hint_x=0.4,
                                multiline=False,
                                height=50,
                                padding=[10, 10, 10, 10],
                            )
                            hv_ops_layout.add_widget(hv_ops_input)
                            measurements_fields_container.add_widget(hv_ops_layout)
                            measurements["hv_sf6_operations_count"] = hv_ops_input
                            
                            # Breaker status section
                            measurements_fields_container.add_widget(
                                wrapped_label("ΚΑΤΑΣΤΑΣΗ ΔΙΑΚΟΠΤΗ")
                            )
                            
                            # Lubrication checkbox
                            lubrication_row = BoxLayout(size_hint_y=None, height=60, spacing=8)
                            lubrication_row.add_widget(
                                Label(text="Λίπανση μηχανισμού αρθρώσεων:", size_hint_x=0.7)
                            )
                            lubrication_cb = CheckBox(
                                size_hint=(None, None),
                                size=(40, 40),
                            )
                            lubrication_row.add_widget(lubrication_cb)
                            measurements_fields_container.add_widget(lubrication_row)
                            measurements["hv_sf6_lubrication"] = lubrication_cb
                            
                            # Leak check (free text)
                            leak_check_input = TextInput(
                                hint_text="Έλεγχος Διαρροών Sf6",
                                multiline=False,
                                size_hint_y=None,
                                height=50,
                                padding=[10, 10, 10, 10],
                            )
                            measurements_fields_container.add_widget(leak_check_input)
                            measurements["hv_sf6_leak_check"] = leak_check_input
                            
                            # Refill SF6 checkbox
                            refill_row = BoxLayout(size_hint_y=None, height=60, spacing=8)
                            refill_row.add_widget(
                                Label(text="Συμπλήρωση Sf6:", size_hint_x=0.7)
                            )
                            refill_cb = CheckBox(
                                size_hint=(None, None),
                                size=(40, 40),
                            )
                            refill_row.add_widget(refill_cb)
                            measurements_fields_container.add_widget(refill_row)
                            measurements["hv_sf6_refill"] = refill_cb
                            
                            # Synchronization check (free text)
                            synch_check_input = TextInput(
                                hint_text="Έλεγχος ταυτοχρονισμού",
                                multiline=False,
                                size_hint_y=None,
                                height=50,
                                padding=[10, 10, 10, 10],
                            )
                            measurements_fields_container.add_widget(synch_check_input)
                            measurements["hv_sf6_synch_check"] = synch_check_input
                            
                            # Wash insulators (free text)
                            wash_insulators_input = TextInput(
                                hint_text="Πλύσιμο Μονωτήρων – Έλεγχος Φθοράς",
                                multiline=False,
                                size_hint_y=None,
                                height=50,
                                padding=[10, 10, 10, 10],
                            )
                            measurements_fields_container.add_widget(wash_insulators_input)
                            measurements["hv_sf6_wash_insulators"] = wash_insulators_input
                            
                            # Corrosion check (free text)
                            corrosion_check_input = TextInput(
                                hint_text="Έλεγχος Διάβρωσης Εξωτερικών Μεταλλικών Τμημάτων",
                                multiline=False,
                                size_hint_y=None,
                                height=50,
                                padding=[10, 10, 10, 10],
                            )
                            measurements_fields_container.add_widget(corrosion_check_input)
                            measurements["hv_sf6_corrosion_check"] = corrosion_check_input
                            
                            # Resistance measurement header
                            measurements_fields_container.add_widget(
                                wrapped_label("Μέτρηση Αντίστασης Διαβάσεως (MΩ)")
                            )
                            
                            # Resistance header row
                            raid_header = BoxLayout(size_hint_y=None, height=40, spacing=8)
                            raid_header.add_widget(Label(text="Α(ΦΑΣΗ)", size_hint_x=0.33))
                            raid_header.add_widget(Label(text="Β(ΦΑΣΗ)", size_hint_x=0.33))
                            raid_header.add_widget(Label(text="C(ΦΑΣΗ)", size_hint_x=0.34))
                            measurements_fields_container.add_widget(raid_header)
                            
                            # Resistance input row
                            raid_row = BoxLayout(size_hint_y=None, height=50, spacing=8)
                            raid_a_input = TextInput(
                                hint_text="0.0",
                                multiline=False,
                                height=50,
                                padding=[10, 10, 10, 10],
                            )
                            raid_b_input = TextInput(
                                hint_text="0.0",
                                multiline=False,
                                height=50,
                                padding=[10, 10, 10, 10],
                            )
                            raid_c_input = TextInput(
                                hint_text="0.0",
                                multiline=False,
                                height=50,
                                padding=[10, 10, 10, 10],
                            )
                            raid_row.add_widget(raid_a_input)
                            raid_row.add_widget(raid_b_input)
                            raid_row.add_widget(raid_c_input)
                            measurements_fields_container.add_widget(raid_row)
                            measurements["hv_sf6_resistance_a"] = raid_a_input
                            measurements["hv_sf6_resistance_b"] = raid_b_input
                            measurements["hv_sf6_resistance_c"] = raid_c_input

                        # Transformer measurements - comprehensive maintenance form matching desktop app
                        if is_transformer and measurements_fields_container:
                            # ΧΕΙΡΙΣΜΟΙ (Operations)
                            measurements_fields_container.add_widget(
                                wrapped_label("ΧΕΙΡΙΣΜΟΙ")
                            )
                            satyf_layout = BoxLayout(size_hint_y=None, height=60, spacing=8)
                            satyf_layout.add_widget(
                                Label(text="Απαριθμητής ΣΑΤΥΦ:", size_hint_x=0.5)
                            )
                            satyf_counter = TextInput(
                                hint_text="Αριθμός Χειρισμών",
                                size_hint_x=0.5,
                                multiline=False,
                                height=50,
                                padding=[10, 10, 10, 10],
                            )
                            satyf_layout.add_widget(satyf_counter)
                            measurements_fields_container.add_widget(satyf_layout)
                            measurements["satyf_counter"] = satyf_counter

                            # 1. ΜΟΝΩΤΗΡΕΣ Υ.Τ & Μ.Τ (Insulators HV & MV)
                            measurements_fields_container.add_widget(
                                wrapped_label("1. ΜΟΝΩΤΗΡΕΣ Υ.Τ & Μ.Τ")
                            )
                            ins_fracture = TextInput(hint_text="ΕΛΕΓΧΟΣ ΓΙΑ ΘΡΑΥΣΗ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(ins_fracture)
                            measurements["insulators_fracture_check"] = ins_fracture
                            
                            ins_leaks = TextInput(hint_text="ΔΙΑΡΡΟΕΣ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(ins_leaks)
                            measurements["insulators_leaks"] = ins_leaks
                            
                            ins_cleaning = TextInput(hint_text="ΚΑΘΑΡΙΣΜΟΣ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(ins_cleaning)
                            measurements["insulators_cleaning"] = ins_cleaning
                            
                            ins_spikes = TextInput(hint_text="ΑΚΙΔΕΣ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(ins_spikes)
                            measurements["insulators_spikes"] = ins_spikes

                            # 2. ΛΑΔΙΑ Μ/Σ (Transformer Oils)
                            measurements_fields_container.add_widget(
                                wrapped_label("2. ΛΑΔΙΑ Μ/Σ")
                            )
                            oil_level = TextInput(hint_text="ΕΛΕΓΧΟΣ ΣΤΑΘΜΗΣ ΕΛΑΙΟΥ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(oil_level)
                            measurements["oil_level_check"] = oil_level
                            
                            oil_filling = TextInput(hint_text="ΣΥΜΠΛΗΡΩΣΗ ΕΛΑΙΟΥ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(oil_filling)
                            measurements["oil_filling"] = oil_filling
                            
                            silica_row = BoxLayout(size_hint_y=None, height=60, spacing=8)
                            silica_row.add_widget(Label(text="ΣΙΛΙΚΑ:", size_hint_x=0.3))
                            silica_spinner = Spinner(
                                text="N/A",
                                values=["OK", "NOT OK", "N/A"],
                                size_hint_x=0.7,
                            )
                            silica_row.add_widget(silica_spinner)
                            measurements_fields_container.add_widget(silica_row)
                            measurements["silica_check"] = silica_spinner

                            # 3. ΑΚΡΟΔΕΚΤΕΣ ΣΥΝΔΕΣΜΟΙ (Terminals Connectors)
                            measurements_fields_container.add_widget(
                                wrapped_label("3. ΑΚΡΟΔΕΚΤΕΣ ΣΥΝΔΕΣΜΟΙ")
                            )
                            term_bolts = TextInput(hint_text="ΕΛΕΓΧΟΣ ΣΥΣΦΙΞΗΣ ΚΟΧΛΙΩΝ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(term_bolts)
                            measurements["terminals_bolt_tightness"] = term_bolts
                            
                            term_connectors = TextInput(hint_text="ΕΛΕΓΧΟΣ ΕΥΚΑΜΠΤΩΝ ΣΥΝΔΕΣΜΩΝ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(term_connectors)
                            measurements["terminals_flexible_connectors"] = term_connectors

                            # 4. ΣΩΜΑ Μ/Σ (Transformer Body)
                            measurements_fields_container.add_widget(
                                wrapped_label("4. ΣΩΜΑ Μ/Σ")
                            )
                            body_leaks = TextInput(hint_text="ΕΛΕΓΧΟΣ ΔΙΑΡΡΟΩΝ ΕΛΑΙΟΥ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(body_leaks)
                            measurements["body_oil_leaks"] = body_leaks
                            
                            body_sealing = TextInput(hint_text="ΣΤΕΓΑΝΟΠΟΙΗΣΗ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(body_sealing)
                            measurements["body_sealing"] = body_sealing
                            
                            body_cleaning = TextInput(hint_text="ΚΑΘΑΡΙΣΜΟΣ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(body_cleaning)
                            measurements["body_cleaning"] = body_cleaning
                            
                            body_relief = TextInput(hint_text="ΕΛΕΓΧΟΣ ΑΝΑΚΟΥΦΙΣΤΙΚΩΝ ΒΑΛΒΙΔΩΝ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(body_relief)
                            measurements["body_relief_valves"] = body_relief
                            
                            body_pressure = TextInput(hint_text="ΕΛΕΓΧΟΣ ΠΡΕΣΣΟΣΤΑΤΙΚΩΝ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(body_pressure)
                            measurements["body_pressure_gauges"] = body_pressure
                            
                            body_bucholz = TextInput(hint_text="ΕΛΕΓΧΟΣ BUCHOLZ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(body_bucholz)
                            measurements["body_bucholz"] = body_bucholz

                            # ΈΛΕΓΧΟΣ ΘΕΡΜΟΣΤΟΙΧΕΙΩΝ (Temperature Thermocouple Check)
                            measurements_fields_container.add_widget(
                                wrapped_label("ΈΛΕΓΧΟΣ ΘΕΡΜΟΣΤΟΙΧΕΙΩΝ (°C)")
                            )
                            
                            # Temperature header row
                            temp_header = BoxLayout(size_hint_y=None, height=40, spacing=8)
                            temp_header.add_widget(Label(text="", size_hint_x=0.2))
                            temp_header.add_widget(Label(text="OIL", size_hint_x=0.26))
                            temp_header.add_widget(Label(text="X1", size_hint_x=0.26))
                            temp_header.add_widget(Label(text="X3", size_hint_x=0.28))
                            measurements_fields_container.add_widget(temp_header)

                            # FAN row
                            fan_row = BoxLayout(size_hint_y=None, height=50, spacing=8)
                            fan_row.add_widget(Label(text="FAN", size_hint_x=0.2))
                            fan_oil = TextInput(hint_text="", multiline=False, height=50, padding=[10, 10, 10, 10])
                            fan_x1 = TextInput(hint_text="", multiline=False, height=50, padding=[10, 10, 10, 10])
                            fan_x3 = TextInput(hint_text="", multiline=False, height=50, padding=[10, 10, 10, 10])
                            fan_row.add_widget(fan_oil)
                            fan_row.add_widget(fan_x1)
                            fan_row.add_widget(fan_x3)
                            measurements_fields_container.add_widget(fan_row)
                            measurements["temp_fan_oil"] = fan_oil
                            measurements["temp_fan_x1"] = fan_x1
                            measurements["temp_fan_x3"] = fan_x3

                            # ALARM row
                            alarm_row = BoxLayout(size_hint_y=None, height=50, spacing=8)
                            alarm_row.add_widget(Label(text="ALARM", size_hint_x=0.2))
                            alarm_oil = TextInput(hint_text="", multiline=False, height=50, padding=[10, 10, 10, 10])
                            alarm_x1 = TextInput(hint_text="", multiline=False, height=50, padding=[10, 10, 10, 10])
                            alarm_x3 = TextInput(hint_text="", multiline=False, height=50, padding=[10, 10, 10, 10])
                            alarm_row.add_widget(alarm_oil)
                            alarm_row.add_widget(alarm_x1)
                            alarm_row.add_widget(alarm_x3)
                            measurements_fields_container.add_widget(alarm_row)
                            measurements["temp_alarm_oil"] = alarm_oil
                            measurements["temp_alarm_x1"] = alarm_x1
                            measurements["temp_alarm_x3"] = alarm_x3

                            # TRIP row
                            trip_row = BoxLayout(size_hint_y=None, height=50, spacing=8)
                            trip_row.add_widget(Label(text="TRIP", size_hint_x=0.2))
                            trip_oil = TextInput(hint_text="", multiline=False, height=50, padding=[10, 10, 10, 10])
                            trip_x1 = TextInput(hint_text="", multiline=False, height=50, padding=[10, 10, 10, 10])
                            trip_x3 = TextInput(hint_text="", multiline=False, height=50, padding=[10, 10, 10, 10])
                            trip_row.add_widget(trip_oil)
                            trip_row.add_widget(trip_x1)
                            trip_row.add_widget(trip_x3)
                            measurements_fields_container.add_widget(trip_row)
                            measurements["temp_trip_oil"] = trip_oil
                            measurements["temp_trip_x1"] = trip_x1
                            measurements["temp_trip_x3"] = trip_x3

                            # 5. ΣΑΤΥΦ - ΜΗΧΑΝΙΣΜΟΣ (SATYF - Mechanism)
                            measurements_fields_container.add_widget(
                                wrapped_label("5. ΣΑΤΥΦ - ΜΗΧΑΝΙΣΜΟΣ")
                            )
                            satyf_gas_transmission = TextInput(hint_text="ΈΛΕΓΧΟΣ ΑΕΟΝΩΝ ΜΕΤΑΔΟΣΗΣ ΚΙΝΗΣΗΣ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(satyf_gas_transmission)
                            measurements["satyf_gas_transmission_check"] = satyf_gas_transmission
                            
                            satyf_joints_cleaning = TextInput(hint_text="ΚΑΘΑΡΙΣΜΟΣ, ΛΙΠΑΝΣΗ ΑΡΘΡΟΣΕΩΝ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(satyf_joints_cleaning)
                            measurements["satyf_joints_cleaning_lubrication"] = satyf_joints_cleaning
                            
                            satyf_gears_cleaning = TextInput(hint_text="ΚΑΘΑΡΙΣΜΟΣ, ΛΙΠΑΝΣΗ ΟΔΟΝΤΟΤΩΝ ΤΡΟΧΩΝ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(satyf_gears_cleaning)
                            measurements["satyf_gears_cleaning_lubrication"] = satyf_gears_cleaning
                            
                            satyf_test_operations = TextInput(hint_text="ΔΟΚΙΜΑΣΤΙΚΟΙ ΧΕΙΡΙΣΜΟΙ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(satyf_test_operations)
                            measurements["satyf_test_operations"] = satyf_test_operations
                            
                            satyf_diverter_cracks = TextInput(hint_text="ΈΛΕΓΧΟΣ ΡΟΓΜΩΝ ΣΤΟ ΧΩΡΟ ΤΟΥ DIVERTER", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(satyf_diverter_cracks)
                            measurements["satyf_diverter_cracks_check"] = satyf_diverter_cracks

                            # 6. DIVERTER - ΜΕΤΑΓΩΓΙΚΟΣ ΔΙΑΚΟΠΤΗΣ (Transfer Switch)
                            measurements_fields_container.add_widget(
                                wrapped_label("6. DIVERTER - ΜΕΤΑΓΩΓΙΚΟΣ ΔΙΑΚΟΠΤΗΣ")
                            )
                            diverter_contacts = TextInput(hint_text="ΈΛΕΓΧΟΣ ΕΠΑΦΩΝ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(diverter_contacts)
                            measurements["diverter_contacts_check"] = diverter_contacts
                            
                            diverter_connections = TextInput(hint_text="ΣΥΝΔΕΣΕΙΣ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(diverter_connections)
                            measurements["diverter_connections"] = diverter_connections
                            
                            diverter_oil_change = TextInput(hint_text="ΑΛΛΑΓΗ ΛΑΔΙΩΝ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(diverter_oil_change)
                            measurements["diverter_oil_change"] = diverter_oil_change
                            
                            diverter_alarm = TextInput(hint_text="ΈΛΕΓΧΟΣ ALARM ΧΑΜΗΛΗΣ ΣΤΑΘΜΗΣ ΛΑΔΙΟΥ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(diverter_alarm)
                            measurements["diverter_low_level_alarm_check"] = diverter_alarm

                            # ΜΕΤΡΗΣΗ ΑΝΤΙΣΤΑΣΗΣ (Ohm) - Resistance Measurement
                            measurements_fields_container.add_widget(
                                wrapped_label("ΜΕΤΡΗΣΗ ΑΝΤΙΣΤΑΣΗΣ (Ohm)")
                            )
                            
                            # Resistance header row
                            resist_header = BoxLayout(size_hint_y=None, height=40, spacing=8)
                            resist_header.add_widget(Label(text="", size_hint_x=0.2))
                            resist_header.add_widget(Label(text="H1-1", size_hint_x=0.4))
                            resist_header.add_widget(Label(text="H1-2", size_hint_x=0.4))
                            measurements_fields_container.add_widget(resist_header)

                            # H1 row
                            h1_row = BoxLayout(size_hint_y=None, height=50, spacing=8)
                            h1_1 = TextInput(hint_text="", multiline=False, height=50, padding=[10, 10, 10, 10])
                            h1_2 = TextInput(hint_text="", multiline=False, height=50, padding=[10, 10, 10, 10])
                            h1_row.add_widget(Label(text="H1", size_hint_x=0.2))
                            h1_row.add_widget(h1_1)
                            h1_row.add_widget(h1_2)
                            measurements_fields_container.add_widget(h1_row)
                            measurements["resistance_h1_1"] = h1_1
                            measurements["resistance_h1_2"] = h1_2

                            # H2 row
                            h2_row = BoxLayout(size_hint_y=None, height=50, spacing=8)
                            h2_1 = TextInput(hint_text="", multiline=False, height=50, padding=[10, 10, 10, 10])
                            h2_2 = TextInput(hint_text="", multiline=False, height=50, padding=[10, 10, 10, 10])
                            h2_row.add_widget(Label(text="H2", size_hint_x=0.2))
                            h2_row.add_widget(h2_1)
                            h2_row.add_widget(h2_2)
                            measurements_fields_container.add_widget(h2_row)
                            measurements["resistance_h2_1"] = h2_1
                            measurements["resistance_h2_2"] = h2_2

                            # H3 row
                            h3_row = BoxLayout(size_hint_y=None, height=50, spacing=8)
                            h3_1 = TextInput(hint_text="", multiline=False, height=50, padding=[10, 10, 10, 10])
                            h3_2 = TextInput(hint_text="", multiline=False, height=50, padding=[10, 10, 10, 10])
                            h3_row.add_widget(Label(text="H3", size_hint_x=0.2))
                            h3_row.add_widget(h3_1)
                            h3_row.add_widget(h3_2)
                            measurements_fields_container.add_widget(h3_row)
                            measurements["resistance_h3_1"] = h3_1
                            measurements["resistance_h3_2"] = h3_2

                            # 7. ΑΝΤΙΣΤΑΣΗΣ ΚΟΜΒΟΥ Μ/Σ (Node Resistance)
                            measurements_fields_container.add_widget(
                                wrapped_label("7. ΑΝΤΙΣΤΑΣΗΣ ΚΟΜΒΟΥ Μ/Σ")
                            )
                            node_resistance_cleaning = TextInput(hint_text="ΚΑΘΑΡΙΣΜΟΣ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(node_resistance_cleaning)
                            measurements["node_resistance_cleaning"] = node_resistance_cleaning

                            # 8. Μ/Σ ΤΑΣΕΟΣ (Voltage Transformer)
                            measurements_fields_container.add_widget(
                                wrapped_label("8. Μ/Σ ΤΑΣΕΟΣ")
                            )
                            vt_visual_check = TextInput(hint_text="ΟΠΤΙΚΟΣ ΕΛΕΓΧΟΣ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(vt_visual_check)
                            measurements["vt_visual_check"] = vt_visual_check
                            
                            vt_leakage_check = TextInput(hint_text="ΕΛΕΓΧΟΣ ΔΙΑΡΡΟΩΝ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(vt_leakage_check)
                            measurements["vt_leakage_check"] = vt_leakage_check
                            
                            vt_tightness_check = TextInput(hint_text="ΕΛΕΓΧΟΣ ΣΥΣΦΙΞΕΩΝ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(vt_tightness_check)
                            measurements["vt_tightness_check"] = vt_tightness_check
                            
                            vt_insulation_check = TextInput(hint_text="ΕΛΕΓΧΟΣ ΑΝΤΙΣΤΑΣΗΣ ΜΟΝΩΣΗΣ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(vt_insulation_check)
                            measurements["vt_insulation_resistance_check"] = vt_insulation_check

                            # 9. Μ/Σ ΕΝΤΑΣΕΟΣ (Current Transformer)
                            measurements_fields_container.add_widget(
                                wrapped_label("9. Μ/Σ ΕΝΤΑΣΕΟΣ")
                            )
                            ct_visual_check = TextInput(hint_text="ΟΠΤΙΚΟΣ ΕΛΕΓΧΟΣ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(ct_visual_check)
                            measurements["ct_visual_check"] = ct_visual_check
                            
                            ct_leakage_check = TextInput(hint_text="ΕΛΕΓΧΟΣ ΔΙΑΡΡΟΩΝ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(ct_leakage_check)
                            measurements["ct_leakage_check"] = ct_leakage_check
                            
                            ct_tightness_check = TextInput(hint_text="ΕΛΕΓΧΟΣ ΣΥΣΦΙΞΕΩΝ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(ct_tightness_check)
                            measurements["ct_tightness_check"] = ct_tightness_check
                            
                            ct_insulation_check = TextInput(hint_text="ΕΛΕΓΧΟΣ ΑΝΤΙΣΤΑΣΗΣ ΜΟΝΩΣΗΣ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(ct_insulation_check)
                            measurements["ct_insulation_resistance_check"] = ct_insulation_check

                            # 10. Μ/Σ ΕΓΧΥΣΕΟΣ (Injection Transformer)
                            measurements_fields_container.add_widget(
                                wrapped_label("10. Μ/Σ ΕΓΧΥΣΕΟΣ")
                            )
                            it_visual_check = TextInput(hint_text="ΟΠΤΙΚΟΣ ΕΛΕΓΧΟΣ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(it_visual_check)
                            measurements["it_visual_check"] = it_visual_check
                            
                            it_leakage_check = TextInput(hint_text="ΕΛΕΓΧΟΣ ΔΙΑΡΡΟΩΝ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(it_leakage_check)
                            measurements["it_leakage_check"] = it_leakage_check
                            
                            it_tightness_check = TextInput(hint_text="ΕΛΕΓΧΟΣ ΣΥΣΦΙΞΕΩΝ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(it_tightness_check)
                            measurements["it_tightness_check"] = it_tightness_check
                            
                            it_insulation_check = TextInput(hint_text="ΕΛΕΓΧΟΣ ΑΝΤΙΣΤΑΣΗΣ ΜΟΝΩΣΗΣ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(it_insulation_check)
                            measurements["it_insulation_resistance_check"] = it_insulation_check

                            # 11. ΑΛΕΞΙΚΕΡΑΥΝΑ (Lightning Arresters)
                            measurements_fields_container.add_widget(
                                wrapped_label("11. ΑΛΕΞΙΚΕΡΑΥΝΑ")
                            )
                            arr_visual_check = TextInput(hint_text="ΟΠΤΙΚΟΣ ΕΛΕΓΧΟΣ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(arr_visual_check)
                            measurements["arresters_visual_check"] = arr_visual_check
                            
                            arr_tightness_check = TextInput(hint_text="ΕΛΕΓΧΟΣ ΣΥΣΦΙΞΕΩΝ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(arr_tightness_check)
                            measurements["arresters_tightness_check"] = arr_tightness_check
                            
                            arr_insulation_check = TextInput(hint_text="ΕΛΕΓΧΟΣ ΑΝΤΙΣΤΑΣΗΣ ΜΟΝΩΣΗΣ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(arr_insulation_check)
                            measurements["arresters_insulation_resistance_check"] = arr_insulation_check

                            # 12. Α/Ζ ΒΜΣ (HV Breaker)
                            measurements_fields_container.add_widget(
                                wrapped_label("12. Α/Ζ ΒΜΣ")
                            )
                            hv_breaker_visual = TextInput(hint_text="ΟΠΤΙΚΟΣ ΕΛΕΓΧΟΣ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(hv_breaker_visual)
                            measurements["hv_breaker_visual_check"] = hv_breaker_visual
                            
                            hv_breaker_cleaning = TextInput(hint_text="ΚΑΘΑΡΙΣΜΟΣ, ΛΙΠΑΝΣΗ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(hv_breaker_cleaning)
                            measurements["hv_breaker_cleaning_lubrication"] = hv_breaker_cleaning
                            
                            hv_breaker_tightness = TextInput(hint_text="ΕΛΕΓΧΟΣ ΣΥΣΦΙΞΕΩΝ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(hv_breaker_tightness)
                            measurements["hv_breaker_tightness_check"] = hv_breaker_tightness

                            # 13. Α/Ζ ΤΑΣΕΟΣ (Voltage Breaker)
                            measurements_fields_container.add_widget(
                                wrapped_label("13. Α/Ζ ΤΑΣΕΟΣ")
                            )
                            vbreaker_visual = TextInput(hint_text="ΟΠΤΙΚΟΣ ΕΛΕΓΧΟΣ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(vbreaker_visual)
                            measurements["voltage_breaker_visual_check"] = vbreaker_visual
                            
                            vbreaker_cleaning = TextInput(hint_text="ΚΑΘΑΡΙΣΜΟΣ, ΛΙΠΑΝΣΗ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(vbreaker_cleaning)
                            measurements["voltage_breaker_cleaning_lubrication"] = vbreaker_cleaning
                            
                            vbreaker_tightness = TextInput(hint_text="ΕΛΕΓΧΟΣ ΣΥΣΦΙΞΕΩΝ", multiline=False, size_hint_y=None, height=50)
                            measurements_fields_container.add_widget(vbreaker_tightness)
                            measurements["voltage_breaker_tightness_check"] = vbreaker_tightness

                        # Toggle measurements visibility based on checkbox
                        def toggle_measurements(cb, value, mfc=measurements_fields_container, dc=details_container):
                            if mfc is None:
                                return
                            # Add or remove measurements container from parent
                            if value:
                                # Show: add container if not already there
                                if mfc.parent is None:
                                    dc.add_widget(mfc)
                            else:
                                # Hide: remove container from parent
                                if mfc.parent is not None:
                                    dc.remove_widget(mfc)

                        if measurements_toggle:
                            measurements_toggle.bind(active=toggle_measurements)

                        def toggle_details(
                            cb, value, eb=elem_box, dc=details_container
                        ):
                            if value:
                                if dc not in eb.children:
                                    eb.add_widget(dc)
                            else:
                                if dc in eb.children:
                                    eb.remove_widget(dc)

                        checkbox.bind(active=toggle_details)
                        content_layout.add_widget(elem_box)

                        element_widgets[elem["id"]] = {
                            "checkbox": checkbox,
                            "comments": elem_comments,
                            "measurements": measurements,
                            "elem_type": elem["element_type"],
                        }
                except Exception as e:
                    if loading_label.parent:
                        content_layout.remove_widget(loading_label)
                    retry_btn.disabled = False
                    retry_btn.opacity = 1
                    self.show_error(f"Error loading elements: {str(e)}")
                return

        retry_btn.bind(on_press=lambda _x: load_elements())

        Clock.schedule_once(lambda *_args: load_elements(), 0)

        # Place the overall comments in a fixed container above the elements scroll
        comments_container = BoxLayout(
            orientation="vertical", size_hint_y=None, height=160
        )
        comments_container.add_widget(wrapped_label(S.get("MESSAGES", {}).get("OVERALL_COMMENTS_LABEL", "Γενικά Σχόλια:")))
        comments_container.add_widget(overall_comments)
        main_layout.add_widget(comments_container)

        scroll.add_widget(content_layout)
        main_layout.add_widget(scroll)

        # Buttons
        button_layout = BoxLayout(size_hint_y=0.15, spacing=10)

        def save_maintenance():
            # Validate
            selected_elements = [
                (eid, widgets)
                for eid, widgets in element_widgets.items()
                if widgets["checkbox"].active
            ]

            if not selected_elements:
                self.show_error("Πρέπει να επιλέξετε τουλάχιστον ένα στοιχείο!")
                return

            if not datetime_input.text.strip():
                self.show_error("Η ημερομηνία είναι υποχρεωτική!")
                return

            # Prepare payload
            maintenance_elements = []
            for elem_id, widgets in selected_elements:
                elem_data = {
                    "element_id": elem_id,
                    "element_comments": widgets["comments"].text.strip(),
                }

                # Add measurements if available
                measurements = widgets["measurements"]
                if measurements:
                    for key, widget in measurements.items():
                        if hasattr(widget, "text"):
                            try:
                                elem_data[key] = (
                                    float(widget.text) if widget.text.strip() else None
                                )
                            except ValueError:
                                elem_data[key] = None
                        else:  # Spinner
                            elem_data[key] = widget.text

                maintenance_elements.append(elem_data)

            payload = {
                "substation_id": substation_id,
                "date_time": datetime_input.text.strip(),
                "overall_comments": overall_comments.text.strip(),
                "maintenance_type": maint_type_spinner.text,
                "elements": maintenance_elements,
            }

            try:
                # On Android we do NOT write changes directly to the main DB.
                # Append an insert entry to the change log which the desktop app
                # will later import. Generate a temporary client-side id.
                temp_id = f"android-{int(datetime.utcnow().timestamp() * 1000)}"
                self._append_change_log(
                    "insert", "maintenance", {"id": temp_id, **payload}
                )
                popup.dismiss()
                show_message_popup(S["TITLES"]["SUCCESS"], S["MESSAGES"]["MAINTENANCE_SAVED_CHANGELOG"])
            except Exception as e:
                Logger.error(f"APP: Failed to append maintenance to change log: {e}")
                self.show_error(f"Local change log error: {str(e)}")

        save_btn = Button(text=S["BUTTONS"]["SAVE"])
        save_btn.bind(on_press=lambda x: save_maintenance())
        button_layout.add_widget(save_btn)

        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
        cancel_btn.bind(on_press=popup.dismiss)
        button_layout.add_widget(cancel_btn)

        main_layout.add_widget(button_layout)
        popup.content = main_layout
        popup.open()

    def show_inspection_entry_popup(self, substation_id, substation):
        """Add a new inspection entry"""

        popup = Popup(
            title=f"Νέα Επιθεώρηση - {substation['name']}", size_hint=(0.95, 0.85)
        )
        main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        scroll = ScrollView(bar_width=10, size_hint=(1, 0.8))
        layout = BoxLayout(
            orientation="vertical", size_hint_y=None, padding=5, spacing=10
        )
        layout.bind(minimum_height=layout.setter("height"))

        def wrapped_label(text_value, bold=False):
            label = Label(
                text=text_value,
                size_hint_y=None,
                halign="left",
                valign="middle",
                bold=bold,
                markup=bold,
            )
            label.bind(
                width=lambda instance, value: setattr(
                    instance, "text_size", (value, None)
                ),
                texture_size=lambda instance, value: setattr(
                    instance, "height", value[1] + 10
                ),
            )
            return label

        layout.add_widget(wrapped_label("Ημερομηνία Επιθεώρησης:"))
        date_input = TextInput(
            text=datetime.now().strftime("%Y-%m-%d"),
            hint_text="YYYY-MM-DD",
            size_hint_y=None,
            height=68,
            multiline=False,
            padding=[14, 14, 14, 14],
        )
        layout.add_widget(date_input)

        field_inputs = []
        for field in self.INSPECTION_FIELDS:
            if isinstance(field, dict) and field.get("type") == "section":
                layout.add_widget(
                    wrapped_label(f"[b]{field.get('title')}[/b]", bold=True)
                )
                continue

            row = BoxLayout(size_hint_y=None, spacing=8)
            row.bind(minimum_height=row.setter("height"))

            label = Label(
                text=str(field),
                size_hint_x=0.62,
                size_hint_y=None,
                halign="left",
                valign="top",
            )
            label.bind(
                width=lambda instance, value: setattr(
                    instance, "text_size", (value, None)
                ),
                texture_size=lambda instance, value: (
                    setattr(instance, "height", value[1] + 10),
                    setattr(row, "height", max(value[1] + 10, 100)),
                ),
            )

            ti = TextInput(
                hint_text="Παρατηρήσεις",
                size_hint_x=0.38,
                size_hint_y=None,
                height=90,
                multiline=True,
                padding=[12, 12, 12, 12],
            )
            ti.bind(
                height=lambda _instance, _value: setattr(
                    row, "height", max(row.height, ti.height)
                )
            )

            row.add_widget(label)
            row.add_widget(ti)
            layout.add_widget(row)
            field_inputs.append((str(field), ti))

        scroll.add_widget(layout)
        main_layout.add_widget(scroll)

        button_layout = BoxLayout(size_hint_y=None, height=60, spacing=10)

        def save_inspection():
            if not date_input.text.strip():
                self.show_error("Η ημερομηνία είναι υποχρεωτική!")
                return

            fields_payload = [
                {"label": label, "value": ti.text.strip()} for label, ti in field_inputs
            ]
            payload = {
                "substation_id": substation_id,
                "inspection_date": date_input.text.strip(),
                "data_json": json.dumps({"fields": fields_payload}, ensure_ascii=False),
                "substation_name": substation.get("name"),
                "month_key": date_input.text.strip()[:7],
                "source_file": "android-local",
                "created_at": datetime.now().strftime("%Y-%m-%d"),
            }

            try:
                # Do not write to the main DB from Android; append to change log
                temp_id = f"android-{int(datetime.utcnow().timestamp() * 1000)}"
                self._append_change_log(
                    "insert", "inspections", {**payload, "id": temp_id}
                )
                popup.dismiss()
                show_message_popup(S["TITLES"]["SUCCESS"], S.get("MESSAGES", {}).get("CHANGELOG_RECORDED", "Η αλλαγή καταγράφηκε στο change log."))
            except Exception as e:
                Logger.error(f"APP: Failed to append inspection to change log: {e}")
                self.show_error(f"Local change log error: {str(e)}")

        save_btn = Button(text=S["BUTTONS"]["SAVE"])
        save_btn.bind(on_press=lambda x: save_inspection())
        button_layout.add_widget(save_btn)

        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
        cancel_btn.bind(on_press=popup.dismiss)
        button_layout.add_widget(cancel_btn)

        main_layout.add_widget(button_layout)
        popup.content = main_layout
        popup.open()

    def show_element_maintenance_history(self, element_id, element_name):
        """Show maintenance history for a specific element"""
        try:
            if not self.local_db_path or not os.path.exists(self.local_db_path):
                self.show_error("Δεν υπάρχει φορτωμένη βάση δεδομένων")
                return
            
            conn = sqlite3.connect(self.local_db_path)
            c = conn.cursor()
            
            # Query all maintenances where this element was maintained
            c.execute(
                """
                SELECT m.id, m.date_time, m.maintenance_type, m.overall_comments,
                       me.element_comments, s.name as substation_name,
                       me.insulation_closed_fa_ground, me.insulation_closed_fb_ground, me.insulation_closed_fc_ground,
                       me.contact_resistance_fa_fa, me.contact_resistance_fb_fb, me.contact_resistance_fc_fc,
                       me.operations_count
                FROM maintenance m
                JOIN maintenance_elements me ON m.id = me.maintenance_id
                JOIN substations s ON m.substation_id = s.id
                WHERE me.element_id = ?
                ORDER BY m.date_time DESC
                """,
                (element_id,),
            )
            maintenance_records = c.fetchall()
            conn.close()
            
            # Create popup
            popup = Popup(
                title=f"Ιστορικό Συντηρήσεων - {element_name}",
                size_hint=(0.95, 0.9)
            )
            main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
            
            if not maintenance_records:
                main_layout.add_widget(
                    Label(
                        text="Δεν υπάρχει ιστορικό συντηρήσεων για αυτό το στοιχείο",
                        size_hint_y=0.8,
                    )
                )
            else:
                # Scrollable history list
                scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
                grid = GridLayout(cols=1, spacing=15, size_hint_y=None, padding=10)
                grid.bind(minimum_height=grid.setter("height"))
                
                for (
                    maint_id,
                    date_time,
                    maint_type,
                    overall_comments,
                    element_comments,
                    substation_name,
                    insul_fa_gnd,
                    insul_fb_gnd,
                    insul_fc_gnd,
                    contact_res_fa,
                    contact_res_fb,
                    contact_res_fc,
                    operations_count,
                ) in maintenance_records:
                    # Container for this maintenance record
                    maint_layout = BoxLayout(
                        size_hint_y=None,
                        orientation="vertical",
                        spacing=5,
                        padding=10
                    )
                    
                    # Calculate height based on content
                    base_height = 120
                    if element_comments:
                        base_height += 30
                    if insul_fa_gnd or insul_fb_gnd or insul_fc_gnd:
                        base_height += 30
                    if contact_res_fa or contact_res_fb or contact_res_fc:
                        base_height += 30
                    maint_layout.height = base_height
                    
                    # Header with date and type
                    header_text = f"[b]{date_time}[/b] - {substation_name}"
                    if maint_type:
                        header_text += f" ({maint_type})"
                    header_label = Label(
                        text=header_text,
                        size_hint_y=None,
                        height=30,
                        markup=True,
                        halign="left",
                        valign="middle"
                    )
                    header_label.bind(
                        width=lambda instance, value: setattr(instance, "text_size", (value, None))
                    )
                    maint_layout.add_widget(header_label)
                    
                    # Element-specific data
                    data_parts = []
                    if element_comments:
                        data_parts.append(f"{S['MESSAGES'].get('ELEMENT_COMMENTS_LABEL', 'Σχόλια Στοιχείου:')} {element_comments}")
                    
                    # Add measurements if present
                    measurements = []
                    if insul_fa_gnd:
                        measurements.append(f"Μόν. FA-GND: {insul_fa_gnd}")
                    if insul_fb_gnd:
                        measurements.append(f"FB-GND: {insul_fb_gnd}")
                    if insul_fc_gnd:
                        measurements.append(f"FC-GND: {insul_fc_gnd}")
                    if contact_res_fa:
                        measurements.append(f"Αντ. Επαφ. FA: {contact_res_fa}")
                    if contact_res_fb:
                        measurements.append(f"FB: {contact_res_fb}")
                    if contact_res_fc:
                        measurements.append(f"FC: {contact_res_fc}")
                    if operations_count:
                        measurements.append(f"Λειτουργίες: {operations_count}")
                    
                    if measurements:
                        data_parts.append(" | ".join(measurements))
                    
                    if data_parts:
                        data_text = "\n".join(data_parts)
                    else:
                        data_text = "Δεν υπάρχουν συγκεκριμένα δεδομένα για το στοιχείο"
                    
                    data_label = Label(
                        text=data_text,
                        size_hint_y=None,
                        height=50 if measurements else 30,
                        markup=True,
                        halign="left",
                        valign="top",
                        color=(0.5, 0.5, 0.5, 1)
                    )
                    data_label.bind(
                        width=lambda instance, value: setattr(instance, "text_size", (value, None))
                    )
                    maint_layout.add_widget(data_label)
                    
                    # Add overall comments if present
                    if overall_comments:
                        comments_label = Label(
                            text=f"Σχόλια: {overall_comments}",
                            size_hint_y=None,
                            height=40,
                            halign="left",
                            valign="top",
                            color=(0.6, 0.5, 0.4, 1)
                        )
                        comments_label.bind(
                            width=lambda instance, value: setattr(instance, "text_size", (value, None))
                        )
                        maint_layout.add_widget(comments_label)
                    
                    grid.add_widget(maint_layout)
                
                scroll.add_widget(grid)
                main_layout.add_widget(scroll)
            
            # Close button
            close_btn = Button(text=S["BUTTONS"].get("CLOSE", "Κλείσιμο"), size_hint_y=0.1)
            close_btn.bind(on_press=popup.dismiss)
            main_layout.add_widget(close_btn)
            
            popup.content = main_layout
            popup.open()
            
        except Exception as e:
            Logger.error(f"APP: Error showing element maintenance history: {e}")
            self.show_error(f"Σφάλμα: {str(e)}")

    def show_error(self, message, is_info=False):
        """Show error or info popup"""

        # Ensure popup creation runs on the Kivy main thread (some callers may be on worker threads)
        def _show(dt=None):
            try:
                from strings_proxy import STRINGS as S
                title = S["TITLES"].get("INFO", "Πληροφορία") if is_info else S["TITLES"]["ERROR"]
                show_message_popup(title, message)
            except Exception as e:
                Logger.error(f"APP: show_error failed to open popup: {e}")

        Clock.schedule_once(_show, 0)

    def _launch_share_intent(self, file_path):
        """Launch Android share chooser for a file. Uses FileProvider when available.

        This method is isolated so tests can monkeypatch `jnius.autoclass` and
        verify behavior without needing nested closures.
        """
        if not file_path:
            raise RuntimeError("No file path provided")
        try:
            from jnius import autoclass

            Intent = autoclass("android.content.Intent")
            Uri = autoclass("android.net.Uri")
            File = autoclass("java.io.File")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            current = PythonActivity.mActivity
            f = File(file_path)

            FileProvider = autoclass("androidx.core.content.FileProvider")
            authority = current.getPackageName() + ".provider"
            try:
                uri = FileProvider.getUriForFile(current, authority, f)
                # If FileProvider produced a file:// URI for some reason,
                # fall back to copying to external cache and retry.
                if uri is not None and str(uri.toString()).startswith("file://"):
                    try:
                        ext_cache = current.getExternalCacheDir()
                        if ext_cache is not None:
                            dest = File(ext_cache.getAbsolutePath() + "/" + f.getName())
                            shutil.copyfile(f.getAbsolutePath(), dest.getAbsolutePath())
                            uri = FileProvider.getUriForFile(current, authority, dest)
                    except Exception:
                        pass
            except Exception:
                # If provider isn't available, copy file to external cache
                # and use a file-based Uri there (some devices may allow it).
                try:
                    ext_cache = current.getExternalCacheDir()
                    if ext_cache is not None:
                        dest = File(ext_cache.getAbsolutePath() + "/" + f.getName())
                        shutil.copyfile(f.getAbsolutePath(), dest.getAbsolutePath())
                        uri = Uri.fromFile(dest)
                    else:
                        uri = Uri.fromFile(f)
                except Exception:
                    uri = Uri.fromFile(f)

            intent = Intent(Intent.ACTION_SEND)
            # Use a binary/* wildcard so the EXTRA_STREAM is treated as a Uri
            intent.setType("*/*")

            # Prefer using ClipData for content:// URIs to avoid Intent.putExtra
            # overload ambiguity that may treat the Uri as a Java String.
            try:
                # Use explicit Java String and ContentResolver instances to avoid
                # ambiguous overload selection in jnius.
                cr = current.getContentResolver()
                ClipData = autoclass("android.content.ClipData")
                JavaString = autoclass("java.lang.String")
                # Create a ClipData holding the Uri and attach it to the intent
                clip = ClipData.newUri(cr, JavaString("change-log"), uri)
                intent.setClipData(clip)
                # Also attempt to include EXTRA_STREAM for receivers that expect it.
                # Some jnius environments may pick the wrong overload; if that
                # happens, fall back to sending the string form.
                try:
                    intent.putExtra(Intent.EXTRA_STREAM, uri)
                except TypeError:
                    try:
                        intent.putExtra(Intent.EXTRA_STREAM, uri.toString())
                    except Exception:
                        # Ignore: keep ClipData as primary delivery mechanism
                        pass
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            except Exception:
                # Fallback: still attempt to put EXTRA_STREAM and grant permission
                try:
                    try:
                        intent.putExtra(Intent.EXTRA_STREAM, uri)
                    except TypeError:
                        intent.putExtra(Intent.EXTRA_STREAM, uri.toString())
                    intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                except Exception:
                    # Let the outer except handle showing error
                    raise

            # Use java.lang.String to ensure the chooser title is passed as a
            # CharSequence (avoid jnius overload confusion). Fall back to a
            # plain Python string if java.lang.String isn't available (tests/shims).
            try:
                JavaString = autoclass("java.lang.String")
                title_obj = JavaString("Share change-log")
            except Exception:
                title_obj = "Share change-log"
            chooser = Intent.createChooser(intent, title_obj)
            current.startActivity(chooser)
        except Exception:
            # Surface the error to the user (useful on-device) then re-raise
            try:
                import traceback as _tb

                self.show_error(f"Κοινοποίηση απέτυχε: {_tb.format_exc()}")
            except Exception:
                pass
            raise


if __name__ == "__main__":
    Logger.info("APP: ========== Running main ==========")
    try:
        app = SubstationAndroidApp()
        Logger.info("APP: App instance created")
        app.run()
        Logger.info("APP: App run completed")
    except Exception as e:
        Logger.critical(f"APP: FATAL ERROR in main: {str(e)}")
        Logger.critical(f"APP: Traceback: {traceback.format_exc()}")
        raise
