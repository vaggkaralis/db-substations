import os

from email_eml_parser import parse_eml_file
from isolation_importer import (
    match_element_ids_from_text,
    match_substation,
    parse_isolation_request_text,
)
from onedrive_hybrid_storage import ensure_isolation_request_storage
from popups import ask_open_file, show_message_popup
from strings_proxy import STRINGS as S
from ui.shared import IconOnlyButton


_STATUS_VALUES = ["Requested", "Accepted", "Cancelled"]


def _get_substations(app):
    c = app.conn.cursor()
    c.execute("SELECT id, name FROM substations ORDER BY name")
    return c.fetchall()


def _get_elements_for_substation(app, substation_id):
    c = app.conn.cursor()
    c.execute(
        """
        SELECT id, name, serial_number, element_type, gate
        FROM elements
        WHERE substation_id = ?
        ORDER BY gate, name
        """,
        (substation_id,),
    )
    return c.fetchall()


def _group_elements_by_gate(elements):
    groups = {}
    for element_id, name, serial_number, element_type, gate in elements:
        gate_name = gate or S["MESSAGES"].get("UNREGISTERED_GATE", "Μη δηλωμένη πύλη")
        groups.setdefault(gate_name, []).append(
            (element_id, name, serial_number, element_type, gate_name)
        )
    return groups


def _prefill_imported_isolation(app, parent_popup, raw_text, status, attachment_paths=None):
    parsed = parse_isolation_request_text(raw_text)
    substations = _get_substations(app)
    matched_substation = match_substation(app, raw_text, substations)

    prefill = {
        "status": status,
        "notes": parsed.get("notes") or "",
        "start_datetime": parsed.get("start_datetime") or "",
        "end_datetime": parsed.get("end_datetime") or "",
        "request_file_path": (attachment_paths or [""])[0] if attachment_paths else "",
    }

    if matched_substation:
        substation_id, substation_name = matched_substation
        prefill["substation_id"] = substation_id
        prefill["substation_name"] = substation_name
        element_rows = _get_elements_for_substation(app, substation_id)
        matched_element_ids, _matched_phrases = match_element_ids_from_text(raw_text, element_rows)
        if not matched_element_ids and getattr(app, "_find_elements_in_body", None):
            matched_element_ids = sorted(app._find_elements_in_body(raw_text, substation_id))
        prefill["element_ids"] = matched_element_ids

    show_add_isolation_request(app, parent_popup, prefill_data=prefill)


def import_isolation_request_from_payload(app, payload, parent_popup=None, status="Requested"):
    raw_text = payload.get("body") or ""
    attachment_paths = payload.get("attachment_paths") or []
    _prefill_imported_isolation(app, parent_popup, raw_text, status, attachment_paths=attachment_paths)


def import_isolation_request_from_eml(app, file_path, parent_popup=None, status="Requested"):
    try:
        payload = parse_eml_file(file_path)
    except Exception as exc:
        show_message_popup(S["TITLES"].get("ERROR", "Σφάλμα"), f"Αποτυχία ανάγνωσης email:\n{exc}")
        return

    import_isolation_request_from_payload(app, payload, parent_popup=parent_popup, status=status)


def _show_import_text_popup(app, parent_popup, status):
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.textinput import TextInput

    popup = Popup(title="Εισαγωγή απομόνωσης από κείμενο", size_hint=(0.9, 0.85))
    layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
    layout.add_widget(
        Label(
            text="Επικολλήστε το κείμενο της αίτησης. Θα γίνει ανάλυση και στη συνέχεια θα ανοίξει η φόρμα για έλεγχο και διόρθωση.",
            size_hint_y=None,
            height=50,
        )
    )
    text_input = TextInput(multiline=True)
    layout.add_widget(text_input)

    buttons = BoxLayout(size_hint_y=None, height=45, spacing=10)

    def do_import():
        raw_text = text_input.text.strip()
        if not raw_text:
            show_message_popup(S["TITLES"].get("ERROR", "Σφάλμα"), "Δεν δόθηκε κείμενο για εισαγωγή.")
            return
        popup.dismiss()
        _prefill_imported_isolation(app, parent_popup, raw_text, status)

    import_btn = Button(text=S["BUTTONS"].get("IMPORT", "Εισαγωγή"))
    import_btn.bind(on_press=lambda _x: do_import())
    buttons.add_widget(import_btn)
    cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
    cancel_btn.bind(on_press=popup.dismiss)
    buttons.add_widget(cancel_btn)
    layout.add_widget(buttons)
    popup.content = layout
    popup.open()


