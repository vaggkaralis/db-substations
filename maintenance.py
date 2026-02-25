import os
from datetime import datetime

from strings import STRINGS as S


def _make_ui_dict(ui):
    # ensure keys exist even if some are None
    keys = (
        "Popup",
        "BoxLayout",
        "Label",
        "Button",
        "TextInput",
        "FileChooserListView",
        "Spinner",
        "ask_open_file",
        "show_message_popup",
        "parse_eml_file",
        "export_maintenances_per_substation",
    )
    return {k: ui.get(k) for k in keys}


def show_maintenance_menu_popup(app, ui):
    ui = _make_ui_dict(ui)
    Popup = ui["Popup"]
    BoxLayout = ui["BoxLayout"]
    Label = ui["Label"]
    Button = ui["Button"]

    menu_popup = Popup(title=S["MESSAGES"].get("MAINTENANCE_BUTTON", "Συντηρήσεις"), size_hint=(0.6, 0.4))
    layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    try:
        app._add_logo_to_layout(layout, height=70)
    except Exception:
        pass

    layout.add_widget(Label(text=S["MESSAGES"].get("SELECT_ACTION_PROMPT", "Επιλέξτε ενέργεια:"), size_hint_y=0.2))

    add_btn = Button(text=S["MESSAGES"].get("ADD_MAINTENANCE", "Καταχώρηση Συντήρησης"), size_hint_y=0.3)
    add_btn.bind(on_press=lambda x: app.show_maintenance_menu(parent_popup=menu_popup))
    layout.add_widget(add_btn)

    import_email_btn = Button(text=S["MESSAGES"].get("IMPORT_MAINT_FROM_EMAIL", "Εισαγωγή συντήρησης από e-mail"), size_hint_y=0.3)
    import_email_btn.bind(on_press=lambda x: app._show_import_maintenance_email_dialog(menu_popup))
    layout.add_widget(import_email_btn)

    # Export maintenances (Excel)
    try:
        export_fn = ui.get("export_maintenances_per_substation")
        if export_fn:
            export_maint_btn = Button(text=S["MESSAGES"].get("EXPORT_MAINTENANCES_EXCEL", "Εξαγωγή Συντηρήσεων (Excel)"), size_hint_y=0.3)
            export_maint_btn.bind(on_press=lambda x: (menu_popup.dismiss(), export_fn(app.conn)))
            layout.add_widget(export_maint_btn)
    except Exception:
        pass

    history_btn = Button(text=S["MESSAGES"].get("MAINT_HISTORY_LABEL", "Ιστορικό Συντηρήσεων"), size_hint_y=0.3)
    history_btn.bind(on_press=lambda x: (menu_popup.dismiss(), app.show_maintenance_history(None)))
    layout.add_widget(history_btn)

    cancel_btn = Button(text=S["BUTTONS"]["CANCEL"], size_hint_y=0.2)
    cancel_btn.bind(on_press=menu_popup.dismiss)
    layout.add_widget(cancel_btn)

    menu_popup.content = layout
    menu_popup.open()


