"""
Model Management UI Functions for Element Models
"""

import os
from popups import ask_open_file


def show_models_management(app_instance):
    """Show model management interface"""
    from kivy.uix.popup import Popup
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.gridlayout import GridLayout
    from kivy.uix.spinner import Spinner

    c = app_instance.conn.cursor()
    c.execute(
        "SELECT id, element_category, model_name, manufacturer, maintenance_cycle, installation_space, breaker_category, manual_pdf FROM element_models ORDER BY element_category, model_name"
    )
    models = c.fetchall()

    popup = Popup(title="Διαχείριση Τύπων Στοιχείων", size_hint=(0.95, 0.9))
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    # Add model button
    add_btn = Button(text="+ Προσθήκη Νέου Μοντέλου", size_hint_y=0.1)
    add_btn.bind(on_press=lambda x: show_add_model_popup(app_instance, popup))
    main_layout.add_widget(add_btn)

    # Filter by element type
    available_categories = [row[1] for row in models]
    ordered_categories = []
    for cat in app_instance.ELEMENT_TYPES:
        if cat in available_categories and cat not in ordered_categories:
            ordered_categories.append(cat)
    for cat in available_categories:
        if cat not in ordered_categories:
            ordered_categories.append(cat)
    filter_values = ["(Όλα)"] + ordered_categories

    filter_bar = BoxLayout(size_hint_y=None, height=40, spacing=10)
    filter_bar.add_widget(Label(text="Φίλτρο Τύπου:", size_hint_x=0.25))
    filter_spinner = Spinner(text="(Όλα)", values=filter_values, size_hint_x=0.75)
    filter_bar.add_widget(filter_spinner)
    main_layout.add_widget(filter_bar)

    # Models list
    scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
    grid = GridLayout(cols=1, spacing=5, size_hint_y=None, padding=5)
    grid.bind(minimum_height=grid.setter("height"))

    def render_models(selected_category):
        grid.clear_widgets()
        filtered_models = models
        if selected_category and selected_category != "(Όλα)":
            filtered_models = [m for m in models if m[1] == selected_category]

        if filtered_models:
            # Categorize models by element type - use dynamic categorization
            from collections import OrderedDict

            categories = OrderedDict()

            # Define priority order for common categories
            priority_categories = [
                "Διακόπτης ΜΤ",
                "Διακόπτης ΥΤ",
                "Μετασχηματιστής 150/20KV",
                "Motor Drive",
            ]

            # Initialize priority categories
            for cat in priority_categories:
                categories[cat] = []

            # Group models by their actual category
            for model in filtered_models:
                (
                    model_id,
                    category,
                    model_name,
                    manufacturer,
                    cycle,
                    space,
                    breaker_cat,
                    manual_pdf,
                ) = model
                if category not in categories:
                    categories[category] = []
                categories[category].append(model)

            # Display categories with models
            for category_name, category_models in categories.items():
                if category_models:
                    # Category header
                    category_label = Label(
                        text=f"[b][size=20]{category_name}[/size][/b] ({len(category_models)})",
                        size_hint_y=None,
                        height=40,
                        bold=True,
                        markup=True,
                    )
                    grid.add_widget(category_label)

                    # For MV and HV breakers, group by breaker category (SF6, Κενού, etc.)
                    if category_name in ["Διακόπτης ΜΤ", "Διακόπτης ΥΤ"]:
                        # Group by breaker category
                        breaker_groups = OrderedDict()
                        breaker_order = (
                            app_instance._get_breaker_categories_for_element_type(
                                category_name
                            )
                        )

                        # Initialize ordered groups
                        for breaker_type in breaker_order:
                            breaker_groups[breaker_type] = []
                        breaker_groups["Άλλο"] = []  # For uncategorized

                        # Sort models into breaker groups
                        for model in category_models:
                            (
                                model_id,
                                category,
                                model_name,
                                manufacturer,
                                cycle,
                                space,
                                breaker_cat,
                                manual_pdf,
                            ) = model
                            if breaker_cat and breaker_cat in breaker_groups:
                                breaker_groups[breaker_cat].append(model)
                            else:
                                breaker_groups["Άλλο"].append(model)

                        # Display each breaker type group
                        for breaker_type, breaker_models in breaker_groups.items():
                            if breaker_models:
                                # Breaker type subheader
                                breaker_header = Label(
                                    text=f"  [b]{breaker_type}[/b] ({len(breaker_models)})",
                                    size_hint_y=None,
                                    height=35,
                                    markup=True,
                                    color=(0.3, 0.7, 1, 1),
                                )
                                grid.add_widget(breaker_header)

                                # Display models in this breaker group
                                for (
                                    model_id,
                                    category,
                                    model_name,
                                    manufacturer,
                                    cycle,
                                    space,
                                    breaker_cat,
                                    manual_pdf,
                                ) in breaker_models:
                                    model_box = BoxLayout(
                                        size_hint_y=None,
                                        height=80,
                                        spacing=5,
                                        orientation="vertical",
                                    )

                                    # Header
                                    header = BoxLayout(
                                        size_hint_y=None, height=30, spacing=5
                                    )
                                    header.add_widget(
                                        Label(
                                            text=f"    {model_name}",
                                            bold=True,
                                            size_hint_x=0.55,
                                        )
                                    )

                                    # Buttons
                                    btn_box = BoxLayout(size_hint_x=0.45, spacing=3)

                                    list_btn = Button(text="Λίστα", size_hint_x=0.25)
                                    list_btn.bind(
                                        on_press=lambda x, mid=model_id, mname=model_name: (
                                            show_model_usages(app_instance, mid, mname)
                                        )
                                    )
                                    btn_box.add_widget(list_btn)

                                    manual_label = (
                                        "Manual"
                                        if manual_pdf and os.path.exists(manual_pdf)
                                        else "Προσθήκη Manual"
                                    )
                                    manual_btn = Button(
                                        text=manual_label, size_hint_x=0.25
                                    )
                                    manual_btn.bind(
                                        on_press=lambda x, mid=model_id, path=manual_pdf, p=popup: (
                                            _handle_manual_pdf(
                                                app_instance, mid, path, p
                                            )
                                        )
                                    )
                                    btn_box.add_widget(manual_btn)

                                    edit_btn = Button(text="Επεξ.", size_hint_x=0.25)
                                    edit_btn.bind(
                                        on_press=lambda x, mid=model_id: (
                                            show_edit_model_popup(
                                                app_instance, mid, popup
                                            )
                                        )
                                    )
                                    btn_box.add_widget(edit_btn)

                                    delete_btn = Button(text="Διαγρ.", size_hint_x=0.25)
                                    delete_btn.bind(
                                        on_press=lambda x, mid=model_id: delete_model(
                                            app_instance, mid, popup
                                        )
                                    )
                                    btn_box.add_widget(delete_btn)

                                    header.add_widget(btn_box)
                                    model_box.add_widget(header)

                                    # Details
                                    details_text = f"    Κατασκευαστής: {manufacturer or '-'} | Κύκλος: {cycle} έτη | Χώρος: {space or '-'}"
                                    details = Label(
                                        text=details_text, size_hint_y=None, height=30
                                    )
                                    model_box.add_widget(details)

                                    grid.add_widget(model_box)
                    else:
                        # Display models in this category normally (not grouped by breaker type)
                        for (
                            model_id,
                            category,
                            model_name,
                            manufacturer,
                            cycle,
                            space,
                            breaker_cat,
                            manual_pdf,
                        ) in category_models:
                            model_box = BoxLayout(
                                size_hint_y=None,
                                height=80,
                                spacing=5,
                                orientation="vertical",
                            )

                            # Header
                            header = BoxLayout(size_hint_y=None, height=30, spacing=5)
                            header.add_widget(
                                Label(text=f"{model_name}", bold=True, size_hint_x=0.55)
                            )

                            # Buttons
                            btn_box = BoxLayout(size_hint_x=0.45, spacing=3)

                            list_btn = Button(text="Λίστα", size_hint_x=0.25)
                            list_btn.bind(
                                on_press=lambda x, mid=model_id, mname=model_name: (
                                    show_model_usages(app_instance, mid, mname)
                                )
                            )
                            btn_box.add_widget(list_btn)

                            manual_label = (
                                "Manual"
                                if manual_pdf and os.path.exists(manual_pdf)
                                else "Προσθήκη Manual"
                            )
                            manual_btn = Button(text=manual_label, size_hint_x=0.25)
                            manual_btn.bind(
                                on_press=lambda x, mid=model_id, path=manual_pdf, p=popup: (
                                    _handle_manual_pdf(app_instance, mid, path, p)
                                )
                            )
                            btn_box.add_widget(manual_btn)

                            edit_btn = Button(text="Επεξ.", size_hint_x=0.25)
                            edit_btn.bind(
                                on_press=lambda x, mid=model_id: show_edit_model_popup(
                                    app_instance, mid, popup
                                )
                            )
                            btn_box.add_widget(edit_btn)

                            delete_btn = Button(text="Διαγρ.", size_hint_x=0.25)
                            delete_btn.bind(
                                on_press=lambda x, mid=model_id: delete_model(
                                    app_instance, mid, popup
                                )
                            )
                            btn_box.add_widget(delete_btn)

                            header.add_widget(btn_box)
                            model_box.add_widget(header)

                            # Details
                            details_text = f"Κατασκευαστής: {manufacturer or '-'} | Κύκλος: {cycle} έτη | Χώρος: {space or '-'}"
                            if breaker_cat:
                                details_text += f" | Κατηγορία: {breaker_cat}"
                            details = Label(
                                text=details_text, size_hint_y=None, height=30
                            )
                            model_box.add_widget(details)

                            grid.add_widget(model_box)

                    # Add spacing between categories
                    spacing_widget = Label(text="", size_hint_y=None, height=20)
                    grid.add_widget(spacing_widget)
        else:
            grid.add_widget(
                Label(
                    text="Δεν υπάρχουν καταχωρημένα μοντέλα",
                    size_hint_y=None,
                    height=40,
                )
            )

    render_models(filter_spinner.text)
    filter_spinner.bind(text=lambda _spinner, text: render_models(text))

    scroll.add_widget(grid)
    main_layout.add_widget(scroll)

    # Close button
    close_btn = Button(text="Κλείσιμο", size_hint_y=0.1)
    close_btn.bind(on_press=popup.dismiss)
    main_layout.add_widget(close_btn)

    popup.content = main_layout
    popup.open()


