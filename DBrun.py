import json
import os
import re
import shutil
import sqlite3
import sys
import subprocess
import unicodedata
import webbrowser
from datetime import datetime

from database import init_db
from email_text_utils import normalize_text, tokenize_text, tokens_match, normalize_substation_tokens, tokenize_substation_text, iter_substation_name_candidates
from importers import (import_elements_from_csv, import_elements_from_excel,
                       import_substations_from_csv,
                       import_substations_from_excel)
from popups import show_message_popup
from settings import DB_PATH
from strings_proxy import STRINGS as S
from config_manager import (get_current_language, set_current_language,
                            get_current_user, set_current_user, clear_current_user,
                            get_db_path, set_db_path, get_app_setting,
                            set_app_setting, clear_app_setting)
from db_version import is_db_compatible, get_app_version_string, get_db_version_string
from db_integrity import check_database_integrity
from import_diagnostics import log_import_diagnostic
from validation import is_user_responsible_capable

# Lazy-evaluated strings (called at runtime, not import time)
def get_unreg():
    """Get unregistered placeholder string in current language"""
    return S["MESSAGES"].get("UNREGISTERED_PLACEHOLDER", "(Μη καταχωρημένο)")
def get_empty():
    """Get empty placeholder string in current language"""
    return S["MESSAGES"].get("EMPTY_PLACEHOLDER", "(Κενό)")
def get_model_prompt():
    """Get model select prompt string in current language"""
    return S["MESSAGES"].get("MODEL_SELECT_PROMPT", "Επιλέξτε μοντέλο")
import importlib

from email_eml_parser import parse_eml_file
from import_wizard import ColumnMappingPopup, DataValidationPopup
from model_management import show_models_management
from onedrive_hybrid_storage import (
    ensure_maintenance_folders,
    delete_maintenance_folders,
    process_hybrid_queue,
    resolve_shared_root,
    ensure_dga_folder,
    get_transformer_report_targets,
    sync_all_substation_structures,
    regenerate_maintenance_reports,
    relink_existing_maintenance_assets,
)
from popups import ask_open_file
from reports import create_elements_template, create_substations_template
from dga_reports import generate_dga_excel_report

try:
    import kivy

    # Ensure the requested Kivy version before loading submodules
    kivy.require("2.3.0")
    import logging

    # Dynamically import Kivy submodules (avoid static imports after code)
    App = importlib.import_module("kivy.app").App
    BoxLayout = importlib.import_module("kivy.uix.boxlayout").BoxLayout
    Button = importlib.import_module("kivy.uix.button").Button
    ToggleButton = importlib.import_module("kivy.uix.togglebutton").ToggleButton
    Label = importlib.import_module("kivy.uix.label").Label
    TextInput = importlib.import_module("kivy.uix.textinput").TextInput
    Popup = importlib.import_module("kivy.uix.popup").Popup
    GridLayout = importlib.import_module("kivy.uix.gridlayout").GridLayout
    ScrollView = importlib.import_module("kivy.uix.scrollview").ScrollView
    Spinner = importlib.import_module("kivy.uix.spinner").Spinner
    CheckBox = importlib.import_module("kivy.uix.checkbox").CheckBox
    FileChooserListView = importlib.import_module(
        "kivy.uix.filechooser"
    ).FileChooserListView
    Image = importlib.import_module("kivy.uix.image").Image
    ButtonBehavior = importlib.import_module("kivy.uix.behaviors").ButtonBehavior
    Widget = importlib.import_module("kivy.uix.widget").Widget
    AnchorLayout = importlib.import_module("kivy.uix.anchorlayout").AnchorLayout
    StringProperty = importlib.import_module("kivy.properties").StringProperty
    ListProperty = importlib.import_module("kivy.properties").ListProperty
    Color = importlib.import_module("kivy.graphics").Color
    Rectangle = importlib.import_module("kivy.graphics").Rectangle
    Ellipse = importlib.import_module("kivy.graphics").Ellipse
    Line = importlib.import_module("kivy.graphics").Line
    Window = importlib.import_module("kivy.core.window").Window
    CoreImage = importlib.import_module("kivy.core.image").Image
    Clipboard = importlib.import_module("kivy.core.clipboard").Clipboard
    Clock = importlib.import_module("kivy.clock").Clock
except Exception:
    # Running in test environment without Kivy available — provide lightweight stubs
    class _StubWidget:
        def __init__(self, *a, **k):
            pass

        def __call__(self, *a, **k):
            return _StubWidget()

    class _StubBehavior:
        def __init__(self, *a, **k):
            pass

    App = _StubWidget
    BoxLayout = _StubWidget
    Button = _StubWidget
    ToggleButton = _StubWidget
    Label = _StubWidget
    TextInput = _StubWidget
    Popup = _StubWidget
    GridLayout = _StubWidget
    ScrollView = _StubWidget
    Spinner = _StubWidget
    CheckBox = _StubWidget
    FileChooserListView = _StubWidget
    Image = _StubWidget
    ButtonBehavior = _StubBehavior
    Widget = _StubWidget
    AnchorLayout = _StubWidget

    class StringProperty:
        def __init__(self, *a, **k):
            pass

    class ListProperty:
        def __init__(self, *a, **k):
            pass

    def Color(*a, **k):
        return None

    Rectangle = _StubWidget
    Ellipse = _StubWidget
    Line = _StubWidget

    class Window:
        modifiers = []

        @staticmethod
        def maximize():
            return None

        @staticmethod
        def bind(*a, **k):
            return None

    CoreImage = _StubWidget
    Clipboard = _StubWidget

    class Clock:
        @staticmethod
        def schedule_once(cb, t=0):
            # run immediately in tests to avoid scheduling
            try:
                cb(0)
            except Exception:
                pass
    import logging
    logging.basicConfig()
from validation import (PEOPLE_ROLES, filter_people_for_maintenance,
                        group_people_by_category)


def apply_change_log_to_db(conn: sqlite3.Connection, file_path: str):
    """Apply a JSONL change-log file to the given sqlite3 connection.

    The change-log format is one JSON object per line: {operation, table, data}
    Currently supports only 'insert' operations. For 'maintenance' inserts the
    helper will also populate `maintenance_elements` and update `elements`.`maintenance_date`.
    """
    import os

    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)

    cur = conn.cursor()
    with open(file_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            op = obj.get("operation")
            table = obj.get("table")
            data = obj.get("data") or {}
            if op != "insert":
                continue

            # Special handling for maintenance rows which may embed elements
            if table == "maintenance":
                # Insert maintenance fields that exist in the schema
                maint_cols = [
                    r[1] for r in cur.execute("PRAGMA table_info(maintenance)")
                ]
                maint_keys = [k for k in data.keys() if k in maint_cols]
                placeholders = ",".join(["?"] * len(maint_keys))
                sql = f"INSERT INTO maintenance ({','.join(maint_keys)}) VALUES ({placeholders})"
                cur.execute(sql, [data[k] for k in maint_keys])
                maintenance_id = cur.lastrowid

                elements = data.get("elements") or []
                seen_element_ids = set()
                for elem in elements:
                    elem_id = elem.get("element_id") or elem.get("id")
                    elem_comments = elem.get("element_comments") or elem.get("comments")
                    if not elem_id:
                        continue
                    # Skip duplicates within one payload entry.
                    if elem_id in seen_element_ids:
                        continue
                    seen_element_ids.add(elem_id)
                    cur.execute(
                        """
                        INSERT INTO maintenance_elements (maintenance_id, element_id, element_comments)
                        SELECT ?, ?, ?
                        WHERE NOT EXISTS (
                            SELECT 1 FROM maintenance_elements
                            WHERE maintenance_id = ? AND element_id = ?
                        )
                        """,
                        (maintenance_id, elem_id, elem_comments, maintenance_id, elem_id),
                    )
                    # Update element maintenance_date if provided
                    if data.get("date_time") and elem_id:
                        cur.execute(
                            "UPDATE elements SET maintenance_date=? WHERE id=?",
                            (data.get("date_time"), elem_id),
                        )
                conn.commit()
                continue

            # Generic insert: map keys to existing table columns
            cols_info = [r[1] for r in cur.execute(f"PRAGMA table_info({table})")]
            insert_keys = [k for k in data.keys() if k in cols_info]
            if not insert_keys:
                continue
            placeholders = ",".join(["?"] * len(insert_keys))
            sql = (
                f"INSERT INTO {table} ({','.join(insert_keys)}) VALUES ({placeholders})"
            )
            cur.execute(sql, [data[k] for k in insert_keys])
            conn.commit()


# Maximize window on startup
Window.maximize()

from ui.shared import IconButton, IconOnlyButton, ShiftSelectableTextInput


class SubstationApp(App):
    # Define element types as a class variable (loaded from `strings.py`)
    # Keep a small, safe fallback to an empty list if the key is missing.
    ELEMENT_TYPES = S["MESSAGES"].get("ELEMENT_TYPES", [])
    BREAKER_CATEGORIES_ALL = S["MESSAGES"].get("BREAKER_CATEGORIES_ALL", ["SF6", "Πτωχού Ελαίου", "Ελαίου", "Κενού"])  # All breaker categories
    # Derive canonical breaker element names from centralized ELEMENT_TYPES
    ELEM_BREAKER_YT = next((t for t in ELEMENT_TYPES if t == S["MESSAGES"].get("ELEMENT_BREAKER_YT", "Διακόπτης ΥΤ")), S["MESSAGES"].get("ELEMENT_BREAKER_YT", "Διακόπτης ΥΤ"))
    ELEM_BREAKER_MT = next((t for t in ELEMENT_TYPES if t == S["MESSAGES"].get("ELEMENT_BREAKER_MT", "Διακόπτης ΜΤ")), S["MESSAGES"].get("ELEMENT_BREAKER_MT", "Διακόπτης ΜΤ"))
    BREAKER_ELEMENT_TYPES = [ELEM_BREAKER_MT, ELEM_BREAKER_YT]

    def _format_elem_type(self, elem_type, is_main_switch):
        """Return element type with breaker subtype in parentheses for breakers.

        Ensures circuit breakers always show a subtype (Κεντρικός/Γραμμής/Διασυνδετικός/Διακόπτης Πυκνωτών).
        """
        if elem_type not in self.BREAKER_ELEMENT_TYPES:
            return elem_type
        try:
            # HV breakers are always treated as central breakers.
            if elem_type == self.ELEM_BREAKER_YT:
                label = S["MESSAGES"].get("BREAKER_LABEL_CENTRAL", "Κεντρικός")
            # MV breakers with is_main_switch==1 are also central breakers.
            elif elem_type == self.ELEM_BREAKER_MT and is_main_switch == 1:
                label = S["MESSAGES"].get("BREAKER_LABEL_CENTRAL", "Κεντρικός")
            elif is_main_switch == 2:
                label = S["MESSAGES"].get("BREAKER_LABEL_INTERCON", "Διασυνδετικός")
            elif is_main_switch == 3:
                label = S["MESSAGES"].get("BREAKER_LABEL_CAPACITOR", "Διακόπτης Πυκνωτών")
            else:
                label = S["MESSAGES"].get("BREAKER_LABEL_LINE", "Γραμμής")
        except Exception:
            label = S["MESSAGES"].get("BREAKER_LABEL_LINE", "Γραμμής")
        return f"{elem_type} ({label})"
    BREAKER_CATEGORIES_HV = S["MESSAGES"].get("BREAKER_CATEGORIES_HV", ["SF6", "Ελαίου"])  # HV breaker categories
    BREAKER_CATEGORIES_MV = S["MESSAGES"].get("BREAKER_CATEGORIES_MV", ["SF6", "Πτωχού Ελαίου", "Ελαίου", "Κενού"])  # MV breaker categories
    BREAKER_TYPES = S["MESSAGES"].get("BREAKER_TYPES", ["Κεντρικός", "Γραμμής", "Διασυνδετικός", "Διακόπτης Πυκνωτών"])  # Main, Line, Interconnection, or Capacitor breaker
    OPERATING_STATUS = S["MESSAGES"].get("OPERATING_STATUS", ["Ενεργή", "Ανενεργή"])
    INSTALLATION_SPACE = S["MESSAGES"].get("INSTALLATION_SPACE", ["Εσωτερικός", "Εξωτερικός"])
    VOLTAGE_LEVELS = S["MESSAGES"].get("VOLTAGE_LEVELS", ["(Κενό)", "150/20KV", "20KV", "150KV", "20KV/400V"])
    THEME_FALLBACK = {
        "primary": (0.05, 0.36, 0.64, 1),
        "primary_dark": (0.03, 0.28, 0.5, 1),
        "accent": (0.12, 0.52, 0.86, 1),
        "background": (0.97, 0.98, 0.99, 1),
        "popup_bg": (1, 1, 1, 1),
        "input_bg": (1, 1, 1, 1),
        "text": (0.12, 0.12, 0.12, 1),
        "text_on_primary": (1, 1, 1, 1),
    }
    # Central definition of element fields for easy future extension
    ELEMENT_FIELD_DEFS = [
        {
            "key": "name",
            "label": S["MESSAGES"].get("ELEMENT_NAME_LABEL", "Όνομα Στοιχείου"),
            "type": "text",
            "hint": S["MESSAGES"].get("ELEMENT_NAME_HINT", "Όνομα Στοιχείου"),
        },
        {
            "key": "serial_number",
            "label": S["MESSAGES"].get("SERIAL_NUMBER_LABEL", "Σειριακός Αριθμός"),
            "type": "text",
            "hint": S["MESSAGES"].get("SERIAL_NUMBER_HINT", "Σειριακός Αριθμός"),
        },
        {
            "key": "manufacture_year",
            "label": S["MESSAGES"].get("ELEMENT_MANUFACTURE_YEAR_LABEL", "Έτος κατασκευής"),
            "type": "text",
            "hint": S["MESSAGES"].get("ELEMENT_MANUFACTURE_YEAR_HINT", "YYYY"),
        },
        {
            "key": "maintenance_date",
            "label": S["MESSAGES"].get("MAINTENANCE_DATE_LABEL", "Τελευταία Συντ."),
            "type": "text",
            "hint": S["MESSAGES"].get("MAINTENANCE_DATE_HINT", "YYYY-MM-DD"),
        },
        {
            "key": "manufacturer",
            "label": S["MESSAGES"].get("MANUFACTURER_LABEL", "Κατασκευαστής"),
            "type": "text",
            "hint": S["MESSAGES"].get("MANUFACTURER_HINT", "Κατασκευαστής"),
        },
        {"key": "model", "label": S["MESSAGES"].get("MODEL_LABEL", "Μοντέλο"), "type": "text", "hint": S["MESSAGES"].get("MODEL_HINT", "Μοντέλο")},
        {
            "key": "model_version",
            "label": S["MESSAGES"].get("MODEL_VERSION_LABEL", "Έκδοση Μοντέλου"),
            "type": "text",
            "hint": S["MESSAGES"].get("MODEL_VERSION_HINT", "Έκδοση"),
        },
        {
            "key": "installation_space",
            "label": S["MESSAGES"].get("INSTALLATION_SPACE_LABEL", "Χώρος Εγκατ."),
            "type": "spinner",
            "values": INSTALLATION_SPACE,
        },
        {
            "key": "operating_status",
            "label": S["MESSAGES"].get("OPERATING_STATUS_LABEL", "Λειτ. Κατάσταση"),
            "type": "spinner",
            "values": OPERATING_STATUS,
        },
        {
            "key": "maintenance_cycle",
            "label": S["MESSAGES"].get("MAINTENANCE_CYCLE_LABEL", "Κύκλος Συντ."),
            "type": "text",
            "hint": S["MESSAGES"].get("MAINTENANCE_CYCLE_HINT", "Αριθμός"),
        },
    ]

    def _get_breaker_categories_for_element_type(self, element_type: str):
        if element_type == self.ELEM_BREAKER_MT:
            return list(self.BREAKER_CATEGORIES_MV)
        if element_type == self.ELEM_BREAKER_YT:
            return list(self.BREAKER_CATEGORIES_HV)
        return list(self.BREAKER_CATEGORIES_ALL)

    def build(self):
        self.title = S["MESSAGES"].get("APP_TITLE", "Υποσταθμοί ΔΕΔΔΗΕ ΔΕΕΔ/ΚΣΜΘ/ΤΕΙ")
        self._apply_theme()
        self.root_layout = BoxLayout(orientation="vertical")
        Window.bind(on_key_down=self._handle_tab_navigation)
        Window.bind(on_request_close=self._handle_request_close)

        self.loading_label = Label(text=S["MESSAGES"]["LOADING"], font_size="22sp")
        self.root_layout.add_widget(self.loading_label)

        Clock.schedule_once(self._finish_build, 0)
        return self.root_layout

    def _check_db_compatibility(self):
        """Check if the database version is compatible with the app version.
        
        Returns:
            True if compatible, False otherwise
        """
        compat_result = is_db_compatible()
        if not compat_result["compatible"]:
            # Show error dialog with incompatibility message
            error_title = S["MESSAGES"].get("ERROR_TITLE", "Σφάλμα")
            error_msg = (
                f"Σφάλμα συμβατότητας βάσης δεδομένων\n\n"
                f"{compat_result['message']}\n\n"
                f"Παρακαλώ ανανεώστε την εφαρμογή ή τη βάση δεδομένων."
            )
            show_message_popup(title=error_title, message=error_msg)
            return False
        return True

    def _check_db_integrity(self):
        """Check database integrity to detect corruption or data issues.
        
        Returns:
            True if integrity check passed or user chose to continue, False to abort
        """
        db_path = get_db_path() or DB_PATH
        
        # Perform quick integrity check (fast, essential checks only)
        integrity_result = check_database_integrity(db_path, quick_check=True)
        
        if integrity_result.errors:
            # Critical errors - block app startup
            error_title = S["MESSAGES"].get("ERROR_TITLE", "Σφάλμα")
            error_msg = (
                "Η βάση δεδομένων έχει κρίσιμα προβλήματα ακεραιότητας:\n\n"
                + "\n".join(f"• {err}" for err in integrity_result.errors[:5])
            )
            if len(integrity_result.errors) > 5:
                error_msg += f"\n... και {len(integrity_result.errors) - 5} ακόμα προβλήματα"
            
            error_msg += (
                "\n\nΗ εφαρμογή δε μπορεί να συνεχίσει με αυτή τη βάση δεδομένων.\n"
                "Παρακαλώ επαναφέρετε ένα αντίγραφο ασφαλείας ή επικοινωνήστε με υποστήριξη."
            )
            show_message_popup(title=error_title, message=error_msg)
            return False
        
        if integrity_result.warnings:
            # Warnings - show but allow user to continue
            warning_title = "Προειδοποίηση"
            warning_msg = (
                "Η βάση δεδομένων έχει κάποια προβλήματα που χρήζουν προσοχής:\n\n"
                + "\n".join(f"• {warn}" for warn in integrity_result.warnings[:5])
            )
            if len(integrity_result.warnings) > 5:
                warning_msg += f"\n... και {len(integrity_result.warnings) - 5} ακόμα προειδοποιήσεις"
            
            warning_msg += "\n\nΘέλετε να συνεχίσετε;"
            
            # Create confirmation popup
            from kivy.uix.popup import Popup
            from kivy.uix.boxlayout import BoxLayout
            from kivy.uix.label import Label
            from kivy.uix.button import Button
            
            popup = Popup(title=warning_title, size_hint=(0.7, 0.6))
            layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
            
            # Warning message (scrollable)
            from kivy.uix.scrollview import ScrollView
            scroll = ScrollView()
            msg_label = Label(
                text=warning_msg, 
                size_hint_y=None,
                text_size=(None, None),
                halign='left',
                valign='top'
            )
            msg_label.bind(size=msg_label.setter('text_size'))
            msg_label.bind(texture_size=msg_label.setter('size'))
            scroll.add_widget(msg_label)
            layout.add_widget(scroll)
            
            # Buttons
            btn_layout = BoxLayout(size_hint_y=None, height=50, spacing=10)
            
            continue_clicked = [False]
            
            def on_continue(*args):
                continue_clicked[0] = True
                popup.dismiss()
            
            def on_cancel(*args):
                popup.dismiss()
            
            continue_btn = Button(text=S["BUTTONS"].get("CONTINUE", "Συνέχεια"))
            continue_btn.bind(on_press=on_continue)
            btn_layout.add_widget(continue_btn)
            
            cancel_btn = Button(text=S["BUTTONS"].get("CANCEL", "Ακύρωση"))
            cancel_btn.bind(on_press=on_cancel)
            btn_layout.add_widget(cancel_btn)
            
            layout.add_widget(btn_layout)
            popup.content = layout
            popup.open()
            
            # Wait for user decision (blocking)
            from kivy.clock import Clock
            while popup._window is not None:
                Clock.tick()
            
            return continue_clicked[0]
        
        # No errors or warnings - all good
        return True

    def _finish_build(self, *_args):
        # Check DB compatibility before proceeding
        if not self._check_db_compatibility():
            return
        
        # Check DB integrity before proceeding
        if not self._check_db_integrity():
            return
        
        # Always show login popup at startup (will pre-select last user)
        self.show_login_popup(on_login_success=lambda: Clock.schedule_once(self._build_main_ui, 0))
    
    def _build_main_ui(self, *_args):
        """Build the main application UI after user login."""
        layout = self.root_layout
        # remove the temporary loading label added during build()
        try:
            if hasattr(self, "loading_label") and self.loading_label in layout.children:
                layout.remove_widget(self.loading_label)
                del self.loading_label
        except Exception:
            pass
        self._add_logo_to_layout(layout, height=120, reserve=True)

        # Top bar with settings and app info
        top_bar = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=40, padding=10
        )
        self.settings_btn = IconOnlyButton(
            icon_type="settings",
            icon_color=list(self.theme.get("primary", (0.05, 0.18, 0.36, 1))),
            size=(34, 34),
            tooltip=S["MESSAGES"].get("SETTINGS_TOOLTIP", "Ρυθμίσεις"),
        )
        self.settings_btn.bind(on_press=self.show_settings_popup)
        top_bar.add_widget(self.settings_btn)
        top_bar.add_widget(Widget())
        self.app_info_btn = Button(
            text=S["MESSAGES"].get("APP_INFO_SHORT", "Πληρ. Εφαρμ."),
            size_hint=(None, None),
            height=30,
            width=130,
            font_size="12sp",
        )
        self.app_info_btn.bind(on_press=self.show_app_info_popup)
        top_bar.add_widget(self.app_info_btn)
        layout.add_widget(top_bar)

        self.show_btn = IconButton(
            text=S["MESSAGES"].get("SHOW_DB_BUTTON", "Προβολή βάσης υποσταθμών"), icon_type="database", theme=self.theme
        )
        self.show_btn.bind(on_press=self.show_records)
        self.import_btn = IconButton(
            text=S["TITLES"].get("IMPORT_MENU", "Εισαγωγή από αρχείο"), icon_type="import", theme=self.theme
        )
        self.import_btn.bind(on_press=self.show_import_menu)
        self.maintenance_btn = IconButton(
            text=S["MESSAGES"].get("MAINTENANCE_BUTTON", S["MESSAGES"].get("MAINTENANCES", "Συντηρήσεις")), icon_type="maintenance", theme=self.theme
        )
        self.maintenance_btn.bind(on_press=self.show_maintenance_menu_popup)
        self.inspection_btn = IconButton(
            text=S["BUTTONS"]["INSPECTIONS"], icon_type="inspection", theme=self.theme
        )
        self.inspection_btn.bind(on_press=self.show_inspection_menu_popup)
        self.isolation_btn = IconButton(
            text=S["MESSAGES"].get("ISOLATION_BUTTON", "Αιτήσεις Απομόνωσης"), icon_type="isolation", theme=self.theme
        )
        self.isolation_btn.bind(on_press=self.show_isolation_requests)
        self.models_btn = IconButton(
            text=S["MESSAGES"].get("MODELS_BUTTON", "Διαχείριση Τύπων Στοιχείων"), icon_type="models", theme=self.theme
        )
        self.models_btn.bind(on_press=self.show_models_management)
        self.people_btn = IconButton(
            text=S["MESSAGES"].get("PEOPLE_BUTTON", "Διαχείριση Προσωπικού"), icon_type="people", theme=self.theme
        )
        self.people_btn.bind(on_press=self.show_people_management)
        self.sf6_btn = IconButton(
            text=S["MESSAGES"].get("SF6_BUTTON", "Διαχείριση SF6"), icon_type="sf6", theme=self.theme
        )
        self.sf6_btn.bind(on_press=self.show_sf6_management_popup)

        buttons_layout = BoxLayout(orientation="horizontal", spacing=10, padding=10)
        left_col = BoxLayout(orientation="vertical", spacing=10)
        right_col = BoxLayout(orientation="vertical", spacing=10)

        left_col.add_widget(self.show_btn)
        left_col.add_widget(self.import_btn)
        left_col.add_widget(self.models_btn)
        left_col.add_widget(self.people_btn)

        right_col.add_widget(self.maintenance_btn)
        right_col.add_widget(self.inspection_btn)
        right_col.add_widget(self.isolation_btn)
        right_col.add_widget(self.sf6_btn)

        buttons_layout.add_widget(left_col)
        buttons_layout.add_widget(right_col)
        layout.add_widget(buttons_layout)

        selected_db_path = get_db_path() or DB_PATH
        self.conn = init_db(selected_db_path)
        self.db_path = os.path.abspath(selected_db_path)
        self._last_sync_cycle_ts = 0
        self._pending_changes = []  # Track changes for export on close
        self._check_previous_sync_issues()  # Check for rejected/conflict files
        self._run_startup_sync_cycle()
        Clock.schedule_interval(self._run_periodic_sync_cycle, 60)

        # Ensure people name columns exist and are populated (migration)
        try:
            self._migrate_people_name_columns()
        except Exception:
            pass

    def _handle_request_close(self, *args):
        self._cleanup_before_exit()
        return False

    def on_stop(self):
        self._cleanup_before_exit()

    def _cleanup_before_exit(self):
        try:
            # Export pending changes before closing
            self._export_pending_changes(show_popup=True)
        except Exception:
            pass
        try:
            if getattr(self, "conn", None):
                self.conn.close()
                self.conn = None
        except Exception:
            pass
        try:
            if self.root:
                self.root.clear_widgets()
        except Exception:
            pass

    def _apply_theme(self):
        """Apply a logo-based theme to common UI widgets."""
        theme = self._get_modern_theme()
        self.theme = theme

        Window.clearcolor = theme["background"]

        Button.background_normal = "atlas://data/images/defaulttheme/button"
        Button.background_down = "atlas://data/images/defaulttheme/button_pressed"
        Button.background_color = theme["primary"]
        Button.color = theme["text_on_primary"]

        Spinner.background_normal = ""
        Spinner.background_down = ""
        Spinner.background_color = theme["primary"]
        Spinner.color = theme["text_on_primary"]

        # Spinner dropdown options (opaque background)
        from kivy.uix.spinner import SpinnerOption

        SpinnerOption.background_normal = ""
        SpinnerOption.background_down = ""
        SpinnerOption.background_color = theme["primary"]
        SpinnerOption.color = theme["text_on_primary"]

        Label.color = theme["text"]

        TextInput.background_color = theme["input_bg"]
        TextInput.foreground_color = theme["text"]
        TextInput.cursor_color = theme["primary_dark"]
        TextInput.selection_color = theme["accent"]

        Popup.background = ""
        Popup.background_color = theme["popup_bg"]

    def _add_logo_to_layout(self, layout, height=80, reserve=False):
        """Add logo to the top of a layout if available."""
        logo_path = os.path.join(os.path.dirname(__file__), "logo_deddie.png")
        fallback_path = os.path.join(os.path.dirname(__file__), "deddie_logo.png")
        if os.path.exists(logo_path) or os.path.exists(fallback_path):
            logo = Image(
                source=logo_path if os.path.exists(logo_path) else fallback_path,
                size_hint_y=None,
                height=height,
            )
            if hasattr(logo, "fit_mode"):
                logo.fit_mode = "contain"
            layout.add_widget(logo)
            return
        if reserve:
            layout.add_widget(Label(text="", size_hint_y=None, height=height))

    def _get_modern_theme(self):
        """Return a modern dark-blue palette."""
        primary = (0.05, 0.18, 0.36, 1)
        primary_dark = (0.03, 0.12, 0.25, 1)
        accent = (0.12, 0.42, 0.85, 1)
        background = (0.94, 0.96, 0.99, 1)
        popup_bg = (0.98, 0.99, 1, 1)

        return {
            "primary": primary,
            "primary_dark": primary_dark,
            "accent": accent,
            "background": background,
            "popup_bg": popup_bg,
            "input_bg": (1, 1, 1, 1),
            "text": (0.12, 0.12, 0.12, 1),
            "text_on_primary": (1, 1, 1, 1),
        }

    def _load_logo_theme(self):
        """Extract a color theme from deddie_logo.png if available."""
        logo_path = os.path.join(os.path.dirname(__file__), "logo_deddie.png")
        fallback_path = os.path.join(os.path.dirname(__file__), "deddie_logo.png")
        if not os.path.exists(logo_path) and not os.path.exists(fallback_path):
            return dict(self.THEME_FALLBACK)

        if not os.path.exists(logo_path):
            logo_path = fallback_path

        try:
            image = CoreImage(logo_path)
            texture = image.texture
            if not texture or not texture.pixels:
                return dict(self.THEME_FALLBACK)

            pixels = texture.pixels
            total_pixels = max(1, texture.size[0] * texture.size[1])
            step = max(1, total_pixels // 5000)

            r_sum = g_sum = b_sum = 0
            count = 0
            for i in range(0, len(pixels), 4 * step):
                r, g, b, a = pixels[i], pixels[i + 1], pixels[i + 2], pixels[i + 3]
                if a < 10:
                    continue
                if r > 245 and g > 245 and b > 245:
                    continue
                r_sum += r
                g_sum += g
                b_sum += b
                count += 1

            if count == 0:
                return dict(self.THEME_FALLBACK)

            primary = (r_sum / count / 255, g_sum / count / 255, b_sum / count / 255, 1)
            primary_dark = self._adjust_color(primary, 0.8)
            accent = self._adjust_color(primary, 1.15)
            background = self._blend_color(primary, (1, 1, 1, 1), 0.92)
            popup_bg = self._blend_color(primary, (1, 1, 1, 1), 0.96)

            brightness = (
                (primary[0] * 0.299) + (primary[1] * 0.587) + (primary[2] * 0.114)
            )
            text_on_primary = (0, 0, 0, 1) if brightness > 0.6 else (1, 1, 1, 1)

            return {
                "primary": primary,
                "primary_dark": primary_dark,
                "accent": accent,
                "background": background,
                "popup_bg": popup_bg,
                "input_bg": (1, 1, 1, 1),
                "text": (0.12, 0.12, 0.12, 1),
                "text_on_primary": text_on_primary,
            }
        except Exception:
            return dict(self.THEME_FALLBACK)

    def _adjust_color(self, color, factor):
        return (
            min(max(color[0] * factor, 0), 1),
            min(max(color[1] * factor, 0), 1),
            min(max(color[2] * factor, 0), 1),
            color[3] if len(color) > 3 else 1,
        )

    def _blend_color(self, color, target, ratio):
        return (
            color[0] * (1 - ratio) + target[0] * ratio,
            color[1] * (1 - ratio) + target[1] * ratio,
            color[2] * (1 - ratio) + target[2] * ratio,
            1,
        )

    def _handle_tab_navigation(self, window, key, scancode, codepoint, modifiers):
        """Use Tab/Shift+Tab to move focus between text inputs."""
        if key != 9:  # Tab
            return False

        text_inputs = []
        for widget in Window.children:
            for child in widget.walk():
                if isinstance(child, TextInput):
                    child.write_tab = False
                    text_inputs.append(child)

        focused = next((ti for ti in text_inputs if ti.focus), None)
        if focused:
            next_widget = (
                focused.get_focus_previous()
                if "shift" in modifiers
                else focused.get_focus_next()
            )
            if next_widget:
                focused.focus = False
                next_widget.focus = True
        return True

    def show_maintenance_menu_popup(self, instance=None):
        # Delegated implementation in maintenance.py
        from maintenance import show_maintenance_menu_popup as _m
        ui = {
            "Popup": Popup,
            "BoxLayout": BoxLayout,
            "Label": Label,
            "Button": Button,
            "TextInput": TextInput,
            "FileChooserListView": FileChooserListView,
            "Spinner": Spinner,
            "ask_open_file": ask_open_file,
            "show_message_popup": show_message_popup,
            "parse_eml_file": parse_eml_file,
        }
        try:
            # provide export helper if available
            from excel_io import export_maintenances_per_substation

            ui["export_maintenances_per_substation"] = export_maintenances_per_substation
        except Exception:
            ui["export_maintenances_per_substation"] = None

        return _m(self, ui)

    def _show_import_maintenance_email_dialog(self, parent_popup=None):
        from maintenance import _show_import_maintenance_email_dialog as _m
        ui = {
            "Popup": Popup,
            "BoxLayout": BoxLayout,
            "Label": Label,
            "Button": Button,
            "TextInput": TextInput,
            "FileChooserListView": FileChooserListView,
            "Spinner": Spinner,
            "ask_open_file": ask_open_file,
            "show_message_popup": show_message_popup,
            "parse_eml_file": parse_eml_file,
        }
        return _m(self, ui, parent_popup)

    def _import_maintenance_from_email_file(self, file_path):
        from maintenance import _import_maintenance_from_email_file as _m
        ui = {
            "parse_eml_file": parse_eml_file,
            "show_message_popup": show_message_popup,
        }
        return _m(self, ui, file_path)

    def _normalize_text(self, value: str) -> str:
        """Wrapper for shared normalize_text function."""
        return normalize_text(value)

    def _is_transformer(self, elem_type: str) -> bool:
        """Return True when an element type represents the 150/20KV transformer.

        This is intentionally permissive because some databases may contain
        mojibake or slightly different spellings; we therefore check for the
        numeric `150/20` marker or the normalized greek stem `μετασχη`.
        """
        if not elem_type:
            return False
        try:
            norm = self._normalize_text(elem_type)
        except Exception:
            norm = (elem_type or "").lower()
        return ("150/20" in (elem_type or "")) or ("150/20" in norm) or ("μετασχη" in norm)

    def _tokenize_text(self, value: str):
        """Wrapper for shared tokenize_text function."""
        return tokenize_text(value)

    def _tokens_match(self, left_tokens, right_tokens):
        """Wrapper for shared tokens_match function."""
        return tokens_match(left_tokens, right_tokens)

    def _normalize_substation_tokens(self, tokens):
        """Wrapper for shared normalize_substation_tokens function."""
        return normalize_substation_tokens(tokens)

    def _tokenize_substation_text(self, value: str):
        """Wrapper for shared tokenize_substation_text function."""
        return tokenize_substation_text(value)

    def _iter_substation_name_candidates(self, substation_name: str):
        """Wrapper for shared iter_substation_name_candidates function."""
        return iter_substation_name_candidates(substation_name)

    def _find_substation_in_text(self, text: str, substations):
        tokens = self._tokenize_substation_text(text)
        if not tokens:
            return None

        for sub_id, sub_name in substations:
            for candidate_name in self._iter_substation_name_candidates(sub_name):
                name_tokens = self._tokenize_substation_text(candidate_name)
                if not name_tokens:
                    continue
                for i in range(len(tokens) - len(name_tokens) + 1):
                    candidate = tokens[i : i + len(name_tokens)]
                    if self._tokens_match(candidate, name_tokens):
                        return sub_id, sub_name

        return None

    def _match_person_by_sender(self, sender_name: str, people):
        sender_tokens = self._tokenize_text(sender_name)
        if not sender_tokens:
            return None
        sender_full = " ".join(sender_tokens)
        for pid, name, _role in people:
            person_tokens = self._tokenize_text(name)
            if not person_tokens:
                continue
            if sender_full == " ".join(person_tokens):
                return pid
        for pid, name, _role in people:
            person_tokens = self._tokenize_text(name)
            if not person_tokens:
                continue
            surname = person_tokens[-1]
            if surname and surname in sender_tokens:
                return pid
        return None

    def _find_people_in_body(self, body_text: str, people, exclude_ids=None):
        exclude_ids = exclude_ids or set()
        tokens = self._tokenize_text(body_text)
        token_pairs = list(zip(tokens, tokens[1:]))
        normalized_body = re.sub(r"[^0-9a-zα-ω]+", " ", self._normalize_text(body_text))
        normalized_body = re.sub(r"\s+", " ", normalized_body).strip()

        def _person_token_match(body_token: str, person_token: str) -> bool:
            if not body_token or not person_token:
                return False
            if body_token == person_token:
                return True
            # Allow Greek declension variants that differ only by a suffix character.
            if len(body_token) >= 4 and len(person_token) >= 4 and body_token[:-1] == person_token[:-1]:
                return True
            return False

        def _matches_initial_and_surname(given_token: str, surname_token: str) -> bool:
            if not given_token or not surname_token or not normalized_body:
                return False
            initial = given_token[0]
            pattern = rf"\b{re.escape(initial)}\s*[.-]?\s*{re.escape(surname_token)}\b"
            return re.search(pattern, normalized_body) is not None

        found = set()
        matched_name_keys = set()
        for pid, name, _role in people:
            if pid in exclude_ids:
                continue
            person_tokens = self._tokenize_text(name)
            if not person_tokens:
                continue

            surname_token = person_tokens[0]
            given_token = person_tokens[-1]
            matched = False

            if len(person_tokens) >= 2:
                for left, right in token_pairs:
                    if _person_token_match(left, surname_token) and _person_token_match(right, given_token):
                        matched = True
                        break
                    if _person_token_match(left, given_token) and _person_token_match(right, surname_token):
                        matched = True
                        break

                if not matched and _matches_initial_and_surname(given_token, surname_token):
                    matched = True
            else:
                matched = any(_person_token_match(tok, person_tokens[0]) for tok in tokens)

            if not matched:
                continue

            name_key = " ".join(person_tokens)
            if name_key in matched_name_keys:
                continue
            matched_name_keys.add(name_key)
            found.add(pid)

        return found

    def _find_elements_in_body(self, body_text: str, substation_id: int):
        # Lightweight fallback: detailed element extraction from free text
        # is complex and was removed accidentally. Return an empty set so
        # callers safely continue when no elements are inferred from the
        # message body. If advanced extraction is needed later, restore
        # the original implementation.
        return set()

    def _get_previous_maintenance_defaults(
        self, substation_id: int, date_time_value: str
    ):
        from maintenance import _get_previous_maintenance_defaults as _m
        return _m(self, substation_id, date_time_value)

    def _open_maintenance_from_email_payload(self, payload, forced_substation=None):
        from maintenance import open_maintenance_from_email_payload as _m
        ui = {
            "Popup": Popup,
            "BoxLayout": BoxLayout,
            "Label": Label,
            "Button": Button,
            "TextInput": TextInput,
            "FileChooserListView": FileChooserListView,
            "Spinner": Spinner,
            "ask_open_file": ask_open_file,
            "show_message_popup": show_message_popup,
            "parse_eml_file": parse_eml_file,
        }
        return _m(self, ui, payload, forced_substation)

    def _prompt_substation_selection(self, substations, payload):
        popup = Popup(title=S["MESSAGES"].get("PROMPT_SUBSTATION_NOT_FOUND_TITLE", "Ο υποσταθμός δε βρέθηκε"), size_hint=(0.7, 0.5))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        layout.add_widget(
            Label(
                text=S["MESSAGES"].get("PROMPT_SUBSTATION_SELECT", "Επιλέξτε υποσταθμό για την εισαγωγή:"), size_hint_y=None, height=40
            )
        )
        substation_names = [s[1] for s in substations if s[1]]
        spinner = Spinner(
            text=substation_names[0] if substation_names else "",
            values=substation_names,
            size_hint_y=None,
            height=40,
        )
        layout.add_widget(spinner)

        layout.add_widget(
            Label(text=S["MESSAGES"]["ADD_NEW_SUBSTATION_PROMPT"], size_hint_y=None, height=30)
        )
        new_name_input = TextInput(
            hint_text=S["MESSAGES"].get("SUBSTATION_NEW_HINT", "Όνομα νέου υποσταθμού"),
            size_hint_y=None,
            height=40,
            multiline=False,
        )
        layout.add_widget(new_name_input)

        buttons = BoxLayout(size_hint_y=None, height=40, spacing=10)

        def confirm():
            if not spinner.text:
                show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["PLEASE_SELECT_OR_ADD_SUBSTATION"])
                return
            popup.dismiss()
            self._open_maintenance_from_email_payload(
                payload, forced_substation=spinner.text
            )

        def add_new_substation():
            new_name = new_name_input.text.strip()
            if not new_name:
                show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["ENTER_SUBSTATION_NAME"])
                return
            c = self.conn.cursor()
            c.execute("SELECT id FROM substations WHERE name=?", (new_name,))
            if c.fetchone():
                show_message_popup(S["TITLES"]["INFO"], S["MESSAGES"]["SUBSTATION_EXISTS"])
                spinner.text = new_name
                return
            c.execute(
                "INSERT INTO substations (name, location, adoption_date, division) VALUES (?, ?, ?, ?)",
                (new_name, "", "", "ΤΜΘ"),
            )
            self.conn.commit()
            new_substation_id = c.lastrowid
            substation_names.append(new_name)
            spinner.values = substation_names
            spinner.text = new_name
            new_name_input.text = ""
            popup.dismiss()
            self._prompt_add_elements_then_continue(
                new_substation_id, new_name, payload
            )

        ok_btn = Button(text=S["BUTTONS"]["CONFIRM"])
        ok_btn.bind(on_press=lambda x: confirm())
        buttons.add_widget(ok_btn)

        add_btn = Button(text=S["BUTTONS"]["ADD"])
        add_btn.bind(on_press=lambda x: add_new_substation())
        buttons.add_widget(add_btn)

        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
        cancel_btn.bind(on_press=popup.dismiss)
        buttons.add_widget(cancel_btn)

        layout.add_widget(buttons)
        popup.content = layout
        popup.open()

    def _prompt_add_elements_then_continue(
        self, substation_id, substation_name, payload
    ):
        popup = Popup(title=S["MESSAGES"].get("ADD_ELEMENTS_TITLE", "Προσθήκη στοιχείων"), size_hint=(0.7, 0.5))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        layout.add_widget(
            Label(
                text=S["MESSAGES"].get("ADD_ELEMENTS_PROMPT", "Προσθέστε στοιχεία για τον νέο υποσταθμό πριν τη συνέχεια:"),
                size_hint_y=None,
                height=50,
            )
        )

        def add_element():
            self.show_add_element_popup_for_substation(
                substation_id, substation_name, popup
            )

        def continue_import():
            c = self.conn.cursor()
            c.execute(
                "SELECT COUNT(*) FROM elements WHERE substation_id=?", (substation_id,)
            )
            count = c.fetchone()[0]
            if count == 0:
                show_message_popup(
                    S["TITLES"]["ERROR"], S["MESSAGES"].get("ADD_ELEMENT_BEFORE_CONTINUE", "Προσθέστε τουλάχιστον ένα στοιχείο πριν τη συνέχεια.")
                )
                return
            popup.dismiss()
            self._open_maintenance_from_email_payload(
                payload, forced_substation=substation_name
            )

        buttons = BoxLayout(size_hint_y=None, height=40, spacing=10)
        add_btn = Button(text=S["BUTTONS"]["ADD"] + " Στοιχείου")
        add_btn.bind(on_press=lambda x: add_element())
        buttons.add_widget(add_btn)

        continue_btn = Button(text=S["MESSAGES"].get("CONTINUE", "Συνέχεια"))
        continue_btn.bind(on_press=lambda x: continue_import())
        buttons.add_widget(continue_btn)

        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
        cancel_btn.bind(on_press=popup.dismiss)
        buttons.add_widget(cancel_btn)

        layout.add_widget(buttons)
        popup.content = layout
        popup.open()

    def _prompt_responsible_selection(self, people, prefill):
        popup = Popup(title=S["MESSAGES"].get("RESPONSIBLE_NOT_FOUND_TITLE", "Ο υπεύθυνος δε βρέθηκε"), size_hint=(0.7, 0.5))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        layout.add_widget(
            Label(text=S["MESSAGES"]["SELECT_MAINT_RESPONSIBLE"], size_hint_y=None, height=40)
        )
        labels = [f"{p[1]} ({p[2]})" for p in people]
        spinner = Spinner(text=labels[0], values=labels, size_hint_y=None, height=40)
        layout.add_widget(spinner)

        buttons = BoxLayout(size_hint_y=None, height=40, spacing=10)

        def confirm():
            selected_index = labels.index(spinner.text)
            prefill["responsible_id"] = people[selected_index][0]
            popup.dismiss()
            self.show_maintenance_menu(
                preselected_substation_name=prefill["substation_name"],
                parent_popup=None,
                maintenance_id=None,
                after_save_callback=None,
                prefill_data=prefill,
            )

        ok_btn = Button(text=S["BUTTONS"]["CONFIRM"])
        ok_btn.bind(on_press=lambda x: confirm())
        buttons.add_widget(ok_btn)

        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
        cancel_btn.bind(on_press=popup.dismiss)
        buttons.add_widget(cancel_btn)

        layout.add_widget(buttons)
        popup.content = layout
        popup.open()

    def _get_ui_font_kwargs(self):
        """Return font kwargs for UI symbols if bundled font exists."""
        font_path = os.path.join(os.path.dirname(__file__), "DejaVuSans.ttf")
        if os.path.exists(font_path):
            return {"font_name": font_path}
        return {}

    def show_app_info_popup(self, instance=None):
        """Show application information."""
        version = self._get_app_version()

        app_dir = os.path.dirname(__file__)
        
        # Get DB version and compatibility info
        db_version = get_db_version_string()
        compat_result = is_db_compatible()
        compat_status = "Συμβατή" if compat_result["compatible"] else "Ασύμβατη"
        
        info_text_plain = S["MESSAGES"].get(
            "APP_INFO_BODY",
            "Υποσταθμοί ΔΕΔΔΗΕ ΔΕΕΔ/ΚΣΜΘ/ΤΕΙ\nΈκδοση: {version}\n\nΦάκελος εφαρμογής: {app_dir}\n\nΈκδοση ΒΔ: {db_version}\nΣυμβατότητα: {compat_status}"
        ).format(version=version, app_dir=app_dir, db_version=db_version, compat_status=compat_status)

        popup = Popup(title=S["MESSAGES"].get("APP_INFO_TITLE", "Πληροφορίες Εφαρμογής"), size_hint=(0.7, 0.6))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        info_field = ShiftSelectableTextInput(
            text=info_text_plain,
            readonly=True,
            multiline=True,
            size_hint_y=None,
            background_normal="",
            background_active="",
            background_color=(0, 0, 0, 0),
            foreground_color=self.theme.get("text", (0.12, 0.12, 0.12, 1)),
            selection_color=(0.3, 0.5, 1, 0.3),
            cursor_blink=False,
            cursor_width=1,
            write_tab=False,
            is_focusable=True,
            allow_copy=True,
            keyboard_mode="managed",
            padding=(5, 5),
        )
        info_field.bind(minimum_height=info_field.setter("height"))
        scroll = ScrollView(bar_width=10, scroll_type=["bars"])
        scroll.add_widget(info_field)
        layout.add_widget(scroll)

        def _sync_field_width(*_args):
            info_field.width = max(10, scroll.width - 10)

        scroll.bind(size=_sync_field_width)
        _sync_field_width()

        def _handle_info_keys(window, key, scancode, codepoint, modifiers):
            key_action_map = {
                276: "cursor_left",
                275: "cursor_right",
                273: "cursor_up",
                274: "cursor_down",
                278: "cursor_home",
                279: "cursor_end",
                280: "cursor_pgup",
                281: "cursor_pgdown",
            }
            if (("ctrl" in modifiers) or ("meta" in modifiers)) and (key == ord("c")):
                if info_field.selection_text:
                    Clipboard.copy(info_field.selection_text)
                    return True
            if key not in key_action_map:
                return False

            ctrl = "ctrl" in modifiers or "meta" in modifiers
            alt = "alt" in modifiers

            if "shift" in modifiers and info_field._shift_select_anchor is None:
                info_field._shift_select_anchor = info_field.cursor_index()

            info_field.do_cursor_movement(key_action_map[key], control=ctrl, alt=alt)

            if "shift" in modifiers:
                info_field.select_text(
                    info_field._shift_select_anchor, info_field.cursor_index()
                )
            else:
                info_field.cancel_selection()
                info_field._shift_select_anchor = info_field.cursor_index()
            return True

        buttons_layout = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=40, spacing=10
        )
        copy_btn = Button(text=S["BUTTONS"].get("COPY", "Αντιγραφή"))
        copy_btn.bind(
            on_press=lambda *_: Clipboard.copy(
                info_field.selection_text or info_text_plain
            )
        )
        close_btn = Button(text=S["BUTTONS"]["CLOSE"])
        close_btn.bind(on_press=popup.dismiss)
        buttons_layout.add_widget(copy_btn)
        buttons_layout.add_widget(close_btn)
        layout.add_widget(buttons_layout)

        popup.content = layout

        def _on_open(*_args):
            Window.bind(on_key_down=_handle_info_keys)
            info_field.focus = True
            info_field.cursor = (0, 0)

        def _on_dismiss(*_args):
            Window.unbind(on_key_down=_handle_info_keys)

        popup.bind(on_open=_on_open, on_dismiss=_on_dismiss)
        popup.open()

    def show_settings_popup(self, instance=None):
        """Show settings popup for language selection, database path, and user logout."""
        from sync_service import resolve_sync_root, resolve_backup_root

        popup = Popup(title=S["TITLES"].get("SETTINGS", "Ρυθμίσεις"), size_hint=(0.6, 0.6))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        # Use scroll view to accommodate multiple settings
        scroll = ScrollView(bar_width=10, scroll_type=["bars"])
        content = BoxLayout(orientation="vertical", size_hint_y=None, spacing=10, padding=10)
        content.bind(minimum_height=content.setter("height"))

        # Current user display
        current_user = get_current_user()
        if current_user:
            user_info_text = S["MESSAGES"].get("LOGGED_IN_AS_FMT", "Συνδεδεμένος ως: {name} ({role})").format(
                name=current_user["name"],
                role=current_user["role"]
            )
        else:
            user_info_text = S["MESSAGES"].get("NO_USER_LOGGED_IN", "Δεν έχει συνδεθεί χρήστης")
        
        user_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=40, spacing=10)
        user_row.add_widget(Label(text=user_info_text, size_hint_x=0.7))
        if current_user:
            logout_btn = Button(text=S["BUTTONS"].get("LOGOUT", "Αποσύνδεση"), size_hint_x=0.3)
            
            def _logout(*_args):
                popup.dismiss()
                self.show_logout_confirm()
            
            logout_btn.bind(on_press=_logout)
            user_row.add_widget(logout_btn)
        content.add_widget(user_row)

        # Language selection
        lang_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=40, spacing=10)
        lang_row.add_widget(Label(text=S["MESSAGES"].get("LANGUAGE_LABEL", "Γλώσσα:"), size_hint_x=0.4))

        language_options = [
            ("el", S["MESSAGES"].get("LANGUAGE_OPTION_EL", "Ελληνικά")),
            ("en", S["MESSAGES"].get("LANGUAGE_OPTION_EN", "English")),
        ]
        labels = [label for _, label in language_options]
        current_code = get_current_language()
        current_label = dict(language_options).get(current_code, labels[0])
        lang_spinner = Spinner(text=current_label, values=labels)
        lang_row.add_widget(lang_spinner)
        content.add_widget(lang_row)

        # Add spacer for better visual separation
        content.add_widget(Widget(size_hint_y=None, height=15))

        # Database path display and selection
        db_path_row = BoxLayout(orientation="vertical", size_hint_y=None, height=80, spacing=5)
        
        db_path_label = Label(text=S["MESSAGES"].get("DB_PATH_LABEL", "Διαδρομή Βάσης Δεδομένων:"), size_hint_y=None, height=20)
        db_path_row.add_widget(db_path_label)
        
        current_db_path = get_db_path()
        db_path_display = Label(
            text=current_db_path or S["MESSAGES"].get("DB_PATH_DEFAULT", "(Προεπιλεγμένη)"),
            size_hint_y=None,
            height=30,
            text_size=(self.root_layout.width * 0.5, None),
            markup=True,
            color=(0.5, 0.5, 0.5, 1)
        )
        db_path_row.add_widget(db_path_display)
        
        db_path_btn_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=40, spacing=10)
        change_db_btn = Button(text=S["MESSAGES"].get("DB_PATH_BUTTON", "Αλλαγή"), size_hint_x=0.5)
        reset_db_btn = Button(text=S["BUTTONS"].get("RESET", "Επαναφορά"), size_hint_x=0.5)
        
        def _change_db_path(*_args):
            from popups import ask_open_file
            try:
                file_path = ask_open_file(
                    title=S["MESSAGES"].get("DB_PATH_SELECT", "Επιλέξτε αρχείο βάσης δεδομένων"),
                    filetypes=(("Database files", "*.db"), ("All files", "*.*"))
                )
                if file_path:
                    if not os.path.exists(file_path):
                        show_message_popup(
                            S["TITLES"].get("ERROR", "Σφάλμα"),
                            S["MESSAGES"].get("DB_FILE_NOT_FOUND", "Το αρχείο της βάσης δεδομένων δεν βρέθηκε!")
                        )
                        return
                    if set_db_path(file_path):
                        db_path_display.text = file_path
                        show_message_popup(
                            S["TITLES"].get("INFO", "Πληροφορία"),
                            S["MESSAGES"].get(
                                "DB_PATH_SAVED_RESTART",
                                "Η διαδρομή της βάσης δεδομένων αποθηκεύτηκε. Η εφαρμογή θα επανεκκινήσει τώρα.",
                            ),
                            callback=lambda: self._restart_app()
                        )
            except Exception as e:
                show_message_popup(S["TITLES"].get("ERROR", "Σφάλμα"), str(e))
        
        def _reset_db_path(*_args):
            from config_manager import clear_db_path
            if clear_db_path():
                db_path_display.text = S["MESSAGES"].get("DB_PATH_DEFAULT", "(Προεπιλεγμένη)")
                show_message_popup(
                    S["TITLES"].get("INFO", "Πληροφορία"),
                    S["MESSAGES"].get(
                        "DB_PATH_SAVED_RESTART",
                        "Η διαδρομή της βάσης δεδομένων αποθηκεύτηκε. Η εφαρμογή θα επανεκκινήσει τώρα.",
                    ),
                    callback=lambda: self._restart_app()
                )
        
        change_db_btn.bind(on_press=_change_db_path)
        reset_db_btn.bind(on_press=_reset_db_path)
        db_path_btn_row.add_widget(change_db_btn)
        db_path_btn_row.add_widget(reset_db_btn)
        db_path_row.add_widget(db_path_btn_row)
        
        content.add_widget(db_path_row)

        content.add_widget(Widget(size_hint_y=None, height=15))

        # Sync/Backup settings
        sync_header_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=34, spacing=10)
        sync_header = Label(
            text=S["MESSAGES"].get("SYNC_SETTINGS_LABEL", "Ρυθμίσεις Συγχρονισμού / Αντιγράφων:"),
            size_hint_x=0.72,
            halign="left",
            valign="middle",
        )
        sync_header.bind(size=lambda obj, _val: setattr(obj, "text_size", (obj.width, obj.height)))

        sync_help_btn = Button(text=S["MESSAGES"].get("SYNC_SETTINGS_HELP_BUTTON", "Βοήθεια Sync Settings"), size_hint_x=0.28)

        def _show_sync_settings_help(*_args):
            help_text = S["MESSAGES"].get(
                "SYNC_SETTINGS_HELP_TEXT",
                "Πρώτη ρύθμιση (νέος υπολογιστής):\n"
                "1) Από τις Ρυθμίσεις, ορίστε πρώτα τη Διαδρομή Βάσης Δεδομένων (db_path).\n"
                "2) Για το sync_root_path: αφήστε κενό για προεπιλογή (δίπλα στη βάση: sync_exchange) ή επιλέξτε φάκελο στο OneDrive.\n"
                "3) Δεν χρειάζεται χειροκίνητη δημιουργία υποφακέλων· η εφαρμογή τους δημιουργεί αυτόματα.\n"
                "4) Κρατήστε ενεργό τον Αυτόματο συγχρονισμό και ορίστε διάστημα (λεπτά).\n"
                "5) Στην εκκίνηση γίνεται άμεσος συγχρονισμός, ενώ υπάρχει και χειροκίνητη επιλογή από το μενού εισαγωγής.",
            )
            show_message_popup(
                S["TITLES"].get("SYNC_SETTINGS", "Ρυθμίσεις Sync"),
                help_text,
            )

        sync_help_btn.bind(on_press=_show_sync_settings_help)
        sync_header_row.add_widget(sync_header)
        sync_header_row.add_widget(sync_help_btn)
        content.add_widget(sync_header_row)

        sync_enabled_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=40, spacing=10)
        sync_enabled_row.add_widget(
            Label(text=S["MESSAGES"].get("SYNC_AUTO_ENABLED_LABEL", "Αυτόματος συγχρονισμός:"), size_hint_x=0.75)
        )
        sync_enabled_chk = CheckBox(
            active=bool(get_app_setting("sync_auto_cycle_enabled", True)),
            size_hint_x=0.25,
        )
        sync_enabled_row.add_widget(sync_enabled_chk)
        content.add_widget(sync_enabled_row)

        startup_probe_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=40, spacing=10)
        startup_probe_row.add_widget(
            Label(
                text=S["MESSAGES"].get(
                    "STARTUP_SYNC_PROBE_ENABLED_LABEL",
                    "Έλεγχος διαφορών στην εκκίνηση (startup probe):",
                ),
                size_hint_x=0.75,
            )
        )
        startup_probe_chk = CheckBox(
            active=bool(get_app_setting("startup_sync_probe_enabled", True)),
            size_hint_x=0.25,
        )
        startup_probe_row.add_widget(startup_probe_chk)
        content.add_widget(startup_probe_row)

        startup_prompt_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=40, spacing=10)
        startup_prompt_row.add_widget(
            Label(
                text=S["MESSAGES"].get(
                    "STARTUP_SYNC_PROMPT_ON_CHANGE_LABEL",
                    "Ερώτηση πριν τον συγχρονισμό όταν υπάρχουν διαφορές:",
                ),
                size_hint_x=0.75,
            )
        )
        startup_prompt_chk = CheckBox(
            active=bool(get_app_setting("startup_sync_prompt_on_change", True)),
            size_hint_x=0.25,
        )
        startup_prompt_row.add_widget(startup_prompt_chk)
        content.add_widget(startup_prompt_row)

        # Prompt setting applies only if startup probe is enabled.
        startup_prompt_chk.disabled = not startup_probe_chk.active

        def _on_startup_probe_toggle(_instance, value):
            startup_prompt_chk.disabled = not bool(value)

        startup_probe_chk.bind(active=_on_startup_probe_toggle)

        interval_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=40, spacing=10)
        interval_row.add_widget(
            Label(text=S["MESSAGES"].get("SYNC_INTERVAL_MINUTES_LABEL", "Διάστημα αυτόματου συγχρονισμού (λεπτά):"), size_hint_x=0.7)
        )
        interval_input = TextInput(
            text=str(int(get_app_setting("sync_auto_cycle_minutes", 60))),
            multiline=False,
            size_hint_x=0.3,
        )
        interval_row.add_widget(interval_input)
        content.add_widget(interval_row)

        backup_on_change_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=40, spacing=10)
        backup_on_change_row.add_widget(
            Label(text=S["MESSAGES"].get("SYNC_BACKUP_ON_CHANGE_LABEL", "Δημιουργία snapshot όταν υπάρχουν νέες αποδεκτές αλλαγές:"), size_hint_x=0.75)
        )
        backup_on_change_chk = CheckBox(
            active=bool(get_app_setting("sync_backup_on_change", True)),
            size_hint_x=0.25,
        )
        backup_on_change_row.add_widget(backup_on_change_chk)
        content.add_widget(backup_on_change_row)

        hot_keep_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=40, spacing=10)
        hot_keep_row.add_widget(
            Label(text=S["MESSAGES"].get("SYNC_HOT_KEEP_LABEL", "Πλήθος snapshots που διατηρούνται (hot backup):"), size_hint_x=0.7)
        )
        hot_keep_input = TextInput(
            text=str(int(get_app_setting("backup_hot_keep", 3) or 3)),
            multiline=False,
            size_hint_x=0.3,
        )
        hot_keep_row.add_widget(hot_keep_input)
        content.add_widget(hot_keep_row)

        sync_root_row = BoxLayout(orientation="vertical", size_hint_y=None, height=110, spacing=5)
        sync_root_row.add_widget(
            Label(text=S["MESSAGES"].get("SYNC_ROOT_PATH_LABEL", "Φάκελος sync_root_path:"), size_hint_y=None, height=20)
        )
        sync_root_default = resolve_sync_root(self.db_path)
        sync_root_input = TextInput(
            text=str(get_app_setting("sync_root_path", sync_root_default) or sync_root_default),
            multiline=False,
            size_hint_y=None,
            height=35,
        )
        sync_root_row.add_widget(sync_root_input)
        sync_root_hint = Label(
            text=S["MESSAGES"].get(
                "SYNC_ROOT_PATH_HINT",
                "Κενό = προεπιλογή (δίπλα στη βάση: sync_exchange)",
            ),
            size_hint_y=None,
            height=20,
            color=(0.5, 0.5, 0.5, 1),
        )
        sync_root_row.add_widget(sync_root_hint)
        sync_root_btn_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=35, spacing=10)
        sync_root_reset_btn = Button(text=S["BUTTONS"].get("RESET", "Επαναφορά"))

        def _reset_sync_root(*_args):
            sync_root_input.text = ""

        sync_root_reset_btn.bind(on_press=_reset_sync_root)
        sync_root_btn_row.add_widget(sync_root_reset_btn)
        sync_root_row.add_widget(sync_root_btn_row)
        content.add_widget(sync_root_row)

        backup_root_row = BoxLayout(orientation="vertical", size_hint_y=None, height=110, spacing=5)
        backup_root_row.add_widget(
            Label(text=S["MESSAGES"].get("BACKUP_ROOT_PATH_LABEL", "Φάκελος backup_root_path:"), size_hint_y=None, height=20)
        )
        backup_root_default = resolve_backup_root(self.db_path)
        backup_root_input = TextInput(
            text=str(get_app_setting("backup_root_path", backup_root_default) or backup_root_default),
            multiline=False,
            size_hint_y=None,
            height=35,
        )
        backup_root_row.add_widget(backup_root_input)
        backup_root_hint = Label(
            text=S["MESSAGES"].get(
                "BACKUP_ROOT_PATH_HINT",
                "Κενό = προεπιλογή (δίπλα στη βάση: backups_auto)",
            ),
            size_hint_y=None,
            height=20,
            color=(0.5, 0.5, 0.5, 1),
        )
        backup_root_row.add_widget(backup_root_hint)
        backup_root_btn_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=35, spacing=10)
        backup_root_reset_btn = Button(text=S["BUTTONS"].get("RESET", "Επαναφορά"))

        def _reset_backup_root(*_args):
            backup_root_input.text = ""

        backup_root_reset_btn.bind(on_press=_reset_backup_root)
        backup_root_btn_row.add_widget(backup_root_reset_btn)
        backup_root_row.add_widget(backup_root_btn_row)
        content.add_widget(backup_root_row)

        scroll.add_widget(content)
        layout.add_widget(scroll)

        buttons = BoxLayout(size_hint_y=None, height=40, spacing=10)
        apply_btn = Button(text=S["BUTTONS"].get("APPLY", "Εφαρμογή"))
        close_btn = Button(text=S["BUTTONS"].get("CLOSE", "Κλείσιμο"))

        def _apply_settings(*_args):
            selected_label = lang_spinner.text
            selected_code = None
            for code, label in language_options:
                if label == selected_label:
                    selected_code = code
                    break
            if not selected_code:
                popup.dismiss()
                return

            try:
                interval_minutes = max(1, int((interval_input.text or "").strip() or "10"))
            except Exception:
                show_message_popup(
                    S["TITLES"].get("ERROR", "Σφάλμα"),
                    S["MESSAGES"].get("SYNC_INTERVAL_INVALID", "Μη έγκυρη τιμή για τα λεπτά αυτόματου συγχρονισμού."),
                )
                return

            try:
                hot_keep = max(1, int((hot_keep_input.text or "").strip() or "3"))
            except Exception:
                show_message_popup(
                    S["TITLES"].get("ERROR", "Σφάλμα"),
                    S["MESSAGES"].get("SYNC_HOT_KEEP_INVALID", "Μη έγκυρη τιμή για το πλήθος hot snapshots."),
                )
                return

            sync_root_text = (sync_root_input.text or "").strip()
            backup_root_text = (backup_root_input.text or "").strip()

            default_sync_root = resolve_sync_root(self.db_path)
            default_backup_root = resolve_backup_root(self.db_path)

            if sync_root_text:
                # Check if it's an existing file (not directory)
                if os.path.exists(sync_root_text) and not os.path.isdir(sync_root_text):
                    show_message_popup(
                        S["TITLES"]["ERROR"],
                        f"Το sync_root_path δείχνει σε αρχείο, όχι φάκελο:\n{sync_root_text}\n\nΠαρακαλώ επιλέξτε φάκελο."
                    )
                    return
                # Create directory only if it doesn't exist
                if not os.path.exists(sync_root_text):
                    try:
                        os.makedirs(sync_root_text)
                    except OSError as e:
                        show_message_popup(
                            S["TITLES"]["ERROR"],
                            f"Αδυναμία δημιουργίας φακέλου sync_root_path:\n\n{sync_root_text}\n\nΣφάλμα: {str(e)}"
                        )
                        return
                set_app_setting("sync_root_path", os.path.abspath(sync_root_text))
            else:
                clear_app_setting("sync_root_path")

            if backup_root_text:
                # Check if it's an existing file (not directory)
                if os.path.exists(backup_root_text) and not os.path.isdir(backup_root_text):
                    show_message_popup(
                        S["TITLES"]["ERROR"],
                        f"Το backup_root_path δείχνει σε αρχείο, όχι φάκελο:\n{backup_root_text}\n\nΠαρακαλώ επιλέξτε φάκελο."
                    )
                    return
                # Create directory only if it doesn't exist
                if not os.path.exists(backup_root_text):
                    try:
                        os.makedirs(backup_root_text)
                    except OSError as e:
                        show_message_popup(
                            S["TITLES"]["ERROR"],
                            f"Αδυναμία δημιουργίας φακέλου backup_root_path:\n\n{backup_root_text}\n\nΣφάλμα: {str(e)}"
                        )
                        return
                set_app_setting("backup_root_path", os.path.abspath(backup_root_text))
            else:
                clear_app_setting("backup_root_path")

            set_app_setting("sync_auto_cycle_enabled", bool(sync_enabled_chk.active))
            set_app_setting("startup_sync_probe_enabled", bool(startup_probe_chk.active))
            set_app_setting("startup_sync_prompt_on_change", bool(startup_prompt_chk.active))
            set_app_setting("sync_auto_cycle_minutes", interval_minutes)
            set_app_setting("sync_backup_on_change", bool(backup_on_change_chk.active))
            set_app_setting("backup_hot_keep", hot_keep)

            if sync_root_text and os.path.abspath(sync_root_text) == os.path.abspath(default_sync_root):
                clear_app_setting("sync_root_path")
            if backup_root_text and os.path.abspath(backup_root_text) == os.path.abspath(default_backup_root):
                clear_app_setting("backup_root_path")

            # Only show language restart message if language actually changed
            current_lang = get_current_language()
            language_changed = False
            if selected_code != current_lang:
                if set_current_language(selected_code):
                    language_changed = True

            popup.dismiss()
            
            if language_changed:
                show_message_popup(
                    S["TITLES"].get("INFO", "Πληροφορία"),
                    S["MESSAGES"].get(
                        "LANGUAGE_SAVED_RESTART",
                        "Η γλώσσα αποθηκεύτηκε. Η εφαρμογή θα επανεκκινήσει τώρα.",
                    ),
                    callback=lambda: self._restart_app()
                )
            else:
                show_message_popup(
                    S["TITLES"].get("SUCCESS", "Επιτυχία"),
                    S["MESSAGES"].get("SETTINGS_SAVED", "Οι ρυθμίσεις αποθηκεύτηκαν!"),
                )

        apply_btn.bind(on_press=_apply_settings)
        close_btn.bind(on_press=popup.dismiss)
        
        backup_btn = Button(text=S["MESSAGES"].get("MANAGE_BACKUPS_BUTTON", "Διαχείριση Αντιγράφων"))
        backup_btn.bind(on_press=lambda x: self._show_backup_management())
        
        buttons.add_widget(backup_btn)
        buttons.add_widget(apply_btn)
        buttons.add_widget(close_btn)
        layout.add_widget(buttons)

        popup.content = layout
        popup.open()

    def _restart_app(self):
        """Restart the application automatically."""
        try:
            # Close the current app
            self.stop()
            # Restart using the same Python executable and script
            python = sys.executable
            script = os.path.abspath(sys.argv[0])
            subprocess.Popen([python, script] + sys.argv[1:])
        except Exception as e:
            import logging
            logging.exception(f"Failed to restart app: {e}")

    def _show_backup_management(self):
        """Show backup management popup - list recent backups and restore options."""
        try:
            from sync_service import resolve_backup_root
            from kivy.uix.popup import Popup
            from kivy.uix.boxlayout import BoxLayout
            from kivy.uix.gridlayout import GridLayout
            from kivy.uix.label import Label
            from kivy.uix.button import Button
            from kivy.uix.scrollview import ScrollView
            
            backup_root = resolve_backup_root(self.db_path)
            hot_backup_dir = os.path.join(backup_root, "hot")
            
            # Get list of backup files
            backups = []
            if os.path.exists(hot_backup_dir):
                for filename in sorted(os.listdir(hot_backup_dir), reverse=True):
                    filepath = os.path.join(hot_backup_dir, filename)
                    if os.path.isfile(filepath) and filename.endswith('.sqlite'):
                        try:
                            size = os.path.getsize(filepath)
                            mtime = os.path.getmtime(filepath)
                            backups.append({
                                'name': filename,
                                'path': filepath,
                                'size': size,
                                'mtime': mtime
                            })
                        except Exception:
                            pass
            
            # Keep only last 5
            backups = backups[:5]
            
            # Create popup
            popup = Popup(
                title=S["MESSAGES"].get("MANAGE_BACKUPS_TITLE", "Διαχείριση Αντιγράφων"),
                size_hint=(0.9, 0.8)
            )
            layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
            
            # Manual backup button
            manual_backup_btn = Button(
                text=S["MESSAGES"].get("CREATE_MANUAL_BACKUP", "Δημιουργία χειροκίνητου αντιγράφου"),
                size_hint_y=0.1
            )
            
            def _create_manual_backup(*_args):
                try:
                    import shutil
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"substations_{timestamp}_manual.sqlite"
                    dest_path = os.path.join(hot_backup_dir, filename)
                    os.makedirs(hot_backup_dir, exist_ok=True)
                    shutil.copy(self.db_path, dest_path)
                    show_message_popup(
                        S["TITLES"].get("SUCCESS", "Επιτυχία"),
                        S["MESSAGES"].get("MANUAL_BACKUP_CREATED", "Χειροκίνητο αντίγραφο δημιουργήθηκε!")
                    )
                    popup.dismiss()
                    self._show_backup_management()  # Refresh
                except Exception as e:
                    show_message_popup(
                        S["TITLES"].get("ERROR", "Σφάλμα"),
                        f"Αδυναμία δημιουργίας αντιγράφου:\n{str(e)}"
                    )
            
            manual_backup_btn.bind(on_press=_create_manual_backup)
            layout.add_widget(manual_backup_btn)
            
            # Backups list
            scroll = ScrollView(size_hint=(1, 0.75))
            backups_list = GridLayout(cols=1, spacing=5, size_hint_y=None, padding=5)
            backups_list.bind(minimum_height=backups_list.setter('height'))
            
            if backups:
                for backup in backups:
                    from datetime import datetime
                    dt = datetime.fromtimestamp(backup['mtime'])
                    size_mb = backup['size'] / (1024*1024)
                    backup_row = BoxLayout(orientation='horizontal', size_hint_y=None, height=60, spacing=5)
                    
                    # Backup info
                    info_text = f"{backup['name']}\n{dt.strftime('%d/%m/%Y %H:%M')} ({size_mb:.1f} MB)"
                    backup_row.add_widget(Label(
                        text=info_text,
                        size_hint_x=0.6,
                        halign='left',
                        valign='middle'
                    ))
                    
                    # Restore button
                    restore_btn = Button(text="Επαναφορά", size_hint_x=0.4)
                    
                    def _restore_backup(backup_info=backup, btn=restore_btn):
                        def _confirm_restore(*_args):
                            try:
                                import shutil
                                # Close connection before restore
                                self.conn.close()
                                # Create safety backup before restore
                                from datetime import datetime
                                safety_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                                safety_backup = os.path.join(hot_backup_dir, f"substations_{safety_ts}_before_restore.sqlite")
                                shutil.copy(self.db_path, safety_backup)
                                # Restore
                                shutil.copy(backup_info['path'], self.db_path)
                                # Reopen connection
                                self.conn = init_db(self.db_path)
                                show_message_popup(
                                    S["TITLES"].get("SUCCESS", "Επιτυχία"),
                                    S["MESSAGES"].get("BACKUP_RESTORED", "Το αντίγραφο επαναφέρθηκε με επιτυχία!")
                                )
                                confirmation_popup.dismiss()
                                popup.dismiss()
                            except Exception as e:
                                show_message_popup(
                                    S["TITLES"].get("ERROR", "Σφάλμα"),
                                    f"Αδυναμία επαναφοράς:\n{str(e)}"
                                )
                        
                        confirmation_popup = Popup(
                            title="Επιβεβαίωση Επαναφοράς",
                            size_hint=(0.8, 0.4)
                        )
                        conf_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
                        conf_layout.add_widget(Label(
                            text=S["MESSAGES"].get("RESTORE_BACKUP_CONFIRM", "Θέλετε να επαναφέρετε αυτό το αντίγραφο;\nΤο τρέχον θα αποθηκευτεί ως safety backup.")
                        ))
                        conf_buttons = BoxLayout(size_hint_y=None, height=40, spacing=10)
                        yes_btn = Button(text=S["BUTTONS"].get("YES", "Ναι"))
                        no_btn = Button(text=S["BUTTONS"].get("NO", "Όχι"))
                        yes_btn.bind(on_press=_confirm_restore)
                        no_btn.bind(on_press=confirmation_popup.dismiss)
                        conf_buttons.add_widget(yes_btn)
                        conf_buttons.add_widget(no_btn)
                        conf_layout.add_widget(conf_buttons)
                        confirmation_popup.content = conf_layout
                        confirmation_popup.open()
                    
                    restore_btn.bind(on_press=_restore_backup)
                    backup_row.add_widget(restore_btn)
                    backups_list.add_widget(backup_row)
            else:
                backups_list.add_widget(Label(
                    text=S["MESSAGES"].get("NO_BACKUPS_AVAILABLE", "Δεν υπάρχουν διαθέσιμα αντίγραφα"),
                    size_hint_y=None,
                    height=40
                ))
            
            scroll.add_widget(backups_list)
            layout.add_widget(scroll)
            
            # Close button
            close_btn = Button(text=S["BUTTONS"].get("CLOSE", "Κλείσιμο"), size_hint_y=0.1)
            close_btn.bind(on_press=popup.dismiss)
            layout.add_widget(close_btn)
            
            popup.content = layout
            popup.open()
            
        except Exception as e:
            logging.exception(f"Failed to show backup management: {e}")
            show_message_popup(
                S["TITLES"].get("ERROR", "Σφάλμα"),
                f"Αδυναμία διαχείρισης αντιγράφων:\n{str(e)}"
            )

    def show_logout_confirm(self):
        """Show logout confirmation dialog."""
        from kivy.uix.popup import Popup
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.label import Label
        from kivy.uix.button import Button
        
        popup = Popup(title=S["BUTTONS"].get("LOGOUT", "Αποσύνδεση"), size_hint=(0.4, 0.3))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
        layout.add_widget(Label(text=S["MESSAGES"].get("LOGOUT_CONFIRM", "Θέλετε να αποσυνδεθείτε;")))
        
        buttons = BoxLayout(size_hint_y=None, height=40, spacing=10)
        yes_btn = Button(text=S["BUTTONS"].get("YES", "Ναι"))
        no_btn = Button(text=S["BUTTONS"].get("NO", "Όχι"))
        
        def _confirm_logout(*_args):
            clear_current_user()
            popup.dismiss()
            # Restart app to show login screen
            self.stop()
        
        yes_btn.bind(on_press=_confirm_logout)
        no_btn.bind(on_press=popup.dismiss)
        buttons.add_widget(yes_btn)
        buttons.add_widget(no_btn)
        layout.add_widget(buttons)
        
        popup.content = layout
        popup.open()

    def show_login_popup(self, on_login_success=None):
        """Show login popup for user to select their name.
        
        Args:
            on_login_success: Callback to invoke after successful login
        """
        from kivy.uix.popup import Popup
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.label import Label
        from kivy.uix.button import Button
        from kivy.uix.spinner import Spinner
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Get all active people
        c.execute("SELECT id, name, role FROM people WHERE active=1 ORDER BY COALESCE(surname, name) COLLATE NOCASE")
        people = c.fetchall()
        conn.close()
        
        if not people:
            show_message_popup(
                S["TITLES"].get("ERROR", "Σφάλμα"),
                S["MESSAGES"].get("NO_PEOPLE", "Δεν υπάρχουν καταχωρημένα άτομα. Παρακαλώ προσθέστε προσωπικό."),
            )
            # Can't continue without people - exit app
            self.stop()
            return
        
        popup = Popup(
            title=S["MESSAGES"].get("LOGIN_TITLE", "Σύνδεση Χρήστη"),
            size_hint=(0.5, 0.4),
            auto_dismiss=False  # Require login - can't dismiss
        )
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
        
        layout.add_widget(Label(
            text=S["MESSAGES"].get("LOGIN_PROMPT", "Επιλέξτε το όνομά σας για να συνδεθείτε:"),
            size_hint_y=None,
            height=30
        ))
        
        # Create people map: display name -> (id, name, role)
        people_map = {f"{p[1]} ({p[2]})": p for p in people}
        people_labels = list(people_map.keys())
        
        # Pre-select last logged-in user if available
        last_user = get_current_user()
        default_selection = people_labels[0] if people_labels else ""
        if last_user:
            # Find the last user in the people map by matching ID
            for label, user_data in people_map.items():
                if user_data[0] == last_user["id"]:
                    default_selection = label
                    break
        
        user_spinner = Spinner(
            text=default_selection,
            values=people_labels,
            size_hint_y=None,
            height=40
        )
        layout.add_widget(user_spinner)
        
        buttons = BoxLayout(size_hint_y=None, height=40, spacing=10)
        login_btn = Button(text=S["BUTTONS"].get("LOGIN", "Σύνδεση"))
        
        def _do_login(*_args):
            selected_label = user_spinner.text
            if not selected_label or selected_label not in people_map:
                return
            
            user_id, name, role = people_map[selected_label]
            if set_current_user(user_id, name, role):
                popup.dismiss()
                if on_login_success:
                    on_login_success()
        
        login_btn.bind(on_press=_do_login)
        buttons.add_widget(login_btn)
        layout.add_widget(buttons)
        
        popup.content = layout
        popup.open()

    def _get_app_version(self):
        version = os.environ.get("APP_VERSION")
        if version:
            return version.strip()

        version_path = os.path.join(os.path.dirname(__file__), "VERSION")
        try:
            if os.path.exists(version_path):
                with open(version_path, "r", encoding="utf-8") as vf:
                    return vf.read().strip() or "-"
        except Exception:
            return "-"

        return "-"

    def _get_sf6_report_data(self, year: str):
        from reports import _get_sf6_report_data as _f
        return _f(self, year)

    def _export_sf6_excel(self, year: str):
        from reports import _export_sf6_excel as _f
        return _f(self, year)

    def show_sf6_management_popup(self, instance=None):
        from reports import show_sf6_management_popup as _f
        return _f(self, instance)

    def _format_maintenance_date(self, date_time_str):
        """Format maintenance date to DD/MM/YYYY for naming."""
        try:
            dt = datetime.strptime(date_time_str, "%Y-%m-%d %H:%M")
            return dt.strftime("%d/%m/%Y")
        except Exception:
            try:
                dt = datetime.strptime(date_time_str, "%Y-%m-%d")
                return dt.strftime("%d/%m/%Y")
            except Exception:
                return date_time_str

    def _build_maintenance_name(self, substation_name, date_time_str):
        formatted_date = self._format_maintenance_date(date_time_str)
        return S["MESSAGES"].get("MAINTENANCE_NAME_FMT", "Υ/Σ {substation_name} - {date}").format(
            substation_name=substation_name, date=formatted_date
        )

    def _derive_voltage_level(self, element_type: str) -> str:
        if self._is_transformer(element_type):
            return "150/20KV"
        if element_type == self.ELEM_BREAKER_MT:
            return "20KV"
        if element_type == self.ELEM_BREAKER_YT:
            return "150KV"
        if element_type == "Μ/Σ ΧΤ/ΜΤ (ΒΜΣ)":
            return "20KV/400V"
        if element_type in ["Συστοιχία Συσσωρευτών", "Μ/Σ Εγχύσεως"]:
            return "20KV"
        return ""

    # Deprecated: previously returned options including an empty placeholder.
    # Use `_derive_voltage_level()` directly and construct values where needed.

    def _get_maintenance_people(self, maintenance_id):
        c = self.conn.cursor()
        c.execute(
            """
            SELECT COALESCE(p.surname, p.name) || ' ' || COALESCE(p.given_name, '') as display_name, mp.role
            FROM maintenance_people mp
            JOIN people p ON mp.person_id = p.id
            WHERE mp.maintenance_id = ?
            ORDER BY mp.role, p.name
        """,
            (maintenance_id,),
        )
        rows = c.fetchall()
        responsible = None
        crew = []
        for name, role in rows:
            if role == "responsible" and responsible is None:
                responsible = name
            elif role == "crew":
                crew.append(name)
        return responsible, crew

    def show_people_management(self, instance=None):
        # Delegate to PeopleManager (extracted to people.py)
        if not hasattr(self, "people_manager"):
            try:
                from people import PeopleManager

                self.people_manager = PeopleManager(self)
            except Exception:
                show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["STAFF_LOAD_FAILED"])
                return
        self.people_manager.show_people_management(instance)

    def _toggle_person_active(self, person_id, active, refresh_cb):
        c = self.conn.cursor()
        c.execute("UPDATE people SET active=? WHERE id=?", (active, person_id))
        self.conn.commit()
        if refresh_cb:
            refresh_cb()

    def _toggle_person_receiver(self, person_id, report_receiver, refresh_cb):
        c = self.conn.cursor()
        c.execute(
            "UPDATE people SET report_receiver=? WHERE id=?",
            (report_receiver, person_id),
        )
        self.conn.commit()
        if refresh_cb:
            refresh_cb()

    def _confirm_delete_person(self, person_id, person_name, refresh_cb):
        """Confirm and delete person if not referenced in maintenance records."""
        c = self.conn.cursor()
        c.execute(
            "SELECT COUNT(*) FROM maintenance_people WHERE person_id=?", (person_id,)
        )
        usage_count = c.fetchone()[0]
        if usage_count > 0:
            show_message_popup(
                S["TITLES"].get("INFO", "Πληροφορία"),
                S["MESSAGES"].get(
                    "PERSON_IN_USE",
                    "Το άτομο έχει χρησιμοποιηθεί σε συντηρήσεις. Διαγράψτε το μόνο αφού αφαιρεθεί από το ιστορικό ή απενεργοποιήστε το.",
                ),
            )
            return

        from reports import show_confirm

        def confirm_delete():
            c.execute("DELETE FROM people WHERE id=?", (person_id,))
            self.conn.commit()
            if refresh_cb:
                refresh_cb()

        show_confirm(
            S["MESSAGES"].get("CONFIRM_DELETE_TITLE", "Επιβεβαίωση Διαγραφής"),
            S["MESSAGES"].get(
                "CONFIRM_DELETE_PERSON_FMT",
                S["MESSAGES"].get("CONFIRM_DELETE_PERSON_FMT", "Είστε σίγουροι ότι θέλετε να διαγράψετε\nτο άτομο \"{person_name}\";"),
            ).format(person_name=person_name),
            yes_callback=confirm_delete,
            yes_color=(1, 0, 0, 1),
            yes_text=S["BUTTONS"]["YES"].upper(),
            no_text=S["BUTTONS"]["NO"].upper(),
        )

    def _migrate_people_name_columns(self):
        """Add `given_name` and `surname` columns to `people` if missing and populate them.

        Existing `name` values are expected as "Given Family" and will be split on the
        last space. If there's no space the whole value is treated as `surname`.
        """
        c = self.conn.cursor()
        cols = [r[1] for r in c.execute("PRAGMA table_info(people)")]
        need_commit = False
        if "given_name" not in cols:
            c.execute("ALTER TABLE people ADD COLUMN given_name TEXT")
            need_commit = True
        if "surname" not in cols:
            c.execute("ALTER TABLE people ADD COLUMN surname TEXT")
            need_commit = True
        if need_commit:
            self.conn.commit()

        # Populate given_name and surname where missing
        c.execute("SELECT id, name, given_name, surname FROM people")
        rows = c.fetchall()
        for pid, fullname, gname, sname in rows:
            if (gname and gname.strip()) or (sname and sname.strip()):
                continue
            if not fullname:
                continue
            parts = fullname.strip().rsplit(" ", 1)
            if len(parts) == 1:
                given = ""
                surname = parts[0]
            else:
                given, surname = parts[0], parts[1]
            # store both components and update the canonical `name` to "Surname Given"
            composite = f"{surname} {given}".strip()
            c.execute(
                "UPDATE people SET given_name=?, surname=?, name=? WHERE id=?",
                (given, surname, composite, pid),
            )
        self.conn.commit()

    def _show_edit_person_popup(self, person_id, refresh_cb):
        """Edit person details."""
        c = self.conn.cursor()
        c.execute(
            "SELECT name, given_name, surname, role, email, report_receiver, active FROM people WHERE id=?",
            (person_id,),
        )
        row = c.fetchone()
        if not row:
            show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"].get("PERSON_NOT_FOUND", "Το άτομο δεν βρέθηκε!"))
            return

        name, given, surname, role, email, report_receiver, active = row

        popup = Popup(title=S["MESSAGES"].get("EDIT_PERSON_TITLE", "Επεξεργασία Προσώπου"), size_hint=(0.6, 0.5))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        form = GridLayout(cols=2, size_hint_y=None, height=160, spacing=5)
        form.add_widget(Label(text=S["MESSAGES"]["SURNAME_LABEL"], size_hint_x=0.3))
        surname_input = TextInput(text=surname or "", multiline=False, size_hint_x=0.7)
        form.add_widget(surname_input)

        form.add_widget(Label(text=S["MESSAGES"]["NAME_LABEL"], size_hint_x=0.3))
        name_input = TextInput(text=given or "", multiline=False, size_hint_x=0.7)
        form.add_widget(name_input)

        form.add_widget(Label(text=S["MESSAGES"]["ROLE_LABEL"], size_hint_x=0.3))
        # Use Spinner for locked role values; include current role if it's not in the enum
        role_values = list(PEOPLE_ROLES)
        if role and role not in role_values:
            role_values.insert(0, role)
        role_spinner = Spinner(text=role or (role_values[0] if role_values else ""), values=role_values, size_hint_x=0.7)
        form.add_widget(role_spinner)

        form.add_widget(Label(text=S["MESSAGES"]["EMAIL_LABEL"], size_hint_x=0.3))
        email_input = TextInput(text=email or "", multiline=False, size_hint_x=0.7)
        form.add_widget(email_input)

        layout.add_widget(form)

        receiver_layout = BoxLayout(size_hint_y=None, height=30, spacing=5)
        receiver_checkbox = CheckBox(
            size_hint_x=0.1,
            active=bool(report_receiver),
            color=self.theme.get("primary", (0.05, 0.18, 0.36, 1)),
        )
        receiver_layout.add_widget(receiver_checkbox)
        receiver_layout.add_widget(
            Label(text=S["MESSAGES"]["EMAIL_RECIPIENT_LABEL"], size_hint_x=0.9)
        )
        layout.add_widget(receiver_layout)

        active_layout = BoxLayout(size_hint_y=None, height=30, spacing=5)
        active_checkbox = CheckBox(
            size_hint_x=0.1,
            active=bool(active),
            color=self.theme.get("primary", (0.05, 0.18, 0.36, 1)),
        )
        active_layout.add_widget(active_checkbox)
        active_layout.add_widget(Label(text=S["MESSAGES"]["ACTIVE_LABEL"], size_hint_x=0.9))
        layout.add_widget(active_layout)

        buttons_layout = BoxLayout(size_hint_y=None, height=40, spacing=10)

        def save_changes():
            new_surname = surname_input.text.strip()
            new_given = name_input.text.strip()
            new_role = role_spinner.text.strip()
            new_email = email_input.text.strip()
            if not new_surname or not new_role:
                show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["SURNAME_ROLE_REQUIRED"])
                return
            composite = f"{new_surname} {new_given}".strip()
            c.execute(
                "UPDATE people SET name=?, given_name=?, surname=?, role=?, email=?, report_receiver=?, active=? WHERE id=?",
                (
                    composite,
                    new_given,
                    new_surname,
                    new_role,
                    new_email,
                    1 if receiver_checkbox.active else 0,
                    1 if active_checkbox.active else 0,
                    person_id,
                ),
            )
            self.conn.commit()
            popup.dismiss()
            if refresh_cb:
                refresh_cb()

        save_btn = Button(text=S["BUTTONS"]["SAVE"])
        save_btn.bind(on_press=lambda x: save_changes())
        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
        cancel_btn.bind(on_press=popup.dismiss)

        buttons_layout.add_widget(save_btn)
        buttons_layout.add_widget(cancel_btn)
        layout.add_widget(buttons_layout)

        popup.content = layout
        popup.open()

    def _element_type_report_label(self, element_type):
        mapping = {
            self.ELEM_BREAKER_MT: "διακόπτες Μέσης Τάσης",
            self.ELEM_BREAKER_YT: "διακόπτες Υψηλής Τάσης",
            "Μετασχηματιστής 150/20KV": "μετασχηματιστές 150/20KV",
            "Motor Drive": "motor drives",
            "Μ/Σ Εγχύσεως": "Μ/Σ Εγχύσεως",
            "Μ/Σ Έντασης": "Μ/Σ Έντασης",
            "Μ/Σ Τάσης": "Μ/Σ Τάσης",
            "Μ/Σ ΧΤ/ΜΤ (ΒΜΣ)": "Μ/Σ ΧΤ/ΜΤ (ΒΜΣ)",
            "Αποζεύκτης": "αποζεύκτες",
            "Ασφαλειοαποζεύκτης": "ασφαλειοαποζεύκτες",
            "Γειωτής": "γειωτές",
            "Συστοιχία Πυκνωτών": "συστοιχίες πυκνωτών",
            "Αντίσταση Κόμβου": "αντιστάσεις κόμβου",
            "Αλεξικέραυνο": "αλεξικέραυνα",
            "Συστοιχία Συσσωρευτών": "συστοιχίες συσσωρευτών",
        }
        return mapping.get(element_type, element_type)

    def send_maintenance_email_report(self, maintenance_id):
        """Compose and open an email report for a maintenance instance."""
        c = self.conn.cursor()
        c.execute(
            """
            SELECT m.name, m.date_time, s.name
            FROM maintenance m
            JOIN substations s ON m.substation_id = s.id
            WHERE m.id = ?
        """,
            (maintenance_id,),
        )
        maint_row = c.fetchone()
        if not maint_row:
            show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"].get("MAINTENANCE_NOT_FOUND", "Η συντήρηση δεν βρέθηκε."))
            return

        maint_name, date_time, substation_name = maint_row
        display_name = maint_name or self._build_maintenance_name(
            substation_name, date_time
        )

        c.execute(
            """
            SELECT e.element_type, e.name
            FROM maintenance_elements me
            JOIN elements e ON me.element_id = e.id
            WHERE me.maintenance_id = ?
            ORDER BY e.element_type, e.name
        """,
            (maintenance_id,),
        )
        elements = c.fetchall()

        if not elements:
            show_message_popup(
                S["TITLES"]["INFO"], S["MESSAGES"].get("NO_RECORD_ELEMENTS", "Δεν υπάρχουν στοιχεία για αυτή τη συντήρηση.")
            )
            return

        # Group by element type
        grouped = {}
        for elem_type, elem_name in elements:
            grouped.setdefault(elem_type, []).append(elem_name)

        responsible, crew = self._get_maintenance_people(maintenance_id)
        crew_text = ", ".join(crew) if crew else "-"
        resp_text = responsible if responsible else "-"

        lines = []
        lines.append(f"Αναφορά Συντήρησης: {display_name}")
        lines.append(f"Υποσταθμός: {substation_name}")
        lines.append(f"{S['MESSAGES'].get('DATE_LABEL','Ημερομηνία')}: {date_time}")
        lines.append(S["MESSAGES"].get("PEOPLE_SUMMARY", "Υπεύθυνος: {resp} | Ομάδα: {crew}").format(resp=resp_text, crew=crew_text))
        lines.append("")

        for elem_type, names in grouped.items():
            label = self._element_type_report_label(elem_type)
            lines.append(f"Συντηρήθηκαν οι παρακάτω {label}:")
            for name in names:
                lines.append(f" - {name}")
            lines.append("")

        body = "\n".join(lines).strip()
        subject = f"Αναφορά Συντήρησης - {display_name}"

        c.execute(
            "SELECT email FROM people WHERE active=1 AND report_receiver=1 AND email IS NOT NULL AND email != ''"
        )
        recipients = [row[0] for row in c.fetchall()]

        if not recipients:
            show_message_popup(
                S["TITLES"]["ERROR"], S["MESSAGES"].get("EMAIL_RECIPIENTS_MISSING", "Δεν υπάρχουν παραλήπτες email. Προσθέστε παραλήπτες από τη Διαχείριση Προσωπικού."),
            )
            return

        import urllib.parse

        mailto = "mailto:" + ",".join(recipients)
        subject_encoded = urllib.parse.quote(subject or "", safe="")
        body_encoded = urllib.parse.quote(body or "", safe="")
        webbrowser.open(f"{mailto}?subject={subject_encoded}&body={body_encoded}")

    def show_inspection_menu_popup(self, instance=None):
        # write a small debug trace to disk (visible even if popup hidden)
        try:
            with open('inspections_debug.log', 'a', encoding='utf-8') as _fh:
                _fh.write('show_inspection_menu_popup invoked\n')
        except Exception:
            pass
        # visual debug popup removed to avoid obscuring the inspection menu
        try:
            from inspections import handle_inspection_menu as _f
            return _f(self, instance)
        except Exception:
            try:
                import traceback
                with open('inspections_debug.log', 'a', encoding='utf-8') as _fh:
                    _fh.write('menu_handler_failed:\n')
                    _fh.write(traceback.format_exc())
                    _fh.write('\n')
            except Exception:
                pass
            return None

    def show_import_inspections_dialog(self, instance):
        from inspections import show_import_inspections_dialog_delegate
        return show_import_inspections_dialog_delegate(self, instance)

    def _read_inspection_template_columns(self):
        from inspections import _read_inspection_template_columns as _f
        return _f()

    def _get_inspection_fallback_fields(self):
        from inspections import _get_inspection_fallback_fields as _f
        return _f()

    def _is_inspection_meta_column(self, col_name, keywords):
        from inspections import _detect_inspection_column as _f
        return bool(_f([col_name], keywords))

    def show_inspection_entry_popup(
        self, instance=None, preselected_substation_name=None, parent_popup=None
    ):
        if parent_popup:
            try:
                parent_popup.dismiss()
            except Exception:
                pass
        c = self.conn.cursor()
        c.execute("SELECT id, name FROM substations ORDER BY name")
        substations = c.fetchall()

        if not substations:
            show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["NO_SUBSTATIONS"])
            return

        popup = Popup(title=S["TITLES"]["INSPECTION_ENTRY"], size_hint=(0.9, 0.95))
        main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
        content_layout = GridLayout(cols=1, spacing=10, size_hint_y=None, padding=10)
        content_layout.bind(minimum_height=content_layout.setter("height"))

        content_layout.add_widget(
            Label(text=S["MESSAGES"]["SELECT_SUBSTATION"], size_hint_y=None, height=35)
        )
        substation_map = {s[1]: s[0] for s in substations}
        initial_substation = (
            preselected_substation_name
            if preselected_substation_name in substation_map
            else substations[0][1]
        )
        substation_row = BoxLayout(size_hint_y=None, height=40, spacing=5)
        substation_label = Label(text=S["MESSAGES"]["SUBSTATION_LABEL"], size_hint_x=0.18)
        substation_picker = BoxLayout(size_hint_x=0.42, spacing=5)
        substation_input = TextInput(
            text=initial_substation, readonly=True, size_hint_x=0.7, multiline=False
        )
        select_sub_btn = Button(text=S["MESSAGES"].get("SELECT_PROMPT", "Επιλογή"), size_hint_x=0.3)
        substation_picker.add_widget(substation_input)
        substation_picker.add_widget(select_sub_btn)
        form_number_label = Label(text=S["MESSAGES"]["FORM_NUMBER"], size_hint_x=0.18)
        form_number_input = TextInput(
            hint_text=S["MESSAGES"].get("FORM_NUMBER_HINT", "Αρ. Δελτίου"), size_hint_x=0.22, multiline=False
        )
        substation_row.add_widget(substation_label)
        substation_row.add_widget(substation_picker)
        substation_row.add_widget(form_number_label)
        substation_row.add_widget(form_number_input)
        content_layout.add_widget(substation_row)

        # People list for inspector
        c.execute("SELECT name FROM people WHERE active=1 ORDER BY COALESCE(surname, name) COLLATE NOCASE")
        people = [row[0] for row in c.fetchall()]
        if not people:
            show_message_popup(
                S["TITLES"]["ERROR"],
                S["MESSAGES"].get("NO_PEOPLE", "Δεν υπάρχουν καταχωρημένα άτομα. Παρακαλώ προσθέστε προσωπικό."),
                callback=lambda: self.show_people_management(None),
            )
            return

        # Pre-select logged-in user as inspector
        inspector_default = people[0] if people else ""
        current_user = get_current_user()
        if current_user:
            # Find the logged-in user's name in the people list
            for person_name in people:
                if current_user["name"] == person_name:
                    inspector_default = person_name
                    break

        row_two = BoxLayout(size_hint_y=None, height=40, spacing=5)
        date_label = Label(text=S["MESSAGES"]["DATE_LABEL"], size_hint_x=0.18)
        date_input = TextInput(
            text=datetime.now().strftime("%Y-%m-%d"),
            hint_text=S["MESSAGES"].get("DATE_HINT", "YYYY-MM-DD"),
            size_hint_x=0.32,
            height=40,
            multiline=False,
        )
        region_label = Label(text=S["MESSAGES"]["REGION_LABEL"], size_hint_x=0.14)
        region_input = TextInput(hint_text=S["MESSAGES"].get("REGION_HINT", "Περιοχή"), size_hint_x=0.16, multiline=False)
        inspector_label = Label(text=S["MESSAGES"]["INSPECTOR_LABEL"], size_hint_x=0.12)
        inspector_spinner = Spinner(
            text=inspector_default, values=people, size_hint_x=0.18, height=40
        )
        row_two.add_widget(date_label)
        row_two.add_widget(date_input)
        row_two.add_widget(region_label)
        row_two.add_widget(region_input)
        row_two.add_widget(inspector_label)
        row_two.add_widget(inspector_spinner)
        content_layout.add_widget(row_two)

        row_three = BoxLayout(size_hint_y=None, height=40, spacing=5)
        month_label = Label(text=S["MESSAGES"]["MONTH_LABEL"], size_hint_x=0.18)
        month_input = TextInput(readonly=True, size_hint_x=0.32, multiline=False)
        day_label = Label(text=S["MESSAGES"]["DAY_LABEL"], size_hint_x=0.18)
        day_input = TextInput(readonly=True, size_hint_x=0.32, multiline=False)
        year_label = Label(text=S["MESSAGES"]["YEAR_LABEL"], size_hint_x=0.18)
        year_input = TextInput(readonly=True, size_hint_x=0.18, multiline=False)
        row_three.add_widget(month_label)
        row_three.add_widget(month_input)
        row_three.add_widget(day_label)
        row_three.add_widget(day_input)
        row_three.add_widget(year_label)
        row_three.add_widget(year_input)
        content_layout.add_widget(row_three)

        fields_inputs = []

        greek_months = S["MESSAGES"].get("MONTHS", [
            "Ιανουάριος",
            "Φεβρουάριος",
            "Μάρτιος",
            "Απρίλιος",
            "Μάιος",
            "Ιούνιος",
            "Ιούλιος",
            "Αύγουστος",
            "Σεπτέμβριος",
            "Οκτώβριος",
            "Νοέμβριος",
            "Δεκέμβριος",
        ])
        greek_days = S["MESSAGES"].get("DAYS", [
            "Δευτέρα",
            "Τρίτη",
            "Τετάρτη",
            "Πέμπτη",
            "Παρασκευή",
            "Σάββατο",
            "Κυριακή",
        ])

        def update_date_meta(_instance=None, text=None):
            parsed = self._parse_inspection_date(date_input.text.strip())
            try:
                dt = datetime.strptime(parsed, "%Y-%m-%d")
                month_input.text = greek_months[dt.month - 1]
                day_input.text = greek_days[dt.weekday()]
                year_input.text = f"{dt.year}"
            except Exception:
                month_input.text = ""
                day_input.text = ""
                year_input.text = ""

        def open_substation_selection(_instance=None):
            self._show_substation_selection_window_with_callback(
                popup,
                substations,
                lambda selected_name: setattr(substation_input, "text", selected_name),
            )

        select_sub_btn.bind(on_press=open_substation_selection)
        date_input.bind(text=update_date_meta)
        update_date_meta()

        # Chapter 2: Έλεγχος Χώρων ΥΣ
        content_layout.add_widget(
            Label(
                text=S["MESSAGES"].get("INSPECTION_SECTION_2", "[b]Έλεγχος Χώρων ΥΣ[/b]"), markup=True, size_hint_y=None, height=35
            )
        )

        rows = S["MESSAGES"].get("INSPECTION_ROWS", [])

        def add_inspection_row(label_text):
            row = BoxLayout(size_hint_y=None, height=60, spacing=5)
            label = Label(text=label_text, size_hint_x=0.7, size_hint_y=None)
            label.bind(width=lambda inst, val: setattr(inst, "text_size", (val, None)))

            ti = TextInput(
                hint_text=S["MESSAGES"]["OBSERVATIONS_HINT"],
                size_hint_x=0.3,
                size_hint_y=None,
                height=60,
                multiline=True,
            )

            def sync_row_height(_instance=None, _value=None):
                row.height = max(
                    label.texture_size[1] if label.texture_size else 0, ti.height, 60
                )
                label.height = row.height

            label.bind(texture_size=sync_row_height)
            ti.bind(height=sync_row_height)
            sync_row_height()

            row.add_widget(label)
            row.add_widget(ti)
            content_layout.add_widget(row)
            fields_inputs.append((label_text, ti))

        # Section 1 rows
        for _r in rows[0:4]:
            add_inspection_row(_r)

        # Chapter 3: Μ/Σ 150/20kV & Διακόπτες 150kV & 20kV
        content_layout.add_widget(
            Label(
                text=S["MESSAGES"].get("INSPECTION_SECTION_3", "[b]Μ/Σ 150/20kV & Διακόπτες 150kV & 20kV[/b]"),
                markup=True,
                size_hint_y=None,
                height=35,
            )
        )

        # Section 2 rows
        for _r in rows[4:12]:
            add_inspection_row(_r)

        # Chapter 3: Υπαίθριες πύλες 20 kV
        content_layout.add_widget(
            Label(
                text=S["MESSAGES"].get("INSPECTION_SECTION_3A", "[b]Υπαίθριες πύλες 20 kV[/b]"),
                markup=True,
                size_hint_y=None,
                height=35,
            )
        )
        # Section 3a: single row
        if len(rows) > 12:
            add_inspection_row(rows[12])

        # Chapter 4: Υπαίθριες πύλες 20 kV
        content_layout.add_widget(
            Label(
                text=S["MESSAGES"].get("INSPECTION_SECTION_3B", "[b]Υπαίθριες πύλες 20 kV[/b]"),
                markup=True,
                size_hint_y=None,
                height=35,
            )
        )
        # Section 3b
        for _r in rows[13:15] if len(rows) > 13 else []:
            add_inspection_row(_r)

        # Chapter 5: Κτίριο χειρισμών & Τ.Α.Σ.
        content_layout.add_widget(
            Label(
                text=S["MESSAGES"].get("INSPECTION_SECTION_4", "[b]Κτίριο χειρισμών & Τ.Α.Σ.[/b]"),
                markup=True,
                size_hint_y=None,
                height=35,
            )
        )
        # Section 4
        for _r in rows[15:18] if len(rows) > 15 else []:
            add_inspection_row(_r)

        # Chapter 6: Αποζευκτες Γραμμών
        content_layout.add_widget(
            Label(
                text=S["MESSAGES"].get("INSPECTION_SECTION_5", "[b]Αποζευκτες Γραμμών[/b]"),
                markup=True,
                size_hint_y=None,
                height=35,
            )
        )
        # Section 5
        if len(rows) > 18:
            add_inspection_row(rows[18])

        # Chapter 7: PC ΧΕΙΡΙΣΜΩΝ
        content_layout.add_widget(
            Label(text=S["MESSAGES"].get("INSPECTION_SECTION_6", "[b]PC ΧΕΙΡΙΣΜΩΝ[/b]"), markup=True, size_hint_y=None, height=35)
        )
        # Section 6
        for _r in rows[19:21] if len(rows) > 19 else []:
            add_inspection_row(_r)

        # Chapter 8: Απόψεις
        content_layout.add_widget(
            Label(text=S["MESSAGES"].get("INSPECTION_SECTION_7", "[b]Απόψεις[/b]"), markup=True, size_hint_y=None, height=35)
        )
        # Final section 7: add an opinions / proposals input row
        opinions_label = S["MESSAGES"].get("INSPECTION_OPINIONS", "Απόψεις - Προτάσεις")
        add_inspection_row(opinions_label)

        scroll.add_widget(content_layout)
        main_layout.add_widget(scroll)

        buttons_layout = BoxLayout(size_hint_y=0.1, spacing=10)

        def save_inspection():
            substation_name = substation_input.text
            substation_id = substation_map.get(substation_name)
            inspection_date = self._parse_inspection_date(
                date_input.text.strip()
            ) or datetime.now().strftime("%Y-%m-%d")
            month_key = self._derive_month_key(inspection_date)

            fields = []
            fields.append({"label": S["MESSAGES"].get("SUBSTATION_LABEL", "Υποσταθμός:"), "value": substation_name})
            fields.append(
                {
                    "label": S["MESSAGES"].get("FORM_NUMBER", "Αρ. Δελτίου:"),
                    "value": self._format_inspection_value(form_number_input.text),
                }
            )
            fields.append(
                {
                    "label": S["MESSAGES"].get("REGION_LABEL", "Περιοχή:"),
                    "value": self._format_inspection_value(region_input.text),
                }
            )
            fields.append(
                {
                    "label": S["MESSAGES"].get("INSPECTOR_LABEL", "Ονομ. Επιθεωρητή:"),
                    "value": self._format_inspection_value(inspector_spinner.text),
                }
            )
            fields.append(
                {
                    "label": S["MESSAGES"].get("MONTH_LABEL", "Μήνας:"),
                    "value": self._format_inspection_value(month_input.text),
                }
            )
            fields.append(
                {
                    "label": S["MESSAGES"].get("DAY_LABEL", "Ημέρα:"),
                    "value": self._format_inspection_value(day_input.text),
                }
            )
            fields.append(
                {
                    "label": S["MESSAGES"].get("YEAR_LABEL", "Έτος:"),
                    "value": self._format_inspection_value(year_input.text),
                }
            )
            fields.append(
                {
                    "label": S["MESSAGES"].get("DATE_LABEL", "Ημερομηνία:"),
                    "value": self._format_inspection_value(inspection_date),
                }
            )
            for label, input_widget in fields_inputs:
                fields.append(
                    {
                        "label": label,
                        "value": self._format_inspection_value(input_widget.text),
                    }
                )

            data_json = json.dumps({"fields": fields}, ensure_ascii=False)
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

            c.execute(
                """
                INSERT INTO inspections (
                    substation_id, substation_name, inspection_date,
                    month_key, data_json, source_file, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    substation_id,
                    substation_name,
                    inspection_date,
                    month_key,
                    data_json,
                    "manual-entry",
                    created_at,
                ),
            )
            self.conn.commit()
            popup.dismiss()
            if parent_popup:
                show_message_popup(
                    S["TITLES"]["SUCCESS"],
                    S["MESSAGES"]["INSPECTION_SAVED"],
                    callback=lambda: self.show_substation_inspection_history(
                        substation_id, substation_name
                    ),
                )
            else:
                show_message_popup(
                    S["TITLES"]["SUCCESS"],
                    S["MESSAGES"]["INSPECTION_SAVED"],
                    callback=lambda: self.show_inspection_history(None),
                )

        save_btn = Button(text=S["BUTTONS"]["SAVE"])
        save_btn.bind(on_press=lambda x: save_inspection())
        buttons_layout.add_widget(save_btn)

        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
        cancel_btn.bind(on_press=popup.dismiss)
        buttons_layout.add_widget(cancel_btn)

        main_layout.add_widget(buttons_layout)
        popup.content = main_layout
        popup.open()

    def _detect_inspection_column(self, columns, keywords):
        from inspections import _detect_inspection_column as _f
        return _f(columns, keywords)

    def _format_inspection_value(self, value):
        from inspections import _format_inspection_value as _f
        return _f(value)

    def _parse_inspection_date(self, value):
        from inspections import _parse_inspection_date as _f
        return _f(value)

    def _derive_month_key(self, date_str):
        from inspections import _derive_month_key as _f
        return _f(date_str)

    def import_inspections_from_file(self, file_path):
        from inspections import import_inspections_from_file as _f
        return _f(self, file_path)

    def show_inspection_history(self, instance=None):
        try:
            from inspections import handle_inspection_history as _f
            return _f(self, instance)
        except Exception as e:
            try:
                from popups import show_message_popup
                show_message_popup(S["TITLES"].get("ERROR", "Σφάλμα"), f"Inspection history failed: {str(e)}")
            except Exception:
                pass
            return None

    def _show_inspection_history(self, instance=None):
        """Show a grouped, searchable, paginated inspection history popup.

        UI features:
        - Substation filter (dropdown: All + individual substations)
        - Text search across substation name and date
        - Pagination with page size control
        """
        try:
            # Prefer module-level widget classes (imported at module top) to avoid
            # creating local names via inner imports which can remain unassigned
            # if the inner import fails at runtime. Use the globals() fallback.
            Popup = globals().get('Popup')
            BoxLayout = globals().get('BoxLayout')
            ScrollView = globals().get('ScrollView')
            GridLayout = globals().get('GridLayout')
            Button = globals().get('Button')
            ToggleButton = globals().get('ToggleButton') or Button
            Label = globals().get('Label')
            TextInput = globals().get('TextInput')
            Spinner = globals().get('Spinner')

            # Fetch distinct substations for filter
            c = self.conn.cursor()
            c.execute("SELECT DISTINCT substation_id, substation_name FROM inspections ORDER BY substation_name")
            subs = c.fetchall()

            # Build base query (we will apply filters later)
            def _query_inspections(sub_id=None, search=None, limit=30, offset=0):
                params = []
                q = "SELECT id, substation_id, substation_name, inspection_date FROM inspections"
                where = []
                if sub_id:
                    where.append("substation_id=?")
                    params.append(sub_id)
                if search:
                    where.append("(substation_name LIKE ? OR inspection_date LIKE ?)")
                    params.extend([f"%{search}%", f"%{search}%"])
                if where:
                    q += " WHERE " + " AND ".join(where)
                q += " ORDER BY inspection_date DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])
                c.execute(q, tuple(params))
                return c.fetchall()

            def _count_inspections(sub_id=None, search=None):
                params = []
                q = "SELECT COUNT(*) FROM inspections"
                where = []
                if sub_id:
                    where.append("substation_id=?")
                    params.append(sub_id)
                if search:
                    where.append("(substation_name LIKE ? OR inspection_date LIKE ?)")
                    params.extend([f"%{search}%", f"%{search}%"])
                if where:
                    q += " WHERE " + " AND ".join(where)
                c.execute(q, tuple(params))
                r = c.fetchone()
                return r[0] if r else 0

            popup = Popup(title=S["TITLES"].get("INSPECTION_HISTORY", "Ιστορικό Επιθεώρησης"), size_hint=(0.95, 0.9))
            main = BoxLayout(orientation="vertical", spacing=8, padding=8)

            # Controls: substation spinner, search box, page size, sort, lazy/load-more
            ctrl_row = BoxLayout(size_hint_y=None, height=40, spacing=8)
            ALL_SUBS = S["MESSAGES"].get("ALL_SUBSTATIONS_LABEL", "Όλοι οι Υ/Σ")
            options = [ALL_SUBS] + [s[1] or "-" for s in subs]
            sub_spinner = Spinner(text=options[0], values=options, size_hint_x=0.34)
            # single-line search input so Enter does not insert a newline
            search_input = TextInput(hint_text=S["MESSAGES"].get("SEARCH_HINT", "Αναζήτηση (όνομα/ημερομηνία)"), size_hint_x=0.30, multiline=False)
            # Sort options: explicit text avoids glyph/arrow corruption in some fonts
            sort_opts = S["MESSAGES"].get("SORT_OPTIONS", ["Ημερομηνία (φθίνουσα)", "Ημερομηνία (αύξουσα)", "Υποσταθμός A-Ω"])
            sort_spinner = Spinner(text=sort_opts[0], values=tuple(sort_opts), size_hint_x=0.16)
            # Page-size control with a small header so users understand purpose
            page_label_header = Label(text=S["MESSAGES"].get("PAGE_SIZE_LABEL", 'Αντικείμενα/σελίδα'), size_hint_x=0.08)
            page_size_spinner = Spinner(text=S["MESSAGES"].get("PAGE_SIZE_OPTIONS", ['10','20','30','50'])[2], values=tuple(S["MESSAGES"].get("PAGE_SIZE_OPTIONS", ['10','20','30','50'])), size_hint_x=0.08)
            ctrl_row.add_widget(sub_spinner)
            ctrl_row.add_widget(search_input)
            ctrl_row.add_widget(sort_spinner)
            ctrl_row.add_widget(page_label_header)
            ctrl_row.add_widget(page_size_spinner)
            main.add_widget(ctrl_row)

            # Hidden hint area that appears when a simple search returns
            # no results. Use a horizontal BoxLayout with matching column
            # size_hint_x proportions so the suggestion aligns exactly
            # under the search input (slot index 1).
            content_hint_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=0)
            main.add_widget(content_hint_box)

            # Listing area
            scroll = ScrollView()
            list_grid = GridLayout(cols=1, spacing=6, size_hint_y=None, padding=4)
            list_grid.bind(minimum_height=list_grid.setter("height"))
            scroll.add_widget(list_grid)
            main.add_widget(scroll)

            # Pagination / load-more controls
            pager = BoxLayout(size_hint_y=None, height=40, spacing=8)
            prev_btn = Button(text=S["MESSAGES"].get("PREVIOUS", "Προηγούμενη"))
            next_btn = Button(text=S["MESSAGES"].get("NEXT", "Επόμενη"))
            load_more_btn = Button(text=S["MESSAGES"].get("LOAD_MORE", "Φόρτωση περισσότερων"))
            page_label = Label(text=S["MESSAGES"].get("PAGE_LABEL_TEMPLATE", "Σελίδα {page}").format(page=1), size_hint_x=0.4)
            pager.add_widget(prev_btn)
            pager.add_widget(page_label)
            pager.add_widget(next_btn)
            pager.add_widget(load_more_btn)
            main.add_widget(pager)

            # Close button
            close = Button(text=S["BUTTONS"].get("CLOSE", "Κλείσιμο"), size_hint_y=None, height=40)
            main.add_widget(close)

            popup.content = main

            # state
            state = {"offset": 0, "limit": int(page_size_spinner.text), "page": 1, "order": 'date_desc', 'lazy': False, 'total': None, 'total_cache_key': None}

            def _query_inspections(sub_id=None, search=None, limit=30, offset=0, order_key='date_desc'):
                params = []
                q = "SELECT id, substation_id, substation_name, inspection_date FROM inspections"
                where = []
                if sub_id:
                    where.append("substation_id=?")
                    params.append(sub_id)
                if search:
                    # By default search only substation_name and inspection_date
                    if state.get('content_search'):
                        where.append("(substation_name LIKE ? OR inspection_date LIKE ? OR data_json LIKE ?)")
                        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
                    else:
                        where.append("(substation_name LIKE ? OR inspection_date LIKE ?)")
                        params.extend([f"%{search}%", f"%{search}%"])
                if where:
                    q += " WHERE " + " AND ".join(where)
                if order_key == 'date_asc':
                    q += " ORDER BY inspection_date ASC"
                elif order_key == 'substation_asc':
                    q += " ORDER BY substation_name ASC, inspection_date DESC"
                else:
                    q += " ORDER BY inspection_date DESC"
                q += " LIMIT ? OFFSET ?"
                params.extend([limit, offset])
                c.execute(q, tuple(params))
                return c.fetchall()

            def _count_inspections(sub_id=None, search=None):
                cache_key = (sub_id, search)
                if state.get('total_cache_key') == cache_key and state.get('total') is not None:
                    return state['total']
                params = []
                q = "SELECT COUNT(*) FROM inspections"
                where = []
                if sub_id:
                    where.append("substation_id=?")
                    params.append(sub_id)
                if search:
                    if state.get('content_search'):
                        where.append("(substation_name LIKE ? OR inspection_date LIKE ? OR data_json LIKE ?)")
                        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
                    else:
                        where.append("(substation_name LIKE ? OR inspection_date LIKE ?)")
                        params.extend([f"%{search}%", f"%{search}%"])
                if where:
                    q += " WHERE " + " AND ".join(where)
                c.execute(q, tuple(params))
                r = c.fetchone()
                total = r[0] if r else 0
                state['total'] = total
                state['total_cache_key'] = cache_key
                return total

            def _render():
                selected = sub_spinner.text
                sub_id = None
                if selected != ALL_SUBS:
                    for s in subs:
                        if (s[1] or "-") == selected:
                            sub_id = s[0]
                            break

                search = search_input.text.strip() or None
                offset = state['offset']
                rows = _query_inspections(sub_id=sub_id, search=search, limit=state['limit'], offset=offset, order_key=state.get('order','date_desc'))
                if not state.get('lazy') or offset == 0:
                    list_grid.clear_widgets()

                total = _count_inspections(sub_id=sub_id, search=search)
                if not rows:
                    list_grid.add_widget(Label(text=S["MESSAGES"].get("NO_INSPECTIONS", "Δεν υπάρχουν καταχωρημένες επιθεωρήσεις."), size_hint_y=None, height=40))
                    # Show a hint to allow broader content search only when
                    # the user entered a query and there are no results.
                    try:
                        content_hint_box.clear_widgets()
                        if search:
                            suggestion = 'Αναζήτηση στο περιεχόμενο (αργό)...'
                            # Instead of a button, show a small framed area "hanging" from
                            # the search field. It's clickable (touch) but visually a frame.
                            suggestion_frame = BoxLayout(size_hint_y=None, height=36, padding=6)
                            lbl = Label(text=suggestion, halign='left', valign='middle', bold=True)
                            lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', inst.size))
                            suggestion_frame.add_widget(lbl)

                            # draw background rect to look like a framed suggestion
                            with suggestion_frame.canvas.before:
                                Color(*self.theme.get('popup_bg', (0.97, 0.98, 0.99, 1)))
                                _rect = Rectangle(pos=suggestion_frame.pos, size=suggestion_frame.size)

                            def _update_rect(instance, value):
                                try:
                                    _rect.pos = instance.pos
                                    _rect.size = instance.size
                                except Exception:
                                    pass

                            suggestion_frame.bind(pos=_update_rect, size=_update_rect)

                            def _on_suggestion_touch(inst, touch):
                                if inst.collide_point(*touch.pos):
                                    try:
                                        state['content_search'] = True
                                        state['offset'] = 0
                                        state['page'] = 1
                                        state['total'] = None
                                        _render()
                                        # hide suggestion after activation
                                        content_hint_box.clear_widgets()
                                        content_hint_box.height = 0
                                    except Exception:
                                        pass
                                    return True
                                return False

                            suggestion_frame.bind(on_touch_down=_on_suggestion_touch)

                            # Fill the horizontal slots so the framed widget
                            # sits exactly under the search input. The
                            # proportions match the control row size_hint_x
                            # values: [0.34,0.30,0.16,0.08,0.08,0.14]
                            proportions = [0.34, 0.30, 0.16, 0.08, 0.08, 0.14]
                            content_hint_box.clear_widgets()
                            for idx, sz in enumerate(proportions):
                                if idx == 1:
                                    suggestion_frame.size_hint_x = sz
                                    content_hint_box.add_widget(suggestion_frame)
                                else:
                                    w = Widget()
                                    w.size_hint_x = sz
                                    content_hint_box.add_widget(w)
                            content_hint_box.height = 40
                        else:
                            content_hint_box.height = 0
                    except Exception:
                        pass
                else:
                    # hide hint box when there are results
                    try:
                        content_hint_box.clear_widgets()
                        content_hint_box.height = 0
                    except Exception:
                        pass
                    if selected == ALL_SUBS:
                        grouped = {}
                        for rid, sid, sname, date in rows:
                            grouped.setdefault(sname or "-", []).append((rid, date))
                        for sname, items in grouped.items():
                            # section header for substation
                            list_grid.add_widget(Label(text=f"[b]{sname}[/b]", markup=True, size_hint_y=None, height=30))
                            for rid, date in items:
                                # row: left-aligned inspection label, right-aligned icon buttons
                                row = BoxLayout(size_hint_y=None, height=44)
                                label_text = f"Επιθεώρηση {sname} {date}"
                                lbl = Label(text=label_text, size_hint_x=0.72, halign='left', valign='middle')
                                lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', (inst.width, None)))
                                actions = BoxLayout(size_hint_x=0.28, spacing=6)

                                view_btn = IconOnlyButton(icon_type="eye", icon_color=self.theme.get('text', (0.12,0.12,0.12,1)), size=(44, 36))
                                # Open details on top without dismissing history so scroll position is preserved
                                view_btn.bind(on_press=lambda _btn, i=rid: self.show_inspection_details(i))
                                actions.add_widget(view_btn)

                                edit_btn = IconOnlyButton(icon_type="edit", icon_color=self.theme.get('primary', (0.2,0.6,1,1)), size=(44, 36))
                                def _edit_inspection(i=rid):
                                    try:
                                        c2 = self.conn.cursor()
                                        c2.execute("SELECT data_json FROM inspections WHERE id=?", (i,))
                                        r = c2.fetchone()
                                        if not r:
                                            return
                                        data_json = r[0]
                                        try:
                                            data = json.loads(data_json)
                                            fields = data.get('fields', [])
                                        except Exception:
                                            fields = []
                                        from inspections import \
                                            _show_edit_inspection_popup as \
                                            _editfn
                                        try:
                                            _editfn(self, i, fields)
                                        except Exception:
                                            pass
                                    except Exception:
                                        pass

                                edit_btn.bind(on_press=lambda _btn, i=rid: _edit_inspection(i))
                                actions.add_widget(edit_btn)

                                def _confirm_delete(i=rid, sname_local=sname, date_local=date):
                                    from reports import show_confirm

                                    def _do_delete():
                                        try:
                                            c.execute("DELETE FROM inspections WHERE id=?", (i,))
                                            self.conn.commit()
                                        except Exception:
                                            pass
                                        # refresh listing
                                        state['offset'] = 0
                                        state['page'] = 1
                                        state['total'] = None
                                        _render()

                                    show_confirm(S["MESSAGES"].get("CONFIRM_DELETE_TITLE", "Επιβεβαίωση Διαγραφής"), f"Διαγραφή επιθεώρησης για {sname_local} ({date_local}); είστε σίγουροι;", yes_callback=_do_delete, yes_color=(1,0,0,1), yes_text=S["BUTTONS"].get("YES", "Ναι"), no_text=S["BUTTONS"].get("NO", "Όχι"))

                                delete_btn = IconOnlyButton(icon_type="delete", icon_color=(1, 0, 0, 1), size=(44, 36))
                                delete_btn.bind(on_press=lambda _btn, i=rid: _confirm_delete(i))
                                actions.add_widget(delete_btn)

                                row.add_widget(lbl)
                                row.add_widget(actions)
                                list_grid.add_widget(row)
                    else:
                        for rid, sid, sname, date in rows:
                            row = BoxLayout(size_hint_y=None, height=44)
                            label_text = f"Επιθεώρηση {sname} {date}"
                            lbl = Label(text=label_text, size_hint_x=0.72, halign='left', valign='middle')
                            lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', (inst.width, None)))
                            actions = BoxLayout(size_hint_x=0.28, spacing=6)

                            view_btn = IconOnlyButton(icon_type="eye", icon_color=self.theme.get('text', (0.12,0.12,0.12,1)), size=(44, 36))
                            view_btn.bind(on_press=lambda _btn, i=rid: self.show_inspection_details(i))
                            actions.add_widget(view_btn)

                            edit_btn = IconOnlyButton(icon_type="edit", icon_color=self.theme.get('primary', (0.2,0.6,1,1)), size=(44, 36))
                            def _edit_inspection_local(i=rid):
                                try:
                                    c2 = self.conn.cursor()
                                    c2.execute("SELECT data_json FROM inspections WHERE id=?", (i,))
                                    r = c2.fetchone()
                                    if not r:
                                        return
                                    data_json = r[0]
                                    try:
                                        data = json.loads(data_json)
                                        fields = data.get('fields', [])
                                    except Exception:
                                        fields = []
                                    from inspections import \
                                        _show_edit_inspection_popup as _editfn
                                    try:
                                        _editfn(self, i, fields)
                                    except Exception:
                                        pass
                                except Exception:
                                    pass

                            edit_btn.bind(on_press=lambda _btn, i=rid: _edit_inspection_local(i))
                            actions.add_widget(edit_btn)

                            def _confirm_delete(i=rid, sname_local=sname, date_local=date):
                                from reports import show_confirm

                                def _do_delete():
                                    try:
                                        c.execute("DELETE FROM inspections WHERE id=?", (i,))
                                        self.conn.commit()
                                    except Exception:
                                        pass
                                    state['offset'] = 0
                                    state['page'] = 1
                                    state['total'] = None
                                    _render()

                                show_confirm(S["MESSAGES"].get("CONFIRM_DELETE_TITLE", "Επιβεβαίωση Διαγραφής"), f"Διαγραφή επιθεώρησης για {sname_local} ({date_local}); είστε σίγουροι;", yes_callback=_do_delete, yes_color=(1,0,0,1), yes_text=S["BUTTONS"].get("YES", "Ναι"), no_text=S["BUTTONS"].get("NO", "Όχι"))

                            delete_btn = IconOnlyButton(icon_type="delete", icon_color=(1, 0, 0, 1), size=(44, 36))
                            delete_btn.bind(on_press=lambda _btn, i=rid: _confirm_delete(i))
                            actions.add_widget(delete_btn)

                            row.add_widget(lbl)
                            row.add_widget(actions)
                            list_grid.add_widget(row)

                # update pager state
                page_label.text = f"Σελίδα {state['page']} ({min(offset+1, total)}-{min(offset+len(rows), total)} / {total})"
                if state.get('lazy'):
                    prev_btn.disabled = True
                    next_btn.disabled = True
                    load_more_btn.disabled = (offset + len(rows) >= total)
                else:
                    prev_btn.disabled = (offset == 0)
                    next_btn.disabled = (offset + state['limit'] >= total)

            def _set_page_size(_spinner, _value):
                try:
                    state['limit'] = int(_value)
                    state['offset'] = 0
                    state['page'] = 1
                    state['total'] = None
                    _render()
                except Exception:
                    pass

            def _search_changed(_inst):
                state['offset'] = 0
                state['page'] = 1
                state['total'] = None
                _render()

            def _prev(_):
                if state['offset'] >= state['limit']:
                    state['offset'] -= state['limit']
                    state['page'] -= 1
                    _render()

            def _next(_):
                state['offset'] += state['limit']
                state['page'] += 1
                _render()

            def _load_more(_):
                # append next page
                state['offset'] += state['limit']
                state['page'] += 1
                _render()

            def _on_sort_change(_spinner, text):
                sort_opts = S["MESSAGES"].get("SORT_OPTIONS", ["Ημερομηνία (φθίνουσα)", "Ημερομηνία (αύξουσα)", "Υποσταθμός A-Ω"])
                if text == sort_opts[1]:
                    state['order'] = 'date_asc'
                elif text == sort_opts[2]:
                    state['order'] = 'substation_asc'
                else:
                    state['order'] = 'date_desc'
                state['offset'] = 0
                state['page'] = 1
                _render()

            # bindings
            page_size_spinner.bind(text=_set_page_size)
            search_input.bind(text=lambda inst, val: _search_changed(inst))
            # When Enter is pressed in single-line TextInput, trigger search
            try:
                search_input.bind(on_text_validate=_search_changed)
            except Exception:
                pass
            sub_spinner.bind(text=lambda inst, val: _search_changed(inst))
            prev_btn.bind(on_press=_prev)
            next_btn.bind(on_press=_next)
            load_more_btn.bind(on_press=_load_more)
            sort_spinner.bind(text=_on_sort_change)
            close.bind(on_press=lambda _btn: popup.dismiss())

            # initial render
            _render()
            popup.open()
        except Exception:
            import logging
            logging.exception('_show_inspection_history_failed')
        return None

    def get_available_gates(self, substation_id, is_interconnection=None):
        """Get available gates (ΠΥΛΗ) based on existing transformers in the substation

        Args:
            substation_id: The ID of the substation
            is_interconnection: If True,run the test suite  returns interconnection gates (1-2, 2-3, etc.)
                               If False, returns regular gates (1, 2, 3, etc.)
                               If None (default), returns both regular and interconnection
                               gates when multiple transformers exist so the caller can
                               choose combined gates (e.g., ΠΥΛΗ 1-2).
        """
        c = self.conn.cursor()
        # Get all transformers for this substation, ordered by name
        c.execute(
            """SELECT name FROM elements
                WHERE substation_id=? AND (element_type LIKE '%150/20%' OR element_type LIKE '%Μετασχη%')
                ORDER BY name""",
            (substation_id,),
        )
        transformers = c.fetchall()

        num_gates = len(transformers)

        # Regular gates: ΠΥΛΗ 1, ΠΥΛΗ 2, ...
        gate_prefix = S["MESSAGES"].get("GATE_PREFIX", "ΠΥΛΗ")
        # Regular gates: ΠΥΛΗ 1, ΠΥΛΗ 2, ...
        regular = [f"{gate_prefix} {i + 1}" for i in range(num_gates)]
        # Interconnection gates: ΠΥΛΗ 1-2, ΠΥΛΗ 2-3, ...
        inter = [f"{gate_prefix} {i}-{i + 1}" for i in range(1, num_gates)]

        if is_interconnection is True:
            gates = inter
        elif is_interconnection is False:
            gates = regular
        else:
            # Default: if there are multiple transformers, include both regular and interconnection
            # so users can pick gates that span transformers (e.g., 1-2).
            gates = regular + inter

        # Always include option for unassigned
        return [get_unreg()] + gates

    def show_import_menu(self, instance):
        from imports import show_import_menu as _f
        return _f(self, instance)

    def _show_import_substations_from_menu(self, menu_popup):
        from imports import _show_import_substations_from_menu as _f
        return _f(self, menu_popup)

    def _show_import_elements_from_menu(self, menu_popup):
        from imports import _show_import_elements_from_menu as _f
        return _f(self, menu_popup)

    def _show_import_android_changes_from_menu(self, menu_popup):
        from imports import _show_import_android_changes_from_menu as _f
        return _f(self, menu_popup)

    def show_add_menu(self, instance):
        # Show intermediate menu for adding substation or element
        menu_popup = Popup(
            title=S["MESSAGES"]["ADD_MENU_TITLE"], size_hint=(0.6, 0.4)
        )
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        self._add_logo_to_layout(layout, height=70)

        layout.add_widget(
            Label(text=S["MESSAGES"]["CHOOSE_WHAT_TO_ADD"], size_hint_y=0.3)
        )

        # Add substation button
        add_substation_btn = Button(text=S["MESSAGES"]["ADD_SUBSTATION_BTN"], size_hint_y=0.3)
        add_substation_btn.bind(
            on_press=lambda x: self._show_add_substation_from_menu(menu_popup)
        )
        layout.add_widget(add_substation_btn)

        # Add element button
        add_element_btn = Button(text=S["MESSAGES"]["ADD_ELEMENT_BTN"], size_hint_y=0.3)
        add_element_btn.bind(
            on_press=lambda x: self._show_add_element_from_menu(menu_popup)
        )
        layout.add_widget(add_element_btn)

        # Cancel button
        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"], size_hint_y=0.2)
        cancel_btn.bind(on_press=menu_popup.dismiss)
        layout.add_widget(cancel_btn)

        menu_popup.content = layout
        menu_popup.open()

    def _show_add_substation_from_menu(self, menu_popup):
        menu_popup.dismiss()
        self.show_add_substation_popup(None)

    def _show_add_element_from_menu(self, menu_popup):
        menu_popup.dismiss()
        self.show_add_element_popup(None)

    def show_add_substation_popup(self, instance):
        # Create popup
        popup = Popup(title=S["MESSAGES"]["ADD_SUBSTATION_BTN"], size_hint=(0.8, 0.5))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        # Name input
        name_input = TextInput(
            hint_text=S["MESSAGES"].get("SUBSTATION_NAME_HINT", "Όνομα Υποσταθμού"), size_hint_y=0.25, multiline=False
        )
        layout.add_widget(Label(text=S["MESSAGES"].get("SUBSTATION_NAME_LABEL", "Όνομα Υποσταθμού:"), size_hint_y=0.15))
        layout.add_widget(name_input)

        # Division spinner
        division_spinner = Spinner(text=S["MESSAGES"].get("DIVISION_DEFAULT", "ΤΜΘ"), values=[S["MESSAGES"].get("DIVISION_DEFAULT", "ΤΜΘ")], size_hint_y=0.25)
        layout.add_widget(Label(text=S["MESSAGES"].get("DIVISION_LABEL", "Τομέας:"), size_hint_y=0.15))
        layout.add_widget(division_spinner)

        # Buttons layout
        buttons_layout = BoxLayout(size_hint_y=0.3, spacing=10)

        def add_substation():
            if not name_input.text:
                show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["ENTER_SUBSTATION_NAME"])
                return

            c = self.conn.cursor()
            c.execute(
                "INSERT INTO substations (name, location, adoption_date, division) VALUES (?, ?, ?, ?)",
                (name_input.text, "", "", division_spinner.text),
            )
            self.conn.commit()
            popup.dismiss()
            show_message_popup(
                S["TITLES"]["SUCCESS"],
                S["MESSAGES"]["SUBSTATION_ADDED"],
                callback=lambda: self.show_records(None),
            )

        add_btn = Button(text=S["BUTTONS"]["ADD"])
        add_btn.bind(on_press=lambda x: add_substation())
        buttons_layout.add_widget(add_btn)

        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
        cancel_btn.bind(on_press=popup.dismiss)
        buttons_layout.add_widget(cancel_btn)

        layout.add_widget(buttons_layout)
        popup.content = layout
        popup.open()

    def show_add_substation_popup_from_db_view(self, parent_popup):
        """Add substation from within the database view, and refresh the view after"""
        # Create popup
        popup = Popup(title=S["MESSAGES"]["ADD_SUBSTATION_BTN"], size_hint=(0.8, 0.5))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        # Name input
        name_input = TextInput(
            hint_text=S["MESSAGES"].get("SUBSTATION_NAME_HINT", "Όνομα Υποσταθμού"), size_hint_y=0.25, multiline=False
        )
        layout.add_widget(Label(text=S["MESSAGES"].get("SUBSTATION_NAME_LABEL", "Όνομα Υποσταθμού:"), size_hint_y=0.15))
        layout.add_widget(name_input)

        # Division spinner
        division_spinner = Spinner(text=S["MESSAGES"].get("DIVISION_DEFAULT", "ΤΜΘ"), values=[S["MESSAGES"].get("DIVISION_DEFAULT", "ΤΜΘ")], size_hint_y=0.25)
        layout.add_widget(Label(text=S["MESSAGES"].get("DIVISION_LABEL", "Τομέας:"), size_hint_y=0.15))
        layout.add_widget(division_spinner)

        # Buttons layout
        buttons_layout = BoxLayout(size_hint_y=0.3, spacing=10)

        def add_substation():
            if not name_input.text:
                show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"].get("ENTER_SUBSTATION_NAME", "Παρακαλώ εισάγετε όνομα υποσταθμού!"))
                return

            c = self.conn.cursor()
            c.execute(
                "INSERT INTO substations (name, location, adoption_date, division) VALUES (?, ?, ?, ?)",
                (name_input.text, "", "", division_spinner.text),
            )
            self.conn.commit()
            popup.dismiss()
            parent_popup.dismiss()
            show_message_popup(
                S["TITLES"].get("SUCCESS", "Επιτυχία"),
                S["MESSAGES"].get("SUBSTATION_ADDED", "Υποσταθμός προστέθηκε!"),
                callback=lambda: self.show_records(None),
            )

        add_btn = Button(text=S["BUTTONS"]["ADD"])
        add_btn.bind(on_press=lambda x: add_substation())
        buttons_layout.add_widget(add_btn)

        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
        cancel_btn.bind(on_press=popup.dismiss)
        buttons_layout.add_widget(cancel_btn)

        layout.add_widget(buttons_layout)
        popup.content = layout
        popup.open()

    def show_records(self, instance):
        # Show intermediate selection dialog
        c = self.conn.cursor()
        c.execute("SELECT id, name FROM substations ORDER BY name")
        all_substations = c.fetchall()

        if not all_substations:
            # Show a popup offering to add a new substation when DB is empty
            empty_popup = Popup(title=S["MESSAGES"].get("NO_SUBSTATIONS", "Δεν βρέθηκαν Υποσταθμοί"), size_hint=(0.6, 0.4))
            v = BoxLayout(orientation="vertical", padding=10, spacing=10)
            v.add_widget(Label(text=S["MESSAGES"]["NO_SUBSTATIONS"]))
            btn_row = BoxLayout(size_hint_y=None, height=40, spacing=10)
            add_btn = Button(text=S["BUTTONS"]["ADD"] + " Υποσταθμού")
            add_btn.bind(on_press=lambda _x: (empty_popup.dismiss(), self.show_add_substation_popup(None)))
            cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
            cancel_btn.bind(on_press=empty_popup.dismiss)
            btn_row.add_widget(Widget())
            btn_row.add_widget(add_btn)
            btn_row.add_widget(cancel_btn)
            btn_row.add_widget(Widget())
            v.add_widget(btn_row)
            empty_popup.content = v
            empty_popup.open()
            return

        # Create selection popup
        selection_popup = Popup(title=S["MESSAGES"].get("VIEW_SELECTION_TITLE", "Επιλογή Προβολής"), size_hint=(0.6, 0.4))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        self._add_logo_to_layout(layout, height=70)

        prompt_field = TextInput(
            text=S["MESSAGES"].get("VIEW_PROMPT", "Επιλέξτε τι θέλετε να δείτε:"),
            readonly=True,
            multiline=False,
            size_hint_y=None,
            height=35,
            background_normal="",
            background_active="",
            background_color=(0, 0, 0, 0),
            foreground_color=self.theme.get("text", (0.12, 0.12, 0.12, 1)),
            selection_color=(0.3, 0.5, 1, 0.3),
            cursor_blink=False,
            cursor_width=0,
            write_tab=False,
            halign="center",
            is_focusable=True,
            allow_copy=True,
            padding=(5, 5),
        )
        layout.add_widget(prompt_field)

        # "Show All" button
        show_all_btn = Button(text=S["MESSAGES"].get("SHOW_ALL_SUBSTATIONS", "Προβολή Όλων των Υποσταθμών"), size_hint_y=0.35)
        show_all_btn.bind(
            on_press=lambda x: self._show_all_substations(selection_popup)
        )
        layout.add_widget(show_all_btn)

        # "Select Specific Substation" button
        select_specific_btn = Button(text=S["MESSAGES"].get("SELECT_SUBSTATION_BTN", "Επιλογή Υποσταθμού"), size_hint_y=0.35)
        select_specific_btn.bind(
            on_press=lambda x: self._show_substation_selection_window(
                selection_popup, all_substations
            )
        )
        layout.add_widget(select_specific_btn)

        # Cancel button
        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"], size_hint_y=0.2)
        cancel_btn.bind(on_press=selection_popup.dismiss)
        layout.add_widget(cancel_btn)

        selection_popup.content = layout
        selection_popup.open()

    def _show_substation_selection_window(self, parent_popup, all_substations):
        """Show a scrollable window with a 5x14 matrix of substation buttons"""
        parent_popup.dismiss()

        # Create selection popup
        selection_popup = Popup(title=S["MESSAGES"].get("SELECT_SUBSTATION_BTN", "Επιλογή Υποσταθμού"), size_hint=(0.9, 0.85))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        # Create scrollable area
        scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
        grid = GridLayout(cols=5, spacing=5, size_hint_y=None, padding=10)
        grid.bind(minimum_height=grid.setter("height"))

        # Create 5x14 matrix (70 positions total)
        total_positions = 70

        # Add buttons for registered substations and empty boxes for remaining positions
        for i in range(total_positions):
            if i < len(all_substations):
                sub_id, sub_name = all_substations[i]
                sub_btn = Button(text=sub_name, size_hint_y=None, height=50)
                sub_btn.bind(
                    on_press=lambda x, name=sub_name, popup=selection_popup: (
                        self._show_specific_substation_from_window(name, popup)
                    )
                )
                grid.add_widget(sub_btn)
            else:
                # Empty box for unregistered positions
                empty_btn = Button(
                    text="",
                    size_hint_y=None,
                    height=50,
                    disabled=True,
                    background_color=(0.3, 0.3, 0.3, 0.5),
                )
                grid.add_widget(empty_btn)

        scroll.add_widget(grid)
        layout.add_widget(scroll)

        # Cancel button
        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"], size_hint_y=0.08)
        cancel_btn.bind(on_press=selection_popup.dismiss)
        layout.add_widget(cancel_btn)

        selection_popup.content = layout
        selection_popup.open()

    def _show_substation_selection_window_with_callback(
        self, parent_popup, all_substations, on_select, title="Επιλογή Υποσταθμού"
    ):
        """Show a selection window and call on_select with the chosen substation name."""
        selection_popup = Popup(title=title, size_hint=(0.9, 0.85))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
        grid = GridLayout(cols=5, spacing=5, size_hint_y=None, padding=10)
        grid.bind(minimum_height=grid.setter("height"))

        total_positions = 70

        def handle_select(sub_name):
            selection_popup.dismiss()
            if parent_popup:
                parent_popup.open()
            if on_select:
                on_select(sub_name)

        for i in range(total_positions):
            if i < len(all_substations):
                _sub_id, sub_name = all_substations[i]
                sub_btn = Button(text=sub_name, size_hint_y=None, height=50)
                sub_btn.bind(on_press=lambda x, name=sub_name: handle_select(name))
                grid.add_widget(sub_btn)
            else:
                empty_btn = Button(
                    text="",
                    size_hint_y=None,
                    height=50,
                    disabled=True,
                    background_color=(0.3, 0.3, 0.3, 0.5),
                )
                grid.add_widget(empty_btn)

        scroll.add_widget(grid)
        layout.add_widget(scroll)

        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"], size_hint_y=0.08)
        cancel_btn.bind(on_press=selection_popup.dismiss)
        layout.add_widget(cancel_btn)

        if parent_popup:
            parent_popup.dismiss()

        selection_popup.content = layout
        selection_popup.open()

    def _show_all_substations(self, selection_popup):
        selection_popup.dismiss()
        self._run_with_loading(
            lambda: self._display_substations(None),
            S["MESSAGES"].get("LOADING_SUBSTATIONS", "Φόρτωση υποσταθμών..."),
        )

    def _show_specific_substation_from_window(self, substation_name, selection_popup):
        selection_popup.dismiss()
        self._display_substations(substation_name)

    def _show_loading_popup(self, message=None):
        """Show a simple non-blocking loading popup and return it."""
        loading_popup = Popup(
            title=S["MESSAGES"].get("LOADING", "Φόρτωση..."),
            size_hint=(0.42, 0.22),
            auto_dismiss=False,
        )
        layout = BoxLayout(orientation="vertical", padding=12, spacing=10)
        layout.add_widget(
            Label(
                text=message
                or S["MESSAGES"].get("LOADING", "Φόρτωση..."),
                halign="center",
                valign="middle",
            )
        )
        loading_popup.content = layout
        loading_popup.open()
        return loading_popup

    def _run_with_loading(self, work_fn, message=None):
        """Render a loading popup first, then run work_fn on the next UI frame."""
        loading_popup = self._show_loading_popup(message)

        def _run(_dt):
            try:
                work_fn()
            finally:
                try:
                    loading_popup.dismiss()
                except Exception:
                    pass

        Clock.schedule_once(_run, 0)

    def _show_brief_info_toast(self, message, duration=2.4, action_text=None, action_callback=None):
        """Show a lightweight auto-dismiss info toast with optional action button."""
        try:
            toast = Popup(
                title=S["TITLES"].get("INFO", "Info"),
                size_hint=(0.62, 0.2),
                auto_dismiss=True,
            )
            layout = BoxLayout(orientation="vertical", padding=8, spacing=6)
            layout.add_widget(
                Label(
                    text=message,
                    halign="center",
                    valign="middle",
                )
            )

            if action_text and action_callback:
                action_row = BoxLayout(orientation="horizontal", size_hint_y=None, height=36, spacing=6)
                action_row.add_widget(Widget())
                action_btn = Button(text=action_text, size_hint_x=0.5)

                def _on_action(_btn):
                    try:
                        toast.dismiss()
                    except Exception:
                        pass
                    Clock.schedule_once(lambda _dt: action_callback(), 0)

                action_btn.bind(on_press=_on_action)
                action_row.add_widget(action_btn)
                action_row.add_widget(Widget())
                layout.add_widget(action_row)

            toast.content = layout
            toast.open()
            Clock.schedule_once(lambda _dt: toast.dismiss(), max(0.8, float(duration)))
        except Exception:
            pass

    def _show_startup_progress_popup(self):
        """Create and return a progress popup for startup operations."""
        from kivy.uix.progressbar import ProgressBar
        
        progress_popup = Popup(
            title=S["MESSAGES"].get("STARTUP_PROGRESS_TITLE", "Initialization in Progress"),
            size_hint=(0.65, 0.35),
            auto_dismiss=False,
        )
        layout = BoxLayout(orientation="vertical", padding=15, spacing=12)
        
        # Operation label
        operation_label = Label(
            text=S["MESSAGES"].get("STARTUP_INITIALIZING", "Initializing..."),
            size_hint_y=None,
            height=30,
        )
        layout.add_widget(operation_label)
        
        # Substation label
        substation_label = Label(
            text="",
            size_hint_y=None,
            height=25,
            font_size="12sp",
        )
        layout.add_widget(substation_label)
        
        # Progress bar
        progress_bar = ProgressBar(
            value=0,
            max=100,
            size_hint_y=None,
            height=30,
        )
        layout.add_widget(progress_bar)
        
        # Progress text
        progress_text = Label(
            text="0%",
            size_hint_y=None,
            height=25,
            font_size="12sp",
        )
        layout.add_widget(progress_text)
        
        progress_popup.content = layout
        return {
            "popup": progress_popup,
            "operation_label": operation_label,
            "substation_label": substation_label,
            "progress_bar": progress_bar,
            "progress_text": progress_text,
        }

    def _update_startup_progress(self, progress_ui, operation, substation, current, total):
        """Update startup progress popup with current status."""
        try:
            def _apply_update(_dt):
                try:
                    percent = int((current / total * 100) if total > 0 else 0)
                    progress_ui["operation_label"].text = operation
                    progress_ui["substation_label"].text = f"{substation}" if substation else ""
                    progress_ui["progress_bar"].value = percent
                    progress_ui["progress_text"].text = f"{percent}%"
                except Exception:
                    pass

            Clock.schedule_once(_apply_update, 0)
        except Exception:
            pass

    def _get_startup_sync_state_path(self):
        """Return path for persisted startup sync probe state."""
        try:
            db_dir = os.path.dirname(os.path.abspath(self.db_path))
        except Exception:
            db_dir = os.path.dirname(os.path.abspath(DB_PATH))
        return os.path.join(db_dir, ".startup_sync_state.json")

    def _load_startup_sync_state(self):
        """Load startup sync probe state from disk."""
        path = self._get_startup_sync_state_path()
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_startup_sync_state(self, state):
        """Persist startup sync probe state atomically."""
        path = self._get_startup_sync_state_path()
        tmp = f"{path}.tmp"
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(state, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass

    def _scan_sync_payload_dir(self, dir_path):
        """Return file count and latest mtime for .json/.jsonl files in a sync folder."""
        count = 0
        latest_mtime = 0.0
        try:
            for name in os.listdir(dir_path):
                fp = os.path.join(dir_path, name)
                if not os.path.isfile(fp):
                    continue
                if not name.lower().endswith((".json", ".jsonl")):
                    continue
                count += 1
                try:
                    mt = os.path.getmtime(fp)
                    if mt > latest_mtime:
                        latest_mtime = mt
                except Exception:
                    pass
        except Exception:
            pass
        return {
            "count": int(count),
            "latest_mtime": round(float(latest_mtime), 3),
        }

    def _compute_startup_sync_probe(self, sync_root):
        """Compute a lightweight signature of shared sync state and local DB state."""
        pending_dir = os.path.join(sync_root, "inbox", "pending")
        accepted_dir = os.path.join(sync_root, "inbox", "processed", "accepted")
        tracker_path = os.path.join(sync_root, "logs", ".processed_files.json")
        shared_root = resolve_shared_root(self.db_path)

        try:
            db_mtime = round(float(os.path.getmtime(self.db_path)), 3)
        except Exception:
            db_mtime = 0.0

        try:
            tracker_mtime = round(float(os.path.getmtime(tracker_path)), 3)
        except Exception:
            tracker_mtime = 0.0

        shared_exists = os.path.isdir(shared_root)
        try:
            shared_mtime = round(float(os.path.getmtime(shared_root)), 3) if shared_exists else 0.0
        except Exception:
            shared_mtime = 0.0

        shared_substation_dirs = 0
        if shared_exists:
            try:
                shared_substation_dirs = sum(
                    1 for name in os.listdir(shared_root)
                    if os.path.isdir(os.path.join(shared_root, name)) and not name.startswith("_")
                )
            except Exception:
                shared_substation_dirs = 0

        return {
            "version": 1,
            "db_path": os.path.abspath(self.db_path),
            "sync_root": os.path.abspath(sync_root),
            "shared_root": os.path.abspath(shared_root),
            "shared_root_exists": bool(shared_exists),
            "shared_root_mtime": shared_mtime,
            "shared_substation_dirs": int(shared_substation_dirs),
            "db_mtime": db_mtime,
            "pending": self._scan_sync_payload_dir(pending_dir),
            "accepted": self._scan_sync_payload_dir(accepted_dir),
            "tracker_mtime": tracker_mtime,
        }

    def _build_startup_probe_summary(self, probe: dict | None) -> str:
        """Build a compact summary shown in the startup sync prompt."""
        if not isinstance(probe, dict):
            return ""

        pending = int(((probe.get("pending") or {}).get("count", 0) or 0))
        accepted = int(((probe.get("accepted") or {}).get("count", 0) or 0))
        shared_dirs = int(probe.get("shared_substation_dirs", 0) or 0)
        shared_exists = bool(probe.get("shared_root_exists", True))

        lines = [S["MESSAGES"].get("STARTUP_SYNC_SUMMARY_TITLE", "Σύνοψη διαφοράς:")]
        lines.append(f"• Εκκρεμή αρχεία εισαγωγής: {pending}")
        lines.append(f"• Αρχεία στο processed/accepted: {accepted}")
        lines.append(f"• Υποσταθμοί στον κοινόχρηστο φάκελο: {shared_dirs}")
        if not shared_exists:
            lines.append("• Προσοχή: ο κοινόχρηστος φάκελος δεν βρέθηκε.")
        return "\n".join(lines)

    def _show_startup_sync_prompt_popup(self, on_sync=None, on_skip=None, summary_text=""):
        """Prompt the user to start full startup sync only when probe detects differences."""
        popup = Popup(
            title=S["MESSAGES"].get("STARTUP_SYNC_PROMPT_TITLE", "Synchronization Detected"),
            size_hint=(0.78, 0.42),
            auto_dismiss=False,
        )

        layout = BoxLayout(orientation="vertical", padding=12, spacing=10)
        msg = S["MESSAGES"].get(
            "STARTUP_SYNC_PROMPT_MESSAGE",
            "Detected differences in the shared sync folder since your last startup.\n"
            "Do you want to run synchronization now?",
        )
        layout.add_widget(Label(text=msg, halign="center", valign="middle"))

        if summary_text:
            summary_label = Label(text=summary_text, halign="left", valign="top", markup=False)
            summary_label.bind(
                width=lambda inst, val: setattr(inst, "text_size", (val, None)),
                texture_size=lambda inst, val: setattr(inst, "height", val[1] + 8),
            )
            summary_label.size_hint_y = None
            layout.add_widget(summary_label)

        buttons = BoxLayout(orientation="horizontal", size_hint_y=None, height=46, spacing=8)
        sync_btn = Button(text=S["BUTTONS"].get("SYNC_NOW", "Sync now"))
        skip_btn = Button(text=S["BUTTONS"].get("SKIP_FOR_NOW", "Skip for now"))
        buttons.add_widget(sync_btn)
        buttons.add_widget(skip_btn)
        layout.add_widget(buttons)
        popup.content = layout

        def _do_sync(_btn):
            try:
                popup.dismiss()
            except Exception:
                pass
            if on_sync:
                Clock.schedule_once(lambda dt: on_sync(), 0)

        def _do_skip(_btn):
            try:
                popup.dismiss()
            except Exception:
                pass
            if on_skip:
                Clock.schedule_once(lambda dt: on_skip(), 0)

        sync_btn.bind(on_press=_do_sync)
        skip_btn.bind(on_press=_do_skip)
        popup.open()

    def _display_substations(
        self,
        filter_name=None,
        reuse_popup=None,
        element_type_filter=None,
        gate_filter=None,
        prev_scroll_y=None,
    ):
        c = self.conn.cursor()
        if filter_name:
            c.execute(
                "SELECT id, name, location, adoption_date, division, monogram_pdf, is_thessaloniki FROM substations WHERE name=?",
                (filter_name,),
            )
            title = f"Υποσταθμός: {filter_name}"
        else:
            c.execute(
                "SELECT id, name, location, adoption_date, division, monogram_pdf, is_thessaloniki FROM substations ORDER BY name"
            )
            title = "Εγγραφές Υποσταθμών"

        substations = c.fetchall()
        show_elements = filter_name is not None

        sub_ids = [row[0] for row in substations]
        elem_count_map = {}
        gate_count_map = {}
        capacitor_count_map = {}
        maint_count_map = {}
        inspection_count_map = {}
        dga_count_map = {}
        last_maint_map = {}
        inactive_count_map = {}

        if sub_ids:
            placeholders = ",".join(["?"] * len(sub_ids))

            c.execute(
                f"SELECT substation_id, COUNT(*) FROM elements WHERE substation_id IN ({placeholders}) GROUP BY substation_id",
                sub_ids,
            )
            elem_count_map = {sid: cnt for sid, cnt in c.fetchall()}

            c.execute(
                f"SELECT substation_id, COUNT(DISTINCT gate) FROM elements WHERE substation_id IN ({placeholders}) "
                "AND gate IS NOT NULL AND gate != '' AND gate NOT LIKE '%-%' GROUP BY substation_id",
                sub_ids,
            )
            gate_count_map = {sid: cnt for sid, cnt in c.fetchall()}

            c.execute(
                f"SELECT substation_id, COUNT(*) FROM elements WHERE substation_id IN ({placeholders}) "
                "AND element_type=? AND is_main_switch=3 GROUP BY substation_id",
                sub_ids + [self.ELEM_BREAKER_MT],
            )
            capacitor_count_map = {sid: cnt for sid, cnt in c.fetchall()}

            c.execute(
                f"SELECT substation_id, COUNT(*) FROM maintenance WHERE substation_id IN ({placeholders}) GROUP BY substation_id",
                sub_ids,
            )
            maint_count_map = {sid: cnt for sid, cnt in c.fetchall()}

            c.execute(
                f"SELECT substation_id, COUNT(*) FROM inspections WHERE substation_id IN ({placeholders}) GROUP BY substation_id",
                sub_ids,
            )
            inspection_count_map = {sid: cnt for sid, cnt in c.fetchall()}

            # Count DGA measurements for each substation (grouped by maintenance type)
            c.execute(
                f"SELECT substation_id, COUNT(DISTINCT m.id) FROM maintenance m WHERE substation_id IN ({placeholders}) AND m.maintenance_type=? GROUP BY substation_id",
                sub_ids + [S["MESSAGES"].get("DGA_LABEL", "Φυσικοχημικές/Αεριοχρωματογραφία")],
            )
            dga_count_map = {sid: cnt for sid, cnt in c.fetchall()}

            c.execute(
                f"SELECT substation_id, MAX(date_time) FROM maintenance WHERE substation_id IN ({placeholders}) GROUP BY substation_id",
                sub_ids,
            )
            last_maint_map = {sid: dt for sid, dt in c.fetchall()}

            c.execute(
                f"SELECT substation_id, COUNT(*) FROM elements WHERE substation_id IN ({placeholders}) "
                "AND operating_status='Ανενεργή' GROUP BY substation_id",
                sub_ids,
            )
            inactive_count_map = {sid: cnt for sid, cnt in c.fetchall()}

        # Create popup window (reuse if requested)
        popup = (
            reuse_popup if reuse_popup else Popup(title=title, size_hint=(0.95, 0.9))
        )
        popup.title = title

        # Create main layout
        main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        # Create scrollable grid for records
        scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
        grid = GridLayout(cols=1, spacing=5, size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))

        # If a previous scroll position was provided, restore it after layout
        if prev_scroll_y is not None:
            try:
                # schedule after frame to ensure widgets have size
                Clock.schedule_once(lambda dt: setattr(scroll, "scroll_y", float(prev_scroll_y)), 0)
            except Exception:
                pass

        if substations:
            for (
                sub_id,
                sub_name,
                location,
                adoption_date,
                division,
                monogram_pdf,
                is_thessaloniki,
            ) in substations:
                # Substation title in bigger letters with optional Thessaloniki tag
                sub_title_layout = BoxLayout(size_hint_y=None, height=45, spacing=8)
                substation_title = Label(
                    text=f"[b][size=22]{sub_name}[/size][/b]",
                    size_hint_x=0.85,
                    markup=True,
                )
                sub_title_layout.add_widget(substation_title)

                is_th = bool(is_thessaloniki)

                if is_th:
                    th_tag = Button(
                        text=S["MESSAGES"].get("SUBSTATION_IS_THESSALONIKI", "Θεσσαλονίκη"),
                        size_hint_x=0.15,
                        background_color=(1, 0, 0, 1),
                        color=(1, 1, 1, 1),
                        background_normal="",
                        background_down="",
                    )
                    # Keep as visual tag; make it a no-op so it isn't dimmed by disabled state
                    th_tag.bind(on_press=lambda *a: None)
                    sub_title_layout.add_widget(th_tag)

                grid.add_widget(sub_title_layout)

                # (removed accidental top-line raw info display)

                # Add header for each substation
                header_layout = BoxLayout(size_hint_y=None, height=35, spacing=5)
                # create header labels and bind their text_size so they stretch to the layout width
                h_loc = Label(text=S["MESSAGES"].get("LOC", "Τοποθεσία"), bold=True, size_hint_x=0.17)
                h_loc.halign = "center"
                h_loc.valign = "middle"
                h_loc.bind(size=lambda instance, value: setattr(instance, "text_size", (value[0], value[1])))
                header_layout.add_widget(h_loc)

                h_ad = Label(text=S["MESSAGES"].get("ADOPTION", "Ανάληψη"), bold=True, size_hint_x=0.1)
                h_ad.halign = "center"
                h_ad.valign = "middle"
                h_ad.bind(size=lambda instance, value: setattr(instance, "text_size", (value[0], value[1])))
                header_layout.add_widget(h_ad)

                h_info = Label(text=S["MESSAGES"].get("INFO", "Στοιχεία"), bold=True, size_hint_x=0.07)
                h_info.halign = "center"
                h_info.valign = "middle"
                h_info.bind(size=lambda instance, value: setattr(instance, "text_size", (value[0], value[1])))
                header_layout.add_widget(h_info)

                h_gates = Label(text=S["MESSAGES"].get("GATES", "Πύλες"), bold=True, size_hint_x=0.07)
                h_gates.halign = "center"
                h_gates.valign = "middle"
                h_gates.bind(size=lambda instance, value: setattr(instance, "text_size", (value[0], value[1])))
                header_layout.add_widget(h_gates)

                h_cap = Label(text=S["MESSAGES"].get("CAPACITORS", "Πυκνωτές"), bold=True, size_hint_x=0.07)
                h_cap.halign = "center"
                h_cap.valign = "middle"
                h_cap.bind(size=lambda instance, value: setattr(instance, "text_size", (value[0], value[1])))
                header_layout.add_widget(h_cap)

                h_main = Label(text=S["MESSAGES"].get("MAINTENANCES", "Συντηρήσεις"), bold=True, size_hint_x=0.1)
                h_main.halign = "center"
                h_main.valign = "middle"
                h_main.bind(size=lambda instance, value: setattr(instance, "text_size", (value[0], value[1])))
                header_layout.add_widget(h_main)

                h_last = Label(text=S["MESSAGES"].get("LAST", "Τελευταία"), bold=True, size_hint_x=0.1)
                h_last.halign = "center"
                h_last.valign = "middle"
                h_last.bind(size=lambda instance, value: setattr(instance, "text_size", (value[0], value[1])))
                header_layout.add_widget(h_last)

                h_mono = Label(text=S["MESSAGES"].get("SINGLE_LINE", "Μονογραμμικό"), bold=True, size_hint_x=0.12)
                h_mono.halign = "center"
                h_mono.valign = "middle"
                h_mono.bind(size=lambda instance, value: setattr(instance, "text_size", (value[0], value[1])))
                header_layout.add_widget(h_mono)

                spacer = Label(text="", size_hint_x=0.2)
                spacer.bind(size=lambda instance, value: setattr(instance, "text_size", (value[0], value[1])))
                header_layout.add_widget(spacer)  # Space for buttons
                grid.add_widget(header_layout)

                elem_count = elem_count_map.get(sub_id, 0)
                gate_count = gate_count_map.get(sub_id, 0)
                capacitor_count = capacitor_count_map.get(sub_id, 0)
                maint_count = maint_count_map.get(sub_id, 0)
                inspection_count = inspection_count_map.get(sub_id, 0)
                dga_count = dga_count_map.get(sub_id, 0)
                last_maint = last_maint_map.get(sub_id)
                last_maint_display = last_maint if last_maint else "-"

                # Substation row (removed name since it's now a title)
                sub_row_layout = BoxLayout(size_hint_y=None, height=40, spacing=5)

                # Location button (clickable) - do not display raw URL; center the button
                if location:
                    btn_holder = BoxLayout(size_hint_x=0.17)
                    btn_holder.add_widget(Widget())
                    location_btn = Button(
                        text=S["MESSAGES"].get("GOOGLE_MAPS_LINK", "Google Maps Link"),
                        size_hint=(None, None),
                        size=(140, 30),
                        font_size="11sp",
                        padding=(5, 5),
                    )
                    location_btn.bind(on_press=lambda x, url=location: webbrowser.open(url))
                    btn_holder.add_widget(location_btn)
                    btn_holder.add_widget(Widget())
                    sub_row_layout.add_widget(btn_holder)
                else:
                    lbl_loc = Label(text=S["MESSAGES"]["DASH"], size_hint_x=0.17)
                    lbl_loc.halign = "center"
                    lbl_loc.valign = "middle"
                    lbl_loc.bind(size=lambda instance, value: setattr(instance, "text_size", (value[0], value[1])))
                    sub_row_layout.add_widget(lbl_loc)

                lbl_ad = Label(text=adoption_date or "-", size_hint_x=0.1)
                lbl_ad.halign = "center"
                lbl_ad.valign = "middle"
                lbl_ad.bind(size=lambda instance, value: setattr(instance, "text_size", (value[0], value[1])))
                sub_row_layout.add_widget(lbl_ad)

                lbl_count = Label(text=str(elem_count), size_hint_x=0.07)
                lbl_count.halign = "center"
                lbl_count.valign = "middle"
                lbl_count.bind(size=lambda instance, value: setattr(instance, "text_size", (value[0], value[1])))
                sub_row_layout.add_widget(lbl_count)

                lbl_gates = Label(text=str(gate_count), size_hint_x=0.07)
                lbl_gates.halign = "center"
                lbl_gates.valign = "middle"
                lbl_gates.bind(size=lambda instance, value: setattr(instance, "text_size", (value[0], value[1])))
                sub_row_layout.add_widget(lbl_gates)

                lbl_cap = Label(text=str(capacitor_count), size_hint_x=0.07)
                lbl_cap.halign = "center"
                lbl_cap.valign = "middle"
                lbl_cap.bind(size=lambda instance, value: setattr(instance, "text_size", (value[0], value[1])))
                sub_row_layout.add_widget(lbl_cap)

                lbl_maint = Label(text=str(maint_count), size_hint_x=0.1)
                lbl_maint.halign = "center"
                lbl_maint.valign = "middle"
                lbl_maint.bind(size=lambda instance, value: setattr(instance, "text_size", (value[0], value[1])))
                sub_row_layout.add_widget(lbl_maint)

                lbl_last = Label(text=last_maint_display, size_hint_x=0.1)
                lbl_last.halign = "center"
                lbl_last.valign = "middle"
                lbl_last.bind(size=lambda instance, value: setattr(instance, "text_size", (value[0], value[1])))
                sub_row_layout.add_widget(lbl_last)

                mono_text = S["BUTTONS"]["OPEN"] if monogram_pdf else S["BUTTONS"]["ADD"]
                # hyperlink style: underline, blue text, transparent background
                monogram_btn = Button(
                    text=f"[u]{mono_text}[/u]",
                    markup=True,
                    background_normal="",
                    background_down="",
                    background_color=(0, 0, 0, 0),
                    color=(0.2, 0.6, 1, 1),
                    size_hint_x=0.12,
                )
                if monogram_pdf and os.path.exists(monogram_pdf):
                    monogram_btn.bind(
                        on_press=lambda x, path=monogram_pdf: self._open_monogram_pdf(path)
                    )
                else:
                    monogram_btn.bind(
                        on_press=lambda x, sid=sub_id, p=popup, f=filter_name: (
                            self._select_monogram_pdf(sid, p, f)
                        )
                    )
                # group monogram and action buttons in a fixed-width container
                actions_container = BoxLayout(size_hint_x=0.32, spacing=6)
                # monogram occupies the left portion (matching header 0.12 / 0.32)
                mono_portion = BoxLayout(size_hint_x=0.375)
                mono_portion.add_widget(Widget())
                mono_portion.add_widget(monogram_btn)
                mono_portion.add_widget(Widget())
                actions_container.add_widget(mono_portion)

                # small action buttons on the right portion
                actions_buttons = BoxLayout(size_hint_x=0.625, spacing=4)
                edit_icon = IconOnlyButton(
                    icon_type="edit",
                    size=(44, 36),
                    icon_color=self.theme.get("primary", (0.2, 0.6, 1, 1)),
                )
                edit_icon.bind(on_press=lambda x, sid=sub_id, sname=sub_name, loc=location, adate=adoption_date, div=division, p=popup: self.show_edit_substation_popup(sid, sname, loc, adate, div, p))
                actions_buttons.add_widget(edit_icon)

                delete_icon = IconOnlyButton(
                    icon_type="delete",
                    size=(44, 36),
                    icon_color=(1, 0.0, 0.0, 1),
                )
                delete_icon.bind(on_press=lambda x, sid=sub_id, sname=sub_name, p=popup: self.confirm_delete_substation(sid, sname, p))
                actions_buttons.add_widget(delete_icon)

                actions_container.add_widget(actions_buttons)
                sub_row_layout.add_widget(actions_container)
                grid.add_widget(sub_row_layout)

                # Keep maintenance/history/DGA buttons grouped separately (larger, with pictograms)
                buttons_layout = BoxLayout(size_hint_y=None, height=48, spacing=8)

                # Add count to button text if there are entries
                maint_btn_text = S["MESSAGES"].get("MAINT_HISTORY_LABEL", "Ιστορικό Συντήρησης")
                if maint_count > 0:
                    maint_btn_text += f" ({maint_count})"
                maint_hist_btn = IconButton(
                    text=maint_btn_text,
                    icon_type="maintenance",
                    size_hint_x=0.33,
                    theme=self.theme,
                )
                maint_hist_btn.bind(on_press=lambda x, sid=sub_id, sname=sub_name, p=popup: (self.show_substation_maintenance_history(sid, sname, p)))
                buttons_layout.add_widget(maint_hist_btn)

                # Add count to button text if there are entries
                insp_btn_text = S["MESSAGES"].get("INSPECTION_HISTORY_LABEL", "Ιστορικό Επιθεώρησης")
                if inspection_count > 0:
                    insp_btn_text += f" ({inspection_count})"
                insp_hist_btn = IconButton(
                    text=insp_btn_text,
                    icon_type="inspection",
                    size_hint_x=0.33,
                    theme=self.theme,
                )
                insp_hist_btn.bind(on_press=lambda x, sid=sub_id, sname=sub_name, p=popup: (self.show_substation_inspection_history(sid, sname, p)))
                buttons_layout.add_widget(insp_hist_btn)

                # DGA measurements button
                dga_btn_text = S["MESSAGES"].get("DGA_LABEL", "Φυσικοχημικές/Αεριοχρωματογραφία")
                if dga_count > 0:
                    dga_btn_text += f" ({dga_count})"
                dga_hist_btn = IconButton(
                    text=dga_btn_text,
                    icon_type="maintenance",
                    size_hint_x=0.34,
                    theme=self.theme,
                )
                dga_hist_btn.bind(on_press=lambda x, sid=sub_id, sname=sub_name, p=popup: (self.show_substation_dga_measurements(sid, sname, p)))
                buttons_layout.add_widget(dga_hist_btn)

                grid.add_widget(buttons_layout)

                # Action buttons row for add/ inactive / view (in one horizontal row)
                btn_row = BoxLayout(size_hint_y=None, height=42, spacing=8)

                add_elem_btn = Button(text="+ " + S["MESSAGES"]["ADD_ELEMENT_BTN"], size_hint_x=0.33)
                add_elem_btn.bind(on_press=lambda x, sid=sub_id, sname=sub_name, p=popup: (self.show_add_element_popup_for_substation(sid, sname, p)))
                btn_row.add_widget(add_elem_btn)

                inactive_count = inactive_count_map.get(sub_id, 0)
                inactive_elem_btn = Button(text=S["MESSAGES"]["INACTIVE_ELEMENTS"].format(count=inactive_count), size_hint_x=0.33)
                inactive_elem_btn.bind(on_press=lambda x, sid=sub_id, sname=sub_name, p=popup: (self.show_inactive_elements(sid, sname, p)))
                btn_row.add_widget(inactive_elem_btn)

                if not show_elements:
                    view_elements_btn = Button(text=S["MESSAGES"]["VIEW_ACTIVE_ELEMENTS"].format(count=elem_count), size_hint_x=0.34)
                    view_elements_btn.bind(on_press=lambda x, sname=sub_name, p=popup: (self._display_substations(sname, p)))
                    btn_row.add_widget(view_elements_btn)

                grid.add_widget(btn_row)

                # If we're not viewing a single substation, skip fetching/displaying elements
                if not show_elements:
                    spacing_widget = Label(text="", size_hint_y=None, height=30)
                    grid.add_widget(spacing_widget)
                    continue

                # Elements section (only active elements)
                c.execute(
                    "SELECT DISTINCT element_type FROM elements WHERE substation_id=? AND (operating_status IS NULL OR operating_status='Ενεργή') ORDER BY element_type",
                    (sub_id,),
                )
                all_label = S["MESSAGES"].get("ALL_LABEL", "(Όλα)")
                type_values = [all_label] + [row[0] for row in c.fetchall() if row[0]]
                current_type_filter = element_type_filter or all_label
                if current_type_filter not in type_values:
                    current_type_filter = all_label

                gate_query = "SELECT DISTINCT gate FROM elements WHERE substation_id=? AND (operating_status IS NULL OR operating_status='Ενεργή')"
                gate_params = [sub_id]
                if current_type_filter != "(Όλα)":
                    gate_query += " AND element_type=?"
                    gate_params.append(current_type_filter)
                c.execute(gate_query, gate_params)
                raw_gates = [row[0] for row in c.fetchall()]
                has_unassigned = any(
                    gate is None or str(gate).strip() == "" for gate in raw_gates
                )
                gate_set = {
                    str(gate).strip()
                    for gate in raw_gates
                    if gate is not None and str(gate).strip() != ""
                }
                gate_values = [all_label]
                # Ensure we have a gate prefix available in this scope for sorting
                gate_prefix = S["MESSAGES"].get("GATE_PREFIX", "ΠΥΛΗ")
                gate_values.extend(sorted([g for g in gate_set if g.startswith(gate_prefix)]))
                gate_values.extend(sorted([g for g in gate_set if not g.startswith(gate_prefix)]))
                if has_unassigned:
                    gate_values.append(get_unreg())
                current_gate_filter = gate_filter or all_label
                if current_gate_filter not in gate_values:
                    current_gate_filter = all_label

                filter_layout = BoxLayout(size_hint_y=None, height=40, spacing=10)
                filter_layout.add_widget(Label(text=S["MESSAGES"].get("FILTER_TYPE", "Φίλτρο Τύπου:"), size_hint_x=0.2))
                type_spinner = Spinner(
                    text=current_type_filter, values=type_values, size_hint_x=0.35
                )
                filter_layout.add_widget(type_spinner)
                filter_layout.add_widget(Label(text=S["MESSAGES"]["FILTER_GATE"], size_hint_x=0.2))
                gate_spinner = Spinner(
                    text=current_gate_filter, values=gate_values, size_hint_x=0.35
                )
                filter_layout.add_widget(gate_spinner)

                def refresh_filters(_spinner, _text):
                    self._display_substations(
                        sub_name, popup, type_spinner.text, gate_spinner.text
                    )

                type_spinner.bind(text=refresh_filters)
                gate_spinner.bind(text=refresh_filters)
                grid.add_widget(filter_layout)

                # Fetch model data from element_models table
                query = """
                          SELECT e.id, e.element_type, e.name, e.serial_number, e.maintenance_date, 
                              e.voltage_level, e.power_mva, e.manufacturer, e.manufacture_year, e.gate, e.is_main_switch,
                           em.breaker_category, em.model_name, em.manufacturer as model_manufacturer,
                           e.maintenance_cycle as element_maintenance_cycle, em.maintenance_cycle as model_maintenance_cycle, em.power_mva as model_power_mva, em.installation_space, e.operating_status, em.manual_pdf
                    FROM elements e 
                    LEFT JOIN element_models em ON e.element_model_id = em.id 
                    WHERE e.substation_id=?
                """
                params = [sub_id]
                if current_type_filter != "(Όλα)":
                    query += " AND e.element_type=?"
                    params.append(current_type_filter)
                if current_gate_filter != "(Όλα)":
                    if current_gate_filter == get_unreg():
                        query += " AND (e.gate IS NULL OR e.gate='')"
                    else:
                        query += " AND e.gate=?"
                        params.append(current_gate_filter)
                query += " ORDER BY e.gate"
                c.execute(query, params)
                all_elements = c.fetchall()
                
                # Split into active and inactive
                active_elements = [e for e in all_elements if not e[18] or e[18] == 'Ενεργή']  # Index 18 is operating_status
                inactive_elements = [e for e in all_elements if e[18] and e[18] == 'Ανενεργή']

                # Get maintenance counts for all elements in this substation
                c.execute("""
                    SELECT me.element_id, COUNT(*) 
                    FROM maintenance_elements me
                    JOIN elements e ON me.element_id = e.id
                    WHERE e.substation_id = ?
                    GROUP BY me.element_id
                """, (sub_id,))
                element_maintenance_counts = {elem_id: count for elem_id, count in c.fetchall()}

                if active_elements or inactive_elements:
                    # Define sort priority for element types
                    def get_element_priority(elem):
                        (
                            elem_id,
                            elem_type,
                            elem_name,
                            serial_number,
                            maintenance_date,
                            voltage_level,
                            power_mva,
                            manufacturer,
                            manufacture_year,
                            gate,
                            is_main_switch,
                            breaker_category,
                            model_name,
                            model_manufacturer,
                            element_maintenance_cycle,
                            model_maintenance_cycle,
                            model_power_mva,
                            installation_space,
                            operating_status,
                            manual_pdf,
                        ) = elem

                        # Priority order: HV breaker, Transformer, Motor Drive, MV main breaker, MV line breakers, MV capacitor breakers, rest
                        if elem_type == self.ELEM_BREAKER_YT:
                            return (1, elem_name)
                        elif self._is_transformer(elem_type):
                            return (2, elem_name)
                        elif elem_type == "Motor Drive":
                            return (3, elem_name)
                        elif (
                            elem_type == self.ELEM_BREAKER_MT and is_main_switch == 1
                        ):  # Main breaker
                            return (4, elem_name)
                        elif (
                            elem_type == self.ELEM_BREAKER_MT and is_main_switch == 2
                        ):  # Interconnection breaker
                            return (5, elem_name)
                        elif (
                            elem_type == self.ELEM_BREAKER_MT and is_main_switch == 0
                        ):  # Line breaker
                            return (6, elem_name)
                        elif (
                            elem_type == self.ELEM_BREAKER_MT and is_main_switch == 3
                        ):  # Capacitor breaker
                            return (7, elem_name)
                        else:
                            return (8, elem_name)

                    # Group active elements by gate
                    gates_dict = {}
                    for elem in active_elements:
                        (
                            elem_id,
                            elem_type,
                            elem_name,
                            serial_number,
                            maintenance_date,
                            voltage_level,
                            power_mva,
                            manufacturer,
                            manufacture_year,
                            gate,
                            is_main_switch,
                            breaker_category,
                            model_name,
                            model_manufacturer,
                            element_maintenance_cycle,
                            model_maintenance_cycle,
                            model_power_mva,
                            installation_space,
                            operating_status,
                            manual_pdf,
                        ) = elem

                        gate_key = gate if gate else get_unreg()
                        if gate_key not in gates_dict:
                            gates_dict[gate_key] = []
                        gates_dict[gate_key].append(elem)

                    # Sort elements within each gate according to priority
                    for gate_key in gates_dict:
                        gates_dict[gate_key].sort(key=get_element_priority)

                    # Display elements grouped by gate
                    # Show gates in order: ΠΥΛΗ 1, ΠΥΛΗ 2, etc., then unassigned
                    sorted_gates = sorted(
                        [g for g in gates_dict.keys() if g.startswith("ΠΥΛΗ")]
                    )
                    unreg_val = get_unreg()
                    if unreg_val in gates_dict:
                        sorted_gates.append(unreg_val)
                    
                    # Note: inactive elements are shown in a separate menu via show_inactive_elements()
                    # They are NOT displayed here in the main element list

                    for gate_name in sorted_gates:
                        gate_elements = gates_dict[gate_name]

                        # Gate header with count
                        element_count = len(gate_elements)
                        # Use red color for inactive gate header
                        header_color = (1, 0, 0, 1) if gate_name == "Ανενεργά" else (0.2, 0.6, 1, 1)
                        gate_label = Label(
                            text=f"   {gate_name} ({element_count} στοιχεία)",
                            size_hint_y=None,
                            height=35,
                            bold=True,
                            color=header_color,
                        )
                        grid.add_widget(gate_label)

                        # Display elements in this gate
                        for j, elem in enumerate(gate_elements, 1):
                            (
                                elem_id,
                                elem_type,
                                elem_name,
                                serial_number,
                                maintenance_date,
                                voltage_level,
                                power_mva,
                                manufacturer,
                                manufacture_year,
                                gate,
                                is_main_switch,
                                breaker_category,
                                model_name,
                                model_manufacturer,
                                element_maintenance_cycle,
                                model_maintenance_cycle,
                                model_power_mva,
                                installation_space,
                                operating_status,
                                manual_pdf,
                            ) = elem

                            # Check if maintenance is overdue or missing
                            from datetime import datetime, timedelta

                            # Prefer element-specific maintenance cycle; fall back to model's if element has none
                            maintenance_cycle = None
                            if element_maintenance_cycle and element_maintenance_cycle > 0:
                                maintenance_cycle = element_maintenance_cycle
                            elif model_maintenance_cycle and model_maintenance_cycle > 0:
                                maintenance_cycle = model_maintenance_cycle

                            is_overdue = False
                            if maintenance_cycle and maintenance_cycle > 0:
                                if (
                                    not maintenance_date
                                    or maintenance_date.strip() == ""
                                ):
                                    # Missing maintenance date when cycle is defined
                                    is_overdue = True
                                else:
                                    try:
                                        last_maint = datetime.strptime(
                                            maintenance_date.split()[0], "%Y-%m-%d"
                                        )
                                        years_ago = datetime.now() - timedelta(
                                            days=maintenance_cycle * 365
                                        )
                                        if last_maint < years_ago:
                                            is_overdue = True
                                    except Exception:
                                        pass

                            # Format maintenance date with color if overdue or missing
                            if is_overdue:
                                maint_display = f"[color=ff0000][b]Τελ. Συντ.: {maintenance_date or '-'}[/b][/color]"
                            else:
                                maint_display = f"Τελ. Συντ.: {maintenance_date or '-'}"
                            
                            # Add inactive indicator
                            inactive_marker = ""
                            if operating_status and operating_status == 'Ανενεργή':
                                inactive_marker = " [color=ff0000][b][ΑΝΕΝΕΡΓΟ][/b][/color]"

                            # Create element text with multiple lines for better readability
                            # Add breaker subtype text for circuit breakers.
                            if elem_type in self.BREAKER_ELEMENT_TYPES:
                                elem_type = self._format_elem_type(elem_type, is_main_switch)

                            breaker_info = (
                                f" | {breaker_category}" if breaker_category else ""
                            )
                            manufacture_info = (
                                f" | Έτος: {manufacture_year}"
                                if manufacture_year
                                else ""
                            )
                            effective_power = model_power_mva if (model_power_mva is not None) else power_mva
                            power_display = f"{effective_power} MVA" if effective_power else "-"
                            elem_text = f"   {j}. [b][size=18]{elem_name}[/size][/b] - {elem_type}{breaker_info}{inactive_marker}\n      S/N: {serial_number or '-'}{manufacture_info}\n      Κατ.: {model_manufacturer or manufacturer or '-'} | Μοντ.: {model_name or '-'} | Χώρος: {installation_space or '-'} | Τάση: {voltage_level or '-'} | Ισχ.: {power_display}\n      Κύκλος: {maintenance_cycle or '-'} έτη | {maint_display} (id:{elem_id})"

                            # Create a horizontal layout for element and buttons
                            elem_layout = BoxLayout(size_hint_y=None, spacing=5)
                            elem_layout.bind(
                                minimum_height=elem_layout.setter("height")
                            )

                            elem_label = Label(
                                text=elem_text, size_hint=(0.75, None), markup=True
                            )
                            # Enable text wrapping and automatic height calculation
                            elem_label.bind(
                                width=lambda instance, value: setattr(
                                    instance, "text_size", (value, None)
                                ),
                                texture_size=lambda instance, value: (
                                    setattr(instance, "height", max(70, value[1] + 10)),
                                    setattr(
                                        elem_layout, "height", max(70, value[1] + 10)
                                    ),
                                ),
                            )
                            elem_layout.add_widget(elem_label)

                            # Button container (icon-only buttons: manual, history, view, edit, delete)
                            btn_box = BoxLayout(size_hint_x=0.25, spacing=6)

                            # Add manual button if manual_pdf exists
                            if manual_pdf and os.path.exists(manual_pdf):
                                manual_btn = IconOnlyButton(icon_type="book", icon_color=(0.8, 0.4, 0, 1))
                                manual_btn.size_hint_x = 0.2
                                manual_btn.bind(on_press=lambda x, mp=manual_pdf: self._open_model_manual(mp))
                                btn_box.add_widget(manual_btn)
                                # Adjust button sizes when manual exists (5 buttons)
                                history_size = 0.2
                                view_size = 0.2
                                edit_size = 0.2
                                delete_size = 0.2
                            else:
                                # Adjust button sizes when no manual (4 buttons)
                                history_size = 0.25
                                view_size = 0.25
                                edit_size = 0.25
                                delete_size = 0.25

                            # Add maintenance history button
                            history_btn = IconOnlyButton(icon_type="maintenance", icon_color=(0.4, 0.6, 0.8, 1))
                            history_btn.size_hint_x = history_size
                            
                            # Check if element has maintenance history
                            elem_maint_count = element_maintenance_counts.get(elem_id, 0)
                            if elem_maint_count > 0:
                                history_btn.bind(on_press=lambda x, eid=elem_id, ename=elem_name, p=popup: (self.show_element_maintenance_history(eid, ename, p)))
                            else:
                                # Grey out and disable button if no maintenance history
                                history_btn.disabled = True
                                history_btn.icon_color = (0.5, 0.5, 0.5, 0.5)
                            btn_box.add_widget(history_btn)

                            view_btn = IconOnlyButton(icon_type="eye", icon_color=self.theme.get("text", (0.12,0.12,0.12,1)))
                            view_btn.size_hint_x = view_size
                            view_btn.bind(on_press=lambda x, eid=elem_id: (self._show_element_quick_view(eid)))
                            btn_box.add_widget(view_btn)

                            edit_elem_btn = IconOnlyButton(icon_type="edit", icon_color=self.theme.get("primary", (0.2, 0.6, 1, 1)))
                            edit_elem_btn.size_hint_x = edit_size
                            edit_elem_btn.bind(
                                on_press=lambda x, eid=elem_id, sid=sub_id, sname=sub_name, p=popup: (
                                    self.show_edit_element_popup(eid, sid, p, sname)
                                )
                            )
                            btn_box.add_widget(edit_elem_btn)

                            delete_elem_btn = IconOnlyButton(icon_type="delete", icon_color=(1, 0.0, 0.0, 1))
                            delete_elem_btn.size_hint_x = delete_size
                            delete_elem_btn.bind(
                                on_press=lambda x, eid=elem_id, ename=elem_name, sid=sub_id, sname=sub_name, p=popup: (
                                    self.confirm_delete_element(
                                        eid, ename, sid, p, sname
                                    )
                                )
                            )
                            btn_box.add_widget(delete_elem_btn)

                            elem_layout.add_widget(btn_box)

                            grid.add_widget(elem_layout)
                else:
                    no_elem_label = Label(
                        text="   " + S["MESSAGES"]["NO_ELEMENTS_PAREN"], size_hint_y=None, height=30
                    )
                    grid.add_widget(no_elem_label)

                # Add spacing between substations
                spacing_widget = Label(text="", size_hint_y=None, height=30)
                grid.add_widget(spacing_widget)
        else:
            empty_label = Label(text=S["MESSAGES"]["EMPTY_DB"], size_hint_y=None, height=40)
            grid.add_widget(empty_label)

        scroll.add_widget(grid)
        main_layout.add_widget(scroll)

        # Add buttons layout
        buttons_bottom_layout = BoxLayout(size_hint_y=0.1, spacing=10)

        add_substation_btn = Button(text="+ " + S["MESSAGES"]["ADD_SUBSTATION_BTN"])
        add_substation_btn.bind(
            on_press=lambda x: self.show_add_substation_popup_from_db_view(popup)
        )
        buttons_bottom_layout.add_widget(add_substation_btn)

        close_btn = Button(text=S["BUTTONS"]["CLOSE"])
        close_btn.bind(on_press=popup.dismiss)
        buttons_bottom_layout.add_widget(close_btn)

        main_layout.add_widget(buttons_bottom_layout)

        popup.content = main_layout
        if not reuse_popup:
            popup.open()

    def create_substations_template(self, instance):
        success, message = create_substations_template(os.path.dirname(__file__))
        title = S["MESSAGES"].get("TEMPLATE_SUBSTATIONS_TITLE", "Template Υποσταθμών") if success else S["TITLES"]["ERROR"]
        show_message_popup(title, message)

    def _create_file_import_dialog(self, title, import_callback, parent_popup=None):
        """Generic file import dialog for substations and elements

        Args:
            title: Popup title
            import_callback: Function to call with file_path when import is confirmed
        """
        # Prefer native dialog first (desktop). If a file is chosen, call back immediately.
        allow_fallback = False
        try:
            fp = ask_open_file(title=title, filetypes=(("Excel/CSV", "*.xlsx;*.csv"),))
        except ImportError:
            allow_fallback = True
            fp = None
        except Exception:
            fp = None

        if fp:
            # If a native file was chosen, dismiss the parent menu then import.
            if parent_popup:
                try:
                    parent_popup.dismiss()
                except Exception:
                    pass
            # sanitize path: strip surrounding whitespace and quotes that may be
            # returned by some native dialogs or pasted by the user
            try:
                if isinstance(fp, str):
                    fp = fp.strip().strip('\"\'')
            except Exception:
                pass
            import_callback(fp)
            return
        if not allow_fallback:
            # user cancelled native dialog -> do not open in-app selector
            return

        popup = Popup(title=title, size_hint=(0.9, 0.9))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        # Path input
        path_label = Label(text=S["MESSAGES"]["FILE_PATH_LABEL"], size_hint_y=0.1)
        layout.add_widget(path_label)

        path_input = TextInput(
            hint_text=S["MESSAGES"]["FILE_PATH_LABEL"], size_hint_y=0.15, multiline=False
        )
        layout.add_widget(path_input)

        # File chooser with default path
        layout.add_widget(Label(text=S["MESSAGES"]["SELECT_FROM_LIST"], size_hint_y=0.1))
        chooser = FileChooserListView(
            filters=["*.xlsx", "*.csv"], path=os.path.dirname(__file__)
        )
        layout.add_widget(chooser)

        # Buttons
        buttons_layout = BoxLayout(size_hint_y=0.1, spacing=10)

        def import_file():
            file_path = (
                path_input.text.strip()
                if path_input.text.strip()
                else (chooser.selection[0] if chooser.selection else None)
            )

            # sanitize user-provided path from input or chooser selection
            try:
                if isinstance(file_path, str):
                    file_path = file_path.strip().strip('"\'')
            except Exception:
                pass

            if not file_path:
                show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["ENTER_PATH"])
                return

            if not os.path.exists(file_path):
                show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["FILE_NOT_FOUND"])
                return

            # perform import and then dismiss popups on success
            try:
                import_callback(file_path)
            except Exception as e:
                show_message_popup(S["TITLES"]["ERROR"], f"{S['MESSAGES']['IMPORT_FAILED']}\n{str(e)}")
                return
            popup.dismiss()
            if parent_popup:
                try:
                    parent_popup.dismiss()
                except Exception:
                    pass

        import_btn = Button(text=S["BUTTONS"]["IMPORT"])
        import_btn.bind(on_press=lambda x: import_file())
        buttons_layout.add_widget(import_btn)

        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
        cancel_btn.bind(on_press=popup.dismiss)
        buttons_layout.add_widget(cancel_btn)

        layout.add_widget(buttons_layout)
        popup.content = layout
        popup.open()

    def _open_monogram_pdf(self, pdf_path):
        from reports import open_file as _open
        return _open(pdf_path, not_found_message="Το αρχείο δεν βρέθηκε!", error_prefix="Αποτυχία ανοίγματος PDF:\n")

    def _select_monogram_pdf(self, substation_id, parent_popup=None, filter_name=None):
        allow_fallback = False
        try:
            fp = ask_open_file(title="Select monogram PDF", filetypes=(("PDF files", "*.pdf"),))
        except ImportError:
            allow_fallback = True
            fp = None
        except Exception:
            fp = None

        if fp:
            if not os.path.exists(fp):
                show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["FILE_NOT_FOUND"])
                return
            if not fp.lower().endswith(".pdf"):
                show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["PLEASE_SELECT_PDF"])
                return
            c = self.conn.cursor()
            c.execute(
                "UPDATE substations SET monogram_pdf=? WHERE id=?",
                (fp, substation_id),
            )
            self.conn.commit()
            if parent_popup:
                try:
                    parent_popup.dismiss()
                except Exception:
                    pass
            self._display_substations(filter_name)
            return

        if not allow_fallback:
            # user cancelled native dialog -> do nothing
            return

        popup = Popup(title=S["MESSAGES"]["SELECT_MONOGRAM_PDF_TITLE"], size_hint=(0.9, 0.9))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
        
        path_label = Label(text=S["MESSAGES"]["FILE_PATH_LABEL"], size_hint_y=0.1)
        layout.add_widget(path_label)

        path_input = TextInput(
            hint_text=S["MESSAGES"]["FILE_PATH_LABEL"], size_hint_y=0.12, multiline=False
        )
        layout.add_widget(path_input)
        
        layout.add_widget(Label(text=S["MESSAGES"]["SELECT_FROM_LIST"], size_hint_y=0.1))
        chooser = FileChooserListView(filters=["*.pdf"], path=os.path.dirname(__file__))
        layout.add_widget(chooser)

        buttons_layout = BoxLayout(size_hint_y=0.12, spacing=10)

        def save_file():
            file_path = (
                path_input.text.strip()
                if path_input.text.strip()
                else (chooser.selection[0] if chooser.selection else None)
            )

            if not file_path:
                show_message_popup(
                    S["TITLES"]["ERROR"], S["MESSAGES"].get("ENTER_PATH", "Παρακαλώ εισάγετε διαδρομή ή επιλέξτε αρχείο!")
                )
                return

            if not os.path.exists(file_path):
                show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["FILE_NOT_FOUND"])
                return

            if not file_path.lower().endswith(".pdf"):
                show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["PLEASE_SELECT_PDF"])
                return

            c = self.conn.cursor()
            c.execute(
                "UPDATE substations SET monogram_pdf=? WHERE id=?",
                (file_path, substation_id),
            )
            self.conn.commit()
            popup.dismiss()

            if parent_popup:
                parent_popup.dismiss()
            self._display_substations(filter_name)

        save_btn = Button(text=S["BUTTONS"]["SAVE"])
        save_btn.bind(on_press=lambda x: save_file())
        buttons_layout.add_widget(save_btn)

        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
        cancel_btn.bind(on_press=popup.dismiss)
        buttons_layout.add_widget(cancel_btn)

        layout.add_widget(buttons_layout)
        popup.content = layout
        popup.open()

    def create_elements_template(self, instance):
        success, message = create_elements_template(os.path.dirname(__file__))
        title = S["MESSAGES"].get("TEMPLATE_ELEMENTS_TITLE", "Template Στοιχείων") if success else S["TITLES"]["ERROR"]
        show_message_popup(title, message)

    def show_import_substations_dialog(self, instance_or_parent_popup):
        from imports import show_import_substations_dialog as _f
        return _f(self, instance_or_parent_popup)

    def show_import_elements_dialog(self, instance_or_parent_popup):
        from imports import show_import_elements_dialog as _f
        return _f(self, instance_or_parent_popup)

    def show_import_android_changes_dialog(self, instance_or_parent_popup):
        from imports import show_import_android_changes_dialog as _f
        return _f(self, instance_or_parent_popup)

    def _create_android_changes_import_dialog(self, title, import_callback, parent_popup=None):
        # Prefer native dialog when available (desktop). If selected, import immediately.
        allow_fallback = False
        try:
            fp = ask_open_file(title=title, filetypes=(("JSONL/JSON", "*.jsonl;*.json"),))
        except ImportError:
            allow_fallback = True
            fp = None
        except Exception:
            fp = None

        if fp:
            # Dismiss parent menu only on success
            if parent_popup:
                try:
                    parent_popup.dismiss()
                except Exception:
                    pass
            import_callback(fp)
            return
        if not allow_fallback:
            # user cancelled native dialog -> do not open in-app selector
            return

        popup = Popup(title=title, size_hint=(0.9, 0.9))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        path_label = Label(
            text=S["MESSAGES"]["CHANGELOG_FILE_LABEL"], size_hint_y=0.1
        )
        layout.add_widget(path_label)

        path_input = TextInput(
            hint_text=S["MESSAGES"]["FILE_PATH_LABEL"], size_hint_y=0.15, multiline=False
        )
        layout.add_widget(path_input)

        layout.add_widget(Label(text=S["MESSAGES"]["SELECT_FROM_LIST"], size_hint_y=0.1))
        chooser = FileChooserListView(
            filters=["*.jsonl", "*.json"], path=os.path.dirname(__file__)
        )
        layout.add_widget(chooser)

        buttons_layout = BoxLayout(size_hint_y=0.1, spacing=10)

        def import_file():
            file_path = (
                path_input.text.strip()
                if path_input.text.strip()
                else (chooser.selection[0] if chooser.selection else None)
            )

            if not file_path:
                show_message_popup(
                    S["TITLES"]["ERROR"], S["MESSAGES"].get("ENTER_PATH", "Παρακαλώ εισάγετε διαδρομή ή επιλέξτε αρχείο!")
                )
                return

            if not os.path.exists(file_path):
                show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["FILE_NOT_FOUND"])
                return

            try:
                import_callback(file_path)
            except Exception as e:
                show_message_popup(S["TITLES"]["ERROR"], f"{S['MESSAGES']['IMPORT_FAILED']}\n{str(e)}")
                return
            popup.dismiss()
            if parent_popup:
                try:
                    parent_popup.dismiss()
                except Exception:
                    pass

        import_btn = Button(text=S["BUTTONS"]["IMPORT"])
        import_btn.bind(on_press=lambda x: import_file())
        buttons_layout.add_widget(import_btn)

        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
        cancel_btn.bind(on_press=popup.dismiss)
        buttons_layout.add_widget(cancel_btn)

        layout.add_widget(buttons_layout)
        popup.content = layout
        popup.open()

    def import_android_changes_from_file(self, file_path):
        from changelog import import_android_changes_from_file as _f
        return _f(self, file_path)

    def process_sync_inbox_now(self):
        from sync_service import run_sync_cycle

        current_user = get_current_user() or {}
        actor = current_user.get("name") or "desktop"
        hot_keep = int(get_app_setting("backup_hot_keep", 3) or 3)
        backup_on_change = bool(get_app_setting("sync_backup_on_change", True))

        summary = run_sync_cycle(
            self.conn,
            db_path=self.db_path,
            actor=actor,
            create_backup_on_change=backup_on_change,
            hot_keep=hot_keep,
        )
        sync = summary["sync"]
        processed = int(sync.get("processed", 0) or 0)
        accepted = int(sync.get("accepted", 0) or 0)
        already_applied = int(sync.get("already_applied", 0) or 0)
        conflicts = sync.get("conflicts", 0)
        rejected = int(sync.get("rejected", 0) or 0)
        
        # If there are conflicts, show conflict resolution UI instead of summary
        if conflicts > 0:
            self._show_sync_notification(summary)
            return

        # Manual sync uses the same visual language as auto sync (bold + color emphasis).
        lines = [
            S["MESSAGES"].get(
                "SYNC_MANUAL_SUMMARY_TITLE",
                "Η επεξεργασία εισερχομένων ολοκληρώθηκε.",
            ),
            "",
            f"Επεξεργασμένα: [b]{processed}[/b]",
            self._format_sync_report_line("Αποδεκτά", accepted, kind="positive"),
        ]
        if already_applied > 0:
            lines.append(f"↻ Ήδη εφαρμοσμένα: [b]{already_applied}[/b]")
        if rejected > 0:
            lines.append(self._format_sync_report_line("Απορριφθέντα", rejected, kind="negative"))

        lines.extend(self._build_sync_file_summary_lines(sync, max_files=6))

        if summary.get("snapshot"):
            lines.append(
                S["MESSAGES"].get(
                    "SYNC_SNAPSHOT_LINE_FMT",
                    "Στιγμιότυπο: {snapshot}",
                ).format(snapshot=summary["snapshot"])
            )

        self._show_rich_sync_report(
            S["TITLES"].get("INFO", "Πληροφορία"),
            "\n".join(lines),
        )

    def _run_startup_sync_cycle(self, force=False):
        try:
            if not bool(get_app_setting("sync_auto_cycle_enabled", True)):
                return
            import threading
            from sync_service import run_sync_cycle, resolve_sync_root, resolve_backup_root, ensure_sync_tree, ensure_backup_tree

            sync_root = resolve_sync_root(self.db_path)
            ensure_sync_tree(sync_root)

            probe_enabled = bool(get_app_setting("startup_sync_probe_enabled", True))
            prompt_on_change = bool(get_app_setting("startup_sync_prompt_on_change", True))

            current_probe = None
            if probe_enabled:
                current_probe = self._compute_startup_sync_probe(sync_root)
                state = self._load_startup_sync_state()
                previous_probe = state.get("last_probe")
                shared_root_exists = bool((current_probe or {}).get("shared_root_exists", True))

                # Never silently skip startup sync when shared root folder is missing.
                if (not force) and previous_probe and previous_probe == current_probe and shared_root_exists:
                    logging.info("Startup sync skipped: no probe changes detected")
                    self._last_sync_cycle_ts = datetime.now().timestamp()
                    return

                probe_changed = bool(previous_probe and previous_probe != current_probe)
                shared_root_missing = not shared_root_exists

                # Prompt when probe changed OR when shared root is missing.
                if (not force) and prompt_on_change and (probe_changed or shared_root_missing):
                    def _defer_startup_sync():
                        logging.info("Startup sync deferred by user")
                        self._show_brief_info_toast(
                            S["MESSAGES"].get(
                                "STARTUP_SYNC_DEFERRED_TOAST",
                                "Startup sync was deferred. You can run sync manually from Import/Sync.",
                            ),
                            duration=4.0,
                            action_text=S["MESSAGES"].get("STARTUP_SYNC_DEFERRED_ACTION", "Open Import/Sync"),
                            action_callback=lambda: self.show_import_menu(None),
                        )

                    self._show_startup_sync_prompt_popup(
                        on_sync=lambda: self._run_startup_sync_cycle(force=True),
                        on_skip=_defer_startup_sync,
                        summary_text=self._build_startup_probe_summary(current_probe),
                    )
                    return
            
            # Show progress popup FIRST on UI thread so it can render
            progress_ui = self._show_startup_progress_popup()
            progress_popup = progress_ui["popup"]
            progress_popup.open()
            
            # Variables to hold results - shared with worker thread
            results = {
                "sync_result": None,
                "report_result": None,
                "relink_result": None,
                "run_result": None,
            }
            
            # Define the heavy work to run in background thread
            def _startup_worker():
                sync_result = {"total": 0, "synced": 0, "failed": 0}
                report_result = {"total": 0, "generated": 0, "skipped": 0, "failed": 0}
                relink_result = {"media_linked": 0, "reports_linked": 0, "reports_already": 0, "reports_missing": 0}
                startup_conn = None

                try:
                    # Use a thread-local DB connection. SQLite connections are thread-affine.
                    startup_conn = init_db(self.db_path)

                    # Ensure directory trees exist at startup
                    sync_root = resolve_sync_root(self.db_path)
                    backup_root = resolve_backup_root(self.db_path)
                    ensure_sync_tree(sync_root)
                    ensure_backup_tree(backup_root)

                    # Ensure folder structure for all substations with elements
                    try:
                        def _sync_progress(operation, substation, current, total):
                            self._update_startup_progress(progress_ui, operation, substation, current, total)
                        
                        sync_result = sync_all_substation_structures(
                            startup_conn,
                            db_path=self.db_path,
                            quiet=True,
                            progress_callback=_sync_progress,
                        )
                        logging.info(
                            "Substation folder sync: total=%s synced=%s failed=%s",
                            sync_result.get("total", 0),
                            sync_result.get("synced", 0),
                            sync_result.get("failed", 0),
                        )
                    except Exception:
                        logging.exception("Failed to sync substation folder structures at startup")

                    # Generate missing PDF reports for existing maintenance records
                    try:
                        def _report_progress(operation, substation, current, total):
                            self._update_startup_progress(progress_ui, operation, substation, current, total)
                        
                        report_result = regenerate_maintenance_reports(
                            startup_conn,
                            db_path=self.db_path,
                            quiet=True,
                            progress_callback=_report_progress,
                        )
                        logging.info(
                            "Maintenance reports: total=%s generated=%s skipped=%s failed=%s",
                            report_result.get("total", 0),
                            report_result.get("generated", 0),
                            report_result.get("skipped", 0),
                            report_result.get("failed", 0),
                        )
                    except Exception:
                        logging.exception("Failed to regenerate maintenance reports at startup")

                    # Relink existing file/folder assets into DB when missing.
                    try:
                        def _relink_progress(operation, substation, current, total):
                            self._update_startup_progress(progress_ui, operation, substation, current, total)
                        
                        relink_result = relink_existing_maintenance_assets(
                            startup_conn,
                            db_path=self.db_path,
                            progress_callback=_relink_progress,
                        )
                        logging.info(
                            "Asset relink: media_linked=%s reports_linked=%s reports_already=%s reports_missing=%s",
                            relink_result.get("media_linked", 0),
                            relink_result.get("reports_linked", 0),
                            relink_result.get("reports_already", 0),
                            relink_result.get("reports_missing", 0),
                        )
                    except Exception:
                        logging.exception("Failed to relink existing maintenance assets at startup")

                    try:
                        startup_conn.commit()
                    except Exception:
                        logging.exception("Failed to commit startup link/report updates")

                    # Store results for main thread access via closure
                    results["sync_result"] = sync_result
                    results["report_result"] = report_result
                    results["relink_result"] = relink_result

                    try:
                        run_result = run_sync_cycle(
                            startup_conn,
                            db_path=self.db_path,
                            actor="startup",
                            create_backup_on_change=bool(get_app_setting("sync_backup_on_change", True)),
                            hot_keep=int(get_app_setting("backup_hot_keep", 3) or 3),
                        )
                        results["run_result"] = run_result
                    except Exception:
                        logging.exception("Failed to run sync cycle at startup")

                finally:
                    try:
                        if startup_conn is not None:
                            startup_conn.close()
                    except Exception:
                        pass

                # Retry deferred hybrid folder jobs (local-first queue worker).
                try:
                    q = process_hybrid_queue(self.db_path, max_jobs=120)
                    if q.get("processed", 0) > 0:
                        logging.info(
                            "Hybrid queue processed=%s succeeded=%s failed=%s remaining=%s",
                            q.get("processed", 0),
                            q.get("succeeded", 0),
                            q.get("failed", 0),
                            q.get("remaining", 0),
                        )
                except Exception:
                    logging.exception("Hybrid queue processing failed at startup")

                # Schedule completion on UI thread
                Clock.schedule_once(lambda dt: _finish_startup(), 0)

            # Define finish callback to run on UI thread
            def _finish_startup():
                try:
                    progress_popup.dismiss()
                except Exception:
                    pass
                
                self._last_sync_cycle_ts = datetime.now().timestamp()
                
                sync_result = results["sync_result"] or {}
                report_result = results["report_result"] or {}
                relink_result = results["relink_result"] or {}
                run_result = results["run_result"]

                startup_sync = (run_result or {}).get("sync", {})
                startup_accepted = int(startup_sync.get("accepted", 0) or 0)
                startup_conflicts = int(startup_sync.get("conflicts", 0) or 0)

                # Only notify for startup auto-sync when there is meaningful change to review.
                if run_result and (startup_accepted > 0 or startup_conflicts > 0):
                    summary_delay = 1.2 if startup_conflicts > 0 else 0.6
                    Clock.schedule_once(
                        lambda dt: self._show_sync_notification(run_result),
                        summary_delay,
                    )

                # Refresh and persist startup probe state after startup sync work.
                if probe_enabled:
                    try:
                        post_probe = self._compute_startup_sync_probe(resolve_sync_root(self.db_path))
                        self._save_startup_sync_state(
                            {
                                "state_version": 1,
                                "updated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                                "last_probe": post_probe,
                                "last_run": {
                                    "sync_processed": (run_result or {}).get("sync", {}).get("processed", 0),
                                    "sync_accepted": (run_result or {}).get("sync", {}).get("accepted", 0),
                                    "sync_conflicts": (run_result or {}).get("sync", {}).get("conflicts", 0),
                                },
                            }
                        )
                    except Exception:
                        logging.exception("Failed to persist startup sync probe state")

            # Start worker thread (daemon so it doesn't block app exit)
            worker_thread = threading.Thread(target=_startup_worker, daemon=True)
            worker_thread.start()
        except Exception:
            logging.exception("Startup sync cycle failed")

    def _run_periodic_sync_cycle(self, *_args):
        try:
            if not bool(get_app_setting("sync_auto_cycle_enabled", True)):
                return
            interval_minutes = int(get_app_setting("sync_auto_cycle_minutes", 60))
            now_ts = datetime.now().timestamp()
            if (now_ts - float(getattr(self, "_last_sync_cycle_ts", 0))) < max(60, interval_minutes * 60):
                return

            self._last_sync_cycle_ts = now_ts
            from sync_service import run_sync_cycle

            result = run_sync_cycle(
                self.conn,
                db_path=self.db_path,
                actor="scheduler",
                create_backup_on_change=bool(get_app_setting("sync_backup_on_change", True)),
                hot_keep=int(get_app_setting("backup_hot_keep", 3) or 3),
            )

            # Retry deferred hybrid folder jobs periodically.
            try:
                q = process_hybrid_queue(self.db_path, max_jobs=120)
                if q.get("processed", 0) > 0:
                    logging.info(
                        "Hybrid queue processed=%s succeeded=%s failed=%s remaining=%s",
                        q.get("processed", 0),
                        q.get("succeeded", 0),
                        q.get("failed", 0),
                        q.get("remaining", 0),
                    )
            except Exception:
                logging.exception("Hybrid queue processing failed in scheduler")

            # Show notification if changes were imported
            if result and result.get("sync", {}).get("processed", 0) > 0:
                self._show_sync_notification(result)
        except Exception:
            logging.exception("Periodic sync cycle failed")

    def _append_change_log(self, operation, table, data):
        """Add a change to the pending changes list for export on close."""
        try:
            if not hasattr(self, "_pending_changes"):
                self._pending_changes = []
            self._pending_changes.append({
                "operation": operation,
                "table": table,
                "data": data
            })
        except Exception:
            logging.exception("Failed to append change log")

    def _export_pending_changes(self, show_popup=False):
        """Export all pending changes to JSONL file in sync inbox."""
        try:
            if not hasattr(self, "_pending_changes") or not self._pending_changes:
                return None

            from sync_service import resolve_sync_root
            from datetime import datetime
            import json

            sync_root = resolve_sync_root(self.db_path)
            inbox_pending = os.path.join(sync_root, "inbox", "pending")
            os.makedirs(inbox_pending, exist_ok=True)

            # Get current user for filename
            current_user = get_current_user()
            username = current_user.get("name", "desktop") if current_user else "desktop"
            # Sanitize username for filename
            username = "".join(c for c in username if c.isalnum() or c in (' ', '_')).replace(' ', '_')
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"desktop_{timestamp}_{username}.jsonl"
            filepath = os.path.join(inbox_pending, filename)

            with open(filepath, "w", encoding="utf-8") as f:
                for change in self._pending_changes:
                    f.write(json.dumps(change, ensure_ascii=False) + "\n")

            change_count = len(self._pending_changes)
            self._pending_changes = []  # Clear after export

            if show_popup:
                show_message_popup(
                    S["TITLES"].get("INFO", "Πληροφορία"),
                    S["MESSAGES"].get(
                        "CHANGES_EXPORTED_FMT",
                        "Εξήχθησαν {count} αλλαγές στο αρχείο:\n{file}"
                    ).format(count=change_count, file=filename)
                )
            return filepath
        except Exception as e:
            logging.exception("Failed to export pending changes")
            if show_popup:
                show_message_popup(
                    S["TITLES"].get("ERROR", "Σφάλμα"),
                    S["MESSAGES"].get("CHANGES_EXPORT_ERROR", "Σφάλμα κατά την εξαγωγή αλλαγών: ") + str(e)
                )
            return None

    def _check_previous_sync_issues(self):
        """Check for rejected or conflict files from previous sessions and warn user."""
        try:
            from sync_service import resolve_sync_root
            import glob

            sync_root = resolve_sync_root(self.db_path)
            current_user = get_current_user()
            if not current_user:
                return

            username = current_user.get("name", "")
            if not username:
                return

            # Sanitize username for pattern matching
            username_clean = "".join(c for c in username if c.isalnum() or c in (' ', '_')).replace(' ', '_')

            # Check rejected and conflicts folders
            rejected_dir = os.path.join(sync_root, "inbox", "processed", "rejected")
            conflicts_dir = os.path.join(sync_root, "inbox", "processed", "conflicts")

            rejected_files = []
            conflicts_files = []

            if os.path.exists(rejected_dir):
                pattern = os.path.join(rejected_dir, f"*{username_clean}*.jsonl")
                rejected_files = glob.glob(pattern)

            if os.path.exists(conflicts_dir):
                pattern = os.path.join(conflicts_dir, f"*{username_clean}*.jsonl")
                conflicts_files = glob.glob(pattern)

            if rejected_files or conflicts_files:
                msg = S["MESSAGES"].get(
                    "SYNC_ISSUES_FOUND",
                    "Βρέθηκαν προηγούμενες αλλαγές με προβλήματα:\n"
                )
                if rejected_files:
                    msg += f"\n❌ Απορριφθέντα: {len(rejected_files)}"
                if conflicts_files:
                    msg += f"\n⚠ Συγκρούσεις: {len(conflicts_files)}"
                msg += "\n\n" + S["MESSAGES"].get(
                    "SYNC_ISSUES_ACTION",
                    "Ελέγξτε τους φακέλους rejected και conflicts."
                )
                
                show_message_popup(
                    S["TITLES"].get("WARNING", "Προειδοποίηση"),
                    msg
                )
        except Exception:
            logging.exception("Failed to check previous sync issues")

    def _show_sync_notification(self, sync_result):
        """Show notification popup after automatic sync imports changes."""
        try:
            sync_summary = sync_result.get("sync", {})
            processed = sync_summary.get("processed", 0)
            accepted = sync_summary.get("accepted", 0)
            already_applied = sync_summary.get("already_applied", 0)
            conflicts = sync_summary.get("conflicts", 0)
            rejected = sync_summary.get("rejected", 0)

            if processed == 0:
                return

            # Show report only when there is something actionable to show.
            if accepted <= 0 and conflicts <= 0:
                return

            if conflicts > 0:
                lines = [
                    S["MESSAGES"].get("SYNC_AUTO_SUMMARY", "Αυτόματος συγχρονισμός ολοκληρώθηκε:"),
                    "",
                ]
                if accepted > 0:
                    lines.append(self._format_sync_report_line("Αποδεκτά", accepted, kind="positive"))
                lines.append(self._format_sync_report_line("Συγκρούσεις", conflicts, kind="negative"))
                if rejected > 0:
                    lines.append(self._format_sync_report_line("Απορριφθέντα", rejected, kind="negative"))
                lines.extend(self._build_sync_file_summary_lines(sync_summary, max_files=6))

                self._show_rich_sync_report(
                    S["TITLES"].get("SYNC_NOTIFICATION", "Συγχρονισμός"),
                    "\n".join(lines),
                )
                # Open conflict resolution right after summary so user can act.
                Clock.schedule_once(lambda dt: self._show_conflict_resolution(sync_result), 0.2)
                return

            lines = [
                S["MESSAGES"].get("SYNC_AUTO_SUMMARY", "Αυτόματος συγχρονισμός ολοκληρώθηκε:"),
                "",
                self._format_sync_report_line("Αποδεκτά", accepted, kind="positive"),
            ]
            if already_applied > 0:
                lines.append(f"↻ Ήδη εφαρμοσμένα: {already_applied}")
            if rejected > 0:
                lines.append(self._format_sync_report_line("Απορριφθέντα", rejected, kind="negative"))

            lines.extend(self._build_sync_file_summary_lines(sync_summary, max_files=6))

            snapshot = sync_result.get("snapshot")
            if snapshot:
                lines.extend(
                    [
                        "",
                        S["MESSAGES"].get(
                            "SYNC_BACKUP_CREATED",
                            "Δημιουργήθηκε αντίγραφο ασφαλείας.",
                        ),
                    ]
                )

            self._show_rich_sync_report(
                S["TITLES"].get("SYNC_NOTIFICATION", "Συγχρονισμός"),
                "\n".join(lines),
            )
        except Exception:
            logging.exception("Failed to show sync notification")

    def _build_sync_file_summary_lines(self, sync_summary, max_files=5):
        """Build compact per-file summary lines for sync popups."""
        summaries = (sync_summary or {}).get("file_summaries") or []
        if not summaries:
            return []

        lines = ["", S["MESSAGES"].get("SYNC_FILE_SUMMARY_TITLE", "Αρχεία αλλαγών:")]
        shown = 0
        for item in summaries:
            if shown >= max_files:
                break
            name = os.path.basename(str(item.get("source_file") or "-") or "-")
            accepted = int(item.get("accepted", 0) or 0)
            already_applied = int(item.get("already_applied", 0) or 0)
            conflicts = int(item.get("conflicts", 0) or 0)
            status = str(item.get("status") or "pending")
            table_counts = item.get("table_counts") or {}

            bits = [f"• {name}"]
            if accepted > 0:
                bits.append(f"+{accepted}")
            if already_applied > 0:
                bits.append(f"↻{already_applied}")
            if conflicts > 0:
                bits.append(f"⚠{conflicts}")
            if status == "rejected":
                bits.append("✖")

            if isinstance(table_counts, dict) and table_counts:
                top_tables = sorted(table_counts.items(), key=lambda kv: int(kv[1]), reverse=True)[:2]
                top_text = ", ".join(f"{tbl}:{cnt}" for tbl, cnt in top_tables)
                bits.append(top_text)

            lines.append(" | ".join(bits))
            shown += 1

        remaining = len(summaries) - shown
        if remaining > 0:
            lines.append(f"… +{remaining} αρχεία")
        return lines

    def _format_sync_report_line(self, label, value, kind="neutral"):
        """Return a sync report line with color emphasis for changed values."""
        if kind == "positive":
            color = "2e7d32"
        elif kind == "negative":
            color = "c62828"
        else:
            color = "1f1f1f"
        return f"{label}: [b][color={color}]{value}[/color][/b]"

    def _show_rich_sync_report(self, title, message):
        """Show sync report popup with markup support (bold + colored values)."""
        msg_len = len(message)
        if msg_len < 100:
            size_hint = (0.7, 0.3)
        elif msg_len < 220:
            size_hint = (0.85, 0.42)
        else:
            size_hint = (0.9, 0.58)

        popup = Popup(title=title, size_hint=size_hint)
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        scroll = ScrollView()
        msg_label = Label(text=message, size_hint_y=None, markup=True, halign="left", valign="top")
        msg_label.bind(
            width=lambda inst, val: setattr(inst, "text_size", (val, None)),
            texture_size=lambda inst, val: setattr(inst, "height", val[1] + 8),
        )
        scroll.add_widget(msg_label)
        layout.add_widget(scroll)

        close_btn = Button(text="OK", size_hint_y=0.15)
        close_btn.bind(on_press=popup.dismiss)
        layout.add_widget(close_btn)

        popup.content = layout
        popup.open()

    def _show_conflict_resolution(self, sync_result):
        """Show conflict resolution UI after sync detects conflicts."""
        try:
            from sync_service import resolve_sync_root
            from kivy.uix.boxlayout import BoxLayout
            from kivy.uix.gridlayout import GridLayout
            from kivy.uix.label import Label
            from kivy.uix.button import Button
            from kivy.uix.scrollview import ScrollView
            from kivy.uix.popup import Popup
            import json
            
            sync_root = resolve_sync_root(self.db_path)
            tracker_path = os.path.join(sync_root, "logs", ".processed_files.json")
            
            if not os.path.exists(tracker_path):
                return
            
            with open(tracker_path, "r", encoding="utf-8") as f:
                tracker = json.load(f)
            
            # Find unresolved conflicts
            conflicts = {}
            for filename, status_info in tracker.items():
                if status_info.get("status") == "conflict":
                    conflicts[filename] = status_info
            
            if not conflicts:
                return
            
            # Create popup UI
            content = BoxLayout(orientation='vertical', padding=10, spacing=10)
            
            # Title
            title_label = Label(
                text=f"{len(conflicts)} σύγκρουση(εις) ανιχνεύθηκαν",
                size_hint_y=0.15,
                bold=True
            )
            content.add_widget(title_label)
            
            # List conflicts
            scroll = ScrollView(size_hint=(1, 0.65))
            conflicts_list = GridLayout(cols=1, spacing=5, size_hint_y=None, padding=5)
            conflicts_list.bind(minimum_height=conflicts_list.setter('height'))
            
            for filename in conflicts.keys():
                row = Label(
                    text=f"{filename}",
                    size_hint_y=None,
                    height=40
                )
                conflicts_list.add_widget(row)
            
            scroll.add_widget(conflicts_list)
            content.add_widget(scroll)
            
            # Buttons
            buttons = BoxLayout(size_hint_y=0.2, spacing=10, padding=5)
            
            resolve_btn = Button(text="Επίλυση")
            close_btn = Button(text="Κλείσιμο")
            
            def on_resolve(_):
                popup.dismiss()
                self._show_conflict_resolver(conflicts)
            
            def on_close(_):
                popup.dismiss()
            
            resolve_btn.bind(on_press=on_resolve)
            close_btn.bind(on_press=on_close)
            buttons.add_widget(resolve_btn)
            buttons.add_widget(close_btn)
            content.add_widget(buttons)
            
            popup = Popup(
                title="Σύγκρουση Συγχρονισμού",
                content=content,
                size_hint=(0.9, 0.8)
            )
            popup.open()
        
        except Exception as e:
            logging.exception(f"Failed to show conflict resolution: {e}")

    def _show_conflict_resolver(self, conflicts):
        """Show resolver for first conflict."""
        try:
            from sync_service import resolve_sync_root
            from kivy.uix.boxlayout import BoxLayout
            from kivy.uix.label import Label
            from kivy.uix.button import Button
            from kivy.uix.popup import Popup
            import json
            
            # Get first conflict
            filename = list(conflicts.keys())[0]
            sync_root = resolve_sync_root(self.db_path)
            
            # Read the change file
            for folder in ["pending", os.path.join("processed", "accepted")]:
                change_path = os.path.join(sync_root, "inbox", folder, filename)
                if os.path.exists(change_path):
                    break
            
            if not os.path.exists(change_path):
                return
            
            # Parse the change
            changes = []
            with open(change_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        changes.append(json.loads(line))
            
            if not changes:
                return
            
            # Get conflicting record
            change = changes[0]
            table = change.get("table", "")
            record_id = change.get("data", {}).get("id", "")
            
            cur = self.conn.cursor()
            cur.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,))
            row = cur.fetchone()
            
            if not row:
                return
            
            cols = [col[0] for col in cur.description]
            my_data = dict(zip(cols, row))
            their_data = change.get("data", {})
            
            # Show comparison
            content = BoxLayout(orientation='vertical', padding=10, spacing=10)
            
            msg = f"Σύγκρουση in {table} (ID: {record_id})\n\n"
            msg += "Δικά μου δεδομένα:\n"
            for k, v in my_data.items():
                if k != "id":
                    msg += f"  {k}: {v}\n"
            msg += "\nΤα δεδομένα τους:\n"
            for k, v in their_data.items():
                if k != "id":
                    msg += f"  {k}: {v}\n"
            
            content.add_widget(Label(text=msg, size_hint_y=0.7))
            
            # Resolution buttons
            buttons = BoxLayout(size_hint_y=0.3, spacing=10)
            
            def keep_mine():
                # Just dismiss, don't apply their change
                self._mark_conflict_resolved(filename, "keep_mine")
                popup.dismiss()
                show_message_popup("Επίλυση", "Κρατήθηκαν τα δικά σας δεδομένα")
            
            def use_theirs():
                # Update with their data
                update_fields = {k: v for k, v in their_data.items() if k != "id" and k in cols}
                if update_fields:
                    set_clause = ", ".join([f"{k}=?" for k in update_fields.keys()])
                    sql = f"UPDATE {table} SET {set_clause} WHERE id=?"
                    self.conn.execute(sql, list(update_fields.values()) + [record_id])
                    self.conn.commit()
                self._mark_conflict_resolved(filename, "use_theirs")
                popup.dismiss()
                show_message_popup("Επίλυση", "Εφαρμόστηκαν τα δεδομένα τους")
            
            buttons.add_widget(Button(text="Δικά μου", on_press=lambda x: keep_mine()))
            buttons.add_widget(Button(text="Δικά τους", on_press=lambda x: use_theirs()))
            
            content.add_widget(buttons)
            
            popup = Popup(
                title=f"Επίλυση: {filename}",
                content=content,
                size_hint=(0.95, 0.85)
            )
            popup.open()
        
        except Exception as e:
            logging.exception(f"Failed to resolve conflict: {e}")

    def _mark_conflict_resolved(self, filename, resolution):
        """Mark a conflict as resolved and move file to appropriate folder.
        
        Args:
            filename: The conflict change file name
            resolution: Either "keep_mine" (→ conflicts folder) or "use_theirs" (→ accepted folder)
        """
        try:
            from sync_service import resolve_sync_root
            import json
            import shutil
            
            sync_root = resolve_sync_root(self.db_path)
            tracker_path = os.path.join(sync_root, "logs", ".processed_files.json")
            
            with open(tracker_path, "r", encoding="utf-8") as f:
                tracker = json.load(f)
            
            # Update tracker: mark as resolved
            if filename in tracker:
                tracker[filename]["resolution"] = resolution
                tracker[filename]["resolved_at"] = datetime.now().isoformat()
                tracker[filename]["status"] = "resolved"
            
            with open(tracker_path, "w", encoding="utf-8") as f:
                json.dump(tracker, f, ensure_ascii=False, indent=2)
            
            # Move file out of pending folder
            pending_path = os.path.join(sync_root, "inbox", "pending", filename)
            os.makedirs(os.path.join(sync_root, "inbox", "processed"), exist_ok=True)
            
            if os.path.exists(pending_path):
                if resolution == "keep_mine":
                    # Move to conflicts folder - keep for audit trail, don't reprocess
                    dest_dir = os.path.join(sync_root, "inbox", "processed", "conflicts")
                    os.makedirs(dest_dir, exist_ok=True)
                    dest_path = os.path.join(dest_dir, filename)
                    shutil.move(pending_path, dest_path)
                elif resolution == "use_theirs":
                    # Move to accepted folder - marks as processed for other users
                    dest_dir = os.path.join(sync_root, "inbox", "processed", "accepted")
                    os.makedirs(dest_dir, exist_ok=True)
                    dest_path = os.path.join(dest_dir, filename)
                    shutil.move(pending_path, dest_path)
        
        except Exception:
            logging.exception("Failed to mark conflict as resolved")

    def import_substations_from_file(self, file_path):
        def on_success(message):
            show_message_popup(
                S["TITLES"].get("IMPORT_SUBSTATIONS_TITLE", "Εισαγωγή Υποσταθμών"),
                message,
                callback=lambda: self.show_records(None),
            )

        def on_error(message):
            show_message_popup(S["TITLES"]["ERROR"], message)

        if file_path.endswith(".xlsx"):
            import_substations_from_excel(self.conn, file_path, on_success, on_error)
        elif file_path.endswith(".csv"):
            import_substations_from_csv(self.conn, file_path, on_success, on_error)
        else:
            on_error("Μη υποστηριζόμενη μορφή αρχείου")

    def _show_element_quick_view(self, element_id):
        """Show a small popup with the element's key details (read-only)."""
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label
        from kivy.uix.popup import Popup
        from kivy.uix.widget import Widget

        c = self.conn.cursor()
        c.execute(
            "SELECT e.name, e.element_type, e.serial_number, e.power_mva, e.manufacturer, e.manufacture_year, e.installation_space, e.maintenance_date, e.substation_id, em.power_mva AS model_power_mva, em.manual_pdf FROM elements e LEFT JOIN element_models em ON e.element_model_id = em.id WHERE e.id=?",
            (element_id,),
        )
        row = c.fetchone()
        if not row:
            show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"].get("ELEMENT_NOT_FOUND", "Το στοιχείο δεν βρέθηκε."))
            return

        (
            name,
            elem_type,
            serial_number,
            power_mva,
            manufacturer,
            manufacture_year,
            installation_space,
            maintenance_date,
            substation_id,
            model_power_mva,
            manual_pdf,
        ) = row

        # Check if transformer (150/20 kV)
        is_transformer = self._is_transformer(elem_type) if elem_type else False

        effective_power = model_power_mva if (model_power_mva is not None) else power_mva
        power_display = f"{effective_power} MVA" if effective_power else "-"
        lines = [
            f"Όνομα: {name}",
            f"Τύπος: {elem_type}",
            f"S/N: {serial_number or '-'}",
            f"Κατασκευαστής: {manufacturer or '-'} ({manufacture_year or '-'})",
            f"Χώρος: {installation_space or '-'}",
            f"Ισχύς: {power_display}",
            S["MESSAGES"].get("MAINT_LAST_LABEL", "Τελευταία Συντήρηση: {date}").format(date=maintenance_date or "-"),
        ]

        layout = BoxLayout(orientation="vertical", padding=10, spacing=8)
        for l in lines:
            layout.add_widget(Label(text=l, size_hint_y=None, height=28))

        btn_row = BoxLayout(size_hint_y=None, height=60, spacing=6)
        
        # Left side buttons
        left_buttons = BoxLayout(size_hint_x=0.55, spacing=6)
        
        # Add manual button if available
        if manual_pdf and os.path.exists(manual_pdf):
            manual_btn = Button(text=S["MESSAGES"].get("MANUAL_LABEL", "Manual"))
            manual_btn.bind(on_press=lambda x: self._open_model_manual(manual_pdf))
            left_buttons.add_widget(manual_btn)
        
        # Add DGA button for transformers
        if is_transformer:
            dga_btn = Button(text=S["MESSAGES"].get("DGA_LABEL", "Φυσικοχημικές/Αεριοχρωματογραφία"))
            dga_btn.bind(
                on_press=lambda x: self.show_element_dga_measurements(
                    element_id=element_id,
                    element_name=name,
                    substation_id=substation_id
                )
            )
            left_buttons.add_widget(dga_btn)
        
        btn_row.add_widget(left_buttons)
        
        # Spacer in the middle
        btn_row.add_widget(Widget())
        
        # Close button (right side)
        close_btn = Button(text=S["BUTTONS"]["CLOSE"], size_hint_x=0.15)

        def _close(_x):
            popup.dismiss()

        close_btn.bind(on_press=_close)
        btn_row.add_widget(close_btn)

        layout.add_widget(btn_row)

        popup = Popup(title=S["MESSAGES"].get("VIEW_ELEMENT_TITLE", "Προβολή Στοιχείου"), size_hint=(0.85, 0.6))
        popup.content = layout
        popup.open()

    def _read_elements_file(self, file_path):
        """Read elements file, handling TEMPLATE_VERSION row if present

        Returns:
            pd.DataFrame: The elements dataframe with proper headers

        Raises:
            ValueError: If file format is not supported
        """
        import pandas as pd

        if file_path.endswith(".xlsx"):
            # Peek at first row to check for version
            df_peek = pd.read_excel(
                file_path, sheet_name="Elements", nrows=1, header=None
            )
            first_cell = str(df_peek.iloc[0, 0]) if len(df_peek) > 0 else ""

            if "Version:" in first_cell or "TEMPLATE_VERSION:" in first_cell:
                return pd.read_excel(file_path, sheet_name="Elements", skiprows=1)
            else:
                return pd.read_excel(file_path, sheet_name="Elements")

        elif file_path.endswith(".csv"):
            # Peek at first row to check for version
            df_peek = pd.read_csv(file_path, nrows=1, header=None)
            first_cell = str(df_peek.iloc[0, 0]) if len(df_peek) > 0 else ""

            if "Version:" in first_cell or "TEMPLATE_VERSION:" in first_cell:
                return pd.read_csv(file_path, skiprows=1)
            else:
                return pd.read_csv(file_path)
        else:
            raise ValueError("Μη υποστηριζόμενη μορφή αρχείου")

    def _load_models_for_element_type(
        self, element_category, breaker_category=None, selected_model_id=None
    ):
        """Load and filter models for a specific element category

        Args:
            element_category: The element type (e.g., 'Διακόπτης ΜΤ')
            breaker_category: Optional breaker category filter for circuit breakers
            selected_model_id: Optional model ID to pre-select

        Returns:
            tuple: (models_data dict, display_names list, selected_display_name)
        """
        c = self.conn.cursor()
        c.execute(
            "SELECT id, model_name, manufacturer, maintenance_cycle, installation_space, breaker_category FROM element_models WHERE element_category=? ORDER BY model_name",
            (element_category,),
        )
        models = c.fetchall()

        models_data = {}
        display_names = []
        selected_display_name = None

        # Filter models for circuit breakers by breaker category
        if element_category in [self.ELEM_BREAKER_MT, self.ELEM_BREAKER_YT] and breaker_category:
            filtered_models = [
                m
                for m in models
                if (m[5] or "Other").strip().lower() == breaker_category.lower()
            ]
        else:
            filtered_models = models

        # Build display names and data dictionary
        for m in filtered_models:
            display_name = f"{m[1]} - {m[2] or 'N/A'}"
            display_names.append(display_name)
            models_data[display_name] = {
                "id": m[0],
                "model_name": m[1],
                "manufacturer": m[2] or "",
                "maintenance_cycle": m[3] or 0,
                "installation_space": m[4] or "",
                "breaker_category": m[5] or "",
            }
            if m[0] == selected_model_id:
                selected_display_name = display_name

        return models_data, display_names, selected_display_name

    def import_elements_from_file(self, file_path):
        """Import elements with validation wizard: Step 1 - Column Mapping, Step 2 - Data Validation"""
        try:
            df_elem = self._read_elements_file(file_path)

            # Show Step 1: Column Mapping Wizard
            column_wizard = ColumnMappingPopup(
                df_columns=list(df_elem.columns),
                df=df_elem,
                conn=self.conn,
                on_continue=lambda mapping: self._on_column_mapping_complete(
                    file_path, df_elem, mapping
                ),
                on_cancel=lambda: None,  # Just close
            )
            column_wizard.show()

        except Exception as e:
            show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"].get("ERROR_DURING_CHECK_PREFIX", "Σφάλμα κατά τον έλεγχο: ") + str(e))

    def _on_column_mapping_complete(self, file_path, df, column_mapping):
        """Callback after column mapping is complete - show validation wizard"""
        # Show Step 2: Data Validation Wizard
        validation_wizard = DataValidationPopup(
            df=df,
            column_mapping=column_mapping,
            conn=self.conn,
            on_continue=lambda corrected_df, mapping: self._on_validation_complete(
                file_path, corrected_df, mapping
            ),
            on_cancel=lambda: None,  # Just close
            on_back=lambda: self.import_elements_from_file(
                file_path
            ),  # Go back to step 1
        )
        validation_wizard.show()

    def _on_validation_complete(self, file_path, df, column_mapping):
        """Callback after validation is complete - proceed with traditional flow"""
        # Rename columns to match expected names
        reverse_mapping = {v: k for k, v in column_mapping.items()}
        df_renamed = df.rename(columns=reverse_mapping)

        # Save the corrected dataframe back to temporary file
        import tempfile

        import pandas as pd

        # Create a temporary file with corrected data
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".xlsx", delete=False, encoding="utf-8"
        ) as tmp_file:
            temp_path = tmp_file.name

        # Write corrected data
        with pd.ExcelWriter(temp_path, engine="openpyxl") as writer:
            df_renamed.to_excel(writer, sheet_name="Elements", index=False)

        # Now proceed with traditional flow (check substations, models, duplicates)
        self._check_substations_and_proceed(temp_path, original_file=file_path)

    def _check_substations_and_proceed(self, file_path, original_file=None):
        """Check for new substations after validation"""
        try:
            import pandas as pd

            cursor = self.conn.cursor()
            df_elem = self._read_elements_file(file_path)

            # Check for new substations
            new_substations = set()
            for _, row in df_elem.iterrows():
                sub_name = (
                    str(row.get("Substation Name", "")).strip()
                    if pd.notna(row.get("Substation Name", ""))
                    else ""
                )
                if sub_name:
                    cursor.execute(
                        "SELECT id FROM substations WHERE name=?", (sub_name,)
                    )
                    if not cursor.fetchone():
                        new_substations.add(sub_name)

            # If new substations found, prompt user
            if new_substations:
                self._show_new_substations_prompt(file_path, new_substations)
            else:
                # No new substations, proceed to check duplicates
                self._check_duplicates_and_import(file_path)

        except Exception as e:
            show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"].get("ERROR_DURING_CHECK_PREFIX", "Σφάλμα κατά τον έλεγχο: ") + str(e))

    def _show_new_substations_prompt(self, file_path, new_substations):
        """Prompt user to confirm creation of new substations"""
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label
        from kivy.uix.popup import Popup
        from kivy.uix.scrollview import ScrollView

        # Make the popup larger so long lists fit; list itself remains scrollable
        popup = Popup(title=S["MESSAGES"].get("NEW_SUBSTATIONS_TITLE", "Νέοι Υποσταθμοί Εντοπίστηκαν"), size_hint=(0.85, 0.8))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        sub_list = "\n".join(f"• {sub}" for sub in sorted(new_substations))
        # Brief header message only; the individual substations are shown in the scrollable list below
        message = S["MESSAGES"].get("MISSING_SUBSTATIONS_WILL_CREATE", "Οι παρακάτω υποσταθμοί δεν υπάρχουν και θα δημιουργηθούν:")

        from kivy.graphics import Color, Rectangle
        from kivy.uix.checkbox import CheckBox

        # Header and per-substation checkbox list so user can mark specific substations
        header = Label(text=S["MESSAGES"].get("SUBSTATION_IS_THESSALONIKI", "Θεσσαλονίκη"), size_hint_y=None, height=30, bold=True, color=(0.9, 0.1, 0.1, 1))
        # Brief header message (fixed height) — the list below stays scrollable
        header_label = Label(text=message, size_hint_y=None, height=60)
        header_label.bind(texture_size=header_label.setter("size"))
        layout.add_widget(header_label)

        # Header row above the list, right-aligned to match checkbox column
        header_row = BoxLayout(size_hint_y=None, height=36)
        header_row.add_widget(Widget())
        header.halign = "right"
        header.valign = "middle"
        header.size_hint_x = None
        header.width = 160
        header_row.add_widget(header)
        layout.add_widget(header_row)

        # Scrollable single-column list where each row contains name (left)
        # and a fixed-width checkbox area (right). Each row has a grey
        # background that becomes blue when selected.
        scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"], size_hint=(1, 0.7))
        list_container = GridLayout(cols=1, spacing=6, size_hint_y=None, padding=6)
        list_container.bind(minimum_height=list_container.setter("height"))

        self._new_sub_cb = {}
        for sub in sorted(new_substations):
            row = BoxLayout(size_hint_y=None, height=40, spacing=8)
            # Row background covering the whole row
            with row.canvas.before:
                row._bg_color = Color(0.95, 0.95, 0.95, 1)
                row._bg_rect = Rectangle(pos=row.pos, size=row.size)
            row.bind(pos=lambda inst, val: setattr(inst._bg_rect, 'pos', val))
            row.bind(size=lambda inst, val: setattr(inst._bg_rect, 'size', val))

            # Left: substation name
            lbl = Label(text=sub, halign="left", valign="middle")
            lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', (val[0], None)))
            # Right: fixed-width anchor for the checkbox so it aligns under header
            cb_anchor = AnchorLayout(anchor_x='right', anchor_y='center', size_hint_x=None, width=160)
            # Preselect Thessaloniki checkbox when the substation name
            # contains the substring "ΘΕΣΣ" (case-insensitive)
            is_th_initial = True if "ΘΕΣΣ" in sub.upper() else False
            cb = CheckBox(active=False, size_hint=(None, None), size=(40, 40))
            self._new_sub_cb[sub] = cb
            cb_anchor.add_widget(cb)

            # Toggle changes the entire row background (selection highlight)
            def _on_toggle(chk, val, r=row):
                if val:
                    r._bg_color.rgba = (0.2, 0.45, 0.8, 1)
                else:
                    r._bg_color.rgba = (0.95, 0.95, 0.95, 1)

            cb.bind(active=_on_toggle)
            # Ensure initial visual state matches preselection
            try:
                cb.active = is_th_initial
            except Exception:
                pass

            # Draw a green border around the checkbox itself (not the container)
            from kivy.graphics import Line
            with cb.canvas.after:
                cb._border_color = Color(0.0, 0.5, 0.0, 1)
                cb._border_line = Line(rectangle=(0, 0, 0, 0), width=2)

            def _update_border(_inst=None, _val=None, line=None, c=cb):
                try:
                    # rectangle expects (x, y, w, h)
                    cb._border_line.rectangle = (c.x - 4, c.y - 4, c.width + 8, c.height + 8)
                except Exception:
                    pass

            cb.bind(pos=_update_border, size=_update_border)
            _update_border()

            row.add_widget(lbl)
            row.add_widget(cb_anchor)
            list_container.add_widget(row)

        scroll.add_widget(list_container)
        layout.add_widget(scroll)

        # Buttons
        btn_layout = BoxLayout(size_hint_y=0.2, spacing=10)

        yes_btn = Button(text=f"{S['BUTTONS']['YES']}, Δημιουργία")
        def _on_yes(_):
            # Gather selected substations
            selected = [name for name, cb in getattr(self, '_new_sub_cb', {}).items() if cb.active]
            self._create_substations_and_continue(file_path, new_substations, popup, selected)
        yes_btn.bind(on_press=_on_yes)
        btn_layout.add_widget(yes_btn)

        no_btn = Button(text=S["BUTTONS"]["CANCEL"])
        no_btn.bind(on_press=popup.dismiss)
        btn_layout.add_widget(no_btn)

        layout.add_widget(btn_layout)
        popup.content = layout
        popup.open()

    def _create_substations_and_continue(
        self, file_path, new_substations, prompt_popup, selected_substations=None
    ):
        """Create new substations and continue with import"""
        cursor = self.conn.cursor()
        # Insert with is_thessaloniki if the column exists in this DB
        try:
            cursor.execute("PRAGMA table_info(substations)")
            sub_cols = [r[1] for r in cursor.fetchall()]
        except Exception:
            sub_cols = []

        for sub_name in new_substations:
            is_th = False
            try:
                is_th = bool(selected_substations and sub_name in selected_substations)
            except Exception:
                is_th = False

            if "is_thessaloniki" in sub_cols:
                try:
                    cursor.execute(
                        "INSERT INTO substations (name, is_thessaloniki) VALUES (?, ?)",
                        (sub_name, 1 if is_th else 0),
                    )
                except Exception:
                    cursor.execute(
                        "INSERT INTO substations (name) VALUES (?)", (sub_name,)
                    )
            else:
                cursor.execute("INSERT INTO substations (name) VALUES (?)", (sub_name,))
        self.conn.commit()
        prompt_popup.dismiss()

        # Now proceed to check duplicates
        self._check_duplicates_and_import(file_path)

    def _check_duplicates_and_import(self, file_path):
        """Check for models first, then duplicate elements, and proceed with import"""
        try:
            import pandas as pd

            cursor = self.conn.cursor()
            df_elem = self._read_elements_file(file_path)

            # First check models
            models_to_check = (
                {}
            )  # Key: (element_type, model_name, manufacturer), Value: {cycle, space}
            for _, row in df_elem.iterrows():
                element_type = (
                    str(row.get("Element Type", "")).strip()
                    if pd.notna(row.get("Element Type", ""))
                    else ""
                )
                model_name = (
                    str(row.get("Model Name", "")).strip()
                    if pd.notna(row.get("Model Name", ""))
                    else ""
                )
                model_manufacturer = (
                    str(row.get("Model Manufacturer", "")).strip()
                    if pd.notna(row.get("Model Manufacturer", ""))
                    else ""
                )
                model_cycle = (
                    int(row.get("Model Maintenance Cycle", 0))
                    if pd.notna(row.get("Model Maintenance Cycle", ""))
                    else 0
                )
                model_space = (
                    str(row.get("Model Installation Space", "")).strip()
                    if pd.notna(row.get("Model Installation Space", ""))
                    else ""
                )

                if model_name:  # Only check if model info provided
                    key = (element_type, model_name, model_manufacturer)
                    # Determine computed cycle for this row using substation flag
                    computed_cycle = None
                    try:
                        sub_name = (
                            str(row.get("Substation Name", "")).strip()
                            if pd.notna(row.get("Substation Name", ""))
                            else ""
                        )
                        # Lookup is_thessaloniki from DB (new substations have been created by now)
                        is_th = False
                        if sub_name:
                            cursor.execute(
                                "SELECT is_thessaloniki FROM substations WHERE name=?",
                                (sub_name,),
                            )
                            r = cursor.fetchone()
                            is_th = bool(r[0]) if r and r[0] else False

                        # breaker type from row
                        breaker_type = (
                            str(row.get("Τύπος Διακόπτη", "")).strip()
                            if pd.notna(row.get("Τύπος Διακόπτη", ""))
                            else ""
                        )

                        et = str(element_type) if pd.notna(element_type) else ""
                        # Compute maintenance cycle in years
                        if "ΥΤ" in et or "150/20" in et or "Transformer" in et:
                            computed_cycle = 3 if is_th else 6
                        elif "ΜΤ" in et or "20/0.4" in et:
                            bt = (breaker_type or "").strip().lower()
                            inst_space_l = (model_space or "").strip().lower()
                            # MV SF6: inside => 1 year, outside => 3 years
                            if bt in ["πτωχού ελαίου", "sf6", "sf-6"] or "sf6" in bt:
                                if inst_space_l and ("εξωτερ" in inst_space_l or "outside" in inst_space_l):
                                    computed_cycle = 3
                                else:
                                    computed_cycle = 1
                            elif bt in ["κενού", "ελαίου"]:
                                computed_cycle = 3
                            else:
                                computed_cycle = 3
                        else:
                            computed_cycle = 6
                    except Exception:
                        computed_cycle = None

                    if key not in models_to_check:
                        # Normalize breaker category for model grouping (if present)
                        try:
                            breaker_type_raw = (
                                str(row.get("Τύπος Διακόπτη", "")).strip()
                                if pd.notna(row.get("Τύπος Διακόπτη", ""))
                                else ""
                            )
                        except Exception:
                            breaker_type_raw = ""
                        normalized_bc = None
                        try:
                            from import_validator import \
                                validate_breaker_category

                            if breaker_type_raw:
                                match = validate_breaker_category(breaker_type_raw)
                                normalized_bc = match[0] if match and match[0] else None
                        except Exception:
                            normalized_bc = breaker_type_raw or None

                        models_to_check[key] = {
                            "cycle": model_cycle,
                            "space": model_space,
                            "computed": computed_cycle,
                            "breaker_category": normalized_bc,
                        }

            # Check which models exist and which need to be added/updated
            new_models = []
            conflicting_models = []

            for (
                elem_type,
                model_name,
                manufacturer,
            ), model_data in models_to_check.items():
                cursor.execute(
                    "SELECT id, maintenance_cycle, installation_space FROM element_models WHERE element_category=? AND model_name=? AND manufacturer=?",
                    (elem_type, model_name, manufacturer),
                )
                existing = cursor.fetchone()

                if existing:
                    existing_id, existing_cycle, existing_space = existing
                    # Check if data differs
                    if existing_cycle != model_data["cycle"] or (
                        existing_space or ""
                    ) != (model_data["space"] or ""):
                        conflicting_models.append(
                            {
                                "category": elem_type,
                                "name": model_name,
                                "manufacturer": manufacturer,
                                "existing": {
                                    "cycle": existing_cycle,
                                    "space": existing_space,
                                },
                                "new": model_data,
                            }
                        )
                else:
                    new_models.append(
                        {
                            "category": elem_type,
                            "name": model_name,
                            "manufacturer": manufacturer,
                            "data": model_data,
                        }
                    )

            # If there are model issues, prompt user
            if new_models or conflicting_models:
                self._show_model_check_popup(file_path, new_models, conflicting_models)
            else:
                # No model issues, proceed to check element duplicates
                self._check_element_duplicates(file_path)

        except Exception as e:
            show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"].get("ERROR_DURING_CHECK_PREFIX", "Σφάλμα κατά τον έλεγχο: ") + str(e))

    def _show_model_check_popup(self, file_path, new_models, conflicting_models):
        """Show popup for user to review and approve model changes"""
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.gridlayout import GridLayout
        from kivy.uix.label import Label
        from kivy.uix.popup import Popup
        from kivy.uix.scrollview import ScrollView

        popup = Popup(title=S["MESSAGES"].get("MODEL_CHECK_TITLE", "Έλεγχος Μοντέλων"), size_hint=(0.85, 0.85))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
        content = GridLayout(cols=1, spacing=10, size_hint_y=None, padding=10)
        content.bind(minimum_height=content.setter("height"))

        if new_models:
            content.add_widget(
                Label(
                    text=S["MESSAGES"]["NEW_MODELS_HEADER"],
                    size_hint_y=None,
                    height=30,
                    markup=True,
                )
            )
            for model in new_models:
                model_cycle = model['data'].get('cycle', 0)
                computed = model['data'].get('computed')
                model_display = f"{model_cycle} έτη" if model_cycle and model_cycle > 0 else "Αυτόματος"
                computed_display = f"{computed} έτη" if computed and computed > 0 else "Αυτόματος"
                text = (
                    f"• {model['category']} - {model['name']} ({model['manufacturer']})\n"
                    f"  Κύκλος (μοντέλου): {model_display} | Κύκλος (υπολογισμένος): {computed_display}, Χώρος: {model['data']['space'] or 'N/A'}"
                )
                content.add_widget(Label(text=text, size_hint_y=None, height=60))

        if conflicting_models:
            content.add_widget(
                Label(
                    text=S["MESSAGES"]["EXISTING_MODELS_DIFF_HEADER"],
                    size_hint_y=None,
                    height=30,
                    markup=True,
                    color=(1, 0.5, 0, 1),
                )
            )
            for model in conflicting_models:
                existing_cycle = model['existing'].get('cycle', 0)
                new_cycle = model['new'].get('cycle', 0)
                existing_display = f"{existing_cycle} έτη" if existing_cycle and existing_cycle > 0 else "Αυτόματος"
                new_display = f"{new_cycle} έτη" if new_cycle and new_cycle > 0 else "Αυτόματος"
                computed = model.get('computed') or model['new'].get('computed') or model['existing'].get('computed')
                computed_display = f"{computed} έτη" if computed and computed > 0 else "Αυτόματος"
                text = (
                    f"• {model['category']} - {model['name']} ({model['manufacturer']})\n"
                    f"  Υπάρχον: Κύκλος {existing_display}, Χώρος {model['existing']['space'] or 'N/A'}\n"
                    f"  Νέο: Κύκλος {new_display}, Χώρος {model['new']['space'] or 'N/A'}\n"
                    f"  Κύκλος (υπολογισμένος): {computed_display}"
                )
                content.add_widget(Label(text=text, size_hint_y=None, height=90, color=(1, 0.7, 0, 1)))

        scroll.add_widget(content)
        layout.add_widget(scroll)

        # Instructions
        if conflicting_models:
            layout.add_widget(
                Label(
                    text='Επιλέξτε "Ενημέρωση" για να αντικαταστήσετε τα υπάρχοντα δεδομένα ή "Χρήση Υπαρχόντων" για να τα κρατήσετε.',
                    size_hint_y=0.1,
                )
            )

        # Buttons
        btn_layout = BoxLayout(size_hint_y=0.1, spacing=10)

        if conflicting_models:
            update_btn = Button(text=S["MESSAGES"].get("MODELS_UPDATE_BTN", "Ενημέρωση Μοντέλων"))
            update_btn.bind(
                on_press=lambda x: self._apply_models_and_continue(
                    file_path, new_models, conflicting_models, True, popup
                )
            )
            btn_layout.add_widget(update_btn)

            keep_btn = Button(text=S["MESSAGES"].get("MODELS_USE_EXISTING_BTN", "Χρήση Υπαρχόντων"))
            keep_btn.bind(
                on_press=lambda x: self._apply_models_and_continue(
                    file_path, new_models, conflicting_models, False, popup
                )
            )
            btn_layout.add_widget(keep_btn)
        else:
            continue_btn = Button(text=S["MESSAGES"].get("CONTINUE", "Συνέχεια"))
            continue_btn.bind(
                on_press=lambda x: self._apply_models_and_continue(
                    file_path, new_models, [], False, popup
                )
            )
            btn_layout.add_widget(continue_btn)

        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
        cancel_btn.bind(on_press=popup.dismiss)
        btn_layout.add_widget(cancel_btn)

        layout.add_widget(btn_layout)
        popup.content = layout
        popup.open()

    def _apply_models_and_continue(
        self, file_path, new_models, conflicting_models, update_conflicts, prompt_popup
    ):
        """Apply model changes and continue with element import"""
        cursor = self.conn.cursor()

        # Detect available columns in element_models so we can include breaker_category when present
        try:
            cursor.execute("PRAGMA table_info(element_models)")
            em_cols = [r[1] for r in cursor.fetchall()]
        except Exception:
            em_cols = []

        # Add new models
        for model in new_models:
            if "breaker_category" in em_cols:
                # Transformer models always have a model maintenance cycle of 6 years.
                is_transformer = False
                try:
                    cat = model.get("category") or ""
                    if isinstance(cat, str):
                        is_transformer = (
                            "ΥΤ" in cat or "150/20" in cat or "Transformer" in cat or "Μετασχηματιστής" in cat or cat.startswith("Μ/Σ")
                        )
                except Exception:
                    is_transformer = False

                # Prefer explicit model cycle if provided (>0), otherwise use computed cycle;
                # but if this is a transformer model, the model cycle is forced to 6.
                mcycle = None
                try:
                    if is_transformer:
                        mcycle = 6
                    else:
                        raw_cycle = model.get("data", {}).get("cycle")
                        computed = model.get("data", {}).get("computed")
                        if raw_cycle and int(raw_cycle) > 0:
                            mcycle = int(raw_cycle)
                        elif computed and int(computed) > 0:
                            mcycle = int(computed)
                except Exception:
                    mcycle = None

                cursor.execute(
                    "INSERT INTO element_models (element_category, model_name, manufacturer, maintenance_cycle, installation_space, breaker_category) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        model["category"],
                        model["name"],
                        model["manufacturer"],
                        mcycle,
                        model["data"]["space"],
                        model["data"].get("breaker_category") if model.get("data") else None,
                    ),
                )
            else:
                # When breaker_category column is absent, behave similarly but without breaker info
                is_transformer = False
                try:
                    cat = model.get("category") or ""
                    if isinstance(cat, str):
                        is_transformer = (
                            "ΥΤ" in cat or "150/20" in cat or "Transformer" in cat or "Μετασχηματιστής" in cat or cat.startswith("Μ/Σ")
                        )
                except Exception:
                    is_transformer = False

                mcycle = None
                try:
                    if is_transformer:
                        mcycle = 6
                    else:
                        raw_cycle = model.get("data", {}).get("cycle")
                        computed = model.get("data", {}).get("computed")
                        if raw_cycle and int(raw_cycle) > 0:
                            mcycle = int(raw_cycle)
                        elif computed and int(computed) > 0:
                            mcycle = int(computed)
                except Exception:
                    mcycle = None

                cursor.execute(
                    "INSERT INTO element_models (element_category, model_name, manufacturer, maintenance_cycle, installation_space) VALUES (?, ?, ?, ?, ?)",
                    (
                        model["category"],
                        model["name"],
                        model["manufacturer"],
                        mcycle,
                        model["data"]["space"],
                    ),
                )

        # Update conflicting models if user chose to
        if update_conflicts:
            for model in conflicting_models:
                if "breaker_category" in em_cols:
                    # Transformer models always use a 6-year model cycle; otherwise prefer explicit or computed
                    is_transformer = False
                    try:
                        cat = model.get("category") or ""
                        if isinstance(cat, str):
                            is_transformer = (
                                "ΥΤ" in cat or "150/20" in cat or "Transformer" in cat or "Μετασχηματιστής" in cat or cat.startswith("Μ/Σ")
                            )
                    except Exception:
                        is_transformer = False

                    mcycle = None
                    try:
                        if is_transformer:
                            mcycle = 6
                        else:
                            raw_cycle = model.get("new", {}).get("cycle")
                            computed = model.get("new", {}).get("computed")
                            if raw_cycle and int(raw_cycle) > 0:
                                mcycle = int(raw_cycle)
                            elif computed and int(computed) > 0:
                                mcycle = int(computed)
                    except Exception:
                        mcycle = None

                    cursor.execute(
                        "UPDATE element_models SET maintenance_cycle=?, installation_space=?, breaker_category=? WHERE element_category=? AND model_name=? AND manufacturer=?",
                        (
                            mcycle,
                            model["new"]["space"],
                            model.get("new", {}).get("breaker_category"),
                            model["category"],
                            model["name"],
                            model["manufacturer"],
                        ),
                    )
                else:
                    # No breaker_category column: still enforce transformer model cycle 6 when applicable
                    is_transformer = False
                    try:
                        cat = model.get("category") or ""
                        if isinstance(cat, str):
                            is_transformer = (
                                "ΥΤ" in cat or "150/20" in cat or "Transformer" in cat or "Μετασχηματιστής" in cat or cat.startswith("Μ/Σ")
                            )
                    except Exception:
                        is_transformer = False

                    if is_transformer:
                        mcycle = 6
                    else:
                        mcycle = model.get("new", {}).get("cycle")

                    cursor.execute(
                        "UPDATE element_models SET maintenance_cycle=?, installation_space=? WHERE element_category=? AND model_name=? AND manufacturer=?",
                        (
                            mcycle,
                            model["new"]["space"],
                            model["category"],
                            model["name"],
                            model["manufacturer"],
                        ),
                    )

        self.conn.commit()
        prompt_popup.dismiss()

        # Now check element duplicates
        self._check_element_duplicates(file_path)

    def _check_element_duplicates(self, file_path):
        """Check for duplicate elements after models are handled"""
        try:
            import pandas as pd

            cursor = self.conn.cursor()
            df_elem = self._read_elements_file(file_path)

            duplicates = []  # list of tuples (sub_name, name, serial)
            for _, row in df_elem.iterrows():
                sub_name = row.get("Substation Name", "")
                name = str(row.get("Name", "")) if pd.notna(row.get("Name", "")) else ""
                serial_number = (
                    str(row.get("Serial Number", ""))
                    if pd.notna(row.get("Serial Number", ""))
                    else ""
                ).strip()

                if sub_name and name:
                    cursor.execute(
                        "SELECT id FROM substations WHERE name=?", (str(sub_name),)
                    )
                    result = cursor.fetchone()
                    if result:
                        sub_id = result[0]
                        cursor.execute(
                            "SELECT id FROM elements WHERE substation_id=? AND name=? AND serial_number=?",
                            (sub_id, name, serial_number),
                        )
                        if cursor.fetchone():
                            duplicates.append((str(sub_name), name, serial_number))

            if duplicates:
                self._show_duplicate_choice_popup(file_path, duplicates)
            else:
                self._proceed_with_import(file_path, default_choice=None, decisions={})

        except Exception as e:
            show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"].get("ERROR_DURING_CHECK_PREFIX", "Σφάλμα κατά τον έλεγχο: ") + str(e))

    def _show_duplicate_choice_popup(self, file_path, duplicates_list):
        # User chooses per-duplicate replace/skip, plus replace-all / skip-all shortcuts
        popup = Popup(title=S["MESSAGES"].get("DUPLICATE_ELEMENTS_TITLE", "Διπλότυπα Στοιχεία Εντοπίστηκαν"), size_hint=(0.9, 0.85))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        instructions = Label(
            text='Επιλέξτε για κάθε διπλότυπο αν θα αντικατασταθεί ή θα παραλειφθεί.\nΜπορείτε να επιλέξετε "Αντικατάσταση Όλων" ή "Παράλειψη Όλων".',
            size_hint_y=None,
            height=60,
        )
        layout.add_widget(instructions)

        # State
        decisions = {}  # key: (sub_name, name, serial) -> True/False
        default_choice = {"value": None}  # True replace all, False skip all
        manual_choice_made = {"value": False}  # track if any per-item choice occurred

        # Scrollable list
        scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
        grid = GridLayout(cols=1, spacing=6, size_hint_y=None)
        grid.bind(minimum_height=grid.setter("height"))

        def update_continue_state():
            # Enable continue only if all decisions made or default chosen
            if default_choice["value"] is not None:
                continue_btn.disabled = False
                return
            continue_btn.disabled = len(decisions) < len(duplicates_list)

        def disable_global_buttons():
            btn_replace_all.disabled = True
            btn_skip_all.disabled = True

        def make_row(sub_name, name, serial):
            row = BoxLayout(size_hint_y=None, height=50, spacing=8)
            label_text = f"{name} (S/N: {serial or '-'}), Υποστ.: {sub_name}"
            row.add_widget(Label(text=label_text, size_hint_x=0.6))

            key = (sub_name, name, serial)

            def set_decision(val, btn_replace, btn_skip):
                decisions[key] = val
                manual_choice_made["value"] = True
                # Gray out both buttons after selection and color to show choice
                btn_replace.disabled = True
                btn_skip.disabled = True
                if val:
                    btn_replace.background_color = (0.6, 1, 0.6, 1)  # light green
                    btn_skip.background_color = (0.7, 0.7, 0.7, 1)
                else:
                    btn_skip.background_color = (1, 0.6, 0.6, 1)  # light red
                    btn_replace.background_color = (0.7, 0.7, 0.7, 1)
                disable_global_buttons()
                update_continue_state()

            replace_btn = Button(text=S["BUTTONS"]["REPLACE"], size_hint_x=0.2)
            skip_btn = Button(text=S["BUTTONS"]["SKIP"], size_hint_x=0.2)
            replace_btn.bind(
                on_press=lambda _x, br=replace_btn, bs=skip_btn: set_decision(
                    True, br, bs
                )
            )
            skip_btn.bind(
                on_press=lambda _x, br=replace_btn, bs=skip_btn: set_decision(
                    False, br, bs
                )
            )

            row.add_widget(replace_btn)
            row.add_widget(skip_btn)
            return row

        for sub_name, name, serial in duplicates_list:
            grid.add_widget(make_row(sub_name, name, serial))

        scroll.add_widget(grid)
        layout.add_widget(scroll)

        # Global buttons
        buttons_all = BoxLayout(size_hint_y=None, height=50, spacing=10)

        def choose_all(val):
            default_choice["value"] = val
            # set all decisions too
            for tup in duplicates_list:
                decisions[tup] = val
            # Gray out all buttons visually by disabling continue gating
            update_continue_state()
            # disable global buttons once used
            btn_replace_all.disabled = True
            btn_skip_all.disabled = True

        btn_replace_all = Button(text=S["BUTTONS"]["REPLACE_ALL"])
        btn_replace_all.bind(on_press=lambda _x: choose_all(True))
        buttons_all.add_widget(btn_replace_all)

        btn_skip_all = Button(text=S["BUTTONS"]["SKIP_ALL"])
        btn_skip_all.bind(on_press=lambda _x: choose_all(False))
        buttons_all.add_widget(btn_skip_all)

        layout.add_widget(buttons_all)

        # Action buttons
        actions = BoxLayout(size_hint_y=None, height=50, spacing=10)

        def on_continue(_x):
            if default_choice["value"] is None and len(decisions) < len(
                duplicates_list
            ):
                show_message_popup(
                    S["TITLES"]["ERROR"],
                    S["MESSAGES"].get("DUPLICATE_OPTIONS_INCOMPLETE", 'Ολοκληρώστε τις επιλογές για όλα τα διπλότυπα ή χρησιμοποιήστε "Αντικατάσταση Όλων" / "Παράλειψη Όλων".'),
                )
                return
            popup.dismiss()
            self._proceed_with_import(
                file_path, default_choice=default_choice["value"], decisions=decisions
            )

        def on_cancel(_x):
            popup.dismiss()

        continue_btn = Button(text=S["MESSAGES"].get("CONTINUE", "Συνέχεια"), disabled=True)
        continue_btn.bind(on_press=on_continue)
        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
        cancel_btn.bind(on_press=on_cancel)

        actions.add_widget(continue_btn)
        actions.add_widget(cancel_btn)
        layout.add_widget(actions)

        popup.content = layout
        popup.open()

        # Initial state
        update_continue_state()

    def _proceed_with_import(self, file_path, default_choice=None, decisions=None):
        decisions = decisions or {}

        def on_success(message):
            show_message_popup(
                "Εισαγωγή Στοιχείων", message, callback=lambda: self.show_records(None)
            )

        def on_error(message):
            show_message_popup(S["TITLES"]["ERROR"], message)

        # Resolver passed to importer per duplicate
        def on_duplicate(sub_name, name, serial_number):
            key = (sub_name, name, serial_number)
            if key in decisions:
                return decisions[key]
            if default_choice is not None:
                return default_choice
            return False  # safe default

        if file_path.endswith(".xlsx"):
            import_elements_from_excel(
                self.conn, file_path, on_success, on_error, on_duplicate
            )
        elif file_path.endswith(".csv"):
            import_elements_from_csv(
                self.conn, file_path, on_success, on_error, on_duplicate
            )
        else:
            on_error("Μη υποστηριζόμενη μορφή αρχείου")

    def show_edit_element_popup(
        self,
        element_id,
        substation_id,
        parent_popup,
        substation_name=None,
        grandparent_popup=None,
    ):
        from elements import show_edit_element_popup as _f
        return _f(self, element_id, substation_id, parent_popup, substation_name, grandparent_popup)

    def confirm_delete_element(
        self,
        element_id,
        element_name,
        substation_id,
        parent_popup,
        substation_name=None,
    ):
        from elements import confirm_delete_element as _f
        return _f(self, element_id, element_name, substation_id, parent_popup, substation_name)

    def delete_element(
        self, element_id, substation_id, parent_popup, substation_name=None
    ):
        from elements import delete_element as _f
        return _f(self, element_id, substation_id, parent_popup, substation_name)

    def show_inactive_elements(self, substation_id, substation_name, parent_popup):
        from elements import show_inactive_elements as _f
        return _f(self, substation_id, substation_name, parent_popup)

    def show_element_maintenance_history(self, element_id, element_name, parent_popup):
        from elements import show_element_maintenance_history as _f
        return _f(self, element_id, element_name, parent_popup)

    def _get_popup_scroll_y(self, popup):
        """Return the first ScrollView.scroll_y found inside popup.content or None."""
        def _find_scroll(widget):
            from kivy.uix.scrollview import ScrollView

            if isinstance(widget, ScrollView):
                return widget.scroll_y
            for child in getattr(widget, "children", []):
                res = _find_scroll(child)
                if res is not None:
                    return res
            return None

        if not popup or not hasattr(popup, "content"):
            return None
        return _find_scroll(popup.content)

    def confirm_delete_substation(self, substation_id, substation_name, parent_popup):
        """Confirm before deleting a substation and its elements."""
        from reports import show_confirm

        def confirm():
            self.delete_substation(substation_id, parent_popup)

        show_confirm(
            "Επιβεβαίωση Διαγραφής",
            S["MESSAGES"].get("CONFIRM_DELETE_SUBSTATION_FMT", f'Είστε σίγουροι ότι θέλετε να διαγράψετε\nτον υποσταθμό "{substation_name}"\nκαι ΟΛΑ τα στοιχεία του;'),
            yes_callback=confirm,
            yes_color=(1, 0, 0, 1),
            yes_text="ΝΑΙ",
            no_text="ΟΧΙ",
        )

    def delete_substation(self, substation_id, parent_popup):
        c = self.conn.cursor()
        # First, delete maintenance records related to this substation (and their children)
        c.execute("SELECT id FROM maintenance WHERE substation_id=?", (substation_id,))
        maintenance_ids = [r[0] for r in c.fetchall()]
        if maintenance_ids:
            for mid in maintenance_ids:
                try:
                    delete_maintenance_folders(self.conn, mid)
                except Exception:
                    pass
            placeholders = ",".join(["?"] * len(maintenance_ids))
            # Delete maintenance_elements and maintenance_people for those maintenance ids
            c.execute(f"DELETE FROM maintenance_elements WHERE maintenance_id IN ({placeholders})", maintenance_ids)
            c.execute(f"DELETE FROM maintenance_people WHERE maintenance_id IN ({placeholders})", maintenance_ids)
            # Delete maintenance records
            c.execute(f"DELETE FROM maintenance WHERE id IN ({placeholders})", maintenance_ids)

        # Delete all elements for this substation
        c.execute("DELETE FROM elements WHERE substation_id=?", (substation_id,))
        # Then delete the substation
        c.execute("DELETE FROM substations WHERE id=?", (substation_id,))
        self.conn.commit()
        # Try to preserve scroll position in the listing popup
        prev_scroll = None
        try:
            prev_scroll = self._get_popup_scroll_y(parent_popup)
        except Exception:
            prev_scroll = None

        # Refresh in-place using the same popup so scroll position can be restored
        self._display_substations(None, reuse_popup=parent_popup, prev_scroll_y=prev_scroll)
        show_message_popup(
            "Ολοκληρώθηκε",
            "Ο υποσταθμός και όλα τα στοιχεία του διαγράφηκαν!",
        )

    def show_edit_substation_popup(
        self,
        substation_id,
        substation_name,
        location,
        adoption_date,
        division,
        parent_popup,
    ):
        # Create popup
        popup = Popup(
            title=f"Επεξεργασία Υποσταθμού: {substation_name}", size_hint=(0.8, 0.7)
        )
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        # Division spinner
        division_spinner = Spinner(
            text=division or "ΤΜΘ", values=["ΤΜΘ"], size_hint_y=0.15
        )
        layout.add_widget(Label(text="Τομέας:", size_hint_y=0.08))
        layout.add_widget(division_spinner)

        # Location input
        location_input = TextInput(
            text=location or "",
            hint_text="Τοποθεσία (Google Maps link)",
            size_hint_y=0.15,
            multiline=False,
        )
        layout.add_widget(Label(text="Τοποθεσία:", size_hint_y=0.08))
        layout.add_widget(location_input)

        # Adoption date input
        date_input = TextInput(
            text=adoption_date or "",
            hint_text="Ημερομηνία Ανάληψης (YYYY-MM-DD)",
            size_hint_y=0.2,
            multiline=False,
        )
        layout.add_widget(Label(text="Ανάληψη:", size_hint_y=0.1))
        layout.add_widget(date_input)

        # Buttons layout
        buttons_layout = BoxLayout(size_hint_y=0.2, spacing=10)

        def save_changes():
            c = self.conn.cursor()
            c.execute(
                "UPDATE substations SET location=?, adoption_date=?, division=? WHERE id=?",
                (
                    location_input.text,
                    date_input.text,
                    division_spinner.text,
                    substation_id,
                ),
            )
            self.conn.commit()
            popup.dismiss()
            parent_popup.dismiss()
            show_message_popup(
                "Ολοκληρώθηκε",
                "Υποσταθμός ενημερώθηκε!",
                callback=lambda: self.show_records(None),
            )

        save_btn = Button(text=S["BUTTONS"]["SAVE"])
        save_btn.bind(on_press=lambda x: save_changes())
        buttons_layout.add_widget(save_btn)

        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
        cancel_btn.bind(on_press=popup.dismiss)
        buttons_layout.add_widget(cancel_btn)

        layout.add_widget(buttons_layout)
        popup.content = layout
        popup.open()

    def show_add_element_popup(self, instance):
        from elements import show_add_element_popup as _f
        return _f(self, instance)
    

    def show_add_element_popup_for_substation(
        self, substation_id, substation_name, parent_popup
    ):
        from elements import show_add_element_popup_for_substation as _f
        return _f(self, substation_id, substation_name, parent_popup)

    def _show_dga_maintenance_form(self, parent_popup=None, preselected_substation_id=None):
        """Show simplified DGA maintenance form: select substation -> transformer -> show DGA popup"""
        # Dismiss parent popup if provided
        if parent_popup:
            parent_popup.dismiss()
        
        c = self.conn.cursor()
        c.execute("SELECT id, name FROM substations ORDER BY name")
        substations = c.fetchall()
        
        if not substations:
            show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"].get("NO_SUBSTATIONS", "Δεν υπάρχουν υποσταθμοί!"))
            return
        
        # If preselected_substation_id is provided, find and select it
        default_substation_name = substations[0][1]
        if preselected_substation_id:
            for sub_id, sub_name in substations:
                if sub_id == preselected_substation_id:
                    default_substation_name = sub_name
                    break
        
        popup = Popup(
            title=S["MESSAGES"].get("DGA_MAINT_FORM_TITLE", "Record DGA Measurement"),
            size_hint=(0.8, 0.7),
        )
        main_layout = BoxLayout(orientation="vertical", padding=15, spacing=15)

        substation_map = {s[1]: s[0] for s in substations}
        selected_substation = {"name": default_substation_name}

        # Matrix-style substation selection (same pattern as other menus)
        main_layout.add_widget(
            Label(text=S["MESSAGES"].get("SUBSTATION_LABEL", "Substation:"), size_hint_y=None, height=30)
        )
        substation_row = BoxLayout(size_hint_y=None, height=44, spacing=8)
        selected_substation_label = Label(text=selected_substation["name"], halign="left", valign="middle")
        selected_substation_label.bind(
            size=lambda instance, value: setattr(instance, "text_size", (value[0], value[1]))
        )

        select_substation_btn = Button(
            text=S["MESSAGES"].get("SELECT_SUBSTATION_BTN", "Επιλογή Υποσταθμού"),
            size_hint_x=0.4,
        )

        substation_row.add_widget(selected_substation_label)
        substation_row.add_widget(select_substation_btn)
        main_layout.add_widget(substation_row)
        
        # Transformer selection
        main_layout.add_widget(
            Label(text=S["MESSAGES"].get("TRANSFORMER_LABEL", "Transformer:"), size_hint_y=None, height=30)
        )
        transformer_spinner = Spinner(
            text="",
            values=[],
            size_hint_y=None,
            height=40
        )
        main_layout.add_widget(transformer_spinner)
        
        def load_transformers(sub_name):
            """Load transformers for selected substation"""
            sub_id = substation_map.get(sub_name)
            if not sub_id:
                transformer_spinner.values = []
                transformer_spinner.text = ""
                return
            
            c.execute(
                """SELECT id, name, serial_number, gate 
                   FROM elements 
                   WHERE substation_id=? AND element_type LIKE '%150/20%'
                   ORDER BY name""",
                (sub_id,)
            )
            transformers = c.fetchall()
            if transformers:
                transformer_spinner.values = [f"{t[1]} (S/N: {t[2] or '-'}, Gate: {t[3] or '-'})" for t in transformers]
                transformer_spinner.text = transformer_spinner.values[0]
                # Store transformer data
                transformer_spinner.transformer_data = [(t[0], t[1], t[2], t[3], sub_id, sub_name) for t in transformers]
            else:
                transformer_spinner.values = []
                transformer_spinner.text = ""
                transformer_spinner.transformer_data = []

        def on_substation_selected(sub_name):
            selected_substation["name"] = sub_name
            selected_substation_label.text = sub_name
            load_transformers(sub_name)

        select_substation_btn.bind(
            on_press=lambda _x: self._show_substation_selection_window_with_callback(
                popup,
                substations,
                on_substation_selected,
                title=S["MESSAGES"].get("SELECT_SUBSTATION_BTN", "Επιλογή Υποσταθμού"),
            )
        )

        # Initialize transformer list from preselected substation
        load_transformers(selected_substation["name"])
        
        # Buttons
        btn_layout = BoxLayout(size_hint_y=None, height=50, spacing=10)
        
        proceed_btn = Button(text=S["MESSAGES"].get("DGA_START_BUTTON", "Start DGA"), size_hint_x=0.5)
        def on_proceed(_x):
            if not transformer_spinner.text:
                show_message_popup(
                    S["TITLES"]["ERROR"],
                    S["MESSAGES"].get("DGA_SELECT_TRANSFORMER_REQUIRED", "Please select a transformer"),
                )
                return
            
            # Get selected transformer data
            idx = transformer_spinner.values.index(transformer_spinner.text)
            elem_id, elem_name, serial_num, gate_val, sub_id, sub_name = transformer_spinner.transformer_data[idx]
            
            # Create a DGA maintenance record
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            maintenance_name = S["MESSAGES"].get(
                "DGA_MAINT_NAME_FMT", "DGA - {element_name} ({date})"
            ).format(element_name=elem_name, date=now_str.split()[0])
            
            c.execute(
                """INSERT INTO maintenance 
                   (substation_id, name, date_time, overall_comments, maintenance_type, user_name)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (sub_id, maintenance_name, now_str, "", S["MESSAGES"].get("DGA_LABEL", "Physicochemical/Gas Chromatography"), "")
            )
            maint_id = c.lastrowid
            self.conn.commit()
            
            # Create empty maintenance_elements record for linking
            c.execute(
                "INSERT INTO maintenance_elements (maintenance_id, element_id) VALUES (?, ?)",
                (maint_id, elem_id)
            )
            self.conn.commit()
            
            # Close this dialog and show DGA form
            popup.dismiss()
            self.show_dga_measurement_popup(
                maintenance_id=maint_id,
                element_id=elem_id,
                element_name=elem_name,
                substation_id=sub_id,
                substation_name=sub_name,
                gate_value=gate_val,
                serial_number=serial_num,
                manufacturer="",
                dga_id=None
            )
        
        proceed_btn.bind(on_press=on_proceed)
        btn_layout.add_widget(proceed_btn)
        
        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"], size_hint_x=0.5)
        cancel_btn.bind(on_press=popup.dismiss)
        btn_layout.add_widget(cancel_btn)
        
        main_layout.add_widget(btn_layout)
        popup.content = main_layout
        popup.open()

    def show_maintenance_menu(
        self,
        instance=None,
        preselected_substation_name=None,
        parent_popup=None,
        maintenance_id=None,
        after_save_callback=None,
        prefill_data=None,
    ):
        """Show maintenance recording dialog

        Args:
            instance: Button instance (optional, for compatibility)
            preselected_substation_name: Name of substation to preselect (optional)
            parent_popup: Parent popup to dismiss when opening this one (optional)
        """
        # Dismiss parent popup if provided
        if parent_popup:
            parent_popup.dismiss()

        # Get list of substations
        c = self.conn.cursor()
        c.execute("SELECT id, name FROM substations ORDER BY name")
        substations = c.fetchall()

        if not substations:
            show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"].get("NO_SUBSTATIONS", "Δεν υπάρχουν υποσταθμοί!"))
            return

        maintenance_record = None
        maintenance_people = []
        existing_elements_data = {}
        responsible_person_id = None
        prefill_data = prefill_data or {}
        prefill_attachment_paths = prefill_data.get("attachment_paths") or []

        if maintenance_id:
            c.execute(
                """
                SELECT substation_id, name, date_time, overall_comments, maintenance_type, user_name, responsible_id, onedrive_media_folder_link
                FROM maintenance
                WHERE id = ?
            """,
                (maintenance_id,),
            )
            maintenance_record = c.fetchone()
            if not maintenance_record:
                show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"].get("MAINTENANCE_NOT_FOUND", "Η συντήρηση δεν βρέθηκε."))
                return

            maint_substation_id = maintenance_record[0]
            c.execute("SELECT name FROM substations WHERE id=?", (maint_substation_id,))
            sub_row = c.fetchone()
            if sub_row:
                preselected_substation_name = sub_row[0]

            c.execute(
                "SELECT person_id, role FROM maintenance_people WHERE maintenance_id=?",
                (maintenance_id,),
            )
            maintenance_people = c.fetchall()
            responsible_person_id = maintenance_record[6]
            if not responsible_person_id:
                for pid, role in maintenance_people:
                    if role == "responsible":
                        responsible_person_id = pid
                        break

            c.execute(
                """
                SELECT element_id, element_comments,
                       insulation_closed_fa_ground, insulation_closed_fa_unit,
                       insulation_closed_fb_ground, insulation_closed_fb_unit,
                       insulation_closed_fc_ground, insulation_closed_fc_unit,
                       insulation_open_fa_fa, insulation_open_fa_unit,
                       insulation_open_fb_fb, insulation_open_fb_unit,
                       insulation_open_fc_fc, insulation_open_fc_unit,
                       contact_resistance_fa_fa, contact_resistance_fb_fb, contact_resistance_fc_fc,
                       operations_count,
                      sf6_leakage_kg, sf6_leak_methodology,
                       sf6_n2_fa, h2o_fa, so2_fa, sf6_n2_fb, h2o_fb, so2_fb, sf6_n2_fc, h2o_fc, so2_fc,
                       vidar_fa, vidar_fb, vidar_fc
                FROM maintenance_elements
                WHERE maintenance_id = ?
            """,
                (maintenance_id,),
            )
            for row in c.fetchall():
                existing_elements_data[row[0]] = {
                    "element_comments": row[1] or "",
                    "ins_closed_fa": row[2],
                    "ins_closed_fa_unit": row[3] or "GΩ",
                    "ins_closed_fb": row[4],
                    "ins_closed_fb_unit": row[5] or "GΩ",
                    "ins_closed_fc": row[6],
                    "ins_closed_fc_unit": row[7] or "GΩ",
                    "ins_open_fa": row[8],
                    "ins_open_fa_unit": row[9] or "GΩ",
                    "ins_open_fb": row[10],
                    "ins_open_fb_unit": row[11] or "GΩ",
                    "ins_open_fc": row[12],
                    "ins_open_fc_unit": row[13] or "GΩ",
                    "cont_fa": row[14],
                    "cont_fb": row[15],
                    "cont_fc": row[16],
                    "ops_count": row[17],
                    "sf6_leakage_kg": row[18],
                    "sf6_leak_methodology": row[19] or "",
                    "sf6": {
                        "sf6_n2_fa": row[20],
                        "h2o_fa": row[21],
                        "so2_fa": row[22],
                        "sf6_n2_fb": row[23],
                        "h2o_fb": row[24],
                        "so2_fb": row[25],
                        "sf6_n2_fc": row[26],
                        "h2o_fc": row[27],
                        "so2_fc": row[28],
                    },
                }

        popup_title = (
            "Επεξεργασία Συντήρησης" if maintenance_id else "Καταχώρηση Συντήρησης"
        )
        popup = Popup(title=popup_title, size_hint=(0.9, 0.95))

        # Create a scrollable container for all content
        scroll_view = ScrollView(bar_width=10, scroll_type=["bars", "content"])
        content_layout = GridLayout(cols=1, spacing=10, size_hint_y=None, padding=10)
        content_layout.bind(minimum_height=content_layout.setter("height"))

        # Substation selection
        content_layout.add_widget(
            Label(text=S["MESSAGES"].get("SELECT_SUBSTATION", "Επιλογή Υποσταθμού:"), size_hint_y=None, height=40)
        )
        substation_map = {s[1]: s[0] for s in substations}

        # Use preselected substation if provided, otherwise use first in list
        prefill_substation_name = preselected_substation_name
        if not prefill_substation_name and prefill_data.get("substation_id"):
            for sid, sname in substations:
                if sid == prefill_data["substation_id"]:
                    prefill_substation_name = sname
                    break
        if not prefill_substation_name and prefill_data.get("substation_name"):
            prefill_substation_name = prefill_data.get("substation_name")
        initial_substation = (
            prefill_substation_name if prefill_substation_name else substations[0][1]
        )

        substation_row = BoxLayout(size_hint_y=None, height=40, spacing=5)
        substation_input = TextInput(
            text=initial_substation, readonly=True, size_hint_x=0.7, multiline=False
        )
        select_sub_btn = Button(text=S["MESSAGES"].get("SELECT_PROMPT", "Επιλογή"), size_hint_x=0.3)
        substation_row.add_widget(substation_input)
        substation_row.add_widget(select_sub_btn)
        
        content_layout.add_widget(substation_row)

        def _on_select_substation(sub_name):
            substation_input.text = sub_name
            load_elements(sub_name)  # Reload elements when substation changes

        def select_substation(*_args):
            self._show_substation_selection_window_with_callback(
                popup, substations, on_select=_on_select_substation,
                title=S["MESSAGES"].get("SELECT_SUBSTATION", "Επιλογή Υποσταθμού")
            )
        
        select_sub_btn.bind(on_press=select_substation)

        # Maintenance Type
        content_layout.add_widget(
            Label(text=S["MESSAGES"].get("MAINT_TYPE_LABEL", "Τύπος Συντήρησης:"), size_hint_y=None, height=35)
        )
        maint_type_default = (
            maintenance_record[4]
            if maintenance_record and maintenance_record[4]
            else S["MESSAGES"]["MAINT_TYPE_DEFAULT"]
        )
        if not maintenance_id and prefill_data.get("maintenance_type"):
            maint_type_default = prefill_data.get("maintenance_type")
        maintenance_type_spinner = Spinner(
            text=maint_type_default,
            values=S["MESSAGES"]["MAINTENANCE_TYPES"],
            size_hint_y=None,
            height=35,
        )
        
        # Handle DGA maintenance type specially
        def on_maintenance_type_change(spinner, text):
            dga_type = S["MESSAGES"].get("DGA_LABEL", "Physicochemical/Gas Chromatography")
            if text == dga_type and not maintenance_id:
                # DGA type selected: show simplified transformer selector
                popup.dismiss()
                self._show_dga_maintenance_form(parent_popup=parent_popup)
        
        maintenance_type_spinner.bind(text=on_maintenance_type_change)
        content_layout.add_widget(maintenance_type_spinner)

        # Date/Time (auto-filled with current)
        from datetime import datetime

        content_layout.add_widget(
            Label(text=S["MESSAGES"].get("DATE_TIME_LABEL", "Ημερομηνία & Ώρα:"), size_hint_y=None, height=35)
        )
        datetime_default = (
            maintenance_record[2]
            if maintenance_record and maintenance_record[2]
            else datetime.now().strftime("%Y-%m-%d %H:%M")
        )
        if not maintenance_id and prefill_data.get("date_time"):
            datetime_default = prefill_data.get("date_time")
        datetime_input = TextInput(
            text=datetime_default,
            hint_text="YYYY-MM-DD HH:MM",
            size_hint_y=None,
            height=35,
            multiline=False,
        )
        content_layout.add_widget(datetime_input)

        # Responsible person (mandatory)
        c.execute(
            "SELECT id, name, role FROM people WHERE active=1 ORDER BY CASE\n                    WHEN role LIKE '%Τομεαρ%' COLLATE NOCASE OR role LIKE '%Τομεάρχ%' COLLATE NOCASE THEN 0\n                    WHEN role LIKE '%Υποτο%' COLLATE NOCASE THEN 1\n                    WHEN role LIKE '%Ειδικ%' COLLATE NOCASE OR role LIKE '%Ειδικό Στέλεχος%' COLLATE NOCASE THEN 2\n                    WHEN role LIKE '%Μηχανικ%' COLLATE NOCASE THEN 3\n                    WHEN role LIKE '%Εργοδηγ%' COLLATE NOCASE THEN 4\n                    WHEN role LIKE '%Αρχιτεχν%' COLLATE NOCASE THEN 5\n                    WHEN role LIKE '%Τεχν%' COLLATE NOCASE THEN 6\n                    WHEN role LIKE '%Χειριστ%' COLLATE NOCASE THEN 7\n                    WHEN role LIKE '%Υποστ%' COLLATE NOCASE THEN 8\n                    ELSE 99 END, COALESCE(surname, name) COLLATE NOCASE"
        )
        people = c.fetchall()
        if not people:
            show_message_popup(
                S["TITLES"].get("ERROR", "Σφάλμα"),
                S["MESSAGES"].get("NO_PEOPLE", "Δεν υπάρχουν καταχωρημένα άτομα. Παρακαλώ προσθέστε προσωπικό."),
                callback=lambda: self.show_people_management(None),
            )
            return

        content_layout.add_widget(
            Label(
                text=S["MESSAGES"].get("RESPONSIBLE_LABEL", "Υπεύθυνος Συντήρησης (υποχρεωτικό):"), size_hint_y=None, height=35
            )
        )

        # Filter people into responsible and crew lists according to role rules
        responsible_people, crew_people = filter_people_for_maintenance(
            people, responsible_person_id
        )

        if not responsible_people:
            show_message_popup(
                S["TITLES"].get("ERROR", "Σφάλμα"),
                S["MESSAGES"].get("NO_AVAILABLE_RESPONSIBLE", "Δεν υπάρχει διαθέσιμος υπεύθυνος συντήρησης με τα κατάλληλα δικαιώματα. Προσθέστε ή ενημερώστε προσωπικό."),
                callback=lambda: self.show_people_management(None),
            )
            return

        people_map = {f"{p[1]} ({p[2]})": p[0] for p in responsible_people}
        responsible_default_text = list(people_map.keys())[0] if people_map else ""
        
        # Pre-fill with logged-in user if they're responsible-capable (for new maintenance only)
        if not maintenance_id and not prefill_data.get("responsible_id"):
            current_user = get_current_user()
            if current_user and is_user_responsible_capable(current_user["role"]):
                # Find the logged-in user in the responsible people list
                for label, pid in people_map.items():
                    if pid == current_user["id"]:
                        responsible_default_text = label
                        responsible_person_id = pid
                        break
        
        # Override with prefill data if provided
        if not maintenance_id and prefill_data.get("responsible_id"):
            responsible_person_id = prefill_data.get("responsible_id")
        
        # Override with existing maintenance responsible if editing
        if responsible_person_id:
            for label, pid in people_map.items():
                if pid == responsible_person_id:
                    responsible_default_text = label
                    break

        responsible_spinner = Spinner(
            text=responsible_default_text,
            values=list(people_map.keys()),
            size_hint_y=None,
            height=35,
        )
        content_layout.add_widget(responsible_spinner)

        # Crew selection (optional)
        content_layout.add_widget(
            Label(text=S["MESSAGES"].get("CREW_LABEL", "Ομάδα Συντήρησης (προαιρετικό):"), size_hint_y=None, height=35)
        )

        crew_actions = BoxLayout(size_hint_y=None, height=30, spacing=5)
        select_all_btn = Button(text=S["MESSAGES"].get("SELECT_ALL_BTN", "Επιλογή Όλων"), size_hint_x=0.5)
        clear_all_btn = Button(text=S["MESSAGES"].get("NONE", "Καμία"), size_hint_x=0.5)
        crew_actions.add_widget(select_all_btn)
        crew_actions.add_widget(clear_all_btn)
        content_layout.add_widget(crew_actions)

        # Create a table-like, multi-column layout for crew checkboxes so many people fit

        preferred_col_width = 280
        max_cols = 5
        cols = max(1, min(max_cols, int(Window.width // preferred_col_width)))
        crew_container = GridLayout(cols=cols, spacing=6, size_hint_y=None, padding=5)
        crew_container.bind(minimum_height=crew_container.setter("height"))
        crew_checks = {}
        crew_ids = {pid for pid, role in maintenance_people if role == "crew"}
        if not maintenance_id and prefill_data.get("crew_ids"):
            crew_ids = set(prefill_data.get("crew_ids"))
        # Ensure responsible person appears in crew list (preselected & not editable)
        responsible_pid = None
        try:
            responsible_pid = people_map.get(responsible_default_text)
        except Exception:
            responsible_pid = None
        if responsible_pid and not any(p[0] == responsible_pid for p in crew_people):
            # find responsible in all people and prepend to crew_people
            found = next((p for p in people if p[0] == responsible_pid), None)
            if found:
                crew_people.insert(0, found)

        # Build categorized crew area: compact gaps, category headers, and per-category grids
        min_cell_h = 18
        # Fixed per-person row height (adjust this value to change cell heights manually)
        crew_cell_h = 26
        # small spacing so headers don't overlap wrapped names
        crew_section = BoxLayout(orientation="vertical", size_hint_y=None, spacing=4)
        crew_section.bind(minimum_height=crew_section.setter("height"))

        # Group crew_people into categories using validation helper
        grouped = group_people_by_category(crew_people)
        for cat, members in grouped.items():
            if not members:
                continue
            # Category header (taller so it doesn't overlap wrapped names)
            hdr = Label(
                text=f"[b]{cat}[/b]",
                markup=True,
                color=self.theme.get("primary", (0.05, 0.18, 0.36, 1)),
                size_hint_y=None,
                height=max(36, min_cell_h + 12),
            )
            crew_section.add_widget(hdr)
            # Small spacer to guarantee separation between header and wrapped rows
            from kivy.uix.widget import Widget as _KivyWidget
            crew_section.add_widget(_KivyWidget(size_hint_y=None, height=8))

            # Grid for this category (horizontal, vertical spacing)
            # Increase vertical spacing between rows so wrapped/second-line items have more room
            cat_grid = GridLayout(cols=cols, spacing=(6,18), size_hint_y=None, padding=10)
            cat_grid.bind(minimum_height=cat_grid.setter("height"))

            for pid, name, role in members:
                # container cell
                cell = BoxLayout(orientation="horizontal", size_hint_y=None, height=min_cell_h, spacing=6, padding=(2,0))
                # anchor layout for checkbox top alignment with text
                anchor = AnchorLayout(size_hint_x=None, size_hint_y=None, width=30, height=min_cell_h, anchor_x='center', anchor_y='top')
                cb = CheckBox(size_hint=(None, None), size=(20, min_cell_h), pos_hint={'top':1}, color=self.theme.get("primary", (0.05, 0.18, 0.36, 1)))
                if pid in crew_ids:
                    cb.active = True
                if responsible_pid and pid == responsible_pid:
                    cb.active = True
                    cb.disabled = True
                anchor.add_widget(cb)
                cell.add_widget(anchor)

                # Simple fixed-height label so you can adjust heights manually.
                lbl = Label(text=f"{name} ({role})", halign="left", valign="top", size_hint_x=1)
                lbl.size_hint_y = None
                lbl.height = crew_cell_h
                lbl.padding = (0, 2)
                # keep text wrapping updated when width changes, but do not re-measure height
                lbl.bind(width=lambda inst, w: setattr(inst, 'text_size', (max(0, w - 6), None)))

                # apply fixed heights to containers and checkbox
                cell.height = crew_cell_h
                anchor.height = crew_cell_h
                cb.size = (20, crew_cell_h)

                cell.add_widget(lbl)
                cat_grid.add_widget(cell)
                crew_checks[pid] = cb

            # Let the GridLayout compute its minimum height from children (handles wrapped labels)
            # (binding to minimum_height already set above)
            crew_section.add_widget(cat_grid)

        # finally add the whole crew section to content layout so it expands fully
        content_layout.add_widget(crew_section)

        # The per-category grids are inside `crew_section` and will size themselves;
        # `crew_container` is unused here so don't add it to avoid extra spacing.

        def set_all_crew(value):
            for cb in crew_checks.values():
                if not getattr(cb, "disabled", False):
                    cb.active = value

        select_all_btn.bind(on_press=lambda x: set_all_crew(True))
        clear_all_btn.bind(on_press=lambda x: set_all_crew(False))

        # When responsible changes, ensure crew checkbox for responsible is selected and disabled
        def _sync_responsible_in_crew(*_args):
            # determine selected responsible pid
            sel_label = responsible_spinner.text
            sel_pid = people_map.get(sel_label)
            for pid, cb in crew_checks.items():
                if pid == sel_pid:
                    cb.active = True
                    cb.disabled = True
                else:
                    # re-enable other checkboxes
                    if getattr(cb, "disabled", False):
                        cb.disabled = False

        responsible_spinner.bind(text=lambda _inst, _val: _sync_responsible_in_crew())

        # Overall comments
        content_layout.add_widget(
            Label(text=S["MESSAGES"].get("OVERALL_COMMENTS_LABEL", "Γενικά Σχόλια Συντήρησης:"), size_hint_y=None, height=35)
        )
        comments_default = (
            maintenance_record[3]
            if maintenance_record and maintenance_record[3]
            else ""
        )
        if not maintenance_id and prefill_data.get("overall_comments"):
            comments_default = prefill_data.get("overall_comments")
        overall_comments = TextInput(
            hint_text="Γενικά σχόλια για την συντήρηση...",
            text=comments_default,
            size_hint_y=None,
            height=60,
            multiline=True,
        )

        def _resize_comments(_instance=None, _value=None):
            lines = overall_comments.text.count("\n") + 1
            overall_comments.height = max(60, min(320, 24 * lines + 20))

        overall_comments.bind(text=_resize_comments)
        _resize_comments()
        content_layout.add_widget(overall_comments)

        # OneDrive Media Folder Link
        content_layout.add_widget(
            Label(text=S["MESSAGES"].get("ONEDRIVE_MEDIA_LABEL", "Σύνδεσμος Φάκελου Εικόνων/Βίδεο (OneDrive):"), size_hint_y=None, height=35)
        )
        onedrive_media_default = (
            maintenance_record[7]
            if maintenance_record and len(maintenance_record) > 7
            else ""
        )
        if not maintenance_id and prefill_data.get("onedrive_media_folder_link"):
            onedrive_media_default = prefill_data.get("onedrive_media_folder_link")
        onedrive_media_link = TextInput(
            hint_text="https://...",
            text=onedrive_media_default or "",
            size_hint_y=None,
            height=40,
            multiline=False,
        )
        content_layout.add_widget(onedrive_media_link)

        # Elements selection area
        content_layout.add_widget(
            Label(
                text=S["MESSAGES"].get("ELEMENTS_SECTION_LABEL", "Στοιχεία που συντηρήθηκαν (τουλάχιστον 1):"),
                size_hint_y=None,
                height=40,
            )
        )

        # Container for element checkboxes (no longer in a separate ScrollView)
        elements_container = GridLayout(cols=1, spacing=5, size_hint_y=None, padding=5)
        elements_container.bind(minimum_height=elements_container.setter("height"))
        content_layout.add_widget(elements_container)

        # Dictionary to store element widgets
        element_widgets = {}

        def load_elements(substation_name):
            """Load elements for selected substation"""
            elements_container.clear_widgets()
            element_widgets.clear()

            substation_id = substation_map[substation_name]
            c = self.conn.cursor()
            c.execute(
                """
                  SELECT e.id, e.element_type, e.name, e.serial_number, e.gate, e.is_main_switch,
                       e.breaker_category, e.manufacturer, e.model, e.operations_count,
                       em.manufacturer as model_manufacturer, em.model_name
                FROM elements e
                LEFT JOIN element_models em ON e.element_model_id = em.id
                WHERE e.substation_id=?
                  ORDER BY e.gate
            """,
                (substation_id,),
            )
            elements = c.fetchall()

            if not elements:
                elements_container.add_widget(
                    Label(
                        text=S["MESSAGES"].get("NO_ELEMENTS_IN_SUBSTATION", "Δεν υπάρχουν στοιχεία σε αυτόν τον υποσταθμό"),
                        size_hint_y=None,
                        height=40,
                    )
                )
                return

            element_ids = [elem[0] for elem in elements]
            last_ops_map = {}
            if element_ids:
                placeholders = ",".join(["?"] * len(element_ids))
                c.execute(
                    f"""
                    SELECT me.element_id, me.operations_count, m.date_time
                    FROM maintenance_elements me
                    JOIN maintenance m ON me.maintenance_id = m.id
                    WHERE me.element_id IN ({placeholders})
                    ORDER BY m.date_time DESC
                """,
                    element_ids,
                )
                for elem_id, ops_count_val, _date_time in c.fetchall():
                    if elem_id not in last_ops_map:
                        last_ops_map[elem_id] = ops_count_val

            # Define sort priority for element types
            def get_element_priority(elem):
                (
                    elem_id,
                    elem_type,
                    elem_name,
                    serial_number,
                    gate,
                    is_main_switch,
                    breaker_category,
                    manufacturer,
                    model,
                    operations_count,
                    model_manufacturer,
                    model_name,
                ) = elem

                # Priority order: HV breaker, Transformer, Motor Drive, MV main breaker, MV interconnection breaker, MV line breaker, MV capacitor breaker, rest
                if elem_type == self.ELEM_BREAKER_YT:
                    return (1, elem_name)
                elif self._is_transformer(elem_type):
                    return (2, elem_name)
                elif elem_type == "Motor Drive":
                    return (3, elem_name)
                elif (
                    elem_type == self.ELEM_BREAKER_MT and is_main_switch == 1
                ):  # Main breaker
                    return (4, elem_name)
                elif (
                    elem_type == self.ELEM_BREAKER_MT and is_main_switch == 2
                ):  # Interconnection breaker
                    return (5, elem_name)
                elif (
                    elem_type == self.ELEM_BREAKER_MT and is_main_switch == 0
                ):  # Line breaker
                    return (6, elem_name)
                elif (
                    elem_type == self.ELEM_BREAKER_MT and is_main_switch == 3
                ):  # Capacitor breaker
                    return (7, elem_name)
                else:
                    return (8, elem_name)

            # Group elements by gate
            gates_dict = {}
            for elem in elements:
                (
                    elem_id,
                    elem_type,
                    elem_name,
                    serial_number,
                    gate,
                    is_main_switch,
                    breaker_category,
                    manufacturer,
                    model,
                    operations_count,
                    model_manufacturer,
                    model_name,
                ) = elem

                gate_key = gate if gate else get_unreg()
                if gate_key not in gates_dict:
                    gates_dict[gate_key] = []
                gates_dict[gate_key].append(elem)

            # Sort elements within each gate according to priority
            for gate_key in gates_dict:
                gates_dict[gate_key].sort(key=get_element_priority)

            # Display elements grouped by gate
            # Show gates in order: ΠΥΛΗ 1, ΠΥΛΗ 2, etc., then unassigned
            sorted_gates = sorted(
                [g for g in gates_dict.keys() if g.startswith("ΠΥΛΗ")]
            )
            unreg_val = get_unreg()
            if unreg_val in gates_dict:
                sorted_gates.append(unreg_val)

            # Display elements grouped by gate
            for gate_name in sorted_gates:
                gate_elements = gates_dict[gate_name]

                # Gate header with count
                element_count = len(gate_elements)
                gate_label = Label(
                    text=f"{gate_name} ({element_count} στοιχεία)",
                    size_hint_y=None,
                    height=35,
                    bold=True,
                    color=(0.2, 0.6, 1, 1),  # Blue color for gate headers
                )
                elements_container.add_widget(gate_label)

                # Display elements in this gate
                for (
                    elem_id,
                    elem_type,
                    elem_name,
                    serial_number,
                    gate,
                    is_main_switch,
                    breaker_category,
                    manufacturer,
                    model,
                    operations_count,
                    model_manufacturer,
                    model_name,
                ) in gate_elements:
                    # Determine if this is a circuit breaker for showing measurement fields
                    is_breaker = elem_type in self.BREAKER_ELEMENT_TYPES

                    # Build element display text with breaker type, manufacturer, and model
                    display_type = self._format_elem_type(elem_type, is_main_switch)
                    elem_display = f"[b]{elem_name}[/b] - {display_type}"
                    if breaker_category:
                        elem_display += f" ({breaker_category})"
                    elem_display += f"\nS/N: {serial_number or '-'}"

                    # Add manufacturer and model info
                    mfr = model_manufacturer or manufacturer or "-"
                    mdl = model_name or model or "-"
                    elem_display += f" | Κατ.: {mfr} | Μοντ.: {mdl} (id:{elem_id or 'N/A'})"

                    # Element container - initially just checkbox and label
                    elem_box = BoxLayout(
                        size_hint_y=None, spacing=5, orientation="vertical"
                    )
                    elem_box.bind(minimum_height=elem_box.setter("height"))

                    # Checkbox and name (always visible)
                    checkbox_layout = BoxLayout(size_hint_y=None, height=50, spacing=5)
                    checkbox = CheckBox(
                        size_hint_x=0.08,
                        color=self.theme.get("primary", (0.05, 0.18, 0.36, 1)),
                    )
                    checkbox_layout.add_widget(checkbox)

                    elem_label = Label(text=elem_display, size_hint_x=0.92, markup=True)
                    checkbox_layout.add_widget(elem_label)
                    elem_box.add_widget(checkbox_layout)

                    # Per-element holders stored in element_widgets to avoid sharing
                    element_widgets.setdefault(elem_id, {})
                    element_widgets[elem_id].setdefault("details_container", None)
                    element_widgets[elem_id].setdefault("comments", None)
                    element_widgets[elem_id].setdefault("measurements", None)
                    element_widgets[elem_id].setdefault("measurements_toggle", None)

                    # Store metadata for this element so builders can use it reliably
                    element_widgets[elem_id]["meta"] = {
                        "elem_name": elem_name,
                        "breaker_category": breaker_category,
                        "elem_type": elem_type,
                        "model_manufacturer": model_manufacturer,
                        "model_name": model_name,
                        "is_breaker": is_breaker,
                        "operations_count": operations_count,
                    }

                    def build_details_for(eid):
                        meta = element_widgets.get(eid, {}).get("meta")
                        if not meta:
                            return
                        if element_widgets.get(eid, {}).get("details_container") is not None:
                            return

                        elem_name = meta.get("elem_name")
                        elem_type = meta.get("elem_type")
                        breaker_category = meta.get("breaker_category")
                        model_manufacturer = meta.get("model_manufacturer")
                        model_name = meta.get("model_name")
                        is_breaker = meta.get("is_breaker")
                        operations_count = meta.get("operations_count")
                        has_measurement_form = bool(
                            is_breaker or self._is_transformer(elem_type)
                        )

                        # Ensure optional widgets exist in local scope to avoid NameError
                        ops_count_input = None

                        # debug logging removed

                        # Additional diagnostics: print transformer-detection result
                        # transformer detection logging removed

                        is_hv_oil = (elem_type == self.ELEM_BREAKER_YT and breaker_category == "Ελαίου")
                        is_hv_sf6 = (elem_type == self.ELEM_BREAKER_YT and breaker_category == "SF6")

                        # build_details_for START

                        details_container = BoxLayout(
                            size_hint_y=None, spacing=5, orientation="vertical"
                        )
                        details_container.bind(
                            minimum_height=details_container.setter("height")
                        )

                        elem_comments = TextInput(
                            hint_text="Παρατηρήσεις για αυτό το στοιχείο...",
                            size_hint_y=None,
                            height=30,
                            multiline=False,
                        )
                        details_container.add_widget(elem_comments)

                        measurements_toggle_row = None
                        measurements_toggle = None
                        measurements_fields_container = None
                        if has_measurement_form:
                            measurements_toggle_row = BoxLayout(
                                size_hint_y=None, height=30, spacing=6
                            )
                            measurements_toggle_row.add_widget(
                                Label(text="Στοιχεία Μετρήσεων:", size_hint_x=0.6)
                            )
                            measurements_toggle = CheckBox(
                                size_hint=(None, None), size=(28, 28)
                            )
                            measurements_toggle.color = self.theme.get(
                                "primary", (0.05, 0.18, 0.36, 1)
                            )
                            measurements_toggle_row.add_widget(measurements_toggle)
                            measurements_toggle_row.add_widget(Widget())
                            details_container.add_widget(measurements_toggle_row)

                            measurements_fields_container = BoxLayout(
                                size_hint_y=None, spacing=5, orientation="vertical"
                            )
                            measurements_fields_container.bind(
                                minimum_height=measurements_fields_container.setter(
                                    "height"
                                )
                            )
                            details_container.add_widget(measurements_fields_container)

                        # created details_container

                        # Initialize measurements structure and container placeholders
                        measurements = {}

                        # Common ops counter input (reused across breaker/transformer UIs)
                        ops_count_input = TextInput(text="", size_hint_x=0.12, multiline=False)

                        # Prepare containers for special measurements
                        sf6_widgets = {}
                        vidar_widgets = {}

                        # High-voltage oil-specific layout (only for ΥΤ & Ελαίου)
                        if is_hv_oil:
                            # Category header
                            details_container.add_widget(
                                Label(
                                    text="ΜΕΤΡΗΤΗΣ ΧΕΙΡΙΣΜΩΝ",
                                    size_hint_y=None,
                                    height=25,
                                    bold=True,
                                )
                            )

                            # Ops count (reuse ops_count_input created above)
                            ops_layout_custom = BoxLayout(
                                size_hint_y=None, height=30, spacing=6
                            )
                            ops_layout_custom.add_widget(
                                Label(text="Αριθμός Χειρισμών:", size_hint_x=0.6)
                            )
                            try:
                                ops_count_input.size_hint_x = 0.12
                                ops_layout_custom.add_widget(ops_count_input)
                            except Exception:
                                ops_layout_custom.add_widget(TextInput(text="", size_hint_x=0.12))
                            ops_layout_custom.add_widget(Widget())
                            details_container.add_widget(ops_layout_custom)

                            # ΚΑΤΑΣΤΑΣΗ ΔΙΑΚΟΠΤΗ
                            details_container.add_widget(
                                Label(
                                    text="ΚΑΤΑΣΤΑΣΗ ΔΙΑΚΟΠΤΗ",
                                    size_hint_y=None,
                                    height=25,
                                    bold=True,
                                )
                            )

                            oil_cond = TextInput(hint_text="Κατάσταση λαδιού", multiline=False, size_hint_y=None, height=30)
                            details_container.add_widget(oil_cond)

                            oil_changed_row = BoxLayout(size_hint_y=None, height=30, spacing=6)
                            oil_changed_row.add_widget(Label(text="Αλλαγή λαδιών:", size_hint_x=0.6))
                            oil_changed_cb = CheckBox(size_hint=(None, None), size=(28, 28))
                            oil_changed_cb.color = (0, 0, 0, 1)
                            oil_changed_row.add_widget(oil_changed_cb)
                            oil_changed_row.add_widget(Widget())
                            details_container.add_widget(oil_changed_row)

                            synch_check = TextInput(hint_text="Έλεγχος ταυτοχρονισμού", multiline=False, size_hint_y=None, height=30)
                            details_container.add_widget(synch_check)

                            wash_insulators = TextInput(hint_text="Πλύσιμο Μονωτήρων - Έλεγχος Φθορών", multiline=False, size_hint_y=None, height=30)
                            details_container.add_widget(wash_insulators)

                            conn_check_row = BoxLayout(size_hint_y=None, height=30, spacing=6)
                            conn_check_row.add_widget(Label(text="Έλεγχος συνδέσμων, κεφαλών, πείρων:", size_hint_x=0.6))
                            conn_check_cb = CheckBox(size_hint=(None, None), size=(28, 28))
                            conn_check_cb.color = (0, 0, 0, 1)
                            conn_check_row.add_widget(conn_check_cb)
                            conn_check_row.add_widget(Widget())
                            details_container.add_widget(conn_check_row)

                            lubrication_row = BoxLayout(size_hint_y=None, height=30, spacing=6)
                            lubrication_row.add_widget(Label(text="Λίπανση Μηχανισμού:", size_hint_x=0.6))
                            lubrication_cb = CheckBox(size_hint=(None, None), size=(28, 28))
                            lubrication_cb.color = (0, 0, 0, 1)
                            lubrication_row.add_widget(lubrication_cb)
                            lubrication_row.add_widget(Widget())
                            details_container.add_widget(lubrication_row)

                            # Μέτρηση Αντίστασης Διαβάσεως (MΩ) - table 3 columns
                            details_container.add_widget(Label(text="Μέτρηση Αντίστασης Διαβάσεως (MΩ):", size_hint_y=None, height=25, bold=True))
                            raid_header = BoxLayout(size_hint_y=None, height=25)
                            raid_header.add_widget(Label(text="Α(ΦΑΣΗ)", size_hint_x=0.33))
                            raid_header.add_widget(Label(text="Β(ΦΑΣΗ)", size_hint_x=0.33))
                            raid_header.add_widget(Label(text="C(ΦΑΣΗ)", size_hint_x=0.34))
                            details_container.add_widget(raid_header)
                            raid_row = BoxLayout(size_hint_y=None, height=32)
                            raid_a = TextInput(hint_text="0.0", multiline=False)
                            raid_b = TextInput(hint_text="0.0", multiline=False)
                            raid_c = TextInput(hint_text="0.0", multiline=False)
                            raid_row.add_widget(raid_a)
                            raid_row.add_widget(raid_b)
                            raid_row.add_widget(raid_c)
                            details_container.add_widget(raid_row)

                            # Μέτρηση Επαφών (Μηχανισμός Κλειστός) - two rows (Α/Ζ, Μ/Σ) in μΩ
                            details_container.add_widget(Label(text="Μέτρηση Επαφών (Μηχανισμός Κλειστός) (μΩ):", size_hint_y=None, height=25, bold=True))
                            contact_header = BoxLayout(size_hint_y=None, height=25)
                            contact_header.add_widget(Label(text="", size_hint_x=0.2))
                            contact_header.add_widget(Label(text="Α(ΦΑΣΗ)", size_hint_x=0.266))
                            contact_header.add_widget(Label(text="Β(ΦΑΣΗ)", size_hint_x=0.266))
                            contact_header.add_widget(Label(text="C(ΦΑΣΗ)", size_hint_x=0.274))
                            details_container.add_widget(contact_header)

                            # Row Α/Ζ
                            contact_row_az = BoxLayout(size_hint_y=None, height=32)
                            contact_row_az.add_widget(Label(text="Α/Ζ", size_hint_x=0.2))
                            contact_az_a = TextInput(hint_text="0.0", multiline=False)
                            contact_az_b = TextInput(hint_text="0.0", multiline=False)
                            contact_az_c = TextInput(hint_text="0.0", multiline=False)
                            contact_row_az.add_widget(contact_az_a)
                            contact_row_az.add_widget(contact_az_b)
                            contact_row_az.add_widget(contact_az_c)
                            details_container.add_widget(contact_row_az)

                            # Row Μ/Σ
                            contact_row_ms = BoxLayout(size_hint_y=None, height=32)
                            contact_row_ms.add_widget(Label(text="Μ/Σ", size_hint_x=0.2))
                            contact_ms_a = TextInput(hint_text="0.0", multiline=False)
                            contact_ms_b = TextInput(hint_text="0.0", multiline=False)
                            contact_ms_c = TextInput(hint_text="0.0", multiline=False)
                            contact_row_ms.add_widget(contact_ms_a)
                            contact_row_ms.add_widget(contact_ms_b)
                            contact_row_ms.add_widget(contact_ms_c)
                            details_container.add_widget(contact_row_ms)

                            # Αποστάσεις Αμορτισέρ (mm) - 3 columns
                            details_container.add_widget(Label(text="Αποστάσεις Αμορτισέρ (mm):", size_hint_y=None, height=25, bold=True))
                            amort_row = BoxLayout(size_hint_y=None, height=32)
                            amort_a = TextInput(hint_text="mm", multiline=False)
                            amort_b = TextInput(hint_text="mm", multiline=False)
                            amort_c = TextInput(hint_text="mm", multiline=False)
                            amort_row.add_widget(amort_a)
                            amort_row.add_widget(amort_b)
                            amort_row.add_widget(amort_c)
                            details_container.add_widget(amort_row)

                            # Expose these widgets in measurements dict so save logic can pick them up
                            measurements.update({
                                "oil_condition": oil_cond,
                                "oil_changed": oil_changed_cb,
                                "synch_check": synch_check,
                                "wash_insulators": wash_insulators,
                                "connections_check": conn_check_cb,
                                "lubrication": lubrication_cb,
                                "resistance_raid": (raid_a, raid_b, raid_c),
                                "contact_az": (contact_az_a, contact_az_b, contact_az_c),
                                "contact_ms": (contact_ms_a, contact_ms_b, contact_ms_c),
                                "amort_dist": (amort_a, amort_b, amort_c),
                            })

                        # High-voltage SF6-specific layout (only for ΥΤ & SF6)
                        elif is_hv_sf6:
                            # Category header (Operations counter)
                            details_container.add_widget(
                                Label(
                                    text="ΜΕΤΡΗΤΗΣ ΧΕΙΡΙΣΜΩΝ",
                                    size_hint_y=None,
                                    height=25,
                                    bold=True,
                                )
                            )

                            ops_layout_sf6 = BoxLayout(size_hint_y=None, height=30, spacing=6)
                            ops_layout_sf6.add_widget(Label(text="Αριθμός Χειρισμών:", size_hint_x=0.6))
                            try:
                                ops_count_input.size_hint_x = 0.12
                                ops_layout_sf6.add_widget(ops_count_input)
                            except Exception:
                                ops_layout_sf6.add_widget(TextInput(text="", size_hint_x=0.12))
                            ops_layout_sf6.add_widget(Widget())
                            details_container.add_widget(ops_layout_sf6)

                            # Status section
                            details_container.add_widget(
                                Label(
                                    text="ΚΑΤΑΣΤΑΣΗ ΔΙΑΚΟΠΤΗ",
                                    size_hint_y=None,
                                    height=25,
                                    bold=True,
                                )
                            )

                            # 2) Lubrication checkbox
                            lubrication_row_sf6 = BoxLayout(size_hint_y=None, height=30, spacing=6)
                            lubrication_row_sf6.add_widget(Label(text="Λίπανση μηχανισμού αρθρώσεων:", size_hint_x=0.6))
                            lubrication_cb_sf6 = CheckBox(size_hint=(None, None), size=(28, 28))
                            lubrication_cb_sf6.color = (0, 0, 0, 1)
                            lubrication_row_sf6.add_widget(lubrication_cb_sf6)
                            lubrication_row_sf6.add_widget(Widget())
                            details_container.add_widget(lubrication_row_sf6)

                            # 3) Leak check (free text)
                            leak_check = TextInput(hint_text="Έλεγχος Διαρροών Sf6", multiline=False, size_hint_y=None, height=30)
                            leak_layout_sf6 = BoxLayout(size_hint_y=None, height=30, spacing=6)
                            leak_layout_sf6.add_widget(Label(text="Έλεγχος Διαρροών Sf6 :", size_hint_x=0.45))
                            leak_layout_sf6.add_widget(leak_check)
                            leak_layout_sf6.add_widget(Widget())
                            details_container.add_widget(leak_layout_sf6)

                            # 4) Refill SF6 checkbox
                            refill_row = BoxLayout(size_hint_y=None, height=30, spacing=6)
                            refill_row.add_widget(Label(text="Συμπλήρωση Sf6 :", size_hint_x=0.6))
                            refill_cb = CheckBox(size_hint=(None, None), size=(28, 28))
                            refill_cb.color = (0, 0, 0, 1)
                            refill_row.add_widget(refill_cb)
                            refill_row.add_widget(Widget())
                            details_container.add_widget(refill_row)

                            # 5) Synchronization check (free text)
                            synch_check_sf6 = TextInput(hint_text="Έλεγχος ταυτοχρονισμού", multiline=False, size_hint_y=None, height=30)
                            details_container.add_widget(synch_check_sf6)

                            # 6) Wash insulators (free text)
                            wash_insulators_sf6 = TextInput(hint_text="Πλύσιμο Μονωτήρων – Έλεγχος Φθοράς", multiline=False, size_hint_y=None, height=30)
                            details_container.add_widget(wash_insulators_sf6)

                            # 7) Corrosion check (free text)
                            corrosion_check = TextInput(hint_text="Έλεγχος Διάβρωσης Εξωτερικών Μεταλλικών Τμημάτων", multiline=False, size_hint_y=None, height=30)
                            details_container.add_widget(corrosion_check)

                            # 8) Μέτρηση Αντίστασης Διαβάσεως (MΩ) - table 3 columns
                            details_container.add_widget(Label(text="Μέτρηση Αντίστασης Διαβάσεως (MΩ):", size_hint_y=None, height=25, bold=True))
                            raid_header_sf6 = BoxLayout(size_hint_y=None, height=25)
                            raid_header_sf6.add_widget(Label(text="Α(ΦΑΣΗ)", size_hint_x=0.33))
                            raid_header_sf6.add_widget(Label(text="Β(ΦΑΣΗ)", size_hint_x=0.33))
                            raid_header_sf6.add_widget(Label(text="C(ΦΑΣΗ)", size_hint_x=0.34))
                            details_container.add_widget(raid_header_sf6)
                            raid_row_sf6 = BoxLayout(size_hint_y=None, height=32)
                            raid_a_sf6 = TextInput(hint_text="0.0", multiline=False)
                            raid_b_sf6 = TextInput(hint_text="0.0", multiline=False)
                            raid_c_sf6 = TextInput(hint_text="0.0", multiline=False)
                            raid_row_sf6.add_widget(raid_a_sf6)
                            raid_row_sf6.add_widget(raid_b_sf6)
                            raid_row_sf6.add_widget(raid_c_sf6)
                            details_container.add_widget(raid_row_sf6)

                            # Expose SF6 widgets for persistence
                            sf6_widgets = {
                                "lubrication": lubrication_cb_sf6,
                                "leak_check": leak_check,
                                "refill": refill_cb,
                                "synch_check": synch_check_sf6,
                                "wash_insulators": wash_insulators_sf6,
                                "corrosion_check": corrosion_check,
                                "resistance_raid": (raid_a_sf6, raid_b_sf6, raid_c_sf6),
                            }

                        elif self._is_transformer(elem_type):
                            try:
                                # Fetch stored power (MVA) for this element
                                try:
                                    c = self.conn.cursor()
                                    c.execute("SELECT e.power_mva, em.power_mva FROM elements e LEFT JOIN element_models em ON e.element_model_id = em.id WHERE e.id=?", (eid,))
                                    row = c.fetchone()
                                    # prefer model power if present
                                    if row:
                                        power_val = str(row[1]) if row[1] is not None else (str(row[0]) if row[0] is not None else "")
                                    else:
                                        power_val = ""
                                except Exception:
                                    power_val = ""

                                # power is element attribute; not editable in maintenance form

                                # Category: ΧΕΙΡΙΣΜΟΙ
                                details_container.add_widget(Label(text="ΧΕΙΡΙΣΜΟΙ", size_hint_y=None, height=25, bold=True))
                                ops_row = BoxLayout(size_hint_y=None, height=30, spacing=6)
                                ops_row.add_widget(Label(text="Απαριθμητής ΣΑΤΥΦ:", size_hint_x=0.6))
                                satyf_counter = TextInput(hint_text="Αριθμός Χειρισμών", multiline=False, size_hint_x=0.12)
                                ops_row.add_widget(satyf_counter)
                                ops_row.add_widget(Widget())
                                details_container.add_widget(ops_row)

                                # Category 1: ΜΟΝΩΤΗΡΕΣ Υ.Τ & Μ.Τ
                                details_container.add_widget(Label(text="1. ΜΟΝΩΤΗΡΕΣ Υ.Τ & Μ.Τ", size_hint_y=None, height=25, bold=True))
                                details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΓΙΑ ΘΡΑΥΣΗ", multiline=False, size_hint_y=None, height=30))
                                details_container.add_widget(TextInput(hint_text="ΔΙΑΡΡΟΕΣ", multiline=False, size_hint_y=None, height=30))
                                details_container.add_widget(TextInput(hint_text="ΚΑΘΑΡΙΣΜΟΣ", multiline=False, size_hint_y=None, height=30))
                                details_container.add_widget(TextInput(hint_text="ΑΚΙΔΕΣ", multiline=False, size_hint_y=None, height=30))

                                # Category 2: ΛΑΔΙΑ Μ/Σ
                                details_container.add_widget(Label(text="2. ΛΑΔΙΑ Μ/Σ", size_hint_y=None, height=25, bold=True))
                                details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΣΤΑΘΜΗΣ ΕΛΑΙΟΥ", multiline=False, size_hint_y=None, height=30))
                                details_container.add_widget(TextInput(hint_text="ΣΥΜΠΛΗΡΩΣΗ ΕΛΑΙΟΥ", multiline=False, size_hint_y=None, height=30))
                                silica_row = BoxLayout(size_hint_y=None, height=30, spacing=6)
                                silica_row.add_widget(Label(text="ΣΙΛΙΚΑ:", size_hint_x=0.4))
                                silica_spinner = Spinner(text="N/A", values=["OK", "NOT OK", "N/A"], size_hint_x=0.2)
                                silica_row.add_widget(silica_spinner)
                                silica_row.add_widget(Widget())
                                details_container.add_widget(silica_row)

                                # Category 3: ΑΚΡΟΔΕΚΤΕΣ ΣΥΝΔΕΣΜΟΙ
                                details_container.add_widget(Label(text="3. ΑΚΡΟΔΕΚΤΕΣ ΣΥΝΔΕΣΜΟΙ", size_hint_y=None, height=25, bold=True))
                                details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΣΥΣΦΙΞΗΣ ΚΟΧΛΙΩΝ", multiline=False, size_hint_y=None, height=30))
                                details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΕΥΚΑΜΠΤΩΝ ΣΥΝΔΕΣΜΩΝ", multiline=False, size_hint_y=None, height=30))

                                # Category 4: ΣΩΜΑ Μ/Σ
                                details_container.add_widget(Label(text="4. ΣΩΜΑ Μ/Σ", size_hint_y=None, height=25, bold=True))
                                details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΔΙΑΡΡΟΩΝ ΕΛΑΙΟΥ", multiline=False, size_hint_y=None, height=30))
                                details_container.add_widget(TextInput(hint_text="ΣΤΕΓΑΝΟΠΟΙΗΣΗ", multiline=False, size_hint_y=None, height=30))
                                details_container.add_widget(TextInput(hint_text="ΚΑΘΑΡΙΣΜΟΣ", multiline=False, size_hint_y=None, height=30))
                                details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΑΝΑΚΟΥΦΙΣΤΙΚΩΝ ΒΑΛΒΙΔΩΝ", multiline=False, size_hint_y=None, height=30))
                                details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΠΡΕΣΣΟΣΤΑΤΙΚΩΝ", multiline=False, size_hint_y=None, height=30))
                                details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ BUCHOLZ", multiline=False, size_hint_y=None, height=30))

                                # 7x7 table for temperature checks header and inputs (3x3 values with labels)
                                details_container.add_widget(Label(text="ΈΛΕΓΧΟΣ ΘΕΡΜΟΣΤΟΙΧΕΙΩΝ (°C)", size_hint_y=None, height=25, bold=True))
                                temp_header = BoxLayout(size_hint_y=None, height=30)
                                temp_header.add_widget(Label(text="", size_hint_x=0.2))
                                temp_header.add_widget(Label(text="OIL", size_hint_x=0.26))
                                temp_header.add_widget(Label(text="X1", size_hint_x=0.26))
                                temp_header.add_widget(Label(text="X3", size_hint_x=0.28))
                                details_container.add_widget(temp_header)

                                # Rows: FAN, ALARM, TRIP
                                fan_row = BoxLayout(size_hint_y=None, height=32)
                                fan_row.add_widget(Label(text="FAN", size_hint_x=0.2))
                                fan_oil = TextInput(hint_text="", multiline=False)
                                fan_x1 = TextInput(hint_text="", multiline=False)
                                fan_x3 = TextInput(hint_text="", multiline=False)
                                fan_row.add_widget(fan_oil)
                                fan_row.add_widget(fan_x1)
                                fan_row.add_widget(fan_x3)
                                details_container.add_widget(fan_row)

                                alarm_row = BoxLayout(size_hint_y=None, height=32)
                                alarm_row.add_widget(Label(text="ALARM", size_hint_x=0.2))
                                alarm_oil = TextInput(hint_text="", multiline=False)
                                alarm_x1 = TextInput(hint_text="", multiline=False)
                                alarm_x3 = TextInput(hint_text="", multiline=False)
                                alarm_row.add_widget(alarm_oil)
                                alarm_row.add_widget(alarm_x1)
                                alarm_row.add_widget(alarm_x3)
                                details_container.add_widget(alarm_row)

                                trip_row = BoxLayout(size_hint_y=None, height=32)
                                trip_row.add_widget(Label(text="TRIP", size_hint_x=0.2))
                                trip_oil = TextInput(hint_text="", multiline=False)
                                trip_x1 = TextInput(hint_text="", multiline=False)
                                trip_x3 = TextInput(hint_text="", multiline=False)
                                trip_row.add_widget(trip_oil)
                                trip_row.add_widget(trip_x1)
                                trip_row.add_widget(trip_x3)
                                details_container.add_widget(trip_row)

                                # Category 5: ΣΑΤΥΦ - ΜΗΧΑΝΙΣΜΟΣ
                                details_container.add_widget(Label(text="5. ΣΑΤΥΦ - ΜΗΧΑΝΙΣΜΟΣ", size_hint_y=None, height=25, bold=True))
                                details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΑΞΟΝΩΝ ΜΕΤΑΔΟΣΗΣ ΚΙΝΗΣΗΣ", multiline=False, size_hint_y=None, height=30))
                                details_container.add_widget(TextInput(hint_text="ΚΑΘΑΡΙΣΜΟΣ, ΛΙΠΑΝΣΗ ΑΡΘΡΩΣΕΩΝ", multiline=False, size_hint_y=None, height=30))
                                details_container.add_widget(TextInput(hint_text="ΚΑΘΑΡΙΣΜΟΣ, ΛΙΠΑΝΣΗ ΟΔΟΝΤΩΤΩΝ ΤΡΟΧΩΝ", multiline=False, size_hint_y=None, height=30))
                                details_container.add_widget(TextInput(hint_text="ΔΟΚΙΜΑΣΤΙΚΟΙ ΧΕΙΡΙΣΜΟΙ", multiline=False, size_hint_y=None, height=30))
                                details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΡΩΓΜΩΝ ΣΤΟ ΧΩΡΟ ΤΟΥ DIVERTER", multiline=False, size_hint_y=None, height=30))

                                # Category 6: DIVERTER – ΜΕΤΑΓΩΓΙΚΟΣ ΔΙΑΚΟΠΤΗΣ
                                details_container.add_widget(Label(text="6. DIVERTER – ΜΕΤΑΓΩΓΙΚΟΣ ΔΙΑΚΟΠΤΗΣ", size_hint_y=None, height=25, bold=True))
                                details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΕΠΑΦΩΝ", multiline=False, size_hint_y=None, height=30))
                                details_container.add_widget(TextInput(hint_text="ΣΥΣΦΙΞΕΙΣ", multiline=False, size_hint_y=None, height=30))
                                details_container.add_widget(TextInput(hint_text="ΑΛΛΑΓΗ ΛΑΔΙΩΝ", multiline=False, size_hint_y=None, height=30))
                                details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ALARM ΧΑΜΗΛΗΣ ΣΤΑΘΜΗΣ ΛΑΔΙΟΥ", multiline=False, size_hint_y=None, height=30))

                                # Diverter resistance measurements (6 values: H1 x2, H2 x2, H3 x2)
                                details_container.add_widget(Label(text=S["MESSAGES"].get("MEASUREMENT_RESISTANCE_HEADER", "ΜΕΤΡΗΣΗ ΑΝΤΙΣΤΑΣΗΣ (Ω)"), size_hint_y=None, height=25, bold=True))
                                div_row1 = BoxLayout(size_hint_y=None, height=32)
                                div_h1_a = TextInput(hint_text="H1-1", multiline=False)
                                div_h1_b = TextInput(hint_text="H1-2", multiline=False)
                                div_row1.add_widget(div_h1_a)
                                div_row1.add_widget(div_h1_b)
                                details_container.add_widget(div_row1)
                                div_row2 = BoxLayout(size_hint_y=None, height=32)
                                div_h2_a = TextInput(hint_text="H2-1", multiline=False)
                                div_h2_b = TextInput(hint_text="H2-2", multiline=False)
                                div_row2.add_widget(div_h2_a)
                                div_row2.add_widget(div_h2_b)
                                details_container.add_widget(div_row2)
                                div_row3 = BoxLayout(size_hint_y=None, height=32)
                                div_h3_a = TextInput(hint_text="H3-1", multiline=False)
                                div_h3_b = TextInput(hint_text="H3-2", multiline=False)
                                div_row3.add_widget(div_h3_a)
                                div_row3.add_widget(div_h3_b)
                                details_container.add_widget(div_row3)

                                # Category 7: ΑΝΤΙΣΤΑΣΗ ΚΟΜΒΟΥ Μ/Σ
                                details_container.add_widget(Label(text="7. ΑΝΤΙΣΤΑΣΗ ΚΟΜΒΟΥ Μ/Σ", size_hint_y=None, height=25, bold=True))
                                details_container.add_widget(TextInput(hint_text="ΚΑΘΑΡΙΣΜΟΣ", multiline=False, size_hint_y=None, height=30))
                                details_container.add_widget(TextInput(hint_text="ΜΕΤΡΗΣΗ (Ω)", multiline=False, size_hint_y=None, height=30))
                                details_container.add_widget(TextInput(hint_text="ΣΥΣΦΙΞΕΙΣ", multiline=False, size_hint_y=None, height=30))

                                # Category 8-10: ΤΑΣΕΩΣ/ΕΝΤΑΣΕΩΣ/ΕΓΧΥΣΕΩΣ
                                for idx, title in enumerate(["8. Μ/Σ ΤΑΣΕΩΣ", "9. Μ/Σ ΕΝΤΑΣΕΩΣ", "10. Μ/Σ ΕΓΧΥΣΕΩΣ"]):
                                    details_container.add_widget(Label(text=title, size_hint_y=None, height=25, bold=True))
                                    details_container.add_widget(TextInput(hint_text="ΟΠΤΙΚΟΣ ΕΛΕΓΧΟΣ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΔΙΑΡΡΟΩΝ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΣΥΣΦΙΞΕΩΝ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΑΝΤΙΣΤΑΣΗΣ ΜΟΝΩΣΗΣ", multiline=False, size_hint_y=None, height=30))

                                # Category 11: ΑΛΕΞΙΚΕΡΑΥΝΑ
                                details_container.add_widget(Label(text="11. ΑΛΕΞΙΚΕΡΑΥΝΑ", size_hint_y=None, height=25, bold=True))
                                details_container.add_widget(TextInput(hint_text="ΟΠΤΙΚΟΣ ΕΛΕΓΧΟΣ", multiline=False, size_hint_y=None, height=30))
                                details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΣΥΣΦΙΞΕΩΝ", multiline=False, size_hint_y=None, height=30))
                                details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΑΝΤΙΣΤΑΣΗΣ ΜΟΝΩΣΗΣ", multiline=False, size_hint_y=None, height=30))

                                # Category 12-13: Α/Ζ ΒΜΣ and Α/Ζ ΤΑΣΕΩΣ
                                for title in ["12. Α/Ζ ΒΜΣ", "13. Α/Ζ ΤΑΣΕΩΣ"]:
                                    details_container.add_widget(Label(text=title, size_hint_y=None, height=25, bold=True))
                                    details_container.add_widget(TextInput(hint_text="ΟΠΤΙΚΟΣ ΕΛΕΓΧΟΣ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΚΑΘΑΡΙΣΜΟΣ, ΛΙΠΑΝΣΗ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΣΥΣΦΙΞΕΩΝ", multiline=False, size_hint_y=None, height=30))

                                # Expose transformer widgets for persistence
                                measurements.setdefault("satyf_counter", satyf_counter)
                                measurements.setdefault("silica", silica_spinner)
                                measurements.setdefault("temp_fan", (fan_oil, fan_x1, fan_x3))
                                measurements.setdefault("temp_alarm", (alarm_oil, alarm_x1, alarm_x3))
                                measurements.setdefault("temp_trip", (trip_oil, trip_x1, trip_x3))
                                measurements.setdefault("diverter_res", (div_h1_a, div_h1_b, div_h2_a, div_h2_b, div_h3_a, div_h3_b))
                            except Exception as _ex:
                                import logging
                                logging.exception(f"Error building transformer UI for element {eid}: {_ex}")

                        elif is_breaker:
                            # Legacy breaker measurement UI (MV and other categories)
                            details_container.add_widget(
                                Label(
                                    text=S["MESSAGES"].get("INSULATION_MEASUREMENT_CLOSED_HEADER", "ΜΕΤΡΗΣΗ ΑΝΤΙΣΤΑΣΗΣ ΜΟΝΩΣΗΣ - ΔΙΑΚΟΠΤΗΣ ΚΛΕΙΣΤΟΣ (Φ-ΓΗ):"),
                                    size_hint_y=None,
                                    height=25,
                                    bold=True,
                                )
                            )

                            closed_fa_layout = BoxLayout(size_hint_y=None, height=30, spacing=3)
                            closed_fa_layout.add_widget(Label(text=S["MESSAGES"].get("INSULATION_LABEL_FA_GND", "ΦΑ-Γη:"), size_hint_x=0.15))
                            ins_closed_fa = TextInput(hint_text=S["MESSAGES"].get("INSULATION_HINT", "0.0"), size_hint_x=0.35, multiline=False)
                            closed_fa_layout.add_widget(ins_closed_fa)
                            ins_closed_fa_unit = Spinner(text="GΩ", values=["MΩ", "GΩ", "TΩ"], size_hint_x=0.15)
                            closed_fa_layout.add_widget(ins_closed_fa_unit)
                            closed_fa_layout.add_widget(Label(text="", size_hint_x=0.35))
                            details_container.add_widget(closed_fa_layout)

                            closed_fb_layout = BoxLayout(size_hint_y=None, height=30, spacing=3)
                            closed_fb_layout.add_widget(Label(text=S["MESSAGES"].get("INSULATION_LABEL_FB_GND", "ΦΒ-Γη:"), size_hint_x=0.15))
                            ins_closed_fb = TextInput(hint_text=S["MESSAGES"].get("INSULATION_HINT", "0.0"), size_hint_x=0.35, multiline=False)
                            closed_fb_layout.add_widget(ins_closed_fb)
                            ins_closed_fb_unit = Spinner(text="GΩ", values=["MΩ", "GΩ", "TΩ"], size_hint_x=0.15)
                            closed_fb_layout.add_widget(ins_closed_fb_unit)
                            closed_fb_layout.add_widget(Label(text="", size_hint_x=0.35))
                            details_container.add_widget(closed_fb_layout)

                            closed_fc_layout = BoxLayout(size_hint_y=None, height=30, spacing=3)
                            closed_fc_layout.add_widget(Label(text=S["MESSAGES"].get("INSULATION_LABEL_FC_GND", "ΦΓ-Γη:"), size_hint_x=0.15))
                            ins_closed_fc = TextInput(hint_text=S["MESSAGES"].get("INSULATION_HINT", "0.0"), size_hint_x=0.35, multiline=False)
                            closed_fc_layout.add_widget(ins_closed_fc)
                            ins_closed_fc_unit = Spinner(text="GΩ", values=["MΩ", "GΩ", "TΩ"], size_hint_x=0.15)
                            closed_fc_layout.add_widget(ins_closed_fc_unit)
                            closed_fc_layout.add_widget(Label(text="", size_hint_x=0.35))
                            details_container.add_widget(closed_fc_layout)

                            details_container.add_widget(Label(text=S["MESSAGES"].get("INSULATION_MEASUREMENT_OPEN_HEADER", "ΜΕΤΡΗΣΗ ΑΝΤΙΣΤΑΣΗΣ ΜΟΝΩΣΗΣ - ΔΙΑΚΟΠΤΗΣ ΑΝΟΙΧΤΟΣ (Φ-Φ):"), size_hint_y=None, height=25, bold=True))
                            open_fa_layout = BoxLayout(size_hint_y=None, height=30, spacing=3)
                            open_fa_layout.add_widget(Label(text=S["MESSAGES"].get("PHASE_TO_PHASE_LABEL_COLON", "ΦΑ-ΦΑ:"), size_hint_x=0.15))
                            ins_open_fa = TextInput(hint_text=S["MESSAGES"].get("INSULATION_HINT", "0.0"), size_hint_x=0.35, multiline=False)
                            open_fa_layout.add_widget(ins_open_fa)
                            ins_open_fa_unit = Spinner(text="GΩ", values=["MΩ", "GΩ", "TΩ"], size_hint_x=0.15)
                            open_fa_layout.add_widget(ins_open_fa_unit)
                            open_fa_layout.add_widget(Label(text="", size_hint_x=0.35))
                            details_container.add_widget(open_fa_layout)

                            open_fb_layout = BoxLayout(size_hint_y=None, height=30, spacing=3)
                            open_fb_layout.add_widget(Label(text=S["MESSAGES"].get("INSULATION_LABEL_FB", "ΦΒ-ΦΒ:"), size_hint_x=0.15))
                            ins_open_fb = TextInput(hint_text=S["MESSAGES"].get("INSULATION_HINT", "0.0"), size_hint_x=0.35, multiline=False)
                            open_fb_layout.add_widget(ins_open_fb)
                            ins_open_fb_unit = Spinner(text="GΩ", values=["MΩ", "GΩ", "TΩ"], size_hint_x=0.15)
                            open_fb_layout.add_widget(ins_open_fb_unit)
                            open_fb_layout.add_widget(Label(text="", size_hint_x=0.35))
                            details_container.add_widget(open_fb_layout)

                            open_fc_layout = BoxLayout(size_hint_y=None, height=30, spacing=3)
                            open_fc_layout.add_widget(Label(text=S["MESSAGES"].get("INSULATION_LABEL_FC", "ΦΓ-ΦΓ:"), size_hint_x=0.15))
                            ins_open_fc = TextInput(hint_text=S["MESSAGES"].get("INSULATION_HINT", "0.0"), size_hint_x=0.35, multiline=False)
                            open_fc_layout.add_widget(ins_open_fc)
                            ins_open_fc_unit = Spinner(text="GΩ", values=["MΩ", "GΩ", "TΩ"], size_hint_x=0.15)
                            open_fc_layout.add_widget(ins_open_fc_unit)
                            open_fc_layout.add_widget(Label(text="", size_hint_x=0.35))
                            details_container.add_widget(open_fc_layout)

                            details_container.add_widget(Label(text=S["MESSAGES"].get("INSULATION_PASSAGE_MEASUREMENT_CLOSED_HEADER", "ΑΝΤΙΣΤΑΣΗ ΔΙΕΛΕΥΣΗΣ (μΩ) - ΔΙΑΚΟΠΤΗΣ ΚΛΕΙΣΤΟΣ:"), size_hint_y=None, height=25, bold=True))
                            contact_layout = BoxLayout(size_hint_y=None, height=30, spacing=3)
                            contact_layout.add_widget(Label(text=S["MESSAGES"].get("PHASE_TO_PHASE_LABEL_COLON", "ΦΑ-ΦΑ:"), size_hint_x=0.15))
                            cont_fa = TextInput(hint_text=S["MESSAGES"].get("INSULATION_HINT", "0.0"), size_hint_x=0.25, multiline=False)
                            contact_layout.add_widget(cont_fa)
                            contact_layout.add_widget(Label(text=S["MESSAGES"].get("INSULATION_LABEL_FB", "ΦΒ-ΦΒ:"), size_hint_x=0.15))
                            cont_fb = TextInput(hint_text=S["MESSAGES"].get("INSULATION_HINT", "0.0"), size_hint_x=0.25, multiline=False)
                            contact_layout.add_widget(cont_fb)
                            contact_layout.add_widget(Label(text=S["MESSAGES"].get("INSULATION_LABEL_FC", "ΦΓ-ΦΓ:"), size_hint_x=0.15))
                            cont_fc = TextInput(hint_text=S["MESSAGES"].get("INSULATION_HINT", "0.0"), size_hint_x=0.25, multiline=False)
                            contact_layout.add_widget(cont_fc)
                            details_container.add_widget(contact_layout)

                            # expose ops_count and placeholders
                            try:
                                measurements.setdefault("ops_count", ops_count_input)
                            except Exception:
                                measurements.setdefault("ops_count", None)
                            measurements.setdefault("sf6", sf6_widgets)
                            measurements.setdefault("sf6_leakage", None)
                            measurements.setdefault("sf6_leak_methodology", None)
                            measurements.setdefault("vidar", vidar_widgets)
                            if breaker_category == "SF6":
                                sf6_leakage_input = TextInput(
                                    hint_text="kg", size_hint_x=0.25, multiline=False
                                )
                                sf6_methodology_input = TextInput(
                                    hint_text="Μεθοδολογία",
                                    size_hint_x=0.55,
                                    multiline=False,
                                )
                                leak_layout = BoxLayout(
                                    size_hint_y=None, height=30, spacing=3
                                )
                                leak_layout.add_widget(
                                    Label(text="Διαρροή SF6 (kg):", size_hint_x=0.45)
                                )
                                leak_layout.add_widget(sf6_leakage_input)
                                leak_layout.add_widget(Label(text="", size_hint_x=0.3))
                                details_container.add_widget(leak_layout)

                                method_layout = BoxLayout(
                                    size_hint_y=None, height=30, spacing=3
                                )
                                method_layout.add_widget(
                                    Label(
                                        text="Πλήρωση/Αντικατάσταση (Μεθοδολογία):",
                                        size_hint_x=0.45,
                                    )
                                )
                                method_layout.add_widget(sf6_methodology_input)
                                details_container.add_widget(method_layout)

                                details_container.add_widget(
                                    Label(
                                        text="ΠΟΙΟΤΗΤΑ ΑΕΡΙΟΥ SF6:",
                                        size_hint_y=None,
                                        height=25,
                                        bold=True,
                                    )
                                )

                                sf6_header = BoxLayout(
                                    size_hint_y=None, height=25, spacing=3
                                )
                                sf6_header.add_widget(Label(text="", size_hint_x=0.15))
                                sf6_header.add_widget(
                                    Label(
                                        text="SF6/N2 (%)", size_hint_x=0.28, bold=True
                                    )
                                )
                                sf6_header.add_widget(
                                    Label(
                                        text="H2O (°C atm)", size_hint_x=0.28, bold=True
                                    )
                                )
                                sf6_header.add_widget(
                                    Label(text="SO2 (ppm)", size_hint_x=0.28, bold=True)
                                )
                                details_container.add_widget(sf6_header)

                                sf6_fa_layout = BoxLayout(
                                    size_hint_y=None, height=30, spacing=3
                                )
                                sf6_fa_layout.add_widget(
                                    Label(text="ΦΑ:", size_hint_x=0.15)
                                )
                                sf6_n2_fa = TextInput(
                                    hint_text="0.0", size_hint_x=0.28, multiline=False
                                )
                                sf6_fa_layout.add_widget(sf6_n2_fa)
                                h2o_fa = TextInput(
                                    hint_text="0.0", size_hint_x=0.28, multiline=False
                                )
                                sf6_fa_layout.add_widget(h2o_fa)
                                so2_fa = TextInput(
                                    hint_text="0.0", size_hint_x=0.28, multiline=False
                                )
                                sf6_fa_layout.add_widget(so2_fa)
                                details_container.add_widget(sf6_fa_layout)

                                sf6_fb_layout = BoxLayout(
                                    size_hint_y=None, height=30, spacing=3
                                )
                                sf6_fb_layout.add_widget(
                                    Label(text="ΦΒ:", size_hint_x=0.15)
                                )
                                sf6_n2_fb = TextInput(
                                    hint_text="0.0", size_hint_x=0.28, multiline=False
                                )
                                sf6_fb_layout.add_widget(sf6_n2_fb)
                                h2o_fb = TextInput(
                                    hint_text="0.0", size_hint_x=0.28, multiline=False
                                )
                                sf6_fb_layout.add_widget(h2o_fb)
                                so2_fb = TextInput(
                                    hint_text="0.0", size_hint_x=0.28, multiline=False
                                )
                                sf6_fb_layout.add_widget(so2_fb)
                                details_container.add_widget(sf6_fb_layout)

                                sf6_fc_layout = BoxLayout(
                                    size_hint_y=None, height=30, spacing=3
                                )
                                sf6_fc_layout.add_widget(
                                    Label(text="ΦΓ:", size_hint_x=0.15)
                                )
                                sf6_n2_fc = TextInput(
                                    hint_text="0.0", size_hint_x=0.28, multiline=False
                                )
                                sf6_fc_layout.add_widget(sf6_n2_fc)
                                h2o_fc = TextInput(
                                    hint_text="0.0", size_hint_x=0.28, multiline=False
                                )
                                sf6_fc_layout.add_widget(h2o_fc)
                                so2_fc = TextInput(
                                    hint_text="0.0", size_hint_x=0.28, multiline=False
                                )
                                sf6_fc_layout.add_widget(so2_fc)
                                details_container.add_widget(sf6_fc_layout)

                                sf6_widgets = {
                                    "sf6_n2_fa": sf6_n2_fa,
                                    "h2o_fa": h2o_fa,
                                    "so2_fa": so2_fa,
                                    "sf6_n2_fb": sf6_n2_fb,
                                    "h2o_fb": h2o_fb,
                                    "so2_fb": so2_fb,
                                    "sf6_n2_fc": sf6_n2_fc,
                                    "h2o_fc": h2o_fc,
                                    "so2_fc": so2_fc,
                                }
                            else:
                                sf6_leakage_input = None
                                sf6_methodology_input = None

                            # VIDAR (vacuum) inputs for MV Vacuum breakers (single-row layout)
                            if elem_type == self.ELEM_BREAKER_MT and breaker_category in ["Vacuum", "Κενού"]:
                                details_container.add_widget(
                                    Label(
                                        text=S["MESSAGES"].get("VIDAR_VACUUM_CHECK_LABEL", "ΕΛΕΓΧΟΣ ΚΕΝΟΥ (VIDAR):"),
                                        size_hint_y=None,
                                        height=25,
                                        bold=True,
                                    )
                                )

                                vidar_layout = BoxLayout(size_hint_y=None, height=30, spacing=3)
                                vidar_layout.add_widget(Label(text=S["MESSAGES"].get("PHASE_TO_PHASE_LABEL_COLON", "ΦΑ-ΦΑ:"), size_hint_x=0.15))
                                vidar_fa = TextInput(hint_text=S["MESSAGES"].get("VIDAR_HINT", "0.0"), size_hint_x=0.25, multiline=False)
                                vidar_layout.add_widget(vidar_fa)
                                vidar_layout.add_widget(Label(text=S["MESSAGES"].get("VIDAR_LABEL_FB", "ΦΒ-ΦΒ:"), size_hint_x=0.15))
                                vidar_fb = TextInput(hint_text=S["MESSAGES"].get("VIDAR_HINT", "0.0"), size_hint_x=0.25, multiline=False)
                                vidar_layout.add_widget(vidar_fb)
                                vidar_layout.add_widget(Label(text=S["MESSAGES"].get("VIDAR_LABEL_FC", "ΦΓ-ΦΓ:"), size_hint_x=0.15))
                                vidar_fc = TextInput(hint_text=S["MESSAGES"].get("VIDAR_HINT", "0.0"), size_hint_x=0.25, multiline=False)
                                vidar_layout.add_widget(vidar_fc)
                                details_container.add_widget(vidar_layout)

                                vidar_widgets = {
                                    "vidar_fa": vidar_fa,
                                    "vidar_fb": vidar_fb,
                                    "vidar_fc": vidar_fc,
                                }

                            # Transformer 150/20kV maintenance form (per-element)
                            if self._is_transformer(elem_type):
                                try:
                                    # Fetch stored power (MVA) for this element
                                    try:
                                        c = self.conn.cursor()
                                        c.execute("SELECT e.power_mva, em.power_mva FROM elements e LEFT JOIN element_models em ON e.element_model_id = em.id WHERE e.id=?", (eid,))
                                        row = c.fetchone()
                                        if row:
                                            power_val = str(row[1]) if row[1] is not None else (str(row[0]) if row[0] is not None else "")
                                        else:
                                            power_val = ""
                                    except Exception:
                                        power_val = ""

                                        # power is element attribute; not editable in maintenance form

                                    # Category: ΧΕΙΡΙΣΜΟΙ
                                    details_container.add_widget(Label(text="ΧΕΙΡΙΣΜΟΙ", size_hint_y=None, height=25, bold=True))
                                    ops_row = BoxLayout(size_hint_y=None, height=30, spacing=6)
                                    ops_row.add_widget(Label(text="Απαριθμητής ΣΑΤΥΦ:", size_hint_x=0.6))
                                    satyf_counter = TextInput(hint_text="Αριθμός Χειρισμών", multiline=False, size_hint_x=0.12)
                                    ops_row.add_widget(satyf_counter)
                                    ops_row.add_widget(Widget())
                                    details_container.add_widget(ops_row)

                                    # Category 1: ΜΟΝΩΤΗΡΕΣ Υ.Τ & Μ.Τ
                                    details_container.add_widget(Label(text="1. ΜΟΝΩΤΗΡΕΣ Υ.Τ & Μ.Τ", size_hint_y=None, height=25, bold=True))
                                    details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΓΙΑ ΘΡΑΥΣΗ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΔΙΑΡΡΟΕΣ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΚΑΘΑΡΙΣΜΟΣ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΑΚΙΔΕΣ", multiline=False, size_hint_y=None, height=30))

                                    # Category 2: ΛΑΔΙΑ Μ/Σ
                                    details_container.add_widget(Label(text="2. ΛΑΔΙΑ Μ/Σ", size_hint_y=None, height=25, bold=True))
                                    details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΣΤΑΘΜΗΣ ΕΛΑΙΟΥ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΣΥΜΠΛΗΡΩΣΗ ΕΛΑΙΟΥ", multiline=False, size_hint_y=None, height=30))
                                    silica_row = BoxLayout(size_hint_y=None, height=30, spacing=6)
                                    silica_row.add_widget(Label(text="ΣΙΛΙΚΑ:", size_hint_x=0.4))
                                    silica_spinner = Spinner(text="N/A", values=["OK", "NOT OK", "N/A"], size_hint_x=0.2)
                                    silica_row.add_widget(silica_spinner)
                                    silica_row.add_widget(Widget())
                                    details_container.add_widget(silica_row)

                                    # Category 3: ΑΚΡΟΔΕΚΤΕΣ ΣΥΝΔΕΣΜΟΙ
                                    details_container.add_widget(Label(text="3. ΑΚΡΟΔΕΚΤΕΣ ΣΥΝΔΕΣΜΟΙ", size_hint_y=None, height=25, bold=True))
                                    details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΣΥΣΦΙΞΗΣ ΚΟΧΛΙΩΝ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΕΥΚΑΜΠΤΩΝ ΣΥΝΔΕΣΜΩΝ", multiline=False, size_hint_y=None, height=30))

                                    # Category 4: ΣΩΜΑ Μ/Σ
                                    details_container.add_widget(Label(text="4. ΣΩΜΑ Μ/Σ", size_hint_y=None, height=25, bold=True))
                                    details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΔΙΑΡΡΟΩΝ ΕΛΑΙΟΥ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΣΤΕΓΑΝΟΠΟΙΗΣΗ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΚΑΘΑΡΙΣΜΟΣ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΑΝΑΚΟΥΦΙΣΤΙΚΩΝ ΒΑΛΒΙΔΩΝ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΠΡΕΣΣΟΣΤΑΤΙΚΩΝ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ BUCHOLZ", multiline=False, size_hint_y=None, height=30))

                                    # 7x7 table for temperature checks header and inputs (3x3 values with labels)
                                    details_container.add_widget(Label(text="ΈΛΕΓΧΟΣ ΘΕΡΜΟΣΤΟΙΧΕΙΩΝ (°C)", size_hint_y=None, height=25, bold=True))
                                    temp_header = BoxLayout(size_hint_y=None, height=30)
                                    temp_header.add_widget(Label(text="", size_hint_x=0.2))
                                    temp_header.add_widget(Label(text="OIL", size_hint_x=0.26))
                                    temp_header.add_widget(Label(text="X1", size_hint_x=0.26))
                                    temp_header.add_widget(Label(text="X3", size_hint_x=0.28))
                                    details_container.add_widget(temp_header)

                                    # Rows: FAN, ALARM, TRIP
                                    fan_row = BoxLayout(size_hint_y=None, height=32)
                                    fan_row.add_widget(Label(text="FAN", size_hint_x=0.2))
                                    fan_oil = TextInput(hint_text="", multiline=False)
                                    fan_x1 = TextInput(hint_text="", multiline=False)
                                    fan_x3 = TextInput(hint_text="", multiline=False)
                                    fan_row.add_widget(fan_oil)
                                    fan_row.add_widget(fan_x1)
                                    fan_row.add_widget(fan_x3)
                                    details_container.add_widget(fan_row)

                                    alarm_row = BoxLayout(size_hint_y=None, height=32)
                                    alarm_row.add_widget(Label(text="ALARM", size_hint_x=0.2))
                                    alarm_oil = TextInput(hint_text="", multiline=False)
                                    alarm_x1 = TextInput(hint_text="", multiline=False)
                                    alarm_x3 = TextInput(hint_text="", multiline=False)
                                    alarm_row.add_widget(alarm_oil)
                                    alarm_row.add_widget(alarm_x1)
                                    alarm_row.add_widget(alarm_x3)
                                    details_container.add_widget(alarm_row)

                                    trip_row = BoxLayout(size_hint_y=None, height=32)
                                    trip_row.add_widget(Label(text="TRIP", size_hint_x=0.2))
                                    trip_oil = TextInput(hint_text="", multiline=False)
                                    trip_x1 = TextInput(hint_text="", multiline=False)
                                    trip_x3 = TextInput(hint_text="", multiline=False)
                                    trip_row.add_widget(trip_oil)
                                    trip_row.add_widget(trip_x1)
                                    trip_row.add_widget(trip_x3)
                                    details_container.add_widget(trip_row)

                                    # Category 5: ΣΑΤΥΦ - ΜΗΧΑΝΙΣΜΟΣ
                                    details_container.add_widget(Label(text="5. ΣΑΤΥΦ - ΜΗΧΑΝΙΣΜΟΣ", size_hint_y=None, height=25, bold=True))
                                    details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΑΞΟΝΩΝ ΜΕΤΑΔΟΣΗΣ ΚΙΝΗΣΗΣ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΚΑΘΑΡΙΣΜΟΣ, ΛΙΠΑΝΣΗ ΑΡΘΡΩΣΕΩΝ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΚΑΘΑΡΙΣΜΟΣ, ΛΙΠΑΝΣΗ ΟΔΟΝΤΩΤΩΝ ΤΡΟΧΩΝ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΔΟΚΙΜΑΣΤΙΚΟΙ ΧΕΙΡΙΣΜΟΙ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΡΩΓΜΩΝ ΣΤΟ ΧΩΡΟ ΤΟΥ DIVERTER", multiline=False, size_hint_y=None, height=30))

                                    # Category 6: DIVERTER – ΜΕΤΑΓΩΓΙΚΟΣ ΔΙΑΚΟΠΤΗΣ
                                    details_container.add_widget(Label(text="6. DIVERTER – ΜΕΤΑΓΩΓΙΚΟΣ ΔΙΑΚΟΠΤΗΣ", size_hint_y=None, height=25, bold=True))
                                    details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΕΠΑΦΩΝ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΣΥΣΦΙΞΕΙΣ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΑΛΛΑΓΗ ΛΑΔΙΩΝ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ALARM ΧΑΜΗΛΗΣ ΣΤΑΘΜΗΣ ΛΑΔΙΟΥ", multiline=False, size_hint_y=None, height=30))

                                    # Diverter resistance measurements (6 values: H1 x2, H2 x2, H3 x2)
                                    details_container.add_widget(Label(text=S["MESSAGES"].get("MEASUREMENT_RESISTANCE_HEADER", "ΜΕΤΡΗΣΗ ΑΝΤΙΣΤΑΣΗΣ (Ω)"), size_hint_y=None, height=25, bold=True))
                                    div_row1 = BoxLayout(size_hint_y=None, height=32)
                                    div_h1_a = TextInput(hint_text="H1-1", multiline=False)
                                    div_h1_b = TextInput(hint_text="H1-2", multiline=False)
                                    div_row1.add_widget(div_h1_a)
                                    div_row1.add_widget(div_h1_b)
                                    details_container.add_widget(div_row1)
                                    div_row2 = BoxLayout(size_hint_y=None, height=32)
                                    div_h2_a = TextInput(hint_text="H2-1", multiline=False)
                                    div_h2_b = TextInput(hint_text="H2-2", multiline=False)
                                    div_row2.add_widget(div_h2_a)
                                    div_row2.add_widget(div_h2_b)
                                    details_container.add_widget(div_row2)
                                    div_row3 = BoxLayout(size_hint_y=None, height=32)
                                    div_h3_a = TextInput(hint_text="H3-1", multiline=False)
                                    div_h3_b = TextInput(hint_text="H3-2", multiline=False)
                                    div_row3.add_widget(div_h3_a)
                                    div_row3.add_widget(div_h3_b)
                                    details_container.add_widget(div_row3)

                                    # Category 7: ΑΝΤΙΣΤΑΣΗ ΚΟΜΒΟΥ Μ/Σ
                                    details_container.add_widget(Label(text="7. ΑΝΤΙΣΤΑΣΗ ΚΟΜΒΟΥ Μ/Σ", size_hint_y=None, height=25, bold=True))
                                    details_container.add_widget(TextInput(hint_text="ΚΑΘΑΡΙΣΜΟΣ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΜΕΤΡΗΣΗ (Ω)", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΣΥΣΦΙΞΕΙΣ", multiline=False, size_hint_y=None, height=30))

                                    # Category 8-10: ΤΑΣΕΩΣ/ΕΝΤΑΣΕΩΣ/ΕΓΧΥΣΕΩΣ
                                    for idx, title in enumerate(["8. Μ/Σ ΤΑΣΕΩΣ", "9. Μ/Σ ΕΝΤΑΣΕΩΣ", "10. Μ/Σ ΕΓΧΥΣΕΩΣ"]):
                                        details_container.add_widget(Label(text=title, size_hint_y=None, height=25, bold=True))
                                        details_container.add_widget(TextInput(hint_text="ΟΠΤΙΚΟΣ ΕΛΕΓΧΟΣ", multiline=False, size_hint_y=None, height=30))
                                        details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΔΙΑΡΡΟΩΝ", multiline=False, size_hint_y=None, height=30))
                                        details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΣΥΣΦΙΞΕΩΝ", multiline=False, size_hint_y=None, height=30))
                                        details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΑΝΤΙΣΤΑΣΗΣ ΜΟΝΩΣΗΣ", multiline=False, size_hint_y=None, height=30))

                                    # Category 11: ΑΛΕΞΙΚΕΡΑΥΝΑ
                                    details_container.add_widget(Label(text="11. ΑΛΕΞΙΚΕΡΑΥΝΑ", size_hint_y=None, height=25, bold=True))
                                    details_container.add_widget(TextInput(hint_text="ΟΠΤΙΚΟΣ ΕΛΕΓΧΟΣ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΣΥΣΦΙΞΕΩΝ", multiline=False, size_hint_y=None, height=30))
                                    details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΑΝΤΙΣΤΑΣΗΣ ΜΟΝΩΣΗΣ", multiline=False, size_hint_y=None, height=30))

                                    # Category 12-13: Α/Ζ ΒΜΣ and Α/Ζ ΤΑΣΕΩΣ
                                    for title in ["12. Α/Ζ ΒΜΣ", "13. Α/Ζ ΤΑΣΕΩΣ"]:
                                        details_container.add_widget(Label(text=title, size_hint_y=None, height=25, bold=True))
                                        details_container.add_widget(TextInput(hint_text="ΟΠΤΙΚΟΣ ΕΛΕΓΧΟΣ", multiline=False, size_hint_y=None, height=30))
                                        details_container.add_widget(TextInput(hint_text="ΚΑΘΑΡΙΣΜΟΣ, ΛΙΠΑΝΣΗ", multiline=False, size_hint_y=None, height=30))
                                        details_container.add_widget(TextInput(hint_text="ΕΛΕΓΧΟΣ ΣΥΣΦΙΞΕΩΝ", multiline=False, size_hint_y=None, height=30))

                                    # Expose transformer widgets for persistence
                                    measurements.setdefault("satyf_counter", satyf_counter)
                                    measurements.setdefault("silica", silica_spinner)
                                    measurements.setdefault("temp_fan", (fan_oil, fan_x1, fan_x3))
                                    measurements.setdefault("temp_alarm", (alarm_oil, alarm_x1, alarm_x3))
                                    measurements.setdefault("temp_trip", (trip_oil, trip_x1, trip_x3))
                                    measurements.setdefault("diverter_res", (div_h1_a, div_h1_b, div_h2_a, div_h2_b, div_h3_a, div_h3_b))
                                except Exception:
                                    import logging
                                    logging.exception('Error building transformer UI for element %s', eid)

                            # Build measurements dict according to branch. For HV oil breakers
                            # we only include the oil-specific widgets added above; for other
                            # breakers include the legacy insulation/contact fields.
                            # For breakers include breaker-specific measurement widgets.
                            # Do not overwrite `measurements` for transformers (they are
                            # handled above and will already contain transformer widgets).
                            if is_hv_oil or is_hv_sf6:
                                try:
                                    measurements.setdefault("ops_count", ops_count_input)
                                except Exception:
                                    measurements.setdefault("ops_count", None)
                                measurements.setdefault("sf6", sf6_widgets)
                                measurements.setdefault("sf6_leakage", sf6_leakage_input)
                                measurements.setdefault("sf6_leak_methodology", sf6_methodology_input)
                                measurements.setdefault("vidar", vidar_widgets)
                            elif is_breaker:
                                # Legacy breaker measurement UI (populate only for breakers)
                                measurements = {
                                    "ins_closed_fa": ins_closed_fa,
                                    "ins_closed_fa_unit": ins_closed_fa_unit,
                                    "ins_closed_fb": ins_closed_fb,
                                    "ins_closed_fb_unit": ins_closed_fb_unit,
                                    "ins_closed_fc": ins_closed_fc,
                                    "ins_closed_fc_unit": ins_closed_fc_unit,
                                    "ins_open_fa": ins_open_fa,
                                    "ins_open_fa_unit": ins_open_fa_unit,
                                    "ins_open_fb": ins_open_fb,
                                    "ins_open_fb_unit": ins_open_fb_unit,
                                    "ins_open_fc": ins_open_fc,
                                    "ins_open_fc_unit": ins_open_fc_unit,
                                    "cont_fa": cont_fa,
                                    "cont_fb": cont_fb,
                                    "cont_fc": cont_fc,
                                    "ops_count": ops_count_input,
                                    "sf6": sf6_widgets,
                                    "sf6_leakage": sf6_leakage_input,
                                    "sf6_leak_methodology": sf6_methodology_input,
                                    "vidar": vidar_widgets,
                                }

                        if has_measurement_form and measurements_fields_container is not None:
                            fixed_widgets = {
                                elem_comments,
                                measurements_toggle_row,
                                measurements_fields_container,
                            }
                            measurement_widgets = [
                                widget
                                for widget in list(reversed(details_container.children))
                                if widget not in fixed_widgets
                            ]

                            for widget in measurement_widgets:
                                if widget.parent is details_container:
                                    details_container.remove_widget(widget)
                            for widget in measurement_widgets:
                                measurements_fields_container.add_widget(widget)

                            if measurements_fields_container.parent is details_container:
                                details_container.remove_widget(measurements_fields_container)

                            def _toggle_measurements(
                                _cb,
                                active,
                                dc=details_container,
                                mfc=measurements_fields_container,
                            ):
                                if active:
                                    if mfc.parent is None:
                                        dc.add_widget(mfc)
                                else:
                                    if mfc.parent is dc:
                                        dc.remove_widget(mfc)

                            measurements_toggle.bind(active=_toggle_measurements)

                        # Save into per-element storage (use eid)
                        element_widgets.setdefault(eid, {})
                        element_widgets[eid]["details_container"] = details_container
                        element_widgets[eid]["comments"] = elem_comments
                        element_widgets[eid]["measurements"] = measurements
                        element_widgets[eid]["measurements_toggle"] = measurements_toggle

                        # saved details_container

                    def ensure_details(elem_box=elem_box, eid=elem_id):
                        # ensure_details debug removed
                        build_details_for(eid)
                        dc = element_widgets.get(eid, {}).get("details_container")
                        # ensure_details found debug removed
                        if dc is not None and dc not in elem_box.children:
                            # details_container child inspection debug removed
                            elem_box.add_widget(dc)

                    def toggle_details(_checkbox_instance, value, elem_box=elem_box, eid=elem_id):
                                        # toggle_details debug removed
                                        if value:
                                            ensure_details(elem_box, eid)
                                        else:
                                            dc = element_widgets.get(eid, {}).get("details_container")
                                            if dc is not None and dc in elem_box.children:
                                                elem_box.remove_widget(dc)

                    checkbox.bind(active=toggle_details)

                    # Checkbox active handler (no debug logging)
                    def _on_checkbox_active(instance, value, eid=elem_id):
                        return

                    checkbox.bind(active=_on_checkbox_active)

                    elements_container.add_widget(elem_box)

                    spacing = Label(text="", size_hint_y=None, height=5)
                    elements_container.add_widget(spacing)

                    # Update existing element_widgets entry instead of overwriting
                    element_widgets.setdefault(elem_id, {})
                    element_widgets[elem_id].update(
                        {
                            "checkbox": checkbox,
                            "label": elem_label,
                            "display": elem_display,
                            "comments": element_widgets[elem_id].get("comments"),
                            "measurements": element_widgets[elem_id].get("measurements"),
                            "measurements_toggle": element_widgets[elem_id].get("measurements_toggle"),
                            "elem_type": elem_type,
                            "details_container": element_widgets[elem_id].get(
                                "details_container"
                            ),
                            "ensure_details": ensure_details,
                        }
                    )

            if not maintenance_id and prefill_data.get("element_ids"):
                prefill_elements = set(prefill_data.get("element_ids"))
                incomplete_elements = set(prefill_data.get("incomplete_elements") or [])
                for elem_id in prefill_elements:
                    if elem_id not in element_widgets:
                        continue
                    widgets = element_widgets[elem_id]
                    widgets["checkbox"].active = True
                    widgets["ensure_details"]()
                    if elem_id in incomplete_elements:
                        widgets["label"].text = (
                            f"[color=ff3333]{widgets['display']}[/color]"
                        )

            if maintenance_id and existing_elements_data:
                for elem_id, data in existing_elements_data.items():
                    if elem_id not in element_widgets:
                        continue
                    widgets = element_widgets[elem_id]
                    widgets["checkbox"].active = True
                    widgets["ensure_details"]()
                    widgets["comments"].text = data.get("element_comments", "")

                    measurements = widgets["measurements"] or {}
                    if measurements:
                        # Safely set measurement widget texts only when the widget exists
                        w = measurements.get("ins_closed_fa")
                        if data.get("ins_closed_fa") is not None and w:
                            w.text = str(data.get("ins_closed_fa"))
                        w = measurements.get("ins_closed_fa_unit")
                        if w:
                            w.text = data.get("ins_closed_fa_unit", "GΩ")

                        w = measurements.get("ins_closed_fb")
                        if data.get("ins_closed_fb") is not None and w:
                            w.text = str(data.get("ins_closed_fb"))
                        w = measurements.get("ins_closed_fb_unit")
                        if w:
                            w.text = data.get("ins_closed_fb_unit", "GΩ")

                        w = measurements.get("ins_closed_fc")
                        if data.get("ins_closed_fc") is not None and w:
                            w.text = str(data.get("ins_closed_fc"))
                        w = measurements.get("ins_closed_fc_unit")
                        if w:
                            w.text = data.get("ins_closed_fc_unit", "GΩ")

                        w = measurements.get("ins_open_fa")
                        if data.get("ins_open_fa") is not None and w:
                            w.text = str(data.get("ins_open_fa"))
                        w = measurements.get("ins_open_fa_unit")
                        if w:
                            w.text = data.get("ins_open_fa_unit", "GΩ")

                        w = measurements.get("ins_open_fb")
                        if data.get("ins_open_fb") is not None and w:
                            w.text = str(data.get("ins_open_fb"))
                        w = measurements.get("ins_open_fb_unit")
                        if w:
                            w.text = data.get("ins_open_fb_unit", "GΩ")

                        w = measurements.get("ins_open_fc")
                        if data.get("ins_open_fc") is not None and w:
                            w.text = str(data.get("ins_open_fc"))
                        w = measurements.get("ins_open_fc_unit")
                        if w:
                            w.text = data.get("ins_open_fc_unit", "GΩ")

                        w = measurements.get("cont_fa")
                        if data.get("cont_fa") is not None and w:
                            w.text = str(data.get("cont_fa"))
                        w = measurements.get("cont_fb")
                        if data.get("cont_fb") is not None and w:
                            w.text = str(data.get("cont_fb"))
                        w = measurements.get("cont_fc")
                        if data.get("cont_fc") is not None and w:
                            w.text = str(data.get("cont_fc"))

                        w = measurements.get("ops_count")
                        if data.get("ops_count") is not None and w:
                            w.text = str(data.get("ops_count"))

                        sf6_widgets = measurements.get("sf6")
                        if sf6_widgets:
                            for key, widget in sf6_widgets.items():
                                if data.get("sf6") and data["sf6"].get(key) is not None:
                                    widget.text = str(data["sf6"].get(key))

                        if (
                            measurements.get("sf6_leakage")
                            and data.get("sf6_leakage_kg") is not None
                        ):
                            measurements["sf6_leakage"].text = str(
                                data.get("sf6_leakage_kg")
                            )

                        if measurements.get("sf6_leak_methodology") and data.get(
                            "sf6_leak_methodology"
                        ):
                            measurements["sf6_leak_methodology"].text = str(
                                data.get("sf6_leak_methodology")
                            )

                        vidar_widgets = measurements.get("vidar")
                        if vidar_widgets:
                            for key, widget in vidar_widgets.items():
                                if data.get("vidar") and data["vidar"].get(key) is not None:
                                    widget.text = str(data["vidar"].get(key))

                        measurement_toggle = widgets.get("measurements_toggle")
                        if measurement_toggle:
                            has_existing_measurements = any(
                                data.get(key) is not None
                                for key in (
                                    "ins_closed_fa",
                                    "ins_closed_fb",
                                    "ins_closed_fc",
                                    "ins_open_fa",
                                    "ins_open_fb",
                                    "ins_open_fc",
                                    "cont_fa",
                                    "cont_fb",
                                    "cont_fc",
                                    "ops_count",
                                    "sf6_leakage_kg",
                                )
                            )
                            has_existing_measurements = has_existing_measurements or bool(
                                data.get("sf6_leak_methodology")
                            )
                            has_existing_measurements = has_existing_measurements or any(
                                value is not None
                                for value in (data.get("sf6") or {}).values()
                            )
                            has_existing_measurements = has_existing_measurements or any(
                                value is not None
                                for value in (data.get("vidar") or {}).values()
                            )
                            if has_existing_measurements:
                                measurement_toggle.active = True

        # Load initial elements
        load_elements(substation_input.text)

        # Update elements when substation changes (via selection callback)

        # Add scrollable content to scroll view
        scroll_view.add_widget(content_layout)

        # Main layout with scroll view and buttons
        main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
        main_layout.add_widget(scroll_view)

        # Add-element button row (inside scrollable area, below elements)
        add_element_row = BoxLayout(size_hint_y=None, height=45, spacing=10)

        def add_element_from_maintenance():
            substation_name = substation_input.text
            substation_id = substation_map.get(substation_name)
            if not substation_id:
                show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"].get("SUBSTATION_NOT_FOUND", "Δεν βρέθηκε υποσταθμός."))
                return
            self.show_add_element_popup_for_substation(
                substation_id, substation_name, popup
            )

        add_element_btn = Button(text=S["BUTTONS"]["ADD"] + " Στοιχείου", size_hint_x=None)
        add_element_btn.bind(on_press=lambda x: add_element_from_maintenance())

        def _resize_add_button(*_args):
            min_width = Window.width * 0.3
            # add a slightly larger margin to avoid a single-character clipping
            text_width = add_element_btn.texture_size[0] + 60
            add_element_btn.width = max(min_width, text_width)

        add_element_btn.bind(texture_size=lambda *_: _resize_add_button())
        Window.bind(size=lambda *_: _resize_add_button())
        # schedule one resize after layout so initial texture metrics are correct
        from kivy.clock import Clock
        Clock.schedule_once(lambda dt: _resize_add_button(), 0)

        add_element_row.add_widget(Widget())
        add_element_row.add_widget(add_element_btn)
        add_element_row.add_widget(Widget())

        content_layout.add_widget(add_element_row)

        # Buttons at the bottom (not scrollable)
        buttons_layout = BoxLayout(size_hint_y=None, height=50, spacing=10)

        def save_maintenance():
            nonlocal maintenance_id
            # Validate at least one element selected
            selected_elements = [
                (eid, widgets)
                for eid, widgets in element_widgets.items()
                if widgets["checkbox"].active
            ]

            # selected_elements prepared

            if not selected_elements:
                show_message_popup(
                    S["TITLES"]["ERROR"], S["MESSAGES"].get("SELECT_AT_LEAST_ONE_ELEMENT", "Πρέπει να επιλέξετε τουλάχιστον ένα στοιχείο!")
                )
                return

            if not datetime_input.text.strip():
                show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"].get("DATE_REQUIRED", "Η ημερομηνία είναι υποχρεωτική!"))
                return

            if not responsible_spinner.text:
                show_message_popup(
                    S["TITLES"]["ERROR"], S["MESSAGES"].get("RESPONSIBLE_REQUIRED", "Ο υπεύθυνος συντήρησης είναι υποχρεωτικός!")
                )
                return

            # Insert/update maintenance record with type and user
            substation_id = substation_map[substation_input.text]
            maintenance_date = datetime_input.text.strip()
            maintenance_type = maintenance_type_spinner.text
            user_name = ""
            maintenance_name = self._build_maintenance_name(
                substation_input.text, maintenance_date
            )
            responsible_id = people_map.get(responsible_spinner.text)

            if maintenance_id:
                c.execute(
                    """UPDATE maintenance
                       SET substation_id=?, name=?, date_time=?, overall_comments=?, maintenance_type=?, user_name=?, responsible_id=?, onedrive_media_folder_link=?
                       WHERE id=?""",
                    (
                        substation_id,
                        maintenance_name,
                        maintenance_date,
                        overall_comments.text.strip(),
                        maintenance_type,
                        user_name,
                        responsible_id,
                        onedrive_media_link.text.strip() or None,
                        maintenance_id,
                    ),
                )
                c.execute(
                    "DELETE FROM maintenance_people WHERE maintenance_id=?",
                    (maintenance_id,),
                )
                c.execute(
                    "DELETE FROM maintenance_elements WHERE maintenance_id=?",
                    (maintenance_id,),
                )
            else:
                c.execute(
                    "INSERT INTO maintenance (substation_id, name, date_time, overall_comments, maintenance_type, user_name, responsible_id, onedrive_media_folder_link) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        substation_id,
                        maintenance_name,
                        maintenance_date,
                        overall_comments.text.strip(),
                        maintenance_type,
                        user_name,
                        responsible_id,
                        onedrive_media_link.text.strip() or None,
                    ),
                )
                maintenance_id = c.lastrowid

            # Store responsible and crew in maintenance_people
            if responsible_id:
                c.execute(
                    "INSERT INTO maintenance_people (maintenance_id, person_id, role) VALUES (?, ?, ?)",
                    (maintenance_id, responsible_id, "responsible"),
                )

            selected_crew_ids = [
                pid for pid, cb in crew_checks.items() if cb.active and pid != responsible_id
            ]
            for pid in selected_crew_ids:
                if pid != responsible_id:
                    c.execute(
                        "INSERT INTO maintenance_people (maintenance_id, person_id, role) VALUES (?, ?, ?)",
                        (maintenance_id, pid, "crew"),
                    )

            if prefill_data.get("_diag_origin") == "email_ui_prefill":
                detected_crew = set(prefill_data.get("_diag_detected_crew_ids") or [])
                final_crew = set(selected_crew_ids)
                log_import_diagnostic(
                    "email_ui_people_saved",
                    maintenance_id=maintenance_id,
                    substation_id=substation_id,
                    sender_name=prefill_data.get("_diag_sender_name") or "",
                    subject=prefill_data.get("_diag_subject") or "",
                    detected_responsible_id=prefill_data.get("_diag_detected_responsible_id"),
                    final_responsible_id=responsible_id,
                    detected_crew_ids=sorted(detected_crew),
                    final_crew_ids=sorted(final_crew),
                    crew_added_after_prefill=sorted(final_crew - detected_crew),
                    crew_removed_after_prefill=sorted(detected_crew - final_crew),
                )

            # Insert maintenance elements and update their maintenance_date
            for elem_id, widgets in selected_elements:
                # Prepare measurement values
                measurements = widgets["measurements"]

                if measurements:  # Circuit breaker with measurements
                    # Helper to parse float or None
                    def parse_float(val):
                        try:
                            return float(val.strip()) if val.strip() else None
                        except Exception:
                            return None

                    # Parse operations count (guard widget presence)
                    ops_count = None
                    try:
                        ops_w = measurements.get("ops_count")
                        if ops_w and getattr(ops_w, "text", None) and ops_w.text.strip():
                            try:
                                ops_count = int(ops_w.text)
                            except Exception:
                                ops_count = None
                    except Exception:
                        ops_count = None

                    # Parse SF6 measurements if present
                    sf6_vals = {}
                    sf6_widgets = measurements.get("sf6")
                    if sf6_widgets:
                        for key, widget in sf6_widgets.items():
                            sf6_vals[key] = parse_float(widget.text)

                    sf6_leakage_val = None
                    if measurements.get("sf6_leakage"):
                        sf6_leakage_val = parse_float(measurements["sf6_leakage"].text)

                    sf6_leak_methodology_val = None
                    if measurements.get("sf6_leak_methodology"):
                        sf6_leak_methodology_val = (
                            measurements["sf6_leak_methodology"].text.strip() or None
                        )

                    if sf6_leakage_val is not None and not sf6_leak_methodology_val:
                        show_message_popup(
                            S["TITLES"].get("ERROR", "Σφάλμα"),
                            S["MESSAGES"].get("SF6_LEAK_METHODOLOGY_REQUIRED", "Για διαρροή SF6 απαιτείται συμπλήρωση μεθοδολογίας (Πλήρωση/Αντικατάσταση)."),
                        )
                        return

                    # Parse VIDAR (vacuum) measurements when present
                    vidar_vals = {}
                    vidar_widgets = measurements.get("vidar")
                    if vidar_widgets:
                        for key, widget in vidar_widgets.items():
                            try:
                                vidar_vals[key] = float(widget.text) if widget.text.strip() else None
                            except Exception:
                                try:
                                    vidar_vals[key] = float(widget.text.replace(',','.'))
                                except Exception:
                                    vidar_vals[key] = None

                    # Build extra JSON for arbitrary/new form fields (transformer, etc.)
                    extra = {}
                    try:
                        if measurements.get("power_mva"):
                            t = measurements["power_mva"].text.strip()
                            if t:
                                extra["power_mva"] = t
                    except Exception:
                        pass
                    try:
                        if measurements.get("satyf_counter"):
                            extra["satyf_counter"] = (
                                measurements["satyf_counter"].text.strip()
                            )
                    except Exception:
                        pass
                    try:
                        if measurements.get("silica"):
                            extra["silica"] = measurements["silica"].text
                    except Exception:
                        pass
                    try:
                        if measurements.get("temp_fan"):
                            extra["temp_fan"] = [w.text.strip() for w in measurements["temp_fan"]]
                    except Exception:
                        pass
                    try:
                        if measurements.get("temp_alarm"):
                            extra["temp_alarm"] = [w.text.strip() for w in measurements["temp_alarm"]]
                    except Exception:
                        pass
                    try:
                        if measurements.get("temp_trip"):
                            extra["temp_trip"] = [w.text.strip() for w in measurements["temp_trip"]]
                    except Exception:
                        pass
                    try:
                        if measurements.get("diverter_res"):
                            extra["diverter_res"] = [w.text.strip() for w in measurements["diverter_res"]]
                    except Exception:
                        pass

                    data_json = json.dumps(extra, ensure_ascii=False) if extra else None

                    # Safely extract measurement values to avoid KeyError when widgets are absent
                    def _m_text(k):
                        w = measurements.get(k)
                        return w.text if w and getattr(w, "text", None) is not None else None

                    def _m_float(k):
                        w = measurements.get(k)
                        if not w or not getattr(w, "text", None):
                            return None
                        try:
                            return parse_float(w.text)
                        except Exception:
                            return None

                    ins_closed_fa_val = _m_float("ins_closed_fa")
                    ins_closed_fa_unit = _m_text("ins_closed_fa_unit")
                    ins_closed_fb_val = _m_float("ins_closed_fb")
                    ins_closed_fb_unit = _m_text("ins_closed_fb_unit")
                    ins_closed_fc_val = _m_float("ins_closed_fc")
                    ins_closed_fc_unit = _m_text("ins_closed_fc_unit")
                    ins_open_fa_val = _m_float("ins_open_fa")
                    ins_open_fa_unit = _m_text("ins_open_fa_unit")
                    ins_open_fb_val = _m_float("ins_open_fb")
                    ins_open_fb_unit = _m_text("ins_open_fb_unit")
                    ins_open_fc_val = _m_float("ins_open_fc")
                    ins_open_fc_unit = _m_text("ins_open_fc_unit")
                    cont_fa_val = _m_float("cont_fa")
                    cont_fb_val = _m_float("cont_fb")
                    cont_fc_val = _m_float("cont_fc")

                    c.execute(
                        """INSERT INTO maintenance_elements 
                        (maintenance_id, element_id, element_comments,
                         insulation_closed_fa_ground, insulation_closed_fa_unit,
                         insulation_closed_fb_ground, insulation_closed_fb_unit,
                         insulation_closed_fc_ground, insulation_closed_fc_unit,
                         insulation_open_fa_fa, insulation_open_fa_unit,
                         insulation_open_fb_fb, insulation_open_fb_unit,
                         insulation_open_fc_fc, insulation_open_fc_unit,
                         contact_resistance_fa_fa, contact_resistance_fb_fb, contact_resistance_fc_fc,
                         operations_count,
                        sf6_leakage_kg, sf6_leak_methodology,
                         sf6_n2_fa, h2o_fa, so2_fa, sf6_n2_fb, h2o_fb, so2_fb, sf6_n2_fc, h2o_fc, so2_fc,
                         vidar_fa, vidar_fb, vidar_fc, data_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            maintenance_id,
                            elem_id,
                            widgets["comments"].text.strip(),
                            ins_closed_fa_val,
                            ins_closed_fa_unit,
                            ins_closed_fb_val,
                            ins_closed_fb_unit,
                            ins_closed_fc_val,
                            ins_closed_fc_unit,
                            ins_open_fa_val,
                            ins_open_fa_unit,
                            ins_open_fb_val,
                            ins_open_fb_unit,
                            ins_open_fc_val,
                            ins_open_fc_unit,
                            cont_fa_val,
                            cont_fb_val,
                            cont_fc_val,
                            ops_count,
                            sf6_leakage_val,
                            sf6_leak_methodology_val,
                            sf6_vals.get("sf6_n2_fa"),
                            sf6_vals.get("h2o_fa"),
                            sf6_vals.get("so2_fa"),
                            sf6_vals.get("sf6_n2_fb"),
                            sf6_vals.get("h2o_fb"),
                            sf6_vals.get("so2_fb"),
                            sf6_vals.get("sf6_n2_fc"),
                            sf6_vals.get("h2o_fc"),
                            sf6_vals.get("so2_fc"),
                            vidar_vals.get("vidar_fa"),
                            vidar_vals.get("vidar_fb"),
                            vidar_vals.get("vidar_fc"),
                            data_json,
                        ),
                    )

                    # Update element's operations_count
                    if ops_count is not None:
                        c.execute(
                            "UPDATE elements SET operations_count=? WHERE id=?",
                            (ops_count, elem_id),
                        )
                    # Update element's power_mva if provided
                    try:
                        if measurements.get("power_mva"):
                            t = measurements["power_mva"].text.strip()
                            if t:
                                try:
                                    pval = float(t.replace(",", "."))
                                    c.execute("UPDATE elements SET power_mva=? WHERE id=?", (pval, elem_id))
                                except Exception:
                                    pass
                    except Exception:
                        pass
                else:  # Other element types without measurements
                    # Still allow storing extra JSON if present
                    extra = {}
                    try:
                        if measurements and measurements.get("power_mva"):
                            t = measurements["power_mva"].text.strip()
                            if t:
                                extra["power_mva"] = t
                    except Exception:
                        pass
                    data_json = json.dumps(extra, ensure_ascii=False) if extra else None
                    c.execute(
                        "INSERT INTO maintenance_elements (maintenance_id, element_id, element_comments, data_json) VALUES (?, ?, ?, ?)",
                        (maintenance_id, elem_id, widgets["comments"].text.strip(), data_json),
                    )

                # Update element's maintenance_date
                c.execute(
                    "UPDATE elements SET maintenance_date=? WHERE id=?",
                    (maintenance_date, elem_id),
                )

            # Update substation's last maintenance date
            c.execute(
                "UPDATE substations SET last_maintenance=? WHERE id=?",
                (maintenance_date, substation_id),
            )

            # Ensure hybrid OneDrive/local folder structure before commit.
            # If folder creation fails, maintenance creation must be blocked.
            try:
                folder_result = ensure_maintenance_folders(
                    self.conn,
                    maintenance_id=maintenance_id,
                    substation_id=substation_id,
                    maintenance_name=maintenance_name,
                    maintenance_type=maintenance_type,
                    date_time=maintenance_date,
                    element_ids=[elem_id for elem_id, _widgets in selected_elements],
                    attachment_paths=prefill_attachment_paths,
                    db_path=self.db_path,
                )
                primary_media_folder = folder_result.get("primary_media_folder")
                if primary_media_folder:
                    c.execute(
                        "UPDATE maintenance SET onedrive_media_folder_link=? WHERE id=?",
                        (primary_media_folder, maintenance_id),
                    )
            except Exception as exc:
                self.conn.rollback()
                show_message_popup(
                    S["TITLES"].get("ERROR", "Σφάλμα"),
                    S["MESSAGES"].get(
                        "MAINT_FOLDERS_CREATE_FAILED_FMT",
                        "Failed to create maintenance folder structure.\nThe entry was cancelled.\n\n{error}",
                    ).format(error=str(exc)),
                )
                return

            # Track change for desktop sync (only for new maintenance records)
            if not maintenance_record:
                elements_data = []
                for elem_id, widgets in selected_elements:
                    elements_data.append({
                        "element_id": elem_id,
                        "element_comments": widgets["comments"].text.strip()
                    })
                
                maintenance_data = {
                    "id": maintenance_id,
                    "substation_id": substation_id,
                    "name": maintenance_name,
                    "date_time": maintenance_date,
                    "overall_comments": overall_comments.text.strip(),
                    "maintenance_type": maintenance_type,
                    "user_name": user_name,
                    "responsible_id": responsible_id,
                    "elements": elements_data
                }
                self._append_change_log("insert", "maintenance", maintenance_data)

            self.conn.commit()
            popup.dismiss()
            success_msg = (
                "Η συντήρηση ενημερώθηκε!"
                if maintenance_record
                else "Η συντήρηση καταχωρήθηκε!"
            )
            if after_save_callback:
                show_message_popup(
                    S["TITLES"].get("SUCCESS", "Επιτυχία"),
                    S["MESSAGES"].get("MAINTENANCE_UPDATED" if maintenance_record else "MAINTENANCE_CREATED", success_msg),
                    callback=lambda: after_save_callback(),
                )
            else:
                show_message_popup(
                    S["TITLES"].get("SUCCESS", "Επιτυχία"),
                    S["MESSAGES"].get("MAINTENANCE_UPDATED" if maintenance_record else "MAINTENANCE_CREATED", success_msg),
                )

        save_btn = Button(text=S["BUTTONS"]["SAVE"])
        save_btn.bind(on_press=lambda x: save_maintenance())
        buttons_layout.add_widget(save_btn)

        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
        cancel_btn.bind(on_press=popup.dismiss)
        buttons_layout.add_widget(cancel_btn)

        main_layout.add_widget(buttons_layout)
        popup.content = main_layout
        popup.open()

    def show_maintenance_menu_for_substation(
        self, substation_id, substation_name, parent_popup=None
    ):
        """Wrapper to show maintenance menu with preselected substation

        Args:
            substation_id: ID of the substation (for compatibility, not used)
            substation_name: Name of the substation to preselect
            parent_popup: Parent popup to dismiss when opening this one
        """
        # Simply call the main function with the preselected substation
        self.show_maintenance_menu(
            instance=None,
            preselected_substation_name=substation_name,
            parent_popup=parent_popup,
        )

    def show_maintenance_history(self, instance, _deferred=False):
        """Show maintenance history"""
        if not _deferred:
            self._run_with_loading(
                lambda: self.show_maintenance_history(instance, _deferred=True),
                S["MESSAGES"].get("LOADING_MAINT_HISTORY", "Φόρτωση ιστορικού συντηρήσεων..."),
            )
            return

        font_kwargs = self._get_ui_font_kwargs()
        history_limit = 80
        c = self.conn.cursor()
        c.execute("SELECT id, name FROM substations")
        all_substations_raw = c.fetchall()
        substation_map = {row[1]: row[0] for row in all_substations_raw}
        all_substations = sorted(all_substations_raw, key=lambda row: row[1])

        c.execute("SELECT COUNT(*) FROM maintenance")
        all_records_count = c.fetchone()[0]

        if not all_records_count:
            show_message_popup(S["TITLES"]["INFO"], S["MESSAGES"].get("NO_MAINTENANCES", "Δεν υπάρχουν καταχωρημένες συντηρήσεις"))
            return

        popup = Popup(title=S["MESSAGES"].get("MAINT_HISTORY_LABEL", "Ιστορικό Συντήρησης"), size_hint=(0.95, 0.9))
        main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        filter_bar = BoxLayout(size_hint_y=None, height=40, spacing=10)
        filter_bar.add_widget(Label(text=S["MESSAGES"].get("FILTER_SUBSTATION", "Φίλτρο Υποσταθμού:"), size_hint_x=0.22))
        substation_input = TextInput(
            text="(Όλα)", readonly=True, multiline=False, size_hint_x=0.48
        )
        filter_bar.add_widget(substation_input)
        select_sub_btn = Button(text=S["MESSAGES"].get("SELECT_PROMPT", "Επιλογή"), size_hint_x=0.15)
        filter_bar.add_widget(select_sub_btn)
        show_all_btn = Button(text=S["MESSAGES"].get("ALL_LABEL", "(Όλα)"), size_hint_x=0.15)
        filter_bar.add_widget(show_all_btn)
        main_layout.add_widget(filter_bar)

        scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
        grid = GridLayout(cols=1, spacing=10, size_hint_y=None, padding=10)
        grid.bind(minimum_height=grid.setter("height"))
        info_label = Label(text="", size_hint_y=None, height=24)
        main_layout.add_widget(info_label)

        # Cache heavy "all substations" dataset to speed repeated filter resets
        all_records_cache = {"records": None, "total_count": None, "people": None, "elements": None}

        def fetch_records(selected_substation):
            if selected_substation and selected_substation != "(Όλα)":
                c.execute(
                    """
                    SELECT m.id, s.name, m.name, m.date_time, m.overall_comments
                    FROM maintenance m
                    JOIN substations s ON m.substation_id = s.id
                    WHERE s.name = ?
                    ORDER BY m.date_time DESC
                    LIMIT ?
                """,
                    (selected_substation, history_limit),
                )
                return c.fetchall()

            if all_records_cache["records"] is not None:
                return all_records_cache["records"]

            c.execute("""
                SELECT m.id, s.name, m.name, m.date_time, m.overall_comments
                FROM maintenance m
                JOIN substations s ON m.substation_id = s.id
                ORDER BY m.date_time DESC
                LIMIT ?
            """, (history_limit,))
            rows = c.fetchall()
            all_records_cache["records"] = rows
            return rows

        def fetch_total_count(selected_substation):
            if selected_substation and selected_substation != "(Όλα)":
                c.execute(
                    """
                    SELECT COUNT(*)
                    FROM maintenance m
                    JOIN substations s ON m.substation_id = s.id
                    WHERE s.name = ?
                """,
                    (selected_substation,),
                )
                return c.fetchone()[0]

            if all_records_cache["total_count"] is not None:
                return all_records_cache["total_count"]

            c.execute("SELECT COUNT(*) FROM maintenance")
            total = c.fetchone()[0]
            all_records_cache["total_count"] = total
            return total

        def render_records(selected_substation):
            grid.clear_widgets()
            maintenance_records = fetch_records(selected_substation)
            total_count = fetch_total_count(selected_substation)
            if total_count > len(maintenance_records):
                info_label.text = f"Εμφανίζονται οι πιο πρόσφατες {len(maintenance_records)} από {total_count} συντηρήσεις."
            else:
                info_label.text = ""
            if not maintenance_records:
                grid.add_widget(
                    Label(
                        text=S["MESSAGES"].get("NO_MAINTENANCES", "Δεν υπάρχουν καταχωρημένες συντηρήσεις"),
                        size_hint_y=None,
                        height=40,
                    )
                )
                return

            def _add_separator(container, color=(0.75, 0.78, 0.82, 1), height=2):
                sep = Widget(size_hint_y=None, height=height)
                if hasattr(sep, "canvas"):
                    try:
                        with sep.canvas.before:
                            sep._sep_color = Color(*color)
                            sep._sep_rect = Rectangle(pos=sep.pos, size=sep.size)

                        def _update_sep(_inst, _val):
                            if hasattr(sep, "_sep_rect"):
                                sep._sep_rect.pos = sep.pos
                                sep._sep_rect.size = sep.size

                        sep.bind(pos=_update_sep, size=_update_sep)
                    except Exception:
                        pass
                container.add_widget(sep)

            def _style_maintenance_card(card_widget):
                if not hasattr(card_widget, "canvas"):
                    return
                try:
                    with card_widget.canvas.before:
                        card_widget._bg_color = Color(*self.theme.get("popup_bg", (0.97, 0.98, 0.99, 1)))
                        card_widget._bg_rect = Rectangle(pos=card_widget.pos, size=card_widget.size)
                    with card_widget.canvas.after:
                        card_widget._border_color = Color(0.72, 0.76, 0.81, 1)
                        card_widget._border_line = Line(
                            rectangle=(
                                card_widget.x,
                                card_widget.y,
                                card_widget.width,
                                card_widget.height,
                            ),
                            width=1,
                        )

                    def _update_card_style(_inst, _val):
                        if hasattr(card_widget, "_bg_rect"):
                            card_widget._bg_rect.pos = card_widget.pos
                            card_widget._bg_rect.size = card_widget.size
                        if hasattr(card_widget, "_border_line"):
                            card_widget._border_line.rectangle = (
                                card_widget.x,
                                card_widget.y,
                                card_widget.width,
                                card_widget.height,
                            )

                    card_widget.bind(pos=_update_card_style, size=_update_card_style)
                except Exception:
                    pass

            maint_ids = [row[0] for row in maintenance_records]
            people_by_maint = {}
            elements_by_maint = {}

            if selected_substation == "(Όλα)" and all_records_cache["people"] is not None and all_records_cache["elements"] is not None:
                people_by_maint = all_records_cache["people"]
                elements_by_maint = all_records_cache["elements"]
            elif maint_ids:
                placeholders = ",".join(["?"] * len(maint_ids))

                # Bulk fetch responsible/crew people for all maintenance rows in this view
                c.execute(
                    f"""
                    SELECT mp.maintenance_id, p.name, mp.role
                    FROM maintenance_people mp
                    JOIN people p ON mp.person_id = p.id
                    WHERE mp.maintenance_id IN ({placeholders})
                    ORDER BY p.name
                    """,
                    maint_ids,
                )
                for m_id, person_name, role in c.fetchall():
                    entry = people_by_maint.setdefault(
                        m_id, {"responsible": None, "crew": []}
                    )
                    if role == "responsible":
                        entry["responsible"] = person_name
                    elif role == "crew":
                        entry["crew"].append(person_name)

                # Bulk fetch elements for all maintenance rows in this view
                # Track already-added element IDs per maintenance to avoid displaying duplicates
                elements_added_per_maint = {mid: set() for mid in maint_ids}
                c.execute(
                    f"""
                    SELECT me.maintenance_id, e.id, e.element_type, e.name, e.serial_number,
                           me.element_comments, e.breaker_category
                    FROM maintenance_elements me
                    JOIN elements e ON me.element_id = e.id
                    WHERE me.maintenance_id IN ({placeholders})
                    ORDER BY me.maintenance_id, e.name
                    """,
                    maint_ids,
                )
                for m_id, elem_id, elem_type, elem_name, serial_num, elem_comments, breaker_category in c.fetchall():
                    # Only add if this element hasn't been added for this maintenance yet
                    if elem_id not in elements_added_per_maint[m_id]:
                        elements_by_maint.setdefault(m_id, []).append(
                            (elem_id, elem_type, elem_name, serial_num, elem_comments, breaker_category)
                        )
                        elements_added_per_maint[m_id].add(elem_id)

                if selected_substation == "(Όλα)":
                    all_records_cache["people"] = people_by_maint
                    all_records_cache["elements"] = elements_by_maint

            grouped_records = {}
            for row in maintenance_records:
                grouped_records.setdefault(row[1], []).append(row)

            sorted_substations = sorted(grouped_records.keys(), key=lambda name: (name or "").lower())

            for group_sub_name in sorted_substations:
                group_rows = grouped_records[group_sub_name]

                section_header = Label(
                    text=f"[b]{group_sub_name}[/b]",
                    markup=True,
                    size_hint_y=None,
                    height=34,
                    halign="left",
                    valign="middle",
                )
                section_header.bind(
                    width=lambda inst, val: setattr(inst, "text_size", (val, None)),
                    texture_size=lambda inst, val: setattr(inst, "height", max(34, val[1] + 8)),
                )
                grid.add_widget(section_header)

                group_count = Label(
                    text=f"{len(group_rows)} συντηρήσεις",
                    size_hint_y=None,
                    height=22,
                    halign="left",
                    valign="middle",
                )
                group_count.bind(
                    width=lambda inst, val: setattr(inst, "text_size", (val, None)),
                    texture_size=lambda inst, val: setattr(inst, "height", max(22, val[1] + 4)),
                )
                grid.add_widget(group_count)
                _add_separator(grid)

                for (
                    maint_id,
                    sub_name,
                    maint_name,
                    date_time,
                    overall_comments,
                ) in group_rows:
                    # Maintenance card
                    card = BoxLayout(
                        orientation="vertical", size_hint_y=None, padding=8, spacing=6
                    )
                    card.bind(minimum_height=card.setter("height"))
                    _style_maintenance_card(card)

                    # Header
                    header = BoxLayout(size_hint_y=None, height=40, spacing=5)
                    display_name = maint_name or self._build_maintenance_name(
                        sub_name, date_time
                    )
                    header.add_widget(
                        Label(
                            text=S["MESSAGES"].get("MAINTENANCE_HEADER", "Συντήρηση: {name}").format(name=display_name), bold=True, size_hint_x=0.45
                        )
                    )
                    header.add_widget(Label(text=f"Ημ/νία: {date_time}", size_hint_x=0.2))
                    from ui.shared import IconOnlyButton
                    edit_btn = IconOnlyButton(icon_type="edit", icon_color=self.theme.get('primary', (0.2,0.6,1,1)), size=(35, 35))
                    delete_btn = IconOnlyButton(icon_type="delete", icon_color=(1, 0.0, 0.0, 1), size=(35, 35))
                    email_btn = Button(text=S["BUTTONS"].get("EMAIL", "Email"), size_hint_x=0.1)

                    def make_delete_handler(m_id, p):
                        return lambda x: self.confirm_delete_maintenance(m_id, p)

                    def make_email_handler(m_id):
                        return lambda x: self.send_maintenance_email_report(m_id)

                    def make_edit_handler(m_id, p):
                        return lambda x: self.show_maintenance_menu(
                            None, None, p, m_id, lambda: self.show_maintenance_history(None)
                        )

                    delete_btn.bind(on_press=make_delete_handler(maint_id, popup))
                    email_btn.bind(on_press=make_email_handler(maint_id))
                    edit_btn.bind(on_press=make_edit_handler(maint_id, popup))
                    header.add_widget(edit_btn)
                    header.add_widget(delete_btn)
                    header.add_widget(email_btn)
                    card.add_widget(header)

                    # Responsible and crew
                    people_info = people_by_maint.get(
                        maint_id, {"responsible": None, "crew": []}
                    )
                    responsible = people_info.get("responsible")
                    crew = people_info.get("crew") or []
                    if responsible or crew:
                        crew_text = ", ".join(crew) if crew else "-"
                        resp_text = responsible if responsible else "-"
                        people_label = Label(
                            text=S["MESSAGES"].get("PEOPLE_SUMMARY", "Υπεύθυνος: {resp} | Ομάδα: {crew}").format(resp=resp_text, crew=crew_text),
                            size_hint_y=None,
                            height=25,
                        )
                        people_label.bind(
                            width=lambda instance, value: setattr(
                                instance, "text_size", (value, None)
                            ),
                            texture_size=lambda instance, value: setattr(
                                instance, "height", value[1] + 6
                            ),
                        )
                        card.add_widget(people_label)

                    # Overall comments
                    if overall_comments:
                        try:
                            from maintenance_email_importer import _format_email_body_for_readability
                            display_comments = _format_email_body_for_readability(overall_comments)
                        except Exception:
                            display_comments = overall_comments

                        comment_label = Label(
                            text=S["MESSAGES"].get("COMMENTS_LABEL", "Σχόλια: {text}").format(text=display_comments), size_hint_y=None, height=30
                        )
                        comment_label.bind(
                            width=lambda instance, value: setattr(
                                instance, "text_size", (value, None)
                            ),
                            texture_size=lambda instance, value: setattr(
                                instance, "height", value[1] + 6
                            ),
                        )
                        card.add_widget(comment_label)

                    # Elements for this maintenance (from bulk prefetch)
                    elements = elements_by_maint.get(maint_id, [])

                    # Elements list
                    elements_label = Label(
                        text=S["MESSAGES"].get("ELEMENTS_LIST_LABEL", "Στοιχεία που συντηρήθηκαν:"),
                        size_hint_y=None,
                        height=25,
                        bold=True,
                    )
                    card.add_widget(elements_label)

                    for (
                        elem_id,
                        elem_type,
                        elem_name,
                        serial_num,
                        elem_comments,
                        breaker_category,
                    ) in elements:
                        # Element info with optional PDF button
                        elem_row = BoxLayout(size_hint_y=None, height=40, spacing=5)
                        elem_row.bind(minimum_height=elem_row.setter("height"))

                        elem_text = (
                            f"  • {elem_type}: {elem_name} (S/N: {serial_num or '-'})"
                        )
                        if elem_comments:
                            elem_text += "\n    " + S["MESSAGES"].get("COMMENTS_LABEL", "Σχόλια: {text}").format(text=elem_comments)

                        elem_label = Label(
                            text=elem_text, size_hint_x=0.6, size_hint_y=None
                        )
                        elem_label.bind(
                            width=lambda instance, value: setattr(
                                instance, "text_size", (value, None)
                            ),
                            texture_size=lambda instance, value: (
                                setattr(instance, "height", value[1] + 6),
                                setattr(elem_row, "height", max(40, value[1] + 10)),
                            ),
                        )
                        elem_row.add_widget(elem_label)

                        # Add PDF button for circuit breakers (check Greek names from BREAKER_CATEGORIES_ALL)
                        buttons_container = BoxLayout(size_hint_x=0.4, spacing=5)

                        view_btn = Button(
                            text=S["MESSAGES"].get("VIEW_SHORT", "Εμφ."),
                            size_hint_x=0.34,
                            size_hint_y=None,
                            height=35,
                            **font_kwargs,
                        )

                        def make_view_handler(m_id, e_id, e_name):
                            return lambda x: self.show_maintenance_element_details(
                                m_id, e_id, e_name
                            )

                        view_btn.bind(
                            on_press=make_view_handler(maint_id, elem_id, elem_name)
                        )
                        buttons_container.add_widget(view_btn)

                        if (
                            S["MESSAGES"].get("ELEMENT_BREAKER_SUBSTR", "Διακόπτης") in elem_type
                            and breaker_category in self.BREAKER_CATEGORIES_ALL
                        ):
                            pdf_btn = Button(
                                text=S["MESSAGES"].get("PDF_BUTTON", "PDF"),
                                size_hint_x=0.5,
                                size_hint_y=None,
                                height=35,
                                **font_kwargs,
                            )

                            def make_pdf_handler(m_id, e_id, e_name):
                                return lambda x: self.generate_pdf_report(
                                    m_id, e_id, e_name
                                )

                            pdf_btn.bind(
                                on_press=make_pdf_handler(maint_id, elem_id, elem_name)
                            )
                            buttons_container.add_widget(pdf_btn)
                        else:
                            buttons_container.add_widget(Label(text="", size_hint_x=0.5))

                        elem_row.add_widget(buttons_container)

                        card.add_widget(elem_row)

                    grid.add_widget(card)
                    _add_separator(grid, color=(0.82, 0.84, 0.87, 1), height=1)

                grid.add_widget(Widget(size_hint_y=None, height=8))

        def _on_select_substation_filter(sub_name):
            substation_input.text = sub_name
            self._run_with_loading(
                lambda: render_records(sub_name),
                S["MESSAGES"].get("LOADING_MAINT_HISTORY", "Φόρτωση ιστορικού συντηρήσεων..."),
            )

        def _open_substation_filter_picker(_instance=None):
            self._show_substation_selection_window_with_callback(
                popup,
                all_substations,
                on_select=_on_select_substation_filter,
                title=S["MESSAGES"].get("FILTER_SUBSTATION", "Φίλτρο Υποσταθμού"),
            )

        def _show_all_substations_filter(_instance=None):
            substation_input.text = "(Όλα)"
            self._run_with_loading(
                lambda: render_records("(Όλα)"),
                S["MESSAGES"].get("LOADING_MAINT_HISTORY", "Φόρτωση ιστορικού συντηρήσεων..."),
            )

        select_sub_btn.bind(on_press=_open_substation_filter_picker)
        show_all_btn.bind(on_press=_show_all_substations_filter)

        render_records(substation_input.text)

        scroll.add_widget(grid)
        main_layout.add_widget(scroll)

        # Close button
        close_btn = Button(text=S["BUTTONS"]["CLOSE"], size_hint_y=0.1)
        close_btn.bind(on_press=popup.dismiss)
        main_layout.add_widget(close_btn)

        popup.content = main_layout
        popup.open()

    def show_substation_maintenance_history(
        self, substation_id, substation_name, parent_display_popup=None
    ):
        """Show maintenance history for a specific substation"""
        font_kwargs = self._get_ui_font_kwargs()
        history_limit = 80
        c = self.conn.cursor()
        c.execute("SELECT COUNT(*) FROM maintenance WHERE substation_id = ?", (substation_id,))
        total_records = c.fetchone()[0]
        c.execute(
            """
            SELECT m.id, m.name, m.date_time, m.overall_comments
            FROM maintenance m
            WHERE m.substation_id = ?
            ORDER BY m.date_time DESC
            LIMIT ?
        """,
            (substation_id, history_limit),
        )
        maintenance_records = c.fetchall()

        popup = Popup(
            title=f"Ιστορικό Συντήρησης: {substation_name}", size_hint=(0.95, 0.9)
        )
        main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        # Add Maintenance button at the top
        add_maint_btn = Button(text=S["BUTTONS"].get("ADD_MAINTENANCE", "+ Προσθήκη Νέας Συντήρησης"), size_hint_y=0.1)
        add_maint_btn.bind(
            on_press=lambda x: self.show_maintenance_menu_for_substation(
                substation_id, substation_name, popup
            )
        )
        main_layout.add_widget(add_maint_btn)

        if not maintenance_records:
            # Show message but still allow adding maintenance
            no_records_label = Label(
                text=S["MESSAGES"].get(
                    "NO_MAINT_FOR_SUBSTATION",
                    'Δεν υπάρχουν καταχωρημένες συντηρήσεις για τον υποσταθμό "{substation_name}".\nΧρησιμοποιήστε το κουμπί παραπάνω για να προσθέσετε.',
                ).format(substation_name=substation_name),
                size_hint_y=0.7,
            )
            main_layout.add_widget(no_records_label)
        else:
            if total_records > len(maintenance_records):
                main_layout.add_widget(
                    Label(
                        text=f"Εμφανίζονται οι πιο πρόσφατες {len(maintenance_records)} από {total_records} συντηρήσεις.",
                        size_hint_y=None,
                        height=24,
                    )
                )
            scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
            grid = GridLayout(cols=1, spacing=10, size_hint_y=None, padding=10)
            grid.bind(minimum_height=grid.setter("height"))

            def _add_separator(container, color=(0.75, 0.78, 0.82, 1), height=2):
                sep = Widget(size_hint_y=None, height=height)
                if hasattr(sep, "canvas"):
                    try:
                        with sep.canvas.before:
                            sep._sep_color = Color(*color)
                            sep._sep_rect = Rectangle(pos=sep.pos, size=sep.size)

                        def _update_sep(_inst, _val):
                            if hasattr(sep, "_sep_rect"):
                                sep._sep_rect.pos = sep.pos
                                sep._sep_rect.size = sep.size

                        sep.bind(pos=_update_sep, size=_update_sep)
                    except Exception:
                        pass
                container.add_widget(sep)

            def _style_maintenance_card(card_widget):
                if not hasattr(card_widget, "canvas"):
                    return
                try:
                    with card_widget.canvas.before:
                        card_widget._bg_color = Color(*self.theme.get("popup_bg", (0.97, 0.98, 0.99, 1)))
                        card_widget._bg_rect = Rectangle(pos=card_widget.pos, size=card_widget.size)
                    with card_widget.canvas.after:
                        card_widget._border_color = Color(0.72, 0.76, 0.81, 1)
                        card_widget._border_line = Line(
                            rectangle=(
                                card_widget.x,
                                card_widget.y,
                                card_widget.width,
                                card_widget.height,
                            ),
                            width=1,
                        )

                    def _update_card_style(_inst, _val):
                        if hasattr(card_widget, "_bg_rect"):
                            card_widget._bg_rect.pos = card_widget.pos
                            card_widget._bg_rect.size = card_widget.size
                        if hasattr(card_widget, "_border_line"):
                            card_widget._border_line.rectangle = (
                                card_widget.x,
                                card_widget.y,
                                card_widget.width,
                                card_widget.height,
                            )

                    card_widget.bind(pos=_update_card_style, size=_update_card_style)
                except Exception:
                    pass

            maint_ids = [row[0] for row in maintenance_records]
            people_by_maint = {}
            elements_by_maint = {}

            if maint_ids:
                placeholders = ",".join(["?"] * len(maint_ids))

                # Bulk fetch responsible/crew people for all maintenance rows in this substation
                c.execute(
                    f"""
                    SELECT mp.maintenance_id, p.name, mp.role
                    FROM maintenance_people mp
                    JOIN people p ON mp.person_id = p.id
                    WHERE mp.maintenance_id IN ({placeholders})
                    ORDER BY p.name
                    """,
                    maint_ids,
                )
                for m_id, person_name, role in c.fetchall():
                    entry = people_by_maint.setdefault(
                        m_id, {"responsible": None, "crew": []}
                    )
                    if role == "responsible":
                        entry["responsible"] = person_name
                    elif role == "crew":
                        entry["crew"].append(person_name)

                # Bulk fetch elements for all maintenance rows in this substation
                # Track already-added element IDs per maintenance to avoid displaying duplicates
                elements_added_per_maint = {mid: set() for mid in maint_ids}
                c.execute(
                    f"""
                    SELECT me.maintenance_id, e.id, e.element_type, e.name, e.serial_number,
                           me.element_comments, e.breaker_category
                    FROM maintenance_elements me
                    JOIN elements e ON me.element_id = e.id
                    WHERE me.maintenance_id IN ({placeholders})
                    ORDER BY me.maintenance_id, e.name
                    """,
                    maint_ids,
                )
                for m_id, elem_id, elem_type, elem_name, serial_num, elem_comments, breaker_category in c.fetchall():
                    # Only add if this element hasn't been added for this maintenance yet
                    if elem_id not in elements_added_per_maint[m_id]:
                        elements_by_maint.setdefault(m_id, []).append(
                            (elem_id, elem_type, elem_name, serial_num, elem_comments, breaker_category)
                        )
                        elements_added_per_maint[m_id].add(elem_id)

            for maint_id, maint_name, date_time, overall_comments in maintenance_records:
                # Maintenance card
                card = BoxLayout(
                    orientation="vertical", size_hint_y=None, padding=8, spacing=6
                )
                card.bind(minimum_height=card.setter("height"))
                _style_maintenance_card(card)

                # Header
                header = BoxLayout(size_hint_y=None, height=40, spacing=5)
                display_name = maint_name or self._build_maintenance_name(
                    substation_name, date_time
                )
                header.add_widget(
                    Label(text=S["MESSAGES"].get("MAINTENANCE_HEADER", "Συντήρηση: {name}").format(name=display_name), bold=True, size_hint_x=0.6)
                )
                from ui.shared import IconOnlyButton
                edit_btn = IconOnlyButton(icon_type="edit", icon_color=self.theme.get('primary', (0.2,0.6,1,1)), size=(35, 35))
                delete_btn = IconOnlyButton(icon_type="delete", icon_color=(1, 0.0, 0.0, 1), size=(35, 35))
                email_btn = Button(text=S["BUTTONS"].get("EMAIL", "Email"), size_hint_x=0.13)

                def make_delete_handler(m_id, p):
                    return lambda x: self.confirm_delete_maintenance_for_substation(
                        m_id, p, substation_id, substation_name, parent_display_popup
                    )

                delete_btn.bind(on_press=make_delete_handler(maint_id, popup))

                def make_email_handler(m_id):
                    return lambda x: self.send_maintenance_email_report(m_id)

                email_btn.bind(on_press=make_email_handler(maint_id))

                def make_edit_handler(m_id, p):
                    return lambda x: self.show_maintenance_menu(
                        None,
                        substation_name,
                        p,
                        m_id,
                        lambda: self.show_substation_maintenance_history(
                            substation_id, substation_name, parent_display_popup
                        ),
                    )

                edit_btn.bind(on_press=make_edit_handler(maint_id, popup))
                header.add_widget(edit_btn)
                header.add_widget(email_btn)
                header.add_widget(delete_btn)
                card.add_widget(header)

                # Responsible and crew
                people_info = people_by_maint.get(
                    maint_id, {"responsible": None, "crew": []}
                )
                responsible = people_info.get("responsible")
                crew = people_info.get("crew") or []
                if responsible or crew:
                    crew_text = ", ".join(crew) if crew else "-"
                    resp_text = responsible if responsible else "-"
                    people_label = Label(
                        text=S["MESSAGES"].get("PEOPLE_SUMMARY", "Υπεύθυνος: {resp} | Ομάδα: {crew}").format(resp=resp_text, crew=crew_text),
                        size_hint_y=None,
                        height=25,
                    )
                    people_label.bind(
                        width=lambda instance, value: setattr(
                            instance, "text_size", (value, None)
                        ),
                        texture_size=lambda instance, value: setattr(
                            instance, "height", value[1] + 6
                        ),
                    )
                    card.add_widget(people_label)

                # Overall comments
                if overall_comments:
                    comment_label = Label(
                        text=S["MESSAGES"].get("COMMENTS_LABEL", "Σχόλια: {text}").format(text=overall_comments), size_hint_y=None, height=30
                    )
                    comment_label.bind(
                        width=lambda instance, value: setattr(
                            instance, "text_size", (value, None)
                        ),
                        texture_size=lambda instance, value: setattr(
                            instance, "height", value[1] + 6
                        ),
                    )
                    card.add_widget(comment_label)

                # Elements for this maintenance (from bulk prefetch)
                elements = elements_by_maint.get(maint_id, [])

                # Elements list
                elements_label = Label(
                    text=S["MESSAGES"].get("ELEMENTS_LIST_LABEL", "Στοιχεία που συντηρήθηκαν:"),
                    size_hint_y=None,
                    height=25,
                    bold=True,
                )
                card.add_widget(elements_label)

                for (
                    elem_id,
                    elem_type,
                    elem_name,
                    serial_num,
                    elem_comments,
                    breaker_category,
                ) in elements:
                    # Element info with optional PDF button
                    elem_row = BoxLayout(size_hint_y=None, height=40, spacing=5)
                    elem_row.bind(minimum_height=elem_row.setter("height"))

                    elem_text = f"  • {elem_type}: {elem_name} (S/N: {serial_num or '-'})"
                    if elem_comments:
                        elem_text += "\n    " + S["MESSAGES"].get("COMMENTS_LABEL", "Σχόλια: {text}").format(text=elem_comments)

                    elem_label = Label(text=elem_text, size_hint_x=0.6, size_hint_y=None)
                    elem_label.bind(
                        width=lambda instance, value: setattr(
                            instance, "text_size", (value, None)
                        ),
                        texture_size=lambda instance, value: (
                            setattr(instance, "height", value[1] + 6),
                            setattr(elem_row, "height", max(40, value[1] + 10)),
                        ),
                    )
                    elem_row.add_widget(elem_label)

                    # Add PDF button for circuit breakers (check Greek names from BREAKER_CATEGORIES_ALL)
                    buttons_container = BoxLayout(size_hint_x=0.4, spacing=5)

                    view_btn = Button(
                        text=S["MESSAGES"].get("VIEW_SHORT", "Προβ."),
                        size_hint_x=0.34,
                        size_hint_y=None,
                        height=35,
                        **font_kwargs,
                    )

                    def make_view_handler(m_id, e_id, e_name):
                        return lambda x: self.show_maintenance_element_details(
                            m_id, e_id, e_name
                        )

                    view_btn.bind(on_press=make_view_handler(maint_id, elem_id, elem_name))
                    buttons_container.add_widget(view_btn)

                    if (
                        S["MESSAGES"].get("ELEMENT_BREAKER_SUBSTR", "Διακόπτης") in elem_type
                        and breaker_category in self.BREAKER_CATEGORIES_ALL
                    ):
                        pdf_btn = Button(
                            text=S["MESSAGES"].get("PDF_BUTTON", "PDF"),
                            size_hint_x=0.5,
                            size_hint_y=None,
                            height=35,
                            **font_kwargs,
                        )

                        def make_pdf_handler(m_id, e_id, e_name):
                            return lambda x: self.generate_pdf_report(m_id, e_id, e_name)

                        pdf_btn.bind(
                            on_press=make_pdf_handler(maint_id, elem_id, elem_name)
                        )
                        buttons_container.add_widget(pdf_btn)
                    else:
                        buttons_container.add_widget(Label(text="", size_hint_x=0.5))

                    elem_row.add_widget(buttons_container)

                    card.add_widget(elem_row)

                grid.add_widget(card)
                _add_separator(grid, color=(0.82, 0.84, 0.87, 1), height=1)

            scroll.add_widget(grid)
            main_layout.add_widget(scroll)

        # Close button
        close_btn = Button(text=S["BUTTONS"]["CLOSE"], size_hint_y=0.1)
        close_btn.bind(on_press=popup.dismiss)
        main_layout.add_widget(close_btn)

        popup.content = main_layout
        popup.open()

    def show_maintenance_full_report(self, maintenance_id, parent_popup=None):
        """Show a read-only full maintenance report for one maintenance instance."""
        font_kwargs = self._get_ui_font_kwargs()
        c = self.conn.cursor()

        c.execute(
            """
            SELECT m.id, m.name, m.date_time, m.overall_comments, m.maintenance_type, m.user_name,
                   s.id, s.name, s.location, s.division
            FROM maintenance m
            JOIN substations s ON s.id = m.substation_id
            WHERE m.id = ?
            LIMIT 1
        """,
            (maintenance_id,),
        )
        maintenance_row = c.fetchone()

        if not maintenance_row:
            show_message_popup(
                S["TITLES"].get("ERROR", "Σφάλμα"),
                S["MESSAGES"].get("MAINTENANCE_NOT_FOUND", "Η συντήρηση δεν βρέθηκε."),
            )
            return

        (
            maint_id,
            maint_name,
            date_time,
            overall_comments,
            maintenance_type,
            user_name,
            substation_id,
            substation_name,
            substation_location,
            substation_division,
        ) = maintenance_row

        display_name = maint_name or self._build_maintenance_name(substation_name, date_time)

        popup = Popup(
            title=f"Αναφορά Συντήρησης: {display_name}",
            size_hint=(0.95, 0.9),
        )
        main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
        content = GridLayout(cols=1, spacing=8, size_hint_y=None, padding=10)
        content.bind(minimum_height=content.setter("height"))

        def add_wrapped_label(text, bold=False):
            label = Label(
                text=f"[b]{text}[/b]" if bold else str(text),
                markup=bold,
                size_hint_y=None,
                halign="left",
                valign="top",
            )
            label.bind(
                width=lambda inst, val: setattr(inst, "text_size", (val, None)),
                texture_size=lambda inst, val: setattr(inst, "height", val[1] + 8),
            )
            content.add_widget(label)

        add_wrapped_label(S["MESSAGES"].get("MAINTENANCE_HEADER", "Συντήρηση: {name}").format(name=display_name), bold=True)
        add_wrapped_label(f"{S['MESSAGES'].get('SUBSTATION_LABEL_PLAIN', 'Υποσταθμός')}: {substation_name}")
        add_wrapped_label(f"{S['MESSAGES'].get('DATE_LABEL', 'Ημερομηνία:')} {date_time or '-'}")
        add_wrapped_label(f"{S['MESSAGES'].get('MAINT_TYPE_LABEL', 'Τύπος Συντήρησης:')} {maintenance_type or '-'}")
        add_wrapped_label(f"{S['MESSAGES'].get('MAINT_USER_LABEL', 'Χειριστής')}: {user_name or '-'}")

        if substation_location:
            add_wrapped_label(f"{S['MESSAGES'].get('LOC', 'Τοποθεσία')}: {substation_location}")
        if substation_division:
            add_wrapped_label(f"{S['MESSAGES'].get('DIVISION_LABEL', 'Τομέας')}: {substation_division}")

        responsible, crew = self._get_maintenance_people(maint_id)
        crew_text = ", ".join(crew) if crew else "-"
        resp_text = responsible if responsible else "-"
        add_wrapped_label(
            S["MESSAGES"].get("PEOPLE_SUMMARY", "Υπεύθυνος: {resp} | Ομάδα: {crew}").format(
                resp=resp_text, crew=crew_text
            )
        )

        add_wrapped_label("", bold=False)
        add_wrapped_label(S["MESSAGES"].get("OVERALL_COMMENTS_LABEL", "Γενικά Σχόλια Συντήρησης:"), bold=True)
        add_wrapped_label(overall_comments or "-")

        add_wrapped_label("", bold=False)
        add_wrapped_label(S["MESSAGES"].get("ELEMENTS_LIST_LABEL", "Στοιχεία που συντηρήθηκαν:"), bold=True)

        c.execute(
            """
            SELECT e.id, e.element_type, e.name, e.serial_number, me.element_comments, e.breaker_category
            FROM maintenance_elements me
            JOIN elements e ON e.id = me.element_id
            WHERE me.maintenance_id = ?
            ORDER BY e.name
        """,
            (maint_id,),
        )
        elements = c.fetchall()

        if not elements:
            add_wrapped_label(S["MESSAGES"].get("NO_ELEMENTS_FOR_ITEM", "Δεν βρέθηκαν στοιχεία για τη συντήρηση."))
        else:
            for elem_id, elem_type, elem_name, serial_num, elem_comments, breaker_category in elements:
                elem_row = BoxLayout(size_hint_y=None, height=42, spacing=6)
                elem_row.bind(minimum_height=elem_row.setter("height"))

                elem_text = f"• {elem_type}: {elem_name} (S/N: {serial_num or '-'})"
                if elem_comments:
                    elem_text += "\n  " + S["MESSAGES"].get("COMMENTS_LABEL", "Σχόλια: {text}").format(text=elem_comments)

                elem_label = Label(text=elem_text, size_hint_x=0.62, size_hint_y=None, halign="left", valign="top")
                elem_label.bind(
                    width=lambda inst, val: setattr(inst, "text_size", (val, None)),
                    texture_size=lambda inst, val: (
                        setattr(inst, "height", val[1] + 8),
                        setattr(elem_row, "height", max(42, val[1] + 10)),
                    ),
                )
                elem_row.add_widget(elem_label)

                btns = BoxLayout(size_hint_x=0.38, spacing=6)

                view_btn = Button(
                    text=S["MESSAGES"].get("VIEW_SHORT", "Προβ."),
                    size_hint_x=0.36,
                    size_hint_y=None,
                    height=34,
                    **font_kwargs,
                )
                view_btn.bind(
                    on_press=lambda x, m_id=maint_id, e_id=elem_id, e_name=elem_name: self.show_maintenance_element_details(
                        m_id, e_id, e_name
                    )
                )
                btns.add_widget(view_btn)

                if (
                    S["MESSAGES"].get("ELEMENT_BREAKER_SUBSTR", "Διακόπτης") in elem_type
                    and breaker_category in self.BREAKER_CATEGORIES_ALL
                ):
                    pdf_btn = Button(
                        text=S["MESSAGES"].get("PDF_BUTTON", "PDF"),
                        size_hint_x=0.64,
                        size_hint_y=None,
                        height=34,
                        **font_kwargs,
                    )
                    pdf_btn.bind(
                        on_press=lambda x, m_id=maint_id, e_id=elem_id, e_name=elem_name: self.generate_pdf_report(
                            m_id, e_id, e_name
                        )
                    )
                    btns.add_widget(pdf_btn)
                else:
                    btns.add_widget(Label(text="", size_hint_x=0.64))

                elem_row.add_widget(btns)
                content.add_widget(elem_row)

        scroll.add_widget(content)
        main_layout.add_widget(scroll)

        close_btn = Button(text=S["BUTTONS"]["CLOSE"], size_hint_y=0.1)
        close_btn.bind(on_press=popup.dismiss)
        main_layout.add_widget(close_btn)

        popup.content = main_layout
        popup.open()

    def _show_substation_inspection_history(self, substation_id, substation_name, parent_display_popup=None):
        """Display all inspections for a substation with full details."""
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.gridlayout import GridLayout
        from kivy.uix.label import Label
        from kivy.uix.popup import Popup
        from kivy.uix.scrollview import ScrollView
        import json

        c = self.conn.cursor()
        c.execute(
            "SELECT id, inspection_date, data_json FROM inspections WHERE substation_id=? ORDER BY inspection_date DESC",
            (substation_id,),
        )
        inspections = c.fetchall()

        popup = Popup(
            title=S["MESSAGES"].get(
                "SUBSTATION_INSPECTION_HISTORY_TITLE_FMT",
                "Inspection History - {substation_name}",
            ).format(substation_name=substation_name),
            size_hint=(0.95, 0.9)
        )
        main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        if not inspections:
            main_layout.add_widget(
                Label(
                    text=S["MESSAGES"].get(
                        "SUBSTATION_INSPECTION_COUNT_FMT",
                        "{count} inspection records for substation {substation_name}",
                    ).format(count=0, substation_name=substation_name),
                    size_hint_y=0.8,
                )
            )
        else:
            scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
            grid = GridLayout(cols=1, spacing=10, size_hint_y=None, padding=10)
            grid.bind(minimum_height=grid.setter("height"))

            for insp_id, insp_date, data_json in inspections:
                # Create row for each inspection
                row_layout = BoxLayout(size_hint_y=None, height=50, spacing=8)
                
                info_text = f"[b]{insp_date}[/b]"
                info_label = Label(text=info_text, markup=True, size_hint_x=0.7)
                row_layout.add_widget(info_label)

                view_btn = Button(text=S["BUTTONS"].get("VIEW", "View"), size_hint_x=0.3)
                view_btn.bind(on_press=lambda x, iid=insp_id: self.show_inspection_details(iid))
                row_layout.add_widget(view_btn)
                
                grid.add_widget(row_layout)

            scroll.add_widget(grid)
            main_layout.add_widget(scroll)

        # Close button
        btn_layout = BoxLayout(size_hint_y=None, height=44, spacing=8)
        close_btn = Button(text=S["BUTTONS"]["CLOSE"])
        close_btn.bind(on_press=popup.dismiss)
        btn_layout.add_widget(close_btn)
        main_layout.add_widget(btn_layout)

        popup.content = main_layout
        if parent_display_popup:
            parent_display_popup.dismiss()
        popup.open()

    def show_substation_inspection_history(
        self, substation_id, substation_name, parent_display_popup=None
    ):
        try:
            try:
                with open('inspections_debug.log', 'a', encoding='utf-8') as _fh:
                    _fh.write(f'show_substation_inspection_history invoked for {substation_name}\n')
            except Exception:
                pass
            # visual debug removed; keep file log only
            from inspections import handle_substation_inspection_history as _f
            return _f(self, substation_id, substation_name, parent_display_popup)
        except Exception:
            return None

    def show_inspection_details(self, inspection_id):
        from inspections import handle_inspection_details as _f
        return _f(self, inspection_id)

    def _open_model_manual(self, manual_path):
        """Open a model's manual (can be a file or folder)."""
        from reports import open_file
        
        if not manual_path or not os.path.exists(manual_path):
            show_message_popup(
                S["TITLES"]["ERROR"],
                S["MESSAGES"].get("MANUAL_NOT_FOUND", "Το εγχειρίδιο δεν βρέθηκε!")
            )
            return False
        
        # Check if it's a directory
        if os.path.isdir(manual_path):
            return open_file(
                manual_path,
                not_found_message=S["MESSAGES"].get("MANUAL_NOT_FOUND", "Το εγχειρίδιο δεν βρέθηκε!"),
                error_prefix=S["MESSAGES"].get("OPEN_MANUAL_ERROR", "Αποτυχία ανοίγματος εγχειριδίου:\n")
            )
        else:
            # It's a file (PDF or other)
            return open_file(
                manual_path,
                not_found_message=S["MESSAGES"].get("MANUAL_NOT_FOUND", "Το εγχειρίδιο δεν βρέθηκε!"),
                error_prefix=S["MESSAGES"].get("OPEN_MANUAL_ERROR", "Αποτυχία ανοίγματος εγχειριδίου:\n")
            )

    def show_maintenance_element_details(
        self, maintenance_id, element_id, element_name
    ):
        """Show stored comments/measurements for a maintenance element entry."""
        c = self.conn.cursor()
        c.execute(
            """
            SELECT m.name, m.date_time, m.overall_comments, m.maintenance_type, m.user_name,
                   s.name as substation_name, s.location, s.division,
                   e.element_type, e.name, e.serial_number, e.manufacturer, e.model,
                   e.breaker_category, e.voltage_level, e.gate, e.manufacture_year,
                   em.model_name, em.manufacturer as model_manufacturer, em.manual_pdf
            FROM maintenance m
            JOIN substations s ON m.substation_id = s.id
            JOIN elements e ON e.id = ?
            LEFT JOIN element_models em ON e.element_model_id = em.id
            WHERE m.id = ?
            LIMIT 1
        """,
            (element_id, maintenance_id),
        )
        header_row = c.fetchone()

        c.execute(
            """
            SELECT me.element_comments,
                   me.insulation_closed_fa_ground, me.insulation_closed_fa_unit,
                   me.insulation_closed_fb_ground, me.insulation_closed_fb_unit,
                   me.insulation_closed_fc_ground, me.insulation_closed_fc_unit,
                   me.insulation_open_fa_fa, me.insulation_open_fa_unit,
                   me.insulation_open_fb_fb, me.insulation_open_fb_unit,
                   me.insulation_open_fc_fc, me.insulation_open_fc_unit,
                   me.contact_resistance_fa_fa, me.contact_resistance_fb_fb, me.contact_resistance_fc_fc,
                   me.operations_count,
                                         me.sf6_leakage_kg, me.sf6_leak_methodology,
                   me.sf6_n2_fa, me.h2o_fa, me.so2_fa,
                   me.sf6_n2_fb, me.h2o_fb, me.so2_fb,
                   me.sf6_n2_fc, me.h2o_fc, me.so2_fc,
                   me.vidar_fa, me.vidar_fb, me.vidar_fc,
                   e.breaker_category
            FROM maintenance_elements me
            JOIN elements e ON me.element_id = e.id
            WHERE me.maintenance_id = ? AND me.element_id = ?
            LIMIT 1
        """,
            (maintenance_id, element_id),
        )
        row = c.fetchone()

        if not row:
            show_message_popup(S["TITLES"]["INFO"], S["MESSAGES"].get("NO_ELEMENTS_FOR_ITEM", "Δεν βρέθηκαν στοιχεία για το στοιχείο."))
            return

        (
            element_comments,
            ins_closed_fa,
            ins_closed_fa_unit,
            ins_closed_fb,
            ins_closed_fb_unit,
            ins_closed_fc,
            ins_closed_fc_unit,
            ins_open_fa,
            ins_open_fa_unit,
            ins_open_fb,
            ins_open_fb_unit,
            ins_open_fc,
            ins_open_fc_unit,
            cont_fa,
            cont_fb,
            cont_fc,
            ops_count,
            sf6_leakage_kg,
            sf6_leak_methodology,
            sf6_n2_fa,
            h2o_fa,
            so2_fa,
            sf6_n2_fb,
            h2o_fb,
            so2_fb,
            sf6_n2_fc,
            h2o_fc,
            so2_fc,
            vidar_fa,
            vidar_fb,
            vidar_fc,
            breaker_category,
        ) = row

        def fmt(val, unit=None):
            if val is None or val == "":
                return "-"
            return f"{val} {unit}" if unit else f"{val}"

        def make_wrapped_label(text, bold=False, size_hint_x=1, font_size="14sp"):
            lbl = Label(
                text=f"[b]{text}[/b]" if bold else str(text),
                markup=bold,
                size_hint_x=size_hint_x,
                size_hint_y=None,
                font_size=font_size,
                halign="left",
                valign="top",
            )
            lbl.bind(
                width=lambda inst, val: setattr(inst, "text_size", (val, None)),
                texture_size=lambda inst, val: setattr(inst, "height", val[1] + 6),
            )
            return lbl

        def add_kv_row(grid, label_text, value_text):
            grid.add_widget(make_wrapped_label(label_text, bold=True, size_hint_x=0.38))
            grid.add_widget(
                make_wrapped_label(value_text, bold=False, size_hint_x=0.62)
            )

        def add_section(title):
            content.add_widget(make_wrapped_label(title, bold=True, font_size="15sp"))

        has_measurements = any(
            [
                ins_closed_fa,
                ins_closed_fb,
                ins_closed_fc,
                ins_open_fa,
                ins_open_fb,
                ins_open_fc,
                cont_fa,
                cont_fb,
                cont_fc,
                ops_count,
                sf6_n2_fa,
                h2o_fa,
                so2_fa,
                sf6_leakage_kg,
                sf6_n2_fb,
                h2o_fb,
                so2_fb,
                sf6_n2_fc,
                h2o_fc,
                so2_fc,
                vidar_fa,
                vidar_fb,
                vidar_fc,
            ]
        )

        popup = Popup(title=f"Μετρήσεις: {element_name}", size_hint=(0.9, 0.9))
        main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
        element_type_for_dga = None
        element_gate_for_dga = None
        substation_id_for_dga = None
        serial_for_dga = None
        manufacturer_for_dga = None
        substation_name_for_dga = None

        # Extract element type early to check if transformer (for DGA access)
        if header_row:
            elem_type = header_row[8] if len(header_row) > 8 else None
            element_type_for_dga = elem_type
            is_transformer = self._is_transformer(elem_type) if elem_type else False
        else:
            is_transformer = False

        # Early return only for non-transformers with no data
        # Transformers always get popup to access DGA buttons
        if not has_measurements and not element_comments and not is_transformer:
            show_message_popup(
                S["TITLES"].get("INFO", "Info"),
                S["MESSAGES"].get("ELEMENT_NO_DATA_INFO", "No registered data for this element."),
            )
            return

        scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
        content = GridLayout(cols=1, spacing=6, size_hint_y=None, padding=10)
        content.bind(minimum_height=content.setter("height"))

        if header_row:
            (
                maint_name,
                maint_date,
                maint_comments,
                maint_type,
                maint_user,
                sub_name,
                sub_location,
                division,
                elem_type,
                elem_name,
                serial_number,
                manufacturer,
                model,
                breaker_cat,
                voltage_level,
                gate,
                manufacture_year,
                model_name,
                model_manufacturer,
                manual_pdf,
            ) = header_row
            element_type_for_dga = elem_type
            element_gate_for_dga = gate
            serial_for_dga = serial_number
            manufacturer_for_dga = manufacturer
            substation_name_for_dga = sub_name

            c.execute("SELECT substation_id FROM maintenance WHERE id=?", (maintenance_id,))
            sid_row = c.fetchone()
            substation_id_for_dga = sid_row[0] if sid_row else None

            add_section("Στοιχεία Συντήρησης")
            grid = GridLayout(cols=2, spacing=6, size_hint_y=None)
            grid.bind(minimum_height=grid.setter("height"))
            add_kv_row(grid, S["MESSAGES"].get("SUBSTATION_LABEL", "Υποσταθμός:"), sub_name or "-")
            add_kv_row(grid, S["MESSAGES"].get("DATE_LABEL", "Ημερομηνία:"), maint_date or "-")
            add_kv_row(grid, S["MESSAGES"].get("MAINT_TYPE_LABEL", "Τύπος Συντήρησης"), maint_type or "-")
            add_kv_row(grid, S["MESSAGES"].get("MAINT_USER_LABEL", "Χειριστής"), maint_user or "-")
            add_kv_row(grid, S["MESSAGES"].get("DIVISION_LABEL", "Τομέας"), division or "-")
            add_kv_row(grid, S["MESSAGES"].get("LOC", "Τοποθεσία"), sub_location or "-")
            content.add_widget(grid)

            add_section("Στοιχεία Διακόπτη")
            grid = GridLayout(cols=2, spacing=6, size_hint_y=None)
            grid.bind(minimum_height=grid.setter("height"))
            add_kv_row(grid, S["MESSAGES"].get("ELEMENT_TYPE_LABEL", "Τύπος"), elem_type or "-")
            add_kv_row(grid, S["MESSAGES"].get("NAME_LABEL", "Όνομα"), elem_name or "-")
            add_kv_row(grid, "S/N", serial_number or "-")
            add_kv_row(grid, "Κατασκευαστής", manufacturer or "-")
            if model_name or model_manufacturer:
                add_kv_row(
                    grid,
                    "Μοντέλο (Βάση)",
                    f"{model_name or '-'} / {model_manufacturer or '-'}",
                )
            add_kv_row(grid, "Μοντέλο (Στοιχείο)", model or "-")
            add_kv_row(grid, "Κατηγορία Διακόπτη", breaker_cat or "-")
            add_kv_row(grid, "Τάση", voltage_level or "-")
            add_kv_row(grid, S["MESSAGES"].get("GATE_LABEL", "Πύλη"), gate or "-")
            add_kv_row(grid, "Έτος Κατασκευής", manufacture_year or "-")
            content.add_widget(grid)

            add_section(S["MESSAGES"].get("MAINTENANCE_COMMENTS_SECTION", "Σχόλια Συντήρησης"))
            content.add_widget(make_wrapped_label(maint_comments or "-", bold=False))

        add_section(S["MESSAGES"].get("ELEMENT_COMMENTS_SECTION", "Σχόλια Στοιχείου"))
        content.add_widget(make_wrapped_label(element_comments or "-", bold=False))

        # Show message for transformers with no measurements (but DGA is still available)
        if not has_measurements and is_transformer:
            add_section("Πληροφορία")
            info_msg = make_wrapped_label(
                S["MESSAGES"].get(
                    "DGA_TRANSFORMER_NO_MEASUREMENTS_INFO",
                    "There are no recorded maintenance measurements for this element.\nUse the DGA buttons below to record dissolved gas measurements.",
                ),
                bold=False
            )
            content.add_widget(info_msg)

        if has_measurements:
            add_section(S["MESSAGES"].get("INSULATION_RESISTANCE_CLOSED_TITLE", "Αντίσταση Μόνωσης - Διακόπτης Κλειστός (Γη)"))
            grid = GridLayout(cols=2, spacing=6, size_hint_y=None)
            grid.bind(minimum_height=grid.setter("height"))
            add_kv_row(grid, S["MESSAGES"].get("INSULATION_LABEL_FA_GND", "ΦΑ-Γη"), fmt(ins_closed_fa, ins_closed_fa_unit))
            add_kv_row(grid, S["MESSAGES"].get("INSULATION_LABEL_FB_GND", "ΦΒ-Γη"), fmt(ins_closed_fb, ins_closed_fb_unit))
            add_kv_row(grid, S["MESSAGES"].get("INSULATION_LABEL_FC_GND", "ΦΓ-Γη"), fmt(ins_closed_fc, ins_closed_fc_unit))
            content.add_widget(grid)

            add_section(S["MESSAGES"].get("INSULATION_RESISTANCE_OPEN_TITLE", "Αντίσταση Μόνωσης - Διακόπτης Ανοικτός (Φάση-Φάση)"))
            grid = GridLayout(cols=2, spacing=6, size_hint_y=None)
            grid.bind(minimum_height=grid.setter("height"))
            add_kv_row(grid, S["MESSAGES"].get("PHASE_TO_PHASE_LABEL", "ΦΑ-ΦΑ"), fmt(ins_open_fa, ins_open_fa_unit))
            add_kv_row(grid, S["MESSAGES"].get("INSULATION_LABEL_FB", "ΦΒ-ΦΒ"), fmt(ins_open_fb, ins_open_fb_unit))
            add_kv_row(grid, S["MESSAGES"].get("INSULATION_LABEL_FC", "ΦΓ-ΦΓ"), fmt(ins_open_fc, ins_open_fc_unit))
            content.add_widget(grid)

            add_section(S["MESSAGES"].get("INSULATION_PASSAGE_TITLE", "Αντίσταση Διέλευσης (μΩ)"))
            grid = GridLayout(cols=2, spacing=6, size_hint_y=None)
            grid.bind(minimum_height=grid.setter("height"))
            add_kv_row(grid, S["MESSAGES"].get("PHASE_TO_PHASE_LABEL", "ΦΑ-ΦΑ"), fmt(cont_fa))
            add_kv_row(grid, "ΦΒ-ΦΒ", fmt(cont_fb))
            add_kv_row(grid, "ΦΓ-ΦΓ", fmt(cont_fc))
            content.add_widget(grid)

            add_section("Μετρητής Χειρισμών")
            grid = GridLayout(cols=2, spacing=6, size_hint_y=None)
            grid.bind(minimum_height=grid.setter("height"))
            add_kv_row(grid, "Αριθμός Χειρισμών", fmt(ops_count))
            content.add_widget(grid)

        if (
            has_measurements
            and breaker_category == "SF6"
            and (
                sf6_leakage_kg is not None
                or any(
                    [
                        sf6_n2_fa,
                        h2o_fa,
                        so2_fa,
                        sf6_n2_fb,
                        h2o_fb,
                        so2_fb,
                        sf6_n2_fc,
                        h2o_fc,
                        so2_fc,
                    ]
                )
            )
        ):
            add_section("Ποιότητα Αερίου SF6")
            grid = GridLayout(cols=2, spacing=6, size_hint_y=None)
            grid.bind(minimum_height=grid.setter("height"))
            add_kv_row(grid, "Διαρροή SF6 (kg)", fmt(sf6_leakage_kg))
            add_kv_row(grid, "Πλήρωση/Αντικατάσταση", sf6_leak_methodology or "-")
            add_kv_row(
                grid,
                "ΦΑ",
                f"SF6/N2 {fmt(sf6_n2_fa)} | H2O {fmt(h2o_fa)} | SO2 {fmt(so2_fa)}",
            )
            add_kv_row(
                grid,
                "ΦΒ",
                f"SF6/N2 {fmt(sf6_n2_fb)} | H2O {fmt(h2o_fb)} | SO2 {fmt(so2_fb)}",
            )
            add_kv_row(
                grid,
                "ΦΓ",
                f"SF6/N2 {fmt(sf6_n2_fc)} | H2O {fmt(h2o_fc)} | SO2 {fmt(so2_fc)}",
            )
            content.add_widget(grid)

        # Show VIDAR (vacuum) measurements for MV Vacuum breakers only
        if (
            has_measurements
            and breaker_category in ["Vacuum", "Κενού"]
            and elem_type == self.ELEM_BREAKER_MT
            and any([vidar_fa, vidar_fb, vidar_fc])
        ):
            add_section(S["MESSAGES"].get("VIDAR_SECTION_TITLE", "Έλεγχος Κενού (VIDAR)"))
            grid = GridLayout(cols=2, spacing=6, size_hint_y=None)
            grid.bind(minimum_height=grid.setter("height"))
            add_kv_row(grid, S["MESSAGES"].get("PHASE_TO_PHASE_LABEL", "ΦΑ-ΦΑ"), fmt(vidar_fa))
            add_kv_row(grid, S["MESSAGES"].get("VIDAR_LABEL_FB", "ΦΒ-ΦΒ"), fmt(vidar_fb))
            add_kv_row(grid, S["MESSAGES"].get("VIDAR_LABEL_FC", "ΦΓ-ΦΓ"), fmt(vidar_fc))
            content.add_widget(grid)

        scroll.add_widget(content)
        main_layout.add_widget(scroll)

        # Bottom buttons
        buttons_layout = BoxLayout(size_hint_y=None, height=40, spacing=10)
        
        # Show manual button if model has a manual
        if header_row and manual_pdf and os.path.exists(manual_pdf):
            manual_btn = Button(text=S["MESSAGES"].get("MANUAL_LABEL", "Manual"))
            manual_btn.bind(on_press=lambda x: self._open_model_manual(manual_pdf))
            buttons_layout.add_widget(manual_btn)
        
        close_btn = Button(text=S["BUTTONS"]["CLOSE"])
        close_btn.bind(on_press=popup.dismiss)
        buttons_layout.add_widget(close_btn)
        
        main_layout.add_widget(buttons_layout)

        popup.content = main_layout
        popup.open()

    def show_substation_dga_measurements(self, substation_id, substation_name, parent_popup=None):
        """Display all DGA measurements for a substation, grouped by transformer."""
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.gridlayout import GridLayout
        from kivy.uix.label import Label
        from kivy.uix.popup import Popup
        from kivy.uix.scrollview import ScrollView

        c = self.conn.cursor()
        
        # Get all transformers in this substation with DGA measurements
        c.execute(
            """
            SELECT DISTINCT e.id, e.name, e.serial_number, COUNT(dm.id) as dga_count
            FROM elements e
            JOIN maintenance m ON e.substation_id = ?
            LEFT JOIN dga_measurements dm ON m.id = dm.maintenance_id AND dm.element_id = e.id
            WHERE e.substation_id = ? AND m.maintenance_type = ? AND dm.id IS NOT NULL
            GROUP BY e.id, e.name, e.serial_number
            ORDER BY e.name
            """,
            (substation_id, substation_id, S["MESSAGES"].get("DGA_LABEL", "Φυσικοχημικές/Αεριοχρωματογραφία")),
        )
        dga_transformers = c.fetchall()

        popup = Popup(
            title=S["MESSAGES"].get(
                "DGA_SUBSTATION_TITLE_FMT", "{dga_label} - {substation_name}"
            ).format(
                dga_label=S["MESSAGES"].get("DGA_LABEL", "Physicochemical/Gas Chromatography"),
                substation_name=substation_name,
            ),
            size_hint=(0.9, 0.8)
        )
        
        main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        # Top button bar with "Add New" button
        top_bar = BoxLayout(size_hint_y=None, height=44, spacing=8)
        add_btn = Button(text=f"+ {S['MESSAGES'].get('DGA_ADD_MEASUREMENT_SHORT', 'Νέα Μέτρηση')}")
        add_btn.bind(on_press=lambda x, p=popup, sid=substation_id: self._show_dga_maintenance_form(parent_popup=p, preselected_substation_id=sid))
        top_bar.add_widget(add_btn)
        main_layout.add_widget(top_bar)

        if not dga_transformers:
            main_layout.add_widget(
                Label(
                    text=S["MESSAGES"].get(
                        "DGA_NO_MEASUREMENTS_FOR_SUBSTATION",
                        "No DGA measurements for this substation",
                    ),
                    size_hint_y=0.8,
                )
            )
        else:
            scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
            grid = GridLayout(cols=1, spacing=10, size_hint_y=None, padding=10)
            grid.bind(minimum_height=grid.setter("height"))

            for elem_id, elem_name, serial_num, dga_cnt in dga_transformers:
                row_layout = BoxLayout(size_hint_y=None, height=40, spacing=8)
                
                info_text = S["MESSAGES"].get(
                    "DGA_MEASUREMENTS_COUNT_FMT",
                    "{element_name} (S/N: {serial_number}) - {count} measurements",
                ).format(
                    element_name=elem_name,
                    serial_number=serial_num or "-",
                    count=dga_cnt,
                )
                info_label = Label(text=info_text, size_hint_x=0.7)
                row_layout.add_widget(info_label)

                view_btn = Button(text=S["BUTTONS"].get("VIEW", "View"), size_hint_x=0.3)
                view_btn.bind(
                    on_press=lambda x, eid=elem_id, ename=elem_name, sid=substation_id, 
                             sname=substation_name: self.show_element_dga_measurements(
                        element_id=eid, 
                        element_name=ename, 
                        substation_id=sid
                    )
                )
                row_layout.add_widget(view_btn)
                grid.add_widget(row_layout)

            scroll.add_widget(grid)
            main_layout.add_widget(scroll)

        # Close button
        btn_layout = BoxLayout(size_hint_y=None, height=44, spacing=8)
        close_btn = Button(text=S["BUTTONS"]["CLOSE"])
        close_btn.bind(on_press=popup.dismiss)
        btn_layout.add_widget(close_btn)
        main_layout.add_widget(btn_layout)

        popup.content = main_layout
        if parent_popup:
            parent_popup.dismiss()
        popup.open()

    def show_element_dga_measurements(self, element_id, element_name, substation_id):
        """Display DGA measurements for a specific transformer."""
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label
        from kivy.uix.popup import Popup

        c = self.conn.cursor()
        
        # Get element details
        c.execute(
            "SELECT name, serial_number, gate, manufacturer FROM elements WHERE id=?",
            (element_id,),
        )
        elem_row = c.fetchone()
        if not elem_row:
            show_message_popup(
                S["TITLES"]["ERROR"],
                S["MESSAGES"].get("DGA_ELEMENT_NOT_FOUND", "Element not found."),
            )
            return
        
        element_serial = elem_row[1] if isinstance(elem_row, (tuple, list)) else elem_row["serial_number"]
        element_gate = elem_row[2] if isinstance(elem_row, (tuple, list)) else elem_row["gate"]
        element_manufacturer = elem_row[3] if isinstance(elem_row, (tuple, list)) else elem_row["manufacturer"]
        
        popup = Popup(
            title=S["MESSAGES"].get("DGA_POPUP_TITLE_FMT", "DGA - {element_name}").format(element_name=element_name),
            size_hint=(0.9, 0.5)
        )
        
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
        layout.add_widget(
            Label(
                text=S["MESSAGES"].get(
                    "DGA_MEASUREMENTS_FOR_FMT", "DGA measurements for: {element_name}"
                ).format(element_name=element_name),
                size_hint_y=None,
                height=30,
            )
        )
        
        # Show DGA history in a button that will open the actual DGA history popup
        view_history_btn = Button(
            text=S["MESSAGES"].get("DGA_VIEW_HISTORY_BUTTON", "View Measurement History"),
            size_hint_y=None,
            height=44,
        )
        view_history_btn.bind(
            on_press=lambda x: self.show_dga_history_popup(
                maintenance_id=None,
                element_id=element_id,
                element_name=element_name,
                substation_id=substation_id,
                substation_name="",
                gate_value=element_gate,
                serial_number=element_serial,
                manufacturer=element_manufacturer,
            )
        )
        layout.add_widget(view_history_btn)
        
        close_btn = Button(text=S["BUTTONS"]["CLOSE"], size_hint_y=None, height=44)
        close_btn.bind(on_press=popup.dismiss)
        layout.add_widget(close_btn)
        
        popup.content = layout
        popup.open()

    def show_dga_measurement_popup(
        self,
        *,
        maintenance_id,
        element_id,
        element_name,
        substation_id,
        substation_name,
        gate_value,
        serial_number,
        manufacturer,
        dga_id=None,
    ):
        """Show DGA measurement form for add or edit."""
        if not substation_id:
            show_message_popup(
                S["TITLES"].get("ERROR", "Σφάλμα"),
                S["MESSAGES"].get("DGA_SUBSTATION_NOT_FOUND", "Substation not found for DGA entry."),
            )
            return

        # If editing existing record, load it
        edit_mode = dga_id is not None
        existing_row = None
        if edit_mode:
            c = self.conn.cursor()
            c.execute(
                """
                SELECT measurement_date, sampling_date, sampling_responsible, measurement_responsible,
                       sample_point, sampling_method, sample_temperature,
                       h2, c2h2, c2h4, c2h6, co, co2, ch4, o2, c3h8, n2, h2o,
                       density, humidity, dielectric_strength, loss_factor, surface_tension,
                       notes, report_path
                FROM dga_measurements WHERE id=?
                """,
                (dga_id,),
            )
            existing_row = c.fetchone()
            if not existing_row:
                show_message_popup(
                    S["TITLES"].get("ERROR", "Σφάλμα"),
                    S["MESSAGES"].get("DGA_RECORD_NOT_FOUND", "DGA record not found."),
                )
                return

        popup_title = (
            S["MESSAGES"].get("DGA_POPUP_TITLE_FMT", "DGA - {element_name}").format(element_name=element_name)
            if not edit_mode
            else S["MESSAGES"].get("DGA_POPUP_EDIT_TITLE_FMT", "Edit DGA - {element_name}").format(element_name=element_name)
        )
        popup = Popup(title=popup_title, size_hint=(0.92, 0.92))
        main_layout = BoxLayout(orientation="vertical", spacing=8, padding=8)
        scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
        content = GridLayout(cols=2, spacing=6, size_hint_y=None, padding=6)
        content.bind(minimum_height=content.setter("height"))

        def add_field(label, default=""):
            content.add_widget(Label(text=label, size_hint_y=None, height=34))
            ti = TextInput(text=default or "", multiline=False, size_hint_y=None, height=34)
            content.add_widget(ti)
            return ti

        def _safe_str(val):
            if val is None:
                return ""
            return str(val)

        now_txt = datetime.now().strftime("%Y-%m-%d")

        if edit_mode and existing_row:
            (meas_date, samp_date, samp_resp, meas_resp, samp_pt, samp_meth, samp_temp,
             h2_v, c2h2_v, c2h4_v, c2h6_v, co_v, co2_v, ch4_v, o2_v, c3h8_v, n2_v, h2o_v,
             dens, hum, diel, loss, surf, nts, rpt_path) = existing_row
            sampling_date = add_field(S["MESSAGES"].get("DGA_SAMPLING_DATE_LABEL", "Sampling Date"), _safe_str(samp_date or now_txt))
            measurement_date = add_field(S["MESSAGES"].get("DGA_MEASUREMENT_DATE_LABEL", "Measurement Date"), _safe_str(meas_date or now_txt))
            sample_point = add_field(S["MESSAGES"].get("DGA_SAMPLE_POINT_LABEL", "Sample Point"), _safe_str(samp_pt))
            sampling_method = add_field(S["MESSAGES"].get("DGA_METHOD_LABEL", "Method"), _safe_str(samp_meth))
            sampling_responsible = add_field(S["MESSAGES"].get("DGA_SAMPLING_RESPONSIBLE_LABEL", "Sampling Responsible"), _safe_str(samp_resp))
            measurement_responsible = add_field(S["MESSAGES"].get("DGA_MEASUREMENT_RESPONSIBLE_LABEL", "Measurement Responsible"), _safe_str(meas_resp))
            sample_temperature = add_field(S["MESSAGES"].get("DGA_SAMPLE_TEMPERATURE_LABEL", "Sample Temperature"), _safe_str(samp_temp))
            h2 = add_field("H2", _safe_str(h2_v))
            c2h2 = add_field("C2H2", _safe_str(c2h2_v))
            c2h4 = add_field("C2H4", _safe_str(c2h4_v))
            c2h6 = add_field("C2H6", _safe_str(c2h6_v))
            co = add_field("CO", _safe_str(co_v))
            co2 = add_field("CO2", _safe_str(co2_v))
            ch4 = add_field("CH4", _safe_str(ch4_v))
            o2 = add_field("O2", _safe_str(o2_v))
            c3h8 = add_field("C3H8", _safe_str(c3h8_v))
            n2 = add_field("N2", _safe_str(n2_v))
            h2o = add_field("H2O", _safe_str(h2o_v))
            density = add_field(S["MESSAGES"].get("DGA_DENSITY_LABEL", "Density"), _safe_str(dens))
            humidity = add_field(S["MESSAGES"].get("DGA_HUMIDITY_LABEL", "Humidity"), _safe_str(hum))
            dielectric_strength = add_field(S["MESSAGES"].get("DGA_DIELECTRIC_STRENGTH_LABEL", "Dielectric Strength"), _safe_str(diel))
            loss_factor = add_field(S["MESSAGES"].get("DGA_LOSS_FACTOR_LABEL", "Loss Factor"), _safe_str(loss))
            surface_tension = add_field(S["MESSAGES"].get("DGA_SURFACE_TENSION_LABEL", "Surface Tension"), _safe_str(surf))
            content.add_widget(Label(text=S["MESSAGES"].get("DGA_NOTES_LABEL", "Notes"), size_hint_y=None, height=34))
            notes = TextInput(text=_safe_str(nts), multiline=True, size_hint_y=None, height=90)
            content.add_widget(notes)
        else:
            sampling_date = add_field(S["MESSAGES"].get("DGA_SAMPLING_DATE_LABEL", "Sampling Date"), now_txt)
            measurement_date = add_field(S["MESSAGES"].get("DGA_MEASUREMENT_DATE_LABEL", "Measurement Date"), now_txt)
            sample_point = add_field(S["MESSAGES"].get("DGA_SAMPLE_POINT_LABEL", "Sample Point"), "")
            sampling_method = add_field(S["MESSAGES"].get("DGA_METHOD_LABEL", "Method"), "")
            sampling_responsible = add_field(S["MESSAGES"].get("DGA_SAMPLING_RESPONSIBLE_LABEL", "Sampling Responsible"), "")
            measurement_responsible = add_field(S["MESSAGES"].get("DGA_MEASUREMENT_RESPONSIBLE_LABEL", "Measurement Responsible"), "")
            sample_temperature = add_field(S["MESSAGES"].get("DGA_SAMPLE_TEMPERATURE_LABEL", "Sample Temperature"), "")
            h2 = add_field("H2", "")
            c2h2 = add_field("C2H2", "")
            c2h4 = add_field("C2H4", "")
            c2h6 = add_field("C2H6", "")
            co = add_field("CO", "")
            co2 = add_field("CO2", "")
            ch4 = add_field("CH4", "")
            o2 = add_field("O2", "")
            c3h8 = add_field("C3H8", "")
            n2 = add_field("N2", "")
            h2o = add_field("H2O", "")
            density = add_field(S["MESSAGES"].get("DGA_DENSITY_LABEL", "Density"), "")
            humidity = add_field(S["MESSAGES"].get("DGA_HUMIDITY_LABEL", "Humidity"), "")
            dielectric_strength = add_field(S["MESSAGES"].get("DGA_DIELECTRIC_STRENGTH_LABEL", "Dielectric Strength"), "")
            loss_factor = add_field(S["MESSAGES"].get("DGA_LOSS_FACTOR_LABEL", "Loss Factor"), "")
            surface_tension = add_field(S["MESSAGES"].get("DGA_SURFACE_TENSION_LABEL", "Surface Tension"), "")
            content.add_widget(Label(text=S["MESSAGES"].get("DGA_NOTES_LABEL", "Notes"), size_hint_y=None, height=34))
            notes = TextInput(text="", multiline=True, size_hint_y=None, height=90)
            content.add_widget(notes)

        scroll.add_widget(content)
        main_layout.add_widget(scroll)

        btns = BoxLayout(size_hint_y=None, height=44, spacing=8)

        def save_dga(_x=None):
            try:
                payload = {
                    "substation_name": substation_name or "",
                    "element_name": element_name or "",
                    "serial_number": serial_number or "",
                    "manufacturer": manufacturer or "",
                    "sample_point": sample_point.text.strip(),
                    "sampling_method": sampling_method.text.strip(),
                    "sampling_responsible": sampling_responsible.text.strip(),
                    "measurement_responsible": measurement_responsible.text.strip(),
                    "sampling_date": sampling_date.text.strip(),
                    "measurement_date": measurement_date.text.strip(),
                    "sample_temperature": sample_temperature.text.strip(),
                    "h2": h2.text.strip(),
                    "c2h2": c2h2.text.strip(),
                    "c2h4": c2h4.text.strip(),
                    "c2h6": c2h6.text.strip(),
                    "co": co.text.strip(),
                    "co2": co2.text.strip(),
                    "ch4": ch4.text.strip(),
                    "o2": o2.text.strip(),
                    "c3h8": c3h8.text.strip(),
                    "n2": n2.text.strip(),
                    "h2o": h2o.text.strip(),
                    "density": density.text.strip(),
                    "humidity": humidity.text.strip(),
                    "dielectric_strength": dielectric_strength.text.strip(),
                    "loss_factor": loss_factor.text.strip(),
                    "surface_tension": surface_tension.text.strip(),
                    "notes": notes.text.strip(),
                }

                # Ensure DGA folder exists
                folder_info = ensure_dga_folder(
                    self.conn,
                    substation_id=substation_id,
                    gate_value=gate_value,
                    element_name=element_name,
                    measurement_date=measurement_date.text.strip(),
                    db_path=self.db_path,
                )

                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_element_name = element_name.replace("/", "_").replace("\\", "_")
                file_base = f"DGA_Report_{safe_element_name}_{stamp}.xlsx"
                primary_report_path = os.path.join(folder_info["folder_path"], file_base)
                template = os.path.join(os.path.dirname(__file__), "dga report.xlsx")
                generate_dga_excel_report(template, primary_report_path, payload)

                # Copy into transformer reports folder(s) for this maintenance
                try:
                    transformer_targets = get_transformer_report_targets(
                        self.conn,
                        maintenance_id=maintenance_id,
                        gate_value=gate_value,
                        db_path=self.db_path,
                    )
                    for target_folder in transformer_targets:
                        secondary_path = os.path.join(target_folder, file_base)
                        shutil.copy2(primary_report_path, secondary_path)
                except Exception:
                    pass  # Non-fatal if secondary copy fails

                c = self.conn.cursor()
                now_db = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                if edit_mode:
                    c.execute(
                        """
                        UPDATE dga_measurements
                        SET measurement_date=?, sampling_date=?,
                            sampling_responsible=?, measurement_responsible=?,
                            sample_point=?, sampling_method=?, sample_temperature=?,
                            h2=?, c2h2=?, c2h4=?, c2h6=?, co=?, co2=?, ch4=?, o2=?, c3h8=?, n2=?, h2o=?,
                            density=?, humidity=?, dielectric_strength=?, loss_factor=?, surface_tension=?,
                            notes=?, report_path=?, updated_at=?
                        WHERE id=?
                        """,
                        (
                            measurement_date.text.strip() or None,
                            sampling_date.text.strip() or None,
                            sampling_responsible.text.strip() or None,
                            measurement_responsible.text.strip() or None,
                            sample_point.text.strip() or None,
                            sampling_method.text.strip() or None,
                            float(sample_temperature.text.replace(",", ".")) if sample_temperature.text.strip() else None,
                            float(h2.text.replace(",", ".")) if h2.text.strip() else None,
                            float(c2h2.text.replace(",", ".")) if c2h2.text.strip() else None,
                            float(c2h4.text.replace(",", ".")) if c2h4.text.strip() else None,
                            float(c2h6.text.replace(",", ".")) if c2h6.text.strip() else None,
                            float(co.text.replace(",", ".")) if co.text.strip() else None,
                            float(co2.text.replace(",", ".")) if co2.text.strip() else None,
                            float(ch4.text.replace(",", ".")) if ch4.text.strip() else None,
                            float(o2.text.replace(",", ".")) if o2.text.strip() else None,
                            float(c3h8.text.replace(",", ".")) if c3h8.text.strip() else None,
                            float(n2.text.replace(",", ".")) if n2.text.strip() else None,
                            float(h2o.text.replace(",", ".")) if h2o.text.strip() else None,
                            float(density.text.replace(",", ".")) if density.text.strip() else None,
                            float(humidity.text.replace(",", ".")) if humidity.text.strip() else None,
                            float(dielectric_strength.text.replace(",", ".")) if dielectric_strength.text.strip() else None,
                            float(loss_factor.text.replace(",", ".")) if loss_factor.text.strip() else None,
                            float(surface_tension.text.replace(",", ".")) if surface_tension.text.strip() else None,
                            notes.text.strip() or None,
                            primary_report_path,
                            now_db,
                            dga_id,
                        ),
                    )
                else:
                    c.execute(
                        """
                        INSERT INTO dga_measurements (
                            maintenance_id, element_id, substation_id,
                            measurement_date, sampling_date,
                            sampling_responsible, measurement_responsible,
                            sample_point, sampling_method, sample_temperature,
                            h2, c2h2, c2h4, c2h6, co, co2, ch4, o2, c3h8, n2, h2o,
                            density, humidity, dielectric_strength, loss_factor, surface_tension,
                            notes, report_path, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            maintenance_id,
                            element_id,
                            substation_id,
                            measurement_date.text.strip() or None,
                            sampling_date.text.strip() or None,
                            sampling_responsible.text.strip() or None,
                            measurement_responsible.text.strip() or None,
                            sample_point.text.strip() or None,
                            sampling_method.text.strip() or None,
                            float(sample_temperature.text.replace(",", ".")) if sample_temperature.text.strip() else None,
                            float(h2.text.replace(",", ".")) if h2.text.strip() else None,
                            float(c2h2.text.replace(",", ".")) if c2h2.text.strip() else None,
                            float(c2h4.text.replace(",", ".")) if c2h4.text.strip() else None,
                            float(c2h6.text.replace(",", ".")) if c2h6.text.strip() else None,
                            float(co.text.replace(",", ".")) if co.text.strip() else None,
                            float(co2.text.replace(",", ".")) if co2.text.strip() else None,
                            float(ch4.text.replace(",", ".")) if ch4.text.strip() else None,
                            float(o2.text.replace(",", ".")) if o2.text.strip() else None,
                            float(c3h8.text.replace(",", ".")) if c3h8.text.strip() else None,
                            float(n2.text.replace(",", ".")) if n2.text.strip() else None,
                            float(h2o.text.replace(",", ".")) if h2o.text.strip() else None,
                            float(density.text.replace(",", ".")) if density.text.strip() else None,
                            float(humidity.text.replace(",", ".")) if humidity.text.strip() else None,
                            float(dielectric_strength.text.replace(",", ".")) if dielectric_strength.text.strip() else None,
                            float(loss_factor.text.replace(",", ".")) if loss_factor.text.strip() else None,
                            float(surface_tension.text.replace(",", ".")) if surface_tension.text.strip() else None,
                            notes.text.strip() or None,
                            primary_report_path,
                            now_db,
                            now_db,
                        ),
                    )
                self.conn.commit()
                popup.dismiss()

                # Open report after save
                from reports import open_file
                def _open():
                    open_file(primary_report_path)

                show_message_popup(
                    S["TITLES"].get("SUCCESS", "Επιτυχία"),
                    S["MESSAGES"].get("DGA_SAVE_SUCCESS_FMT", "DGA report saved:\n{path}").format(path=primary_report_path),
                    callback=_open,
                )
            except Exception as exc:
                self.conn.rollback()
                show_message_popup(
                    S["TITLES"].get("ERROR", "Σφάλμα"),
                    S["MESSAGES"].get("DGA_SAVE_FAILED_FMT", "Failed to save DGA:\n{error}").format(error=str(exc)),
                )

        save_btn = Button(text=S["BUTTONS"].get("SAVE", "Αποθήκευση"))
        save_btn.bind(on_press=save_dga)
        btns.add_widget(save_btn)

        cancel_btn = Button(text=S["BUTTONS"].get("CANCEL", "Ακύρωση"))
        cancel_btn.bind(on_press=popup.dismiss)
        btns.add_widget(cancel_btn)

        main_layout.add_widget(btns)
        popup.content = main_layout
        popup.open()

    def show_dga_history_popup(
        self,
        *,
        maintenance_id,
        element_id,
        element_name,
        substation_id,
        substation_name,
        gate_value,
        serial_number,
        manufacturer,
    ):
        """Show list of DGA measurements for this element, with actions to open/edit/delete."""
        c = self.conn.cursor()
        c.execute(
            """
            SELECT id, measurement_date, sampling_date, report_path, created_at
            FROM dga_measurements
            WHERE element_id=?
            ORDER BY measurement_date DESC, created_at DESC
            """,
            (element_id,),
        )
        rows = c.fetchall()

        popup = Popup(
            title=S["MESSAGES"].get("DGA_HISTORY_TITLE_FMT", "DGA History - {element_name}").format(element_name=element_name),
            size_hint=(0.92, 0.88),
        )
        main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        if not rows:
            main_layout.add_widget(
                Label(
                    text=S["MESSAGES"].get("DGA_NO_MEASUREMENTS_FOR_ELEMENT", "No DGA measurements found for this element."),
                    size_hint_y=0.8,
                )
            )
        else:
            scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
            content = GridLayout(cols=1, spacing=6, size_hint_y=None, padding=6)
            content.bind(minimum_height=content.setter("height"))

            for row in rows:
                dga_id, meas_date, samp_date, rpt_path, created = row
                row_layout = BoxLayout(orientation="vertical", size_hint_y=None, height=80, padding=4, spacing=4)

                info_line = Label(
                    text=S["MESSAGES"].get(
                        "DGA_HISTORY_ROW_FMT",
                        "Measurement: {measurement_date} | Sampling: {sampling_date} | Created: {created_at}",
                    ).format(
                        measurement_date=meas_date or "-",
                        sampling_date=samp_date or "-",
                        created_at=created or "-",
                    ),
                    size_hint_y=None,
                    height=28,
                )
                row_layout.add_widget(info_line)

                btns = BoxLayout(size_hint_y=None, height=38, spacing=6)

                def _make_open(path):
                    def _open(_x):
                        from reports import open_file
                        open_file(path)
                    return _open

                def _make_edit(did):
                    def _edit(_x):
                        popup.dismiss()
                        self.show_dga_measurement_popup(
                            maintenance_id=maintenance_id,
                            element_id=element_id,
                            element_name=element_name,
                            substation_id=substation_id,
                            substation_name=substation_name,
                            gate_value=gate_value,
                            serial_number=serial_number,
                            manufacturer=manufacturer,
                            dga_id=did,
                        )
                    return _edit

                def _make_delete(did, path):
                    def _del(_x):
                        self._confirm_delete_dga(did, path, popup, element_id, element_name, substation_id, substation_name, gate_value, serial_number, manufacturer, maintenance_id)
                    return _del

                open_btn = Button(text=S["MESSAGES"].get("DGA_OPEN_REPORT_BUTTON", "Open Report"))
                open_btn.bind(on_press=_make_open(rpt_path))
                btns.add_widget(open_btn)

                edit_btn = Button(text=S["BUTTONS"].get("EDIT", "Edit"))
                edit_btn.bind(on_press=_make_edit(dga_id))
                btns.add_widget(edit_btn)

                delete_btn = Button(text=S["BUTTONS"].get("DELETE", "Delete"))
                delete_btn.bind(on_press=_make_delete(dga_id, rpt_path))
                btns.add_widget(delete_btn)

                row_layout.add_widget(btns)
                content.add_widget(row_layout)

            scroll.add_widget(content)
            main_layout.add_widget(scroll)

        bottom_btns = BoxLayout(size_hint_y=None, height=44, spacing=8)

        # Add new measurement
        add_btn = Button(text=S["MESSAGES"].get("DGA_NEW_MEASUREMENT_LABEL", "New DGA Measurement"))
        add_btn.bind(
            on_press=lambda _x: (
                popup.dismiss(),
                self.show_dga_measurement_popup(
                    maintenance_id=maintenance_id,
                    element_id=element_id,
                    element_name=element_name,
                    substation_id=substation_id,
                    substation_name=substation_name,
                    gate_value=gate_value,
                    serial_number=serial_number,
                    manufacturer=manufacturer,
                    dga_id=None,
                ),
            )
        )
        bottom_btns.add_widget(add_btn)

        close_btn = Button(text=S["BUTTONS"].get("CLOSE", "Κλείσιμο"))
        close_btn.bind(on_press=popup.dismiss)
        bottom_btns.add_widget(close_btn)

        main_layout.add_widget(bottom_btns)
        popup.content = main_layout
        popup.open()

    def _confirm_delete_dga(self, dga_id, report_path, parent_popup, element_id, element_name, substation_id, substation_name, gate_value, serial_number, manufacturer, maintenance_id):
        """Confirm before deleting a DGA record and its report file."""
        from reports import show_confirm

        def confirm():
            c = self.conn.cursor()
            c.execute("DELETE FROM dga_measurements WHERE id=?", (dga_id,))
            self.conn.commit()
            try:
                if report_path and os.path.exists(report_path):
                    os.remove(report_path)
            except Exception:
                pass
            parent_popup.dismiss()
            # Reopen history
            self.show_dga_history_popup(
                maintenance_id=maintenance_id,
                element_id=element_id,
                element_name=element_name,
                substation_id=substation_id,
                substation_name=substation_name,
                gate_value=gate_value,
                serial_number=serial_number,
                manufacturer=manufacturer,
            )

        show_confirm(
            S["MESSAGES"].get("CONFIRM_DELETE_DGA_TITLE", "Delete Confirmation"),
            S["MESSAGES"].get(
                "CONFIRM_DELETE_DGA_MSG",
                "Are you sure you want to delete this DGA report?\n\nDeletion is PERMANENT.",
            ),
            yes_callback=confirm,
            yes_color=(1, 0, 0, 1),
            yes_text=S["BUTTONS"].get("YES", "Yes"),
            no_text=S["BUTTONS"].get("NO", "No"),
        )

    def generate_pdf_report(self, maintenance_id, element_id, element_name):
        from reports import generate_pdf_report as _f
        return _f(self, maintenance_id, element_id, element_name)

    def confirm_delete_maintenance(self, maintenance_id, parent_popup):
        """Confirm before deleting a maintenance record."""
        from reports import show_confirm

        def confirm():
            self.delete_maintenance(maintenance_id, parent_popup)

        show_confirm(
            "Επιβεβαίωση Διαγραφής",
            S["MESSAGES"].get(
                "CONFIRM_DELETE_MAINT_FMT",
                "Είστε σίγουροι ότι θέλετε να διαγράψετε\nαυτή τη συντήρηση;\n\n"
                "Η διαγραφή είναι ΜΟΝΙΜΗ και θα διαγραφούν και οι σχετικοί φάκελοι/αρχεία.",
            ),
            yes_callback=confirm,
            yes_color=(1, 0, 0, 1),
            yes_text="ΝΑΙ",
            no_text="ΟΧΙ",
        )

    def delete_maintenance(self, maintenance_id, parent_popup):
        """Delete a maintenance record and update related last maintenance dates"""
        c = self.conn.cursor()

        # Get substation_id and affected elements before deletion
        c.execute("SELECT substation_id FROM maintenance WHERE id=?", (maintenance_id,))
        result = c.fetchone()
        if not result:
            show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"].get("MAINTENANCE_NOT_FOUND", "Η συντήρηση δεν βρέθηκε."))
            return
        substation_id = result[0]

        c.execute(
            "SELECT element_id FROM maintenance_elements WHERE maintenance_id=?",
            (maintenance_id,),
        )
        affected_elements = [row[0] for row in c.fetchall()]

        # Try deleting associated storage folders first (permanent deletion).
        try:
            delete_maintenance_folders(self.conn, maintenance_id)
        except Exception:
            pass

        # Explicitly delete maintenance_elements records first
        c.execute(
            "DELETE FROM maintenance_elements WHERE maintenance_id=?", (maintenance_id,)
        )

        # Delete the maintenance record
        c.execute("DELETE FROM maintenance WHERE id=?", (maintenance_id,))

        # Update last maintenance date for each affected element
        for element_id in affected_elements:
            c.execute(
                """
                SELECT m.date_time 
                FROM maintenance m
                JOIN maintenance_elements me ON m.id = me.maintenance_id
                WHERE me.element_id = ?
                ORDER BY m.date_time DESC
                LIMIT 1
            """,
                (element_id,),
            )
            result = c.fetchone()
            new_date = result[0] if result else ""
            c.execute(
                "UPDATE elements SET maintenance_date=? WHERE id=?",
                (new_date, element_id),
            )

        # Update last maintenance date for the substation
        c.execute(
            """
            SELECT MAX(date_time) 
            FROM maintenance 
            WHERE substation_id=?
        """,
            (substation_id,),
        )
        result = c.fetchone()
        new_sub_date = result[0] if result and result[0] else ""
        c.execute(
            "UPDATE substations SET last_maintenance=? WHERE id=?",
            (new_sub_date, substation_id),
        )

        self.conn.commit()
        parent_popup.dismiss()

        # Refresh both maintenance history and main records view
        def on_close():
            self.show_maintenance_history(None)
            self.show_records(None)

        show_message_popup(S["TITLES"]["SUCCESS"], S["MESSAGES"].get("MAINTENANCE_DELETED", "Η συντήρηση διαγράφηκε!"), callback=on_close)

    def confirm_delete_maintenance_for_substation(
        self,
        maintenance_id,
        parent_popup,
        substation_id,
        substation_name,
        parent_display_popup=None,
    ):
        """Confirm before deleting a maintenance record for a substation."""
        from reports import show_confirm

        def confirm():
            self.delete_maintenance_for_substation(
                maintenance_id,
                parent_popup,
                substation_id,
                substation_name,
                parent_display_popup,
            )

        show_confirm(
            "Επιβεβαίωση Διαγραφής",
            f'Είστε σίγουροι ότι θέλετε να διαγράψετε\nτη συντήρηση του υποσταθμού "{substation_name}";\n\n'
            "Η διαγραφή είναι ΜΟΝΙΜΗ και θα διαγραφούν και οι σχετικοί φάκελοι/αρχεία.",
            yes_callback=confirm,
            yes_color=(1, 0, 0, 1),
            yes_text="ΝΑΙ",
            no_text="ΟΧΙ",
        )

    def delete_maintenance_for_substation(
        self,
        maintenance_id,
        parent_popup,
        substation_id,
        substation_name,
        parent_display_popup=None,
    ):
        """Delete a maintenance record, update last maintenance dates, and refresh substation-specific view"""
        c = self.conn.cursor()

        # Get affected elements before deletion
        c.execute(
            "SELECT element_id FROM maintenance_elements WHERE maintenance_id=?",
            (maintenance_id,),
        )
        affected_elements = [row[0] for row in c.fetchall()]

        # Try deleting associated storage folders first (permanent deletion).
        try:
            delete_maintenance_folders(self.conn, maintenance_id)
        except Exception:
            pass

        # Explicitly delete maintenance_elements records first
        c.execute(
            "DELETE FROM maintenance_elements WHERE maintenance_id=?", (maintenance_id,)
        )

        # Delete the maintenance record
        c.execute("DELETE FROM maintenance WHERE id=?", (maintenance_id,))

        # Update last maintenance date for each affected element
        for element_id in affected_elements:
            c.execute(
                """
                SELECT m.date_time 
                FROM maintenance m
                JOIN maintenance_elements me ON m.id = me.maintenance_id
                WHERE me.element_id = ?
                ORDER BY m.date_time DESC
                LIMIT 1
            """,
                (element_id,),
            )
            result = c.fetchone()
            new_date = result[0] if result else None
            c.execute(
                "UPDATE elements SET maintenance_date=? WHERE id=?",
                (new_date, element_id),
            )

        # Update last maintenance date for the substation
        c.execute(
            """
            SELECT MAX(date_time) 
            FROM maintenance 
            WHERE substation_id=?
        """,
            (substation_id,),
        )
        result = c.fetchone()
        new_sub_date = result[0] if (result and result[0] is not None) else None
        c.execute(
            "UPDATE substations SET last_maintenance=? WHERE id=?",
            (new_sub_date, substation_id),
        )

        self.conn.commit()

        # Close both popups - maintenance history and parent display
        parent_popup.dismiss()
        if parent_display_popup:
            parent_display_popup.dismiss()

    def show_isolation_requests(self, instance=None):
        from isolation_ui import show_isolation_requests as _f
        return _f(self, instance)

    def show_add_isolation_request(self, parent_popup):
        from isolation_ui import show_add_isolation_request as _f
        return _f(self, parent_popup)

    def show_isolation_request_details(self, request_id, parent_popup):
        from isolation_ui import show_isolation_request_details as _f
        return _f(self, request_id, parent_popup)

    def show_models_management(self, instance):
        """Show model management interface"""
        show_models_management(self)


if __name__ == "__main__":
    SubstationApp().run()
