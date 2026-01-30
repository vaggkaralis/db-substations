import kivy
kivy.require('2.0.0')
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.checkbox import CheckBox
from kivy.uix.filechooser import FileChooserListView
from kivy.core.window import Window
import webbrowser
import os
from datetime import datetime
import requests
import json

# Maximize window on startup
Window.maximize()

from database import init_db
from importers import (
    import_elements_from_csv,
    import_elements_from_excel,
    import_substations_from_csv,
    import_substations_from_excel,
)
from popups import show_message_popup
from templates import create_elements_template, create_substations_template
from model_management import show_models_management

class CloudSync:
    """Helper class to sync TEST substation changes to Render.com"""
    API_BASE_URL = 'https://db-substations.onrender.com/api'
    TEST_SUBSTATION_NAME = 'TEST'
    
    @classmethod
    def get_test_substation_id(cls, conn):
        """Get the local ID of TEST substation"""
        c = conn.cursor()
        c.execute("SELECT id FROM substations WHERE name=?", (cls.TEST_SUBSTATION_NAME,))
        result = c.fetchone()
        return result[0] if result else None
    
    @classmethod
    def sync_element_add(cls, conn, element_id, substation_id):
        """Sync newly added element to cloud if it's in TEST substation"""
        test_id = cls.get_test_substation_id(conn)
        if test_id is None or substation_id != test_id:
            return  # Not TEST substation, skip sync
        
        # Get element data
        c = conn.cursor()
        c.execute("""
            SELECT element_type, name, serial_number, maintenance_date, manufacturer, 
                   model, model_version, installation_space, operating_status, 
                   maintenance_cycle, manufacture_year, bar, is_main_switch, 
                   breaker_category, voltage_level
            FROM elements WHERE id=?
        """, (element_id,))
        elem = c.fetchone()
        if not elem:
            return
        
        # Prepare payload
        payload = {
            'substation_id': 1,  # Cloud TEST substation ID
            'element_type': elem[0],
            'name': elem[1],
            'serial_number': elem[2] or '',
            'maintenance_date': elem[3] or '',
            'manufacturer': elem[4] or '',
            'model': elem[5] or '',
            'model_version': elem[6] or '',
            'installation_space': elem[7] or 'Εσωτερικός',
            'operating_status': elem[8] or 'Ενεργή',
            'maintenance_cycle': elem[9] or 0,
            'manufacture_year': elem[10] or '',
            'bar': elem[11] or '',
            'is_main_switch': elem[12] or 0,
            'breaker_category': elem[13] or '',
            'voltage_level': elem[14] or ''
        }
        
        try:
            response = requests.post(
                f'{cls.API_BASE_URL}/elements',
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            if response.status_code == 201:
                print(f"✓ Synced new element '{elem[1]}' to cloud")
            else:
                print(f"✗ Failed to sync element: {response.text}")
        except Exception as e:
            print(f"✗ Sync error: {str(e)}")
    
    @classmethod
    def sync_element_update(cls, conn, element_id, substation_id):
        """Sync element updates to cloud if it's in TEST substation"""
        test_id = cls.get_test_substation_id(conn)
        if test_id is None or substation_id != test_id:
            return
        
        # Get element data
        c = conn.cursor()
        c.execute("""
            SELECT name, element_type, serial_number, maintenance_date, manufacturer,
                   model, model_version, installation_space, operating_status,
                   maintenance_cycle, manufacture_year, bar, is_main_switch,
                   breaker_category, voltage_level
            FROM elements WHERE id=?
        """, (element_id,))
        elem = c.fetchone()
        if not elem:
            return
        
        # Find cloud element by name (since IDs differ)
        try:
            # Get cloud element ID by name
            response = requests.get(
                f'{cls.API_BASE_URL}/elements?substation_id=1',
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    cloud_elements = data.get('data', [])
                    cloud_elem = next((e for e in cloud_elements if e['name'] == elem[0]), None)
                    
                    if cloud_elem:
                        # Update existing element
                        cloud_id = cloud_elem['id']
                        payload = {
                            'element_type': elem[1],
                            'name': elem[0],
                            'serial_number': elem[2] or '',
                            'maintenance_date': elem[3] or '',
                            'manufacturer': elem[4] or '',
                            'model': elem[5] or '',
                            'model_version': elem[6] or '',
                            'installation_space': elem[7] or 'Εσωτερικός',
                            'operating_status': elem[8] or 'Ενεργή',
                            'maintenance_cycle': elem[9] or 0,
                            'manufacture_year': elem[10] or '',
                            'bar': elem[11] or '',
                            'is_main_switch': elem[12] or 0,
                            'breaker_category': elem[13] or '',
                            'voltage_level': elem[14] or ''
                        }
                        
                        update_response = requests.put(
                            f'{cls.API_BASE_URL}/elements/{cloud_id}',
                            json=payload,
                            headers={'Content-Type': 'application/json'},
                            timeout=30
                        )
                        if update_response.status_code == 200:
                            print(f"✓ Synced updated element '{elem[0]}' to cloud")
                        else:
                            print(f"✗ Failed to sync element update: {update_response.text}")
        except Exception as e:
            print(f"✗ Sync error: {str(e)}")
    
    @classmethod
    def sync_element_delete(cls, conn, element_name, substation_id):
        """Sync element deletion to cloud if it's in TEST substation"""
        test_id = cls.get_test_substation_id(conn)
        if test_id is None or substation_id != test_id:
            return
        
        try:
            # Get cloud element ID by name
            response = requests.get(
                f'{cls.API_BASE_URL}/elements?substation_id=1',
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    cloud_elements = data.get('data', [])
                    cloud_elem = next((e for e in cloud_elements if e['name'] == element_name), None)
                    
                    if cloud_elem:
                        cloud_id = cloud_elem['id']
                        delete_response = requests.delete(
                            f'{cls.API_BASE_URL}/elements/{cloud_id}',
                            timeout=30
                        )
                        if delete_response.status_code == 200:
                            print(f"✓ Synced deleted element '{element_name}' to cloud")
                        else:
                            print(f"✗ Failed to sync element deletion: {delete_response.text}")
        except Exception as e:
            print(f"✗ Sync error: {str(e)}")

class SubstationApp(App):
    # Define element types as a class variable
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
    BREAKER_CATEGORIES = ['Πτωχού Ελαίου', 'SF6', 'Κενού']
    BREAKER_TYPES = ['Κεντρικός', 'Γραμμής', 'Διασυνδετικός', 'Διακόπτης Πυκνωτών']  # Main, Line, Interconnection, or Capacitor breaker
    OPERATING_STATUS = ['Ενεργή', 'Ανενεργή']
    INSTALLATION_SPACE = ['Εσωτερικός', 'Εξωτερικός']
    # Central definition of element fields for easy future extension
    ELEMENT_FIELD_DEFS = [
        {'key': 'name', 'label': 'Όνομα Στοιχείου', 'type': 'text', 'hint': 'Όνομα Στοιχείου'},
        {'key': 'serial_number', 'label': 'Σειριακός Αριθμός', 'type': 'text', 'hint': 'Σειριακός Αριθμός'},
        {'key': 'manufacture_year', 'label': 'Έτος κατασκευής', 'type': 'text', 'hint': 'YYYY'},
        {'key': 'maintenance_date', 'label': 'Τελευταία Συντ.', 'type': 'text', 'hint': 'YYYY-MM-DD'},
        {'key': 'manufacturer', 'label': 'Κατασκευαστής', 'type': 'text', 'hint': 'Κατασκευαστής'},
        {'key': 'model', 'label': 'Μοντέλο', 'type': 'text', 'hint': 'Μοντέλο'},
        {'key': 'model_version', 'label': 'Έκδοση Μοντέλου', 'type': 'text', 'hint': 'Έκδοση'},
        {'key': 'installation_space', 'label': 'Χώρος Εγκατ.', 'type': 'spinner', 'values': INSTALLATION_SPACE},
        {'key': 'operating_status', 'label': 'Λειτ. Κατάσταση', 'type': 'spinner', 'values': OPERATING_STATUS},
        {'key': 'maintenance_cycle', 'label': 'Κύκλος Συντ.', 'type': 'text', 'hint': 'Αριθμός'},
    ]
    
    def build(self):
        self.title = 'Υποσταθμοί ΔΕΔΔΗΕ ΔΕΕΔ/ΚΣΜΘ/ΤΕΙ'
        layout = BoxLayout(orientation='vertical')
        self.show_btn = Button(text='Εμφάνιση βάσης υποσταθμών')
        self.show_btn.bind(on_press=self.show_records)
        self.import_btn = Button(text='Εισαγωγή υποσταθμών και στοιχείων από αρχείο')
        self.import_btn.bind(on_press=self.show_import_menu)
        self.maintenance_btn = Button(text='Καταχώρηση Συντήρησης')
        self.maintenance_btn.bind(on_press=self.show_maintenance_menu)
        self.models_btn = Button(text='Διαχείριση Τύπων Στοιχείων')
        self.models_btn.bind(on_press=self.show_models_management)
        self.delete_btn = Button(text='Διαγραφή όλων (ΠΡΟΣΟΧΗ!)', color=(1, 0, 0, 1))
        self.delete_btn.bind(on_press=self.delete_all)
        layout.add_widget(self.show_btn)
        layout.add_widget(self.import_btn)
        layout.add_widget(self.maintenance_btn)
        layout.add_widget(self.models_btn)
        layout.add_widget(self.delete_btn)
        self.conn = init_db()
        return layout
    
    def get_available_bars(self, substation_id, is_interconnection=False):
        """Get available bars (ΖΥΓΟΣ) based on existing transformers in the substation
        
        Args:
            substation_id: The ID of the substation
            is_interconnection: If True, returns interconnection bars (1-2, 2-3, etc.)
                               If False, returns regular bars (1, 2, 3, etc.)
        """
        c = self.conn.cursor()
        # Get all transformers for this substation, ordered by name
        c.execute("""SELECT name FROM elements 
                    WHERE substation_id=? AND element_type='Μετασχηματιστής 150/20KV' 
                    ORDER BY name""", (substation_id,))
        transformers = c.fetchall()
        
        num_bars = len(transformers)
        
        if is_interconnection:
            # Generate interconnection bars: ΖΥΓΟΣ 1-2, ΖΥΓΟΣ 2-3, etc.
            bars = [f"ΖΥΓΟΣ {i}-{i+1}" for i in range(1, num_bars)]
        else:
            # Generate regular bars: ΖΥΓΟΣ 1, ΖΥΓΟΣ 2, etc.
            bars = [f"ΖΥΓΟΣ {i+1}" for i in range(num_bars)]
        
        # Always include option for unassigned
        return ['(Μη καταχωρημένο)'] + bars

    def show_import_menu(self, instance):
        # Show menu for importing elements (substations will be auto-created)
        menu_popup = Popup(title='Εισαγωγή στοιχείων από αρχείο', size_hint=(0.6, 0.45))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        layout.add_widget(Label(text='Εισάγετε στοιχεία από αρχείο Excel.\nΝέοι υποσταθμοί θα δημιουργηθούν αυτόματα.', size_hint_y=0.2))
        
        # Import elements button
        import_elements_btn = Button(text='Εισαγωγή Στοιχείων από Αρχείο', size_hint_y=0.3)
        import_elements_btn.bind(on_press=lambda x: self._show_import_elements_from_menu(menu_popup))
        layout.add_widget(import_elements_btn)
        
        # Separator
        layout.add_widget(Label(text='Ή δημιουργήστε πρότυπο εισαγωγής:', size_hint_y=0.15))
        
        # Template button
        template_elements_btn = Button(text='Δημιουργία Template Εισαγωγής', size_hint_y=0.3)
        template_elements_btn.bind(on_press=self.create_elements_template)
        layout.add_widget(template_elements_btn)
        
        # Cancel button
        cancel_btn = Button(text='Ακύρωση', size_hint_y=0.2)
        cancel_btn.bind(on_press=menu_popup.dismiss)
        layout.add_widget(cancel_btn)
        
        menu_popup.content = layout
        menu_popup.open()
    
    def _show_import_substations_from_menu(self, menu_popup):
        menu_popup.dismiss()
        self.show_import_substations_dialog(None)
    
    def _show_import_elements_from_menu(self, menu_popup):
        menu_popup.dismiss()
        self.show_import_elements_dialog(None)

    def show_add_menu(self, instance):
        # Show intermediate menu for adding substation or element
        menu_popup = Popup(title='Προσθήκη υποσταθμών και στοιχείων', size_hint=(0.6, 0.4))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        layout.add_widget(Label(text='Επιλέξτε τι θέλετε να προσθέσετε:', size_hint_y=0.3))
        
        # Add substation button
        add_substation_btn = Button(text='Προσθήκη Νέου Υποσταθμού', size_hint_y=0.3)
        add_substation_btn.bind(on_press=lambda x: self._show_add_substation_from_menu(menu_popup))
        layout.add_widget(add_substation_btn)
        
        # Add element button
        add_element_btn = Button(text='Προσθήκη Νέου Στοιχείου', size_hint_y=0.3)
        add_element_btn.bind(on_press=lambda x: self._show_add_element_from_menu(menu_popup))
        layout.add_widget(add_element_btn)
        
        # Cancel button
        cancel_btn = Button(text='Ακύρωση', size_hint_y=0.2)
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
        popup = Popup(title='Προσθήκη Νέου Υποσταθμού', size_hint=(0.8, 0.5))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Name input
        name_input = TextInput(
            hint_text='Όνομα Υποσταθμού',
            size_hint_y=0.25,
            multiline=False
        )
        layout.add_widget(Label(text='Όνομα Υποσταθμού:', size_hint_y=0.15))
        layout.add_widget(name_input)
        
        # Division spinner
        division_spinner = Spinner(
            text='ΤΜΘ',
            values=['ΤΜΘ'],
            size_hint_y=0.25
        )
        layout.add_widget(Label(text='Τομέας:', size_hint_y=0.15))
        layout.add_widget(division_spinner)
        
        # Buttons layout
        buttons_layout = BoxLayout(size_hint_y=0.3, spacing=10)
        
        def add_substation():
            if not name_input.text:
                show_message_popup('Σφάλμα', 'Παρακαλώ εισάγετε όνομα υποσταθμού!')
                return
            
            c = self.conn.cursor()
            c.execute("INSERT INTO substations (name, location, adoption_date, division) VALUES (?, ?, ?, ?)", 
                     (name_input.text, '', '', division_spinner.text))
            self.conn.commit()
            popup.dismiss()
            show_message_popup('Επιτυχία', 'Υποσταθμός προστέθηκε!', callback=lambda: self.show_records(None))
        
        add_btn = Button(text='Προσθήκη')
        add_btn.bind(on_press=lambda x: add_substation())
        buttons_layout.add_widget(add_btn)
        
        cancel_btn = Button(text='Ακύρωση')
        cancel_btn.bind(on_press=popup.dismiss)
        buttons_layout.add_widget(cancel_btn)
        
        layout.add_widget(buttons_layout)
        popup.content = layout
        popup.open()
    
    def show_add_substation_popup_from_db_view(self, parent_popup):
        """Add substation from within the database view, and refresh the view after"""
        # Create popup
        popup = Popup(title='Προσθήκη Νέου Υποσταθμού', size_hint=(0.8, 0.5))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Name input
        name_input = TextInput(
            hint_text='Όνομα Υποσταθμού',
            size_hint_y=0.25,
            multiline=False
        )
        layout.add_widget(Label(text='Όνομα Υποσταθμού:', size_hint_y=0.15))
        layout.add_widget(name_input)
        
        # Division spinner
        division_spinner = Spinner(
            text='ΤΜΘ',
            values=['ΤΜΘ'],
            size_hint_y=0.25
        )
        layout.add_widget(Label(text='Τομέας:', size_hint_y=0.15))
        layout.add_widget(division_spinner)
        
        # Buttons layout
        buttons_layout = BoxLayout(size_hint_y=0.3, spacing=10)
        
        def add_substation():
            if not name_input.text:
                show_message_popup('Σφάλμα', 'Παρακαλώ εισάγετε όνομα υποσταθμού!')
                return
            
            c = self.conn.cursor()
            c.execute("INSERT INTO substations (name, location, adoption_date, division) VALUES (?, ?, ?, ?)", 
                     (name_input.text, '', '', division_spinner.text))
            self.conn.commit()
            popup.dismiss()
            parent_popup.dismiss()
            show_message_popup('Επιτυχία', 'Υποσταθμός προστέθηκε!', callback=lambda: self.show_records(None))
        
        add_btn = Button(text='Προσθήκη')
        add_btn.bind(on_press=lambda x: add_substation())
        buttons_layout.add_widget(add_btn)
        
        cancel_btn = Button(text='Ακύρωση')
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
            show_message_popup('Σφάλμα', 'Δεν υπάρχουν υποσταθμοί στη βάση!')
            return
        
        # Create selection popup
        selection_popup = Popup(title='Επιλογή Προβολής', size_hint=(0.6, 0.4))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        layout.add_widget(Label(text='Επιλέξτε τι θέλετε να δείτε:', size_hint_y=0.3))
        
        # "Show All" button
        show_all_btn = Button(text='Εμφάνιση Όλων των Υποσταθμών', size_hint_y=0.35)
        show_all_btn.bind(on_press=lambda x: self._show_all_substations(selection_popup))
        layout.add_widget(show_all_btn)
        
        # "Select Specific Substation" button
        select_specific_btn = Button(text='Επιλογή Υποσταθμού', size_hint_y=0.35)
        select_specific_btn.bind(on_press=lambda x: self._show_substation_selection_window(selection_popup, all_substations))
        layout.add_widget(select_specific_btn)
        
        # Cancel button
        cancel_btn = Button(text='Ακύρωση', size_hint_y=0.2)
        cancel_btn.bind(on_press=selection_popup.dismiss)
        layout.add_widget(cancel_btn)
        
        selection_popup.content = layout
        selection_popup.open()
    
    def _show_substation_selection_window(self, parent_popup, all_substations):
        """Show a scrollable window with a 5x14 matrix of substation buttons"""
        parent_popup.dismiss()
        
        # Create selection popup
        selection_popup = Popup(title='Επιλογή Υποσταθμού', size_hint=(0.9, 0.85))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Create scrollable area
        scroll = ScrollView(bar_width=10, scroll_type=['bars', 'content'])
        grid = GridLayout(cols=5, spacing=5, size_hint_y=None, padding=10)
        grid.bind(minimum_height=grid.setter('height'))
        
        # Create 5x14 matrix (70 positions total)
        total_positions = 70
        
        # Add buttons for registered substations and empty boxes for remaining positions
        for i in range(total_positions):
            if i < len(all_substations):
                sub_id, sub_name = all_substations[i]
                sub_btn = Button(
                    text=sub_name,
                    size_hint_y=None,
                    height=50
                )
                sub_btn.bind(on_press=lambda x, name=sub_name, popup=selection_popup: self._show_specific_substation_from_window(name, popup))
                grid.add_widget(sub_btn)
            else:
                # Empty box for unregistered positions
                empty_btn = Button(
                    text='',
                    size_hint_y=None,
                    height=50,
                    disabled=True,
                    background_color=(0.3, 0.3, 0.3, 0.5)
                )
                grid.add_widget(empty_btn)
        
        scroll.add_widget(grid)
        layout.add_widget(scroll)
        
        # Cancel button
        cancel_btn = Button(text='Ακύρωση', size_hint_y=0.08)
        cancel_btn.bind(on_press=selection_popup.dismiss)
        layout.add_widget(cancel_btn)
        
        selection_popup.content = layout
        selection_popup.open()
    
    def _show_all_substations(self, selection_popup):
        selection_popup.dismiss()
        self._display_substations(None)
    
    def _show_specific_substation_from_window(self, substation_name, selection_popup):
        selection_popup.dismiss()
        self._display_substations(substation_name)
    
    def _display_substations(self, filter_name=None):
        c = self.conn.cursor()
        if filter_name:
            c.execute("SELECT id, name, location, adoption_date, division FROM substations WHERE name=?", (filter_name,))
            title = f'Υποσταθμός: {filter_name}'
        else:
            c.execute("SELECT id, name, location, adoption_date, division FROM substations ORDER BY name")
            title = 'Εγγραφές Υποσταθμών'
        
        substations = c.fetchall()
        
        # Create popup window
        popup = Popup(title=title, size_hint=(0.95, 0.9))
        
        # Create main layout
        main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Create scrollable grid for records
        scroll = ScrollView(bar_width=10, scroll_type=['bars', 'content'])
        grid = GridLayout(cols=1, spacing=5, size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))
        
        if substations:
            for sub_id, sub_name, location, adoption_date, division in substations:
                # Substation title in bigger letters
                substation_title = Label(
                    text=f'[b][size=22]{sub_name}[/size][/b]',
                    size_hint_y=None,
                    height=45,
                    markup=True
                )
                grid.add_widget(substation_title)
                
                # Add header for each substation
                header_layout = BoxLayout(size_hint_y=None, height=35, spacing=5)
                header_layout.add_widget(Label(text='Τοποθεσία', bold=True, size_hint_x=0.2))
                header_layout.add_widget(Label(text='Ανάληψη', bold=True, size_hint_x=0.12))
                header_layout.add_widget(Label(text='Στοιχεία', bold=True, size_hint_x=0.08))
                header_layout.add_widget(Label(text='Ζυγοί', bold=True, size_hint_x=0.08))
                header_layout.add_widget(Label(text='Πυκνωτές', bold=True, size_hint_x=0.08))
                header_layout.add_widget(Label(text='Συντηρήσεις', bold=True, size_hint_x=0.12))
                header_layout.add_widget(Label(text='Τελευταία', bold=True, size_hint_x=0.12))
                header_layout.add_widget(Label(text='', size_hint_x=0.2))  # Space for buttons
                grid.add_widget(header_layout)
                
                # Count elements for this substation
                c.execute("SELECT COUNT(*) FROM elements WHERE substation_id=?", (sub_id,))
                elem_count = c.fetchone()[0]
                
                # Count number of unique bars (excluding unassigned and interconnection bars)
                # Interconnection bars contain a hyphen (e.g., "ΖΥΓΟΣ 1-2")
                c.execute("SELECT COUNT(DISTINCT bar) FROM elements WHERE substation_id=? AND bar IS NOT NULL AND bar != '' AND bar NOT LIKE '%-%'", (sub_id,))
                bar_count = c.fetchone()[0]
                
                # Count active capacitor circuit breakers
                c.execute("SELECT COUNT(*) FROM elements WHERE substation_id=? AND element_type='Διακόπτης ΜΤ' AND is_main_switch=3", (sub_id,))
                capacitor_count = c.fetchone()[0]
                
                # Get maintenance statistics
                c.execute("SELECT COUNT(*) FROM maintenance WHERE substation_id=?", (sub_id,))
                maint_count = c.fetchone()[0]
                
                c.execute("SELECT MAX(date_time) FROM maintenance WHERE substation_id=?", (sub_id,))
                last_maint = c.fetchone()[0]
                last_maint_display = last_maint if last_maint else '-'
                
                # Substation row (removed name since it's now a title)
                sub_row_layout = BoxLayout(size_hint_y=None, height=40, spacing=5)
                
                # Location button (clickable)
                if location:
                    location_btn = Button(
                        text='Google Maps Link', 
                        size_hint_x=0.2,
                        font_size='11sp',
                        padding=(5, 5)
                    )
                    # Bind text_size to button size for proper text wrapping
                    location_btn.bind(size=lambda btn, size: setattr(btn, 'text_size', size))
                    location_btn.bind(on_press=lambda x, url=location: webbrowser.open(url))
                    sub_row_layout.add_widget(location_btn)
                else:
                    sub_row_layout.add_widget(Label(text='-', size_hint_x=0.2))
                
                sub_row_layout.add_widget(Label(text=adoption_date or '-', size_hint_x=0.12))
                sub_row_layout.add_widget(Label(text=str(elem_count), size_hint_x=0.08))
                sub_row_layout.add_widget(Label(text=str(bar_count), size_hint_x=0.08))
                sub_row_layout.add_widget(Label(text=str(capacitor_count), size_hint_x=0.08))
                sub_row_layout.add_widget(Label(text=str(maint_count), size_hint_x=0.12))
                sub_row_layout.add_widget(Label(text=last_maint_display, size_hint_x=0.12))
                sub_row_layout.add_widget(Label(text='', size_hint_x=0.2))  # Empty space to match header
                grid.add_widget(sub_row_layout)
                
                # Edit, Delete, and Maintenance History buttons
                buttons_layout = BoxLayout(size_hint_y=None, height=35, spacing=5)
                
                edit_btn = Button(text='Επεξεργασία', size_hint_x=0.33)
                edit_btn.bind(on_press=lambda x, sid=sub_id, sname=sub_name, loc=location, adate=adoption_date, div=division, p=popup: self.show_edit_substation_popup(sid, sname, loc, adate, div, p))
                buttons_layout.add_widget(edit_btn)
                
                maint_hist_btn = Button(text='Ιστορικό Συντ.', size_hint_x=0.34)
                maint_hist_btn.bind(on_press=lambda x, sid=sub_id, sname=sub_name, p=popup: self.show_substation_maintenance_history(sid, sname, p))
                buttons_layout.add_widget(maint_hist_btn)
                
                delete_sub_btn = Button(text='Διαγραφή', size_hint_x=0.33)
                delete_sub_btn.bind(on_press=lambda x, sid=sub_id, p=popup: self.delete_substation(sid, p))
                buttons_layout.add_widget(delete_sub_btn)
                
                grid.add_widget(buttons_layout)
                
                # Add element button for this substation
                add_elem_btn = Button(
                    text=f"   + Προσθήκη Στοιχείου",
                    size_hint_y=None,
                    height=35
                )
                add_elem_btn.bind(on_press=lambda x, sid=sub_id, sname=sub_name, p=popup: self.show_add_element_popup_for_substation(sid, sname, p))
                grid.add_widget(add_elem_btn)
                
                # Inactive elements button with count
                c.execute("SELECT COUNT(*) FROM elements WHERE substation_id=? AND operating_status='Ανενεργή'", (sub_id,))
                inactive_count = c.fetchone()[0]
                inactive_elem_btn = Button(
                    text=f"   Ανενεργά Στοιχεία ({inactive_count})",
                    size_hint_y=None,
                    height=35
                )
                inactive_elem_btn.bind(on_press=lambda x, sid=sub_id, sname=sub_name, p=popup: self.show_inactive_elements(sid, sname, p))
                grid.add_widget(inactive_elem_btn)
                
                # Elements section (only active elements)
                # Fetch model data from element_models table
                c.execute("""
                    SELECT e.id, e.element_type, e.name, e.serial_number, e.maintenance_date, 
                           e.manufacturer, e.manufacture_year, e.bar, e.is_main_switch,
                           em.breaker_category, em.model_name, em.manufacturer as model_manufacturer, 
                           em.maintenance_cycle, em.installation_space
                    FROM elements e 
                    LEFT JOIN element_models em ON e.element_model_id = em.id 
                    WHERE e.substation_id=? AND (e.operating_status IS NULL OR e.operating_status='Ενεργή') 
                    ORDER BY e.bar
                """, (sub_id,))
                elements = c.fetchall()
                
                if elements:
                    # Define sort priority for element types
                    def get_element_priority(elem):
                        elem_id, elem_type, elem_name, serial_number, maintenance_date, manufacturer, manufacture_year, bar, is_main_switch, breaker_category, model_name, model_manufacturer, maintenance_cycle, installation_space = elem
                        
                        # Priority order: HV breaker, Transformer, Motor Drive, MV main breaker, MV line breakers, MV capacitor breakers, rest
                        if elem_type == 'Διακόπτης ΥΤ':
                            return (1, elem_name)
                        elif elem_type == 'Μετασχηματιστής 150/20KV':
                            return (2, elem_name)
                        elif elem_type == 'Motor Drive':
                            return (3, elem_name)
                        elif elem_type == 'Διακόπτης ΜΤ' and is_main_switch == 1:  # Main breaker
                            return (4, elem_name)
                        elif elem_type == 'Διακόπτης ΜΤ' and is_main_switch == 2:  # Interconnection breaker
                            return (5, elem_name)
                        elif elem_type == 'Διακόπτης ΜΤ' and is_main_switch == 0:  # Line breaker
                            return (6, elem_name)
                        elif elem_type == 'Διακόπτης ΜΤ' and is_main_switch == 3:  # Capacitor breaker
                            return (7, elem_name)
                        else:
                            return (8, elem_name)
                    
                    # Group elements by bar
                    bars_dict = {}
                    for elem in elements:
                        elem_id, elem_type, elem_name, serial_number, maintenance_date, manufacturer, manufacture_year, bar, is_main_switch, breaker_category, model_name, model_manufacturer, maintenance_cycle, installation_space = elem
                        
                        bar_key = bar if bar else '(Μη καταχωρημένο)'
                        if bar_key not in bars_dict:
                            bars_dict[bar_key] = []
                        bars_dict[bar_key].append(elem)
                    
                    # Sort elements within each bar according to priority
                    for bar_key in bars_dict:
                        bars_dict[bar_key].sort(key=get_element_priority)
                    
                    # Display elements grouped by bar
                    # Show bars in order: ΖΥΓΟΣ 1, ΖΥΓΟΣ 2, etc., then unassigned
                    sorted_bars = sorted([b for b in bars_dict.keys() if b.startswith('ΖΥΓΟΣ')])
                    if '(Μη καταχωρημένο)' in bars_dict:
                        sorted_bars.append('(Μη καταχωρημένο)')
                    
                    for bar_name in sorted_bars:
                        bar_elements = bars_dict[bar_name]
                        
                        # Bar header with count
                        element_count = len(bar_elements)
                        bar_label = Label(
                            text=f"   {bar_name} ({element_count} στοιχεία)",
                            size_hint_y=None,
                            height=35,
                            bold=True,
                            color=(0.2, 0.6, 1, 1)  # Blue color for bar headers
                        )
                        grid.add_widget(bar_label)
                        
                        # Display elements in this bar
                        for j, elem in enumerate(bar_elements, 1):
                            elem_id, elem_type, elem_name, serial_number, maintenance_date, manufacturer, manufacture_year, bar, is_main_switch, breaker_category, model_name, model_manufacturer, maintenance_cycle, installation_space = elem
                            
                            # Check if maintenance is overdue or missing
                            from datetime import datetime, timedelta
                            is_overdue = False
                            if maintenance_cycle and maintenance_cycle > 0:
                                if not maintenance_date or maintenance_date.strip() == '':
                                    # Missing maintenance date when cycle is defined
                                    is_overdue = True
                                else:
                                    try:
                                        last_maint = datetime.strptime(maintenance_date.split()[0], '%Y-%m-%d')
                                        years_ago = datetime.now() - timedelta(days=maintenance_cycle * 365)
                                        if last_maint < years_ago:
                                            is_overdue = True
                                    except:
                                        pass
                            
                            # Format maintenance date with color if overdue or missing
                            if is_overdue:
                                maint_display = f"[color=ff0000][b]Τελ. Συντ.: {maintenance_date or '-'}[/b][/color]"
                            else:
                                maint_display = f"Τελ. Συντ.: {maintenance_date or '-'}"
                            
                            # Create element text with multiple lines for better readability
                            # Add breaker type label for circuit breakers
                            if elem_type in ['Διακόπτης ΥΤ', 'Διακόπτης ΜΤ']:
                                if is_main_switch == 1:
                                    breaker_type_label = 'Κεντρικός'
                                elif is_main_switch == 2:
                                    breaker_type_label = 'Διασυνδετικός'
                                elif is_main_switch == 3:
                                    breaker_type_label = 'Διακόπτης Πυκνωτών'
                                else:
                                    breaker_type_label = 'Γραμμής'
                                elem_type = f"{elem_type} ({breaker_type_label})"
                            
                            breaker_info = f" | {breaker_category}" if breaker_category else ""
                            manufacture_info = f" | Έτος: {manufacture_year}" if manufacture_year else ""
                            elem_text = f"   {j}. [b][size=18]{elem_name}[/size][/b] - {elem_type}{breaker_info}\n      S/N: {serial_number or '-'}{manufacture_info}\n      Κατ.: {model_manufacturer or manufacturer or '-'} | Μοντ.: {model_name or '-'} | Χώρος: {installation_space or '-'}\n      Κύκλος: {maintenance_cycle or '-'} έτη | {maint_display}"
                            
                            # Create a horizontal layout for element and buttons
                            elem_layout = BoxLayout(size_hint_y=None, spacing=5)
                            elem_layout.bind(minimum_height=elem_layout.setter('height'))
                            
                            elem_label = Label(
                                text=elem_text,
                                size_hint=(0.75, None),
                                markup=True
                            )
                            # Enable text wrapping and automatic height calculation
                            elem_label.bind(
                                width=lambda instance, value: setattr(instance, 'text_size', (value, None)),
                                texture_size=lambda instance, value: (
                                    setattr(instance, 'height', max(70, value[1] + 10)),
                                    setattr(elem_layout, 'height', max(70, value[1] + 10))
                                )
                            )
                            elem_layout.add_widget(elem_label)
                            
                            # Button container
                            btn_box = BoxLayout(size_hint_x=0.25, spacing=3)
                            
                            edit_elem_btn = Button(
                                text="Επεξ.",
                                size_hint_x=0.5
                            )
                            edit_elem_btn.bind(on_press=lambda x, eid=elem_id, sid=sub_id, sname=sub_name, p=popup: self.show_edit_element_popup(eid, sid, p, sname))
                            btn_box.add_widget(edit_elem_btn)
                            
                            delete_elem_btn = Button(
                                text="Διαγρ.",
                                size_hint_x=0.5
                            )
                            delete_elem_btn.bind(on_press=lambda x, eid=elem_id, ename=elem_name, sid=sub_id, sname=sub_name, p=popup: self.confirm_delete_element(eid, ename, sid, p, sname))
                            btn_box.add_widget(delete_elem_btn)
                            
                            elem_layout.add_widget(btn_box)
                            
                            grid.add_widget(elem_layout)
                else:
                    no_elem_label = Label(
                        text="   (Χωρίς στοιχεία)",
                        size_hint_y=None,
                        height=30
                    )
                    grid.add_widget(no_elem_label)
                
                # Add spacing between substations
                spacing_widget = Label(text='', size_hint_y=None, height=30)
                grid.add_widget(spacing_widget)
        else:
            empty_label = Label(
                text='Κενή βάση',
                size_hint_y=None,
                height=40
            )
            grid.add_widget(empty_label)
        
        scroll.add_widget(grid)
        main_layout.add_widget(scroll)
        
        # Add buttons layout
        buttons_bottom_layout = BoxLayout(size_hint_y=0.1, spacing=10)
        
        add_substation_btn = Button(text='+ Προσθήκη Υποσταθμού')
        add_substation_btn.bind(on_press=lambda x: self.show_add_substation_popup_from_db_view(popup))
        buttons_bottom_layout.add_widget(add_substation_btn)
        
        close_btn = Button(text='Κλείσιμο')
        close_btn.bind(on_press=popup.dismiss)
        buttons_bottom_layout.add_widget(close_btn)
        
        main_layout.add_widget(buttons_bottom_layout)
        
        popup.content = main_layout
        popup.open()

    def delete_all(self, instance):
        """Delete all data from the database with confirmation"""
        # Create confirmation popup
        confirm_popup = Popup(title='Επιβεβαίωση Διαγραφής', size_hint=(0.6, 0.3))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        warning_label = Label(
            text='Είστε σίγουροι ότι θέλετε να διαγράψετε\nΟΛΕΣ τις εγγραφές από τη βάση δεδομένων;',
            size_hint_y=0.5
        )
        layout.add_widget(warning_label)
        
        buttons_layout = BoxLayout(size_hint_y=0.3, spacing=10)
        
        def confirm_delete():
            confirm_popup.dismiss()
            c = self.conn.cursor()
            # Delete in correct order to respect foreign key constraints
            c.execute("DELETE FROM maintenance_elements")
            c.execute("DELETE FROM maintenance")
            c.execute("DELETE FROM elements")
            c.execute("DELETE FROM substations")
            c.execute("DELETE FROM element_models")
            self.conn.commit()
            show_message_popup('Ολοκληρώθηκε', 'Όλες οι εγγραφές διαγράφηκαν!')
        
        yes_btn = Button(text='ΝΑΙ', color=(1, 0, 0, 1))
        yes_btn.bind(on_press=lambda x: confirm_delete())
        buttons_layout.add_widget(yes_btn)
        
        no_btn = Button(text='ΟΧΙ')
        no_btn.bind(on_press=confirm_popup.dismiss)
        buttons_layout.add_widget(no_btn)
        
        layout.add_widget(buttons_layout)
        confirm_popup.content = layout
        confirm_popup.open()
    
    def create_substations_template(self, instance):
        success, message = create_substations_template(os.path.dirname(__file__))
        title = 'Template Υποσταθμών' if success else 'Σφάλμα'
        show_message_popup(title, message)
    
    def create_elements_template(self, instance):
        success, message = create_elements_template(os.path.dirname(__file__))
        title = 'Template Στοιχείων' if success else 'Σφάλμα'
        show_message_popup(title, message)
    
    def show_import_substations_dialog(self, instance):
        popup = Popup(title='Εισαγωγή υποσταθμών από αρχείο', size_hint=(0.9, 0.9))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Path input
        path_label = Label(text='Διαδρομή αρχείου:', size_hint_y=0.1)
        layout.add_widget(path_label)
        
        path_input = TextInput(
            hint_text='Παστάρε διαδρομή αρχείου',
            size_hint_y=0.15,
            multiline=False
        )
        layout.add_widget(path_input)
        
        # File chooser with default path
        layout.add_widget(Label(text='Ή επιλέξτε από τη λίστα:', size_hint_y=0.1))
        chooser = FileChooserListView(filters=['*.xlsx', '*.csv'], path=os.path.dirname(__file__))
        layout.add_widget(chooser)
        
        # Buttons
        buttons_layout = BoxLayout(size_hint_y=0.1, spacing=10)
        
        def import_file():
            file_path = path_input.text.strip() if path_input.text.strip() else (chooser.selection[0] if chooser.selection else None)
            
            if not file_path:
                show_message_popup('Σφάλμα', 'Παρακαλώ εισάγετε διαδρομή ή επιλέξτε αρχείο!')
                return
            
            if not os.path.exists(file_path):
                show_message_popup('Σφάλμα', 'Το αρχείο δεν βρέθηκε!')
                return
            
            self.import_substations_from_file(file_path)
            popup.dismiss()
        
        import_btn = Button(text='Εισαγωγή')
        import_btn.bind(on_press=lambda x: import_file())
        buttons_layout.add_widget(import_btn)
        
        cancel_btn = Button(text='Ακύρωση')
        cancel_btn.bind(on_press=popup.dismiss)
        buttons_layout.add_widget(cancel_btn)
        
        layout.add_widget(buttons_layout)
        popup.content = layout
        popup.open()
    
    def show_import_elements_dialog(self, instance):
        popup = Popup(title='Εισαγωγή στοιχείων από αρχείο', size_hint=(0.9, 0.9))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Path input
        path_label = Label(text='Διαδρομή αρχείου:', size_hint_y=0.1)
        layout.add_widget(path_label)
        
        path_input = TextInput(
            hint_text='Διαδρομή αρχείου',
            size_hint_y=0.15,
            multiline=False
        )
        layout.add_widget(path_input)
        
        # File chooser with default path
        layout.add_widget(Label(text='Ή επιλέξτε από τη λίστα:', size_hint_y=0.1))
        chooser = FileChooserListView(filters=['*.xlsx', '*.csv'], path=os.path.dirname(__file__))
        layout.add_widget(chooser)
        
        # Buttons
        buttons_layout = BoxLayout(size_hint_y=0.1, spacing=10)
        
        def import_file():
            file_path = path_input.text.strip() if path_input.text.strip() else (chooser.selection[0] if chooser.selection else None)
            
            if not file_path:
                show_message_popup('Σφάλμα', 'Παρακαλώ εισάγετε διαδρομή ή επιλέξτε αρχείο!')
                return
            
            if not os.path.exists(file_path):
                show_message_popup('Σφάλμα', 'Το αρχείο δεν βρέθηκε!')
                return
            
            self.import_elements_from_file(file_path)
            popup.dismiss()
        
        import_btn = Button(text='Εισαγωγή')
        import_btn.bind(on_press=lambda x: import_file())
        buttons_layout.add_widget(import_btn)
        
        cancel_btn = Button(text='Ακύρωση')
        cancel_btn.bind(on_press=popup.dismiss)
        buttons_layout.add_widget(cancel_btn)
        
        layout.add_widget(buttons_layout)
        popup.content = layout
        popup.open()
    
    def import_substations_from_file(self, file_path):
        def on_success(message):
            show_message_popup('Εισαγωγή Υποσταθμών', message, callback=lambda: self.show_records(None))

        def on_error(message):
            show_message_popup('Σφάλμα', message)

        if file_path.endswith('.xlsx'):
            import_substations_from_excel(self.conn, file_path, on_success, on_error)
        elif file_path.endswith('.csv'):
            import_substations_from_csv(self.conn, file_path, on_success, on_error)
        else:
            on_error('Μη υποστηριζόμενη μορφή αρχείου')
    
    def import_elements_from_file(self, file_path):
        # Step 1: detect new substations and duplicates
        try:
            import pandas as pd
            cursor = self.conn.cursor()

            if file_path.endswith('.xlsx'):
                df_elem = pd.read_excel(file_path, sheet_name='Elements')
            elif file_path.endswith('.csv'):
                df_elem = pd.read_csv(file_path)
            else:
                show_message_popup('Σφάλμα', 'Μη υποστηριζόμενη μορφή αρχείου')
                return

            # Check for new substations
            new_substations = set()
            for _, row in df_elem.iterrows():
                sub_name = str(row.get('Substation Name', '')).strip() if pd.notna(row.get('Substation Name', '')) else ''
                if sub_name:
                    cursor.execute('SELECT id FROM substations WHERE name=?', (sub_name,))
                    if not cursor.fetchone():
                        new_substations.add(sub_name)
            
            # If new substations found, prompt user
            if new_substations:
                self._show_new_substations_prompt(file_path, new_substations)
            else:
                # No new substations, proceed to check duplicates
                self._check_duplicates_and_import(file_path)

        except Exception as e:
            show_message_popup('Σφάλμα', f'Σφάλμα κατά τον έλεγχο: {e}')

    def _show_new_substations_prompt(self, file_path, new_substations):
        """Prompt user to confirm creation of new substations"""
        from kivy.uix.popup import Popup
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label
        from kivy.uix.scrollview import ScrollView
        
        popup = Popup(title='Νέοι Υποσταθμοί Εντοπίστηκαν', size_hint=(0.6, 0.5))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        sub_list = '\\n'.join(f'• {sub}' for sub in sorted(new_substations))
        message = f'Οι παρακάτω υποσταθμοί δεν υπάρχουν και θα δημιουργηθούν:\\n\\n{sub_list}\\n\\nΣυνέχεια;'
        
        scroll = ScrollView(bar_width=10, scroll_type=['bars', 'content'])
        label = Label(text=message, size_hint_y=None)
        label.bind(texture_size=label.setter('size'))
        scroll.add_widget(label)
        layout.add_widget(scroll)
        
        # Buttons
        btn_layout = BoxLayout(size_hint_y=0.2, spacing=10)
        
        yes_btn = Button(text='Ναι, Δημιουργία')
        yes_btn.bind(on_press=lambda x: self._create_substations_and_continue(file_path, new_substations, popup))
        btn_layout.add_widget(yes_btn)
        
        no_btn = Button(text='Ακύρωση')
        no_btn.bind(on_press=popup.dismiss)
        btn_layout.add_widget(no_btn)
        
        layout.add_widget(btn_layout)
        popup.content = layout
        popup.open()
    
    def _create_substations_and_continue(self, file_path, new_substations, prompt_popup):
        """Create new substations and continue with import"""
        cursor = self.conn.cursor()
        for sub_name in new_substations:
            cursor.execute('INSERT INTO substations (name) VALUES (?)', (sub_name,))
        self.conn.commit()
        prompt_popup.dismiss()
        
        # Now proceed to check duplicates
        self._check_duplicates_and_import(file_path)
    
    def _check_duplicates_and_import(self, file_path):
        """Check for models first, then duplicate elements, and proceed with import"""
        try:
            import pandas as pd
            cursor = self.conn.cursor()

            if file_path.endswith('.xlsx'):
                df_elem = pd.read_excel(file_path, sheet_name='Elements')
            elif file_path.endswith('.csv'):
                df_elem = pd.read_csv(file_path)
            else:
                show_message_popup('Σφάλμα', 'Μη υποστηριζόμενη μορφή αρχείου')
                return

            # First check models
            models_to_check = {}  # Key: (element_type, model_name, manufacturer), Value: {cycle, space}
            for _, row in df_elem.iterrows():
                element_type = str(row.get('Element Type', '')).strip() if pd.notna(row.get('Element Type', '')) else ''
                model_name = str(row.get('Model Name', '')).strip() if pd.notna(row.get('Model Name', '')) else ''
                model_manufacturer = str(row.get('Model Manufacturer', '')).strip() if pd.notna(row.get('Model Manufacturer', '')) else ''
                model_cycle = int(row.get('Model Maintenance Cycle', 0)) if pd.notna(row.get('Model Maintenance Cycle', '')) else 0
                model_space = str(row.get('Model Installation Space', '')).strip() if pd.notna(row.get('Model Installation Space', '')) else ''
                
                if model_name:  # Only check if model info provided
                    key = (element_type, model_name, model_manufacturer)
                    if key not in models_to_check:
                        models_to_check[key] = {
                            'cycle': model_cycle,
                            'space': model_space
                        }
            
            # Check which models exist and which need to be added/updated
            new_models = []
            conflicting_models = []
            
            for (elem_type, model_name, manufacturer), model_data in models_to_check.items():
                cursor.execute(
                    'SELECT id, maintenance_cycle, installation_space FROM element_models WHERE element_category=? AND model_name=? AND manufacturer=?',
                    (elem_type, model_name, manufacturer)
                )
                existing = cursor.fetchone()
                
                if existing:
                    existing_id, existing_cycle, existing_space = existing
                    # Check if data differs
                    if (existing_cycle != model_data['cycle'] or 
                        (existing_space or '') != (model_data['space'] or '')):
                        conflicting_models.append({
                            'category': elem_type,
                            'name': model_name,
                            'manufacturer': manufacturer,
                            'existing': {'cycle': existing_cycle, 'space': existing_space},
                            'new': model_data
                        })
                else:
                    new_models.append({
                        'category': elem_type,
                        'name': model_name,
                        'manufacturer': manufacturer,
                        'data': model_data
                    })
            
            # If there are model issues, prompt user
            if new_models or conflicting_models:
                self._show_model_check_popup(file_path, new_models, conflicting_models)
            else:
                # No model issues, proceed to check element duplicates
                self._check_element_duplicates(file_path)

        except Exception as e:
            show_message_popup('Σφάλμα', f'Σφάλμα κατά τον έλεγχο: {e}')
    
    def _show_model_check_popup(self, file_path, new_models, conflicting_models):
        """Show popup for user to review and approve model changes"""
        from kivy.uix.popup import Popup
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label
        from kivy.uix.scrollview import ScrollView
        from kivy.uix.gridlayout import GridLayout
        
        popup = Popup(title='Έλεγχος Μοντέλων', size_hint=(0.85, 0.85))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        scroll = ScrollView(bar_width=10, scroll_type=['bars', 'content'])
        content = GridLayout(cols=1, spacing=10, size_hint_y=None, padding=10)
        content.bind(minimum_height=content.setter('height'))
        
        if new_models:
            content.add_widget(Label(
                text='[b]Νέα Μοντέλα (θα προστεθούν):[/b]',
                size_hint_y=None,
                height=30,
                markup=True
            ))
            for model in new_models:
                text = f"• {model['category']} - {model['name']} ({model['manufacturer']})\n  Κύκλος: {model['data']['cycle']} μήνες, Χώρος: {model['data']['space'] or 'N/A'}"
                content.add_widget(Label(
                    text=text,
                    size_hint_y=None,
                    height=50
                ))
        
        if conflicting_models:
            content.add_widget(Label(
                text='[b]Υπάρχοντα Μοντέλα με Διαφορετικά Δεδομένα:[/b]',
                size_hint_y=None,
                height=30,
                markup=True,
                color=(1, 0.5, 0, 1)
            ))
            for model in conflicting_models:
                text = f"• {model['category']} - {model['name']} ({model['manufacturer']})\n  Υπάρχον: Κύκλος {model['existing']['cycle']}, Χώρος {model['existing']['space'] or 'N/A'}\n  Νέο: Κύκλος {model['new']['cycle']}, Χώρος {model['new']['space'] or 'N/A'}"
                content.add_widget(Label(
                    text=text,
                    size_hint_y=None,
                    height=80,
                    color=(1, 0.7, 0, 1)
                ))
        
        scroll.add_widget(content)
        layout.add_widget(scroll)
        
        # Instructions
        if conflicting_models:
            layout.add_widget(Label(
                text='Επιλέξτε "Ενημέρωση" για να αντικαταστήσετε τα υπάρχοντα δεδομένα ή "Χρήση Υπαρχόντων" για να τα κρατήσετε.',
                size_hint_y=0.1
            ))
        
        # Buttons
        btn_layout = BoxLayout(size_hint_y=0.1, spacing=10)
        
        if conflicting_models:
            update_btn = Button(text='Ενημέρωση Μοντέλων')
            update_btn.bind(on_press=lambda x: self._apply_models_and_continue(file_path, new_models, conflicting_models, True, popup))
            btn_layout.add_widget(update_btn)
            
            keep_btn = Button(text='Χρήση Υπαρχόντων')
            keep_btn.bind(on_press=lambda x: self._apply_models_and_continue(file_path, new_models, conflicting_models, False, popup))
            btn_layout.add_widget(keep_btn)
        else:
            continue_btn = Button(text='Συνέχεια')
            continue_btn.bind(on_press=lambda x: self._apply_models_and_continue(file_path, new_models, [], False, popup))
            btn_layout.add_widget(continue_btn)
        
        cancel_btn = Button(text='Ακύρωση')
        cancel_btn.bind(on_press=popup.dismiss)
        btn_layout.add_widget(cancel_btn)
        
        layout.add_widget(btn_layout)
        popup.content = layout
        popup.open()
    
    def _apply_models_and_continue(self, file_path, new_models, conflicting_models, update_conflicts, prompt_popup):
        """Apply model changes and continue with element import"""
        cursor = self.conn.cursor()
        
        # Add new models
        for model in new_models:
            cursor.execute(
                'INSERT INTO element_models (element_category, model_name, manufacturer, maintenance_cycle, installation_space) VALUES (?, ?, ?, ?, ?)',
                (model['category'], model['name'], model['manufacturer'], model['data']['cycle'], model['data']['space'])
            )
        
        # Update conflicting models if user chose to
        if update_conflicts:
            for model in conflicting_models:
                cursor.execute(
                    'UPDATE element_models SET maintenance_cycle=?, installation_space=? WHERE element_category=? AND model_name=? AND manufacturer=?',
                    (model['new']['cycle'], model['new']['space'], model['category'], model['name'], model['manufacturer'])
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

            if file_path.endswith('.xlsx'):
                df_elem = pd.read_excel(file_path, sheet_name='Elements')
            elif file_path.endswith('.csv'):
                df_elem = pd.read_csv(file_path)
            else:
                show_message_popup('Σφάλμα', 'Μη υποστηριζόμενη μορφή αρχείου')
                return

            duplicates = []  # list of tuples (sub_name, name, serial)
            for _, row in df_elem.iterrows():
                sub_name = row.get('Substation Name', '')
                name = str(row.get('Name', '')) if pd.notna(row.get('Name', '')) else ''
                serial_number = str(row.get('Serial Number', '')) if pd.notna(row.get('Serial Number', '')) else ''

                if sub_name and name:
                    cursor.execute('SELECT id FROM substations WHERE name=?', (str(sub_name),))
                    result = cursor.fetchone()
                    if result:
                        sub_id = result[0]
                        cursor.execute(
                            'SELECT id FROM elements WHERE substation_id=? AND name=? AND serial_number=?',
                            (sub_id, name, serial_number)
                        )
                        if cursor.fetchone():
                            duplicates.append((str(sub_name), name, serial_number))

            if duplicates:
                self._show_duplicate_choice_popup(file_path, duplicates)
            else:
                self._proceed_with_import(file_path, default_choice=None, decisions={})

        except Exception as e:
            show_message_popup('Σφάλμα', f'Σφάλμα κατά τον έλεγχο: {e}')

    def _show_duplicate_choice_popup(self, file_path, duplicates_list):
        # User chooses per-duplicate replace/skip, plus replace-all / skip-all shortcuts
        popup = Popup(title='Διπλότυπα Στοιχεία Εντοπίστηκαν', size_hint=(0.9, 0.85))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)

        instructions = Label(
            text='Επιλέξτε για κάθε διπλότυπο αν θα αντικατασταθεί ή θα παραλειφθεί.\nΜπορείτε να επιλέξετε "Αντικατάσταση Όλων" ή "Παράλειψη Όλων".',
            size_hint_y=None,
            height=60
        )
        layout.add_widget(instructions)

        # State
        decisions = {}  # key: (sub_name, name, serial) -> True/False
        default_choice = {'value': None}  # True replace all, False skip all
        manual_choice_made = {'value': False}  # track if any per-item choice occurred

        # Scrollable list
        scroll = ScrollView(bar_width=10, scroll_type=['bars', 'content'])
        grid = GridLayout(cols=1, spacing=6, size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))

        def update_continue_state():
            # Enable continue only if all decisions made or default chosen
            if default_choice['value'] is not None:
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
                manual_choice_made['value'] = True
                # Gray out both buttons after selection and color to show choice
                btn_replace.disabled = True
                btn_skip.disabled = True
                if val:
                    btn_replace.background_color = (0.6, 1, 0.6, 1)  # light green
                    btn_skip.background_color = (0.7, 0.7, 0.7, 1)
                else:
                    btn_skip.background_color = (1, 0.6, 0.6, 1)    # light red
                    btn_replace.background_color = (0.7, 0.7, 0.7, 1)
                disable_global_buttons()
                update_continue_state()

            replace_btn = Button(text='Αντικατάσταση', size_hint_x=0.2)
            skip_btn = Button(text='Παράλειψη', size_hint_x=0.2)
            replace_btn.bind(on_press=lambda _x, br=replace_btn, bs=skip_btn: set_decision(True, br, bs))
            skip_btn.bind(on_press=lambda _x, br=replace_btn, bs=skip_btn: set_decision(False, br, bs))

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
            default_choice['value'] = val
            # set all decisions too
            for tup in duplicates_list:
                decisions[tup] = val
            # Gray out all buttons visually by disabling continue gating
            update_continue_state()
            # disable global buttons once used
            btn_replace_all.disabled = True
            btn_skip_all.disabled = True

        btn_replace_all = Button(text='Αντικατάσταση Όλων')
        btn_replace_all.bind(on_press=lambda _x: choose_all(True))
        buttons_all.add_widget(btn_replace_all)

        btn_skip_all = Button(text='Παράλειψη Όλων')
        btn_skip_all.bind(on_press=lambda _x: choose_all(False))
        buttons_all.add_widget(btn_skip_all)

        layout.add_widget(buttons_all)

        # Action buttons
        actions = BoxLayout(size_hint_y=None, height=50, spacing=10)

        def on_continue(_x):
            if default_choice['value'] is None and len(decisions) < len(duplicates_list):
                show_message_popup('Σφάλμα', 'Ολοκληρώστε τις επιλογές για όλα τα διπλότυπα ή χρησιμοποιήστε "Αντικατάσταση Όλων" / "Παράλειψη Όλων".')
                return
            popup.dismiss()
            self._proceed_with_import(file_path, default_choice=default_choice['value'], decisions=decisions)

        def on_cancel(_x):
            popup.dismiss()

        continue_btn = Button(text='Συνέχεια', disabled=True)
        continue_btn.bind(on_press=on_continue)
        cancel_btn = Button(text='Ακύρωση')
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
            show_message_popup('Εισαγωγή Στοιχείων', message, callback=lambda: self.show_records(None))

        def on_error(message):
            show_message_popup('Σφάλμα', message)

        # Resolver passed to importer per duplicate
        def on_duplicate(sub_name, name, serial_number):
            key = (sub_name, name, serial_number)
            if key in decisions:
                return decisions[key]
            if default_choice is not None:
                return default_choice
            return False  # safe default

        if file_path.endswith('.xlsx'):
            import_elements_from_excel(self.conn, file_path, on_success, on_error, on_duplicate)
        elif file_path.endswith('.csv'):
            import_elements_from_csv(self.conn, file_path, on_success, on_error, on_duplicate)
        else:
            on_error('Μη υποστηριζόμενη μορφή αρχείου')

    def show_edit_element_popup(self, element_id, substation_id, parent_popup, substation_name=None, grandparent_popup=None):
        """Show popup to edit an existing element"""
        from kivy.uix.popup import Popup
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label
        from kivy.uix.textinput import TextInput
        from kivy.uix.spinner import Spinner
        from kivy.uix.scrollview import ScrollView
        
        # Fetch element data
        c = self.conn.cursor()
        c.execute("SELECT element_type, name, serial_number, maintenance_date, manufacturer, model, model_version, installation_space, operating_status, maintenance_cycle, manufacture_year, element_model_id, bar, is_main_switch FROM elements WHERE id=?", (element_id,))
        element = c.fetchone()
        
        if not element:
            show_message_popup('Σφάλμα', 'Το στοιχείο δεν βρέθηκε!')
            return
        
        elem_type, name, serial_num, maint_date, manufacturer, model, model_version, install_space, op_status, maint_cycle, manuf_year, model_id, bar, is_main_switch = element
        
        popup = Popup(title=f'Επεξεργασία: {name}', size_hint=(0.9, 0.9))
        main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        scroll = ScrollView(bar_width=10, scroll_type=['bars', 'content'])
        layout = BoxLayout(orientation='vertical', size_hint_y=None, padding=5, spacing=8)
        layout.bind(minimum_height=layout.setter('height'))
        
        # Element type (read-only)
        layout.add_widget(Label(text=f'Τύπος: {elem_type}', size_hint_y=None, height=30, bold=True))
        
        # Model selection
        layout.add_widget(Label(text='Μοντέλο:', size_hint_y=None, height=30))
        
        # Load models for this category
        c.execute("SELECT id, model_name, manufacturer FROM element_models WHERE element_category=? ORDER BY model_name", (elem_type,))
        models = c.fetchall()
        
        models_data = {}
        model_values = []
        selected_model_text = 'Επιλέξτε μοντέλο'
        
        if models:
            for m in models:
                key = f"{m[1]} - {m[2] or 'N/A'}"
                model_values.append(key)
                models_data[key] = {'id': m[0], 'model_name': m[1], 'manufacturer': m[2] or ''}
                if m[0] == model_id:
                    selected_model_text = key
        
        model_spinner = Spinner(
            text=selected_model_text,
            values=model_values if model_values else ['Δεν υπάρχουν μοντέλα'],
            size_hint_y=None,
            height=40
        )
        layout.add_widget(model_spinner)
        
        # Bar selection
        layout.add_widget(Label(text='Ζυγός (Bar):', size_hint_y=None, height=30))
        # Determine if current element is an interconnection breaker (only MV breakers can be interconnecting)
        is_interconnection = (elem_type == 'Διακόπτης ΜΤ' and is_main_switch == 2)
        available_bars = self.get_available_bars(substation_id, is_interconnection)
        current_bar_text = bar if bar else '(Μη καταχωρημένο)'
        # Ensure current bar is in the list
        if current_bar_text not in available_bars:
            available_bars.append(current_bar_text)
        bar_spinner = Spinner(
            text=current_bar_text,
            values=available_bars,
            size_hint_y=None,
            height=40
        )
        layout.add_widget(bar_spinner)
        
        # Breaker type selection (only for MV circuit breakers)
        breaker_type_label = Label(text='Τύπος Διακόπτη:', size_hint_y=None, height=30)
        if is_main_switch == 1:
            current_breaker_type = 'Κεντρικός'
        elif is_main_switch == 2:
            current_breaker_type = 'Διασυνδετικός'
        elif is_main_switch == 3:
            current_breaker_type = 'Διακόπτης Πυκνωτών'
        else:
            current_breaker_type = 'Γραμμής'
        breaker_type_spinner = Spinner(
            text=current_breaker_type,
            values=self.BREAKER_TYPES,
            size_hint_y=None,
            height=40
        )
        
        # Handler to refresh bars when breaker type changes
        def on_breaker_type_change(spinner, text):
            is_interconnection = (text == 'Διασυνδετικός')
            available_bars = self.get_available_bars(substation_id, is_interconnection)
            bar_spinner.values = available_bars
            if bar_spinner.text not in available_bars:
                bar_spinner.text = available_bars[0] if available_bars else '(Μη καταχωρημένο)'
        
        breaker_type_spinner.bind(text=on_breaker_type_change)
        
        # Only show breaker type selector for MV circuit breakers (HV breakers are always main)
        if elem_type == 'Διακόπτης ΜΤ':
            layout.add_widget(breaker_type_label)
            layout.add_widget(breaker_type_spinner)
        
        # Dynamic fields
        field_inputs = {}
        for field in self.ELEMENT_FIELD_DEFS:
            layout.add_widget(Label(text=f"{field['label']}:", size_hint_y=None, height=30))
            
            # Get current value
            current_value = ''
            if field['key'] == 'name':
                current_value = name or ''
            elif field['key'] == 'serial_number':
                current_value = serial_num or ''
            elif field['key'] == 'manufacture_year':
                current_value = manuf_year or ''
            elif field['key'] == 'maintenance_date':
                current_value = maint_date or ''
            elif field['key'] == 'manufacturer':
                current_value = manufacturer or ''
            elif field['key'] == 'model':
                current_value = model or ''
            elif field['key'] == 'model_version':
                current_value = model_version or ''
            elif field['key'] == 'installation_space':
                current_value = install_space or self.INSTALLATION_SPACE[0]
            elif field['key'] == 'operating_status':
                current_value = op_status or self.OPERATING_STATUS[0]
            elif field['key'] == 'maintenance_cycle':
                current_value = str(maint_cycle) if maint_cycle else '0'
            
            if field.get('type') == 'spinner':
                spinner = Spinner(text=current_value, values=field['values'], size_hint_y=None, height=40)
                field_inputs[field['key']] = spinner
                layout.add_widget(spinner)
            else:
                ti = TextInput(text=current_value, hint_text=field.get('hint', ''), size_hint_y=None, height=40, multiline=False)
                field_inputs[field['key']] = ti
                layout.add_widget(ti)
        
        scroll.add_widget(layout)
        main_layout.add_widget(scroll)
        
        # Buttons
        buttons_layout = BoxLayout(size_hint_y=0.1, spacing=10)
        
        def save_changes():
            name_val = field_inputs['name'].text.strip()
            if not name_val:
                show_message_popup('Σφάλμα', 'Το όνομα είναι υποχρεωτικό!')
                return
            
            # Validate maintenance_cycle
            try:
                cycle_val = int(field_inputs['maintenance_cycle'].text) if field_inputs['maintenance_cycle'].text else 0
            except ValueError:
                show_message_popup('Σφάλμα', 'Ο κύκλος συντήρησης πρέπει να είναι αριθμός!')
                return
            
            # Check for duplicate name (excluding current element)
            c = self.conn.cursor()
            c.execute("SELECT id FROM elements WHERE substation_id=? AND name=? AND id!=?", (substation_id, name_val, element_id))
            if c.fetchone():
                show_message_popup('Σφάλμα', f'Υπάρχει ήδη στοιχείο με όνομα "{name_val}" σε αυτόν τον υποσταθμό!')
                return
            
            # Get model_id if selected
            new_model_id = models_data[model_spinner.text]['id'] if model_spinner.text in models_data else None
            
            # Get bar value
            bar_value = bar_spinner.text if bar_spinner.text != '(Μη καταχωρημένο)' else ''
            
            # Update is_main_switch based on element type and breaker type selection
            if elem_type == 'Διακόπτης ΥΤ':
                # HV breakers are always main breakers
                new_is_main_switch = 1
            elif elem_type == 'Διακόπτης ΜΤ':
                if breaker_type_spinner.text == 'Κεντρικός':
                    new_is_main_switch = 1
                elif breaker_type_spinner.text == 'Διασυνδετικός':
                    new_is_main_switch = 2
                elif breaker_type_spinner.text == 'Διακόπτης Πυκνωτών':
                    new_is_main_switch = 3
                else:
                    new_is_main_switch = 0
            else:
                new_is_main_switch = 0
            
            c.execute("""UPDATE elements SET 
                        name=?, serial_number=?, maintenance_date=?, manufacturer=?, model=?, model_version=?,
                        installation_space=?, operating_status=?, 
                        maintenance_cycle=?, manufacture_year=?, element_model_id=?, bar=?, is_main_switch=?
                        WHERE id=?""",
                     (name_val,
                      field_inputs['serial_number'].text.strip(),
                      field_inputs['maintenance_date'].text.strip(),
                      field_inputs['manufacturer'].text.strip(),
                      field_inputs['model'].text.strip(),
                      field_inputs['model_version'].text.strip(),
                      field_inputs['installation_space'].text,
                      field_inputs['operating_status'].text,
                      cycle_val,
                      field_inputs['manufacture_year'].text.strip(),
                      new_model_id,
                      bar_value,
                      new_is_main_switch,
                      element_id))
            self.conn.commit()
            popup.dismiss()
            parent_popup.dismiss()
            if grandparent_popup:
                grandparent_popup.dismiss()
            if substation_name:
                show_message_popup('Επιτυχία', 'Οι αλλαγές αποθηκεύτηκαν!', callback=lambda: self._display_substations(substation_name))
            else:
                show_message_popup('Επιτυχία', 'Οι αλλαγές αποθηκεύτηκαν!', callback=lambda: self.show_records(None))
        
        save_btn = Button(text='Αποθήκευση')
        save_btn.bind(on_press=lambda x: save_changes())
        buttons_layout.add_widget(save_btn)
        
        cancel_btn = Button(text='Ακύρωση')
        cancel_btn.bind(on_press=popup.dismiss)
        buttons_layout.add_widget(cancel_btn)
        
        main_layout.add_widget(buttons_layout)
        popup.content = main_layout
        popup.open()
    
    def confirm_delete_element(self, element_id, element_name, substation_id, parent_popup, substation_name=None):
        """Show confirmation popup before deleting an element"""
        from kivy.uix.popup import Popup
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label
        
        confirm_popup = Popup(title='Επιβεβαίωση Διαγραφής', size_hint=(0.6, 0.3))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        warning_label = Label(
            text=f'Είστε σίγουροι ότι θέλετε να διαγράψετε\nτο στοιχείο "{element_name}";',
            size_hint_y=0.5
        )
        layout.add_widget(warning_label)
        
        buttons_layout = BoxLayout(size_hint_y=0.3, spacing=10)
        
        def confirm():
            confirm_popup.dismiss()
            self.delete_element(element_id, substation_id, parent_popup, substation_name)
        
        yes_btn = Button(text='ΝΑΙ', color=(1, 0, 0, 1))
        yes_btn.bind(on_press=lambda x: confirm())
        buttons_layout.add_widget(yes_btn)
        
        no_btn = Button(text='ΟΧΙ')
        no_btn.bind(on_press=confirm_popup.dismiss)
        buttons_layout.add_widget(no_btn)
        
        layout.add_widget(buttons_layout)
        confirm_popup.content = layout
        confirm_popup.open()

    def delete_element(self, element_id, substation_id, parent_popup, substation_name=None):
        c = self.conn.cursor()
        c.execute("DELETE FROM elements WHERE id=?", (element_id,))
        self.conn.commit()
        parent_popup.dismiss()
        if substation_name:
            show_message_popup('Ολοκληρώθηκε', 'Το στοιχείο διαγράφηκε!', callback=lambda: self._display_substations(substation_name))
        else:
            show_message_popup('Ολοκληρώθηκε', 'Το στοιχείο διαγράφηκε!', callback=lambda: self.show_records(None))

    def show_inactive_elements(self, substation_id, substation_name, parent_popup):
        """Show list of inactive elements for a substation"""
        from kivy.uix.popup import Popup
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label
        from kivy.uix.scrollview import ScrollView
        from kivy.uix.gridlayout import GridLayout
        
        c = self.conn.cursor()
        # Fetch model data from element_models table
        c.execute("""
            SELECT e.id, e.element_type, e.name, e.serial_number, 
                   em.manufacturer as model_manufacturer, em.model_name, e.is_main_switch
            FROM elements e 
            LEFT JOIN element_models em ON e.element_model_id = em.id
            WHERE e.substation_id=? AND e.operating_status='Ανενεργή' 
            ORDER BY e.name
        """, (substation_id,))
        inactive_elements = c.fetchall()
        
        popup = Popup(title=f'Ανενεργά Στοιχεία - {substation_name}', size_hint=(0.8, 0.8))
        main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        if not inactive_elements:
            main_layout.add_widget(Label(
                text='Δεν υπάρχουν ανενεργά στοιχεία σε αυτόν τον υποσταθμό',
                size_hint_y=0.8
            ))
        else:
            scroll = ScrollView(bar_width=10, scroll_type=['bars', 'content'])
            grid = GridLayout(cols=1, spacing=10, size_hint_y=None, padding=10)
            grid.bind(minimum_height=grid.setter('height'))
            
            for elem_id, elem_type, elem_name, serial_number, model_manufacturer, model_name, is_main_switch in inactive_elements:
                elem_layout = BoxLayout(size_hint_y=None, height=80, spacing=5, orientation='vertical')
                
                # Add breaker type label for circuit breakers
                display_elem_type = elem_type
                if elem_type in ['Διακόπτης ΥΤ', 'Διακόπτης ΜΤ']:
                    if is_main_switch == 1:
                        breaker_type_label = 'Κεντρικός'
                    elif is_main_switch == 2:
                        breaker_type_label = 'Διασυνδετικός'
                    elif is_main_switch == 3:
                        breaker_type_label = 'Διακόπτης Πυκνωτών'
                    else:
                        breaker_type_label = 'Γραμμής'
                    display_elem_type = f"{elem_type} ({breaker_type_label})"
                
                # Element info
                info_text = f'[b]{elem_name}[/b] - {display_elem_type}\nS/N: {serial_number or "-"} | Κατ.: {model_manufacturer or "-"} | Μοντ.: {model_name or "-"}'
                elem_label = Label(
                    text=info_text,
                    size_hint_y=None,
                    height=50,
                    markup=True
                )
                elem_layout.add_widget(elem_label)
                
                # Buttons
                btn_layout = BoxLayout(size_hint_y=None, height=30, spacing=5)
                
                edit_btn = Button(text='Επεξεργασία')
                edit_btn.bind(on_press=lambda x, eid=elem_id, sid=substation_id, sname=substation_name, p=popup, gp=parent_popup: self.show_edit_element_popup(eid, sid, p, sname, gp))
                btn_layout.add_widget(edit_btn)
                
                elem_layout.add_widget(btn_layout)
                grid.add_widget(elem_layout)
            
            scroll.add_widget(grid)
            main_layout.add_widget(scroll)
        
        # Close button
        close_btn = Button(text='Κλείσιμο', size_hint_y=0.1)
        close_btn.bind(on_press=popup.dismiss)
        main_layout.add_widget(close_btn)
        
        popup.content = main_layout
        popup.open()

    def delete_substation(self, substation_id, parent_popup):
        c = self.conn.cursor()
        # Delete all elements for this substation first
        c.execute("DELETE FROM elements WHERE substation_id=?", (substation_id,))
        # Then delete the substation
        c.execute("DELETE FROM substations WHERE id=?", (substation_id,))
        self.conn.commit()
        parent_popup.dismiss()
        show_message_popup('Ολοκληρώθηκε', 'Ο υποσταθμός και όλα τα στοιχεία του διαγράφηκαν!', callback=lambda: self.show_records(None))
    
    def show_edit_substation_popup(self, substation_id, substation_name, location, adoption_date, division, parent_popup):
        # Create popup
        popup = Popup(title=f'Επεξεργασία Υποσταθμού: {substation_name}', size_hint=(0.8, 0.7))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Division spinner
        division_spinner = Spinner(
            text=division or 'ΤΜΘ',
            values=['ΤΜΘ'],
            size_hint_y=0.15
        )
        layout.add_widget(Label(text='Τομέας:', size_hint_y=0.08))
        layout.add_widget(division_spinner)
        
        # Location input
        location_input = TextInput(
            text=location or '',
            hint_text='Τοποθεσία (Google Maps link)',
            size_hint_y=0.15,
            multiline=False
        )
        layout.add_widget(Label(text='Τοποθεσία:', size_hint_y=0.08))
        layout.add_widget(location_input)
        
        # Adoption date input
        date_input = TextInput(
            text=adoption_date or '',
            hint_text='Ημερομηνία Ανάληψης (YYYY-MM-DD)',
            size_hint_y=0.2,
            multiline=False
        )
        layout.add_widget(Label(text='Ανάληψη:', size_hint_y=0.1))
        layout.add_widget(date_input)
        
        # Buttons layout
        buttons_layout = BoxLayout(size_hint_y=0.2, spacing=10)
        
        def save_changes():
            c = self.conn.cursor()
            c.execute("UPDATE substations SET location=?, adoption_date=?, division=? WHERE id=?", 
                     (location_input.text, date_input.text, division_spinner.text, substation_id))
            self.conn.commit()
            popup.dismiss()
            parent_popup.dismiss()
            show_message_popup('Ολοκληρώθηκε', 'Υποσταθμός ενημερώθηκε!', callback=lambda: self.show_records(None))
        
        save_btn = Button(text='Αποθήκευση')
        save_btn.bind(on_press=lambda x: save_changes())
        buttons_layout.add_widget(save_btn)
        
        cancel_btn = Button(text='Ακύρωση')
        cancel_btn.bind(on_press=popup.dismiss)
        buttons_layout.add_widget(cancel_btn)
        
        layout.add_widget(buttons_layout)
        popup.content = layout
        popup.open()

    def show_add_element_popup(self, instance):
        # Get list of substations
        c = self.conn.cursor()
        c.execute("SELECT id, name FROM substations ORDER BY name")
        substations = c.fetchall()
        
        if not substations:
            show_message_popup('Σφάλμα', 'Δεν υπάρχουν υποσταθμοί!')
            return
        
        # Store substations mapping for later use
        self.substations_map = {s[1]: s[0] for s in substations}
        
        # Create popup
        popup = Popup(title='Προσθήκη Στοιχείου', size_hint=(0.8, 0.9))
        main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Create scrollable area for inputs
        scroll = ScrollView(bar_width=10, scroll_type=['bars', 'content'])
        layout = BoxLayout(orientation='vertical', size_hint_y=None, padding=5, spacing=8)
        layout.bind(minimum_height=layout.setter('height'))
        
        # Substation spinner
        substation_names = list(self.substations_map.keys())
        layout.add_widget(Label(text='Επιλέξτε Υποσταθμό:', size_hint_y=None, height=30))
        substation_spinner = Spinner(
            text=substation_names[0],
            values=substation_names,
            size_hint_y=None,
            height=40
        )
        layout.add_widget(substation_spinner)
        
        # Element type spinner
        layout.add_widget(Label(text='Επιλέξτε Στοιχείο:', size_hint_y=None, height=30))
        element_spinner = Spinner(
            text=self.ELEMENT_TYPES[0],
            values=self.ELEMENT_TYPES,
            size_hint_y=None,
            height=40
        )
        layout.add_widget(element_spinner)
        
        # Bar selection (auto-populated from transformers)
        bar_label = Label(text='Ζυγός (Bar):', size_hint_y=None, height=30)
        layout.add_widget(bar_label)
        
        # Get initial bars for the first substation
        initial_bars = self.get_available_bars(self.substations_map[substation_names[0]])
        bar_spinner = Spinner(
            text=initial_bars[0] if initial_bars else '(Μη καταχωρημένο)',
            values=initial_bars if initial_bars else ['(Μη καταχωρημένο)'],
            size_hint_y=None,
            height=40
        )
        layout.add_widget(bar_spinner)
        
        # Update bars when substation changes
        def on_substation_change(spinner, text):
            substation_id = self.substations_map[text]
            # Check if current element type is a breaker and breaker type is Διασυνδετικός
            is_interconnection = (element_spinner.text in ['Διακόπτης ΥΤ', 'Διακόπτης ΜΤ'] and 
                                 breaker_type_spinner.text == 'Διασυνδετικός')
            available_bars = self.get_available_bars(substation_id, is_interconnection)
            bar_spinner.values = available_bars
            bar_spinner.text = available_bars[0] if available_bars else '(Μη καταχωρημένο)'
        
        substation_spinner.bind(text=on_substation_change)
        
        # Breaker type selection (Main or Line or Interconnection) - only for circuit breakers
        breaker_type_label = Label(text='Τύπος Διακόπτη:', size_hint_y=None, height=30)
        breaker_type_spinner = Spinner(
            text=self.BREAKER_TYPES[0],
            values=self.BREAKER_TYPES,
            size_hint_y=None,
            height=40
        )
        
        # Update bars when breaker type changes
        def on_breaker_type_change(spinner, text):
            substation_id = self.substations_map[substation_spinner.text]
            is_interconnection = (element_spinner.text in ['Διακόπτης ΥΤ', 'Διακόπτης ΜΤ'] and 
                                 text == 'Διασυνδετικός')
            available_bars = self.get_available_bars(substation_id, is_interconnection)
            bar_spinner.values = available_bars
            bar_spinner.text = available_bars[0] if available_bars else '(Μη καταχωρημένο)'
        
        breaker_type_spinner.bind(text=on_breaker_type_change)
        
        # Model selection with "Add New" button
        model_header = BoxLayout(size_hint_y=None, height=30, spacing=5)
        model_header.add_widget(Label(text='Μοντέλο:', size_hint_x=0.7))
        add_model_btn = Button(text='+ Νέο Μοντέλο', size_hint_x=0.3, size_hint_y=None, height=30)
        model_header.add_widget(add_model_btn)
        layout.add_widget(model_header)
        
        # Model spinner (will be populated based on element type)
        model_spinner = Spinner(
            text='Επιλέξτε μοντέλο',
            values=['Επιλέξτε μοντέλο'],
            size_hint_y=None,
            height=40
        )
        layout.add_widget(model_spinner)
        
        # Store model data
        models_data = {}
        
        def load_models_for_category(category):
            """Load models for selected element category"""
            c = self.conn.cursor()
            c.execute("SELECT id, model_name, manufacturer, maintenance_cycle, installation_space, breaker_category FROM element_models WHERE element_category=? ORDER BY model_name", (category,))
            models = c.fetchall()
            
            models_data.clear()
            if models:
                # Build display names
                display_names = []
                for m in models:
                    display_name = m[1]  # model_name
                    display_name += f" - {m[2] or 'N/A'}"  # manufacturer
                    display_names.append(display_name)
                
                model_spinner.values = display_names
                for i, m in enumerate(models):
                    key = display_names[i]
                    models_data[key] = {
                        'id': m[0],
                        'model_name': m[1],
                        'manufacturer': m[2] or '',
                        'maintenance_cycle': m[3] or 0,
                        'installation_space': m[4] or '',
                        'breaker_category': m[5] or ''
                    }
                model_spinner.text = model_spinner.values[0]
            else:
                model_spinner.values = ['Επιλέξτε μοντέλο']
                model_spinner.text = 'Επιλέξτε μοντέλο'
        
        # Function to load models when element type changes
        def on_element_type_change(spinner, text):
            load_models_for_category(text)
            # Show breaker type selector for circuit breakers
            if text in ['Διακόπτης ΥΤ', 'Διακόπτης ΜΤ']:
                if breaker_type_label not in layout.children:
                    idx = layout.children.index(model_spinner)
                    layout.add_widget(breaker_type_spinner, index=idx)
                    layout.add_widget(breaker_type_label, index=idx+1)
                # Update bars based on breaker type
                substation_id = self.substations_map[substation_spinner.text]
                is_interconnection = (breaker_type_spinner.text == 'Διασυνδετικός')
                available_bars = self.get_available_bars(substation_id, is_interconnection)
                bar_spinner.values = available_bars
                bar_spinner.text = available_bars[0] if available_bars else '(Μη καταχωρημένο)'
            else:
                if breaker_type_label in layout.children:
                    layout.remove_widget(breaker_type_label)
                    layout.remove_widget(breaker_type_spinner)
                # Reset to regular bars for non-breaker elements
                substation_id = self.substations_map[substation_spinner.text]
                available_bars = self.get_available_bars(substation_id, False)
                bar_spinner.values = available_bars
                bar_spinner.text = available_bars[0] if available_bars else '(Μη καταχωρημένο)'
        
        element_spinner.bind(text=on_element_type_change)
        on_element_type_change(element_spinner, element_spinner.text)
        
        # Dynamic element fields (auto-filled from model, can be overridden)
        field_inputs = {}
        for field in self.ELEMENT_FIELD_DEFS:
            layout.add_widget(Label(text=f"{field['label']}:", size_hint_y=None, height=30))
            if field.get('type') == 'spinner':
                spinner = Spinner(text=field['values'][0], values=field['values'], size_hint_y=None, height=40)
                field_inputs[field['key']] = spinner
                layout.add_widget(spinner)
            else:
                ti = TextInput(hint_text=field.get('hint', ''), size_hint_y=None, height=40, multiline=False)
                field_inputs[field['key']] = ti
                layout.add_widget(ti)
        
        # Auto-fill fields when model is selected
        def on_model_selected(spinner, text):
            if text in models_data:
                model = models_data[text]
                # Auto-fill fields from model
                field_inputs['manufacturer'].text = model['manufacturer']
                field_inputs['model'].text = model['model_name']
                field_inputs['maintenance_cycle'].text = str(model['maintenance_cycle'])
                field_inputs['installation_space'].text = model['installation_space']
        
        model_spinner.bind(text=on_model_selected)
        
        # Add model button action
        def open_add_model():
            from model_management import show_add_model_popup
            def reload_models():
                load_models_for_category(element_spinner.text)
            show_add_model_popup(self, callback=reload_models, category=element_spinner.text)
        
        add_model_btn.bind(on_press=lambda x: open_add_model())
        
        scroll.add_widget(layout)
        main_layout.add_widget(scroll)

        # Buttons layout
        buttons_layout = BoxLayout(size_hint_y=0.1, spacing=10)

        def add_element():
            substation_name = substation_spinner.text
            substation_id = self.substations_map[substation_name]
            element_type = element_spinner.text

            name_val = field_inputs['name'].text if hasattr(field_inputs['name'], 'text') else field_inputs['name'].text
            if not name_val:
                show_message_popup('Σφάλμα', 'Παρακαλώ εισάγετε όνομα στοιχείου!')
                return

            # Gather values
            values = {
                key: (field_inputs[key].text if hasattr(field_inputs[key], 'text') else field_inputs[key].text)
                for key in field_inputs
            }
            if 'operating_status' in values and hasattr(field_inputs['operating_status'], 'text'):
                values['operating_status'] = field_inputs['operating_status'].text

            # Determine is_main_switch based on element type and breaker type
            # HV breakers are always main breakers (is_main_switch=1)
            if element_type == 'Διακόπτης ΥΤ':
                is_main_switch = 1
            elif element_type == 'Διακόπτης ΜΤ':
                if breaker_type_spinner.text == 'Κεντρικός':
                    is_main_switch = 1
                elif breaker_type_spinner.text == 'Διασυνδετικός':
                    is_main_switch = 2
                elif breaker_type_spinner.text == 'Διακόπτης Πυκνωτών':
                    is_main_switch = 3
                else:
                    is_main_switch = 0
            else:
                is_main_switch = 0
            
            # Get bar assignment
            bar_value = bar_spinner.text if bar_spinner.text != '(Μη καταχωρημένο)' else ''
            
            # Get model_id if selected
            model_id = None
            if model_spinner.text in models_data:
                model_id = models_data[model_spinner.text]['id']
            
            # Validate maintenance_cycle is a number
            maintenance_cycle = values.get('maintenance_cycle', '0')
            try:
                maintenance_cycle_int = int(maintenance_cycle) if maintenance_cycle else 0
            except ValueError:
                show_message_popup('Σφάλμα', 'Ο κύκλος συντήρησης πρέπει να είναι αριθμός!')
                return

            # Check for unique name within substation
            c = self.conn.cursor()
            c.execute("SELECT id FROM elements WHERE substation_id=? AND name=?", (substation_id, name_val))
            if c.fetchone():
                show_message_popup('Σφάλμα', f'Υπάρχει ήδη στοιχείο με όνομα "{name_val}" σε αυτόν τον υποσταθμό!')
                return

            c.execute(
                "INSERT INTO elements (substation_id, element_type, name, serial_number, maintenance_date, manufacturer, model, model_version, installation_space, operating_status, maintenance_cycle, element_model_id, manufacture_year, bar, is_main_switch) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    substation_id,
                    element_type,
                    values.get('name', ''),
                    values.get('serial_number', ''),
                    values.get('maintenance_date', ''),
                    values.get('manufacturer', ''),
                    values.get('model', ''),
                    values.get('model_version', ''),
                    values.get('installation_space', 'Εσωτερικός'),
                    values.get('operating_status', 'Ενεργή'),
                    maintenance_cycle_int,
                    model_id,
                    values.get('manufacture_year', ''),
                    bar_value,
                    is_main_switch,
                ),
            )
            new_element_id = c.lastrowid
            self.conn.commit()
            
            # Sync to cloud if TEST substation
            CloudSync.sync_element_add(self.conn, new_element_id, substation_id)
            
            popup.dismiss()
            show_message_popup('Επιτυχία', f'Στοιχείο προστέθηκε στον {substation_name}!', callback=lambda: self._display_substations(substation_name))
        
        add_btn = Button(text='Προσθήκη')
        add_btn.bind(on_press=lambda x: add_element())
        buttons_layout.add_widget(add_btn)
        
        cancel_btn = Button(text='Ακύρωση')
        cancel_btn.bind(on_press=popup.dismiss)
        buttons_layout.add_widget(cancel_btn)
        
        main_layout.add_widget(buttons_layout)
        popup.content = main_layout
        popup.open()

    def show_add_element_popup_for_substation(self, substation_id, substation_name, parent_popup):
        # Create popup
        popup = Popup(title=f'Προσθήκη Στοιχείου', size_hint=(0.8, 0.9))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Create scrollable area for inputs
        scroll = ScrollView(bar_width=10, scroll_type=['bars', 'content'])
        input_layout = BoxLayout(orientation='vertical', size_hint_y=None, padding=10, spacing=10)
        input_layout.bind(minimum_height=input_layout.setter('height'))
        
        # Substation selection dropdown at the top
        input_layout.add_widget(Label(text='Υποσταθμός:', size_hint_y=None, height=30))
        c = self.conn.cursor()
        c.execute("SELECT id, name FROM substations ORDER BY name")
        all_substations = c.fetchall()
        
        substation_spinner = Spinner(
            text=substation_name,
            values=[sub[1] for sub in all_substations],
            size_hint_y=None,
            height=40
        )
        input_layout.add_widget(substation_spinner)
        
        # Store substation mapping (name -> id)
        substation_map = {sub[1]: sub[0] for sub in all_substations}
        
        # Element type spinner
        element_spinner = Spinner(
            text=self.ELEMENT_TYPES[0],
            values=self.ELEMENT_TYPES,
            size_hint_y=None,
            height=40
        )
        input_layout.add_widget(Label(text='Επιλέξτε Τύπο Στοιχείου:', size_hint_y=None, height=30))
        input_layout.add_widget(element_spinner)
        
        # Bar selection (auto-populated from transformers)
        bar_label = Label(text='Ζυγός (Bar):', size_hint_y=None, height=30)
        input_layout.add_widget(bar_label)
        
        # Get initial bars for the selected substation
        initial_bars = self.get_available_bars(substation_id)
        bar_spinner = Spinner(
            text=initial_bars[0] if initial_bars else '(Μη καταχωρημένο)',
            values=initial_bars if initial_bars else ['(Μη καταχωρημένο)'],
            size_hint_y=None,
            height=40
        )
        input_layout.add_widget(bar_spinner)
        
        # Update bars when substation changes
        def on_substation_change(spinner, text):
            selected_substation_id = substation_map[text]
            # Check if current element type is a breaker and breaker type is Διασυνδετικός
            is_interconnection = (element_spinner.text in ['Διακόπτης ΥΤ', 'Διακόπτης ΜΤ'] and 
                                 breaker_type_spinner.text == 'Διασυνδετικός')
            available_bars = self.get_available_bars(selected_substation_id, is_interconnection)
            bar_spinner.values = available_bars
            bar_spinner.text = available_bars[0] if available_bars else '(Μη καταχωρημένο)'
        
        substation_spinner.bind(text=on_substation_change)
        
        # Breaker type selection (Main, Line, or Interconnection) - only for circuit breakers
        breaker_type_label = Label(text='Τύπος Διακόπτη:', size_hint_y=None, height=30)
        breaker_type_spinner = Spinner(
            text=self.BREAKER_TYPES[0],
            values=self.BREAKER_TYPES,
            size_hint_y=None,
            height=40
        )
        
        # Update bars when breaker type changes
        def on_breaker_type_change(spinner, text):
            selected_substation_id = substation_map[substation_spinner.text]
            is_interconnection = (element_spinner.text in ['Διακόπτης ΥΤ', 'Διακόπτης ΜΤ'] and 
                                 text == 'Διασυνδετικός')
            available_bars = self.get_available_bars(selected_substation_id, is_interconnection)
            bar_spinner.values = available_bars
            bar_spinner.text = available_bars[0] if available_bars else '(Μη καταχωρημένο)'
        
        breaker_type_spinner.bind(text=on_breaker_type_change)
        
        # Model selection with "Add New" button
        model_header = BoxLayout(size_hint_y=None, height=30, spacing=5)
        model_header.add_widget(Label(text='Μοντέλο:', size_hint_x=0.7))
        add_model_btn = Button(text='+ Νέο Μοντέλο', size_hint_x=0.3, size_hint_y=None, height=30)
        model_header.add_widget(add_model_btn)
        input_layout.add_widget(model_header)
        
        # Model spinner (will be populated based on element type)
        model_spinner = Spinner(
            text='Επιλέξτε μοντέλο',
            values=['Επιλέξτε μοντέλο'],
            size_hint_y=None,
            height=40
        )
        input_layout.add_widget(model_spinner)
        
        # Store model data
        models_data = {}
        
        def load_models_for_category(category):
            """Load models for selected element category"""
            c = self.conn.cursor()
            c.execute("SELECT id, model_name, manufacturer, maintenance_cycle, installation_space, breaker_category FROM element_models WHERE element_category=? ORDER BY model_name", (category,))
            models = c.fetchall()
            
            models_data.clear()
            if models:
                # Build display names
                display_names = []
                for m in models:
                    display_name = m[1]  # model_name
                    display_name += f" - {m[2] or 'N/A'}"  # manufacturer
                    display_names.append(display_name)
                
                model_spinner.values = display_names
                for i, m in enumerate(models):
                    key = display_names[i]
                    models_data[key] = {
                        'id': m[0],
                        'model_name': m[1],
                        'manufacturer': m[2] or '',
                        'maintenance_cycle': m[3] or 0,
                        'installation_space': m[4] or '',
                        'breaker_category': m[5] or ''
                    }
                model_spinner.text = model_spinner.values[0]
            else:
                model_spinner.values = ['Επιλέξτε μοντέλο']
                model_spinner.text = 'Επιλέξτε μοντέλο'
        
        # Function to load models when element type changes
        def on_element_type_change(spinner, text):
            load_models_for_category(text)
            # Show/hide breaker type spinner based on element type (only for MV breakers)
            if text == 'Διακόπτης ΜΤ':
                if breaker_type_label not in input_layout.children:
                    input_layout.add_widget(breaker_type_spinner, index=input_layout.children.index(bar_spinner) + 2)
                    input_layout.add_widget(breaker_type_label, index=input_layout.children.index(breaker_type_spinner) + 1)
                # Refresh bars based on current breaker type
                is_interconnection = (breaker_type_spinner.text == 'Διασυνδετικός')
                available_bars = self.get_available_bars(substation_id, is_interconnection)
                bar_spinner.values = available_bars
                if bar_spinner.text not in available_bars:
                    bar_spinner.text = available_bars[0] if available_bars else '(Μη καταχωρημένο)'
            else:
                if breaker_type_label in input_layout.children:
                    input_layout.remove_widget(breaker_type_label)
                    input_layout.remove_widget(breaker_type_spinner)
                # Reset to regular bars for non-MV breaker elements (HV breakers also use regular bars)
                available_bars = self.get_available_bars(substation_id, False)
                bar_spinner.values = available_bars
                if bar_spinner.text not in available_bars:
                    bar_spinner.text = available_bars[0] if available_bars else '(Μη καταχωρημένο)'
        
        element_spinner.bind(text=on_element_type_change)
        on_element_type_change(element_spinner, element_spinner.text)
        
        # Auto-fill callback when model is selected
        def on_model_selected(spinner, text):
            if text in models_data:
                model = models_data[text]
                # Auto-fill fields from model
                if 'manufacturer' in field_inputs:
                    field_inputs['manufacturer'].text = model['manufacturer']
                if 'maintenance_cycle' in field_inputs:
                    field_inputs['maintenance_cycle'].text = str(model['maintenance_cycle'])
                if 'installation_space' in field_inputs:
                    field_inputs['installation_space'].text = model['installation_space']
                if 'model' in field_inputs:
                    field_inputs['model'].text = model['model_name']
        
        model_spinner.bind(text=on_model_selected)
        
        # Bind "Add New Model" button
        def open_add_model(instance):
            from model_management import show_add_model_popup
            def reload_models():
                load_models_for_category(element_spinner.text)
            show_add_model_popup(self, callback=reload_models, category=element_spinner.text)
        
        add_model_btn.bind(on_press=open_add_model)

        # Dynamic element fields
        field_inputs = {}
        for field in self.ELEMENT_FIELD_DEFS:
            input_layout.add_widget(Label(text=f"{field['label']}:", size_hint_y=None, height=30))
            if field.get('type') == 'spinner':
                spinner = Spinner(
                    text=field['values'][0],
                    values=field['values'],
                    size_hint_y=None,
                    height=40
                )
                field_inputs[field['key']] = spinner
                input_layout.add_widget(spinner)
            else:
                ti = TextInput(
                    hint_text=field.get('hint', ''),
                    size_hint_y=None,
                    height=40,
                    multiline=False
                )
                field_inputs[field['key']] = ti
                input_layout.add_widget(ti)
        
        # Trigger initial auto-fill for default selection
        if model_spinner.text in models_data:
            on_model_selected(model_spinner, model_spinner.text)
        
        scroll.add_widget(input_layout)
        layout.add_widget(scroll)
        
        # Buttons layout
        buttons_layout = BoxLayout(size_hint_y=0.1, spacing=10)
        
        def add_element():
            element_type = element_spinner.text

            # Gather values
            values = {
                key: (field_inputs[key].text if hasattr(field_inputs[key], 'text') else field_inputs[key].text)
                for key in field_inputs
            }
            if 'operating_status' in values and hasattr(field_inputs['operating_status'], 'text'):
                values['operating_status'] = field_inputs['operating_status'].text

            if not values.get('name'):
                show_message_popup('Σφάλμα', 'Παρακαλώ εισάγετε όνομα στοιχείου!')
                return
            
            # Determine breaker type value based on element type and selection
            # HV breakers are always main breakers (is_main_switch=1)
            if element_type == 'Διακόπτης ΥΤ':
                is_main_switch = 1
            elif element_type == 'Διακόπτης ΜΤ':
                if breaker_type_spinner.text == 'Κεντρικός':
                    is_main_switch = 1
                elif breaker_type_spinner.text == 'Διασυνδετικός':
                    is_main_switch = 2
                elif breaker_type_spinner.text == 'Διακόπτης Πυκνωτών':
                    is_main_switch = 3
                else:
                    is_main_switch = 0
            else:
                is_main_switch = 0
            
            # Get bar assignment
            bar_value = bar_spinner.text if bar_spinner.text != '(Μη καταχωρημένο)' else ''
            
            # Validate maintenance_cycle is a number
            maintenance_cycle = values.get('maintenance_cycle', '0')
            try:
                maintenance_cycle_int = int(maintenance_cycle) if maintenance_cycle else 0
            except ValueError:
                show_message_popup('Σφάλμα', 'Ο κύκλος συντήρησης πρέπει να είναι αριθμός!')
                return
            
            # Get selected substation from dropdown
            selected_substation_name = substation_spinner.text
            selected_substation_id = substation_map[selected_substation_name]
            
            # Check for unique name within substation
            c = self.conn.cursor()
            c.execute("SELECT id FROM elements WHERE substation_id=? AND name=?", (selected_substation_id, values.get('name')))
            if c.fetchone():
                show_message_popup('Σφάλμα', f'Υπάρχει ήδη στοιχείο με όνομα "{values.get("name")}" σε αυτόν τον υποσταθμό!')
                return
            
            # Get model_id if a model is selected
            model_id = models_data[model_spinner.text]['id'] if model_spinner.text in models_data else None
            
            c.execute("INSERT INTO elements (substation_id, element_type, name, serial_number, maintenance_date, manufacturer, model, model_version, installation_space, operating_status, maintenance_cycle, element_model_id, manufacture_year, bar, is_main_switch) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
                     (
                        selected_substation_id,
                        element_type,
                        values.get('name', ''),
                        values.get('serial_number', ''),
                        values.get('maintenance_date', ''),
                        values.get('manufacturer', ''),
                        values.get('model', ''),
                        values.get('model_version', ''),
                        values.get('installation_space', 'Εσωτερικός'),
                        values.get('operating_status', 'Ενεργή'),
                        maintenance_cycle_int,
                        model_id,
                        values.get('manufacture_year', ''),
                        bar_value,
                        is_main_switch,
                     ))
            new_element_id = c.lastrowid
            self.conn.commit()
            
            # Sync to cloud if TEST substation
            CloudSync.sync_element_add(self.conn, new_element_id, selected_substation_id)
            
            popup.dismiss()
            parent_popup.dismiss()
            show_message_popup('Επιτυχία', 'Στοιχείο προστέθηκε!', callback=lambda: self._display_substations(selected_substation_name))
        
        add_btn = Button(text='Προσθήκη')
        add_btn.bind(on_press=lambda x: add_element())
        buttons_layout.add_widget(add_btn)
        
        cancel_btn = Button(text='Ακύρωση')
        cancel_btn.bind(on_press=popup.dismiss)
        buttons_layout.add_widget(cancel_btn)
        
        layout.add_widget(buttons_layout)
        popup.content = layout
        popup.open()

    def show_maintenance_menu(self, instance=None, preselected_substation_name=None, parent_popup=None):
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
            show_message_popup('Σφάλμα', 'Δεν υπάρχουν υποσταθμοί!')
            return
        
        popup = Popup(title='Καταχώρηση Συντήρησης', size_hint=(0.9, 0.95))
        
        # Create a scrollable container for all content
        scroll_view = ScrollView(bar_width=10, scroll_type=['bars', 'content'])
        content_layout = GridLayout(cols=1, spacing=10, size_hint_y=None, padding=10)
        content_layout.bind(minimum_height=content_layout.setter('height'))
        
        # Substation selection
        content_layout.add_widget(Label(text='Επιλογή Υποσταθμού:', size_hint_y=None, height=40))
        substation_map = {s[1]: s[0] for s in substations}
        
        # Use preselected substation if provided, otherwise use first in list
        initial_substation = preselected_substation_name if preselected_substation_name else substations[0][1]
        
        substation_spinner = Spinner(
            text=initial_substation,
            values=[s[1] for s in substations],
            size_hint_y=None,
            height=40
        )
        content_layout.add_widget(substation_spinner)
        
        # Maintenance Type
        content_layout.add_widget(Label(text='Τύπος Συντήρησης:', size_hint_y=None, height=35))
        maintenance_type_spinner = Spinner(
            text='Επαναληπτική συντήρηση',
            values=['Επαναληπτική συντήρηση', 'Βλάβη', 'Οπτικός έλεγχος'],
            size_hint_y=None,
            height=35
        )
        content_layout.add_widget(maintenance_type_spinner)
        
        # Date/Time (auto-filled with current)
        from datetime import datetime
        content_layout.add_widget(Label(text='Ημερομηνία & Ώρα:', size_hint_y=None, height=35))
        datetime_input = TextInput(
            text=datetime.now().strftime('%Y-%m-%d %H:%M'),
            hint_text='YYYY-MM-DD HH:MM',
            size_hint_y=None,
            height=35,
            multiline=False
        )
        content_layout.add_widget(datetime_input)
        
        # Overall comments
        content_layout.add_widget(Label(text='Γενικά Σχόλια Συντήρησης:', size_hint_y=None, height=35))
        overall_comments = TextInput(
            hint_text='Γενικά σχόλια για την συντήρηση...',
            size_hint_y=None,
            height=60,
            multiline=True
        )
        content_layout.add_widget(overall_comments)
        
        # Elements selection area
        content_layout.add_widget(Label(text='Στοιχεία που συντηρήθηκαν (τουλάχιστον 1):', size_hint_y=None, height=40))
        
        # Container for element checkboxes (no longer in a separate ScrollView)
        elements_container = GridLayout(cols=1, spacing=5, size_hint_y=None, padding=5)
        elements_container.bind(minimum_height=elements_container.setter('height'))
        content_layout.add_widget(elements_container)
        
        # Dictionary to store element widgets
        element_widgets = {}
        
        def load_elements(substation_name):
            """Load elements for selected substation"""
            elements_container.clear_widgets()
            element_widgets.clear()
            
            substation_id = substation_map[substation_name]
            c = self.conn.cursor()
            c.execute("""
                SELECT e.id, e.element_type, e.name, e.serial_number, e.bar, e.is_main_switch,
                       e.breaker_category, e.manufacturer, e.model,
                       em.manufacturer as model_manufacturer, em.model_name
                FROM elements e
                LEFT JOIN element_models em ON e.element_model_id = em.id
                WHERE e.substation_id=?
                ORDER BY e.bar
            """, (substation_id,))
            elements = c.fetchall()
            
            if not elements:
                elements_container.add_widget(Label(
                    text='Δεν υπάρχουν στοιχεία σε αυτόν τον υποσταθμό',
                    size_hint_y=None,
                    height=40
                ))
                return
            
            # Define sort priority for element types
            def get_element_priority(elem):
                elem_id, elem_type, elem_name, serial_number, bar, is_main_switch, breaker_category, manufacturer, model, model_manufacturer, model_name = elem
                
                # Priority order: HV breaker, Transformer, Motor Drive, MV main breaker, MV interconnection breaker, MV line breaker, MV capacitor breaker, rest
                if elem_type == 'Διακόπτης ΥΤ':
                    return (1, elem_name)
                elif elem_type == 'Μετασχηματιστής 150/20KV':
                    return (2, elem_name)
                elif elem_type == 'Motor Drive':
                    return (3, elem_name)
                elif elem_type == 'Διακόπτης ΜΤ' and is_main_switch == 1:  # Main breaker
                    return (4, elem_name)
                elif elem_type == 'Διακόπτης ΜΤ' and is_main_switch == 2:  # Interconnection breaker
                    return (5, elem_name)
                elif elem_type == 'Διακόπτης ΜΤ' and is_main_switch == 0:  # Line breaker
                    return (6, elem_name)
                elif elem_type == 'Διακόπτης ΜΤ' and is_main_switch == 3:  # Capacitor breaker
                    return (7, elem_name)
                else:
                    return (8, elem_name)
            
            # Group elements by bar
            bars_dict = {}
            for elem in elements:
                elem_id, elem_type, elem_name, serial_number, bar, is_main_switch, breaker_category, manufacturer, model, model_manufacturer, model_name = elem
                
                bar_key = bar if bar else '(Μη καταχωρημένο)'
                if bar_key not in bars_dict:
                    bars_dict[bar_key] = []
                bars_dict[bar_key].append(elem)
            
            # Sort elements within each bar according to priority
            for bar_key in bars_dict:
                bars_dict[bar_key].sort(key=get_element_priority)
            
            # Display elements grouped by bar
            # Show bars in order: ΖΥΓΟΣ 1, ΖΥΓΟΣ 2, etc., then unassigned
            sorted_bars = sorted([b for b in bars_dict.keys() if b.startswith('ΖΥΓΟΣ')])
            if '(Μη καταχωρημένο)' in bars_dict:
                sorted_bars.append('(Μη καταχωρημένο)')
            
            # Display elements grouped by bar
            for bar_name in sorted_bars:
                bar_elements = bars_dict[bar_name]
                
                # Bar header with count
                element_count = len(bar_elements)
                bar_label = Label(
                    text=f'{bar_name} ({element_count} στοιχεία)',
                    size_hint_y=None,
                    height=35,
                    bold=True,
                    color=(0.2, 0.6, 1, 1)  # Blue color for bar headers
                )
                elements_container.add_widget(bar_label)
                
                # Display elements in this bar
                for elem_id, elem_type, elem_name, serial_number, bar, is_main_switch, breaker_category, manufacturer, model, model_manufacturer, model_name in bar_elements:
                    # Determine if this is a circuit breaker for showing measurement fields
                    is_breaker = (elem_type in ['Διακόπτης ΜΤ', 'Διακόπτης ΥΤ'])
                    
                    # Build element display text with breaker type, manufacturer, and model
                    elem_display = f'[b]{elem_name}[/b] - {elem_type}'
                    if breaker_category:
                        elem_display += f' ({breaker_category})'
                    elem_display += f'\nS/N: {serial_number or "-"}'
                    
                    # Add manufacturer and model info
                    mfr = model_manufacturer or manufacturer or '-'
                    mdl = model_name or model or '-'
                    elem_display += f' | Κατ.: {mfr} | Μοντ.: {mdl}'
                    
                    # Element container - initially just checkbox and label
                    elem_box = BoxLayout(size_hint_y=None, spacing=5, orientation='vertical')
                    elem_box.bind(minimum_height=elem_box.setter('height'))
                    
                    # Checkbox and name (always visible)
                    checkbox_layout = BoxLayout(size_hint_y=None, height=50, spacing=5)
                    checkbox = CheckBox(size_hint_x=0.08)
                    checkbox_layout.add_widget(checkbox)
                    
                    elem_label = Label(
                        text=elem_display,
                        size_hint_x=0.92,
                        markup=True
                    )
                    checkbox_layout.add_widget(elem_label)
                    elem_box.add_widget(checkbox_layout)
                    
                    # Container for details (initially hidden)
                    details_container = BoxLayout(size_hint_y=None, spacing=5, orientation='vertical')
                    details_container.bind(minimum_height=details_container.setter('height'))
                    
                    # Comments for this element
                    elem_comments = TextInput(
                        hint_text='Σχόλια για αυτό το στοιχείο...',
                        size_hint_y=None,
                        height=30,
                        multiline=False
                    )
                    details_container.add_widget(elem_comments)
                    
                    # Measurement fields dictionary
                    measurements = {}
                    
                    # Add measurement fields for circuit breakers
                    if is_breaker:
                        # Insulation - Switch Closed (to ground)
                        details_container.add_widget(Label(
                            text='ΜΕΤΡΗΣΗ ΑΝΤΙΣΤΑΣΗΣ ΜΟΝΩΣΗΣ - ΔΙΑΚΟΠΤΗΣ ΚΛΕΙΣΤΟΣ (Φ-ΓΗ):',
                            size_hint_y=None,
                            height=25,
                            bold=True
                        ))
                        
                        # ΦΑ-ΓΗ
                        closed_fa_layout = BoxLayout(size_hint_y=None, height=30, spacing=3)
                        closed_fa_layout.add_widget(Label(text='ΦΑ-ΓΗ:', size_hint_x=0.15))
                        ins_closed_fa = TextInput(hint_text='0.0', size_hint_x=0.35, multiline=False)
                        closed_fa_layout.add_widget(ins_closed_fa)
                        ins_closed_fa_unit = Spinner(text='GΩ', values=['MΩ', 'GΩ', 'TΩ'], size_hint_x=0.15)
                        closed_fa_layout.add_widget(ins_closed_fa_unit)
                        closed_fa_layout.add_widget(Label(text='', size_hint_x=0.35))  # Spacer
                        details_container.add_widget(closed_fa_layout)
                        
                        # ΦΒ-ΓΗ
                        closed_fb_layout = BoxLayout(size_hint_y=None, height=30, spacing=3)
                        closed_fb_layout.add_widget(Label(text='ΦΒ-ΓΗ:', size_hint_x=0.15))
                        ins_closed_fb = TextInput(hint_text='0.0', size_hint_x=0.35, multiline=False)
                        closed_fb_layout.add_widget(ins_closed_fb)
                        ins_closed_fb_unit = Spinner(text='GΩ', values=['MΩ', 'GΩ', 'TΩ'], size_hint_x=0.15)
                        closed_fb_layout.add_widget(ins_closed_fb_unit)
                        closed_fb_layout.add_widget(Label(text='', size_hint_x=0.35))  # Spacer
                        details_container.add_widget(closed_fb_layout)
                        
                        # ΦΓ-ΓΗ
                        closed_fc_layout = BoxLayout(size_hint_y=None, height=30, spacing=3)
                        closed_fc_layout.add_widget(Label(text='ΦΓ-ΓΗ:', size_hint_x=0.15))
                        ins_closed_fc = TextInput(hint_text='0.0', size_hint_x=0.35, multiline=False)
                        closed_fc_layout.add_widget(ins_closed_fc)
                        ins_closed_fc_unit = Spinner(text='GΩ', values=['MΩ', 'GΩ', 'TΩ'], size_hint_x=0.15)
                        closed_fc_layout.add_widget(ins_closed_fc_unit)
                        closed_fc_layout.add_widget(Label(text='', size_hint_x=0.35))  # Spacer
                        details_container.add_widget(closed_fc_layout)
                        
                        # Insulation - Switch Open (phase to phase)
                        details_container.add_widget(Label(
                            text='ΜΕΤΡΗΣΗ ΑΝΤΙΣΤΑΣΗΣ ΜΟΝΩΣΗΣ - ΔΙΑΚΟΠΤΗΣ ΑΝΟΙΧΤΟΣ (Φ-Φ):',
                            size_hint_y=None,
                            height=25,
                            bold=True
                        ))
                        
                        # ΦΑ-ΦΑ
                        open_fa_layout = BoxLayout(size_hint_y=None, height=30, spacing=3)
                        open_fa_layout.add_widget(Label(text='ΦΑ-ΦΑ:', size_hint_x=0.15))
                        ins_open_fa = TextInput(hint_text='0.0', size_hint_x=0.35, multiline=False)
                        open_fa_layout.add_widget(ins_open_fa)
                        ins_open_fa_unit = Spinner(text='GΩ', values=['MΩ', 'GΩ', 'TΩ'], size_hint_x=0.15)
                        open_fa_layout.add_widget(ins_open_fa_unit)
                        open_fa_layout.add_widget(Label(text='', size_hint_x=0.35))  # Spacer
                        details_container.add_widget(open_fa_layout)
                        
                        # ΦΒ-ΦΒ
                        open_fb_layout = BoxLayout(size_hint_y=None, height=30, spacing=3)
                        open_fb_layout.add_widget(Label(text='ΦΒ-ΦΒ:', size_hint_x=0.15))
                        ins_open_fb = TextInput(hint_text='0.0', size_hint_x=0.35, multiline=False)
                        open_fb_layout.add_widget(ins_open_fb)
                        ins_open_fb_unit = Spinner(text='GΩ', values=['MΩ', 'GΩ', 'TΩ'], size_hint_x=0.15)
                        open_fb_layout.add_widget(ins_open_fb_unit)
                        open_fb_layout.add_widget(Label(text='', size_hint_x=0.35))  # Spacer
                        details_container.add_widget(open_fb_layout)
                        
                        # ΦΓ-ΦΓ
                        open_fc_layout = BoxLayout(size_hint_y=None, height=30, spacing=3)
                        open_fc_layout.add_widget(Label(text='ΦΓ-ΦΓ:', size_hint_x=0.15))
                        ins_open_fc = TextInput(hint_text='0.0', size_hint_x=0.35, multiline=False)
                        open_fc_layout.add_widget(ins_open_fc)
                        ins_open_fc_unit = Spinner(text='GΩ', values=['MΩ', 'GΩ', 'TΩ'], size_hint_x=0.15)
                        open_fc_layout.add_widget(ins_open_fc_unit)
                        open_fc_layout.add_widget(Label(text='', size_hint_x=0.35))  # Spacer
                        details_container.add_widget(open_fc_layout)
                        
                        # Contact Resistance - Switch Closed
                        details_container.add_widget(Label(
                            text='ΑΝΤΙΣΤΑΣΗ ΔΙΕΛΕΥΣΗΣ (μΩ) - ΔΙΑΚΟΠΤΗΣ ΚΛΕΙΣΤΟΣ:',
                            size_hint_y=None,
                            height=25,
                            bold=True
                        ))
                        
                        contact_layout = BoxLayout(size_hint_y=None, height=30, spacing=3)
                        contact_layout.add_widget(Label(text='ΦΑ-ΦΑ:', size_hint_x=0.15))
                        cont_fa = TextInput(hint_text='0.0', size_hint_x=0.25, multiline=False)
                        contact_layout.add_widget(cont_fa)
                        contact_layout.add_widget(Label(text='ΦΒ-ΦΒ:', size_hint_x=0.15))
                        cont_fb = TextInput(hint_text='0.0', size_hint_x=0.25, multiline=False)
                        contact_layout.add_widget(cont_fb)
                        contact_layout.add_widget(Label(text='ΦΓ-ΦΓ:', size_hint_x=0.15))
                        cont_fc = TextInput(hint_text='0.0', size_hint_x=0.25, multiline=False)
                        contact_layout.add_widget(cont_fc)
                        details_container.add_widget(contact_layout)
                        
                        # Store measurement widgets
                        measurements = {
                            'ins_closed_fa': ins_closed_fa,
                            'ins_closed_fa_unit': ins_closed_fa_unit,
                            'ins_closed_fb': ins_closed_fb,
                            'ins_closed_fb_unit': ins_closed_fb_unit,
                            'ins_closed_fc': ins_closed_fc,
                            'ins_closed_fc_unit': ins_closed_fc_unit,
                            'ins_open_fa': ins_open_fa,
                            'ins_open_fa_unit': ins_open_fa_unit,
                            'ins_open_fb': ins_open_fb,
                                'ins_open_fb_unit': ins_open_fb_unit,
                                'ins_open_fc': ins_open_fc,
                                'ins_open_fc_unit': ins_open_fc_unit,
                                'cont_fa': cont_fa,
                                'cont_fb': cont_fb,
                                'cont_fc': cont_fc
                            }
                    
                    # Don't add details_container yet - will be added when checkbox is checked
                    
                    # Function to toggle details visibility
                    def toggle_details(checkbox_instance, value, elem_box=elem_box, details_container=details_container):
                        if value:
                            # Show details - add container to elem_box
                            if details_container not in elem_box.children:
                                elem_box.add_widget(details_container)
                        else:
                            # Hide details - remove container from elem_box
                            if details_container in elem_box.children:
                                elem_box.remove_widget(details_container)
                    
                    # Bind checkbox to toggle function
                    checkbox.bind(active=toggle_details)
                    
                    elements_container.add_widget(elem_box)
                    
                    # Add spacing between elements
                    spacing = Label(text='', size_hint_y=None, height=5)
                    elements_container.add_widget(spacing)
                    
                    element_widgets[elem_id] = {
                        'checkbox': checkbox,
                        'comments': elem_comments,
                        'measurements': measurements,
                        'elem_type': elem_type
                    }
        
        # Load initial elements
        load_elements(substation_spinner.text)
        
        # Update elements when substation changes
        substation_spinner.bind(text=lambda spinner, text: load_elements(text))
        
        # Add scrollable content to scroll view
        scroll_view.add_widget(content_layout)
        
        # Main layout with scroll view and buttons
        main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        main_layout.add_widget(scroll_view)
        
        # Buttons at the bottom (not scrollable)
        buttons_layout = BoxLayout(size_hint_y=None, height=50, spacing=10)
        
        def save_maintenance():
            # Validate at least one element selected
            selected_elements = [(eid, widgets) for eid, widgets in element_widgets.items() 
                                if widgets['checkbox'].active]
            
            if not selected_elements:
                show_message_popup('Σφάλμα', 'Πρέπει να επιλέξετε τουλάχιστον ένα στοιχείο!')
                return
            
            if not datetime_input.text.strip():
                show_message_popup('Σφάλμα', 'Η ημερομηνία είναι υποχρεωτική!')
                return
            
            # Insert maintenance record with type
            substation_id = substation_map[substation_spinner.text]
            maintenance_date = datetime_input.text.strip()
            maintenance_type = maintenance_type_spinner.text
            c.execute(
                "INSERT INTO maintenance (substation_id, date_time, overall_comments, maintenance_type) VALUES (?, ?, ?, ?)",
                (substation_id, maintenance_date, overall_comments.text.strip(), maintenance_type)
            )
            maintenance_id = c.lastrowid
            
            # Insert maintenance elements and update their maintenance_date
            for elem_id, widgets in selected_elements:
                # Prepare measurement values
                measurements = widgets['measurements']
                
                if measurements:  # Circuit breaker with measurements
                    # Helper to parse float or None
                    def parse_float(val):
                        try:
                            return float(val.strip()) if val.strip() else None
                        except:
                            return None
                    
                    c.execute(
                        """INSERT INTO maintenance_elements 
                        (maintenance_id, element_id, element_comments,
                         insulation_closed_fa_ground, insulation_closed_fa_unit,
                         insulation_closed_fb_ground, insulation_closed_fb_unit,
                         insulation_closed_fc_ground, insulation_closed_fc_unit,
                         insulation_open_fa_fa, insulation_open_fa_unit,
                         insulation_open_fb_fb, insulation_open_fb_unit,
                         insulation_open_fc_fc, insulation_open_fc_unit,
                         contact_resistance_fa_fa, contact_resistance_fb_fb, contact_resistance_fc_fc)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (maintenance_id, elem_id, widgets['comments'].text.strip(),
                         parse_float(measurements['ins_closed_fa'].text), measurements['ins_closed_fa_unit'].text,
                         parse_float(measurements['ins_closed_fb'].text), measurements['ins_closed_fb_unit'].text,
                         parse_float(measurements['ins_closed_fc'].text), measurements['ins_closed_fc_unit'].text,
                         parse_float(measurements['ins_open_fa'].text), measurements['ins_open_fa_unit'].text,
                         parse_float(measurements['ins_open_fb'].text), measurements['ins_open_fb_unit'].text,
                         parse_float(measurements['ins_open_fc'].text), measurements['ins_open_fc_unit'].text,
                         parse_float(measurements['cont_fa'].text),
                         parse_float(measurements['cont_fb'].text),
                         parse_float(measurements['cont_fc'].text))
                    )
                else:  # Other element types without measurements
                    c.execute(
                        "INSERT INTO maintenance_elements (maintenance_id, element_id, element_comments) VALUES (?, ?, ?)",
                        (maintenance_id, elem_id, widgets['comments'].text.strip())
                    )
                
                # Update element's maintenance_date
                c.execute(
                    "UPDATE elements SET maintenance_date=? WHERE id=?",
                    (maintenance_date, elem_id)
                )
            
            # Update substation's last maintenance date
            c.execute(
                "UPDATE substations SET last_maintenance=? WHERE id=?",
                (maintenance_date, substation_id)
            )
            
            self.conn.commit()
            popup.dismiss()
            show_message_popup('Επιτυχία', 'Η συντήρηση καταχωρήθηκε!')
        
        save_btn = Button(text='Αποθήκευση')
        save_btn.bind(on_press=lambda x: save_maintenance())
        buttons_layout.add_widget(save_btn)
        
        cancel_btn = Button(text='Ακύρωση')
        cancel_btn.bind(on_press=popup.dismiss)
        buttons_layout.add_widget(cancel_btn)
        
        main_layout.add_widget(buttons_layout)
        popup.content = main_layout
        popup.open()
    
    def show_maintenance_menu_for_substation(self, substation_id, substation_name, parent_popup=None):
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
            parent_popup=parent_popup
        )
    
    def show_maintenance_history(self, instance):
        """Show maintenance history"""
        c = self.conn.cursor()
        c.execute('''
            SELECT m.id, s.name, m.date_time, m.overall_comments
            FROM maintenance m
            JOIN substations s ON m.substation_id = s.id
            ORDER BY m.date_time DESC
        ''')
        maintenance_records = c.fetchall()
        
        if not maintenance_records:
            show_message_popup('Πληροφορία', 'Δεν υπάρχουν καταχωρημένες συντηρήσεις')
            return
        
        popup = Popup(title='Ιστορικό Συντήρησης', size_hint=(0.95, 0.9))
        main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        scroll = ScrollView(bar_width=10, scroll_type=['bars', 'content'])
        grid = GridLayout(cols=1, spacing=10, size_hint_y=None, padding=10)
        grid.bind(minimum_height=grid.setter('height'))
        
        for maint_id, sub_name, date_time, overall_comments in maintenance_records:
            # Maintenance card
            card = BoxLayout(orientation='vertical', size_hint_y=None, padding=5, spacing=5)
            
            # Calculate card height as we build
            card_height = 0
            
            # Header
            header = BoxLayout(size_hint_y=None, height=40, spacing=5)
            header.add_widget(Label(
                text=f'Υποσταθμός: {sub_name}',
                bold=True,
                size_hint_x=0.6
            ))
            header.add_widget(Label(
                text=f'Ημ/νία: {date_time}',
                size_hint_x=0.4
            ))
            card.add_widget(header)
            card_height += 40
            
            # Overall comments
            if overall_comments:
                comment_label = Label(
                    text=f'Σχόλια: {overall_comments}',
                    size_hint_y=None,
                    height=30
                )
                card.add_widget(comment_label)
                card_height += 30
            
            # Get elements for this maintenance
            c.execute('''
                SELECT e.element_type, e.name, e.serial_number, me.element_comments
                FROM maintenance_elements me
                JOIN elements e ON me.element_id = e.id
                WHERE me.maintenance_id = ?
            ''', (maint_id,))
            elements = c.fetchall()
            
            # Elements list
            elements_label = Label(
                text='Στοιχεία που συντηρήθηκαν:',
                size_hint_y=None,
                height=25,
                bold=True
            )
            card.add_widget(elements_label)
            card_height += 25
            
            for elem_type, elem_name, serial_num, elem_comments in elements:
                elem_text = f'  • {elem_type}: {elem_name} (S/N: {serial_num or "-"})'
                if elem_comments:
                    elem_text += f'\n    Σχόλια: {elem_comments}'
                
                elem_height = 40 if elem_comments else 25
                elem_label = Label(
                    text=elem_text,
                    size_hint_y=None,
                    height=elem_height
                )
                card.add_widget(elem_label)
                card_height += elem_height
            
            # Delete button
            delete_btn = Button(
                text='Διαγραφή Συντήρησης',
                size_hint_y=None,
                height=35
            )
            # Use a proper function to avoid lambda issues
            def make_delete_handler(m_id, p):
                return lambda x: self.delete_maintenance(m_id, p)
            
            delete_btn.bind(on_press=make_delete_handler(maint_id, popup))
            card.add_widget(delete_btn)
            card_height += 35
            
            # Add spacing at bottom
            card_height += 10
            
            # Set final card height
            card.height = card_height
            
            grid.add_widget(card)
        
        scroll.add_widget(grid)
        main_layout.add_widget(scroll)
        
        # Close button
        close_btn = Button(text='Κλείσιμο', size_hint_y=0.1)
        close_btn.bind(on_press=popup.dismiss)
        main_layout.add_widget(close_btn)
        
        popup.content = main_layout
        popup.open()
    
    def show_substation_maintenance_history(self, substation_id, substation_name, parent_display_popup=None):
        """Show maintenance history for a specific substation"""
        c = self.conn.cursor()
        c.execute('''
            SELECT m.id, m.date_time, m.overall_comments
            FROM maintenance m
            WHERE m.substation_id = ?
            ORDER BY m.date_time DESC
        ''', (substation_id,))
        maintenance_records = c.fetchall()
        
        popup = Popup(title=f'Ιστορικό Συντήρησης: {substation_name}', size_hint=(0.95, 0.9))
        main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Add Maintenance button at the top
        add_maint_btn = Button(text='+ Προσθήκη Νέας Συντήρησης', size_hint_y=0.1)
        add_maint_btn.bind(on_press=lambda x: self.show_maintenance_menu_for_substation(substation_id, substation_name, popup))
        main_layout.add_widget(add_maint_btn)
        
        if not maintenance_records:
            # Show message but still allow adding maintenance
            no_records_label = Label(
                text=f'Δεν υπάρχουν καταχωρημένες συντηρήσεις για τον υποσταθμό "{substation_name}".\nΧρησιμοποιήστε το κουμπί παραπάνω για να προσθέσετε.',
                size_hint_y=0.7
            )
            main_layout.add_widget(no_records_label)
        else:
            scroll = ScrollView(bar_width=10, scroll_type=['bars', 'content'])
            grid = GridLayout(cols=1, spacing=10, size_hint_y=None, padding=10)
            grid.bind(minimum_height=grid.setter('height'))
        
        for maint_id, date_time, overall_comments in maintenance_records:
            # Maintenance card
            card = BoxLayout(orientation='vertical', size_hint_y=None, padding=5, spacing=5)
            
            # Calculate card height as we build
            card_height = 0
            
            # Header
            header = BoxLayout(size_hint_y=None, height=40, spacing=5)
            header.add_widget(Label(
                text=f'Ημερομηνία: {date_time}',
                bold=True,
                size_hint_x=1.0
            ))
            card.add_widget(header)
            card_height += 40
            
            # Overall comments
            if overall_comments:
                comment_label = Label(
                    text=f'Σχόλια: {overall_comments}',
                    size_hint_y=None,
                    height=30
                )
                card.add_widget(comment_label)
                card_height += 30
            
            # Get elements for this maintenance
            c.execute('''
                SELECT e.element_type, e.name, e.serial_number, me.element_comments
                FROM maintenance_elements me
                JOIN elements e ON me.element_id = e.id
                WHERE me.maintenance_id = ?
            ''', (maint_id,))
            elements = c.fetchall()
            
            # Elements list
            elements_label = Label(
                text='Στοιχεία που συντηρήθηκαν:',
                size_hint_y=None,
                height=25,
                bold=True
            )
            card.add_widget(elements_label)
            card_height += 25
            
            for elem_type, elem_name, serial_num, elem_comments in elements:
                elem_text = f'  • {elem_type}: {elem_name} (S/N: {serial_num or "-"})'
                if elem_comments:
                    elem_text += f'\n    Σχόλια: {elem_comments}'
                
                elem_height = 40 if elem_comments else 25
                elem_label = Label(
                    text=elem_text,
                    size_hint_y=None,
                    height=elem_height
                )
                card.add_widget(elem_label)
                card_height += elem_height
            
            # Delete button
            delete_btn = Button(
                text='Διαγραφή Συντήρησης',
                size_hint_y=None,
                height=35
            )
            # Use a proper function to avoid lambda issues
            def make_delete_handler(m_id, p):
                return lambda x: self.delete_maintenance_for_substation(m_id, p, substation_id, substation_name, parent_display_popup)
            
            delete_btn.bind(on_press=make_delete_handler(maint_id, popup))
            card.add_widget(delete_btn)
            card_height += 35
            
            # Add spacing at bottom
            card_height += 10
            
            # Set final card height
            card.height = card_height
            
            grid.add_widget(card)
        
            scroll.add_widget(grid)
            main_layout.add_widget(scroll)
        
        # Close button
        close_btn = Button(text='Κλείσιμο', size_hint_y=0.1)
        close_btn.bind(on_press=popup.dismiss)
        main_layout.add_widget(close_btn)
        
        popup.content = main_layout
        popup.open()
    
    def delete_maintenance(self, maintenance_id, parent_popup):
        """Delete a maintenance record and update related last maintenance dates"""
        c = self.conn.cursor()
        
        # Get substation_id and affected elements before deletion
        c.execute("SELECT substation_id FROM maintenance WHERE id=?", (maintenance_id,))
        result = c.fetchone()
        if not result:
            show_message_popup('Σφάλμα', 'Η συντήρηση δεν βρέθηκε!')
            return
        substation_id = result[0]
        
        c.execute("SELECT element_id FROM maintenance_elements WHERE maintenance_id=?", (maintenance_id,))
        affected_elements = [row[0] for row in c.fetchall()]
        
        # Explicitly delete maintenance_elements records first
        c.execute("DELETE FROM maintenance_elements WHERE maintenance_id=?", (maintenance_id,))
        
        # Delete the maintenance record
        c.execute("DELETE FROM maintenance WHERE id=?", (maintenance_id,))
        
        # Update last maintenance date for each affected element
        for element_id in affected_elements:
            c.execute("""
                SELECT m.date_time 
                FROM maintenance m
                JOIN maintenance_elements me ON m.id = me.maintenance_id
                WHERE me.element_id = ?
                ORDER BY m.date_time DESC
                LIMIT 1
            """, (element_id,))
            result = c.fetchone()
            new_date = result[0] if result else ''
            c.execute("UPDATE elements SET maintenance_date=? WHERE id=?", (new_date, element_id))
        
        # Update last maintenance date for the substation
        c.execute("""
            SELECT MAX(date_time) 
            FROM maintenance 
            WHERE substation_id=?
        """, (substation_id,))
        result = c.fetchone()
        new_sub_date = result[0] if result and result[0] else ''
        c.execute("UPDATE substations SET last_maintenance=? WHERE id=?", (new_sub_date, substation_id))
        
        self.conn.commit()
        parent_popup.dismiss()
        
        # Refresh both maintenance history and main records view
        def on_close():
            self.show_maintenance_history(None)
            self.show_records(None)
        
        show_message_popup('Ολοκληρώθηκε', 'Η συντήρηση διαγράφηκε!', callback=on_close)
    
    def delete_maintenance_for_substation(self, maintenance_id, parent_popup, substation_id, substation_name, parent_display_popup=None):
        """Delete a maintenance record, update last maintenance dates, and refresh substation-specific view"""
        c = self.conn.cursor()
        
        # Get affected elements before deletion
        c.execute("SELECT element_id FROM maintenance_elements WHERE maintenance_id=?", (maintenance_id,))
        affected_elements = [row[0] for row in c.fetchall()]
        
        # Explicitly delete maintenance_elements records first
        c.execute("DELETE FROM maintenance_elements WHERE maintenance_id=?", (maintenance_id,))
        
        # Delete the maintenance record
        c.execute("DELETE FROM maintenance WHERE id=?", (maintenance_id,))
        
        # Update last maintenance date for each affected element
        for element_id in affected_elements:
            c.execute("""
                SELECT m.date_time 
                FROM maintenance m
                JOIN maintenance_elements me ON m.id = me.maintenance_id
                WHERE me.element_id = ?
                ORDER BY m.date_time DESC
                LIMIT 1
            """, (element_id,))
            result = c.fetchone()
            new_date = result[0] if result else None
            c.execute("UPDATE elements SET maintenance_date=? WHERE id=?", (new_date, element_id))
        
        # Update last maintenance date for the substation
        c.execute("""
            SELECT MAX(date_time) 
            FROM maintenance 
            WHERE substation_id=?
        """, (substation_id,))
        result = c.fetchone()
        new_sub_date = result[0] if (result and result[0] is not None) else None
        c.execute("UPDATE substations SET last_maintenance=? WHERE id=?", (new_sub_date, substation_id))
        
        self.conn.commit()
        
        # Close both popups - maintenance history and parent display
        parent_popup.dismiss()
        if parent_display_popup:
            parent_display_popup.dismiss()
    
    def show_models_management(self, instance):
        """Show model management interface"""
        show_models_management(self)

SubstationApp().run()