def show_add_model_popup(app_instance, parent_popup=None, category=None, callback=None):
    """Show add new model popup

    Args:
        app_instance: The app instance with conn and ELEMENT_TYPES
        parent_popup: Parent popup to dismiss after save (optional)
        category: Pre-selected category (optional)
        callback: Function to call after successful save (optional)
    """
    from kivy.uix.popup import Popup
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.textinput import TextInput
    from kivy.uix.spinner import Spinner
    from kivy.uix.scrollview import ScrollView
    from popups import show_message_popup

    popup = Popup(title="Προσθήκη Νέου Μοντέλου", size_hint=(0.8, 0.8))
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
    layout = BoxLayout(orientation="vertical", size_hint_y=None, padding=5, spacing=8)
    layout.bind(minimum_height=layout.setter("height"))

    # Element category
    layout.add_widget(Label(text="Κατηγορία Στοιχείου:", size_hint_y=None, height=30))
    category_spinner = Spinner(
        text=category if category else app_instance.ELEMENT_TYPES[0],
        values=app_instance.ELEMENT_TYPES,
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(category_spinner)

    # Model name
    layout.add_widget(Label(text="Όνομα Μοντέλου:", size_hint_y=None, height=30))
    model_name_input = TextInput(
        hint_text="Όνομα Μοντέλου", size_hint_y=None, height=40, multiline=False
    )
    layout.add_widget(model_name_input)

    # Breaker category (conditional - placed early for better UX)
    breaker_label = Label(text="Κατηγορία Διακόπτη:", size_hint_y=None, height=30)
    initial_breaker_categories = app_instance._get_breaker_categories_for_element_type(
        category_spinner.text
    )
    breaker_spinner = Spinner(
        text=initial_breaker_categories[0] if initial_breaker_categories else "SF6",
        values=initial_breaker_categories,
        size_hint_y=None,
        height=40,
    )

    # SF6 capacity (kg) - only for SF6 breaker models
    sf6_capacity_label = Label(
        text="Χωρητικότητα SF6 (kg):", size_hint_y=None, height=30
    )
    sf6_capacity_input = TextInput(
        hint_text="kg", size_hint_y=None, height=40, multiline=False
    )

    # Manufacturer
    layout.add_widget(Label(text="Κατασκευαστής:", size_hint_y=None, height=30))
    manufacturer_input = TextInput(
        hint_text="Κατασκευαστής", size_hint_y=None, height=40, multiline=False
    )
    layout.add_widget(manufacturer_input)

    # Maintenance cycle
    layout.add_widget(
        Label(text="Κύκλος Συντήρησης (έτη):", size_hint_y=None, height=30)
    )
    cycle_input = TextInput(
        hint_text="Αριθμός ετών", size_hint_y=None, height=40, multiline=False
    )
    layout.add_widget(cycle_input)

    # Installation space
    layout.add_widget(Label(text="Χώρος Εγκατάστασης:", size_hint_y=None, height=30))
    space_spinner = Spinner(
        text="Εξωτερικός",
        values=["Εσωτερικός", "Εξωτερικός"],
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(space_spinner)

    def on_category_change(spinner, text):
        # Remove breaker fields if they exist
        if breaker_label in layout.children:
            layout.remove_widget(breaker_label)
            layout.remove_widget(breaker_spinner)
        if sf6_capacity_label in layout.children:
            layout.remove_widget(sf6_capacity_label)
            layout.remove_widget(sf6_capacity_input)

        # Add them back only if circuit breaker is selected
        if text in ["Διακόπτης ΜΤ", "Διακόπτης ΥΤ"]:
            breaker_categories = app_instance._get_breaker_categories_for_element_type(
                text
            )
            breaker_spinner.values = breaker_categories
            if breaker_spinner.text not in breaker_categories:
                breaker_spinner.text = (
                    breaker_categories[0] if breaker_categories else "SF6"
                )
            # Insert after model_name_input (which means before manufacturer in the visual order)
            idx = layout.children.index(model_name_input)
            layout.add_widget(breaker_spinner, index=idx)
            layout.add_widget(breaker_label, index=idx + 1)
            if breaker_spinner.text == "SF6":
                layout.add_widget(sf6_capacity_input, index=idx)
                layout.add_widget(sf6_capacity_label, index=idx + 1)

    def on_breaker_category_change(_spinner, _text):
        if sf6_capacity_label in layout.children:
            layout.remove_widget(sf6_capacity_label)
            layout.remove_widget(sf6_capacity_input)
        if (
            category_spinner.text in ["Διακόπτης ΜΤ", "Διακόπτης ΥΤ"]
            and breaker_spinner.text == "SF6"
        ):
            idx = layout.children.index(model_name_input)
            layout.add_widget(sf6_capacity_input, index=idx)
            layout.add_widget(sf6_capacity_label, index=idx + 1)

    category_spinner.bind(text=on_category_change)
    breaker_spinner.bind(text=on_breaker_category_change)
    on_category_change(category_spinner, category_spinner.text)

    scroll.add_widget(layout)
    main_layout.add_widget(scroll)

    # Buttons
    buttons_layout = BoxLayout(size_hint_y=0.15, spacing=10)

    def save_model():
        if not model_name_input.text.strip():
            show_message_popup("Σφάλμα", "Το όνομα μοντέλου είναι υποχρεωτικό!")
            return

        try:
            cycle = int(cycle_input.text) if cycle_input.text.strip() else 0
        except ValueError:
            show_message_popup("Σφάλμα", "Ο κύκλος συντήρησης πρέπει να είναι αριθμός!")
            return

        breaker_cat = (
            breaker_spinner.text
            if category_spinner.text in ["Διακόπτης ΜΤ", "Διακόπτης ΥΤ"]
            else ""
        )

        sf6_capacity_val = None
        if breaker_cat == "SF6":
            if not sf6_capacity_input.text.strip():
                show_message_popup(
                    "Σφάλμα",
                    "Η χωρητικότητα SF6 (kg) είναι υποχρεωτική για μοντέλα SF6!",
                )
                return
            try:
                sf6_capacity_val = float(sf6_capacity_input.text.strip())
            except ValueError:
                show_message_popup(
                    "Σφάλμα", "Η χωρητικότητα SF6 πρέπει να είναι αριθμός!"
                )
                return

        c = app_instance.conn.cursor()
        try:
            c.execute(
                "INSERT INTO element_models (element_category, model_name, manufacturer, maintenance_cycle, installation_space, breaker_category, sf6_capacity_kg) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    category_spinner.text,
                    model_name_input.text.strip(),
                    manufacturer_input.text.strip(),
                    cycle,
                    space_spinner.text,
                    breaker_cat,
                    sf6_capacity_val,
                ),
            )
            app_instance.conn.commit()
            popup.dismiss()

            # Handle different callback scenarios
            if callback:
                show_message_popup(
                    "Επιτυχία", "Το μοντέλο προστέθηκε!", callback=callback
                )
            elif parent_popup:
                parent_popup.dismiss()
                show_message_popup(
                    "Επιτυχία",
                    "Το μοντέλο προστέθηκε!",
                    callback=lambda: show_models_management(app_instance),
                )
            else:
                show_message_popup("Επιτυχία", "Το μοντέλο προστέθηκε!")
        except Exception as e:
            show_message_popup("Σφάλμα", f"Σφάλμα κατά την αποθήκευση: {str(e)}")

    save_btn = Button(text="Αποθήκευση")
    save_btn.bind(on_press=lambda x: save_model())
    buttons_layout.add_widget(save_btn)

    cancel_btn = Button(text="Ακύρωση")
    cancel_btn.bind(on_press=popup.dismiss)
    buttons_layout.add_widget(cancel_btn)

    main_layout.add_widget(buttons_layout)
    popup.content = main_layout
    popup.open()


def show_edit_model_popup(app_instance, model_id, parent_popup):
    """Show edit model popup"""
    from kivy.uix.popup import Popup
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.textinput import TextInput
    from kivy.uix.spinner import Spinner
    from kivy.uix.scrollview import ScrollView
    from popups import show_message_popup

    c = app_instance.conn.cursor()
    c.execute(
        "SELECT element_category, model_name, manufacturer, maintenance_cycle, installation_space, breaker_category, sf6_capacity_kg FROM element_models WHERE id=?",
        (model_id,),
    )
    model = c.fetchone()

    if not model:
        show_message_popup("Σφάλμα", "Το μοντέλο δεν βρέθηκε!")
        return

    category, model_name, manufacturer, cycle, space, breaker_cat, sf6_capacity = model

    popup = Popup(title=f"Επεξεργασία: {model_name}", size_hint=(0.8, 0.8))
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
    layout = BoxLayout(orientation="vertical", size_hint_y=None, padding=5, spacing=8)
    layout.bind(minimum_height=layout.setter("height"))

    # Category (read-only display)
    layout.add_widget(
        Label(text=f"Κατηγορία: {category}", size_hint_y=None, height=30, bold=True)
    )

    # Model name
    layout.add_widget(Label(text="Όνομα Μοντέλου:", size_hint_y=None, height=30))
    model_name_input = TextInput(
        text=model_name, size_hint_y=None, height=40, multiline=False
    )
    layout.add_widget(model_name_input)

    # Manufacturer
    layout.add_widget(Label(text="Κατασκευαστής:", size_hint_y=None, height=30))
    manufacturer_input = TextInput(
        text=manufacturer or "", size_hint_y=None, height=40, multiline=False
    )
    layout.add_widget(manufacturer_input)

    # Maintenance cycle
    layout.add_widget(
        Label(text="Κύκλος Συντήρησης (έτη):", size_hint_y=None, height=30)
    )
    cycle_input = TextInput(
        text=str(cycle), size_hint_y=None, height=40, multiline=False
    )
    layout.add_widget(cycle_input)

    # Installation space
    layout.add_widget(Label(text="Χώρος Εγκατάστασης:", size_hint_y=None, height=30))
    space_spinner = Spinner(
        text=space or "Εξωτερικός",
        values=["Εσωτερικός", "Εξωτερικός"],
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(space_spinner)

    # Breaker category (if applicable)
    if category in ["Διακόπτης ΜΤ", "Διακόπτης ΥΤ"]:
        layout.add_widget(
            Label(text="Κατηγορία Διακόπτη:", size_hint_y=None, height=30)
        )
        breaker_categories = app_instance._get_breaker_categories_for_element_type(
            category
        )
        breaker_spinner = Spinner(
            text=(
                breaker_cat
                if breaker_cat in breaker_categories
                else (breaker_categories[0] if breaker_categories else "SF6")
            ),
            values=breaker_categories,
            size_hint_y=None,
            height=40,
        )
        layout.add_widget(breaker_spinner)
    else:
        breaker_spinner = None

    # SF6 capacity (kg) - only for SF6 breaker models
    sf6_capacity_input = None
    if category in ["Διακόπτης ΜΤ", "Διακόπτης ΥΤ"] and breaker_cat == "SF6":
        layout.add_widget(
            Label(text="Χωρητικότητα SF6 (kg):", size_hint_y=None, height=30)
        )
        sf6_capacity_input = TextInput(
            text=str(sf6_capacity) if sf6_capacity is not None else "",
            size_hint_y=None,
            height=40,
            multiline=False,
        )
        layout.add_widget(sf6_capacity_input)

    scroll.add_widget(layout)
    main_layout.add_widget(scroll)

    # Buttons
    buttons_layout = BoxLayout(size_hint_y=0.15, spacing=10)

    def save_changes():
        if not model_name_input.text.strip():
            show_message_popup("Σφάλμα", "Το όνομα μοντέλου είναι υποχρεωτικό!")
            return

        try:
            cycle_val = int(cycle_input.text) if cycle_input.text.strip() else 0
        except ValueError:
            show_message_popup("Σφάλμα", "Ο κύκλος συντήρησης πρέπει να είναι αριθμός!")
            return

        breaker_cat_val = breaker_spinner.text if breaker_spinner else ""

        sf6_capacity_val = None
        if breaker_cat_val == "SF6":
            if not sf6_capacity_input or not sf6_capacity_input.text.strip():
                show_message_popup(
                    "Σφάλμα",
                    "Η χωρητικότητα SF6 (kg) είναι υποχρεωτική για μοντέλα SF6!",
                )
                return
            try:
                sf6_capacity_val = float(sf6_capacity_input.text.strip())
            except ValueError:
                show_message_popup(
                    "Σφάλμα", "Η χωρητικότητα SF6 πρέπει να είναι αριθμός!"
                )
                return

        c = app_instance.conn.cursor()

        # Update the model
        c.execute(
            "UPDATE element_models SET model_name=?, manufacturer=?, maintenance_cycle=?, installation_space=?, breaker_category=?, sf6_capacity_kg=? WHERE id=?",
            (
                model_name_input.text.strip(),
                manufacturer_input.text.strip(),
                cycle_val,
                space_spinner.text,
                breaker_cat_val,
                sf6_capacity_val,
                model_id,
            ),
        )

        # Update all linked elements with the new model name
        new_model_display = model_name_input.text.strip()

        c.execute(
            "UPDATE elements SET model=?, manufacturer=?, maintenance_cycle=?, installation_space=? WHERE element_model_id=?",
            (
                new_model_display,
                manufacturer_input.text.strip(),
                cycle_val,
                space_spinner.text,
                model_id,
            ),
        )

        app_instance.conn.commit()
        popup.dismiss()
        parent_popup.dismiss()
        show_message_popup(
            "Επιτυχία",
            "Το μοντέλο και όλα τα συνδεδεμένα στοιχεία ενημερώθηκαν!",
            callback=lambda: show_models_management(app_instance),
        )

    save_btn = Button(text="Αποθήκευση")
    save_btn.bind(on_press=lambda x: save_changes())
    buttons_layout.add_widget(save_btn)

    cancel_btn = Button(text="Ακύρωση")
    cancel_btn.bind(on_press=popup.dismiss)
    buttons_layout.add_widget(cancel_btn)

    main_layout.add_widget(buttons_layout)
    popup.content = main_layout
    popup.open()


def _handle_manual_pdf(app_instance, model_id, manual_pdf, parent_popup=None):
    if manual_pdf and os.path.exists(manual_pdf):
        _open_manual_pdf(manual_pdf)
    else:
        _select_manual_pdf(app_instance, model_id, parent_popup)


def _open_manual_pdf(pdf_path):
    from popups import show_message_popup

    if not pdf_path or not os.path.exists(pdf_path):
        show_message_popup("Σφάλμα", "Το αρχείο δεν βρέθηκε!")
        return
    try:
        import subprocess
        import sys

        if sys.platform == "win32":
            os.startfile(pdf_path)
        elif sys.platform == "darwin":
            subprocess.call(["open", pdf_path])
        else:
            subprocess.call(["xdg-open", pdf_path])
    except Exception as exc:
        show_message_popup("Σφάλμα", f"Αποτυχία ανοίγματος PDF:\n{str(exc)}")


def _select_manual_pdf(app_instance, model_id, parent_popup=None):
    from kivy.uix.popup import Popup
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.textinput import TextInput
    from kivy.uix.filechooser import FileChooserListView
    from popups import show_message_popup

    # Try native desktop dialog first
    allow_fallback = False
    try:
        fp = ask_open_file(title="Select Manual PDF", filetypes=(("PDF files", "*.pdf"),))
    except ImportError:
        allow_fallback = True
        fp = None
    except Exception:
        fp = None

    if fp:
        if not os.path.exists(fp):
            show_message_popup("Σφάλμα", "Το αρχείο δεν βρέθηκε!")
            return
        if not fp.lower().endswith(".pdf"):
            show_message_popup("Σφάλμα", "Παρακαλώ επιλέξτε αρχείο PDF!")
            return
        c = app_instance.conn.cursor()
        c.execute(
            "UPDATE models SET manual_pdf=? WHERE id=?",
            (fp, model_id),
        )
        app_instance.conn.commit()
        if parent_popup:
            try:
                parent_popup.dismiss()
            except Exception:
                pass
        return

    if not allow_fallback:
        # user cancelled native dialog -> do nothing
        return

    popup = Popup(title="Επιλογή Manual PDF", size_hint=(0.9, 0.9))
    layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    path_label = Label(text="Διαδρομή αρχείου:", size_hint_y=0.1)
    layout.add_widget(path_label)

    path_input = TextInput(
        hint_text="Διαδρομή αρχείου", size_hint_y=0.12, multiline=False
    )
    layout.add_widget(path_input)

    layout.add_widget(Label(text="Ή επιλέξτε από τη λίστα:", size_hint_y=0.1))
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
                "Σφάλμα", "Παρακαλώ εισάγετε διαδρομή ή επιλέξτε αρχείο!"
            )
            return

        if not os.path.exists(file_path):
            show_message_popup("Σφάλμα", "Το αρχείο δεν βρέθηκε!")
            return

        if not file_path.lower().endswith(".pdf"):
            show_message_popup("Σφάλμα", "Παρακαλώ επιλέξτε αρχείο PDF!")
            return

        c = app_instance.conn.cursor()
        c.execute(
            "UPDATE element_models SET manual_pdf=? WHERE id=?", (file_path, model_id)
        )
        app_instance.conn.commit()
        popup.dismiss()

        if parent_popup:
            parent_popup.dismiss()
        show_models_management(app_instance)

    save_btn = Button(text="Αποθήκευση")
    save_btn.bind(on_press=lambda x: save_file())
    buttons_layout.add_widget(save_btn)

    cancel_btn = Button(text="Ακύρωση")
    cancel_btn.bind(on_press=popup.dismiss)
    buttons_layout.add_widget(cancel_btn)

    layout.add_widget(buttons_layout)
    popup.content = layout
    popup.open()


def delete_model(app_instance, model_id, parent_popup):
    """Delete a model"""
    from kivy.uix.popup import Popup
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from popups import show_message_popup

    c = app_instance.conn.cursor()

    # Check if model is in use
    c.execute("SELECT COUNT(*) FROM elements WHERE element_model_id=?", (model_id,))
    count = c.fetchone()[0]

    if count > 0:
        show_message_popup(
            "Σφάλμα",
            f"Το μοντέλο χρησιμοποιείται σε {count} στοιχεία και δεν μπορεί να διαγραφεί!",
        )
        return

    confirm_popup = Popup(title="Επιβεβαίωση Διαγραφής", size_hint=(0.6, 0.3))
    layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    warning_label = Label(
        text="Είστε σίγουροι ότι θέλετε να διαγράψετε\nαυτό το μοντέλο;",
        size_hint_y=0.6,
    )
    layout.add_widget(warning_label)

    buttons_layout = BoxLayout(size_hint_y=0.3, spacing=10)

    def confirm():
        confirm_popup.dismiss()
        c.execute("DELETE FROM element_models WHERE id=?", (model_id,))
        app_instance.conn.commit()
        parent_popup.dismiss()
        show_message_popup(
            "Ολοκληρώθηκε",
            "Το μοντέλο διαγράφηκε!",
            callback=lambda: show_models_management(app_instance),
        )

    yes_btn = Button(text="ΝΑΙ", color=(1, 0, 0, 1))
    yes_btn.bind(on_press=lambda x: confirm())
    buttons_layout.add_widget(yes_btn)

    no_btn = Button(text="ΟΧΙ")
    no_btn.bind(on_press=confirm_popup.dismiss)
    buttons_layout.add_widget(no_btn)

    layout.add_widget(buttons_layout)
    confirm_popup.content = layout
    confirm_popup.open()


def jump_to_substation(app_instance, substation_name, current_popup):
    """Jump to substation elements view and close current popup"""
    current_popup.dismiss()
    # Call the display function from app_instance
    app_instance._display_substations(substation_name)


def show_model_usages(app_instance, model_id, model_name):
    """Show list of substations and elements using this model"""
    from kivy.uix.popup import Popup
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.gridlayout import GridLayout

    c = app_instance.conn.cursor()

    # Get all elements using this model with full details
    c.execute(
        """
        SELECT e.id, e.element_type, e.name, e.serial_number, e.maintenance_date, 
               e.manufacturer, e.installation_space, e.operating_status, e.maintenance_cycle, 
               e.breaker_category, e.manufacture_year,
               s.name as substation_name, s.id as substation_id
        FROM elements e
        JOIN substations s ON e.substation_id = s.id
        WHERE e.element_model_id = ?
        ORDER BY s.name, e.element_type, e.name
    """,
        (model_id,),
    )

    usages = c.fetchall()

    popup = Popup(title=f"Χρήση Μοντέλου: {model_name}", size_hint=(0.95, 0.9))
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    if usages:
        # Header info
        info_label = Label(
            text=f"Το μοντέλο χρησιμοποιείται σε {len(usages)} στοιχεία:",
            size_hint_y=None,
            height=35,
            bold=True,
        )
        main_layout.add_widget(info_label)

        # Scrollable list
        scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
        grid = GridLayout(cols=1, spacing=5, size_hint_y=None, padding=5)
        grid.bind(minimum_height=grid.setter("height"))

        # Group by substation
        current_substation = None
        for elem_data in usages:
            (
                elem_id,
                elem_type,
                elem_name,
                serial_number,
                maintenance_date,
                manufacturer,
                installation_space,
                operating_status,
                maintenance_cycle,
                breaker_category,
                manufacture_year,
                substation_name,
                substation_id,
            ) = elem_data

            # Substation header (only when it changes)
            if current_substation != substation_name:
                current_substation = substation_name

                # Create a layout for substation header with button
                substation_header_layout = BoxLayout(
                    size_hint_y=None, height=40, spacing=10
                )

                substation_header = Label(
                    text=f"[b][size=18]{substation_name}[/size][/b]",
                    size_hint_x=0.7,
                    markup=True,
                    halign="left",
                    valign="middle",
                )
                substation_header.bind(size=substation_header.setter("text_size"))
                substation_header_layout.add_widget(substation_header)

                # Add button to jump to substation elements view
                jump_btn = Button(text="Μετάβαση στον Υποσταθμό", size_hint_x=0.3)
                jump_btn.bind(
                    on_press=lambda x, sname=substation_name, p=popup: (
                        jump_to_substation(app_instance, sname, p)
                    )
                )
                substation_header_layout.add_widget(jump_btn)

                grid.add_widget(substation_header_layout)

            # Element details box
            elem_box = BoxLayout(
                size_hint_y=None,
                height=90,
                spacing=5,
                orientation="vertical",
                padding=(10, 0, 0, 0),
            )

            # Element name and type (bold, larger)
            breaker_info = f" | {breaker_category}" if breaker_category else ""
            name_text = (
                f"[b][size=16]{elem_name}[/size][/b] - {elem_type}{breaker_info}"
            )
            name_label = Label(
                text=name_text,
                size_hint_y=None,
                height=25,
                markup=True,
                halign="left",
                valign="middle",
            )
            name_label.bind(size=name_label.setter("text_size"))
            elem_box.add_widget(name_label)

            # Serial number and manufacture year
            manufacture_info = (
                f" | Έτος: {manufacture_year}" if manufacture_year else ""
            )
            sn_text = f"S/N: {serial_number or '-'}{manufacture_info}"
            sn_label = Label(
                text=sn_text,
                size_hint_y=None,
                height=20,
                halign="left",
                valign="middle",
            )
            sn_label.bind(size=sn_label.setter("text_size"))
            elem_box.add_widget(sn_label)

            # Manufacturer, installation space, operating status
            details_text = f"Κατ.: {manufacturer or '-'} | Χώρος: {installation_space or '-'} | Κατάστ.: {operating_status or 'Ενεργή'}"
            details_label = Label(
                text=details_text,
                size_hint_y=None,
                height=20,
                halign="left",
                valign="middle",
            )
            details_label.bind(size=details_label.setter("text_size"))
            elem_box.add_widget(details_label)

            # Maintenance info
            maint_text = f"Κύκλος: {maintenance_cycle or '-'} | Τελ. Συντ.: {maintenance_date or '-'}"
            maint_label = Label(
                text=maint_text,
                size_hint_y=None,
                height=20,
                halign="left",
                valign="middle",
            )
            maint_label.bind(size=maint_label.setter("text_size"))
            elem_box.add_widget(maint_label)

            grid.add_widget(elem_box)

        scroll.add_widget(grid)
        main_layout.add_widget(scroll)
    else:
        # No usages found
        no_usage_label = Label(
            text="Το μοντέλο δεν χρησιμοποιείται σε κανένα στοιχείο.", size_hint_y=0.7
        )
        main_layout.add_widget(no_usage_label)

    # Close button
    close_btn = Button(text="Κλείσιμο", size_hint_y=0.1)
    close_btn.bind(on_press=popup.dismiss)
    main_layout.add_widget(close_btn)

    popup.content = main_layout
    popup.open()
