"""
Delegating wrappers for element-related UI functions in `DBrun.py`.
These thin wrappers call the app instance methods to keep behavior unchanged
while allowing incremental extraction.
"""


def show_add_element_popup_delegate(app, instance=None):
    return app.show_add_element_popup(instance)


def show_add_element_popup_for_substation_delegate(app, substation_id, parent_popup=None):
    return app.show_add_element_popup_for_substation(substation_id, parent_popup)


def show_edit_element_popup_delegate(app, element_id, substation_id, parent_popup, substation_name=None):
    return app.show_edit_element_popup(element_id, substation_id, parent_popup, substation_name)


def show_inactive_elements_delegate(app, substation_id, substation_name, parent_popup):
    return app.show_inactive_elements(substation_id, substation_name, parent_popup)


def show_maintenance_element_details_delegate(app, maintenance_id, element_id):
    return app.show_maintenance_element_details(maintenance_id, element_id)


def show_add_element_popup(app, instance):
    from popups import show_message_popup
    from strings import STRINGS as S

    # Get list of substations
    c = app.conn.cursor()
    c.execute("SELECT id, name FROM substations ORDER BY name")
    substations = c.fetchall()

    if not substations:
        show_message_popup(S["TITLES"]["ERROR"], "Δεν υπάρχουν υποσταθμοί!")
        return

    # Get active people for responsible/crew selection
    c.execute("SELECT id, name, role FROM people WHERE active=1 ORDER BY COALESCE(surname, name) COLLATE NOCASE")
    people = c.fetchall()
    if not people:
        show_message_popup(
            S["TITLES"]["ERROR"],
            "Δεν υπάρχουν καταχωρημένα άτομα. Παρακαλώ προσθέστε προσωπικό.",
            callback=lambda: app.show_people_management(None),
        )
        return

    # Store substations mapping for later use
    app.substations_map = {s[1]: s[0] for s in substations}

    # Create popup
    from kivy.uix.popup import Popup
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.textinput import TextInput
    from kivy.uix.spinner import Spinner
    from kivy.uix.scrollview import ScrollView

    popup = Popup(title="Προσθήκη Στοιχείου", size_hint=(0.8, 0.9))
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    # Create scrollable area for inputs
    scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
    layout = BoxLayout(
        orientation="vertical", size_hint_y=None, padding=5, spacing=8
    )
    layout.bind(minimum_height=layout.setter("height"))

    # Substation spinner
    substation_names = list(app.substations_map.keys())
    layout.add_widget(
        Label(text="Επιλέξτε Υποσταθμό:", size_hint_y=None, height=30)
    )
    substation_spinner = Spinner(
        text=substation_names[0],
        values=substation_names,
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(substation_spinner)

    # Element type spinner
    layout.add_widget(Label(text="Επιλέξτε Στοιχείο:", size_hint_y=None, height=30))
    element_spinner = Spinner(
        text=app.ELEMENT_TYPES[0],
        values=app.ELEMENT_TYPES,
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(element_spinner)

    # Voltage level selection
    layout.add_widget(Label(text="Επίπεδο Τάσης:", size_hint_y=None, height=30))
    _derived = app._derive_voltage_level(element_spinner.text)
    initial_voltage = _derived or "(Κενό)"
    voltage_level_spinner = Spinner(
        text=initial_voltage,
        values=[_derived] if _derived else list(app.VOLTAGE_LEVELS),
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(voltage_level_spinner)

    # Gate selection (auto-populated from transformers)
    gate_label = Label(text="Πύλη (Gate):", size_hint_y=None, height=30)
    layout.add_widget(gate_label)

    # Get initial gates for the first substation
    initial_gates = app.get_available_gates(
        app.substations_map[substation_names[0]]
    )
    gate_spinner = Spinner(
        text=initial_gates[0] if initial_gates else "(Μη καταχωρημένο)",
        values=initial_gates if initial_gates else ["(Μη καταχωρημένο)"],
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(gate_spinner)

    # Rated power (Ονομαστική Ισχύς) - optional attribute for any element
    layout.add_widget(Label(text="Ονομαστική Ισχύς (MVA):", size_hint_y=None, height=30))
    rated_power_input = TextInput(hint_text="π.χ. 50", size_hint_y=None, height=40, multiline=False)
    layout.add_widget(rated_power_input)

    # Update gates when substation changes
    def on_substation_change(spinner, text):
        substation_id = app.substations_map[text]
        if element_spinner.text in ["Διακόπτης ΥΤ", "Διακόπτης ΜΤ"]:
            if breaker_type_spinner.text == "Διασυνδετικός":
                available_gates = app.get_available_gates(substation_id, True)
            else:
                available_gates = app.get_available_gates(substation_id, False)
        else:
            available_gates = app.get_available_gates(substation_id, False)
        gate_spinner.values = available_gates
        gate_spinner.text = (
            available_gates[0] if available_gates else "(Μη καταχωρημένο)"
        )

    substation_spinner.bind(text=on_substation_change)

    # Breaker type selection (Main or Line or Interconnection) - only for circuit breakers
    breaker_type_label = Label(text="Τύπος Διακόπτη:", size_hint_y=None, height=30)
    breaker_type_spinner = Spinner(
        text=app.BREAKER_TYPES[0],
        values=app.BREAKER_TYPES,
        size_hint_y=None,
        height=40,
    )

    def on_breaker_type_change(spinner, text):
        substation_id = app.substations_map[substation_spinner.text]
        if element_spinner.text in ["Διακόπτης ΥΤ", "Διακόπτης ΜΤ"]:
            if text == "Διασυνδετικός":
                available_gates = app.get_available_gates(substation_id, True)
            else:
                available_gates = app.get_available_gates(substation_id, False)
        else:
            available_gates = app.get_available_gates(substation_id, False)
        gate_spinner.values = available_gates
        gate_spinner.text = (
            available_gates[0] if available_gates else "(Μη καταχωρημένο)"
        )

    breaker_type_spinner.bind(text=on_breaker_type_change)

    # Breaker category filter (only for circuit breakers)
    breaker_category_label = Label(
        text="Κατηγορία Διακόπτη:", size_hint_y=None, height=30
    )
    initial_breaker_categories = app._get_breaker_categories_for_element_type(
        element_spinner.text
    )
    breaker_category_spinner = Spinner(
        text=initial_breaker_categories[0] if initial_breaker_categories else "SF6",
        values=initial_breaker_categories,
        size_hint_y=None,
        height=40,
    )

    def on_breaker_category_change(spinner, text):
        try:
            current_element_type = element_spinner.text
        except Exception:
            current_element_type = None
        try:
            load_models_for_category(current_element_type, text)
        except Exception:
            pass

    breaker_category_spinner.bind(text=on_breaker_category_change)

    # Model selection with "Add New" button
    model_header = BoxLayout(size_hint_y=None, height=30, spacing=5)
    model_header.add_widget(Label(text="Μοντέλο:", size_hint_x=0.7))
    add_model_btn = Button(
        text="+ Νέο Μοντέλο", size_hint_x=0.3, size_hint_y=None, height=30
    )
    model_header.add_widget(add_model_btn)
    layout.add_widget(model_header)

    model_spinner = Spinner(
        text="Επιλέξτε μοντέλο",
        values=["Επιλέξτε μοντέλο"],
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(model_spinner)

    # Store model data
    models_data = {}

    def load_models_for_category(category, selected_breaker_category=None):
        models_data_temp, display_names, _ = app._load_models_for_element_type(
            category, selected_breaker_category
        )
        models_data.clear()
        models_data.update(models_data_temp)

        if display_names:
            model_spinner.values = display_names
            model_spinner.text = display_names[0]
        else:
            model_spinner.values = ["Επιλέξτε μοντέλο"]
            model_spinner.text = "Επιλέξτε μοντέλο"

    def on_element_type_change(spinner, text):
        if text in ["Διακόπτης ΥΤ", "Διακόπτης ΜΤ"]:
            breaker_category_options = app._get_breaker_categories_for_element_type(text)
            breaker_category_spinner.values = breaker_category_options
            if breaker_category_spinner.text not in breaker_category_options:
                breaker_category_spinner.text = (
                    breaker_category_options[0] if breaker_category_options else "SF6"
                )
            if breaker_category_label not in layout.children:
                idx = layout.children.index(model_header)
                layout.add_widget(breaker_category_spinner, index=idx + 1)
                layout.add_widget(breaker_category_label, index=idx + 2)
                breaker_category_spinner.bind(text=on_breaker_category_change)
            load_models_for_category(text, breaker_category_spinner.text)
        else:
            if breaker_category_label in layout.children:
                breaker_category_spinner.unbind(text=on_breaker_category_change)
                layout.remove_widget(breaker_category_label)
                layout.remove_widget(breaker_category_spinner)
            load_models_for_category(text, None)

        if text in ["Διακόπτης ΥΤ", "Διακόπτης ΜΤ"]:
            if breaker_type_label not in layout.children:
                idx = layout.children.index(model_spinner)
                layout.add_widget(breaker_type_spinner, index=idx)
                layout.add_widget(breaker_type_label, index=idx + 1)
            substation_id = app.substations_map[substation_spinner.text]
            if breaker_type_spinner.text == "Διασυνδετικός":
                available_gates = app.get_available_gates(substation_id, True)
            else:
                available_gates = app.get_available_gates(substation_id, False)
            gate_spinner.values = available_gates
            gate_spinner.text = (
                available_gates[0] if available_gates else "(Μη καταχωρημένο)"
            )
        else:
            if breaker_type_label in layout.children:
                layout.remove_widget(breaker_type_label)
                layout.remove_widget(breaker_type_spinner)
            substation_id = app.substations_map[substation_spinner.text]
            available_gates = app.get_available_gates(substation_id, False)
            gate_spinner.values = available_gates
            gate_spinner.text = (
                available_gates[0] if available_gates else "(Μη καταχωρημένο)"
            )

        _derived = app._derive_voltage_level(text)
        voltage_level_spinner.values = [_derived] if _derived else list(app.VOLTAGE_LEVELS)
        voltage_level_spinner.text = _derived or "(Κενό)"

    element_spinner.bind(text=on_element_type_change)
    on_element_type_change(element_spinner, element_spinner.text)

    # Dynamic element fields (auto-filled from model, can be overridden)
    field_inputs = {}
    for field in app.ELEMENT_FIELD_DEFS:
        layout.add_widget(
            Label(text=f"{field['label']}:", size_hint_y=None, height=30)
        )
        if field.get("type") == "spinner":
            spinner = Spinner(
                text=field["values"][0],
                values=field["values"],
                size_hint_y=None,
                height=40,
            )
            field_inputs[field["key"]] = spinner
            layout.add_widget(spinner)
        else:
            ti = TextInput(
                hint_text=field.get("hint", ""),
                size_hint_y=None,
                height=40,
                multiline=False,
            )
            field_inputs[field["key"]] = ti
            layout.add_widget(ti)

    def on_model_selected(spinner, text):
        if text in models_data:
            model = models_data[text]
            field_inputs["manufacturer"].text = model["manufacturer"]
            field_inputs["model"].text = model["model_name"]
            field_inputs["maintenance_cycle"].text = str(model["maintenance_cycle"])
            field_inputs["installation_space"].text = model["installation_space"]

    model_spinner.bind(text=on_model_selected)

    def open_add_model():
        from model_management import show_add_model_popup

        def reload_models():
            load_models_for_category(element_spinner.text)

        show_add_model_popup(
            app, callback=reload_models, category=element_spinner.text
        )

    add_model_btn.bind(on_press=lambda x: open_add_model())

    scroll.add_widget(layout)
    main_layout.add_widget(scroll)

    # Buttons layout
    buttons_layout = BoxLayout(size_hint_y=0.1, spacing=10)

    def add_element():
        substation_name = substation_spinner.text
        substation_id = app.substations_map[substation_name]
        element_type = element_spinner.text

        name_val = (
            field_inputs["name"].text
            if hasattr(field_inputs["name"], "text")
            else field_inputs["name"].text
        )
        if not name_val:
            show_message_popup("Σφάλμα", "Παρακαλώ εισάγετε όνομα στοιχείου!")
            return

        values = {
            key: (
                field_inputs[key].text
                if hasattr(field_inputs[key], "text")
                else field_inputs[key].text
            )
            for key in field_inputs
        }
        if "operating_status" in values and hasattr(
            field_inputs["operating_status"], "text"
        ):
            values["operating_status"] = field_inputs["operating_status"].text

        if element_type == "Διακόπτης ΥΤ":
            is_main_switch = 1
        elif element_type == "Διακόπτης ΜΤ":
            if breaker_type_spinner.text == "Κεντρικός":
                is_main_switch = 1
            elif breaker_type_spinner.text == "Διασυνδετικός":
                is_main_switch = 2
            elif breaker_type_spinner.text == "Διακόπτης Πυκνωτών":
                is_main_switch = 3
            else:
                is_main_switch = 0
        else:
            is_main_switch = 0

        gate_value = (
            gate_spinner.text if gate_spinner.text != "(Μη καταχωρημένο)" else ""
        )

        try:
            validate_gate_assignment(element_type, breaker_type_spinner.text, gate_value)
        except ValueError as e:
            show_message_popup(S["TITLES"]["ERROR"], str(e))
            return

        breaker_category_value = None
        if element_type in ["Διακόπτης ΥΤ", "Διακόπτης ΜΤ"]:
            breaker_category_value = breaker_category_spinner.text

        try:
            validate_breaker_category_required(element_type, breaker_category_value)
        except ValueError as e:
            show_message_popup(S["TITLES"]["ERROR"], str(e))
            return

        model_id = None
        if model_spinner.text in models_data:
            model_id = models_data[model_spinner.text]["id"]

        rated_power_val = ""
        try:
            rated_power_val = rated_power_input.text.strip()
        except Exception:
            rated_power_val = ""

        maintenance_cycle = values.get("maintenance_cycle", "0")
        try:
            maintenance_cycle_int = (
                int(maintenance_cycle) if maintenance_cycle else 0
            )
        except ValueError:
            show_message_popup(
                "Σφάλμα", "Ο κύκλος συντήρησης πρέπει να είναι αριθμός!"
            )
            return

        c = app.conn.cursor()
        c.execute(
            "SELECT id FROM elements WHERE substation_id=? AND name=?",
            (substation_id, name_val),
        )
        if c.fetchone():
            show_message_popup(
                "Σφάλμα",
                f'Υπάρχει ήδη στοιχείο με όνομα "{name_val}" σε αυτόν τον υποσταθμό!',
            )
            return

        voltage_level_value = (
            voltage_level_spinner.text
            if voltage_level_spinner.text != "(Κενό)"
            else ""
        )

        c.execute(
            "INSERT INTO elements (substation_id, element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, model, model_version, installation_space, operating_status, maintenance_cycle, element_model_id, manufacture_year, gate, is_main_switch, breaker_category, power_mva) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                substation_id,
                element_type,
                values.get("name", ""),
                (values.get("serial_number", "") or "").strip(),
                values.get("maintenance_date", ""),
                voltage_level_value,
                values.get("manufacturer", ""),
                values.get("model", ""),
                values.get("model_version", ""),
                values.get("installation_space", "Εσωτερικός"),
                values.get("operating_status", "Ενεργή"),
                maintenance_cycle_int,
                model_id,
                values.get("manufacture_year", ""),
                gate_value,
                is_main_switch,
                breaker_category_value,
                (None if rated_power_val == "" else float(rated_power_val.replace(",", "."))) if rated_power_val else None,
            ),
        )
        app.conn.commit()

        try:
            if model_id and rated_power_val:
                rp_val = None if rated_power_val == "" else float(rated_power_val.replace(",", "."))
                if rp_val is not None:
                    c.execute("UPDATE element_models SET power_mva=? WHERE id=?", (rp_val, model_id))
                    app.conn.commit()
        except Exception:
            pass

        popup.dismiss()
        show_message_popup(
            "Επιτυχία",
            f"Στοιχείο προστέθηκε στον {substation_name}!",
            callback=lambda: app._display_substations(substation_name),
        )

    add_btn = Button(text=S["BUTTONS"]["ADD"])
    add_btn.bind(on_press=lambda x: add_element())
    buttons_layout.add_widget(add_btn)

    cancel_btn = Button(text="Ακύρωση")
    cancel_btn.bind(on_press=popup.dismiss)
    buttons_layout.add_widget(cancel_btn)

    main_layout.add_widget(buttons_layout)
    popup.content = main_layout
    popup.open()


def _copy_common_delete_logic(app, element_id, substation_id, parent_popup, substation_name=None):
    c = app.conn.cursor()
    c.execute(
        "SELECT element_type, gate, is_main_switch FROM elements WHERE id=?",
        (element_id,),
    )
    row = c.fetchone()
    if row:
        elem_type, gate, is_main = row
        if elem_type in ["Διακόπτης ΥΤ", "Διακόπτης ΜΤ"] and is_main == 1:
            gate_value = gate or ""
            c.execute(
                "SELECT COUNT(*) FROM elements WHERE substation_id=? AND gate=? AND element_type=? AND is_main_switch=1 AND id!=?",
                (substation_id, gate_value, elem_type, element_id),
            )
            remaining = c.fetchone()[0]
            if remaining == 0:
                from popups import show_message_popup

                show_message_popup(
                    "Σφάλμα",
                    f"Η πύλη '{gate_value or '(Μη καταχωρημένο)'}' πρέπει να έχει τουλάχιστον έναν κεντρικό { 'Διακόπτης ΥΤ' if elem_type=='Διακόπτης ΥΤ' else 'Διακόπτης ΜΤ' }.",
                )
                return False
    return True


def confirm_delete_element(app, element_id, element_name, substation_id, parent_popup, substation_name=None):
    from reports import show_confirm

    def confirm():
        delete_element(app, element_id, substation_id, parent_popup, substation_name)

    show_confirm(
        "Επιβεβαίωση Διαγραφής",
        f'Είστε σίγουροι ότι θέλετε να διαγράψετε\nτο στοιχείο "{element_name}"?','"',
        yes_callback=confirm,
        yes_color=(1, 0, 0, 1),
    )


def delete_element(app, element_id, substation_id, parent_popup, substation_name=None):
    c = app.conn.cursor()
    if not _copy_common_delete_logic(app, element_id, substation_id, parent_popup, substation_name):
        return

    prev_scroll = None
    try:
        prev_scroll = app._get_popup_scroll_y(parent_popup)
    except Exception:
        prev_scroll = None

    c.execute("DELETE FROM elements WHERE id=?", (element_id,))
    app.conn.commit()

    if substation_name:
        app._display_substations(substation_name, reuse_popup=parent_popup, prev_scroll_y=prev_scroll)
        from popups import show_message_popup

        show_message_popup("Ολοκληρώθηκε", "Το στοιχείο διαγράφηκε!")
    else:
        app._display_substations(None, reuse_popup=parent_popup, prev_scroll_y=prev_scroll)
        from popups import show_message_popup

        show_message_popup("Ολοκληρώθηκε", "Το στοιχείο διαγράφηκε!")


def show_inactive_elements(app, substation_id, substation_name, parent_popup):
    from kivy.uix.popup import Popup
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.gridlayout import GridLayout

    c = app.conn.cursor()
    c.execute(
        """
            SELECT e.id, e.element_type, e.name, e.serial_number, 
                   em.manufacturer as model_manufacturer, em.model_name, e.is_main_switch
            FROM elements e 
            LEFT JOIN element_models em ON e.element_model_id = em.id
            WHERE e.substation_id=? AND e.operating_status='Ανενεργή' 
            ORDER BY e.name
        """,
        (substation_id,),
    )
    inactive_elements = c.fetchall()

    popup = Popup(
        title=f"Ανενεργά Στοιχεία - {substation_name}", size_hint=(0.8, 0.8)
    )
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    if not inactive_elements:
        main_layout.add_widget(
            Label(
                text="Δεν υπάρχουν ανενεργά στοιχεία σε αυτόν τον υποσταθμό",
                size_hint_y=0.8,
            )
        )
    else:
        scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
        grid = GridLayout(cols=1, spacing=10, size_hint_y=None, padding=10)
        grid.bind(minimum_height=grid.setter("height"))

        for (
            elem_id,
            elem_type,
            elem_name,
            serial_number,
            model_manufacturer,
            model_name,
            is_main_switch,
        ) in inactive_elements:
            elem_layout = BoxLayout(
                size_hint_y=None, height=80, spacing=5, orientation="vertical"
            )

            display_elem_type = elem_type
            if elem_type in ["Διακόπτης ΥΤ", "Διακόπτης ΜΤ"]:
                if elem_type == "Διακόπτης ΥΤ":
                    breaker_type_label = "Κεντρικός"
                elif is_main_switch == 1:
                    breaker_type_label = "Κεντρικός"
                elif is_main_switch == 2:
                    breaker_type_label = "Διασυνδετικός"
                elif is_main_switch == 3:
                    breaker_type_label = "Διακόπτης Πυκνωτών"
                else:
                    breaker_type_label = "Γραμμής"
                display_elem_type = app._format_elem_type(elem_type, is_main_switch)

            info_text = f"[b]{elem_name}[/b] - {display_elem_type}\nS/N: {serial_number or '-'} | Κατ.: {model_manufacturer or '-'} | Μοντ.: {model_name or '-'} (id:{elem_id})"
            elem_label = Label(
                text=info_text, size_hint_y=None, height=50, markup=True
            )
            elem_layout.add_widget(elem_label)

            btn_layout = BoxLayout(size_hint_y=None, height=30, spacing=5)

            edit_btn = Button(text=S["BUTTONS"]["EDIT"])
            edit_btn.bind(
                on_press=lambda x, eid=elem_id, sid=substation_id, sname=substation_name, p=popup, gp=parent_popup: (
                    app.show_edit_element_popup(eid, sid, p, sname, gp)
                )
            )
            btn_layout.add_widget(edit_btn)

            elem_layout.add_widget(btn_layout)
            grid.add_widget(elem_layout)

        scroll.add_widget(grid)
        main_layout.add_widget(scroll)

    close_btn = Button(text=S["BUTTONS"]["CLOSE"], size_hint_y=0.1)
    close_btn.bind(on_press=popup.dismiss)
    main_layout.add_widget(close_btn)

    popup.content = main_layout
    popup.open()


def show_edit_element_popup(app, element_id, substation_id, parent_popup, substation_name=None, grandparent_popup=None):
    from popups import show_message_popup
    from kivy.uix.popup import Popup
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.textinput import TextInput
    from kivy.uix.spinner import Spinner
    from kivy.uix.scrollview import ScrollView

    # Fetch element data
    c = app.conn.cursor()
    c.execute(
        "SELECT element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, model, model_version, installation_space, operating_status, maintenance_cycle, manufacture_year, element_model_id, gate, is_main_switch, breaker_category, power_mva FROM elements WHERE id=?",
        (element_id,),
    )
    element = c.fetchone()

    if not element:
        show_message_popup(S["TITLES"]["ERROR"], "Το στοιχείο δεν βρέθηκε!")
        return

    (
        elem_type,
        name,
        serial_num,
        maint_date,
        voltage_level,
        manufacturer,
        model,
        model_version,
        install_space,
        op_status,
        maint_cycle,
        manuf_year,
        model_id,
        gate,
        is_main_switch,
        breaker_category,
        power_mva,
    ) = element

    popup = Popup(title=f"Επεξεργασία: {name}", size_hint=(0.9, 0.9))
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
    layout = BoxLayout(
        orientation="vertical", size_hint_y=None, padding=5, spacing=8
    )
    layout.bind(minimum_height=layout.setter("height"))

    # Element type (read-only)
    layout.add_widget(
        Label(text=f"Τύπος: {elem_type}", size_hint_y=None, height=30, bold=True)
    )

    # Voltage level (dropdown)
    layout.add_widget(Label(text="Επίπεδο Τάσης:", size_hint_y=None, height=30))
    current_voltage = (
        voltage_level or app._derive_voltage_level(elem_type) or "(Κενό)"
    )
    _derived = app._derive_voltage_level(elem_type)
    voltage_options = [_derived] if _derived else list(app.VOLTAGE_LEVELS)
    if current_voltage not in voltage_options:
        voltage_options.append(current_voltage)
    voltage_level_spinner = Spinner(
        text=current_voltage, values=voltage_options, size_hint_y=None, height=40
    )
    layout.add_widget(voltage_level_spinner)

    # Rated power (Ονομαστική Ισχύς) - element attribute, editable here
    layout.add_widget(Label(text="Ονομαστική Ισχύς (MVA):", size_hint_y=None, height=30))
    # Prefer model-rated power if the element is linked to a model
    model_power_val = None
    try:
        if model_id:
            c.execute("SELECT power_mva FROM element_models WHERE id=?", (model_id,))
            mr = c.fetchone()
            if mr and mr[0] is not None:
                model_power_val = mr[0]
    except Exception:
        model_power_val = None

    rated_power_input = TextInput(text=(str(model_power_val) if model_power_val is not None else (str(power_mva) if power_mva is not None else "")), size_hint_y=None, height=40, multiline=False)
    layout.add_widget(rated_power_input)

    # Model selection
    breaker_category_label = Label(
        text="Κατηγορία Διακόπτη:", size_hint_y=None, height=30
    )
    breaker_category_options = app._get_breaker_categories_for_element_type(
        elem_type
    )
    breaker_category_text = (
        breaker_category
        if breaker_category in breaker_category_options
        else (breaker_category_options[0] if breaker_category_options else "SF6")
    )
    breaker_category_spinner = Spinner(
        text=breaker_category_text,
        values=breaker_category_options,
        size_hint_y=None,
        height=40,
    )

    if elem_type in ["Διακόπτης ΜΤ", "Διακόπτης ΥΤ"]:
        layout.add_widget(breaker_category_label)
        layout.add_widget(breaker_category_spinner)

    layout.add_widget(Label(text="Μοντέλο:", size_hint_y=None, height=30))

    # Load all models for this element type
    c.execute(
        "SELECT id, model_name, manufacturer, breaker_category FROM element_models WHERE element_category=? ORDER BY model_name",
        (elem_type,),
    )
    c.fetchall()

    models_data = {}
    model_spinner = Spinner(
        text="Επιλέξτε μοντέλο",
        values=["Επιλέξτε μοντέλο"],
        size_hint_y=None,
        height=40,
    )

    def load_models_for_breaker_category(selected_category):
        models_data_temp, display_names, selected_display_name = (
            app._load_models_for_element_type(
                elem_type, selected_category, model_id
            )
        )
        models_data.clear()
        models_data.update(models_data_temp)

        model_spinner.values = (
            display_names if display_names else ["Δεν υπάρχουν μοντέλα"]
        )
        model_spinner.text = (
            selected_display_name
            if selected_display_name
            and selected_display_name in model_spinner.values
            else model_spinner.values[0]
        )

    if elem_type in ["Διακόπτης ΜΤ", "Διακόπτης ΥΤ"]:
        breaker_category_spinner.bind(
            text=lambda spinner, text: load_models_for_breaker_category(text)
        )
        load_models_for_breaker_category(breaker_category_spinner.text)
    else:
        load_models_for_breaker_category(None)

    layout.add_widget(model_spinner)

    # Gate selection
    layout.add_widget(Label(text="Πύλη (Gate):", size_hint_y=None, height=30))
    is_interconnection = elem_type == "Διακόπτης ΜΤ" and is_main_switch == 2
    available_gates = app.get_available_gates(substation_id, is_interconnection)
    current_gate_text = gate if gate else "(Μη καταχωρημένο)"
    if current_gate_text not in available_gates:
        available_gates.append(current_gate_text)
    gate_spinner = Spinner(
        text=current_gate_text, values=available_gates, size_hint_y=None, height=40
    )
    layout.add_widget(gate_spinner)

    # Breaker type selection
    breaker_type_label = Label(text="Τύπος Διακόπτη:", size_hint_y=None, height=30)
    if is_main_switch == 1:
        current_breaker_type = "Κεντρικός"
    elif is_main_switch == 2:
        current_breaker_type = "Διασυνδετικός"
    elif is_main_switch == 3:
        current_breaker_type = "Διακόπτης Πυκνωτών"
    else:
        current_breaker_type = "Γραμμής"

    if elem_type == "Διακόπτης ΥΤ":
        breaker_type_spinner = Spinner(
            text="Κεντρικός",
            values=["Κεντρικός"],
            size_hint_y=None,
            height=40,
            disabled=True,
        )
    else:
        breaker_type_spinner = Spinner(
            text=current_breaker_type,
            values=app.BREAKER_TYPES,
            size_hint_y=None,
            height=40,
        )

    def on_breaker_type_change(spinner, text):
        is_interconnection = text == "Διασυνδετικός"
        available_gates = app.get_available_gates(
            substation_id, is_interconnection
        )
        gate_spinner.values = available_gates
        if gate_spinner.text not in available_gates:
            gate_spinner.text = (
                available_gates[0] if available_gates else "(Μη καταχωρημένο)"
            )

    breaker_type_spinner.bind(text=on_breaker_type_change)

    if elem_type in ["Διακόπτης ΜΤ", "Διακόπτης ΥΤ"]:
        layout.add_widget(breaker_type_label)
        layout.add_widget(breaker_type_spinner)

    # Dynamic fields
    field_inputs = {}
    for field in app.ELEMENT_FIELD_DEFS:
        layout.add_widget(
            Label(text=f"{field['label']}:", size_hint_y=None, height=30)
        )

        current_value = ""
        if field["key"] == "name":
            current_value = name or ""
        elif field["key"] == "serial_number":
            current_value = serial_num or ""
        elif field["key"] == "manufacture_year":
            current_value = manuf_year or ""
        elif field["key"] == "maintenance_date":
            current_value = maint_date or ""
        elif field["key"] == "manufacturer":
            current_value = manufacturer or ""
        elif field["key"] == "model":
            current_value = model or ""
        elif field["key"] == "model_version":
            current_value = model_version or ""
        elif field["key"] == "installation_space":
            current_value = install_space or app.INSTALLATION_SPACE[0]
        elif field["key"] == "operating_status":
            current_value = op_status or app.OPERATING_STATUS[0]
        elif field["key"] == "maintenance_cycle":
            current_value = str(maint_cycle) if maint_cycle else "0"

        if field.get("type") == "spinner":
            spinner = Spinner(
                text=current_value,
                values=field["values"],
                size_hint_y=None,
                height=40,
            )
            field_inputs[field["key"]] = spinner
            layout.add_widget(spinner)
        else:
            ti = TextInput(
                text=current_value,
                hint_text=field.get("hint", ""),
                size_hint_y=None,
                height=40,
                multiline=False,
            )
            field_inputs[field["key"]] = ti
            layout.add_widget(ti)

    scroll.add_widget(layout)
    main_layout.add_widget(scroll)

    # Buttons
    buttons_layout = BoxLayout(size_hint_y=0.1, spacing=10)

    def save_changes():
        name_val = field_inputs["name"].text.strip()
        if not name_val:
            show_message_popup(S["TITLES"]["ERROR"], "Το όνομα είναι υποχρεωτικό!")
            return

        try:
            cycle_val = (
                int(field_inputs["maintenance_cycle"].text)
                if field_inputs["maintenance_cycle"].text
                else 0
            )
        except ValueError:
            show_message_popup(
                "Σφάλμα", "Ο κύκλος συντήρησης πρέπει να είναι αριθμός!"
            )
            return

        c = app.conn.cursor()
        c.execute(
            "SELECT id FROM elements WHERE substation_id=? AND name=? AND id!=?",
            (substation_id, name_val, element_id),
        )
        if c.fetchone():
            show_message_popup(
                "Σφάλμα",
                f'Υπάρχει ήδη στοιχείο με όνομα "{name_val}" σε αυτόν τον υποσταθμό!',
            )
            return

        new_model_id = (
            models_data[model_spinner.text]["id"]
            if model_spinner.text in models_data
            else None
        )

        gate_value = (
            gate_spinner.text if gate_spinner.text != "(Μη καταχωρημένο)" else ""
        )

        breaker_category_value = None
        if elem_type in ["Διακόπτης ΥΤ", "Διακόπτης ΜΤ"]:
            breaker_category_value = breaker_category_spinner.text

        if elem_type in ["Διακόπτης ΥΤ", "Διακόπτης ΜΤ"] and (
            breaker_category_value is None or str(breaker_category_value).strip() == ""
        ):
            show_message_popup(
                "Σφάλμα", "Η κατηγορία διακόπτη είναι υποχρεωτική για τους διακόπτες!"
            )
            return

        if elem_type == "Διακόπτης ΥΤ":
            new_is_main_switch = 1
        elif elem_type == "Διακόπτης ΜΤ":
            if breaker_type_spinner.text == "Κεντρικός":
                new_is_main_switch = 1
            elif breaker_type_spinner.text == "Διασυνδετικός":
                new_is_main_switch = 2
            elif breaker_type_spinner.text == "Διακόπτης Πυκνωτών":
                new_is_main_switch = 3
            else:
                new_is_main_switch = 0
        else:
            new_is_main_switch = 0

        voltage_level_value = (
            voltage_level_spinner.text
            if voltage_level_spinner.text != "(Κενό)"
            else ""
        )

        try:
            validate_gate_assignment(elem_type, breaker_type_spinner.text, gate_value)
        except ValueError as e:
            show_message_popup("Σφάλμα", str(e))
            return

        try:
            if elem_type in ["Διακόπτης ΥΤ", "Διακόπτης ΜΤ"]:
                if is_main_switch == 1 and (
                    new_is_main_switch != 1 or gate_value != (gate or "")
                ):
                    old_gate = gate or ""
                    c.execute(
                        "SELECT COUNT(*) FROM elements WHERE substation_id=? AND gate=? AND element_type=? AND is_main_switch=1 AND id!=?",
                        (substation_id, old_gate, elem_type, element_id),
                    )
                    remaining = c.fetchone()[0]
                    if remaining == 0:
                        show_message_popup(
                            "Σφάλμα",
                            f"Η πύλη '{old_gate or '(Μη καταχωρημένο)'}' πρέπει να έχει τουλάχιστον έναν κεντρικό { 'Διακόπτης ΥΤ' if elem_type=='Διακόπτης ΥΤ' else 'Διακόπτης ΜΤ' }.",
                        )
                        return
        except Exception:
            pass

        try:
            rp_txt = rated_power_input.text.strip()
            power_val_to_set = None if rp_txt == "" else float(rp_txt.replace(",", "."))
        except Exception:
            power_val_to_set = None

        c.execute(
            """UPDATE elements SET 
                            name=?, serial_number=?, maintenance_date=?, voltage_level=?, manufacturer=?, model=?, model_version=?,
                            installation_space=?, operating_status=?, 
                            maintenance_cycle=?, manufacture_year=?, element_model_id=?, gate=?, is_main_switch=?, breaker_category=?, power_mva=?
                            WHERE id=?""",
            (
                name_val,
                field_inputs["serial_number"].text.strip(),
                field_inputs["maintenance_date"].text.strip(),
                voltage_level_value,
                field_inputs["manufacturer"].text.strip(),
                field_inputs["model"].text.strip(),
                field_inputs["model_version"].text.strip(),
                field_inputs["installation_space"].text,
                field_inputs["operating_status"].text,
                cycle_val,
                field_inputs["manufacture_year"].text.strip(),
                new_model_id,
                gate_value,
                new_is_main_switch,
                breaker_category_value,
                power_val_to_set,
                element_id,
            ),
        )
        app.conn.commit()
        try:
            if new_model_id and power_val_to_set is not None:
                c.execute("UPDATE element_models SET power_mva=? WHERE id=?", (power_val_to_set, new_model_id))
                app.conn.commit()
        except Exception:
            pass
        popup.dismiss()
        parent_popup.dismiss()
        if grandparent_popup:
            grandparent_popup.dismiss()
        if substation_name:
            show_message_popup(
                "Επιτυχία",
                "Οι αλλαγές αποθηκεύτηκαν!",
                callback=lambda: app._display_substations(substation_name),
            )
        else:
            show_message_popup(
                "Επιτυχία",
                "Οι αλλαγές αποθηκεύτηκαν!",
                callback=lambda: app.show_records(None),
            )

    save_btn = Button(text=S["BUTTONS"]["SAVE"])
    save_btn.bind(on_press=lambda x: save_changes())
    buttons_layout.add_widget(save_btn)

    cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
    cancel_btn.bind(on_press=popup.dismiss)
    buttons_layout.add_widget(cancel_btn)

    main_layout.add_widget(buttons_layout)
    popup.content = main_layout
    popup.open()


def show_add_element_popup_for_substation(app, substation_id, substation_name, parent_popup):
    from popups import show_message_popup
    from kivy.uix.popup import Popup
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.spinner import Spinner
    from kivy.uix.textinput import TextInput

    popup = Popup(title="Προσθήκη Στοιχείου", size_hint=(0.8, 0.9))
    layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
    input_layout = BoxLayout(
        orientation="vertical", size_hint_y=None, padding=10, spacing=10
    )
    input_layout.bind(minimum_height=input_layout.setter("height"))

    input_layout.add_widget(Label(text="Υποσταθμός:", size_hint_y=None, height=30))
    c = app.conn.cursor()
    c.execute("SELECT id, name FROM substations ORDER BY name")
    all_substations = c.fetchall()

    substation_spinner = Spinner(
        text=substation_name,
        values=[sub[1] for sub in all_substations],
        size_hint_y=None,
        height=40,
    )
    input_layout.add_widget(substation_spinner)

    substation_map = {sub[1]: sub[0] for sub in all_substations}

    element_spinner = Spinner(
        text=app.ELEMENT_TYPES[0],
        values=app.ELEMENT_TYPES,
        size_hint_y=None,
        height=40,
    )
    input_layout.add_widget(Label(text="Επιλέξτε Τύπο Στοιχείου:", size_hint_y=None, height=30))
    input_layout.add_widget(element_spinner)

    input_layout.add_widget(Label(text="Επίπεδο Τάσης:", size_hint_y=None, height=30))
    _derived = app._derive_voltage_level(element_spinner.text)
    initial_voltage = _derived or "(Κενό)"
    voltage_level_spinner = Spinner(
        text=initial_voltage,
        values=[_derived] if _derived else list(app.VOLTAGE_LEVELS),
        size_hint_y=None,
        height=40,
    )
    input_layout.add_widget(voltage_level_spinner)

    gate_label = Label(text="Πύλη (Gate):", size_hint_y=None, height=30)
    input_layout.add_widget(gate_label)

    initial_gates = app.get_available_gates(substation_id)
    gate_spinner = Spinner(
        text=initial_gates[0] if initial_gates else "(Μη καταχωρημένο)",
        values=initial_gates if initial_gates else ["(Μη καταχωρημένο)"],
        size_hint_y=None,
        height=40,
    )
    input_layout.add_widget(gate_spinner)

    input_layout.add_widget(Label(text="Ονομαστική Ισχύς (MVA):", size_hint_y=None, height=30))
    rated_power_input = TextInput(hint_text="π.χ. 50", size_hint_y=None, height=40, multiline=False)
    input_layout.add_widget(rated_power_input)

    def on_substation_change(spinner, text):
        selected_substation_id = substation_map[text]
        if element_spinner.text in ["Διακόπτης ΥΤ", "Διακόπτης ΜΤ"]:
            if breaker_type_spinner.text == "Διασυνδετικός":
                available_gates = app.get_available_gates(selected_substation_id, True)
            else:
                available_gates = app.get_available_gates(selected_substation_id, False)
        else:
            available_gates = app.get_available_gates(selected_substation_id, False)
        gate_spinner.values = available_gates
        gate_spinner.text = (
            available_gates[0] if available_gates else "(Μη καταχωρημένο)"
        )

    substation_spinner.bind(text=on_substation_change)

    breaker_type_label = Label(text="Τύπος Διακόπτη:", size_hint_y=None, height=30)
    breaker_type_spinner = Spinner(
        text=app.BREAKER_TYPES[0],
        values=app.BREAKER_TYPES,
        size_hint_y=None,
        height=40,
    )

    def on_breaker_type_change(spinner, text):
        selected_substation_id = substation_map[substation_spinner.text]
        if element_spinner.text in ["Διακόπτης ΥΤ", "Διακόπτης ΜΤ"]:
            if text == "Διασυνδετικός":
                available_gates = app.get_available_gates(selected_substation_id, True)
            else:
                available_gates = app.get_available_gates(selected_substation_id, False)
        else:
            available_gates = app.get_available_gates(selected_substation_id, False)
        gate_spinner.values = available_gates
        gate_spinner.text = (
            available_gates[0] if available_gates else "(Μη καταχωρημένο)"
        )

    breaker_type_spinner.bind(text=on_breaker_type_change)

    breaker_category_label = Label(
        text="Κατηγορία Διακόπτη:", size_hint_y=None, height=30
    )
    initial_breaker_categories = app._get_breaker_categories_for_element_type(
        element_spinner.text
    )
    breaker_category_spinner = Spinner(
        text=initial_breaker_categories[0] if initial_breaker_categories else "SF6",
        values=initial_breaker_categories,
        size_hint_y=None,
        height=40,
    )

    model_header = BoxLayout(size_hint_y=None, height=30, spacing=5)
    model_header.add_widget(Label(text="Μοντέλο:", size_hint_x=0.7))
    add_model_btn = Button(
        text="+ Νέο Μοντέλο", size_hint_x=0.3, size_hint_y=None, height=30
    )
    model_header.add_widget(add_model_btn)
    input_layout.add_widget(model_header)

    model_spinner = Spinner(
        text="Επιλέξτε μοντέλο",
        values=["Επιλέξτε μοντέλο"],
        size_hint_y=None,
        height=40,
    )
    input_layout.add_widget(model_spinner)

    models_data = {}

    def on_breaker_category_change(spinner, text):
        current_element_type = element_spinner.text
        load_models_for_category(current_element_type, text)

    def load_models_for_category(category, selected_breaker_category=None):
        c = app.conn.cursor()
        c.execute(
            "SELECT id, model_name, manufacturer, maintenance_cycle, installation_space, breaker_category FROM element_models WHERE element_category=? ORDER BY model_name",
            (category,),
        )
        models = c.fetchall()

        models_data.clear()
        if models:
            if category in ["Διακόπτης ΜΤ", "Διακόπτης ΥΤ"]:
                if selected_breaker_category:
                    filtered_models = [m for m in models if (m[5] or "").strip().lower() == selected_breaker_category.lower()]
                else:
                    filtered_models = models
                display_names = []
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
                model_spinner.values = (display_names if display_names else ["Δεν υπάρχουν μοντέλα"])
                model_spinner.text = (display_names[0] if display_names else "Δεν υπάρχουν μοντέλα")
            else:
                display_names = []
                for m in models:
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
                model_spinner.values = display_names
                model_spinner.text = (display_names[0] if display_names else "Επιλέξτε μοντέλο")
        else:
            model_spinner.values = ["Επιλέξτε μοντέλο"]
            model_spinner.text = "Επιλέξτε μοντέλο"

    def on_element_type_change(spinner, text):
        if text in ["Διακόπτης ΥΤ", "Διακόπτης ΜΤ"]:
            breaker_category_options = app._get_breaker_categories_for_element_type(text)
            breaker_category_spinner.values = breaker_category_options
            if breaker_category_spinner.text not in breaker_category_options:
                breaker_category_spinner.text = (breaker_category_options[0] if breaker_category_options else "SF6")
            if breaker_category_label not in input_layout.children:
                idx = input_layout.children.index(model_header)
                input_layout.add_widget(breaker_category_spinner, index=idx + 1)
                input_layout.add_widget(breaker_category_label, index=idx + 2)
                breaker_category_spinner.bind(text=on_breaker_category_change)
            load_models_for_category(text, breaker_category_spinner.text)
        else:
            if breaker_category_label in input_layout.children:
                breaker_category_spinner.unbind(text=on_breaker_category_change)
                input_layout.remove_widget(breaker_category_label)
                input_layout.remove_widget(breaker_category_spinner)
            load_models_for_category(text, None)

        if text == "Διακόπτης ΜΤ":
            if breaker_type_label not in input_layout.children:
                input_layout.add_widget(
                    breaker_type_spinner,
                    index=input_layout.children.index(gate_spinner) + 2,
                )
                input_layout.add_widget(
                    breaker_type_label,
                    index=input_layout.children.index(breaker_type_spinner) + 1,
                )
                if breaker_type_spinner.text == "Διασυνδετικός":
                    available_gates = app.get_available_gates(substation_id, True)
                else:
                    available_gates = app.get_available_gates(substation_id, False)
                gate_spinner.values = available_gates
                if gate_spinner.text not in available_gates:
                    gate_spinner.text = (available_gates[0] if available_gates else "(Μη καταχωρημένο)")
        else:
            if breaker_type_label in input_layout.children:
                input_layout.remove_widget(breaker_type_label)
                input_layout.remove_widget(breaker_type_spinner)
            available_gates = app.get_available_gates(substation_id, False)
            gate_spinner.values = available_gates
            if gate_spinner.text not in available_gates:
                gate_spinner.text = (available_gates[0] if available_gates else "(Μη καταχωρημένο)")

        _derived = app._derive_voltage_level(text)
        voltage_level_spinner.values = [_derived] if _derived else list(app.VOLTAGE_LEVELS)
        voltage_level_spinner.text = _derived or "(Κενό)"

    element_spinner.bind(text=on_element_type_change)
    on_element_type_change(element_spinner, element_spinner.text)

    def on_model_selected(spinner, text):
        if text in models_data:
            model = models_data[text]
            if "manufacturer" in field_inputs:
                field_inputs["manufacturer"].text = model["manufacturer"]
            if "maintenance_cycle" in field_inputs:
                field_inputs["maintenance_cycle"].text = str(model["maintenance_cycle"])
            if "installation_space" in field_inputs:
                field_inputs["installation_space"].text = model["installation_space"]
            if "model" in field_inputs:
                field_inputs["model"].text = model["model_name"]

    model_spinner.bind(text=on_model_selected)

    def open_add_model(instance=None):
        from model_management import show_add_model_popup

        def reload_models():
            load_models_for_category(element_spinner.text)

        show_add_model_popup(
            app, callback=reload_models, category=element_spinner.text
        )

    add_model_btn.bind(on_press=open_add_model)

    field_inputs = {}
    for field in app.ELEMENT_FIELD_DEFS:
        input_layout.add_widget(
            Label(text=f"{field['label']}:", size_hint_y=None, height=30)
        )
        if field.get("type") == "spinner":
            spinner = Spinner(
                text=field["values"][0],
                values=field["values"],
                size_hint_y=None,
                height=40,
            )
            field_inputs[field["key"]] = spinner
            input_layout.add_widget(spinner)
        else:
            ti = TextInput(
                hint_text=field.get("hint", ""),
                size_hint_y=None,
                height=40,
                multiline=False,
            )
            field_inputs[field["key"]] = ti
            input_layout.add_widget(ti)

    if model_spinner.text in models_data:
        on_model_selected(model_spinner, model_spinner.text)

    scroll.add_widget(input_layout)
    layout.add_widget(scroll)

    buttons_layout = BoxLayout(size_hint_y=0.1, spacing=10)

    def add_element():
        element_type = element_spinner.text
        values = {
            key: (
                field_inputs[key].text if hasattr(field_inputs[key], "text") else field_inputs[key].text
            )
            for key in field_inputs
        }
        if "operating_status" in values and hasattr(field_inputs["operating_status"], "text"):
            values["operating_status"] = field_inputs["operating_status"].text

        if not values.get("name"):
            show_message_popup("Σφάλμα", "Παρακαλώ εισάγετε όνομα στοιχείου!")
            return

        if element_type == "Διακόπτης ΥΤ":
            is_main_switch = 1
        elif element_type == "Διακόπτης ΜΤ":
            if breaker_type_spinner.text == "Κεντρικός":
                is_main_switch = 1
            elif breaker_type_spinner.text == "Διασυνδετικός":
                is_main_switch = 2
            elif breaker_type_spinner.text == "Διακόπτης Πυκνωτών":
                is_main_switch = 3
            else:
                is_main_switch = 0
        else:
            is_main_switch = 0

        gate_value = (
            gate_spinner.text if gate_spinner.text != "(Μη καταχωρημένο)" else ""
        )

        breaker_category_value = None
        if element_type in ["Διακόπτης ΥΤ", "Διακόπτης ΜΤ"]:
            breaker_category_value = breaker_category_spinner.text

        if element_type in ["Διακόπτης ΥΤ", "Διακόπτης ΜΤ"] and (
            breaker_category_value is None or str(breaker_category_value).strip() == ""
        ):
            show_message_popup("Σφάλμα", "Παρακαλώ επιλέξτε κατηγορία διακόπτη!")
            return

        try:
            maintenance_cycle_int = int(values.get("maintenance_cycle", "0") or 0)
        except ValueError:
            show_message_popup("Σφάλμα", "Ο κύκλος συντήρησης πρέπει να είναι αριθμός!")
            return

        selected_substation_name = substation_spinner.text
        selected_substation_id = substation_map[selected_substation_name]

        c = app.conn.cursor()
        c.execute(
            "SELECT id FROM elements WHERE substation_id=? AND name=?",
            (selected_substation_id, values.get("name")),
        )
        if c.fetchone():
            show_message_popup(
                "Σφάλμα",
                f'Υπάρχει ήδη στοιχείο με όνομα "{values.get("name")}" σε αυτόν τον υποσταθμό!',
            )
            return

        model_id = (
            models_data[model_spinner.text]["id"] if model_spinner.text in models_data else None
        )

        voltage_level_value = (
            voltage_level_spinner.text if voltage_level_spinner.text != "(Κενό)" else ""
        )

        c.execute(
            "INSERT INTO elements (substation_id, element_type, name, serial_number, maintenance_date, voltage_level, manufacturer, model, model_version, installation_space, operating_status, maintenance_cycle, element_model_id, manufacture_year, gate, is_main_switch, breaker_category, power_mva) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                selected_substation_id,
                element_type,
                values.get("name", ""),
                (values.get("serial_number", "") or "").strip(),
                values.get("maintenance_date", ""),
                voltage_level_value,
                values.get("manufacturer", ""),
                values.get("model", ""),
                values.get("model_version", ""),
                values.get("installation_space", "Εσωτερικός"),
                values.get("operating_status", "Ενεργή"),
                maintenance_cycle_int,
                model_id,
                values.get("manufacture_year", ""),
                gate_value,
                is_main_switch,
                breaker_category_value,
                (None if rated_power_input.text.strip() == "" else float(rated_power_input.text.strip().replace(",", "."))),
            ),
        )
        app.conn.commit()

        try:
            rp_text = rated_power_input.text.strip()
            rp_val = None if rp_text == "" else float(rp_text.replace(",", "."))
            if model_id and rp_val is not None:
                c.execute("UPDATE element_models SET power_mva=? WHERE id=?", (rp_val, model_id))
                app.conn.commit()
        except Exception:
            pass

        popup.dismiss()
        parent_popup.dismiss()
        show_message_popup(
            "Επιτυχία",
            "Στοιχείο προστέθηκε!",
            callback=lambda: app._display_substations(selected_substation_name),
        )

    add_btn = Button(text=S["BUTTONS"]["ADD"])
    add_btn.bind(on_press=lambda x: add_element())
    buttons_layout.add_widget(add_btn)

    cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
    cancel_btn.bind(on_press=popup.dismiss)
    buttons_layout.add_widget(cancel_btn)

    layout.add_widget(buttons_layout)
    popup.content = layout
    popup.open()

