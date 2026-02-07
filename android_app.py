"""
Android Kivy App for DB Substations - local DB only
"""
"""
Android Kivy App for DB Substations - local DB only
"""
import sys
import traceback
import os
import sqlite3
import shutil
from datetime import datetime

# Set up logging FIRST before any other imports
from kivy.logger import Logger
Logger.info('APP: ========== Starting DB Substations App ==========' )
Logger.info(f'APP: Python version: {sys.version}')

try:
    import kivy
    Logger.info(f'APP: Kivy version: {kivy.__version__}')
    kivy.require('2.3.0')  # Minimum version with Android Cython modules
    from kivy.app import App
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.gridlayout import GridLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.textinput import TextInput
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.spinner import Spinner
    from kivy.clock import Clock
    from kivy.utils import platform
except Exception as e:
    Logger.warning(f'APP: Kivy import failed: {str(e)}')
    platform = 'unknown'

# Android-specific imports
filechooser = None
FileChooserListView = None
try:
    from plyer import filechooser
except Exception as e:
    Logger.warning(f'APP: plyer.filechooser import failed: {str(e)}')
    filechooser = None
try:
    from kivy.uix.filechooser import FileChooserListView
except Exception as e:
    Logger.warning(f'APP: FileChooserListView import failed: {str(e)}')
    FileChooserListView = None

import json
Logger.info('APP: JSON import successful')

import threading
Logger.info('APP: Threading import successful')

