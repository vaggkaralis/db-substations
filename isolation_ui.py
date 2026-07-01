import os
import glob
import mimetypes
import tempfile
from datetime import datetime, timedelta
from email.parser import BytesHeaderParser
from email import policy
from email.message import EmailMessage
from email.utils import getaddresses

from config_manager import get_app_setting
from email_eml_parser import parse_eml_file
from isolation_importer import (
    match_element_ids_from_text,
    match_substation,
    parse_isolation_request_text,
    split_isolation_email_payload,
)
from onedrive_hybrid_storage import ensure_isolation_request_storage
from popups import ask_open_file, show_message_popup
from strings_proxy import STRINGS as S

_STATUS_VALUES = ["Requested", "Accepted", "Cancelled"]
_DEFAULT_IMPORTED_STATUS = "Accepted"
_ISOLATION_EMAIL_TEMPLATE_SETTING_KEY = "isolation_email_template_path"
_ISOLATION_EMAIL_TEMPLATE_CACHE = {
    "path": "",
    "mtime": 0.0,
    "payload": None,
}


def _extract_email_addresses(raw_header_value):
    if not raw_header_value:
        return []
    result = []
    for _name, email in getaddresses([str(raw_header_value)]):
        email_text = str(email or "").strip()
        if email_text:
            result.append(email_text)
    # Keep stable order while de-duplicating.
    return list(dict.fromkeys(result))


def _build_isolation_email_subject(request_id, substation_name, template_payload=None):
    template_subject = str((template_payload or {}).get("subject") or "").strip()
    if template_subject:
        return f"{template_subject} | Αίτηση #{request_id}"
    return f"Αίτηση Απομόνωσης #{request_id} - {substation_name}"


def _build_isolation_email_body(
    request_id,
    substation_name,
    start_dt,
    end_dt,
    notes,
    selected_elements,
):
    lines = [
        "Καλησπέρα σας,",
        "",
        "Παρακαλώ για την απομόνωση και άδεια εργασίας σύμφωνα με τα στοιχεία:",
        f"- Αίτηση: #{request_id}",
        f"- Υποσταθμός: {substation_name}",
        f"- Έναρξη: {start_dt}",
        f"- Λήξη: {end_dt}",
    ]

    if selected_elements:
        lines.append("- Στοιχεία:")
        for element_name, element_type, gate in selected_elements:
            type_part = str(element_type or "-").strip()
            gate_part = str(
                gate or S["MESSAGES"].get("UNREGISTERED_GATE", "Μη δηλωμένη πύλη")
            ).strip()
            lines.append(f"  * {element_name} | {type_part} | {gate_part}")

    note_text = str(notes or "").strip()
    if note_text:
        lines.append("")
        lines.append("Παρατηρήσεις:")
        lines.append(note_text)

    lines.extend(["", "Το αρχείο αίτησης επισυνάπτεται αυτόματα.", "", "Με εκτίμηση"])
    return "\n".join(lines).strip()


def _resolve_isolation_email_template_path():
    configured = str(
        get_app_setting(_ISOLATION_EMAIL_TEMPLATE_SETTING_KEY, "") or ""
    ).strip()
    if configured and os.path.isfile(configured):
        return configured

    workspace_root = os.path.dirname(os.path.abspath(__file__))
    candidates = sorted(glob.glob(os.path.join(workspace_root, "*ΑΠΟΜΟΝΩΣΗ*.eml")))
    if candidates:
        return candidates[0]
    return ""


def _pick_template_xlsx_attachment(template_payload):
    if not isinstance(template_payload, dict):
        return ""
    paths = template_payload.get("document_attachment_paths") or []
    for path in paths:
        file_path = str(path or "").strip()
        if file_path.lower().endswith(".xlsx") and os.path.isfile(file_path):
            return file_path
    return ""


def _ensure_template_xlsx_attachment_path(template_payload):
    cached = str((template_payload or {}).get("_template_xlsx_path") or "").strip()
    if cached and os.path.isfile(cached):
        return cached

    template_eml_path = str(
        (template_payload or {}).get("_template_eml_path") or ""
    ).strip()
    if not template_eml_path or not os.path.isfile(template_eml_path):
        return ""

    try:
        parsed_payload = parse_eml_file(template_eml_path)
    except Exception:
        return ""

    xlsx_path = _pick_template_xlsx_attachment(parsed_payload)
    if xlsx_path:
        template_payload["_template_xlsx_path"] = xlsx_path
    return xlsx_path


