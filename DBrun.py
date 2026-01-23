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
from kivy.uix.filechooser import FileChooserListView
import sqlite3
import webbrowser
import os
try:
    import pandas as pd
except ImportError:
    pd = None
try:
    import openpyxl
except ImportError:
    openpyxl = None

class SubstationApp(App):
    # Define element types as a class variable
    ELEMENT_TYPES = ['Διακόπτης Ισχύος', 'Μετασχηματιστής', 'Motor Drive']
    VOLTAGE_LEVELS = ['20 KV', '150 KV', '20/150 KV']
    
    def build(self):
        layout = BoxLayout(orientation='vertical')
        self.submit_btn = Button(text='Προσθήκη Υποσταθμού')
        self.submit_btn.bind(on_press=self.show_add_substation_popup)
        self.show_btn = Button(text='Εμφάνιση')
        self.show_btn.bind(on_press=self.show_records)
        self.delete_btn = Button(text='Διαγραφή όλων')
        self.delete_btn.bind(on_press=self.delete_all)
        self.import_sub_btn = Button(text='Εισαγωγή Υποσταθμών')
        self.import_sub_btn.bind(on_press=self.show_import_substations_dialog)
        self.import_elem_btn = Button(text='Εισαγωγή Στοιχείων')
        self.import_elem_btn.bind(on_press=self.show_import_elements_dialog)
        self.output = Label(text='Καμία εγγραφή')
        layout.add_widget(self.submit_btn)
        layout.add_widget(self.show_btn)
        layout.add_widget(self.delete_btn)
        layout.add_widget(self.import_sub_btn)
        layout.add_widget(self.import_elem_btn)
        layout.add_widget(self.output)
        self.init_db()
        return layout

    def init_db(self):
        self.conn = sqlite3.connect('substations.db')
        c = self.conn.cursor()
        
        # Create tables with new schema
        c.execute('''CREATE TABLE IF NOT EXISTS substations (id INTEGER PRIMARY KEY, name TEXT, location TEXT, adoption_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS elements (id INTEGER PRIMARY KEY, substation_id INTEGER, element_type TEXT, name TEXT, serial_number TEXT, maintenance_date TEXT, voltage_level TEXT, manufacturer TEXT, type TEXT, FOREIGN KEY(substation_id) REFERENCES substations(id))''')
        
        # Check if substations table needs migration (has old schema without location/adoption_date)
        c.execute("PRAGMA table_info(substations)")
        columns = [column[1] for column in c.fetchall()]
        
        # If old schema without location column, add it
        if 'location' not in columns:
            try:
                c.execute("ALTER TABLE substations ADD COLUMN location TEXT DEFAULT ''")
            except:
                pass
        
        # If old schema without adoption_date column, add it
        if 'adoption_date' not in columns:
            try:
                c.execute("ALTER TABLE substations ADD COLUMN adoption_date TEXT DEFAULT ''")
            except:
                pass
        
        # Check if elements table needs migration
        c.execute("PRAGMA table_info(elements)")
        elem_columns = [column[1] for column in c.fetchall()]
        
        # If old schema without serial_number column, add it
        if elem_columns and 'serial_number' not in elem_columns:
            try:
                c.execute("ALTER TABLE elements ADD COLUMN serial_number TEXT DEFAULT ''")
            except:
                pass
        
        # If old schema without maintenance_date column, add it
        if elem_columns and 'maintenance_date' not in elem_columns:
            try:
                c.execute("ALTER TABLE elements ADD COLUMN maintenance_date TEXT DEFAULT ''")
            except:
                pass
        
        # If old schema without voltage_level column, add it
        if elem_columns and 'voltage_level' not in elem_columns:
            try:
                c.execute("ALTER TABLE elements ADD COLUMN voltage_level TEXT DEFAULT ''")
            except:
                pass
        
        # If old schema without manufacturer column, add it
        if elem_columns and 'manufacturer' not in elem_columns:
            try:
                c.execute("ALTER TABLE elements ADD COLUMN manufacturer TEXT DEFAULT ''")
            except:
                pass
        
        # If old schema without type column, add it
        if elem_columns and 'type' not in elem_columns:
            try:
                c.execute("ALTER TABLE elements ADD COLUMN type TEXT DEFAULT ''")
            except:
                pass
        
        self.conn.commit()

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
                self.output.text = 'Παρακαλώ εισάγετε όνομα υποσταθμού!'
                return
            
            c = self.conn.cursor()
            c.execute("INSERT INTO substations (name, location, adoption_date) VALUES (?, ?, ?)", (name_input.text, '', ''))
            self.conn.commit()
            self.output.text = 'Υποσταθμός προστέθηκε!'
            popup.dismiss()
            # Refresh display
            self.show_records(None)
        
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
        c = self.conn.cursor()
        c.execute("SELECT id, name, location, adoption_date FROM substations")
        substations = c.fetchall()
        
        # Create popup window
        popup = Popup(title='Εγγραφές Υποσταθμών', size_hint=(0.95, 0.9))
        
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
                header_layout.add_widget(Label(text='Όνομα', bold=True, size_hint_x=0.25))
                header_layout.add_widget(Label(text='Τοποθεσία', bold=True, size_hint_x=0.3))
                header_layout.add_widget(Label(text='Ανάληψη', bold=True, size_hint_x=0.2))
                header_layout.add_widget(Label(text='Στοιχεία', bold=True, size_hint_x=0.15))
                grid.add_widget(header_layout)
                
                # Count elements for this substation
                c.execute("SELECT COUNT(*) FROM elements WHERE substation_id=?", (sub_id,))
                elem_count = c.fetchone()[0]
                
                # Substation row
                sub_row_layout = BoxLayout(size_hint_y=None, height=40, spacing=5)
                sub_row_layout.add_widget(Label(text=sub_name, size_hint_x=0.25))
                
                # Location button (clickable)
                if location:
                    location_display = (location[:30] + '...') if len(location) > 30 else location
                    location_btn = Button(text=location_display, size_hint_x=0.3)
                    location_btn.bind(on_press=lambda x, url=location: webbrowser.open(url))
                    sub_row_layout.add_widget(location_btn)
                else:
                    sub_row_layout.add_widget(Label(text='-', size_hint_x=0.3))
                
                sub_row_layout.add_widget(Label(text=adoption_date or '-', size_hint_x=0.2))
                sub_row_layout.add_widget(Label(text=str(elem_count), size_hint_x=0.15))
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
        self.output.text = 'Όλες οι εγγραφές διαγράφηκαν!'
    
    def create_substations_template(self, instance):
        if openpyxl is None:
            self.output.text = 'openpyxl δεν είναι εγκατεστημένο!'
            return
        
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill
            
            wb = Workbook()
            ws = wb.active
            ws.title = 'Substations'
            
            # Substations sheet
            headers = ['Name', 'Location', 'Adoption Date']
            for col, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col, value=header)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
                cell.font = Font(bold=True, color='FFFFFF')
            
            ws.column_dimensions['A'].width = 30
            ws.column_dimensions['B'].width = 50
            ws.column_dimensions['C'].width = 15
            
            # Add example rows
            examples = [
                ('Υποσταθμός Α', 'https://maps.google.com/?q=example1', '2025-01-15'),
                ('Υποσταθμός Β', 'https://maps.google.com/?q=example2', '2025-01-20'),
            ]
            for idx, (name, location, date) in enumerate(examples, 2):
                ws.cell(row=idx, column=1, value=name)
                ws.cell(row=idx, column=2, value=location)
                ws.cell(row=idx, column=3, value=date)
            
            template_path = os.path.join(os.path.dirname(__file__), 'substations_import_template.xlsx')
            wb.save(template_path)
            self.output.text = f'Template Υποσταθμών δημιουργήθηκε: {template_path}'
        except Exception as e:
            self.output.text = f'Σφάλμα: {str(e)}'
    
    def create_elements_template(self, instance):
        if openpyxl is None:
            self.output.text = 'openpyxl δεν είναι εγκατεστημένο!'
            return
        
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill
            
            wb = Workbook()
            ws = wb.active
            ws.title = 'Elements'
            
            # Elements sheet
            headers = ['Substation Name', 'Element Type', 'Name', 'Serial Number', 'Maintenance Date', 'Voltage Level', 'Manufacturer', 'Type']
            for col, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col, value=header)
                cell.font = Font(bold=True, color='FFFFFF')
                cell.fill = PatternFill(start_color='70AD47', end_color='70AD47', fill_type='solid')
            
            ws.column_dimensions['A'].width = 30
            ws.column_dimensions['B'].width = 20
            ws.column_dimensions['C'].width = 20
            ws.column_dimensions['D'].width = 15
            ws.column_dimensions['E'].width = 15
            ws.column_dimensions['F'].width = 15
            ws.column_dimensions['G'].width = 20
            ws.column_dimensions['H'].width = 20
            
            # Add example rows
            examples = [
                ('Υποσταθμός Α', 'Διακόπτης Ισχύος', 'Main Breaker', 'SN-001', '2025-01-20', '150 KV', 'ABB', 'Type-X'),
                ('Υποσταθμός Α', 'Μετασχηματιστής', 'Transformer 1', 'SN-002', '2025-01-18', '20/150 KV', 'Siemens', 'Type-Y'),
            ]
            for idx, row_data in enumerate(examples, 2):
                for col, value in enumerate(row_data, 1):
                    ws.cell(row=idx, column=col, value=value)
            
            template_path = os.path.join(os.path.dirname(__file__), 'elements_import_template.xlsx')
            wb.save(template_path)
            self.output.text = f'Template Στοιχείων δημιουργήθηκε: {template_path}'
        except Exception as e:
            self.output.text = f'Σφάλμα: {str(e)}'
    
    def show_import_substations_dialog(self, instance):
        popup = Popup(title='Εισαγωγή Υποσταθμών', size_hint=(0.9, 0.9))
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
                self.output.text = 'Παρακαλώ εισάγετε διαδρομή ή επιλέξτε αρχείο!'
                return
            
            if not os.path.exists(file_path):
                self.output.text = 'Το αρχείο δεν βρέθηκε!'
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
        popup = Popup(title='Εισαγωγή Στοιχείων', size_hint=(0.9, 0.9))
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
                self.output.text = 'Παρακαλώ εισάγετε διαδρομή ή επιλέξτε αρχείο!'
                return
            
            if not os.path.exists(file_path):
                self.output.text = 'Το αρχείο δεν βρέθηκε!'
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
        try:
            if file_path.endswith('.xlsx'):
                self.import_substations_from_excel(file_path)
            elif file_path.endswith('.csv'):
                self.import_substations_from_csv(file_path)
        except Exception as e:
            self.output.text = f'Σφάλμα κατά την εισαγωγή: {str(e)}'
    
    def import_elements_from_file(self, file_path):
        try:
            if file_path.endswith('.xlsx'):
                self.import_elements_from_excel(file_path)
            elif file_path.endswith('.csv'):
                self.import_elements_from_csv(file_path)
        except Exception as e:
            self.output.text = f'Σφάλμα κατά την εισαγωγή: {str(e)}'
    
    def import_substations_from_excel(self, file_path):
        if pd is None:
            self.output.text = 'pandas δεν είναι εγκατεστημένο!'
            return
        
        try:
            c = self.conn.cursor()
            df_sub = pd.read_excel(file_path, sheet_name='Substations')
            count = 0
            duplicates = []
            
            for _, row in df_sub.iterrows():
                name = str(row.get('Name', '')).strip() if pd.notna(row.get('Name', '')) else ''
                location = str(row.get('Location', '')) if pd.notna(row.get('Location', '')) else ''
                adoption_date = str(row.get('Adoption Date', '')) if pd.notna(row.get('Adoption Date', '')) else ''
                
                if name and name.strip():
                    # Check if substation already exists
                    c.execute("SELECT id FROM substations WHERE name=?", (name,))
                    if c.fetchone():
                        duplicates.append(name)
                    else:
                        c.execute("INSERT INTO substations (name, location, adoption_date) VALUES (?, ?, ?)",
                                 (name, location, adoption_date))
                        count += 1
            
            self.conn.commit()
            
            if duplicates:
                dup_list = ', '.join(duplicates)
                msg = f'{count} νέοι υποσταθμοί εισήχθησαν.\nΥπάρχοντες (δεν εισήχθησαν): {dup_list}'
            else:
                msg = f'{count} υποσταθμοί εισήχθησαν με επιτυχία!'
            
            self.output.text = msg
            # Show popup with message, then refresh records
            self.show_message_popup('Εισαγωγή Υποσταθμών (Excel)', msg, callback=lambda: self.show_records(None))
        except Exception as e:
            error_msg = f'Σφάλμα: {str(e)}'
            self.output.text = error_msg
            self.show_message_popup('Σφάλμα', error_msg)
    
    def import_substations_from_csv(self, file_path):
        if pd is None:
            self.output.text = 'pandas δεν είναι εγκατεστημένο!'
            return
        
        try:
            c = self.conn.cursor()
            df_sub = pd.read_csv(file_path)
            count = 0
            duplicates = []
            
            for _, row in df_sub.iterrows():
                name = str(row.get('Name', '')).strip() if pd.notna(row.get('Name', '')) else ''
                location = str(row.get('Location', '')) if pd.notna(row.get('Location', '')) else ''
                adoption_date = str(row.get('Adoption Date', '')) if pd.notna(row.get('Adoption Date', '')) else ''
                
                if name and name.strip():
                    # Check if substation already exists
                    c.execute("SELECT id FROM substations WHERE name=?", (name,))
                    if c.fetchone():
                        duplicates.append(name)
                    else:
                        c.execute("INSERT INTO substations (name, location, adoption_date) VALUES (?, ?, ?)",
                                 (name, location, adoption_date))
                        count += 1
            
            self.conn.commit()
            
            if duplicates:
                dup_list = ', '.join(duplicates)
                msg = f'{count} νέοι υποσταθμοί εισήχθησαν.\nΥπάρχοντες (δεν εισήχθησαν): {dup_list}'
            else:
                msg = f'{count} υποσταθμοί εισήχθησαν με επιτυχία!'
            
            self.output.text = msg
            # Show popup with message, then refresh records
            self.show_message_popup('Εισαγωγή Υποσταθμών (CSV)', msg, callback=lambda: self.show_records(None))
        except Exception as e:
            error_msg = f'Σφάλμα: {str(e)}'
            self.output.text = error_msg
            self.show_message_popup('Σφάλμα', error_msg)
    
    def import_elements_from_excel(self, file_path):
        if pd is None:
            self.output.text = 'pandas δεν είναι εγκατεστημένο!'
            return
        
        try:
            c = self.conn.cursor()
            df_elem = pd.read_excel(file_path, sheet_name='Elements')
            count = 0
            not_found = []
            
            for _, row in df_elem.iterrows():
                sub_name = row.get('Substation Name', '')
                element_type = row.get('Element Type', '')
                name = row.get('Name', '')
                serial_number = row.get('Serial Number', '')
                maintenance_date = row.get('Maintenance Date', '')
                voltage_level = row.get('Voltage Level', '')
                manufacturer = row.get('Manufacturer', '')
                elem_type = row.get('Type', '')
                
                if sub_name and name:
                    c.execute("SELECT id FROM substations WHERE name=?", (str(sub_name),))
                    result = c.fetchone()
                    if result:
                        sub_id = result[0]
                        c.execute("INSERT INTO elements (substation_id, element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                 (sub_id, str(element_type) if pd.notna(element_type) else '', str(name), str(serial_number) if pd.notna(serial_number) else '', str(maintenance_date) if pd.notna(maintenance_date) else '', str(voltage_level) if pd.notna(voltage_level) else '', str(manufacturer) if pd.notna(manufacturer) else '', str(elem_type) if pd.notna(elem_type) else ''))
                        count += 1
                    else:
                        not_found.append(sub_name)
            
            self.conn.commit()
            
            if not_found:
                msg = f'{count} στοιχεία εισήχθησαν. Υποσταθμοί δεν βρέθησαν: {set(not_found)}'
            else:
                msg = f'{count} στοιχεία εισήχθησαν με επιτυχία!'
            
            self.output.text = msg
            # Show popup with message, then refresh records
            self.show_message_popup('Εισαγωγή Στοιχείων (Excel)', msg, callback=lambda: self.show_records(None))
        except Exception as e:
            error_msg = f'Σφάλμα: {str(e)}'
            self.output.text = error_msg
            self.show_message_popup('Σφάλμα', error_msg)
    
    def import_elements_from_csv(self, file_path):
        if pd is None:
            self.output.text = 'pandas δεν είναι εγκατεστημένο!'
            return
        
        try:
            c = self.conn.cursor()
            df_elem = pd.read_csv(file_path)
            count = 0
            not_found = []
            
            for _, row in df_elem.iterrows():
                sub_name = row.get('Substation Name', '')
                element_type = row.get('Element Type', '')
                name = row.get('Name', '')
                serial_number = row.get('Serial Number', '')
                maintenance_date = row.get('Maintenance Date', '')
                voltage_level = row.get('Voltage Level', '')
                manufacturer = row.get('Manufacturer', '')
                elem_type = row.get('Type', '')
                
                if sub_name and name:
                    c.execute("SELECT id FROM substations WHERE name=?", (str(sub_name),))
                    result = c.fetchone()
                    if result:
                        sub_id = result[0]
                        c.execute("INSERT INTO elements (substation_id, element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                 (sub_id, str(element_type) if pd.notna(element_type) else '', str(name), str(serial_number) if pd.notna(serial_number) else '', str(maintenance_date) if pd.notna(maintenance_date) else '', str(voltage_level) if pd.notna(voltage_level) else '', str(manufacturer) if pd.notna(manufacturer) else '', str(elem_type) if pd.notna(elem_type) else ''))
                        count += 1
                    else:
                        not_found.append(sub_name)
            
            self.conn.commit()
            
            if not_found:
                msg = f'{count} στοιχεία εισήχθησαν. Υποσταθμοί δεν βρέθησαν: {set(not_found)}'
            else:
                msg = f'{count} στοιχεία εισήχθησαν με επιτυχία!'
            
            self.output.text = msg
            # Show popup with message, then refresh records
            self.show_message_popup('Εισαγωγή Στοιχείων (CSV)', msg, callback=lambda: self.show_records(None))
        except Exception as e:
            error_msg = f'Σφάλμα: {str(e)}'
            self.output.text = error_msg
            self.show_message_popup('Σφάλμα', error_msg)

    def delete_element(self, element_id, substation_id, parent_popup):
        c = self.conn.cursor()
        c.execute("DELETE FROM elements WHERE id=?", (element_id,))
        self.conn.commit()
        self.output.text = 'Στοιχείο διαγράφηκε!'
        parent_popup.dismiss()
        # Refresh the records view to show the updated list
        self.show_records(None)

    def delete_substation(self, substation_id, parent_popup):
        c = self.conn.cursor()
        # Delete all elements for this substation first
        c.execute("DELETE FROM elements WHERE substation_id=?", (substation_id,))
        # Then delete the substation
        c.execute("DELETE FROM substations WHERE id=?", (substation_id,))
        self.conn.commit()
        self.output.text = 'Υποσταθμός και όλα τα στοιχεία του διαγράφηκαν!'
        parent_popup.dismiss()
        # Refresh the records view
        self.show_records(None)
    
    def show_message_popup(self, title, message, callback=None):
        # Dynamically adjust popup size based on message length
        msg_len = len(message)
        if msg_len < 100:
            size_hint = (0.7, 0.3)
        elif msg_len < 200:
            size_hint = (0.85, 0.4)
        else:
            size_hint = (0.9, 0.55)
        
        popup = Popup(title=title, size_hint=size_hint)
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Scrollable message for long text
        scroll = ScrollView()
        msg_label = Label(text=message, size_hint_y=None, markup=False)
        msg_label.bind(texture_size=msg_label.setter('size'))
        scroll.add_widget(msg_label)
        layout.add_widget(scroll)
        
        close_btn = Button(text='OK', size_hint_y=0.15)
        def on_close(btn):
            popup.dismiss()
            if callback:
                callback()
        close_btn.bind(on_press=on_close)
        layout.add_widget(close_btn)
        
        popup.content = layout
        popup.open()

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
            self.output.text = 'Υποσταθμός ενημερώθηκε!'
            popup.dismiss()
            parent_popup.dismiss()
            # Refresh the records view
            self.show_records(None)
        
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
            self.output.text = 'Δεν υπάρχουν υποσταθμοί!'
            return
        
        # Store substations mapping for later use
        self.substations_map = {s[1]: s[0] for s in substations}
        
        # Create popup
        popup = Popup(title='Προσθήκη Στοιχείου', size_hint=(0.8, 0.6))
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # Substation spinner
        substation_names = list(self.substations_map.keys())
        substation_spinner = Spinner(
            text=substation_names[0],
            values=substation_names,
            size_hint_y=0.2
        )
        layout.add_widget(Label(text='Επιλέξτε Υποσταθμό:', size_hint_y=0.2))
        layout.add_widget(substation_spinner)
        
        # Element type spinner
        element_spinner = Spinner(
            text=self.ELEMENT_TYPES[0],
            values=self.ELEMENT_TYPES,
            size_hint_y=0.2
        )
        layout.add_widget(Label(text='Επιλέξτε Στοιχείο:', size_hint_y=0.2))
        layout.add_widget(element_spinner)
        
        # Buttons layout
        buttons_layout = BoxLayout(size_hint_y=0.2, spacing=10)
        
        def add_element():
            substation_name = substation_spinner.text
            element_type = element_spinner.text
            substation_id = self.substations_map[substation_name]
            
            c = self.conn.cursor()
            c.execute("INSERT INTO elements (substation_id, element_type) VALUES (?, ?)", 
                     (substation_id, element_type))
            self.conn.commit()
            self.output.text = f'Στοιχείο προστέθηκε στον {substation_name}!'
            popup.dismiss()
        
        add_btn = Button(text='Προσθήκη')
        add_btn.bind(on_press=lambda x: add_element())
        buttons_layout.add_widget(add_btn)
        
        cancel_btn = Button(text='Ακύρωση')
        cancel_btn.bind(on_press=popup.dismiss)
        buttons_layout.add_widget(cancel_btn)
        
        layout.add_widget(buttons_layout)
        popup.content = layout
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
        
        # Element name input
        element_name_input = TextInput(
            hint_text='Όνομα Στοιχείου',
            size_hint_y=None,
            height=40,
            multiline=False
        )
        input_layout.add_widget(Label(text='Όνομα Στοιχείου:', size_hint_y=None, height=30))
        input_layout.add_widget(element_name_input)
        
        # Serial number input
        serial_number_input = TextInput(
            hint_text='Σειριακός Αριθμός',
            size_hint_y=None,
            height=40,
            multiline=False
        )
        input_layout.add_widget(Label(text='Σειριακός Αριθμός:', size_hint_y=None, height=30))
        input_layout.add_widget(serial_number_input)
        
        # Maintenance date input
        maintenance_date_input = TextInput(
            hint_text='Ημερομηνία (YYYY-MM-DD)',
            size_hint_y=None,
            height=40,
            multiline=False
        )
        input_layout.add_widget(Label(text='Ημερομηνία τελευταίας συντήρησης:', size_hint_y=None, height=30))
        input_layout.add_widget(maintenance_date_input)
        
        # Voltage level spinner
        voltage_spinner = Spinner(
            text=self.VOLTAGE_LEVELS[0],
            values=self.VOLTAGE_LEVELS,
            size_hint_y=None,
            height=40
        )
        input_layout.add_widget(Label(text='Επίπεδο Τάσης:', size_hint_y=None, height=30))
        input_layout.add_widget(voltage_spinner)
        
        # Manufacturer input
        manufacturer_input = TextInput(
            hint_text='Κατασκευστής',
            size_hint_y=None,
            height=40,
            multiline=False
        )
        input_layout.add_widget(Label(text='Κατασκευστής:', size_hint_y=None, height=30))
        input_layout.add_widget(manufacturer_input)
        
        # Type input
        type_input = TextInput(
            hint_text='Τύπος',
            size_hint_y=None,
            height=40,
            multiline=False
        )
        input_layout.add_widget(Label(text='Τύπος:', size_hint_y=None, height=30))
        input_layout.add_widget(type_input)
        
        scroll.add_widget(input_layout)
        layout.add_widget(scroll)
        
        # Buttons layout
        buttons_layout = BoxLayout(size_hint_y=0.1, spacing=10)
        
        def add_element():
            element_type = element_spinner.text
            element_name = element_name_input.text
            serial_number = serial_number_input.text
            maintenance_date = maintenance_date_input.text
            voltage_level = voltage_spinner.text
            manufacturer = manufacturer_input.text
            elem_type = type_input.text
            
            if not element_name:
                self.output.text = 'Παρακαλώ εισάγετε όνομα στοιχείου!'
                return
            
            c = self.conn.cursor()
            c.execute("INSERT INTO elements (substation_id, element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", 
                     (substation_id, element_type, element_name, serial_number, maintenance_date, voltage_level, manufacturer, elem_type))
            self.conn.commit()
            self.output.text = f'Στοιχείο προστέθηκε!'
            popup.dismiss()
            parent_popup.dismiss()
            # Refresh the records view to show the new element
            self.show_records(None)
        
        add_btn = Button(text='Προσθήκη')
        add_btn.bind(on_press=lambda x: add_element())
        buttons_layout.add_widget(add_btn)
        
        cancel_btn = Button(text='Ακύρωση')
        cancel_btn.bind(on_press=popup.dismiss)
        buttons_layout.add_widget(cancel_btn)
        
        layout.add_widget(buttons_layout)
        popup.content = layout
        popup.open()

SubstationApp().run()