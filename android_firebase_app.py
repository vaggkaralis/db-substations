"""
Firebase-based Android Kivy App for DB Substations
Works with mobile data - no WiFi required
"""
import kivy
kivy.require('2.0.0')
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
import json
import threading
from datetime import datetime
import uuid

# Firebase imports
try:
    import firebase_admin
    from firebase_admin import db, credentials, auth
    FIREBASE_AVAILABLE = True
except ImportError:
    FIREBASE_AVAILABLE = False

class SubstationFirebaseApp(App):
    # Element field definitions (same as other versions)
    ELEMENT_TYPES = ['Διακόπτης Ισχύος', 'Μετασχηματιστής', 'Motor Drive']
    VOLTAGE_LEVELS = ['20 KV', '150 KV', '20/150 KV']
    ELEMENT_FIELD_DEFS = [
        {'key': 'name', 'label': 'Όνομα Στοιχείου', 'type': 'text', 'hint': 'Όνομα Στοιχείου'},
        {'key': 'serial_number', 'label': 'Σειριακός Αριθμός', 'type': 'text', 'hint': 'Σειριακός Αριθμός'},
        {'key': 'maintenance_date', 'label': 'Ημερομηνία τελευταίας συντήρησης', 'type': 'text', 'hint': 'YYYY-MM-DD'},
        {'key': 'voltage_level', 'label': 'Επίπεδο Τάσης', 'type': 'spinner', 'values': VOLTAGE_LEVELS},
        {'key': 'manufacturer', 'label': 'Κατασκευαστής', 'type': 'text', 'hint': 'Κατασκευαστής'},
        {'key': 'type', 'label': 'Τύπος', 'type': 'text', 'hint': 'Τύπος'},
    ]
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.substations = {}
        self.elements = {}
        self.current_substation_id = None
        self.firebase_ref = None
        self.user_id = str(uuid.uuid4())[:8]  # Anonymous user ID
        
    def build(self):
        self.title = 'DB Substations'
        
        if not FIREBASE_AVAILABLE:
            return self._build_error_screen()
        
        self._init_firebase()
        
        main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Header
        header = Label(
            text='Υποσταθμοί ΔΕΔΔΗΕ',
            size_hint_y=0.1,
            bold=True
        )
        main_layout.add_widget(header)
        
        # Main content area
        self.content_layout = BoxLayout(orientation='vertical', size_hint_y=0.8)
        main_layout.add_widget(self.content_layout)
        
        # Bottom buttons
        button_layout = BoxLayout(size_hint_y=0.1, spacing=10)
        
        refresh_btn = Button(text='Ανανέωση')
        refresh_btn.bind(on_press=self.load_substations)
        button_layout.add_widget(refresh_btn)
        
        add_substation_btn = Button(text='+ Υποσταθμός')
        add_substation_btn.bind(on_press=self.show_add_substation_popup)
        button_layout.add_widget(add_substation_btn)
        
        main_layout.add_widget(button_layout)
        
        # Load data on startup
        Clock.schedule_once(lambda dt: self.load_substations(None), 0.5)
        
        return main_layout
    
    def _build_error_screen(self):
        """Show error if Firebase not available"""
        layout = BoxLayout(orientation='vertical', padding=20, spacing=20)
        layout.add_widget(Label(text='Firebase SDK not installed!\n\nInstall with:\npip install firebase-admin'))
        close_btn = Button(text='Exit', size_hint_y=0.2)
        close_btn.bind(on_press=self.stop)
        layout.add_widget(close_btn)
        return layout
    
    def _init_firebase(self):
        """Initialize Firebase (uses anonymous authentication)"""
        try:
            if not firebase_admin._apps:
                # Initialize with your Firebase config
                # Download from Firebase Console > Project Settings > Service Account
                cred = credentials.Certificate('firebase-credentials.json')
                firebase_admin.initialize_app(
                    cred,
                    {
                        'databaseURL': 'https://YOUR_PROJECT.firebaseio.com'
                    }
                )
            
            self.firebase_ref = db.reference('/')
            
            # Optional: Sign in anonymously for better security
            # This requires enabling anonymous auth in Firebase Console
            
        except Exception as e:
            self.show_error(f'Firebase init error: {str(e)}')
    
    def load_substations(self, instance):
        """Load substations from Firebase"""
        self.content_layout.clear_widgets()
        loading_label = Label(text='Φόρτωση...', size_hint_y=1)
        self.content_layout.add_widget(loading_label)
        
        def fetch_data():
            try:
                data = self.firebase_ref.child('substations').get()
                if data.val():
                    self.substations = data.val() if isinstance(data.val(), dict) else {}
                else:
                    self.substations = {}
                
                Clock.schedule_once(lambda dt: self.display_substations(), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self.show_error(f'Error: {str(e)}'), 0)
        
        # Non-blocking fetch
        thread = threading.Thread(target=fetch_data, daemon=True)
        thread.start()
    
    def display_substations(self):
        """Display list of substations"""
        self.content_layout.clear_widgets()
        
        if not self.substations:
            self.content_layout.add_widget(Label(text='Κανένας υποσταθμός δεν βρέθηκε'))
            return
        
        scroll = ScrollView()
        grid = GridLayout(cols=1, spacing=10, size_hint_y=None, padding=10)
        grid.bind(minimum_height=grid.setter('height'))
        
        for sub_id, substation in self.substations.items():
            btn_layout = BoxLayout(size_hint_y=None, height=60, spacing=10)
            
            # Substation info
            info_text = f"{substation.get('name', 'N/A')}\nΤοποθεσία: {substation.get('location', '-')}"
            info_label = Label(text=info_text, size_hint_x=0.7)
            btn_layout.add_widget(info_label)
            
            # View button
            view_btn = Button(text='Δες', size_hint_x=0.3)
            view_btn.bind(on_press=lambda x, sid=sub_id: self.show_substation_details(sid))
            btn_layout.add_widget(view_btn)
            
            grid.add_widget(btn_layout)
        
        scroll.add_widget(grid)
        self.content_layout.add_widget(scroll)
    
    def show_substation_details(self, substation_id):
        """Show details of a substation and its elements"""
        self.current_substation_id = substation_id
        substation = self.substations.get(substation_id, {})
        
        main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Substation header
        header = Label(
            text=f"{substation.get('name', 'N/A')}\nΤοποθεσία: {substation.get('location', '-')}",
            size_hint_y=0.15,
            bold=True
        )
        main_layout.add_widget(header)
        
        # Elements scroll area
        scroll = ScrollView()
        grid = GridLayout(cols=1, spacing=10, size_hint_y=None, padding=10)
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
        def fetch_elements():
            try:
                elem_ref = self.firebase_ref.child('elements')
                data = elem_ref.get()
                elements = []
                
                if data.val():
                    for elem_id, elem_data in data.val().items():
                        if elem_data.get('substation_id') == substation_id:
                            elem_copy = elem_data.copy()
                            elem_copy['id'] = elem_id
                            elements.append(elem_copy)
                
                Clock.schedule_once(lambda dt: self._display_elements(grid, elements, substation_id), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: grid.add_widget(Label(text=f'Error: {str(e)}', size_hint_y=None, height=40)), 0)
        
        thread = threading.Thread(target=fetch_elements, daemon=True)
        thread.start()
    
    def _display_elements(self, grid, elements, substation_id):
        """Display elements in grid"""
        if not elements:
            grid.add_widget(Label(text='Κανένα στοιχείο', size_hint_y=None, height=40))
            return
        
        for elem in elements:
            elem_layout = BoxLayout(size_hint_y=None, height=70, spacing=5, orientation='vertical')
            
            elem_text = f"{elem.get('element_type', 'N/A')}: {elem.get('name', 'N/A')}\nS/N: {elem.get('serial_number', '-')} | Voltage: {elem.get('voltage_level', '-')}"
            label = Label(text=elem_text)
            elem_layout.add_widget(label)
            
            # Delete button
            del_btn = Button(text='X', size_hint_y=None, height=30)
            del_btn.bind(on_press=lambda x, eid=elem['id']: self.delete_element(eid))
            elem_layout.add_widget(del_btn)
            
            grid.add_widget(elem_layout)
    
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
            
            def save_data():
                try:
                    sub_id = str(uuid.uuid4())
                    self.firebase_ref.child('substations').child(sub_id).set({
                        'name': name_input.text.strip(),
                        'location': location_input.text.strip(),
                        'adoption_date': date_input.text.strip(),
                        'created_at': datetime.now().isoformat()
                    })
                    Clock.schedule_once(lambda dt: popup.dismiss(), 0)
                    Clock.schedule_once(lambda dt: self.load_substations(None), 0.2)
                except Exception as e:
                    Clock.schedule_once(lambda dt: self.show_error(f'Error: {str(e)}'), 0)
            
            thread = threading.Thread(target=save_data, daemon=True)
            thread.start()
        
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
            
            def save_element():
                try:
                    elem_id = str(uuid.uuid4())
                    self.firebase_ref.child('elements').child(elem_id).set({
                        'substation_id': substation_id,
                        'element_type': element_spinner.text,
                        'name': field_inputs['name'].text.strip(),
                        'serial_number': field_inputs['serial_number'].text.strip(),
                        'maintenance_date': field_inputs['maintenance_date'].text.strip(),
                        'voltage_level': field_inputs['voltage_level'].text,
                        'manufacturer': field_inputs['manufacturer'].text.strip(),
                        'type': field_inputs['type'].text.strip(),
                        'created_at': datetime.now().isoformat()
                    })
                    Clock.schedule_once(lambda dt: popup.dismiss(), 0)
                    Clock.schedule_once(lambda dt: self.show_substation_details(substation_id), 0.2)
                except Exception as e:
                    Clock.schedule_once(lambda dt: self.show_error(f'Error: {str(e)}'), 0)
            
            thread = threading.Thread(target=save_element, daemon=True)
            thread.start()
        
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
        def delete_data():
            try:
                self.firebase_ref.child('elements').child(element_id).delete()
                Clock.schedule_once(lambda dt: self.show_substation_details(self.current_substation_id), 0.2)
            except Exception as e:
                Clock.schedule_once(lambda dt: self.show_error(f'Error: {str(e)}'), 0)
        
        thread = threading.Thread(target=delete_data, daemon=True)
        thread.start()
    
    def delete_substation(self, substation_id):
        """Delete a substation and all its elements"""
        def delete_data():
            try:
                # Delete all elements for this substation
                elem_ref = self.firebase_ref.child('elements')
                data = elem_ref.get()
                if data.val():
                    for elem_id, elem_data in data.val().items():
                        if elem_data.get('substation_id') == substation_id:
                            elem_ref.child(elem_id).delete()
                
                # Delete substation
                self.firebase_ref.child('substations').child(substation_id).delete()
                Clock.schedule_once(lambda dt: self.load_substations(None), 0.2)
            except Exception as e:
                Clock.schedule_once(lambda dt: self.show_error(f'Error: {str(e)}'), 0)
        
        thread = threading.Thread(target=delete_data, daemon=True)
        thread.start()
    
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
    SubstationFirebaseApp().run()
