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
        {'key': 'bar', 'label': 'Ζυγός', 'type': 'text', 'hint': 'π.χ. ΖΥΓΟΣ 1'},
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
        
        add_elem_btn = Button(text='+ Στοιχείο')
        add_elem_btn.bind(on_press=lambda x: self.show_add_element_popup(substation_id))
        button_layout.add_widget(add_elem_btn)
        
        delete_sub_btn = Button(text='Διαγραφή')
        delete_sub_btn.bind(on_press=lambda x: self.delete_substation(substation_id))
        button_layout.add_widget(delete_sub_btn)
        
        back_btn = Button(text='Πίσω')
        back_btn.bind(on_press=lambda x: self.load_substations(None))
        button_layout.add_widget(back_btn)
        
        main_layout.add_widget(button_layout)
        self.content_layout.clear_widgets()
        self.content_layout.add_widget(main_layout)
    
    def _load_substation_elements(self, substation_id, grid):
        """Load and display elements for a substation"""
        def on_success(req, result):
            try:
                data = self.parse_json_response(result)
                if data.get('success'):
                    elements = data.get('data', [])
                    if not elements:
                        grid.add_widget(Label(text='Κανένα στοιχείο', size_hint_y=None, height=40))
                    else:
                        for elem in elements:
                            elem_layout = BoxLayout(size_hint_y=None, height=120, spacing=5, orientation='vertical')
                            
                            # Line 1: Type and Name
                            elem_text = f"{elem['element_type']}: {elem['name']}"
                            # Line 2: S/N, Voltage, Manufacturer
                            elem_text += f"\nS/N: {elem.get('serial_number', '-')} | Τάση: {elem.get('voltage_level', '-')}"
                            # Line 3: Model, Year, Status
                            model_info = f"Μοντέλο: {elem.get('model', '-')}" if elem.get('model') else ""
                            year_info = f"Έτος: {elem.get('manufacture_year', '-')}" if elem.get('manufacture_year') else ""
                            status = elem.get('operating_status', '-')
                            elem_text += f"\n{model_info} {year_info} | Κατάσταση: {status}"
                            
                            label = Label(text=elem_text, size_hint_y=None, height=75)
                            elem_layout.add_widget(label)
                            
                            # Delete button
                            del_btn = Button(text='X', size_hint_y=None, height=40)
                            del_btn.bind(on_press=lambda x, eid=elem['id']: self.delete_element(eid))
                            elem_layout.add_widget(del_btn)
                            
                            grid.add_widget(elem_layout)
            except Exception as e:
                grid.add_widget(Label(text=f'Error: {str(e)}', size_hint_y=None, height=40))
        
        def on_error(req, error):
            grid.add_widget(Label(text=f'Error loading elements: {str(error)}', size_hint_y=None, height=40))
        
        UrlRequest(
            f'{self.API_BASE_URL}/elements?substation_id={substation_id}',
            on_success=on_success,
            on_error=on_error
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
        
        # Element type
        layout.add_widget(Label(text='Τύπος Στοιχείου:', size_hint_y=None, height=30))
        element_spinner = Spinner(
            text=self.ELEMENT_TYPES[0],
            values=self.ELEMENT_TYPES,
            size_hint_y=None,
            height=40
        )
        layout.add_widget(element_spinner)
        
        # Dynamic fields
        field_inputs = {}
        for field in self.ELEMENT_FIELD_DEFS:
            layout.add_widget(Label(text=f"{field['label']}:", size_hint_y=None, height=30))
            if field.get('type') == 'spinner':
                spinner = Spinner(
                    text=field['values'][0],
                    values=field['values'],
                    size_hint_y=None,
                    height=40
                )
                field_inputs[field['key']] = spinner
                layout.add_widget(spinner)
            else:
                ti = TextInput(
                    hint_text=field.get('hint', ''),
                    size_hint_y=None,
                    height=40,
                    multiline=False
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
                'bar': get_field_value('bar'),
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
    
    def delete_substation(self, substation_id):
        """Delete a substation"""
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