def _import_from_eml(app, parent_popup, status):
    file_path = ask_open_file(title="Select .eml file", filetypes=(("EML files", "*.eml"),))
    if not file_path:
        return
    import_isolation_request_from_eml(app, file_path, parent_popup=parent_popup, status=status)


def show_import_isolation_request(app, parent_popup=None):
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.spinner import Spinner

    popup = Popup(title="Εισαγωγή αίτησης απομόνωσης", size_hint=(0.7, 0.45))
    layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
    layout.add_widget(Label(text="Ορίστε κατάσταση για την εισαγόμενη απομόνωση:", size_hint_y=None, height=35))
    status_spinner = Spinner(text="Requested", values=_STATUS_VALUES, size_hint_y=None, height=40)
    layout.add_widget(status_spinner)

    buttons = BoxLayout(size_hint_y=None, height=50, spacing=10)
    text_btn = Button(text="Από κείμενο")
    text_btn.bind(on_press=lambda _x: (popup.dismiss(), _show_import_text_popup(app, parent_popup, status_spinner.text)))
    buttons.add_widget(text_btn)

    email_btn = Button(text="Από e-mail (.eml)")
    email_btn.bind(on_press=lambda _x: (popup.dismiss(), _import_from_eml(app, parent_popup, status_spinner.text)))
    buttons.add_widget(email_btn)
    layout.add_widget(buttons)

    cancel_btn = Button(text=S["BUTTONS"]["CANCEL"], size_hint_y=None, height=45)
    cancel_btn.bind(on_press=popup.dismiss)
    layout.add_widget(cancel_btn)
    popup.content = layout
    popup.open()