def _create_outlook_isolation_draft(
    template_payload,
    subject,
    body,
    attachment_path,
):
    headers = (template_payload or {}).get("headers") or {}
    to_recipients = _extract_email_addresses(headers.get("to"))
    cc_recipients = _extract_email_addresses(headers.get("cc"))

    if not to_recipients:
        return False, "Δεν βρέθηκαν παραλήπτες (To) στο πρότυπο email."

    if not attachment_path or not os.path.isfile(attachment_path):
        return False, "Δεν βρέθηκε το επισυναπτόμενο αρχείο αίτησης."

    prefer_shell_open = bool((template_payload or {}).get("_prefer_shell_open"))

    def _open_draft_via_eml_shell():
        try:
            msg = EmailMessage()
            msg["To"] = "; ".join(to_recipients)
            if cc_recipients:
                msg["Cc"] = "; ".join(cc_recipients)
            msg["Subject"] = str(subject or "").strip()
            # Widely used hint for opening as an unsent draft.
            msg["X-Unsent"] = "1"
            msg.set_content(str(body or ""), subtype="plain", charset="utf-8")

            file_name = os.path.basename(attachment_path)
            guessed_type, _enc = mimetypes.guess_type(file_name)
            maintype, subtype = (
                guessed_type.split("/", 1)
                if guessed_type
                else ["application", "octet-stream"]
            )
            with open(attachment_path, "rb") as fh:
                msg.add_attachment(
                    fh.read(),
                    maintype=maintype,
                    subtype=subtype,
                    filename=file_name,
                )

            with tempfile.NamedTemporaryFile(
                mode="wb", suffix=".eml", delete=False
            ) as temp_fh:
                temp_fh.write(msg.as_bytes(policy=policy.default))
                temp_eml = temp_fh.name

            if hasattr(os, "startfile"):
                os.startfile(temp_eml)
                return True, ""

            return (
                False,
                "Το λειτουργικό σύστημα δεν υποστηρίζει άνοιγμα .eml με startfile.",
            )
        except Exception as exc:
            return False, f"Αποτυχία δημιουργίας τοπικού προσχεδίου .eml: {exc}"

    if prefer_shell_open:
        ok, msg_text = _open_draft_via_eml_shell()
        if ok:
            return True, ""

    try:
        import win32com.client

        try:
            import pythoncom
        except Exception:
            pythoncom = None
    except Exception:
        # Fallback to shell-opened .eml when COM is unavailable.
        ok, msg_text = _open_draft_via_eml_shell()
        if ok:
            return True, ""
        return (False, f"Δεν είναι διαθέσιμο το Outlook COM (pywin32).\n{msg_text}")

    try:
        if pythoncom is not None:
            pythoncom.CoInitialize()
        outlook = win32com.client.Dispatch("Outlook.Application")

        # Prefer opening the original .eml template. In some Outlook profiles,
        # CreateItem can fail when no default data store/account is configured.
        mail = None
        template_eml_path = str(
            (template_payload or {}).get("_template_eml_path") or ""
        ).strip()
        if template_eml_path and os.path.isfile(template_eml_path):
            try:
                namespace = outlook.GetNamespace("MAPI")
                mail = namespace.OpenSharedItem(template_eml_path)
            except Exception:
                mail = None

        if mail is None:
            mail = outlook.CreateItem(0)

        try:
            attachments = getattr(mail, "Attachments", None)
            count = int(getattr(attachments, "Count", 0) or 0)
            for idx in range(count, 0, -1):
                attachments.Remove(idx)
        except Exception:
            pass

        mail.To = ";".join(to_recipients)
        mail.CC = ";".join(cc_recipients)
        mail.Subject = str(subject or "").strip()
        mail.Body = str(body or "")
        mail.Attachments.Add(os.path.abspath(attachment_path))
        # Open draft for final user review before send.
        mail.Display(False)
        return True, ""
    except Exception as exc:
        # Last-resort fallback path.
        ok, msg_text = _open_draft_via_eml_shell()
        if ok:
            return True, ""
        return False, f"Αποτυχία δημιουργίας email στο Outlook: {exc}\n{msg_text}"
    finally:
        try:
            if "pythoncom" in locals() and pythoncom is not None:
                pythoncom.CoUninitialize()
        except Exception:
            pass


def _load_isolation_email_template_payload():
    template_path = _resolve_isolation_email_template_path()
    if not template_path:
        return None, "Δεν βρέθηκε αρχείο προτύπου .eml για απομόνωση."

    try:
        mtime = float(os.path.getmtime(template_path))
    except Exception:
        mtime = 0.0

    cached_payload = _ISOLATION_EMAIL_TEMPLATE_CACHE.get("payload")
    if (
        _ISOLATION_EMAIL_TEMPLATE_CACHE.get("path") == template_path
        and _ISOLATION_EMAIL_TEMPLATE_CACHE.get("mtime") == mtime
        and isinstance(cached_payload, dict)
    ):
        return cached_payload, ""

    try:
        with open(template_path, "rb") as fh:
            msg = BytesHeaderParser(policy=policy.default).parse(fh)
        payload = {
            "subject": str(msg.get("subject") or "").strip(),
            "headers": {
                "to": str(msg.get("to") or "").strip(),
                "cc": str(msg.get("cc") or "").strip(),
            },
        }
        payload["_template_eml_path"] = template_path
        payload["_template_xlsx_path"] = ""
        _ISOLATION_EMAIL_TEMPLATE_CACHE["path"] = template_path
        _ISOLATION_EMAIL_TEMPLATE_CACHE["mtime"] = mtime
        _ISOLATION_EMAIL_TEMPLATE_CACHE["payload"] = payload
        return payload, ""
    except Exception as exc:
        return None, f"Αποτυχία ανάγνωσης προτύπου email: {exc}"


def _default_isolation_end_datetime(start_value, parsed_end_value=None):
    end_value = str(parsed_end_value or "").strip()
    if end_value:
        return end_value

    start_text = str(start_value or "").strip()
    if start_text:
        try:
            start_dt = datetime.strptime(start_text, "%Y-%m-%d %H:%M")
            candidate = start_dt.replace(hour=14, minute=0)
            if candidate <= start_dt:
                candidate = start_dt.replace(minute=0) + timedelta(hours=4)
            return candidate.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass

    return datetime.now().strftime("%Y-%m-%d 14:00")


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


def _prefill_imported_isolation(
    app,
    parent_popup,
    raw_text,
    status,
    attachment_paths=None,
    after_save_callback=None,
):
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
        matched_element_ids, _matched_phrases = match_element_ids_from_text(
            raw_text, element_rows
        )
        if not matched_element_ids and getattr(app, "_find_elements_in_body", None):
            matched_element_ids = sorted(
                app._find_elements_in_body(raw_text, substation_id)
            )
        prefill["element_ids"] = matched_element_ids

    show_add_isolation_request(
        app,
        parent_popup,
        prefill_data=prefill,
        after_save_callback=after_save_callback,
    )