def _show_import_maintenance_email_dialog(app, ui, parent_popup=None):
    ui = _make_ui_dict(ui)
    ask_open_file = ui["ask_open_file"]
    Popup = ui["Popup"]
    BoxLayout = ui["BoxLayout"]
    Label = ui["Label"]
    TextInput = ui["TextInput"]
    FileChooserListView = ui["FileChooserListView"]
    Button = ui["Button"]
    show_message_popup = ui["show_message_popup"]

    allow_fallback = False
    try:
        fp = ask_open_file(title="Select .eml file", filetypes=(("EML files", "*.eml"),))
    except ImportError:
        allow_fallback = True
        fp = None
    except Exception:
        fp = None

    if fp:
        try:
            if parent_popup:
                parent_popup.dismiss()
        except Exception:
            pass
        app._import_maintenance_from_email_file(fp)
        return

    if not allow_fallback:
        return

    popup = Popup(title="Εισαγωγή Συντήρησης από E-mail", size_hint=(0.9, 0.9))
    layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    path_label = Label(text="Διαδρομή αρχείου (.eml):", size_hint_y=0.1)
    layout.add_widget(path_label)

    path_row = BoxLayout(orientation="horizontal", size_hint_y=0.12, spacing=8)
    path_input = TextInput(hint_text="Διαδρομή αρχείου .emλ", multiline=False)

    def _choose_file_native(_instance=None):
        try:
            fp = ask_open_file(title="Select .eml file", filetypes=(("EML files", "*.eml"),))
        except ImportError:
            show_message_popup(
                "Σφάλμα",
                "Δεν είναι δυνατή η εμφάνιση εγγενούς διαλόγου αρχείων. Χρησιμοποιήστε τον επιλεγέα της εφαρμογής.",
            )
            return
        except Exception:
            return

        if fp:
            path_input.text = fp

    choose_btn = Button(text="Επιλογή αρχείου...", size_hint_x=None, width=180)
    choose_btn.bind(on_press=_choose_file_native)

    path_row.add_widget(path_input)
    path_row.add_widget(choose_btn)
    layout.add_widget(path_row)

    layout.add_widget(Label(text="Ή επιλέξτε από τη λίστα:", size_hint_y=0.1))
    chooser = FileChooserListView(filters=["*.eml"], path=os.path.dirname(__file__))
    layout.add_widget(chooser)

    buttons_layout = BoxLayout(size_hint_y=0.12, spacing=10)

    def import_email_file():
        file_path = (
            path_input.text.strip()
            if path_input.text.strip()
            else (chooser.selection[0] if chooser.selection else None)
        )

        if not file_path:
            show_message_popup("Σφάλμα", "Παρακαλώ εισάγετε διαδρομή ή επιλέξτε αρχείο!")
            return

        if not os.path.exists(file_path):
            show_message_popup("Σφάλμα", "Το αρχείο δεν βρέθηκε!")
            return

        if not file_path.lower().endswith(".eml"):
            show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["PLEASE_SELECT_EML"])
            return

        popup.dismiss()
        if parent_popup:
            parent_popup.dismiss()
        app._import_maintenance_from_email_file(file_path)

    import_btn = Button(text="Εισαγωγή")
    import_btn.bind(on_press=lambda x: import_email_file())
    buttons_layout.add_widget(import_btn)

    cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
    cancel_btn.bind(on_press=popup.dismiss)
    buttons_layout.add_widget(cancel_btn)

    layout.add_widget(buttons_layout)
    popup.content = layout
    popup.open()


def _import_maintenance_from_email_file(app, ui, file_path):
    parse_eml_file = ui.get("parse_eml_file")
    show_message_popup = ui.get("show_message_popup")
    try:
        payload = parse_eml_file(file_path)
    except Exception as exc:
        show_message_popup("Σφάλμα", f"Αποτυχία ανάγνωσης .emλ:\n{str(exc)}")
        return

    app._open_maintenance_from_email_payload(payload)


def _get_previous_maintenance_defaults(app, substation_id: int, date_time_value: str):
    c = app.conn.cursor()
    c.execute(
        """
            SELECT id, maintenance_type, overall_comments, responsible_id
            FROM maintenance
            WHERE substation_id = ? AND date_time < ?
            ORDER BY date_time DESC
            LIMIT 1
            """,
        (substation_id, date_time_value),
    )
    row = c.fetchone()
    if not row:
        return {}

    maintenance_id, maint_type, comments, responsible_id = row

    c.execute("SELECT person_id, role FROM maintenance_people WHERE maintenance_id=?", (maintenance_id,))
    people_rows = c.fetchall()
    crew_ids = {pid for pid, role in people_rows if role == "crew"}
    if not responsible_id:
        for pid, role in people_rows:
            if role == "responsible":
                responsible_id = pid
                break

    c.execute("SELECT element_id FROM maintenance_elements WHERE maintenance_id=?", (maintenance_id,))
    element_ids = {row[0] for row in c.fetchall()}

    return {
        "maintenance_type": maint_type,
        "overall_comments": comments,
        "responsible_id": responsible_id,
        "crew_ids": crew_ids,
        "element_ids": element_ids,
    }


