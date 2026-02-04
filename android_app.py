"""
Android Kivy App for DB Substations - connects to Flask API backend
"""
import sys
import traceback

# Set up logging FIRST before any other imports
from kivy.logger import Logger
Logger.info('APP: ========== Starting DB Substations App ==========')
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
    Logger.info('APP: Kivy UI imports successful')
    
    from kivy.network.urlrequest import UrlRequest
    Logger.info('APP: UrlRequest import successful')
    
    import json
    Logger.info('APP: JSON import successful')
    
    import threading
    Logger.info('APP: Threading import successful')
    
    # Test SSL/HTTPS dependencies
    try:
        import ssl
        Logger.info(f'APP: SSL module available: {ssl.OPENSSL_VERSION}')
    except Exception as e:
        Logger.warning(f'APP: SSL module issue: {str(e)}')
    
    try:
        import certifi
        Logger.info(f'APP: Certifi available at: {certifi.where()}')
    except Exception as e:
        Logger.warning(f'APP: Certifi issue: {str(e)}')
        
    try:
        import urllib3
        Logger.info(f'APP: urllib3 version: {urllib3.__version__}')
    except Exception as e:
        Logger.warning(f'APP: urllib3 issue: {str(e)}')
    
    Logger.info('APP: All imports completed successfully')
    