def import_isolation_request_from_payload(
    app,
    payload,
    parent_popup=None,
    status=_DEFAULT_IMPORTED_STATUS,
    after_save_callback=None,
):
    split_payloads = split_isolation_email_payload(payload)

    if len(split_payloads) == 1:
        current_payload = split_payloads[0]
        _prefill_imported_isolation(
            app,
            parent_popup,
            current_payload.get("body") or "",
            status,
            attachment_paths=(
                current_payload.get("document_attachment_paths")
                or current_payload.get("all_attachment_paths")
                or current_payload.get("attachment_paths")
                or []
            ),
            after_save_callback=after_save_callback,
        )
        return

    def _open_split_payload(index):
        current_payload = split_payloads[index]
        raw_text = current_payload.get("body") or ""
        attachment_paths = (
            current_payload.get("document_attachment_paths")
            or current_payload.get("all_attachment_paths")
            or current_payload.get("attachment_paths")
            or []
        )

        def _after_save_current():
            if index + 1 < len(split_payloads):
                _open_split_payload(index + 1)
                return
            if after_save_callback:
                after_save_callback()

        _prefill_imported_isolation(
            app,
            parent_popup,
            raw_text,
            status,
            attachment_paths=attachment_paths,
            after_save_callback=_after_save_current,
        )

    _open_split_payload(0)


def import_isolation_request_from_eml(
    app,
    file_path,
    parent_popup=None,
    status=_DEFAULT_IMPORTED_STATUS,
    after_save_callback=None,
):
    try:
        payload = parse_eml_file(file_path)
    except Exception as exc:
        show_message_popup(
            S["TITLES"].get("ERROR", "Σφάλμα"), f"Αποτυχία ανάγνωσης email:\n{exc}"
        )
        return

    import_isolation_request_from_payload(
        app,
        payload,
        parent_popup=parent_popup,
        status=status,
        after_save_callback=after_save_callback,
    )


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
            show_message_popup(
                S["TITLES"].get("ERROR", "Σφάλμα"), "Δεν δόθηκε κείμενο για εισαγωγή."
            )
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
    file_path = ask_open_file(
        title="Select .eml file", filetypes=(("EML files", "*.eml"),)
    )
    if not file_path:
        return
    import_isolation_request_from_eml(
        app, file_path, parent_popup=parent_popup, status=status
    )


def show_import_isolation_request(app, parent_popup=None):
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.spinner import Spinner

    popup = Popup(title="Εισαγωγή αίτησης απομόνωσης", size_hint=(0.7, 0.45))
    layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
    layout.add_widget(
        Label(
            text="Ορίστε κατάσταση για την εισαγόμενη απομόνωση:",
            size_hint_y=None,
            height=35,
        )
    )
    status_spinner = Spinner(
        text=_DEFAULT_IMPORTED_STATUS,
        values=_STATUS_VALUES,
        size_hint_y=None,
        height=40,
    )
    layout.add_widget(status_spinner)

    buttons = BoxLayout(size_hint_y=None, height=50, spacing=10)
    text_btn = Button(text="Από κείμενο")
    text_btn.bind(
        on_press=lambda _x: (
            popup.dismiss(),
            _show_import_text_popup(app, parent_popup, status_spinner.text),
        )
    )
    buttons.add_widget(text_btn)

    email_btn = Button(text="Από e-mail (.eml)")
    email_btn.bind(
        on_press=lambda _x: (
            popup.dismiss(),
            _import_from_eml(app, parent_popup, status_spinner.text),
        )
    )
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
    legend_layout.add_widget(
        Label(text="● Αιτήθηκε", size_hint_x=0.22, color=(1, 0.85, 0, 1), **font_kwargs)
    )
    legend_layout.add_widget(
        Label(
            text="● Εγκρίθηκε",
            size_hint_x=0.22,
            color=(0.2, 0.8, 0.2, 1),
            **font_kwargs,
        )
    )
    legend_layout.add_widget(
        Label(
            text="● Ακυρώθηκε",
            size_hint_x=0.22,
            color=(0.9, 0.2, 0.2, 1),
            **font_kwargs,
        )
    )
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
        # Determine calendar display range (start = Monday of first week, end = Sunday of last week)
        first_of_month = datetime(year, month, 1).date()
        last_of_month = datetime(year, month, monthrange(year, month)[1]).date()

        start_date = first_of_month - timedelta(days=first_of_month.weekday())
        end_date = last_of_month + timedelta(days=(6 - last_of_month.weekday()))

        first_day = f"{start_date.strftime('%Y-%m-%d')} 00:00"
        last_day = f"{end_date.strftime('%Y-%m-%d')} 23:59"

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
        # Index requests by exact date (date objects) across the displayed range
        requests_by_day = {}
        for req_id, sub_id, sub_name, start_dt, end_dt, status, notes in requests:
            try:
                start = datetime.strptime(start_dt, "%Y-%m-%d %H:%M")
                end = datetime.strptime(end_dt, "%Y-%m-%d %H:%M")
                current = start
                while current <= end:
                    current_date = current.date()
                    # only store dates that fall inside the display range to limit memory
                    if start_date <= current_date <= end_date:
                        requests_by_day.setdefault(current_date, [])
                        if not any(
                            existing[0] == req_id
                            for existing in requests_by_day[current_date]
                        ):
                            requests_by_day[current_date].append(
                                (
                                    req_id,
                                    sub_id,
                                    sub_name,
                                    start_dt,
                                    end_dt,
                                    status,
                                    notes,
                                )
                            )
                    current += timedelta(days=1)
            except Exception:
                continue

        calendar_grid = GridLayout(cols=7, spacing=2)
        for day_name in ["Δευ", "Τρί", "Τετ", "Πέμ", "Παρ", "Σάβ", "Κυρ"]:
            calendar_grid.add_widget(
                Label(text=day_name, size_hint_y=None, height=30, bold=True)
            )

        # Build a continuous range starting from the Monday of the week
        # containing the month's first day, and ending on the Sunday of the
        # week containing the month's last day. This shows leading/trailing
        # days from adjacent months.

        first_of_month = datetime(year, month, 1).date()
        last_of_month = datetime(year, month, monthrange(year, month)[1]).date()

        start_date = first_of_month - timedelta(days=first_of_month.weekday())
        end_date = last_of_month + timedelta(days=(6 - last_of_month.weekday()))

        current_day = start_date
        while current_day <= end_date:
            is_current_month = current_day.month == month and current_day.year == year
            is_leading = current_day < first_of_month
            is_trailing = current_day > last_of_month
            day_box = BoxLayout(orientation="vertical", size_hint_y=None, height=100)

            # Day number label: different color for leading vs trailing month days
            if is_leading:
                day_label_color = (0.55, 0.55, 0.7, 1)
            elif is_trailing:
                day_label_color = (0.55, 0.7, 0.55, 1)
            else:
                day_label_color = (1, 1, 1, 1)
            day_label_kwargs = dict(size_hint_y=0.3)
            if is_current_month:
                day_label = Label(
                    text=str(current_day.day),
                    bold=True,
                    **day_label_kwargs,
                    **font_kwargs,
                )
            else:
                # Show different (muted) style for previous/next month days
                day_label = Label(
                    text=str(current_day.day),
                    color=day_label_color,
                    bold=False,
                    font_size="12sp",
                    **day_label_kwargs,
                )

            day_box.add_widget(day_label)

            # Show requests if any for this calendar date (including leading/trailing)
            if current_day in requests_by_day:
                scroll = ScrollView(size_hint_y=0.7)
                requests_layout = GridLayout(
                    cols=1, size_hint_y=None, spacing=2, padding=2
                )
                requests_layout.bind(minimum_height=requests_layout.setter("height"))

                for (
                    req_id,
                    _sub_id,
                    sub_name,
                    _start_dt,
                    _end_dt,
                    status,
                    _notes,
                ) in requests_by_day[current_day]:
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
                        on_press=lambda _x, r_id=req_id, popup_ref=popup: (
                            show_isolation_request_details(app, r_id, popup_ref)
                        )
                    )
                    requests_layout.add_widget(req_btn)

                scroll.add_widget(requests_layout)
                day_box.add_widget(scroll)
            else:
                day_box.add_widget(Label(text="", size_hint_y=0.7))

            calendar_grid.add_widget(day_box)
            current_day += timedelta(days=1)

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