def open_maintenance_from_email_payload(app, ui, payload, forced_substation=None):
    # this mirrors the logic previously on SubstationApp but keeps UI/API via app
    subject = payload.get("subject", "")
    body = payload.get("body", "")
    sender_name = payload.get("sender_name", "")
    received_at = payload.get("received_at", "")

    c = app.conn.cursor()
    c.execute("SELECT id, name FROM substations ORDER BY name")
    substations = c.fetchall()
    from popups import show_message_popup
    if not substations:
        show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["NO_SUBSTATIONS"])
        return

    substation = None
    if forced_substation:
        for sub_id, sub_name in substations:
            if sub_name == forced_substation:
                substation = (sub_id, sub_name)
                break
    if not substation:
        substation = app._find_substation_in_text(subject, substations)
    if not substation:
        substation = app._find_substation_in_text(body, substations)
    if not substation:
        app._prompt_substation_selection(substations, payload)
        return

    substation_id, substation_name = substation

    c.execute("SELECT COUNT(*) FROM elements WHERE substation_id=?", (substation_id,))
    if c.fetchone()[0] == 0:
        app._prompt_add_elements_then_continue(substation_id, substation_name, payload)
        return

    c.execute("SELECT id, name, role FROM people WHERE active=1 ORDER BY COALESCE(surname, name) COLLATE NOCASE")
    people = c.fetchall()
    if not people:
        show_message_popup(
            "Σφάλμα",
            "Δεν υπάρχουν καταχωρημένα άτομα. Παρακαλώ προσθέστε προσωπικό.",
        )
        return

    responsible_id = app._match_person_by_sender(sender_name, people)
    crew_ids = app._find_people_in_body(body, people, exclude_ids={responsible_id} if responsible_id else set())

    element_ids = app._find_elements_in_body(body, substation_id)
    incomplete_elements = set(element_ids)

    date_time_value = ""
    if received_at:
        try:
            dt = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
            date_time_value = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            date_time_value = ""
    if not date_time_value:
        date_time_value = datetime.now().strftime("%Y-%m-%d %H:%M")

    prefill = {
        "substation_id": substation_id,
        "substation_name": substation_name,
        "maintenance_type": S.get("MESSAGES", {}).get("MAINT_TYPE_DEFAULT", "Επαναληπτική συντήρηση"),
        "date_time": date_time_value,
        "overall_comments": body,
        "responsible_id": responsible_id,
        "crew_ids": crew_ids,
        "element_ids": element_ids,
        "incomplete_elements": incomplete_elements,
    }

    prev = _get_previous_maintenance_defaults(app, substation_id, date_time_value)
    if prev:
        if not prefill["responsible_id"] and prev.get("responsible_id"):
            prefill["responsible_id"] = prev.get("responsible_id")
        if not prefill["crew_ids"] and prev.get("crew_ids"):
            prefill["crew_ids"] = prev.get("crew_ids")
        if not prefill["element_ids"] and prev.get("element_ids"):
            prefill["element_ids"] = prev.get("element_ids")
            prefill["incomplete_elements"] = set(prefill["element_ids"])
        if not prefill["maintenance_type"] and prev.get("maintenance_type"):
            prefill["maintenance_type"] = prev.get("maintenance_type")
        if not prefill["overall_comments"] and prev.get("overall_comments"):
            prefill["overall_comments"] = prev.get("overall_comments")

    if not prefill["responsible_id"]:
        app._prompt_responsible_selection(people, prefill)
        return

    app.show_maintenance_menu(
        preselected_substation_name=substation_name,
        parent_popup=None,
        maintenance_id=None,
        after_save_callback=None,
        prefill_data=prefill,
    )