def show_isolation_requests(app, instance=None):
    from calendar import monthrange
    from datetime import datetime, timedelta
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.gridlayout import GridLayout
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView

    font_kwargs = app._get_ui_font_kwargs()

    popup = Popup(title="Αιτήσεις Απομόνωσης", size_hint=(0.95, 0.95))
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    current_date = datetime.now()
    current_month = [current_date.month]
    current_year = [current_date.year]

    controls_layout = BoxLayout(size_hint_y=0.1, spacing=10)
    prev_btn = Button(text="◀ Προηγούμενος", **font_kwargs)
    next_btn = Button(text="Επόμενος ▶", **font_kwargs)
    today_btn = Button(text="Σήμερα", **font_kwargs)
    add_btn = Button(text="+ Νέα Αίτηση", **font_kwargs)
    import_btn = Button(text="Εισαγωγή", **font_kwargs)

    controls_layout.add_widget(prev_btn)
    controls_layout.add_widget(today_btn)
    controls_layout.add_widget(next_btn)
    controls_layout.add_widget(add_btn)
    controls_layout.add_widget(import_btn)
    main_layout.add_widget(controls_layout)

    header_label = Label(text="", size_hint_y=0.08, font_size="20sp", bold=True)
    main_layout.add_widget(header_label)

    calendar_container = BoxLayout(orientation="vertical")
    main_layout.add_widget(calendar_container)

    legend_layout = BoxLayout(size_hint_y=0.08, spacing=10, padding=[10, 5])
    legend_layout.add_widget(Label(text="", size_hint_x=0.25, **font_kwargs))
    legend_layout.add_widget(Label(text="● Αιτήθηκε", size_hint_x=0.22, color=(1, 0.85, 0, 1), **font_kwargs))
    legend_layout.add_widget(Label(text="● Εγκρίθηκε", size_hint_x=0.22, color=(0.2, 0.8, 0.2, 1), **font_kwargs))
    legend_layout.add_widget(Label(text="● Ακυρώθηκε", size_hint_x=0.22, color=(0.9, 0.2, 0.2, 1), **font_kwargs))
    legend_layout.add_widget(Label(text="", size_hint_x=0.09, **font_kwargs))
    main_layout.add_widget(legend_layout)

    def load_calendar():
        calendar_container.clear_widgets()
        month = current_month[0]
        year = current_year[0]
        month_names = [
            "",
            "Ιανουάριος",
            "Φεβρουάριος",
            "Μάρτιος",
            "Απρίλιος",
            "Μάιος",
            "Ιούνιος",
            "Ιούλιος",
            "Αύγουστος",
            "Σεπτέμβριος",
            "Οκτώβριος",
            "Νοέμβριος",
            "Δεκέμβριος",
        ]
        header_label.text = f"{month_names[month]} {year}"

        c = app.conn.cursor()
        first_day = f"{year}-{month:02d}-01 00:00"
        last_day_num = monthrange(year, month)[1]
        last_day = f"{year}-{month:02d}-{last_day_num} 23:59"

        c.execute(
            """
            SELECT ir.id, ir.substation_id, s.name, ir.start_datetime, ir.end_datetime,
                   ir.status, ir.notes
            FROM isolation_requests ir
            JOIN substations s ON ir.substation_id = s.id
            WHERE (ir.start_datetime <= ? AND ir.end_datetime >= ?)
               OR (ir.start_datetime >= ? AND ir.start_datetime <= ?)
            ORDER BY ir.start_datetime
            """,
            (last_day, first_day, first_day, last_day),
        )
        requests = c.fetchall()

        requests_by_day = {}
        for req_id, sub_id, sub_name, start_dt, end_dt, status, notes in requests:
            try:
                start = datetime.strptime(start_dt, "%Y-%m-%d %H:%M")
                end = datetime.strptime(end_dt, "%Y-%m-%d %H:%M")
                current = start
                while current <= end:
                    if current.year == year and current.month == month:
                        requests_by_day.setdefault(current.day, [])
                        if not any(existing[0] == req_id for existing in requests_by_day[current.day]):
                            requests_by_day[current.day].append((req_id, sub_id, sub_name, start_dt, end_dt, status, notes))
                    current += timedelta(days=1)
            except Exception:
                continue

        calendar_grid = GridLayout(cols=7, spacing=2)
        for day_name in ["Δευ", "Τρί", "Τετ", "Πέμ", "Παρ", "Σάβ", "Κυρ"]:
            calendar_grid.add_widget(Label(text=day_name, size_hint_y=None, height=30, bold=True))

        first_weekday = datetime(year, month, 1).weekday()
        days_in_month = monthrange(year, month)[1]

        for _ in range(first_weekday):
            calendar_grid.add_widget(Label(text=""))

        for day in range(1, days_in_month + 1):
            day_box = BoxLayout(orientation="vertical", size_hint_y=None, height=100)
            day_box.add_widget(Label(text=str(day), size_hint_y=0.3, bold=True))

            if day in requests_by_day:
                scroll = ScrollView(size_hint_y=0.7)
                requests_layout = GridLayout(cols=1, size_hint_y=None, spacing=2, padding=2)
                requests_layout.bind(minimum_height=requests_layout.setter("height"))

                for req_id, _sub_id, sub_name, _start_dt, _end_dt, status, _notes in requests_by_day[day]:
                    if status == "Accepted":
                        color = (0.2, 0.8, 0.2, 1)
                    elif status == "Cancelled":
                        color = (0.8, 0.2, 0.2, 1)
                    else:
                        color = (0.8, 0.8, 0.2, 1)

                    req_btn = Button(
                        text=f"● {sub_name[:15]}",
                        size_hint_y=None,
                        height=30,
                        background_color=color,
                        **font_kwargs,
                    )
                    req_btn.bind(
                        on_press=lambda _x, r_id=req_id, popup_ref=popup: show_isolation_request_details(app, r_id, popup_ref)
                    )
                    requests_layout.add_widget(req_btn)

                scroll.add_widget(requests_layout)
                day_box.add_widget(scroll)
            else:
                day_box.add_widget(Label(text="", size_hint_y=0.7))

            calendar_grid.add_widget(day_box)

        calendar_container.add_widget(calendar_grid)

    def _go_prev(_x):
        if current_month[0] == 1:
            current_month[0] = 12
            current_year[0] -= 1
        else:
            current_month[0] -= 1
        load_calendar()

    def _go_next(_x):
        if current_month[0] == 12:
            current_month[0] = 1
            current_year[0] += 1
        else:
            current_month[0] += 1
        load_calendar()

    prev_btn.bind(on_press=_go_prev)
    next_btn.bind(on_press=_go_next)
    today_btn.bind(
        on_press=lambda _x: (
            current_month.__setitem__(0, datetime.now().month),
            current_year.__setitem__(0, datetime.now().year),
            load_calendar(),
        )
    )
    add_btn.bind(on_press=lambda _x: show_add_isolation_request(app, popup))
    import_btn.bind(on_press=lambda _x: show_import_isolation_request(app, popup))

    load_calendar()

    close_btn = Button(text=S["BUTTONS"]["CLOSE"], size_hint_y=0.08)
    close_btn.bind(on_press=popup.dismiss)
    main_layout.add_widget(close_btn)
    popup.content = main_layout
    popup.open()