def _show_isolation_request_form(
    app,
    parent_popup,
    request_id=None,
    prefill_data=None,
    after_save_callback=None,
):
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
        show_message_popup(
            S["TITLES"].get("ERROR", "Σφάλμα"),
            S["MESSAGES"].get("NO_SUBSTATIONS", "Δεν υπάρχουν υποσταθμοί!"),
        )
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
            show_message_popup(
                S["TITLES"].get("ERROR", "Σφάλμα"), "Η αίτηση απομόνωσης δεν βρέθηκε."
            )
            return
        c.execute(
            "SELECT element_id FROM isolation_request_elements WHERE request_id=?",
            (request_id,),
        )
        selected_element_ids = {row[0] for row in c.fetchall()}
        existing_attachment_path = str(request_record[7] or "").strip()
        storage_folder_path = str(request_record[8] or "").strip()

        # Normalize legacy ISO_/Αίτηση storage and recover the attachment path
        # when the DB row has only the folder stored.
        storage_result = ensure_isolation_request_storage(
            app.conn,
            request_id=request_record[0],
            substation_id=request_record[1],
            start_datetime=request_record[3],
            attachment_paths=None,
            storage_folder_path=storage_folder_path,
            request_file_path=existing_attachment_path,
            db_path=getattr(app, "db_path", None),
        )
        storage_folder_path = (
            storage_result.get("storage_folder") or storage_folder_path
        )
        stored_files = storage_result.get("stored_files") or []
        if (not existing_attachment_path) or (
            existing_attachment_path and not os.path.exists(existing_attachment_path)
        ):
            if stored_files:
                existing_attachment_path = stored_files[0]

        if (
            existing_attachment_path != str(request_record[7] or "").strip()
            or storage_folder_path != str(request_record[8] or "").strip()
        ):
            c.execute(
                """
                UPDATE isolation_requests
                SET request_file_path=?, storage_folder_path=?, updated_at=?
                WHERE id=?
                """,
                (
                    existing_attachment_path or None,
                    storage_folder_path or None,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    request_id,
                ),
            )
            app.conn.commit()

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

    content.add_widget(
        Label(text="Υποσταθμός:", size_hint_y=None, height=30, bold=True)
    )
    substation_row = BoxLayout(size_hint_y=None, height=40, spacing=5)
    substation_input = TextInput(
        text=initial_substation, readonly=True, multiline=False, size_hint_x=0.72
    )
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

    content.add_widget(
        Label(text="Ημ/νία & Ώρα Έναρξης:", size_hint_y=None, height=30, bold=True)
    )
    start_default = (
        request_record[3]
        if request_record
        else prefill_data.get("start_datetime")
        or datetime.now().strftime("%Y-%m-%d 09:00")
    )
    start_input = TextInput(
        text=start_default,
        hint_text="YYYY-MM-DD HH:MM",
        multiline=False,
        size_hint_y=None,
        height=35,
    )
    content.add_widget(start_input)

    start_presets = BoxLayout(size_hint_y=None, height=35, spacing=5)
    start_presets.add_widget(
        Button(
            text="Σήμερα 08:00",
            on_press=lambda _x: setattr(
                start_input, "text", datetime.now().strftime("%Y-%m-%d 08:00")
            ),
        )
    )
    start_presets.add_widget(
        Button(
            text="Σήμερα 18:00",
            on_press=lambda _x: setattr(
                start_input, "text", datetime.now().strftime("%Y-%m-%d 18:00")
            ),
        )
    )
    content.add_widget(start_presets)

    content.add_widget(
        Label(text="Ημ/νία & Ώρα Λήξης:", size_hint_y=None, height=30, bold=True)
    )
    end_default = (
        request_record[4]
        if request_record
        else _default_isolation_end_datetime(
            start_default,
            prefill_data.get("end_datetime"),
        )
    )
    end_input = TextInput(
        text=end_default,
        hint_text="YYYY-MM-DD HH:MM",
        multiline=False,
        size_hint_y=None,
        height=35,
    )
    content.add_widget(end_input)

    duration_row = BoxLayout(size_hint_y=None, height=35, spacing=5)

    def _set_duration(hours):
        try:
            start_dt = datetime.strptime(start_input.text.strip(), "%Y-%m-%d %H:%M")
            end_input.text = (start_dt + timedelta(hours=hours)).strftime(
                "%Y-%m-%d %H:%M"
            )
        except Exception:
            pass

    duration_row.add_widget(Button(text="2 ώρες", on_press=lambda _x: _set_duration(2)))
    duration_row.add_widget(Button(text="4 ώρες", on_press=lambda _x: _set_duration(4)))
    duration_row.add_widget(
        Button(text="1 ημέρα", on_press=lambda _x: _set_duration(24))
    )
    content.add_widget(duration_row)

    content.add_widget(Label(text="Κατάσταση:", size_hint_y=None, height=30, bold=True))
    status_default = (
        request_record[5]
        if request_record
        else prefill_data.get("status") or _DEFAULT_IMPORTED_STATUS
    )
    status_spinner = Spinner(
        text=status_default, values=_STATUS_VALUES, size_hint_y=None, height=40
    )
    content.add_widget(status_spinner)

    content.add_widget(
        Label(text="Συνημμένη αίτηση/αρχείο:", size_hint_y=None, height=30, bold=True)
    )
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
            ask_open_file(
                title="Select request file", filetypes=(("All files", "*.*"),)
            )
            or attachment_input.text,
        )
    )

    def _open_attachment(_x):
        nonlocal existing_attachment_path, storage_folder_path
        attachment_path = attachment_input.text.strip()
        if (not attachment_path) and request_id and request_record:
            storage_result = ensure_isolation_request_storage(
                app.conn,
                request_id=request_record[0],
                substation_id=request_record[1],
                start_datetime=request_record[3],
                attachment_paths=None,
                storage_folder_path=storage_folder_path,
                request_file_path=existing_attachment_path,
                db_path=getattr(app, "db_path", None),
            )
            storage_folder_path = (
                storage_result.get("storage_folder") or storage_folder_path
            )
            stored_files = storage_result.get("stored_files") or []
            if stored_files:
                attachment_path = stored_files[0]
                existing_attachment_path = attachment_path
                attachment_input.text = attachment_path
                c.execute(
                    """
                    UPDATE isolation_requests
                    SET request_file_path=?, storage_folder_path=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        attachment_path,
                        storage_folder_path or None,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        request_id,
                    ),
                )
                app.conn.commit()

        if attachment_path:
            open_file(attachment_path)
        else:
            show_message_popup(
                S["TITLES"].get("ERROR", "Σφάλμα"), "Δεν έχει οριστεί συνημμένο αρχείο."
            )

    open_attachment_btn.bind(on_press=_open_attachment)
    clear_attachment_btn.bind(on_press=lambda _x: setattr(attachment_input, "text", ""))

    content.add_widget(
        Label(
            text="Στοιχεία που θα απομονωθούν:", size_hint_y=None, height=30, bold=True
        )
    )
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
        grouped = _group_elements_by_gate(
            _get_elements_for_substation(app, substation_id)
        )
        gate_names = [gate for gate in grouped.keys() if gate.startswith("ΠΥΛΗ")]
        gate_names = sorted(gate_names) + [
            gate for gate in grouped.keys() if gate not in gate_names
        ]
        for gate_name in gate_names:
            elements_container.add_widget(
                Label(
                    text=f"{gate_name} ({len(grouped[gate_name])} στοιχεία)",
                    size_hint_y=None,
                    height=30,
                    bold=True,
                )
            )
            for element_id, name, serial_number, element_type, _gate_name in grouped[
                gate_name
            ]:
                row = BoxLayout(size_hint_y=None, height=34, spacing=5)
                anchor = AnchorLayout(
                    size_hint_x=None, width=32, anchor_x="center", anchor_y="center"
                )
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

    select_all_btn.bind(
        on_press=lambda _x: [
            setattr(cb, "active", True) for cb in element_checks.values()
        ]
    )
    clear_all_btn.bind(
        on_press=lambda _x: [
            setattr(cb, "active", False) for cb in element_checks.values()
        ]
    )
    load_elements(initial_substation)

    content.add_widget(
        Label(
            text="Σχόλια / Κείμενο εισαγωγής:", size_hint_y=None, height=30, bold=True
        )
    )
    notes_default = (
        request_record[6] if request_record else prefill_data.get("notes") or ""
    )
    notes_input = TextInput(
        text=notes_default, size_hint_y=None, height=180, multiline=True
    )

    def _resize_notes_input(*_args):
        try:
            rendered_lines = getattr(notes_input, "_lines", None) or []
            line_count = max(
                1, len(rendered_lines) or len(notes_input.text.splitlines())
            )
            line_height = getattr(notes_input, "line_height", 18) or 18
            notes_input.height = min(320, max(120, int(line_count * line_height + 28)))
        except Exception:
            notes_input.height = 120

    notes_input.bind(text=lambda *_args: _resize_notes_input())
    notes_input.bind(width=lambda *_args: _resize_notes_input())
    notes_input.bind(
        focus=lambda _instance, focused: setattr(scroll, "do_scroll_y", not focused)
    )
    _resize_notes_input()
    content.add_widget(notes_input)

    send_email_checkbox = None
    if is_new_request:
        send_email_row = BoxLayout(size_hint_y=None, height=34, spacing=8)
        send_email_checkbox = CheckBox(active=False, size_hint_x=None, width=34)
        send_email_row.add_widget(send_email_checkbox)
        send_email_row.add_widget(
            Label(
                text="Μετά την αποθήκευση: δημιουργία email Outlook με συνημμένη αίτηση",
                halign="left",
                valign="middle",
            )
        )
        content.add_widget(send_email_row)

    if request_record:
        linked_box = GridLayout(cols=1, size_hint_y=None, spacing=6)
        linked_box.bind(minimum_height=linked_box.setter("height"))
        linked_box.add_widget(
            Label(
                text="Συνδεδεμένες συντηρήσεις:", size_hint_y=None, height=30, bold=True
            )
        )

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
            for (
                maint_id,
                maint_name,
                date_time,
                maintenance_type,
            ) in linked_maintenances:
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
                            after_save_callback=lambda: show_isolation_request_details(
                                app, request_id, parent_popup
                            ),
                        ),
                    )
                )
                row.add_widget(open_btn)
                linked_box.add_widget(row)
        else:
            linked_box.add_widget(
                Label(
                    text="Δεν υπάρχει ακόμη συνδεδεμένη συντήρηση.",
                    size_hint_y=None,
                    height=28,
                )
            )

        create_maint_btn = Button(
            text="Νέα συντήρηση από την απομόνωση", size_hint_y=None, height=42
        )

        def _create_linked_maintenance():
            selected_ids = [
                element_id
                for element_id, checkbox in element_checks.items()
                if checkbox.active
            ]
            popup.dismiss()
            app.show_maintenance_menu(
                preselected_substation_name=substation_input.text,
                after_save_callback=lambda: show_isolation_request_details(
                    app, request_id, parent_popup
                ),
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
        content.add_widget(
            Label(
                text=f"Δημιουργήθηκε: {request_record[9]}",
                size_hint_y=None,
                height=24,
                font_size="11sp",
            )
        )
        content.add_widget(
            Label(
                text=f"Τελευταία ενημέρωση: {request_record[10]}",
                size_hint_y=None,
                height=24,
                font_size="11sp",
            )
        )
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
    buttons_layout.size_hint_x = 1

    def _validate_datetimes():
        start_dt = start_input.text.strip()
        end_dt = end_input.text.strip()
        try:
            start_value = datetime.strptime(start_dt, "%Y-%m-%d %H:%M")
            end_value = datetime.strptime(end_dt, "%Y-%m-%d %H:%M")
        except ValueError:
            show_message_popup(
                S["TITLES"].get("ERROR", "Σφάλμα"),
                "Μη έγκυρη μορφή ημερομηνίας. Χρησιμοποιήστε YYYY-MM-DD HH:MM.",
            )
            return None
        if end_value <= start_value:
            show_message_popup(
                S["TITLES"].get("ERROR", "Σφάλμα"),
                "Η ημερομηνία λήξης πρέπει να είναι μετά την έναρξη.",
            )
            return None
        return start_dt, end_dt

    def save_request():
        nonlocal \
            request_id, \
            existing_attachment_path, \
            storage_folder_path, \
            request_record
        validated = _validate_datetimes()
        if not validated:
            return
        start_dt, end_dt = validated
        substation_id = substation_map.get(substation_input.text)
        if not substation_id:
            show_message_popup(
                S["TITLES"].get("ERROR", "Σφάλμα"), "Δεν βρέθηκε υποσταθμός."
            )
            return

        selected_ids = [
            element_id
            for element_id, checkbox in element_checks.items()
            if checkbox.active
        ]
        notes_value = notes_input.text.strip()
        status_value = status_spinner.text
        selected_attachment = attachment_input.text.strip()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        send_email_enabled = bool(
            is_new_request and send_email_checkbox and send_email_checkbox.active
        )
        template_payload = None
        if send_email_enabled:
            template_payload, template_error = _load_isolation_email_template_payload()
            if not template_payload:
                show_message_popup(
                    S["TITLES"].get("ERROR", "Σφάλμα"),
                    template_error,
                )
                return

        if request_id:
            c.execute(
                """
                UPDATE isolation_requests
                SET substation_id=?, start_datetime=?, end_datetime=?, status=?, notes=?, updated_at=?
                WHERE id=?
                """,
                (
                    substation_id,
                    start_dt,
                    end_dt,
                    status_value,
                    notes_value,
                    now,
                    request_id,
                ),
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
            existing_abs = (
                os.path.abspath(existing_attachment_path)
                if existing_attachment_path
                else ""
            )
            if selected_abs != existing_abs:
                copied_attachment_paths = [selected_attachment]
        elif send_email_enabled:
            template_xlsx = _ensure_template_xlsx_attachment_path(template_payload)
            if template_xlsx:
                copied_attachment_paths = [template_xlsx]

        stored_attachment_path = (
            existing_attachment_path
            if selected_attachment == existing_attachment_path
            else ""
        )
        if copied_attachment_paths or selected_attachment or storage_folder_path:
            storage_result = ensure_isolation_request_storage(
                app.conn,
                request_id=request_id,
                substation_id=substation_id,
                start_datetime=start_dt,
                attachment_paths=copied_attachment_paths,
                storage_folder_path=storage_folder_path,
                request_file_path=selected_attachment or existing_attachment_path,
                db_path=getattr(app, "db_path", None),
            )
            storage_folder_path = (
                storage_result.get("storage_folder") or storage_folder_path
            )
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
            (
                stored_attachment_path or None,
                storage_folder_path or None,
                now,
                request_id,
            ),
        )

        c.execute(
            "DELETE FROM isolation_request_elements WHERE request_id=?", (request_id,)
        )
        for element_id in selected_ids:
            c.execute(
                "INSERT OR IGNORE INTO isolation_request_elements (request_id, element_id) VALUES (?, ?)",
                (request_id, element_id),
            )

        app.conn.commit()
        app._append_change_log(
            "update" if request_record else "insert",
            "isolation_requests",
            {
                "id": request_id,
                "substation_id": substation_id,
                "start_datetime": start_dt,
                "end_datetime": end_dt,
                "status": status_value,
                "notes": notes_value,
                "request_file_path": stored_attachment_path or None,
                "storage_folder_path": storage_folder_path or None,
                "elements": [
                    {"element_id": element_id} for element_id in sorted(selected_ids)
                ],
            },
        )
        existing_attachment_path = stored_attachment_path
        attachment_input.text = stored_attachment_path or ""

        email_result_message = ""
        if send_email_enabled:
            selected_elements = []
            if selected_ids:
                placeholders = ",".join(["?"] * len(selected_ids))
                c.execute(
                    f"""
                    SELECT name, element_type, gate
                    FROM elements
                    WHERE id IN ({placeholders})
                    ORDER BY gate, name
                    """,
                    tuple(selected_ids),
                )
                selected_elements = c.fetchall()

            subject = _build_isolation_email_subject(
                request_id=request_id,
                substation_name=substation_input.text.strip(),
                template_payload=template_payload,
            )
            body = _build_isolation_email_body(
                request_id=request_id,
                substation_name=substation_input.text.strip(),
                start_dt=start_dt,
                end_dt=end_dt,
                notes=notes_value,
                selected_elements=selected_elements,
            )
            ok, error_message = _create_outlook_isolation_draft(
                template_payload=template_payload,
                subject=subject,
                body=body,
                attachment_path=stored_attachment_path,
            )
            if ok:
                email_result_message = "\n\nΔημιουργήθηκε προσχέδιο email στο Outlook."
            else:
                email_result_message = f"\n\nΗ αποθήκευση ολοκληρώθηκε, αλλά το email δεν δημιουργήθηκε:\n{error_message}"

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
        message = (
            "Η αίτηση απομόνωσης καταχωρήθηκε!"
            if is_new_request
            else "Η αίτηση απομόνωσης ενημερώθηκε!"
        )
        if email_result_message:
            message = f"{message}{email_result_message}"
        show_message_popup(
            S["TITLES"].get("SUCCESS", "Επιτυχία"),
            message,
            callback=(
                after_save_callback
                if callable(after_save_callback)
                else lambda: show_isolation_requests(app, None)
            ),
        )

    save_btn = Button(
        text=(
            S["BUTTONS"]["SAVE"]
            if is_new_request
            else S["BUTTONS"].get("UPDATE", S["BUTTONS"]["SAVE"])
        )
    )
    save_btn.size_hint_x = 1
    save_btn.bind(on_press=lambda _x: save_request())
    buttons_layout.add_widget(save_btn)

    send_email_btn = None
    sending_email_in_progress = [False]
    send_email_watchdog_state = {"cycles": 0}

    def _start_outlook_draft_async(template_payload, subject, body, attachment_path):
        if sending_email_in_progress[0]:
            show_message_popup(
                S["TITLES"].get("ERROR", "Σφάλμα"),
                "Η δημιουργία email είναι ήδη σε εξέλιξη. Παρακαλώ περιμένετε.",
            )
            return

        try:
            import threading
            from kivy.clock import Clock
        except Exception:
            ok, error_message = _create_outlook_isolation_draft(
                template_payload=template_payload,
                subject=subject,
                body=body,
                attachment_path=attachment_path,
            )
            if ok:
                show_message_popup(
                    S["TITLES"].get("SUCCESS", "Επιτυχία"),
                    "Δημιουργήθηκε προσχέδιο email στο Outlook.",
                )
            else:
                show_message_popup(
                    S["TITLES"].get("ERROR", "Σφάλμα"),
                    f"Το email δεν δημιουργήθηκε:\n{error_message}",
                )
            return

        sending_email_in_progress[0] = True
        send_email_watchdog_state["cycles"] = 0
        original_text = ""
        if send_email_btn is not None:
            original_text = str(send_email_btn.text or "")
            send_email_btn.disabled = True
            send_email_btn.text = "Αποστολή..."

        worker_ref = {"thread": None}

        def _restore_button_state():
            sending_email_in_progress[0] = False
            if send_email_btn is not None:
                try:
                    send_email_btn.disabled = False
                    send_email_btn.text = original_text or "Αποστολή Email"
                except Exception:
                    pass

        def _worker():
            worker_payload = dict(template_payload or {})
            worker_payload["_prefer_shell_open"] = True
            ok, error_message = _create_outlook_isolation_draft(
                template_payload=worker_payload,
                subject=subject,
                body=body,
                attachment_path=attachment_path,
            )

            def _on_done(_dt):
                _restore_button_state()
                if ok:
                    show_message_popup(
                        S["TITLES"].get("SUCCESS", "Επιτυχία"),
                        "Δημιουργήθηκε προσχέδιο email στο Outlook.",
                    )
                else:
                    show_message_popup(
                        S["TITLES"].get("ERROR", "Σφάλμα"),
                        f"Το email δεν δημιουργήθηκε:\n{error_message}",
                    )

            Clock.schedule_once(_on_done, 0)

        # Fail-safe: if Outlook blocks, do not freeze UI or show immediate false errors.
        def _watchdog(_dt):
            if not sending_email_in_progress[0]:
                return

            worker = worker_ref.get("thread")
            if worker is not None and worker.is_alive():
                send_email_watchdog_state["cycles"] += 1
                if send_email_btn is not None:
                    try:
                        send_email_btn.text = "Αναμονή Outlook..."
                    except Exception:
                        pass

                # Keep waiting while Outlook is still working.
                # After ~2 minutes, restore UI and inform user without hard error.
                if send_email_watchdog_state["cycles"] >= 6:
                    _restore_button_state()
                    show_message_popup(
                        S["TITLES"].get("WARNING", "Προειδοποίηση"),
                        "Το Outlook καθυστερεί να απαντήσει.\n"
                        "Η εφαρμογή παραμένει λειτουργική και μπορείτε να δοκιμάσετε ξανά.",
                    )
                    return

                Clock.schedule_once(_watchdog, 20)
                return

            # Worker seems finished but UI callback has not restored state yet.
            Clock.schedule_once(_watchdog, 0.5)

        Clock.schedule_once(_watchdog, 20)
        worker_thread = threading.Thread(target=_worker, daemon=True)
        worker_ref["thread"] = worker_thread
        worker_thread.start()

    def send_email_for_existing_request():
        nonlocal existing_attachment_path, storage_folder_path

        if not request_id:
            show_message_popup(
                S["TITLES"].get("ERROR", "Σφάλμα"),
                "Αποθηκεύστε πρώτα την αίτηση και στη συνέχεια στείλτε email.",
            )
            return

        validated = _validate_datetimes()
        if not validated:
            return
        start_dt, end_dt = validated

        substation_id = substation_map.get(substation_input.text)
        if not substation_id:
            show_message_popup(
                S["TITLES"].get("ERROR", "Σφάλμα"), "Δεν βρέθηκε υποσταθμός."
            )
            return

        template_payload, template_error = _load_isolation_email_template_payload()
        if not template_payload:
            show_message_popup(S["TITLES"].get("ERROR", "Σφάλμα"), template_error)
            return

        selected_ids = [
            element_id
            for element_id, checkbox in element_checks.items()
            if checkbox.active
        ]
        notes_value = notes_input.text.strip()
        selected_attachment = attachment_input.text.strip()
        attachment_path = ""

        if selected_attachment and os.path.isfile(selected_attachment):
            attachment_path = selected_attachment
        elif existing_attachment_path and os.path.isfile(existing_attachment_path):
            attachment_path = existing_attachment_path
        else:
            template_xlsx = _ensure_template_xlsx_attachment_path(template_payload)
            copied_paths = [template_xlsx] if template_xlsx else []
            storage_result = ensure_isolation_request_storage(
                app.conn,
                request_id=request_id,
                substation_id=substation_id,
                start_datetime=start_dt,
                attachment_paths=copied_paths,
                storage_folder_path=storage_folder_path,
                request_file_path=selected_attachment or existing_attachment_path,
                db_path=getattr(app, "db_path", None),
            )
            storage_folder_path = (
                storage_result.get("storage_folder") or storage_folder_path
            )
            stored_files = storage_result.get("stored_files") or []
            if stored_files:
                attachment_path = stored_files[0]

            existing_attachment_path = attachment_path
            attachment_input.text = attachment_path or ""
            c.execute(
                """
                UPDATE isolation_requests
                SET request_file_path=?, storage_folder_path=?, updated_at=?
                WHERE id=?
                """,
                (
                    attachment_path or None,
                    storage_folder_path or None,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    request_id,
                ),
            )
            app.conn.commit()

        selected_elements = []
        if selected_ids:
            placeholders = ",".join(["?"] * len(selected_ids))
            c.execute(
                f"""
                SELECT name, element_type, gate
                FROM elements
                WHERE id IN ({placeholders})
                ORDER BY gate, name
                """,
                tuple(selected_ids),
            )
            selected_elements = c.fetchall()

        subject = _build_isolation_email_subject(
            request_id=request_id,
            substation_name=substation_input.text.strip(),
            template_payload=template_payload,
        )
        body = _build_isolation_email_body(
            request_id=request_id,
            substation_name=substation_input.text.strip(),
            start_dt=start_dt,
            end_dt=end_dt,
            notes=notes_value,
            selected_elements=selected_elements,
        )
        _start_outlook_draft_async(
            template_payload=template_payload,
            subject=subject,
            body=body,
            attachment_path=attachment_path,
        )

    if request_id:
        send_email_btn = Button(text="Αποστολή Email")
        send_email_btn.size_hint_x = 1
        send_email_btn.bind(on_press=lambda _x: send_email_for_existing_request())
        buttons_layout.add_widget(send_email_btn)

        def delete_request():
            def _do_delete():
                c.execute(
                    "UPDATE maintenance SET isolation_request_id=NULL WHERE isolation_request_id=?",
                    (request_id,),
                )
                c.execute(
                    "DELETE FROM isolation_request_elements WHERE request_id=?",
                    (request_id,),
                )
                c.execute("DELETE FROM isolation_requests WHERE id=?", (request_id,))
                app.conn.commit()
                app._append_change_log(
                    "delete", "isolation_requests", {"id": request_id}
                )
                try:
                    popup.dismiss()
                except Exception:
                    pass
                try:
                    if parent_popup:
                        parent_popup.dismiss()
                except Exception:
                    pass
                show_message_popup(
                    S["TITLES"].get("SUCCESS", "Επιτυχία"),
                    "Η αίτηση απομόνωσης διαγράφηκε!",
                    callback=lambda: show_isolation_requests(app, None),
                )

            show_confirm(
                "Επιβεβαίωση",
                "Είστε σίγουροι ότι θέλετε να διαγράψετε αυτήν την αίτηση απομόνωσης;",
                yes_callback=_do_delete,
                yes_text="Ναι",
                no_text="Όχι",
                yes_color=(1, 0, 0, 1),
            )

        delete_btn = Button(text=S["BUTTONS"].get("DELETE", "Delete"))
        delete_btn.size_hint_x = 1
        delete_btn.bind(on_press=lambda _x: delete_request())
        buttons_layout.add_widget(delete_btn)

    cancel_btn = Button(
        text=S["BUTTONS"]["CANCEL"] if is_new_request else S["BUTTONS"]["CLOSE"]
    )
    cancel_btn.size_hint_x = 1
    cancel_btn.bind(on_press=popup.dismiss)
    buttons_layout.add_widget(cancel_btn)

    main_layout.add_widget(buttons_layout)
    popup.content = main_layout
    popup.open()


def show_add_isolation_request(
    app, parent_popup, prefill_data=None, after_save_callback=None
):
    _show_isolation_request_form(
        app,
        parent_popup,
        request_id=None,
        prefill_data=prefill_data,
        after_save_callback=after_save_callback,
    )


def show_isolation_request_details(app, request_id, parent_popup):
    _show_isolation_request_form(
        app, parent_popup, request_id=request_id, prefill_data=None
    )
