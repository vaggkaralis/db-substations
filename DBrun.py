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
import webbrowser
import os
from datetime import datetime

from database import init_db
from importers import (
    import_elements_from_csv,
    import_elements_from_excel,
    import_substations_from_csv,
    import_substations_from_excel,
)
from popups import show_message_popup
from templates import create_elements_template, create_substations_template

class SubstationApp(App):
    # Define element types as a class variable
    ELEMENT_TYPES = ['Διακόπτης Ισχύος', 'Μετασχηματιστής', 'Motor Drive']
    VOLTAGE_LEVELS = ['20 KV', '150 KV', '20/150 KV']
    # Central definition of element fields for easy future extension
    ELEMENT_FIELD_DEFS = [
        {'key': 'name', 'label': 'Όνομα Στοιχείου', 'type': 'text', 'hint': 'Όνομα Στοιχείου'},
        {'key': 'serial_number', 'label': 'Σειριακός Αριθμός', 'type': 'text', 'hint': 'Σειριακός Αριθμός'},
        {'key': 'maintenance_date', 'label': 'Ημερομηνία τελευταίας συντήρησης', 'type': 'text', 'hint': 'YYYY-MM-DD'},
        {'key': 'voltage_level', 'label': 'Επίπεδο Τάσης', 'type': 'spinner', 'values': VOLTAGE_LEVELS},
        {'key': 'manufacturer', 'label': 'Κατασκευαστής', 'type': 'text', 'hint': 'Κατασκευαστής'},
        {'key': 'type', 'label': 'Τύπος', 'type': 'text', 'hint': 'Τύπος'},
    ]
    
    def build(self):
        self.title = 'Υποσταθμοί ΔΕΔΔΗΕ ΔΕΕΔ/ΚΣΜΘ/ΤΕΙ'
        layout = BoxLayout(orientation='vertical')
        self.show_btn = Button(text='Εμφάνιση βάσης υποσταθμών')
        self.show_btn.bind(on_press=self.show_records)
        self.import_btn = Button(text='Εισαγωγή υποσταθμών και στοιχείων από αρχείο')
        self.import_btn.bind(on_press=self.show_import_menu)
        self.add_btn = Button(text='Προσθήκη υποσταθμών και στοιχείων')
        self.add_btn.bind(on_press=self.show_add_menu)
        self.maintenance_btn = Button(text='Καταχώρηση Συντήρησης')
        self.maintenance_btn.bind(on_press=self.show_maintenance_menu)
        self.view_maintenance_btn = Button(text='Προβολή Ιστορικού Συντήρησης')
        self.view_maintenance_btn.bind(on_press=self.show_maintenance_history)
        self.delete_btn = Button(text='Διαγραφή όλων')
        self.delete_btn.bind(on_press=self.delete_all)
        layout.add_widget(self.show_btn)
        layout.add_widget(self.import_btn)
        layout.add_widget(self.add_btn)
        layout.add_widget(self.maintenance_btn)
        layout.add_widget(self.view_maintenance_btn)
        layout.add_widget(self.delete_btn)
        self.conn = init_db()
        return layout

    def show_import_menu(self, instance):
        # Show intermediate menu for importing substations or elements
        menu_popup = Popup(title='Εισαγωγή υποσταθμών και στοιχείων από αρχείο', size_hint=(0.6, 0.4))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        layout.add_widget(Label(text='Επιλέξτε τι θέλετε να εισάγετε:', size_hint_y=0.3))
        
        # Import substations button
        import_substations_btn = Button(text='Εισαγωγή Υποσταθμών από Αρχείο', size_hint_y=0.3)
        import_substations_btn.bind(on_press=lambda x: self._show_import_substations_from_menu(menu_popup))
        layout.add_widget(import_substations_btn)
        
        # Import elements button
        import_elements_btn = Button(text='Εισαγωγή Στοιχείων από Αρχείο', size_hint_y=0.3)
        import_elements_btn.bind(on_press=lambda x: self._show_import_elements_from_menu(menu_popup))
        layout.add_widget(import_elements_btn)
        
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
        popup = Popup(title='Προσθήκη Νέου Υποσταθμού', size_hint=(0.8, 0.4))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Name input
        name_input = TextInput(
            hint_text='Όνομα Υποσταθμού',
            size_hint_y=0.3,
            multiline=False
        )
        layout.add_widget(Label(text='Όνομα Υποσταθμού:', size_hint_y=0.2))
        layout.add_widget(name_input)
        
        # Buttons layout
        buttons_layout = BoxLayout(size_hint_y=0.3, spacing=10)
        
        def add_substation():
            if not name_input.text:
                show_message_popup('Σφάλμα', 'Παρακαλώ εισάγετε όνομα υποσταθμού!')
                return
            
            c = self.conn.cursor()
            c.execute("INSERT INTO substations (name, location, adoption_date) VALUES (?, ?, ?)", (name_input.text, '', ''))
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

    def show_records(self, instance):
        # Show intermediate selection dialog
        c = self.conn.cursor()
        c.execute("SELECT id, name FROM substations ORDER BY name")
        all_substations = c.fetchall()
        
        if not all_substations:
            show_message_popup('Σφάλμα', 'Δεν υπάρχουν υποσταθμοί στη βάση!')
            return
        
        # Create selection popup
        selection_popup = Popup(title='Επιλογή Προβολής', size_hint=(0.6, 0.5))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        layout.add_widget(Label(text='Επιλέξτε τι θέλετε να δείτε:', size_hint_y=0.2))
        
        # "Show All" button
        show_all_btn = Button(text='Εμφάνιση Όλων των Υποσταθμών', size_hint_y=0.25)
        show_all_btn.bind(on_press=lambda x: self._show_all_substations(selection_popup))
        layout.add_widget(show_all_btn)
        
        # Dropdown for specific substation
        layout.add_widget(Label(text='Ή επιλέξτε συγκεκριμένο υποσταθμό:', size_hint_y=0.15))
        
        substation_names = [name for _, name in all_substations]
        substation_spinner = Spinner(
            text=substation_names[0],
            values=substation_names,
            size_hint_y=0.2
        )
        layout.add_widget(substation_spinner)
        
        show_specific_btn = Button(text='Εμφάνιση Επιλεγμένου', size_hint_y=0.25)
        show_specific_btn.bind(on_press=lambda x: self._show_specific_substation(substation_spinner.text, selection_popup))
        layout.add_widget(show_specific_btn)
        
        # Cancel button
        cancel_btn = Button(text='Ακύρωση', size_hint_y=0.2)
        cancel_btn.bind(on_press=selection_popup.dismiss)
        layout.add_widget(cancel_btn)
        
        selection_popup.content = layout
        selection_popup.open()
    
    def _show_all_substations(self, selection_popup):
        selection_popup.dismiss()
        self._display_substations(None)
    
    def _show_specific_substation(self, substation_name, selection_popup):
        selection_popup.dismiss()
        self._display_substations(substation_name)
    
    def _display_substations(self, filter_name=None):
        c = self.conn.cursor()
        if filter_name:
            c.execute("SELECT id, name, location, adoption_date FROM substations WHERE name=?", (filter_name,))
            title = f'Υποσταθμός: {filter_name}'
        else:
            c.execute("SELECT id, name, location, adoption_date FROM substations")
            title = 'Εγγραφές Υποσταθμών'
        
        substations = c.fetchall()
        
        # Create popup window
        popup = Popup(title=title, size_hint=(0.95, 0.9))
        
        # Create main layout
        main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Create scrollable grid for records
        scroll = ScrollView()
        grid = GridLayout(cols=1, spacing=5, size_hint_y=None)
        grid.bind(minimum_height=grid.setter('height'))
        
        if substations:
            for sub_id, sub_name, location, adoption_date in substations:
                # Add header for each substation
                header_layout = BoxLayout(size_hint_y=None, height=35, spacing=5)
                header_layout.add_widget(Label(text='Όνομα', bold=True, size_hint_x=0.2))
                header_layout.add_widget(Label(text='Τοποθεσία', bold=True, size_hint_x=0.25))
                header_layout.add_widget(Label(text='Ανάληψη', bold=True, size_hint_x=0.15))
                header_layout.add_widget(Label(text='Στοιχεία', bold=True, size_hint_x=0.1))
                header_layout.add_widget(Label(text='Συντηρήσεις', bold=True, size_hint_x=0.15))
                header_layout.add_widget(Label(text='Τελευταία', bold=True, size_hint_x=0.15))
                grid.add_widget(header_layout)
                
                # Count elements for this substation
                c.execute("SELECT COUNT(*) FROM elements WHERE substation_id=?", (sub_id,))
                elem_count = c.fetchone()[0]
                
                # Get maintenance statistics
                c.execute("SELECT COUNT(*) FROM maintenance WHERE substation_id=?", (sub_id,))
                maint_count = c.fetchone()[0]
                
                c.execute("SELECT MAX(date_time) FROM maintenance WHERE substation_id=?", (sub_id,))
                last_maint = c.fetchone()[0]
                last_maint_display = last_maint if last_maint else '-'
                
                # Substation row
                sub_row_layout = BoxLayout(size_hint_y=None, height=40, spacing=5)
                sub_row_layout.add_widget(Label(text=sub_name, size_hint_x=0.2))
                
                # Location button (clickable)
                if location:
                    # Shorten location text to fit
                    if len(location) > 25:
                        location_display = location[:22] + '...'
                    else:
                        location_display = location
                    
                    location_btn = Button(
                        text=location_display, 
                        size_hint_x=0.25,
                        font_size='11sp',
                        padding=(5, 5)
                    )
                    # Bind text_size to button size for proper text wrapping
                    location_btn.bind(size=lambda btn, size: setattr(btn, 'text_size', size))
                    location_btn.bind(on_press=lambda x, url=location: webbrowser.open(url))
                    sub_row_layout.add_widget(location_btn)
                else:
                    sub_row_layout.add_widget(Label(text='-', size_hint_x=0.25))
                
                sub_row_layout.add_widget(Label(text=adoption_date or '-', size_hint_x=0.15))
                sub_row_layout.add_widget(Label(text=str(elem_count), size_hint_x=0.1))
                sub_row_layout.add_widget(Label(text=str(maint_count), size_hint_x=0.15))
                sub_row_layout.add_widget(Label(text=last_maint_display, size_hint_x=0.15))
                grid.add_widget(sub_row_layout)
                
                # Edit and Delete buttons
                buttons_layout = BoxLayout(size_hint_y=None, height=35, spacing=5)
                
                edit_btn = Button(text='Επεξεργασία', size_hint_x=0.5)
                edit_btn.bind(on_press=lambda x, sid=sub_id, sname=sub_name, loc=location, adate=adoption_date, p=popup: self.show_edit_substation_popup(sid, sname, loc, adate, p))
                buttons_layout.add_widget(edit_btn)
                
                delete_sub_btn = Button(text='Διαγραφή', size_hint_x=0.5)
                delete_sub_btn.bind(on_press=lambda x, sid=sub_id, p=popup: self.delete_substation(sid, p))
                buttons_layout.add_widget(delete_sub_btn)
                
                grid.add_widget(buttons_layout)
                
                # Elements section
                c.execute("SELECT id, element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, type FROM elements WHERE substation_id=?", (sub_id,))
                elements = c.fetchall()
                
                if elements:
                    for j, (elem_id, elem_type, elem_name, serial_number, maintenance_date, voltage_level, manufacturer, elem_type_field) in enumerate(elements, 1):
                        # Create element text with multiple lines for better readability
                        elem_text = f"   {j}. {elem_type}: {elem_name}\n      S/N: {serial_number} | Date: {maintenance_date or '-'} | Voltage: {voltage_level}\n      Manufacturer: {manufacturer or '-'} | Type: {elem_type_field or '-'}"
                        
                        # Create a horizontal layout for element and delete button
                        elem_layout = BoxLayout(size_hint_y=None, height=70, spacing=5)
                        
                        elem_label = Label(
                            text=elem_text,
                            size_hint_x=0.8
                        )
                        elem_layout.add_widget(elem_label)
                        
                        delete_elem_btn = Button(
                            text="X",
                            size_hint_x=0.2
                        )
                        delete_elem_btn.bind(on_press=lambda x, eid=elem_id, sid=sub_id, p=popup: self.delete_element(eid, sid, p))
                        elem_layout.add_widget(delete_elem_btn)
                        
                        grid.add_widget(elem_layout)
                else:
                    no_elem_label = Label(
                        text="   (Χωρίς στοιχεία)",
                        size_hint_y=None,
                        height=30
                    )
                    grid.add_widget(no_elem_label)
                
                # Add element button for this substation
                add_elem_btn = Button(
                    text=f"   + Προσθήκη Στοιχείου",
                    size_hint_y=None,
                    height=35
                )
                add_elem_btn.bind(on_press=lambda x, sid=sub_id, sname=sub_name, p=popup: self.show_add_element_popup_for_substation(sid, sname, p))
                grid.add_widget(add_elem_btn)
        else:
            empty_label = Label(
                text='Κενή βάση',
                size_hint_y=None,
                height=40
            )
            grid.add_widget(empty_label)
        
        scroll.add_widget(grid)
        main_layout.add_widget(scroll)
        
        # Add close button
        close_btn = Button(text='Κλείσιμο', size_hint_y=0.1)
        close_btn.bind(on_press=popup.dismiss)
        main_layout.add_widget(close_btn)
        
        popup.content = main_layout
        popup.open()

    def delete_all(self, instance):
        c = self.conn.cursor()
        c.execute("DELETE FROM substations")
        self.conn.commit()
        show_message_popup('Ολοκληρώθηκε', 'Όλες οι εγγραφές διαγράφηκαν!', callback=lambda: self.show_records(None))
    
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
        # Step 1: detect duplicates
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
        scroll = ScrollView()
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

    def delete_element(self, element_id, substation_id, parent_popup):
        c = self.conn.cursor()
        c.execute("DELETE FROM elements WHERE id=?", (element_id,))
        self.conn.commit()
        parent_popup.dismiss()
        show_message_popup('Ολοκληρώθηκε', 'Το στοιχείο διαγράφηκε!', callback=lambda: self.show_records(None))

    def delete_substation(self, substation_id, parent_popup):
        c = self.conn.cursor()
        # Delete all elements for this substation first
        c.execute("DELETE FROM elements WHERE substation_id=?", (substation_id,))
        # Then delete the substation
        c.execute("DELETE FROM substations WHERE id=?", (substation_id,))
        self.conn.commit()
        parent_popup.dismiss()
        show_message_popup('Ολοκληρώθηκε', 'Ο υποσταθμός και όλα τα στοιχεία του διαγράφηκαν!', callback=lambda: self.show_records(None))
    
    def show_edit_substation_popup(self, substation_id, substation_name, location, adoption_date, parent_popup):
        # Create popup
        popup = Popup(title=f'Επεξεργασία Υποσταθμού: {substation_name}', size_hint=(0.8, 0.6))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Location input
        location_input = TextInput(
            text=location or '',
            hint_text='Τοποθεσία (Google Maps link)',
            size_hint_y=0.2,
            multiline=False
        )
        layout.add_widget(Label(text='Τοποθεσία:', size_hint_y=0.1))
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
            c.execute("UPDATE substations SET location=?, adoption_date=? WHERE id=?", 
                     (location_input.text, date_input.text, substation_id))
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
        c.execute("SELECT id, name FROM substations")
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
        scroll = ScrollView()
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
        
        # Dynamic element fields
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
            if 'voltage_level' in values and hasattr(field_inputs['voltage_level'], 'text'):
                values['voltage_level'] = field_inputs['voltage_level'].text

            c = self.conn.cursor()
            c.execute(
                "INSERT INTO elements (substation_id, element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    substation_id,
                    element_type,
                    values.get('name', ''),
                    values.get('serial_number', ''),
                    values.get('maintenance_date', ''),
                    values.get('voltage_level', ''),
                    values.get('manufacturer', ''),
                    values.get('type', ''),
                ),
            )
            self.conn.commit()
            popup.dismiss()
            show_message_popup('Επιτυχία', f'Στοιχείο προστέθηκε στον {substation_name}!', callback=lambda: self.show_records(None))
        
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
        popup = Popup(title=f'Προσθήκη Στοιχείου για {substation_name}', size_hint=(0.8, 0.9))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Create scrollable area for inputs
        scroll = ScrollView()
        input_layout = BoxLayout(orientation='vertical', size_hint_y=None, padding=10, spacing=10)
        input_layout.bind(minimum_height=input_layout.setter('height'))
        
        # Element type spinner
        element_spinner = Spinner(
            text=self.ELEMENT_TYPES[0],
            values=self.ELEMENT_TYPES,
            size_hint_y=None,
            height=40
        )
        input_layout.add_widget(Label(text='Επιλέξτε Τύπο Στοιχείου:', size_hint_y=None, height=30))
        input_layout.add_widget(element_spinner)

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
            if 'voltage_level' in values and hasattr(field_inputs['voltage_level'], 'text'):
                values['voltage_level'] = field_inputs['voltage_level'].text

            if not values.get('name'):
                show_message_popup('Σφάλμα', 'Παρακαλώ εισάγετε όνομα στοιχείου!')
                return
            
            c = self.conn.cursor()
            c.execute("INSERT INTO elements (substation_id, element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                     (
                        substation_id,
                        element_type,
                        values.get('name', ''),
                        values.get('serial_number', ''),
                        values.get('maintenance_date', ''),
                        values.get('voltage_level', ''),
                        values.get('manufacturer', ''),
                        values.get('type', ''),
                     ))
            self.conn.commit()
            popup.dismiss()
            parent_popup.dismiss()
            show_message_popup('Επιτυχία', 'Στοιχείο προστέθηκε!', callback=lambda: self.show_records(None))
        
        add_btn = Button(text='Προσθήκη')
        add_btn.bind(on_press=lambda x: add_element())
        buttons_layout.add_widget(add_btn)
        
        cancel_btn = Button(text='Ακύρωση')
        cancel_btn.bind(on_press=popup.dismiss)
        buttons_layout.add_widget(cancel_btn)
        
        layout.add_widget(buttons_layout)
        popup.content = layout
        popup.open()

    def show_maintenance_menu(self, instance):
        """Show maintenance recording dialog"""
        # Get list of substations
        c = self.conn.cursor()
        c.execute("SELECT id, name FROM substations ORDER BY name")
        substations = c.fetchall()
        
        if not substations:
            show_message_popup('Σφάλμα', 'Δεν υπάρχουν υποσταθμοί!')
            return
        
        popup = Popup(title='Καταχώρηση Συντήρησης', size_hint=(0.9, 0.95))
        main_layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Substation selection
        main_layout.add_widget(Label(text='Επιλογή Υποσταθμού:', size_hint_y=0.08))
        substation_map = {s[1]: s[0] for s in substations}
        substation_spinner = Spinner(
            text=substations[0][1],
            values=[s[1] for s in substations],
            size_hint_y=0.08
        )
        main_layout.add_widget(substation_spinner)
        
        # Date/Time (auto-filled with current)
        from datetime import datetime
        main_layout.add_widget(Label(text='Ημερομηνία & Ώρα:', size_hint_y=0.08))
        datetime_input = TextInput(
            text=datetime.now().strftime('%Y-%m-%d %H:%M'),
            hint_text='YYYY-MM-DD HH:MM',
            size_hint_y=0.08,
            multiline=False
        )
        main_layout.add_widget(datetime_input)
        
        # Overall comments
        main_layout.add_widget(Label(text='Γενικά Σχόλια Συντήρησης:', size_hint_y=0.08))
        overall_comments = TextInput(
            hint_text='Γενικά σχόλια για την συντήρηση...',
            size_hint_y=0.15,
            multiline=True
        )
        main_layout.add_widget(overall_comments)
        
        # Elements selection area
        main_layout.add_widget(Label(text='Στοιχεία που συντηρήθηκαν (τουλάχιστον 1):', size_hint_y=0.08))
        
        # Container for element checkboxes
        elements_scroll = ScrollView(size_hint_y=0.3)
        elements_container = GridLayout(cols=1, spacing=5, size_hint_y=None, padding=5)
        elements_container.bind(minimum_height=elements_container.setter('height'))
        elements_scroll.add_widget(elements_container)
        main_layout.add_widget(elements_scroll)
        
        # Dictionary to store element widgets
        element_widgets = {}
        
        def load_elements(substation_name):
            """Load elements for selected substation"""
            elements_container.clear_widgets()
            element_widgets.clear()
            
            substation_id = substation_map[substation_name]
            c.execute("SELECT id, element_type, name, serial_number FROM elements WHERE substation_id=? ORDER BY name", (substation_id,))
            elements = c.fetchall()
            
            if not elements:
                elements_container.add_widget(Label(
                    text='Δεν υπάρχουν στοιχεία σε αυτόν τον υποσταθμό',
                    size_hint_y=None,
                    height=40
                ))
                return
            
            for elem_id, elem_type, elem_name, serial_number in elements:
                # Element row
                elem_box = BoxLayout(size_hint_y=None, height=80, spacing=5, orientation='vertical')
                
                # Checkbox and name
                checkbox_layout = BoxLayout(size_hint_y=None, height=40, spacing=5)
                checkbox = CheckBox(size_hint_x=0.1)
                checkbox_layout.add_widget(checkbox)
                
                elem_label = Label(
                    text=f'{elem_type}: {elem_name}\n S/N: {serial_number or "-"}',
                    size_hint_x=0.9
                )
                checkbox_layout.add_widget(elem_label)
                elem_box.add_widget(checkbox_layout)
                
                # Comments for this element
                elem_comments = TextInput(
                    hint_text='Σχόλια για αυτό το στοιχείο...',
                    size_hint_y=None,
                    height=40,
                    multiline=False
                )
                elem_box.add_widget(elem_comments)
                
                elements_container.add_widget(elem_box)
                element_widgets[elem_id] = {'checkbox': checkbox, 'comments': elem_comments}
        
        # Load initial elements
        load_elements(substation_spinner.text)
        
        # Update elements when substation changes
        substation_spinner.bind(text=lambda spinner, text: load_elements(text))
        
        # Save button
        buttons_layout = BoxLayout(size_hint_y=0.1, spacing=10)
        
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
            
            # Insert maintenance record
            substation_id = substation_map[substation_spinner.text]
            c.execute(
                "INSERT INTO maintenance (substation_id, date_time, overall_comments) VALUES (?, ?, ?)",
                (substation_id, datetime_input.text.strip(), overall_comments.text.strip())
            )
            maintenance_id = c.lastrowid
            
            # Insert maintenance elements
            for elem_id, widgets in selected_elements:
                c.execute(
                    "INSERT INTO maintenance_elements (maintenance_id, element_id, element_comments) VALUES (?, ?, ?)",
                    (maintenance_id, elem_id, widgets['comments'].text.strip())
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
        
        scroll = ScrollView()
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
    
    def delete_maintenance(self, maintenance_id, parent_popup):
        """Delete a maintenance record"""
        c = self.conn.cursor()
        c.execute("DELETE FROM maintenance WHERE id=?", (maintenance_id,))
        self.conn.commit()
        parent_popup.dismiss()
        show_message_popup('Ολοκληρώθηκε', 'Η συντήρηση διαγράφηκε!', callback=lambda: self.show_maintenance_history(None))

SubstationApp().run()