except Exception as e:
    Logger.critical(f'APP: FATAL - Import error: {str(e)}')
    Logger.critical(f'APP: Traceback: {traceback.format_exc()}')
    raise

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
    
    API_BASE_URL = 'https://db-substations.onrender.com/api'  # Render Cloud API URL
    
    @staticmethod
    def parse_json_response(result):
        """Helper to parse JSON response - handles both string and already-parsed dict"""
        if isinstance(result, (dict, list)):
            # Already parsed
            return result
        elif isinstance(result, bytes):
            # Decode bytes to string first
            return json.loads(result.decode('utf-8'))
        elif isinstance(result, str):
            # Parse string
            return json.loads(result)
        else:
            raise ValueError(f"Unexpected result type: {type(result)}")
    
    def __init__(self, **kwargs):
        Logger.info('APP: Initializing SubstationAndroidApp')
        try:
            super().__init__(**kwargs)
            self.substations = []
            self.elements = {}
            self.current_substation = None
            Logger.info('APP: SubstationAndroidApp initialized successfully')
        except Exception as e:
            Logger.critical(f'APP: Error in __init__: {str(e)}')
            Logger.critical(f'APP: Traceback: {traceback.format_exc()}')
            raise
        
    def build(self):
        Logger.info('APP: ========== BUILD METHOD STARTING ==========')
        Logger.info('APP: Building UI')
        try:
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
        """Load substations from API"""
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
            
            def on_success(req, result):
                Logger.info(f'APP: API success, result type: {type(result)}')
                try:
                    data = self.parse_json_response(result)
                    Logger.info(f'APP: Parsed JSON: {data}')
                    if data.get('success'):
                        self.substations = data.get('data', [])
                        Logger.info(f'APP: Loaded {len(self.substations)} substations')
                        self.root.ids = {}  # Clear any cached IDs
                        self.display_substations()
                    else:
                        error_msg = data.get('error', 'Unknown error')
                        Logger.error(f'APP: API returned error: {error_msg}')
                        self.show_error(error_msg)
                except Exception as e:
                    Logger.error(f'APP: Parse error: {str(e)}')
                    Logger.error(f'APP: Traceback: {traceback.format_exc()}')
                    self.show_error(f'Parse error: {str(e)}')
            
            def on_error(req, error):
                Logger.error(f'APP: Connection error: {str(error)}')
                Logger.error(f'APP: Request: {req}')
                self.show_error(f'Connection error: {str(error)}')
            
            # Non-blocking request
            url = f'{self.API_BASE_URL}/substations'
            Logger.info(f'APP: Making request to: {url}')
            UrlRequest(
                url,
                on_success=on_success,
                on_error=on_error,
                timeout=60  # Increased for Render.com cold start
            )
            Logger.info('APP: UrlRequest initiated')
            
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

        def on_success(req, result):
            try:
                data = self.parse_json_response(result)
                if data.get('success'):
                    if loading_label.parent:
                        grid.remove_widget(loading_label)
                    elements = data.get('data', [])
                    if not elements:
                        grid.add_widget(Label(text='Κανένα στοιχείο', size_hint_y=None, height=40))
                    else:
                        for elem in elements:
                            elem_layout = BoxLayout(size_hint_y=None, spacing=5, orientation='vertical')
                            elem_layout.bind(minimum_height=elem_layout.setter('height'))
                            
                            # Line 1: Type and Name
                            elem_text = f"{elem['element_type']}: {elem['name']}"
                            # Line 2: S/N, Voltage, Manufacturer
                            elem_text += f"\nS/N: {elem.get('serial_number', '-')} | Τάση: {elem.get('voltage_level', '-')}"
                            # Line 3: Model, Year, Status
                            model_info = f"Μοντέλο: {elem.get('model', '-')}" if elem.get('model') else ""
                            year_info = f"Έτος: {elem.get('manufacture_year', '-')}" if elem.get('manufacture_year') else ""
                            status = elem.get('operating_status', '-')
                            elem_text += f"\n{model_info} {year_info} | Κατάσταση: {status}"
                            
                            label = Label(text=elem_text, size_hint=(1, None))
                            # Enable text wrapping and automatic height calculation
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

        def fallback_load_all():
            def on_success_all(_req, result):
                try:
                    data = self.parse_json_response(result)
                    if data.get('success'):
                        all_elements = data.get('data', [])
                        filtered = [e for e in all_elements if e.get('substation_id') == substation_id]
                        if loading_label.parent:
                            grid.remove_widget(loading_label)
                        if not filtered:
                            grid.add_widget(Label(text='Κανένα στοιχείο', size_hint_y=None, height=40))
                        else:
                            for elem in filtered:
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
                    else:
                        if loading_label.parent:
                            grid.remove_widget(loading_label)
                        grid.add_widget(Label(text='Αποτυχία φόρτωσης στοιχείων', size_hint_y=None, height=60))
                except Exception as e:
                    if loading_label.parent:
                        grid.remove_widget(loading_label)
                    grid.add_widget(Label(text=f'Error: {str(e)}', size_hint_y=None, height=60))

            def on_error_all(_req, _error):
                if loading_label.parent:
                    grid.remove_widget(loading_label)
                grid.add_widget(Label(text='Αποτυχία φόρτωσης στοιχείων', size_hint_y=None, height=60))

            UrlRequest(
                f'{self.API_BASE_URL}/elements',
                on_success=on_success_all,
                on_error=on_error_all,
                timeout=60,
                req_headers={'Cache-Control': 'no-cache'}
            )
        
        def on_error(req, error):
            if loading_label.parent:
                grid.remove_widget(loading_label)
            status = getattr(req, 'resp_status', None)
            grid.add_widget(Label(text=f'Error loading elements: {str(error)}' + (f' (HTTP {status})' if status else ''), size_hint_y=None, height=60))
            fallback_load_all()

        def on_failure(req, result):
            if loading_label.parent:
                grid.remove_widget(loading_label)
            status = getattr(req, 'resp_status', None)
            grid.add_widget(Label(text='Αποτυχία φόρτωσης στοιχείων' + (f' (HTTP {status})' if status else ''), size_hint_y=None, height=60))
            fallback_load_all()
        
        UrlRequest(
            f'{self.API_BASE_URL}/elements?substation_id={substation_id}',
            on_success=on_success,
            on_error=on_error,
            on_failure=on_failure,
            timeout=60,
            req_headers={'Cache-Control': 'no-cache'}
        )
    
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
            
            def on_success(req, result):
                try:
                    data = self.parse_json_response(result)
                    if data.get('success'):
                        popup.dismiss()
                        self.load_substations(None)
                    else:
                        self.show_error(data.get('error', 'Unknown error'))
                except Exception as e:
                    self.show_error(f'Error: {str(e)}')
            
            def on_error(req, error):
                self.show_error(f'Error: {str(error)}')
            
            payload = {
                'name': name_input.text.strip(),
                'location': location_input.text.strip(),
                'adoption_date': date_input.text.strip()
            }
            
            UrlRequest(
                f'{self.API_BASE_URL}/substations',
                req_body=json.dumps(payload),
                req_headers={'Content-Type': 'application/json'},
                on_success=on_success,
                on_error=on_error,
                method='POST'
            )
        
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
            
            def on_success(req, result):
                try:
                    data = self.parse_json_response(result)
                    if data.get('success'):
                        popup.dismiss()
                        self.show_substation_details(substation_id)
                    else:
                        self.show_error(data.get('error', 'Unknown error'))
                except Exception as e:
                    self.show_error(f'Error: {str(e)}')
            
            def on_error(req, error):
                self.show_error(f'Error: {str(error)}')
            
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
                'breaker_category': '',  # Will be set from model selection later
                'manufacture_year': get_field_value('manufacture_year'),
                'model': get_field_value('model'),
                'model_version': get_field_value('model_version'),
                'operating_status': get_field_value('operating_status'),
                'installation_space': get_field_value('installation_space'),
                'maintenance_cycle': get_field_value('maintenance_cycle'),
                'gate': get_field_value('gate'),
                'is_main_switch': 0,  # Default to Line breaker
                'element_model_id': None  # Will be added later with model selection
            }
            
            UrlRequest(
                f'{self.API_BASE_URL}/elements',
                req_body=json.dumps(payload),
                req_headers={'Content-Type': 'application/json'},
                on_success=on_success,
                on_error=on_error,
                method='POST'
            )
        
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

            def on_success(req, result):
                try:
                    data = self.parse_json_response(result)
                    if data.get('success'):
                        self.show_substation_details(self.current_substation['id'])
                    else:
                        self.show_error(data.get('error', 'Unknown error'))
                except Exception as e:
                    self.show_error(f'Error: {str(e)}')

            def on_error(req, error):
                self.show_error(f'Error: {str(error)}')

            UrlRequest(
                f'{self.API_BASE_URL}/elements/{element_id}',
                on_success=on_success,
                on_error=on_error,
                method='DELETE'
            )

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

            def on_success(req, result):
                try:
                    data = self.parse_json_response(result)
                    if data.get('success'):
                        self.load_substations(None)
                    else:
                        self.show_error(data.get('error', 'Unknown error'))
                except Exception as e:
                    self.show_error(f'Error: {str(e)}')

            def on_error(req, error):
                self.show_error(f'Error: {str(error)}')

            UrlRequest(
                f'{self.API_BASE_URL}/substations/{substation_id}',
                on_success=on_success,
                on_error=on_error,
                method='DELETE'
            )

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

            def fallback_load_all():
                def on_success_all(_req, result):
                    try:
                        data = self.parse_json_response(result)
                        if data.get('success'):
                            all_elements = data.get('data', [])
                            filtered = [e for e in all_elements if e.get('substation_id') == substation_id]
                            if loading_label.parent:
                                content_layout.remove_widget(loading_label)
                            if not filtered:
                                content_layout.add_widget(Label(text='Κανένα στοιχείο', size_hint_y=None, height=40))
                            else:
                                for elem in filtered:
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
                        else:
                            if loading_label.parent:
                                content_layout.remove_widget(loading_label)
                            retry_btn.disabled = False
                            retry_btn.opacity = 1
                            self.show_error('Αποτυχία φόρτωσης στοιχείων')
                    except Exception as e:
                        if loading_label.parent:
                            content_layout.remove_widget(loading_label)
                        retry_btn.disabled = False
                        retry_btn.opacity = 1
                        self.show_error(f'Error loading elements: {str(e)}')

                def on_error_all(_req, _error):
                    if loading_label.parent:
                        content_layout.remove_widget(loading_label)
                    retry_btn.disabled = False
                    retry_btn.opacity = 1
                    self.show_error('Αποτυχία φόρτωσης στοιχείων')

                UrlRequest(
                    f'{self.API_BASE_URL}/elements',
                    on_success=on_success_all,
                    on_error=on_error_all,
                    timeout=60,
                    req_headers={'Cache-Control': 'no-cache'}
                )

            def on_success(req, result):
                try:
                    data = self.parse_json_response(result)
                    if data.get('success'):
                        if loading_label.parent:
                            content_layout.remove_widget(loading_label)
                        elements = data.get('data', [])
                        if not elements:
                            content_layout.add_widget(Label(text='Κανένα στοιχείο', size_hint_y=None, height=40))
                        else:
                            for elem in elements:
                                # Element container
                                elem_box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5, padding=5)
                                elem_box.bind(minimum_height=elem_box.setter('height'))
                                
                                # Build element display text
                                elem_type_display = elem['element_type']
                                if elem.get('breaker_category'):
                                    elem_type_display += f" ({elem['breaker_category']})"
                                
                                elem_text = f"{elem['name']} - {elem_type_display}\n"
                                elem_text += f"S/N: {elem.get('serial_number', '-')}"
                                
                                # Add manufacturer and model
                                mfr = elem.get('manufacturer', '-')
                                mdl = elem.get('model', '-')
                                if mfr != '-' or mdl != '-':
                                    elem_text += f"\nΚατ.: {mfr} | Μοντ.: {mdl}"
                                
                                # Checkbox and name
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
                                
                                # Container for details (initially hidden)
                                details_container = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
                                details_container.bind(minimum_height=details_container.setter('height'))
                                
                                # Comments
                                elem_comments = TextInput(
                                    hint_text='Σχόλια για αυτό το στοιχείο...',
                                    size_hint_y=None,
                                    height=56,
                                    multiline=False,
                                    padding=[12, 12, 12, 12]
                                )
                                details_container.add_widget(elem_comments)
                                
                                # Measurement fields for circuit breakers
                                measurements = {}
                                is_breaker = elem['element_type'] in ['Διακόπτης ΥΤ', 'Διακόπτης ΜΤ']
                                
                                if is_breaker:
                                    # Insulation measurements (closed position)
                                    details_container.add_widget(wrapped_label('Μονώσεις (Κλειστό):'))
                                    
                                    for phase in ['fa', 'fb', 'fc']:
                                        phase_label = {'fa': 'Φάση A', 'fb': 'Φάση B', 'fc': 'Φάση C'}[phase]
                                        phase_layout = BoxLayout(size_hint_y=None, height=60, spacing=8)
                                        phase_layout.add_widget(Label(text=f'{phase_label}:', size_hint_x=0.25))
                                        
                                        value_input = TextInput(hint_text='Τιμή', size_hint_x=0.5, multiline=False, height=50, padding=[10, 10, 10, 10])
                                        phase_layout.add_widget(value_input)
                                        
                                        unit_spinner = Spinner(
                                            text='GΩ',
                                            values=['GΩ', 'MΩ', 'kΩ'],
                                            size_hint_x=0.25,
                                            height=50
                                        )
                                        phase_layout.add_widget(unit_spinner)
                                        details_container.add_widget(phase_layout)
                                        
                                        measurements[f'ins_closed_{phase}'] = value_input
                                        measurements[f'ins_closed_{phase}_unit'] = unit_spinner
                                    
                                    # Insulation measurements (open position)
                                    details_container.add_widget(wrapped_label('Μονώσεις (Ανοιχτό):'))
                                    
                                    for phase in ['fa', 'fb', 'fc']:
                                        phase_label = {'fa': 'Φάση A-A', 'fb': 'Φάση B-B', 'fc': 'Φάση C-C'}[phase]
                                        phase_layout = BoxLayout(size_hint_y=None, height=60, spacing=8)
                                        phase_layout.add_widget(Label(text=f'{phase_label}:', size_hint_x=0.25))
                                        
                                        value_input = TextInput(hint_text='Τιμή', size_hint_x=0.5, multiline=False, height=50, padding=[10, 10, 10, 10])
                                        phase_layout.add_widget(value_input)
                                        
                                        unit_spinner = Spinner(
                                            text='GΩ',
                                            values=['GΩ', 'MΩ', 'kΩ'],
                                            size_hint_x=0.25,
                                            height=50
                                        )
                                        phase_layout.add_widget(unit_spinner)
                                        details_container.add_widget(phase_layout)
                                        
                                        measurements[f'ins_open_{phase}'] = value_input
                                        measurements[f'ins_open_{phase}_unit'] = unit_spinner
                                    
                                    # Contact resistance
                                    details_container.add_widget(wrapped_label('Αντίσταση Επαφών (μΩ):'))
                                    
                                    for phase in ['fa', 'fb', 'fc']:
                                        phase_label = {'fa': 'Φάση A', 'fb': 'Φάση B', 'fc': 'Φάση C'}[phase]
                                        phase_layout = BoxLayout(size_hint_y=None, height=60, spacing=8)
                                        phase_layout.add_widget(Label(text=f'{phase_label}:', size_hint_x=0.3))
                                        
                                        value_input = TextInput(hint_text='Τιμή μΩ', size_hint_x=0.7, multiline=False, height=50, padding=[10, 10, 10, 10])
                                        phase_layout.add_widget(value_input)
                                        details_container.add_widget(phase_layout)
                                        
                                        measurements[f'cont_{phase}'] = value_input
                                
                                # Toggle details visibility
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
            
            def on_error(req, error):
                if loading_label.parent:
                    content_layout.remove_widget(loading_label)
                retry_btn.disabled = False
                retry_btn.opacity = 1
                status = getattr(req, 'resp_status', None)
                self.show_error(f'Error: {str(error)}' + (f' (HTTP {status})' if status else ''))
                fallback_load_all()

            def on_failure(req, result):
                if loading_label.parent:
                    content_layout.remove_widget(loading_label)
                retry_btn.disabled = False
                retry_btn.opacity = 1
                status = getattr(req, 'resp_status', None)
                self.show_error('Αποτυχία φόρτωσης στοιχείων' + (f' (HTTP {status})' if status else ''))
                fallback_load_all()
            
            UrlRequest(
                f'{self.API_BASE_URL}/elements?substation_id={substation_id}',
                on_success=on_success,
                on_error=on_error,
                on_failure=on_failure,
                timeout=60,
                req_headers={'Cache-Control': 'no-cache'}
            )

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
            
            def on_success(req, result):
                try:
                    data = self.parse_json_response(result)
                    if data.get('success'):
                        popup.dismiss()
                        # Show success message
                        success_popup = Popup(title='Επιτυχία', size_hint=(0.8, 0.4))
                        success_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
                        success_layout.add_widget(Label(text='Η συντήρηση καταχωρήθηκε!'))
                        ok_btn = Button(text='OK', size_hint_y=0.3)
                        ok_btn.bind(on_press=success_popup.dismiss)
                        success_layout.add_widget(ok_btn)
                        success_popup.content = success_layout
                        success_popup.open()
                    else:
                        self.show_error(data.get('error', 'Unknown error'))
                except Exception as e:
                    self.show_error(f'Error: {str(e)}')
            
            def on_error(req, error):
                self.show_error(f'Error saving maintenance: {str(error)}')
            
            import json
            UrlRequest(
                f'{self.API_BASE_URL}/maintenance',
                on_success=on_success,
                on_error=on_error,
                method='POST',
                req_headers={'Content-Type': 'application/json'},
                req_body=json.dumps(payload),
                timeout=60
            )
        
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
                'data_json': json.dumps({'fields': fields_payload}, ensure_ascii=False)
            }

            def on_success(req, result):
                try:
                    data = self.parse_json_response(result)
                    if data.get('success'):
                        popup.dismiss()
                        success_popup = Popup(title='Επιτυχία', size_hint=(0.8, 0.4))
                        success_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
                        success_layout.add_widget(Label(text='Η επιθεώρηση καταχωρήθηκε!'))
                        ok_btn = Button(text='OK', size_hint_y=0.3)
                        ok_btn.bind(on_press=success_popup.dismiss)
                        success_layout.add_widget(ok_btn)
                        success_popup.content = success_layout
                        success_popup.open()
                    else:
                        self.show_error(data.get('error', 'Unknown error'))
                except Exception as e:
                    self.show_error(f'Error: {str(e)}')

            def on_error(req, error):
                self.show_error(f'Error saving inspection: {str(error)}')

            UrlRequest(
                f'{self.API_BASE_URL}/inspections',
                on_success=on_success,
                on_error=on_error,
                method='POST',
                req_headers={'Content-Type': 'application/json'},
                req_body=json.dumps(payload),
                timeout=60
            )

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
        popup = Popup(title='Σφάλμα', size_hint=(0.8, 0.4))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        layout.add_widget(Label(text=message))
        
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