class SubstationAndroidApp(App):
    # Element types - matches desktop app
    ELEMENT_TYPES = [
        'Διακόπτης ΥΤ',
        'Διακόπτης ΜΤ',
        'Μετασχηματιστής 150/20KV',
        'Motor Drive',
        'Μ/Σ Εγχύσεως',
        'Μ/Σ Έντασης',
        'Μ/Σ Τάσης',
        'Μ/Σ ΧΤ/ΜΤ (ΒΜΣ)',
        'Αποζεύκτης',
        'Ασφαλειοαποζεύκτης',
        'Γειωτής',
        'Συστοιχία Πυκνωτών',
        'Αντίσταση Κόμβου',
        'Αλεξικέραυνο',
        'Συστοιχία Συσσωρευτών'
    ]
    VOLTAGE_LEVELS = ['20 KV', '150 KV', '20/150 KV']
    OPERATING_STATUS = ['Ενεργή', 'Ανενεργή']
    INSTALLATION_SPACE = ['Εσωτερικός', 'Εξωτερικός']
    ELEMENT_FIELD_DEFS = [
        {'key': 'name', 'label': 'Όνομα Στοιχείου', 'type': 'text', 'hint': 'Όνομα Στοιχείου'},
        {'key': 'serial_number', 'label': 'Σειριακός Αριθμός', 'type': 'text', 'hint': 'Σειριακός Αριθμός'},
        {'key': 'maintenance_date', 'label': 'Ημερομηνία τελευταίας συντήρησης', 'type': 'text', 'hint': 'YYYY-MM-DD'},
        {'key': 'voltage_level', 'label': 'Επίπεδο Τάσης', 'type': 'text', 'hint': 'π.χ. 20 KV, 150 KV'},
        {'key': 'manufacturer', 'label': 'Κατασκευαστής', 'type': 'text', 'hint': 'Κατασκευαστής'},
        {'key': 'type', 'label': 'Τύπος', 'type': 'text', 'hint': 'Τύπος'},
        {'key': 'manufacture_year', 'label': 'Έτος Κατασκευής', 'type': 'text', 'hint': 'π.χ. 2010'},
        {'key': 'model', 'label': 'Μοντέλο', 'type': 'text', 'hint': 'Μοντέλο'},
        {'key': 'model_version', 'label': 'Έκδοση Μοντέλου', 'type': 'text', 'hint': 'Έκδοση'},
        {'key': 'operating_status', 'label': 'Κατάσταση Λειτουργίας', 'type': 'spinner', 'values': OPERATING_STATUS},
        {'key': 'installation_space', 'label': 'Χώρος Εγκατάστασης', 'type': 'spinner', 'values': INSTALLATION_SPACE},
        {'key': 'maintenance_cycle', 'label': 'Κύκλος Συντήρησης (μήνες)', 'type': 'text', 'hint': 'π.χ. 12'},
        {'key': 'gate', 'label': 'Πύλη', 'type': 'text', 'hint': 'π.χ. ΠΥΛΗ 1'},
    ]
    INSPECTION_FIELDS = [
        {'type': 'section', 'title': '1. Έλεγχος Χώρων ΥΣ'},
        'Παρατηρήσεις (1. Έλεγχος Χώρων ΥΣ)',
        'Έλεγχος εξωτερικών & εσωτερικών Θυρών ΥΣ',
        'Έλεγχος εσωτερικού Χώρου κτηρίου (Φωτισμός, κλιματισμός κλπ)',
        'Έλεγχος περιβάλλοντος χώρου (βλάστηση, δένδρα, φωτισμός κλπ)',
        'Έλεγχος μέσων πυρόσβεσης γενικά',
        {'type': 'section', 'title': '2. Μ/Σ 150/20kV & Διακόπτες 150kV & 20kV'},
        'Παρατηρήσεις (2. Μ/Σ 150/20kV & Διακόπτες 150kV & 20kV)',
        'Οπτικός έλεγχος, διαρροής/στάθμης/θερμοκρασίας λαδιού, silica gel στον Μ/Σ',
        'Οπτικός έλεγχος διαρροής λαδιού ή πίεσης SF6 ή πίεσης αέρα στους Διακόπτες Ισχύος 150kV & 20kV',
        'Έλεγχος λειτουργίας ανεμιστήρων Μ/Σ',
        'Οπτικός έλεγχος Μ/Σ εγχύσεως, ΜΣΕ, ΜΣΤ, Μ/Σ εσωτ. Υπηρ., αντίστασης κόμβου (θερμοκρασία)',
        'Οπτικός έλεγχος Μονωτήρων (ρύπανση, εκδορές κ.α.)',
        'Οπτικός έλεγχος τηκτών πυκνωτών',
        'Έλεγχος σημάνσεων στους Πίνακες Μ/Σ , Α/Δ 150kV & 20kV',
        'Λήψη φωτογραφίας όταν απαιτείται',
        {'type': 'section', 'title': '3α. Υπαίθριες πύλες 20 kV'},
        'Παρατηρήσεις (3α. Υπαίθριες πύλες 20 kV)',
        'Οπτικός έλεγχος των πυλών, A/Z και γενικά του ικριώματος για τυχόν φωλιές από πτηνά, σπασίματα, μονωτήρες, κλαδιά, σύρματα κλπ',
        {'type': 'section', 'title': '3β. Πίνακες 20 kV'},
        'Παρατηρήσεις (3β. Πίνακες 20 kV)',
        'Οπτικός έλεγχος στους πίνακες Διακοπτών 20kV (αναγγελίες, ενδείξεις οργάνων, πόρτες) και έλεγχος θορύβων, ιονισμών',
        'Έλεγχοι υγρασίας (υπόγειο, κανάλια καλωδίων), αφυγραντήρων, θερμαντικών, φορητών πυροσβεστήρων',
        {'type': 'section', 'title': '4. Κτίριο χειρισμών & Τ.Α.Σ.'},
        'Παρατηρήσεις (4. Κτίριο χειρισμών & Τ.Α.Σ.)',
        'Έλεγχος φορτιστή 110 V οπτικά με έλεγχο της τάσης, έντασης και καταγραφή',
        'Έλεγχος για alarm έλλειψης DC στον γενικό πίνακα DC',
        'Οπτικός έλεγχος διαρροών στοιχείων συσσωρευτών',
        {'type': 'section', 'title': '5. Αποζεύκτες Γραμμών'},
        'Παρατηρήσεις (5. Αποζεύκτες Γραμμών)',
        'Οπτικός έλεγχος των ΑΠ/Ζ και των "γεφυρών" αυτών στον 1ο Στύλο κάθε Γραμμής (σπασμένοι ΑΠ/Ζ, μονωτήρες, εκτονωμένα Α/Ξ κλπ)',
        {'type': 'section', 'title': '6. PC ΧΕΙΡΙΣΜΩΝ'},
        'Παρατηρήσεις (6. PC ΧΕΙΡΙΣΜΩΝ)',
        'Έλεγχος λειτουργίας ψηφιακού συστήματος (χειρισμοί, ενδείξεις, σημάνσεις)',
        'Τροφοδοσία υπολογιστή',
        {'type': 'section', 'title': '7. Απόψεις'},
        'Απόψεις - Προτάσεις'
    ]
    
    

    def _ensure_change_log_path(self):
        if not self.change_log_path:
            try:
                if self.local_db_path and os.path.exists(self.local_db_path):
                    base_dir = os.path.dirname(self.local_db_path)
                else:
                    base_dir = self.user_data_dir
            except Exception:
                base_dir = os.getcwd()
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.change_log_path = os.path.join(base_dir, f'change_log_{timestamp}.jsonl')
            try:
                os.makedirs(base_dir, exist_ok=True)
                with open(self.change_log_path, 'a', encoding='utf-8'):
                    pass
            except Exception:
                pass

    def _settings_path(self):
        try:
            base_dir = self.user_data_dir
        except Exception:
            base_dir = os.getcwd()
        return os.path.join(base_dir, 'android_settings.json')

    def _load_settings(self):
        try:
            with open(self._settings_path(), 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_settings(self, data):
        try:
            os.makedirs(os.path.dirname(self._settings_path()), exist_ok=True)
            with open(self._settings_path(), 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            Logger.warning(f'APP: Failed to save settings: {str(e)}')

    def _get_saved_db_path(self):
        settings = self._load_settings()
        return settings.get('local_db_path') or ''

    def _set_saved_db_path(self, db_path):
        settings = self._load_settings()
        settings['local_db_path'] = db_path
        self._save_settings(settings)

    def _generate_temp_id(self):
        return -int(datetime.now().timestamp() * 1000)

    def _auto_load_saved_db(self):
        saved_path = self._get_saved_db_path()
        if not saved_path:
            return False
        try:
            db_path = self._prepare_local_db_path(saved_path)
        except Exception as e:
            Logger.warning(f'APP: Failed to auto-load saved DB: {str(e)}')
            return False
        self.local_db_path = db_path
        self.data_mode = 'local'
        self.change_log_path = None
        self._ensure_change_log_path()
        if hasattr(self, 'mode_label'):
            self.mode_label.text = 'Πηγή: Τοπική Βάση'
        return True

    def _copy_content_uri_to_file(self, uri_str: str) -> str:
        target_dir = getattr(self, 'user_data_dir', None) or os.getcwd()
        os.makedirs(target_dir, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        target_path = os.path.join(target_dir, f'local_db_{timestamp}.db')
        if platform != 'android':
            raise RuntimeError('Android file copy only supported on Android platform')
        try:
            from jnius import autoclass, jarray, jbyte
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            current_activity = PythonActivity.mActivity
            content_resolver = current_activity.getContentResolver()
            Uri = autoclass('android.net.Uri')
            input_stream = content_resolver.openInputStream(Uri.parse(uri_str))
            if input_stream is None:
                raise RuntimeError('Unable to open selected file')
            FileOutputStream = autoclass('java.io.FileOutputStream')
            output_stream = FileOutputStream(target_path)
            buf = jarray(jbyte)(1024 * 1024)
            while True:
                count = input_stream.read(buf)
                if count == -1:
                    break
                output_stream.write(buf, 0, count)
            output_stream.flush()
            output_stream.close()
            input_stream.close()
            return target_path
        except Exception as e:
            raise RuntimeError(f'Unable to read selected file: {str(e)}') from e

    def _append_change_log(self, operation, table, payload):
        try:
            self._ensure_change_log_path()
            record = {
                'ts': datetime.now().isoformat(timespec='seconds'),
                'operation': operation,
                'table': table,
                'payload': payload
            }
            with open(self.change_log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
        except Exception as e:
            Logger.warning(f'APP: Failed to write change log: {str(e)}')

    def _get_local_conn(self):
        if not self.local_db_path:
            raise RuntimeError('Local DB path not set')
        conn = sqlite3.connect(f'file:{self.local_db_path}?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def _local_table_columns(self, conn, table_name):
        cur = conn.cursor()
        cur.execute(f'PRAGMA table_info({table_name})')
        return {row[1] for row in cur.fetchall()}

    def _local_fetch_substations(self):
        conn = self._get_local_conn()
        cur = conn.cursor()
        cur.execute('SELECT id, name, location, adoption_date, division FROM substations ORDER BY name')
        substations = [dict(row) for row in cur.fetchall()]
        conn.close()
        return substations

    def _local_fetch_elements(self, substation_id):
        conn = self._get_local_conn()
        cur = conn.cursor()
        columns = self._local_table_columns(conn, 'elements')
        desired = [
            'id', 'substation_id', 'element_type', 'name', 'serial_number', 'maintenance_date',
            'voltage_level', 'manufacturer', 'type', 'element_model_id', 'manufacture_year',
            'model', 'model_version', 'operating_status', 'installation_space', 'maintenance_cycle',
            'gate', 'is_main_switch', 'breaker_category'
        ]
        select_parts = []
        for col in desired:
            if col in columns:
                select_parts.append(col)
            elif col == 'gate' and 'bar' in columns:
                select_parts.append('bar AS gate')
            else:
                select_parts.append(f"NULL AS {col}")
        query = f"SELECT {', '.join(select_parts)} FROM elements WHERE substation_id = ? ORDER BY name"
        cur.execute(query, (substation_id,))
        rows = [dict(row) for row in cur.fetchall()]
        conn.close()
        return rows

    def _local_insert(self, table, data):
        return self._generate_temp_id()

    def _local_delete(self, table, row_id):
        return

    def open_local_db_picker(self):
        self._prompt_local_db_path()

    def _on_local_db_selected(self, selection):
        if selection and len(selection) > 0:
            self.use_local_mode(selection[0])

    def _prompt_local_db_path(self):
        popup = Popup(title='Άνοιγμα Τοπικής Βάσης', size_hint=(0.9, 0.4))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        layout.add_widget(Label(text='Δώσε πλήρες path του αρχείου .db'))
        default_path = self._get_saved_db_path() or '/storage/emulated/0/Download/substations.db'
        path_input = TextInput(text=default_path, hint_text='/storage/emulated/0/Download/substations.db', multiline=False)
        layout.add_widget(path_input)

        chooser_layout = BoxLayout(size_hint_y=0.25, spacing=10)
        choose_btn = Button(text='Αναζήτηση αρχείου')
        choose_btn.disabled = not (filechooser or FileChooserListView)

        def open_picker():
            if platform == 'android':
                self._open_android_document_picker(_selected)
                return
            if not filechooser:
                if FileChooserListView:
                    self.show_error('Ο επιλογέας αρχείων του Android δεν είναι διαθέσιμος. Χρησιμοποίησε τη λίστα αρχείων στο παράθυρο.')
                    return
                self.show_error('Ο επιλογέας αρχείων δεν είναι διαθέσιμος')
                return

            def _selected(selection):
                if selection and len(selection) > 0:
                    raw_value = selection[0]
                    if raw_value is None:
                        self.show_error('Ο επιλογέας επέστρεψε κενή επιλογή (None).')
                        return
                    if isinstance(raw_value, bytes):
                        selected_path = raw_value.decode('utf-8', errors='ignore')
                    else:
                        selected_path = str(raw_value)
                    if selected_path.strip().lower() in ('', 'none', 'null'):
                        self.show_error('Ο επιλογέας επέστρεψε κενή επιλογή (None).')
                        return
                    Logger.info(f'APP: File chooser selected: {selected_path}')
                    Clock.schedule_once(lambda _dt: setattr(path_input, 'text', selected_path), 0)

            filechooser.open_file(on_selection=_selected)

        choose_btn.bind(on_press=lambda _x: open_picker())
        chooser_layout.add_widget(choose_btn)
        layout.add_widget(chooser_layout)

        if FileChooserListView:
            chooser_path = os.path.dirname(default_path) if default_path else '/storage/emulated/0'
            file_chooser = FileChooserListView(filters=['*.db'], path=chooser_path, size_hint_y=0.6)
            def _file_list_selected(_instance, selection):
                if selection:
                    raw_value = selection[0]
                    if raw_value is None:
                        self.show_error('Ο επιλογέας επέστρεψε κενή επιλογή (None).')
                        return
                    if isinstance(raw_value, bytes):
                        selected_path = raw_value.decode('utf-8', errors='ignore')
                    else:
                        selected_path = str(raw_value)
                    if selected_path.strip().lower() in ('', 'none', 'null'):
                        self.show_error('Ο επιλογέας επέστρεψε κενή επιλογή (None).')
                        return
                    Logger.info(f'APP: File list selected: {selected_path}')
                    Clock.schedule_once(lambda _dt: setattr(path_input, 'text', selected_path), 0)
            file_chooser.bind(selection=_file_list_selected)
            file_chooser.bind(on_submit=lambda _instance, selection, _touch: _file_list_selected(_instance, selection))
            layout.add_widget(file_chooser)

        buttons = BoxLayout(size_hint_y=0.3, spacing=10)
        open_btn = Button(text='Άνοιγμα')
        open_btn.bind(on_press=lambda _x: (popup.dismiss(), self.use_local_mode(path_input.text.strip())))
        cancel_btn = Button(text='Ακύρωση')
        cancel_btn.bind(on_press=popup.dismiss)
        buttons.add_widget(open_btn)
        buttons.add_widget(cancel_btn)
        layout.add_widget(buttons)
        popup.content = layout
        popup.open()

    def _open_android_document_picker(self, on_selected):
        if platform != 'android':
            Logger.warning('APP: SAF picker only available on Android platform')
            self.show_error('Ο επιλογέας αρχείων είναι διαθέσιμος μόνο σε Android.')
            return
        # Request permissions before proceeding
        try:
            from android.permissions import request_permissions, Permission, check_permission
            needed_perms = [
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
            ]
            # Check if permissions are already granted
            perms_granted = all(check_permission(p) for p in needed_perms)
            if not perms_granted:
                # Request permissions and return, user must retry after granting
                request_permissions(needed_perms)
                self.show_error('Απαιτούνται δικαιώματα αποθήκευσης. Παρακαλώ επιτρέψτε τα και ξαναδοκιμάστε.')
                return
        except Exception as perm_e:
            Logger.warning(f'APP: Permission check/request failed: {str(perm_e)}')
            # Continue, may work on older Android or if permissions not enforced

        try:
            from android import activity
            from jnius import autoclass
        except Exception as e:
            Logger.warning(f'APP: Android SAF picker not available: {str(e)}')
            self.show_error('Ο επιλογέας αρχείων δεν είναι διαθέσιμος')
            return

        try:
            Intent = autoclass('android.content.Intent')
            Activity = autoclass('android.app.Activity')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')

            intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            intent.setType('*/*')

            request_code = 61423

            def _activity_result(req_code, result_code, data):
                if req_code != request_code:
                    Logger.warning('APP: Activity result request code mismatch.')
                    self.show_error('Εσωτερικό σφάλμα επιλογέα αρχείων.')
                    return
                activity.unbind(on_activity_result=_activity_result)
                if result_code != Activity.RESULT_OK or data is None:
                    Logger.warning('APP: Activity result not OK or data is None.')
                    self.show_error('Η επιλογή αρχείου απέτυχε ή ακυρώθηκε.')
                    return
                try:
                    uri = data.getData()
                    if uri is None:
                        Logger.warning('APP: SAF picker returned None URI.')
                        self.show_error('Ο επιλογέας επέστρεψε κενή επιλογή (None).')
                        return
                    uri_str = uri.toString()
                    Logger.info(f'APP: SAF selected: {uri_str}')
                    on_selected([uri_str])
                except Exception as e:
                    Logger.warning(f'APP: SAF selection failed: {str(e)}')
                    self.show_error('Σφάλμα κατά την επιλογή αρχείου: ' + str(e))

            activity.bind(on_activity_result=_activity_result)
            current_activity = PythonActivity.mActivity
            current_activity.startActivityForResult(intent, request_code)
        except Exception as e:
            Logger.warning(f'APP: Failed to open SAF picker: {str(e)}')
            self.show_error('Αποτυχία ανοίγματος επιλογέα αρχείων: ' + str(e))

    def use_local_mode(self, db_path):
        if not db_path or str(db_path).strip().lower() in ('none', 'null'):
            self.show_error('Δεν επιλέχθηκε αρχείο βάσης')
            return
        try:
            db_path = self._prepare_local_db_path(db_path)
        except FileNotFoundError:
            self.show_error('Το αρχείο βάσης δεν βρέθηκε')
            return
        except Exception as e:
            self.show_error(f'Αποτυχία ανοίγματος βάσης: {str(e)}')
            return
        self.local_db_path = db_path
        self._set_saved_db_path(db_path)
        self.data_mode = 'local'
        self.change_log_path = None
        self._ensure_change_log_path()
        if hasattr(self, 'mode_label'):
            self.mode_label.text = 'Πηγή: Τοπική Βάση'
        self.show_error(f'Τοπική βάση ενεργή. Change log: {self.change_log_path}')
        self.load_substations(None)

    def _normalize_android_storage_path(self, path_value: str) -> str:
        if not path_value:
            return path_value
        normalized = path_value.strip().replace('\\', '/')
        prefix_map = [
            '/Εσωτερικός χώρος αποθήκευσης',
            '/Internal storage',
        ]
        for prefix in prefix_map:
            if normalized.startswith(prefix):
                normalized = '/storage/emulated/0' + normalized[len(prefix):]
                break
        return normalized

    def _prepare_local_db_path(self, path_value: str) -> str:
        normalized = self._normalize_android_storage_path(path_value)
        if normalized.startswith('content://'):
            return self._copy_content_uri_to_file(normalized)
        if not os.path.exists(normalized):
            raise FileNotFoundError(normalized)
        try:
            conn = sqlite3.connect(f'file:{normalized}?mode=ro', uri=True)
            conn.close()
            return normalized
        except sqlite3.OperationalError as e:
            if 'unable to open database file' not in str(e).lower():
                raise
            try:
                target_dir = getattr(self, 'user_data_dir', None) or os.getcwd()
                os.makedirs(target_dir, exist_ok=True)
                target_path = os.path.join(target_dir, os.path.basename(normalized))
                shutil.copy2(normalized, target_path)
                conn = sqlite3.connect(f'file:{target_path}?mode=ro', uri=True)
                conn.close()
                return target_path
            except Exception as copy_err:
                raise RuntimeError(f'Unable to open database file: {normalized}') from copy_err

    def __init__(self, **kwargs):
        Logger.info('APP: Initializing SubstationAndroidApp')
        try:
            super().__init__(**kwargs)
            self.substations = []
            self.elements = {}
            self.current_substation = None
            self.data_mode = 'local'
            self.local_db_path = None
            self.change_log_path = None
            Logger.info('APP: SubstationAndroidApp initialized successfully')
        except Exception as e:
            Logger.critical(f'APP: Error in __init__: {str(e)}')
            Logger.critical(f'APP: Traceback: {traceback.format_exc()}')
            raise

    def _request_android_permissions(self):
        if platform != 'android':
            Logger.info('APP: Android permissions only required on Android platform')
            return
        try:
            from android.permissions import request_permissions, Permission
            request_permissions([
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
            ])
        except Exception:
            Logger.info('APP: Android permissions not available or not required')
        
    def build(self):
        Logger.info('APP: ========== BUILD METHOD STARTING ==========')
        Logger.info('APP: Building UI')
        try:
            self._request_android_permissions()
            Logger.info('APP: Setting window title')
            self.title = 'DB Substations'
            # Ensure spinner dropdowns are fully opaque
            from kivy.uix.spinner import SpinnerOption
            primary = (0.05, 0.18, 0.36, 1)
            text_on_primary = (1, 1, 1, 1)
            Spinner.background_normal = ''
            Spinner.background_down = ''
            Spinner.background_color = primary
            Spinner.color = text_on_primary
            SpinnerOption.background_normal = ''
            SpinnerOption.background_down = ''
            SpinnerOption.background_color = primary
            SpinnerOption.color = text_on_primary
            Logger.info('APP: Creating main_layout BoxLayout')
            main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
            Logger.info('APP: Main layout created successfully')
            
            # Header
            Logger.info('APP: Creating header Label')
            header = Label(
                text='Υποσταθμοί ΔΕΔΔΗΕ',
                size_hint_y=0.1,
                bold=True
            )
            main_layout.add_widget(header)
            Logger.info('APP: Header added')

            # Data source controls
            mode_layout = BoxLayout(size_hint_y=0.08, spacing=10)
            self.mode_label = Label(text='Πηγή: Τοπική Βάση', size_hint_x=0.6)

            local_btn = Button(text='Τοπική Βάση', size_hint_x=0.4)
            local_btn.bind(on_press=lambda _x: self.open_local_db_picker())

            mode_layout.add_widget(self.mode_label)
            mode_layout.add_widget(local_btn)
            main_layout.add_widget(mode_layout)
            
            # Main content area
            self.content_layout = BoxLayout(orientation='vertical', size_hint_y=0.8)
            main_layout.add_widget(self.content_layout)
            Logger.info('APP: Content layout added')
            
            # Bottom buttons
            button_layout = BoxLayout(size_hint_y=0.1, spacing=10)
            
            refresh_btn = Button(text='Ανανέωση')
            refresh_btn.bind(on_press=self.load_substations)
            button_layout.add_widget(refresh_btn)
            
            add_substation_btn = Button(text='+ Υποσταθμός')
            add_substation_btn.bind(on_press=self.show_add_substation_popup)
            button_layout.add_widget(add_substation_btn)
            
            main_layout.add_widget(button_layout)
            Logger.info('APP: Buttons added')
            
            # Load data after UI is rendered (prevent ANR)
            Logger.info('APP: Scheduling load_substations to run after UI renders')
            if not self._auto_load_saved_db():
                Clock.schedule_once(self.load_substations, 0.5)
            else:
                Clock.schedule_once(self.load_substations, 0.5)
            
            Logger.info('APP: UI build completed successfully')
            return main_layout
            
        except Exception as e:
            Logger.critical(f'APP: Error in build(): {str(e)}')
            Logger.critical(f'APP: Traceback: {traceback.format_exc()}')
            # Return a simple error display instead of crashing
            error_layout = BoxLayout(orientation='vertical', padding=20)
            error_layout.add_widget(Label(text=f'Error: {str(e)}'))
            return error_layout
    
    def load_substations(self, instance):
        """Load substations from local database"""
        Logger.info('APP: ========== LOAD_SUBSTATIONS CALLED ==========')
        Logger.info(f'APP: Instance: {instance}')
        Logger.info(f'APP: Content layout exists: {hasattr(self, "content_layout")}')
        try:
            Logger.info('APP: Clearing content_layout widgets')
            self.content_layout.clear_widgets()
            Logger.info('APP: Creating loading label')
            loading_label = Label(text='Φόρτωση...', size_hint_y=1)
            self.content_layout.add_widget(loading_label)
            Logger.info('APP: Loading label added')

            if not self.local_db_path:
                self.content_layout.clear_widgets()
                self.content_layout.add_widget(Label(text='Επίλεξε αρχείο βάσης για να ξεκινήσεις.'))
                return
            
            try:
                self.substations = self._local_fetch_substations()
                Logger.info(f'APP: Loaded {len(self.substations)} local substations')
                self.root.ids = {}
                self.display_substations()
            except Exception as e:
                Logger.error(f'APP: Local DB error: {str(e)}')
                self.show_error(f'Local DB error: {str(e)}')
            return
            
        except Exception as e:
            Logger.critical(f'APP: Error in load_substations: {str(e)}')
            Logger.critical(f'APP: Traceback: {traceback.format_exc()}')
            self.show_error(f'Error: {str(e)}')
    
    def display_substations(self):
        """Display list of substations"""
        Logger.info('APP: ========== DISPLAY_SUBSTATIONS CALLED ==========')
        Logger.info(f'APP: Number of substations: {len(self.substations)}')
        self.content_layout.clear_widgets()
        Logger.info('APP: Content layout cleared')
        
        if not self.substations:
            Logger.info('APP: No substations found - showing message')
            self.content_layout.add_widget(Label(text='Κανένας υποσταθμός δεν βρέθηκε'))
            return
        
        scroll = ScrollView()
        grid = GridLayout(cols=1, spacing=20, size_hint_y=None, padding=10)
        grid.bind(minimum_height=grid.setter('height'))
        
        for substation in self.substations:
            btn_layout = BoxLayout(size_hint_y=None, height=100, spacing=10, orientation='vertical')
            
            # Top row: Name and View button
            top_row = BoxLayout(size_hint_y=None, height=40, spacing=10)
            name_label = Label(text=substation['name'], size_hint_x=0.7, bold=True)
            top_row.add_widget(name_label)
            
            view_btn = Button(text='Δες', size_hint_x=0.3)
            view_btn.bind(on_press=lambda x, sid=substation['id']: self.show_substation_details(sid))
            top_row.add_widget(view_btn)
            
            btn_layout.add_widget(top_row)
            
            # Bottom row: Location link
            location = substation.get('location', '')
            location_text = 'Google Maps Link' if location else '-'
            location_label = Label(text=f'Τοποθεσία: {location_text}', size_hint_y=None, height=30, font_size='14sp')
            btn_layout.add_widget(location_label)
            
            grid.add_widget(btn_layout)
        
        scroll.add_widget(grid)
        self.content_layout.add_widget(scroll)
    
    def show_substation_details(self, substation_id):
        """Show details of a substation and its elements"""
        self.content_layout.clear_widgets()
        
        # Find substation
        substation = next((s for s in self.substations if s['id'] == substation_id), None)
        if not substation:
            self.show_error('Substation not found')
            return
        
        self.current_substation = substation
        
        main_layout = BoxLayout(orientation='vertical', padding=10, spacing=15)
        
        # Substation header
        header_layout = BoxLayout(orientation='vertical', size_hint_y=0.15, spacing=5)
        name_label = Label(text=substation['name'], bold=True, font_size='18sp', size_hint_y=None, height=30)
        location = substation.get('location', '')
        location_text = 'Google Maps Link' if location else '-'
        location_label = Label(text=f'Τοποθεσία: {location_text}', font_size='14sp', size_hint_y=None, height=25)
        header_layout.add_widget(name_label)
        header_layout.add_widget(location_label)
        main_layout.add_widget(header_layout)
        
        # Load elements for this substation
        scroll = ScrollView()
        grid = GridLayout(cols=1, spacing=15, size_hint_y=None, padding=10)
        grid.bind(minimum_height=grid.setter('height'))
        
        self._load_substation_elements(substation_id, grid)
        
        scroll.add_widget(grid)
        main_layout.add_widget(scroll)
        
        # Action buttons
        button_layout = BoxLayout(size_hint_y=0.15, spacing=10)
        
        maint_btn = Button(text='Συντήρηση')
        maint_btn.bind(on_press=lambda x: self.show_maintenance_menu(substation_id, substation))
        button_layout.add_widget(maint_btn)

        inspect_btn = Button(text='Επιθεώρηση')
        inspect_btn.bind(on_press=lambda x: self.show_inspection_entry_popup(substation_id, substation))
        button_layout.add_widget(inspect_btn)

        add_elem_btn = Button(text='+ Στοιχείο')
        add_elem_btn.bind(on_press=lambda x: self.show_add_element_popup(substation_id))
        button_layout.add_widget(add_elem_btn)
        
        back_btn = Button(text='Πίσω')
        back_btn.bind(on_press=lambda x: self.load_substations(None))
        button_layout.add_widget(back_btn)
        
        main_layout.add_widget(button_layout)
        self.content_layout.clear_widgets()
        self.content_layout.add_widget(main_layout)
    
    def _load_substation_elements(self, substation_id, grid):
        """Load and display elements for a substation"""
        grid.clear_widgets()
        loading_label = Label(text='Φόρτωση στοιχείων...', size_hint_y=None, height=40)
        grid.add_widget(loading_label)

        if self.data_mode == 'local':
            try:
                elements = self._local_fetch_elements(substation_id)
                if loading_label.parent:
                    grid.remove_widget(loading_label)
                if not elements:
                    grid.add_widget(Label(text='Κανένα στοιχείο', size_hint_y=None, height=40))
                    return
                for elem in elements:
                    elem_layout = BoxLayout(size_hint_y=None, spacing=5, orientation='vertical')
                    elem_layout.bind(minimum_height=elem_layout.setter('height'))

                    elem_text = f"{elem['element_type']}: {elem['name']}"
                    elem_text += f"\nS/N: {elem.get('serial_number', '-')} | Τάση: {elem.get('voltage_level', '-')}"
                    model_info = f"Μοντέλο: {elem.get('model', '-')}" if elem.get('model') else ""
                    year_info = f"Έτος: {elem.get('manufacture_year', '-')}" if elem.get('manufacture_year') else ""
                    status = elem.get('operating_status', '-')
                    elem_text += f"\n{model_info} {year_info} | Κατάσταση: {status}"

                    label = Label(text=elem_text, size_hint=(1, None))
                    label.bind(
                        width=lambda instance, value: setattr(instance, 'text_size', (value, None)),
                        texture_size=lambda instance, value: (
                            setattr(instance, 'height', max(75, value[1] + 10)),
                            setattr(elem_layout, 'height', max(75, value[1] + 10))
                        )
                    )
                    elem_layout.add_widget(label)
                    grid.add_widget(elem_layout)
            except Exception as e:
                if loading_label.parent:
                    grid.remove_widget(loading_label)
                grid.add_widget(Label(text=f'Error: {str(e)}', size_hint_y=None, height=40))
            return
    
    def show_add_substation_popup(self, instance):
        """Show popup to add a new substation"""
        popup = Popup(title='Προσθήκη Υποσταθμού', size_hint=(0.95, 0.7))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Name input
        layout.add_widget(Label(text='Όνομα Υποσταθμού:', size_hint_y=0.15))
        name_input = TextInput(hint_text='Όνομα', size_hint_y=0.15, multiline=False)
        layout.add_widget(name_input)
        
        # Location input
        layout.add_widget(Label(text='Τοποθεσία:', size_hint_y=0.15))
        location_input = TextInput(hint_text='Τοποθεσία', size_hint_y=0.15, multiline=False)
        layout.add_widget(location_input)
        
        # Adoption date input
        layout.add_widget(Label(text='Ημερομηνία Υιοθέτησης:', size_hint_y=0.15))
        date_input = TextInput(hint_text='YYYY-MM-DD', size_hint_y=0.15, multiline=False)
        layout.add_widget(date_input)
        
        # Buttons
        button_layout = BoxLayout(size_hint_y=0.2, spacing=10)
        
        def add_substation():
            if not name_input.text.strip():
                self.show_error('Το όνομα είναι υποχρεωτικό')
                return

            try:
                payload = {
                    'name': name_input.text.strip(),
                    'location': location_input.text.strip(),
                    'adoption_date': date_input.text.strip(),
                    'division': 'ΤΜΘ'
                }
                new_id = self._local_insert('substations', payload)
                self._append_change_log('insert', 'substations', {**payload, 'id': new_id})
                popup.dismiss()
                success_popup = Popup(title='Επιτυχία', size_hint=(0.85, 0.45))
                success_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
                success_layout.add_widget(Label(text='Η αλλαγή καταγράφηκε στο change log.'))
                ok_btn = Button(text='OK', size_hint_y=0.3)
                ok_btn.bind(on_press=success_popup.dismiss)
                success_layout.add_widget(ok_btn)
                success_popup.content = success_layout
                success_popup.open()
            except Exception as e:
                self.show_error(f'Local DB error: {str(e)}')
        
        add_btn = Button(text='Προσθήκη')
        add_btn.bind(on_press=lambda x: add_substation())
        button_layout.add_widget(add_btn)
        
        cancel_btn = Button(text='Ακύρωση')
        cancel_btn.bind(on_press=popup.dismiss)
        button_layout.add_widget(cancel_btn)
        
        layout.add_widget(button_layout)
        popup.content = layout
        popup.open()
    
    def show_add_element_popup(self, substation_id):
        """Show popup to add a new element"""
        popup = Popup(title='Προσθήκη Στοιχείου', size_hint=(0.95, 0.9))
        main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Scrollable input area
        scroll = ScrollView()
        layout = BoxLayout(orientation='vertical', size_hint_y=None, padding=5, spacing=8)
        layout.bind(minimum_height=layout.setter('height'))
        
        def wrapped_label(text_value):
            label = Label(text=text_value, size_hint_y=None, halign='left', valign='middle')
            label.bind(
                width=lambda instance, value: setattr(instance, 'text_size', (value, None)),
                texture_size=lambda instance, value: setattr(instance, 'height', value[1] + 10)
            )
            return label

        # Element type
        layout.add_widget(wrapped_label('Τύπος Στοιχείου:'))
        element_spinner = Spinner(
            text=self.ELEMENT_TYPES[0],
            values=self.ELEMENT_TYPES,
            size_hint_y=None,
            height=64
        )
        layout.add_widget(element_spinner)
        
        # Dynamic fields
        field_inputs = {}
        for field in self.ELEMENT_FIELD_DEFS:
            layout.add_widget(wrapped_label(f"{field['label']}:") )
            if field.get('type') == 'spinner':
                spinner = Spinner(
                    text=field['values'][0],
                    values=field['values'],
                    size_hint_y=None,
                    height=64
                )
                field_inputs[field['key']] = spinner
                layout.add_widget(spinner)
            else:
                ti = TextInput(
                    hint_text=field.get('hint', ''),
                    size_hint_y=None,
                    height=68,
                    multiline=False,
                    padding=[14, 14, 14, 14]
                )
                field_inputs[field['key']] = ti
                layout.add_widget(ti)
        
        scroll.add_widget(layout)
        main_layout.add_widget(scroll)
        
        # Buttons
        button_layout = BoxLayout(size_hint_y=0.1, spacing=10)
        
        def add_element():
            if not field_inputs['name'].text.strip():
                self.show_error('Το όνομα είναι υποχρεωτικό')
                return
            
            # Get all field values, handling both text and spinner fields
            def get_field_value(key):
                field = field_inputs.get(key)
                if not field:
                    return ''
                return field.text.strip() if hasattr(field, 'text') else ''
            
            payload = {
                'substation_id': substation_id,
                'element_type': element_spinner.text,
                'name': get_field_value('name'),
                'serial_number': get_field_value('serial_number'),
                'maintenance_date': get_field_value('maintenance_date'),
                'voltage_level': get_field_value('voltage_level'),
                'manufacturer': get_field_value('manufacturer'),
                'type': get_field_value('type'),
                'breaker_category': '',
                'manufacture_year': get_field_value('manufacture_year'),
                'model': get_field_value('model'),
                'model_version': get_field_value('model_version'),
                'operating_status': get_field_value('operating_status'),
                'installation_space': get_field_value('installation_space'),
                'maintenance_cycle': get_field_value('maintenance_cycle'),
                'gate': get_field_value('gate'),
                'is_main_switch': 0,
                'element_model_id': None
            }

            try:
                new_id = self._local_insert('elements', payload)
                self._append_change_log('insert', 'elements', {**payload, 'id': new_id})
                popup.dismiss()
                success_popup = Popup(title='Επιτυχία', size_hint=(0.85, 0.45))
                success_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
                success_layout.add_widget(Label(text='Η αλλαγή καταγράφηκε στο change log.'))
                ok_btn = Button(text='OK', size_hint_y=0.3)
                ok_btn.bind(on_press=success_popup.dismiss)
                success_layout.add_widget(ok_btn)
                success_popup.content = success_layout
                success_popup.open()
            except Exception as e:
                self.show_error(f'Local DB error: {str(e)}')
        
        add_btn = Button(text='Προσθήκη')
        add_btn.bind(on_press=lambda x: add_element())
        button_layout.add_widget(add_btn)
        
        cancel_btn = Button(text='Ακύρωση')
        cancel_btn.bind(on_press=popup.dismiss)
        button_layout.add_widget(cancel_btn)
        
        main_layout.add_widget(button_layout)
        popup.content = main_layout
        popup.open()
    
    def delete_element(self, element_id):
        """Delete an element"""
        confirm_popup = Popup(title='Επιβεβαίωση Διαγραφής', size_hint=(0.7, 0.35))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)

        layout.add_widget(Label(text='Είστε σίγουροι ότι θέλετε να διαγράψετε\nαυτό το στοιχείο;'))

        buttons_layout = BoxLayout(size_hint_y=0.3, spacing=10)

        def do_delete():
            confirm_popup.dismiss()
            try:
                self._append_change_log('delete', 'elements', {'id': element_id})
                success_popup = Popup(title='Επιτυχία', size_hint=(0.85, 0.45))
                success_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
                success_layout.add_widget(Label(text='Η αλλαγή καταγράφηκε στο change log.'))
                ok_btn = Button(text='OK', size_hint_y=0.3)
                ok_btn.bind(on_press=success_popup.dismiss)
                success_layout.add_widget(ok_btn)
                success_popup.content = success_layout
                success_popup.open()
            except Exception as e:
                self.show_error(f'Local DB error: {str(e)}')

        yes_btn = Button(text='Ναι')
        yes_btn.bind(on_press=lambda x: do_delete())
        buttons_layout.add_widget(yes_btn)

        no_btn = Button(text='Όχι')
        no_btn.bind(on_press=confirm_popup.dismiss)
        buttons_layout.add_widget(no_btn)

        layout.add_widget(buttons_layout)
        confirm_popup.content = layout
        confirm_popup.open()
    
    def delete_substation(self, substation_id):
        """Delete a substation"""
        confirm_popup = Popup(title='Επιβεβαίωση Διαγραφής', size_hint=(0.7, 0.35))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)

        layout.add_widget(Label(text='Είστε σίγουροι ότι θέλετε να διαγράψετε\nαυτόν τον υποσταθμό και τα στοιχεία του;'))

        buttons_layout = BoxLayout(size_hint_y=0.3, spacing=10)

        def do_delete():
            confirm_popup.dismiss()
            try:
                self._append_change_log('delete', 'substations', {'id': substation_id})
                success_popup = Popup(title='Επιτυχία', size_hint=(0.85, 0.45))
                success_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
                success_layout.add_widget(Label(text='Η αλλαγή καταγράφηκε στο change log.'))
                ok_btn = Button(text='OK', size_hint_y=0.3)
                ok_btn.bind(on_press=success_popup.dismiss)
                success_layout.add_widget(ok_btn)
                success_popup.content = success_layout
                success_popup.open()
            except Exception as e:
                self.show_error(f'Local DB error: {str(e)}')

        yes_btn = Button(text='Ναι')
        yes_btn.bind(on_press=lambda x: do_delete())
        buttons_layout.add_widget(yes_btn)

        no_btn = Button(text='Όχι')
        no_btn.bind(on_press=confirm_popup.dismiss)
        buttons_layout.add_widget(no_btn)

        layout.add_widget(buttons_layout)
        confirm_popup.content = layout
        confirm_popup.open()
    
    def show_maintenance_menu(self, substation_id, substation):
        """Show maintenance recording interface"""
        from datetime import datetime
        from kivy.uix.checkbox import CheckBox
        from kivy.uix.spinner import Spinner
        
        popup = Popup(title=f'Συντήρηση - {substation["name"]}', size_hint=(0.95, 0.95))
        main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Scrollable content area
        scroll = ScrollView(bar_width=10, size_hint=(1, 0.85))
        content_layout = BoxLayout(orientation='vertical', size_hint_y=None, padding=5, spacing=10)
        content_layout.bind(minimum_height=content_layout.setter('height'))
        
        def wrapped_label(text_value):
            label = Label(text=text_value, size_hint_y=None, halign='left', valign='middle')
            label.bind(
                width=lambda instance, value: setattr(instance, 'text_size', (value, None)),
                texture_size=lambda instance, value: setattr(instance, 'height', value[1] + 10)
            )
            return label

        # Maintenance Type
        content_layout.add_widget(wrapped_label('Τύπος Συντήρησης:'))
        maint_type_spinner = Spinner(
            text='Επαναληπτική συντήρηση',
            values=['Επαναληπτική συντήρηση', 'Βλάβη', 'Οπτικός έλεγχος'],
            size_hint_y=None,
            height=56
        )
        content_layout.add_widget(maint_type_spinner)
        
        # Date/Time
        content_layout.add_widget(wrapped_label('Ημερομηνία & Ώρα:'))
        datetime_input = TextInput(
            text=datetime.now().strftime('%Y-%m-%d %H:%M'),
            hint_text='YYYY-MM-DD HH:MM',
            size_hint_y=None,
            height=60,
            multiline=False,
            padding=[12, 12, 12, 12]
        )
        content_layout.add_widget(datetime_input)
        
        # Overall comments
        content_layout.add_widget(wrapped_label('Γενικά Σχόλια:'))
        overall_comments = TextInput(
            hint_text='Γενικά σχόλια για την συντήρηση...',
            size_hint_y=None,
            height=120,
            multiline=True,
            padding=[12, 12, 12, 12]
        )
        content_layout.add_widget(overall_comments)
        
        # Elements section
        content_layout.add_widget(Label(text='Στοιχεία που συντηρήθηκαν:', size_hint_y=None, height=40, bold=True))
        loading_label = Label(text='Φόρτωση στοιχείων...', size_hint_y=None, height=40)
        content_layout.add_widget(loading_label)
        retry_btn = Button(text='Επανάληψη φόρτωσης', size_hint_y=None, height=40, disabled=True, opacity=0)
        content_layout.add_widget(retry_btn)
        
        # Store element widgets
        element_widgets = {}
        
        def load_elements():
            """Load elements and create checkboxes with fields"""
            retry_btn.disabled = True
            retry_btn.opacity = 0
            if loading_label.parent is None:
                content_layout.add_widget(loading_label)

            if self.data_mode == 'local':
                try:
                    elements = self._local_fetch_elements(substation_id)
                    if loading_label.parent:
                        content_layout.remove_widget(loading_label)
                    if not elements:
                        content_layout.add_widget(Label(text='Κανένα στοιχείο', size_hint_y=None, height=40))
                        return
                    for elem in elements:
                        # Element container
                        elem_box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5, padding=5)
                        elem_box.bind(minimum_height=elem_box.setter('height'))

                        elem_type_display = elem['element_type']
                        if elem.get('breaker_category'):
                            elem_type_display += f" ({elem['breaker_category']})"

                        elem_text = f"{elem['name']} - {elem_type_display}\n"
                        elem_text += f"S/N: {elem.get('serial_number', '-')}"

                        mfr = elem.get('manufacturer', '-')
                        mdl = elem.get('model', '-')
                        if mfr != '-' or mdl != '-':
                            elem_text += f"\nΚατ.: {mfr} | Μοντ.: {mdl}"

                        checkbox_layout = BoxLayout(size_hint_y=None, spacing=10, padding=[0, 4, 0, 4])
                        checkbox_layout.bind(minimum_height=checkbox_layout.setter('height'))
                        checkbox = CheckBox(size_hint=(None, None), size=(44, 44))
                        checkbox_layout.add_widget(checkbox)

                        elem_label = Label(
                            text=elem_text,
                            size_hint_x=1,
                            size_hint_y=None,
                            halign='left',
                            valign='top'
                        )
                        elem_label.bind(
                            width=lambda instance, value: setattr(instance, 'text_size', (value, None)),
                            texture_size=lambda instance, value: setattr(instance, 'height', max(80, value[1] + 16))
                        )
                        checkbox_layout.add_widget(elem_label)
                        elem_box.add_widget(checkbox_layout)

                        details_container = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
                        details_container.bind(minimum_height=details_container.setter('height'))

                        elem_comments = TextInput(
                            hint_text='Σχόλια για αυτό το στοιχείο...',
                            size_hint_y=None,
                            height=56,
                            multiline=False,
                            padding=[12, 12, 12, 12]
                        )
                        details_container.add_widget(elem_comments)

                        measurements = {}
                        is_breaker = elem['element_type'] in ['Διακόπτης ΥΤ', 'Διακόπτης ΜΤ']

                        if is_breaker:
                            details_container.add_widget(wrapped_label('Μονώσεις (Κλειστό):'))
                            for phase in ['fa', 'fb', 'fc']:
                                phase_label = {'fa': 'Φάση A', 'fb': 'Φάση B', 'fc': 'Φάση C'}[phase]
                                phase_layout = BoxLayout(size_hint_y=None, height=60, spacing=8)
                                phase_layout.add_widget(Label(text=f'{phase_label}:', size_hint_x=0.25))
                                value_input = TextInput(hint_text='Τιμή', size_hint_x=0.5, multiline=False, height=50, padding=[10, 10, 10, 10])
                                phase_layout.add_widget(value_input)
                                unit_spinner = Spinner(text='GΩ', values=['GΩ', 'MΩ', 'kΩ'], size_hint_x=0.25)
                                phase_layout.add_widget(unit_spinner)
                                details_container.add_widget(phase_layout)
                                measurements[f'ins_closed_{phase}'] = value_input
                                measurements[f'ins_closed_{phase}_unit'] = unit_spinner

                            details_container.add_widget(wrapped_label('Μονώσεις (Ανοιχτό):'))
                            for phase in ['fa', 'fb', 'fc']:
                                phase_label = {'fa': 'Φάση A-A', 'fb': 'Φάση B-B', 'fc': 'Φάση C-C'}[phase]
                                phase_layout = BoxLayout(size_hint_y=None, height=60, spacing=8)
                                phase_layout.add_widget(Label(text=f'{phase_label}:', size_hint_x=0.25))
                                value_input = TextInput(hint_text='Τιμή', size_hint_x=0.5, multiline=False, height=50, padding=[10, 10, 10, 10])
                                phase_layout.add_widget(value_input)
                                unit_spinner = Spinner(text='GΩ', values=['GΩ', 'MΩ', 'kΩ'], size_hint_x=0.25)
                                phase_layout.add_widget(unit_spinner)
                                details_container.add_widget(phase_layout)
                                measurements[f'ins_open_{phase}'] = value_input
                                measurements[f'ins_open_{phase}_unit'] = unit_spinner

                            details_container.add_widget(wrapped_label('Αντίσταση Επαφών (μΩ):'))
                            for phase in ['fa', 'fb', 'fc']:
                                phase_label = {'fa': 'Φάση A', 'fb': 'Φάση B', 'fc': 'Φάση C'}[phase]
                                phase_layout = BoxLayout(size_hint_y=None, height=60, spacing=8)
                                phase_layout.add_widget(Label(text=f'{phase_label}:', size_hint_x=0.3))
                                value_input = TextInput(hint_text='Τιμή μΩ', size_hint_x=0.7, multiline=False, height=50, padding=[10, 10, 10, 10])
                                phase_layout.add_widget(value_input)
                                details_container.add_widget(phase_layout)
                                measurements[f'cont_{phase}'] = value_input

                        def toggle_details(cb, value, eb=elem_box, dc=details_container):
                            if value:
                                if dc not in eb.children:
                                    eb.add_widget(dc)
                            else:
                                if dc in eb.children:
                                    eb.remove_widget(dc)

                        checkbox.bind(active=toggle_details)
                        content_layout.add_widget(elem_box)

                        element_widgets[elem['id']] = {
                            'checkbox': checkbox,
                            'comments': elem_comments,
                            'measurements': measurements,
                            'elem_type': elem['element_type']
                        }
                except Exception as e:
                    if loading_label.parent:
                        content_layout.remove_widget(loading_label)
                    retry_btn.disabled = False
                    retry_btn.opacity = 1
                    self.show_error(f'Error loading elements: {str(e)}')
                return

        retry_btn.bind(on_press=lambda _x: load_elements())
        
        Clock.schedule_once(lambda *_args: load_elements(), 0)
        
        scroll.add_widget(content_layout)
        main_layout.add_widget(scroll)
        
        # Buttons
        button_layout = BoxLayout(size_hint_y=0.15, spacing=10)
        
        def save_maintenance():
            # Validate
            selected_elements = [(eid, widgets) for eid, widgets in element_widgets.items() 
                                if widgets['checkbox'].active]
            
            if not selected_elements:
                self.show_error('Πρέπει να επιλέξετε τουλάχιστον ένα στοιχείο!')
                return
            
            if not datetime_input.text.strip():
                self.show_error('Η ημερομηνία είναι υποχρεωτική!')
                return
            
            # Prepare payload
            maintenance_elements = []
            for elem_id, widgets in selected_elements:
                elem_data = {
                    'element_id': elem_id,
                    'element_comments': widgets['comments'].text.strip()
                }
                
                # Add measurements if available
                measurements = widgets['measurements']
                if measurements:
                    for key, widget in measurements.items():
                        if hasattr(widget, 'text'):
                            try:
                                elem_data[key] = float(widget.text) if widget.text.strip() else None
                            except ValueError:
                                elem_data[key] = None
                        else:  # Spinner
                            elem_data[key] = widget.text
                
                maintenance_elements.append(elem_data)
            
            payload = {
                'substation_id': substation_id,
                'date_time': datetime_input.text.strip(),
                'overall_comments': overall_comments.text.strip(),
                'maintenance_type': maint_type_spinner.text,
                'elements': maintenance_elements
            }

            try:
                maintenance_id = self._local_insert('maintenance', payload)
                self._append_change_log('insert', 'maintenance', {
                    'id': maintenance_id,
                    **payload
                })
                popup.dismiss()
                success_popup = Popup(title='Επιτυχία', size_hint=(0.8, 0.4))
                success_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
                success_layout.add_widget(Label(text='Η συντήρηση καταχωρήθηκε!'))
                ok_btn = Button(text='OK', size_hint_y=0.3)
                ok_btn.bind(on_press=success_popup.dismiss)
                success_layout.add_widget(ok_btn)
                success_popup.content = success_layout
                success_popup.open()
            except Exception as e:
                self.show_error(f'Local DB error: {str(e)}')
        
        save_btn = Button(text='Αποθήκευση')
        save_btn.bind(on_press=lambda x: save_maintenance())
        button_layout.add_widget(save_btn)
        
        cancel_btn = Button(text='Ακύρωση')
        cancel_btn.bind(on_press=popup.dismiss)
        button_layout.add_widget(cancel_btn)
        
        main_layout.add_widget(button_layout)
        popup.content = main_layout
        popup.open()

    def show_inspection_entry_popup(self, substation_id, substation):
        """Add a new inspection entry"""
        from datetime import datetime

        popup = Popup(title=f'Νέα Επιθεώρηση - {substation["name"]}', size_hint=(0.95, 0.85))
        main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)

        scroll = ScrollView(bar_width=10, size_hint=(1, 0.8))
        layout = BoxLayout(orientation='vertical', size_hint_y=None, padding=5, spacing=10)
        layout.bind(minimum_height=layout.setter('height'))

        def wrapped_label(text_value, bold=False):
            label = Label(text=text_value, size_hint_y=None, halign='left', valign='middle', bold=bold, markup=bold)
            label.bind(
                width=lambda instance, value: setattr(instance, 'text_size', (value, None)),
                texture_size=lambda instance, value: setattr(instance, 'height', value[1] + 10)
            )
            return label

        layout.add_widget(wrapped_label('Ημερομηνία Επιθεώρησης:'))
        date_input = TextInput(
            text=datetime.now().strftime('%Y-%m-%d'),
            hint_text='YYYY-MM-DD',
            size_hint_y=None,
            height=68,
            multiline=False,
            padding=[14, 14, 14, 14]
        )
        layout.add_widget(date_input)

        field_inputs = []
        for field in self.INSPECTION_FIELDS:
            if isinstance(field, dict) and field.get('type') == 'section':
                layout.add_widget(wrapped_label(f"[b]{field.get('title')}[/b]", bold=True))
                continue

            row = BoxLayout(size_hint_y=None, spacing=8)
            row.bind(minimum_height=row.setter('height'))

            label = Label(text=str(field), size_hint_x=0.62, size_hint_y=None, halign='left', valign='top')
            label.bind(
                width=lambda instance, value: setattr(instance, 'text_size', (value, None)),
                texture_size=lambda instance, value: (
                    setattr(instance, 'height', value[1] + 10),
                    setattr(row, 'height', max(value[1] + 10, 100))
                )
            )

            ti = TextInput(
                hint_text='Παρατηρήσεις',
                size_hint_x=0.38,
                size_hint_y=None,
                height=90,
                multiline=True,
                padding=[12, 12, 12, 12]
            )
            ti.bind(height=lambda _instance, _value: setattr(row, 'height', max(row.height, ti.height)))

            row.add_widget(label)
            row.add_widget(ti)
            layout.add_widget(row)
            field_inputs.append((str(field), ti))

        scroll.add_widget(layout)
        main_layout.add_widget(scroll)

        button_layout = BoxLayout(size_hint_y=None, height=60, spacing=10)

        def save_inspection():
            if not date_input.text.strip():
                self.show_error('Η ημερομηνία είναι υποχρεωτική!')
                return

            fields_payload = [{'label': label, 'value': ti.text.strip()} for label, ti in field_inputs]
            payload = {
                'substation_id': substation_id,
                'inspection_date': date_input.text.strip(),
                'data_json': json.dumps({'fields': fields_payload}, ensure_ascii=False),
                'substation_name': substation.get('name'),
                'month_key': date_input.text.strip()[:7],
                'source_file': 'android-local',
                'created_at': datetime.now().strftime('%Y-%m-%d')
            }

            try:
                inspection_id = self._local_insert('inspections', payload)
                self._append_change_log('insert', 'inspections', {**payload, 'id': inspection_id})
                popup.dismiss()
                success_popup = Popup(title='Επιτυχία', size_hint=(0.8, 0.4))
                success_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
                success_layout.add_widget(Label(text='Η επιθεώρηση καταχωρήθηκε!'))
                ok_btn = Button(text='OK', size_hint_y=0.3)
                ok_btn.bind(on_press=success_popup.dismiss)
                success_layout.add_widget(ok_btn)
                success_popup.content = success_layout
                success_popup.open()
            except Exception as e:
                self.show_error(f'Local DB error: {str(e)}')

        save_btn = Button(text='Αποθήκευση')
        save_btn.bind(on_press=lambda x: save_inspection())
        button_layout.add_widget(save_btn)

        cancel_btn = Button(text='Ακύρωση')
        cancel_btn.bind(on_press=popup.dismiss)
        button_layout.add_widget(cancel_btn)

        main_layout.add_widget(button_layout)
        popup.content = main_layout
        popup.open()

    def show_error(self, message):
        """Show error popup"""
        popup = Popup(title='Σφάλμα', size_hint=(0.9, 0.7))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        scroll = ScrollView(size_hint=(1, 1))
        msg_label = Label(text=message, size_hint_y=None, halign='left', valign='top')
        msg_label.bind(
            width=lambda instance, value: setattr(instance, 'text_size', (value, None)),
            texture_size=lambda instance, value: setattr(instance, 'height', value[1] + 10)
        )
        scroll.add_widget(msg_label)
        layout.add_widget(scroll)
        
        close_btn = Button(text='Κλείσιμο', size_hint_y=0.3)
        close_btn.bind(on_press=popup.dismiss)
        layout.add_widget(close_btn)
        
        popup.content = layout
        popup.open()

if __name__ == '__main__':
    Logger.info('APP: ========== Running main ==========')
    try:
        app = SubstationAndroidApp()
        Logger.info('APP: App instance created')
        app.run()
        Logger.info('APP: App run completed')
    except Exception as e:
        Logger.critical(f'APP: FATAL ERROR in main: {str(e)}')
        Logger.critical(f'APP: Traceback: {traceback.format_exc()}')
        raise