def _show_isolation_request_form(app, parent_popup, request_id=None, prefill_data=None):
    from datetime import datetime, timedelta
    from kivy.uix.anchorlayout import AnchorLayout
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.checkbox import CheckBox
    from kivy.uix.gridlayout import GridLayout
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.spinner import Spinner
    from kivy.uix.textinput import TextInput
    from kivy.uix.widget import Widget
    from reports import open_file, show_confirm

    prefill_data = prefill_data or {}
    substations = _get_substations(app)
    if not substations:
        show_message_popup(S["TITLES"].get("ERROR", "Σφάλμα"), S["MESSAGES"].get("NO_SUBSTATIONS", "Δεν υπάρχουν υποσταθμοί!"))
        return

    c = app.conn.cursor()
    request_record = None
    selected_element_ids = set(prefill_data.get("element_ids") or [])
    existing_attachment_path = str(prefill_data.get("request_file_path") or "").strip()
    storage_folder_path = ""
    is_new_request = request_id is None

    if request_id:
        c.execute(
            """
            SELECT ir.id, ir.substation_id, s.name, ir.start_datetime, ir.end_datetime,
                   ir.status, ir.notes, ir.request_file_path, ir.storage_folder_path,
                   ir.created_at, ir.updated_at
            FROM isolation_requests ir
            JOIN substations s ON s.id = ir.substation_id
            WHERE ir.id = ?
            """,
            (request_id,),
        )
        request_record = c.fetchone()
        if not request_record:
            show_message_popup(S["TITLES"].get("ERROR", "Σφάλμα"), "Η αίτηση απομόνωσης δεν βρέθηκε.")
            return
        c.execute("SELECT element_id FROM isolation_request_elements WHERE request_id=?", (request_id,))
        selected_element_ids = {row[0] for row in c.fetchall()}
        existing_attachment_path = str(request_record[7] or "").strip()
        storage_folder_path = str(request_record[8] or "").strip()

    title = "Επεξεργασία Αίτησης Απομόνωσης" if request_id else "Νέα Αίτηση Απομόνωσης"
    popup = Popup(title=title, size_hint=(0.88, 0.95))
    main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
    scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
    content = GridLayout(cols=1, spacing=10, size_hint_y=None, padding=5)
    content.bind(minimum_height=content.setter("height"))

    substation_map = {name: sub_id for sub_id, name in substations}
    initial_substation = substations[0][1]
    if request_record:
        initial_substation = request_record[2]
    elif prefill_data.get("substation_name") in substation_map:
        initial_substation = prefill_data["substation_name"]

    content.add_widget(Label(text="Υποσταθμός:", size_hint_y=None, height=30, bold=True))
    substation_row = BoxLayout(size_hint_y=None, height=40, spacing=5)
    substation_input = TextInput(text=initial_substation, readonly=True, multiline=False, size_hint_x=0.72)
    select_sub_btn = Button(text="Επιλογή", size_hint_x=0.28)
    substation_row.add_widget(substation_input)
    substation_row.add_widget(select_sub_btn)
    content.add_widget(substation_row)

    def _on_select_substation(sub_name):
        substation_input.text = sub_name
        load_elements(sub_name)

    select_sub_btn.bind(
        on_press=lambda _x: app._show_substation_selection_window_with_callback(
            popup,
            substations,
            on_select=_on_select_substation,
            title="Επιλογή Υποσταθμού",
        )
    )

    content.add_widget(Label(text="Ημ/νία & Ώρα Έναρξης:", size_hint_y=None, height=30, bold=True))
    start_default = (
        request_record[3]
        if request_record
        else prefill_data.get("start_datetime") or datetime.now().strftime("%Y-%m-%d %H:%M")
    )
    start_input = TextInput(text=start_default, hint_text="YYYY-MM-DD HH:MM", multiline=False, size_hint_y=None, height=35)
    content.add_widget(start_input)

    start_presets = BoxLayout(size_hint_y=None, height=35, spacing=5)
    start_presets.add_widget(Button(text="Σήμερα 08:00", on_press=lambda _x: setattr(start_input, "text", datetime.now().strftime("%Y-%m-%d 08:00"))))
    start_presets.add_widget(Button(text="Σήμερα 18:00", on_press=lambda _x: setattr(start_input, "text", datetime.now().strftime("%Y-%m-%d 18:00"))))
    content.add_widget(start_presets)

    content.add_widget(Label(text="Ημ/νία & Ώρα Λήξης:", size_hint_y=None, height=30, bold=True))
    end_default = (
        request_record[4]
        if request_record
        else prefill_data.get("end_datetime") or (datetime.now() + timedelta(hours=4)).strftime("%Y-%m-%d %H:%M")
    )
    end_input = TextInput(text=end_default, hint_text="YYYY-MM-DD HH:MM", multiline=False, size_hint_y=None, height=35)
    content.add_widget(end_input)

    duration_row = BoxLayout(size_hint_y=None, height=35, spacing=5)

    def _set_duration(hours):
        try:
            start_dt = datetime.strptime(start_input.text.strip(), "%Y-%m-%d %H:%M")
            end_input.text = (start_dt + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass

    duration_row.add_widget(Button(text="2 ώρες", on_press=lambda _x: _set_duration(2)))
    duration_row.add_widget(Button(text="4 ώρες", on_press=lambda _x: _set_duration(4)))
    duration_row.add_widget(Button(text="1 ημέρα", on_press=lambda _x: _set_duration(24)))
    content.add_widget(duration_row)

    content.add_widget(Label(text="Κατάσταση:", size_hint_y=None, height=30, bold=True))
    status_default = request_record[5] if request_record else prefill_data.get("status") or "Requested"
    status_spinner = Spinner(text=status_default, values=_STATUS_VALUES, size_hint_y=None, height=40)
    content.add_widget(status_spinner)

    content.add_widget(Label(text="Συνημμένη αίτηση/αρχείο:", size_hint_y=None, height=30, bold=True))
    attachment_row = BoxLayout(size_hint_y=None, height=40, spacing=5)
    attachment_input = TextInput(
        text=existing_attachment_path,
        hint_text="Επιλέξτε αρχείο αίτησης",
        multiline=False,
        readonly=True,
        size_hint_x=0.56,
    )
    choose_attachment_btn = Button(text="Επιλογή", size_hint_x=0.16)
    open_attachment_btn = Button(text="Άνοιγμα", size_hint_x=0.16)
    clear_attachment_btn = Button(text="Καθαρισμός", size_hint_x=0.12)
    attachment_row.add_widget(attachment_input)
    attachment_row.add_widget(choose_attachment_btn)
    attachment_row.add_widget(open_attachment_btn)
    attachment_row.add_widget(clear_attachment_btn)
    content.add_widget(attachment_row)

    choose_attachment_btn.bind(
        on_press=lambda _x: setattr(
            attachment_input,
            "text",
            ask_open_file(title="Select request file", filetypes=(("All files", "*.*"),)) or attachment_input.text,
        )
    )
    open_attachment_btn.bind(
        on_press=lambda _x: (
            open_file(attachment_input.text.strip())
            if attachment_input.text.strip()
            else show_message_popup(S["TITLES"].get("ERROR", "Σφάλμα"), "Δεν έχει οριστεί συνημμένο αρχείο.")
        )
    )
    clear_attachment_btn.bind(on_press=lambda _x: setattr(attachment_input, "text", ""))

    content.add_widget(Label(text="Στοιχεία που θα απομονωθούν:", size_hint_y=None, height=30, bold=True))
    element_actions = BoxLayout(size_hint_y=None, height=35, spacing=5)
    select_all_btn = Button(text=S["MESSAGES"].get("SELECT_ALL_BTN", "Επιλογή Όλων"))
    clear_all_btn = Button(text=S["MESSAGES"].get("NONE", "Καμία"))
    element_actions.add_widget(select_all_btn)
    element_actions.add_widget(clear_all_btn)
    content.add_widget(element_actions)

    elements_container = GridLayout(cols=1, spacing=5, size_hint_y=None, padding=5)
    elements_container.bind(minimum_height=elements_container.setter("height"))
    content.add_widget(elements_container)
    element_checks = {}

    def load_elements(sub_name):
        elements_container.clear_widgets()
        element_checks.clear()
        substation_id = substation_map.get(sub_name)
        if not substation_id:
            return
        grouped = _group_elements_by_gate(_get_elements_for_substation(app, substation_id))
        gate_names = [gate for gate in grouped.keys() if gate.startswith("ΠΥΛΗ")]
        gate_names = sorted(gate_names) + [gate for gate in grouped.keys() if gate not in gate_names]
        for gate_name in gate_names:
            elements_container.add_widget(
                Label(text=f"{gate_name} ({len(grouped[gate_name])} στοιχεία)", size_hint_y=None, height=30, bold=True)
            )
            for element_id, name, serial_number, element_type, _gate_name in grouped[gate_name]:
                row = BoxLayout(size_hint_y=None, height=34, spacing=5)
                anchor = AnchorLayout(size_hint_x=None, width=32, anchor_x="center", anchor_y="center")
                checkbox = CheckBox(active=element_id in selected_element_ids)
                anchor.add_widget(checkbox)
                row.add_widget(anchor)
                row.add_widget(
                    Label(
                        text=f"{name} | {element_type} | S/N: {serial_number or '-'}",
                        halign="left",
                        valign="middle",
                    )
                )
                elements_container.add_widget(row)
                element_checks[element_id] = checkbox

    select_all_btn.bind(on_press=lambda _x: [setattr(cb, "active", True) for cb in element_checks.values()])
    clear_all_btn.bind(on_press=lambda _x: [setattr(cb, "active", False) for cb in element_checks.values()])
    load_elements(initial_substation)

    content.add_widget(Label(text="Σχόλια / Κείμενο εισαγωγής:", size_hint_y=None, height=30, bold=True))
    notes_default = request_record[6] if request_record else prefill_data.get("notes") or ""
    notes_input = TextInput(text=notes_default, size_hint_y=None, height=180, multiline=True)

    def _resize_notes_input(*_args):
        try:
            notes_input.height = max(180, notes_input.minimum_height + 20)
        except Exception:
            notes_input.height = 180

    notes_input.bind(text=lambda *_args: _resize_notes_input())
    notes_input.bind(width=lambda *_args: _resize_notes_input())
    notes_input.bind(focus=lambda _instance, focused: setattr(scroll, "do_scroll_y", not focused))
    _resize_notes_input()
    content.add_widget(notes_input)

    if request_record:
        linked_box = GridLayout(cols=1, size_hint_y=None, spacing=6)
        linked_box.bind(minimum_height=linked_box.setter("height"))
        linked_box.add_widget(Label(text="Συνδεδεμένες συντηρήσεις:", size_hint_y=None, height=30, bold=True))

        c.execute(
            """
            SELECT id, name, date_time, maintenance_type
            FROM maintenance
            WHERE isolation_request_id = ?
            ORDER BY date_time DESC
            """,
            (request_id,),
        )
        linked_maintenances = c.fetchall()

        if linked_maintenances:
            for maint_id, maint_name, date_time, maintenance_type in linked_maintenances:
                row = BoxLayout(size_hint_y=None, height=38, spacing=5)
                row.add_widget(
                    Label(
                        text=f"{date_time} | {maintenance_type or '-'} | {maint_name or '-'}",
                        size_hint_x=0.75,
                        halign="left",
                        valign="middle",
                    )
                )
                open_btn = Button(text="Άνοιγμα", size_hint_x=0.25)
                open_btn.bind(
                    on_press=lambda _x, mid=maint_id: (
                        popup.dismiss(),
                        app.show_maintenance_menu(
                            maintenance_id=mid,
                            after_save_callback=lambda: show_isolation_request_details(app, request_id, parent_popup),
                        ),
                    )
                )
                row.add_widget(open_btn)
                linked_box.add_widget(row)
        else:
            linked_box.add_widget(Label(text="Δεν υπάρχει ακόμη συνδεδεμένη συντήρηση.", size_hint_y=None, height=28))

        create_maint_btn = Button(text="Νέα συντήρηση από την απομόνωση", size_hint_y=None, height=42)

        def _create_linked_maintenance():
            selected_ids = [element_id for element_id, checkbox in element_checks.items() if checkbox.active]
            popup.dismiss()
            app.show_maintenance_menu(
                preselected_substation_name=substation_input.text,
                after_save_callback=lambda: show_isolation_request_details(app, request_id, parent_popup),
                prefill_data={
                    "substation_id": substation_map.get(substation_input.text),
                    "substation_name": substation_input.text,
                    "date_time": start_input.text.strip(),
                    "overall_comments": notes_input.text.strip(),
                    "element_ids": selected_ids,
                    "linked_isolation_request_id": request_id,
                },
            )

        create_maint_btn.bind(on_press=lambda _x: _create_linked_maintenance())
        linked_box.add_widget(create_maint_btn)
        content.add_widget(linked_box)
        content.add_widget(Widget(size_hint_y=None, height=4))
        content.add_widget(Label(text=f"Δημιουργήθηκε: {request_record[9]}", size_hint_y=None, height=24, font_size="11sp"))
        content.add_widget(Label(text=f"Τελευταία ενημέρωση: {request_record[10]}", size_hint_y=None, height=24, font_size="11sp"))
    else:
        content.add_widget(
            Label(
                text="Αποθηκεύστε πρώτα την απομόνωση για να δημιουργήσετε ή να συνδέσετε συντήρηση.",
                size_hint_y=None,
                height=26,
                font_size="11sp",
            )
        )

    scroll.add_widget(content)
    main_layout.add_widget(scroll)

    buttons_layout = BoxLayout(size_hint_y=None, height=50, spacing=10)

    def _validate_datetimes():
        start_dt = start_input.text.strip()
        end_dt = end_input.text.strip()
        try:
            start_value = datetime.strptime(start_dt, "%Y-%m-%d %H:%M")
            end_value = datetime.strptime(end_dt, "%Y-%m-%d %H:%M")
        except ValueError:
            show_message_popup(S["TITLES"].get("ERROR", "Σφάλμα"), "Μη έγκυρη μορφή ημερομηνίας. Χρησιμοποιήστε YYYY-MM-DD HH:MM.")
            return None
        if end_value <= start_value:
            show_message_popup(S["TITLES"].get("ERROR", "Σφάλμα"), "Η ημερομηνία λήξης πρέπει να είναι μετά την έναρξη.")
            return None
        return start_dt, end_dt

    def save_request():
        nonlocal request_id, existing_attachment_path, storage_folder_path, request_record, is_new_request
        validated = _validate_datetimes()
        if not validated:
            return
        start_dt, end_dt = validated
        substation_id = substation_map.get(substation_input.text)
        if not substation_id:
            show_message_popup(S["TITLES"].get("ERROR", "Σφάλμα"), "Δεν βρέθηκε υποσταθμός.")
            return

        selected_ids = [element_id for element_id, checkbox in element_checks.items() if checkbox.active]
        notes_value = notes_input.text.strip()
        status_value = status_spinner.text
        selected_attachment = attachment_input.text.strip()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if request_id:
            c.execute(
                """
                UPDATE isolation_requests
                SET substation_id=?, start_datetime=?, end_datetime=?, status=?, notes=?, updated_at=?
                WHERE id=?
                """,
                (substation_id, start_dt, end_dt, status_value, notes_value, now, request_id),
            )
        else:
            c.execute(
                """
                INSERT INTO isolation_requests
                (substation_id, start_datetime, end_datetime, status, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (substation_id, start_dt, end_dt, status_value, notes_value, now, now),
            )
            request_id = c.lastrowid

        copied_attachment_paths = []
        if selected_attachment and os.path.isfile(selected_attachment):
            selected_abs = os.path.abspath(selected_attachment)
            existing_abs = os.path.abspath(existing_attachment_path) if existing_attachment_path else ""
            if selected_abs != existing_abs:
                copied_attachment_paths = [selected_attachment]

        stored_attachment_path = existing_attachment_path if selected_attachment == existing_attachment_path else ""
        if copied_attachment_paths or (selected_attachment and not storage_folder_path):
            storage_result = ensure_isolation_request_storage(
                app.conn,
                request_id=request_id,
                substation_id=substation_id,
                start_datetime=start_dt,
                attachment_paths=copied_attachment_paths,
                db_path=getattr(app, "db_path", None),
            )
            storage_folder_path = storage_result.get("storage_folder") or storage_folder_path
            stored_files = storage_result.get("stored_files") or []
            if stored_files:
                stored_attachment_path = stored_files[0]
        elif not selected_attachment:
            stored_attachment_path = ""

        c.execute(
            """
            UPDATE isolation_requests
            SET request_file_path=?, storage_folder_path=?, updated_at=?
            WHERE id=?
            """,
            (stored_attachment_path or None, storage_folder_path or None, now, request_id),
        )

        c.execute("DELETE FROM isolation_request_elements WHERE request_id=?", (request_id,))
        for element_id in selected_ids:
            c.execute(
                "INSERT OR IGNORE INTO isolation_request_elements (request_id, element_id) VALUES (?, ?)",
                (request_id, element_id),
            )

        app.conn.commit()
        existing_attachment_path = stored_attachment_path
        attachment_input.text = stored_attachment_path or ""

        if not request_record:
            c.execute(
                """
                SELECT ir.id, ir.substation_id, s.name, ir.start_datetime, ir.end_datetime,
                       ir.status, ir.notes, ir.request_file_path, ir.storage_folder_path,
                       ir.created_at, ir.updated_at
                FROM isolation_requests ir
                JOIN substations s ON s.id = ir.substation_id
                WHERE ir.id = ?
                """,
                (request_id,),
            )
            request_record = c.fetchone()

        popup.dismiss()
        if parent_popup:
            try:
                parent_popup.dismiss()
            except Exception:
                pass
        message = "Η αίτηση απομόνωσης καταχωρήθηκε!" if is_new_request else "Η αίτηση απομόνωσης ενημερώθηκε!"
        show_message_popup(
            S["TITLES"].get("SUCCESS", "Επιτυχία"),
            message,
            callback=lambda: show_isolation_requests(app, None),
        )

    save_btn = Button(text=S["BUTTONS"]["SAVE"] if is_new_request else S["BUTTONS"].get("UPDATE", S["BUTTONS"]["SAVE"]))
    save_btn.bind(on_press=lambda _x: save_request())
    buttons_layout.add_widget(save_btn)

    if request_id:
        def delete_request():
            def _do_delete():
                c.execute("UPDATE maintenance SET isolation_request_id=NULL WHERE isolation_request_id=?", (request_id,))
                c.execute("DELETE FROM isolation_request_elements WHERE request_id=?", (request_id,))
                c.execute("DELETE FROM isolation_requests WHERE id=?", (request_id,))
                app.conn.commit()
                try:
                    popup.dismiss()
                except Exception:
                    pass
                try:
                    if parent_popup:
                        parent_popup.dismiss()
                except Exception:
                    pass
                show_message_popup(S["TITLES"].get("SUCCESS", "Επιτυχία"), "Η αίτηση απομόνωσης διαγράφηκε!", callback=lambda: show_isolation_requests(app, None))

            show_confirm(
                "Επιβεβαίωση",
                "Είστε σίγουροι ότι θέλετε να διαγράψετε αυτήν την αίτηση απομόνωσης;",
                yes_callback=_do_delete,
                yes_text="Ναι",
                no_text="Όχι",
                yes_color=(1, 0, 0, 1),
            )

        delete_btn = IconOnlyButton(icon_type="delete", icon_color=(1, 0.0, 0.0, 1), size=(35, 35))
        delete_btn.size_hint_x = 0.2
        delete_btn.bind(on_press=lambda _x: delete_request())
        buttons_layout.add_widget(delete_btn)

    cancel_btn = Button(text=S["BUTTONS"]["CANCEL"] if is_new_request else S["BUTTONS"]["CLOSE"])
    cancel_btn.bind(on_press=popup.dismiss)
    buttons_layout.add_widget(cancel_btn)

    main_layout.add_widget(buttons_layout)
    popup.content = main_layout
    popup.open()


def show_add_isolation_request(app, parent_popup, prefill_data=None):
    _show_isolation_request_form(app, parent_popup, request_id=None, prefill_data=prefill_data)


def show_isolation_request_details(app, request_id, parent_popup):
    _show_isolation_request_form(app, parent_popup, request_id=request_id, prefill_data=None)
