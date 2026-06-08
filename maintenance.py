import json
import os
import re
import threading
from datetime import datetime

from import_diagnostics import log_import_diagnostic
from strings_proxy import STRINGS as S


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
        "parse_pdf_file",
        "import_maintenance_from_pst_file",
        "export_maintenances_per_substation",
    )
    return {k: ui.get(k) for k in keys}


def show_maintenance_menu_popup(app, ui):
    ui = _make_ui_dict(ui)
    Popup = ui["Popup"]
    BoxLayout = ui["BoxLayout"]
    Label = ui["Label"]
    Button = ui["Button"]

    menu_popup = Popup(
        title=S["MESSAGES"].get("MAINTENANCE_BUTTON", "Συντηρήσεις"),
        size_hint=(0.6, 0.55),
    )
    layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    try:
        app._add_logo_to_layout(layout, height=70)
    except Exception:
        pass

    layout.add_widget(
        Label(
            text=S["MESSAGES"].get("SELECT_ACTION_PROMPT", "Επιλέξτε ενέργεια:"),
            size_hint_y=None,
            height=45,
        )
    )

    add_btn = Button(
        text=S["MESSAGES"].get("ADD_MAINTENANCE", "Καταχώρηση Συντήρησης"),
        size_hint_y=None,
        height=60,
    )

    def _on_add(_instance=None):
        try:
            app.show_maintenance_menu(parent_popup=menu_popup)
        except Exception:
            try:
                import traceback

                tb = traceback.format_exc()
                log_path = os.path.join(
                    os.path.dirname(__file__), "maintenance_error.log"
                )
                try:
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(
                            f"[{datetime.now().isoformat()}] Error opening maintenance form:\n{tb}\n"
                        )
                except Exception:
                    pass
                ui.get("show_message_popup", lambda *a, **k: None)(
                    S.get("TITLES", {}).get("ERROR", "Σφάλμα"),
                    f"Σφάλμα κατά το άνοιγμα φόρμας συντήρησης. Δείτε log: {log_path}",
                )
            except Exception:
                pass

    add_btn.bind(on_press=_on_add)
    layout.add_widget(add_btn)

    import_email_btn = Button(
        text=S["MESSAGES"].get(
            "IMPORT_MAINT_FROM_EMAIL", "Εισαγωγή συντήρησης από e-mail"
        ),
        size_hint_y=None,
        height=60,
    )

    def _on_import_email(_instance=None):
        try:
            app._show_import_maintenance_email_dialog(menu_popup)
        except Exception as exc:
            try:
                ui.get("show_message_popup", lambda *a, **k: None)(
                    S.get("TITLES", {}).get("ERROR", "Σφάλμα"),
                    f"Σφάλμα κατά την εισαγωγή από e-mail:\n{exc}",
                )
            except Exception:
                pass

    import_email_btn.bind(on_press=_on_import_email)
    layout.add_widget(import_email_btn)

    # Export maintenances (Excel)
    try:
        export_fn = ui.get("export_maintenances_per_substation")
        if export_fn:
            export_maint_btn = Button(
                text=S["MESSAGES"].get(
                    "EXPORT_MAINTENANCES_EXCEL", "Εξαγωγή Συντηρήσεων (Excel)"
                ),
                size_hint_y=None,
                height=60,
            )
            export_maint_btn.bind(
                on_press=lambda x: (menu_popup.dismiss(), export_fn(app.conn))
            )
            layout.add_widget(export_maint_btn)
    except Exception:
        pass

    def _open_history_choice(_instance=None):
        # present chooser between full history and undone maintenances
        choice_popup = Popup(
            title=S["MESSAGES"].get("MAINT_HISTORY_LABEL", "Ιστορικό Συντηρήσεων"),
            size_hint=(0.5, 0.35),
        )
        ch_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
        info = Label(
            text=S["MESSAGES"].get("SELECT_ACTION_PROMPT", "Επιλέξτε ενέργεια:"),
            size_hint_y=None,
            height=30,
        )
        ch_layout.add_widget(info)

        btns = BoxLayout(orientation="vertical", spacing=8)
        complete_btn = Button(
            text=S["MESSAGES"].get("MAINT_HISTORY_LABEL", "Ιστορικό Συντηρήσεων"),
            size_hint_y=None,
            height=50,
        )
        undone_btn = Button(
            text=S["MESSAGES"].get(
                "UNDONE_MAINTENANCES_LABEL", "Εκκρεμείς Συντηρήσεις"
            ),
            size_hint_y=None,
            height=50,
        )

        def _on_complete(_btn):
            choice_popup.dismiss()
            menu_popup.dismiss()
            app.show_maintenance_history(None)

        def _on_undone(_btn):
            choice_popup.dismiss()
            menu_popup.dismiss()
            app.show_undone_maintenances(parent_popup=menu_popup)

        complete_btn.bind(on_press=_on_complete)
        undone_btn.bind(on_press=_on_undone)
        btns.add_widget(complete_btn)
        btns.add_widget(undone_btn)
        ch_layout.add_widget(btns)
        choice_popup.content = ch_layout
        choice_popup.open()

    history_btn = Button(
        text=S["MESSAGES"].get("MAINT_HISTORY_LABEL", "Ιστορικό Συντηρήσεων"),
        size_hint_y=None,
        height=60,
    )

    def _on_history(_instance=None):
        try:
            _open_history_choice()
        except Exception as exc:
            try:
                ui.get("show_message_popup", lambda *a, **k: None)(
                    S.get("TITLES", {}).get("ERROR", "Σφάλμα"),
                    f"Σφάλμα κατά το άνοιγμα ιστορικού συντηρήσεων:\n{exc}",
                )
            except Exception:
                pass

    history_btn.bind(on_press=_on_history)
    layout.add_widget(history_btn)

    # Measurements history (global) - opens a list of measurement instances
    meas_btn = Button(
        text=S["MESSAGES"].get("MEASUREMENTS_HISTORY_LABEL", "Ιστορικό Μετρήσεων"),
        size_hint_y=None,
        height=60,
    )

    def _on_meas(_instance=None):
        try:
            menu_popup.dismiss()
            app.show_measurements_history(parent_popup=menu_popup)
        except Exception as exc:
            try:
                ui.get("show_message_popup", lambda *a, **k: None)(
                    S.get("TITLES", {}).get("ERROR", "Σφάλμα"),
                    f"Σφάλμα κατά το άνοιγμα ιστορικού μετρήσεων:\n{exc}",
                )
            except Exception:
                pass

    meas_btn.bind(on_press=_on_meas)
    layout.add_widget(meas_btn)

    cancel_btn = Button(text=S["BUTTONS"]["CANCEL"], size_hint_y=None, height=60)
    cancel_btn.bind(on_press=menu_popup.dismiss)
    layout.add_widget(cancel_btn)

    menu_popup.content = layout
    menu_popup.open()


def _show_import_maintenance_email_dialog(app, ui, parent_popup=None):
    ui = _make_ui_dict(ui)
    Popup = ui["Popup"]
    BoxLayout = ui["BoxLayout"]
    Label = ui["Label"]
    Button = ui["Button"]

    popup = Popup(
        title=S["MESSAGES"].get(
            "IMPORT_MAINT_FROM_EMAIL", "Εισαγωγή συντήρησης από e-mail"
        ),
        size_hint=(0.8, 0.35),
    )
    layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
    layout.add_widget(
        Label(
            text=S["MESSAGES"].get("SELECT_ACTION_PROMPT", "Επιλέξτε ενέργεια:"),
            size_hint_y=0.35,
        )
    )

    buttons_row = BoxLayout(orientation="horizontal", spacing=10, size_hint_y=0.35)

    import_eml_btn = Button(
        text=S["MESSAGES"].get("IMPORT_EML_FILE", "Εισαγωγή αρχείου .eml")
    )

    def _on_import_eml(_instance=None):
        popup.dismiss()
        _show_import_maintenance_eml_dialog(app, ui, parent_popup=parent_popup)

    import_eml_btn.bind(on_press=_on_import_eml)
    buttons_row.add_widget(import_eml_btn)

    import_pst_btn = Button(
        text=S["MESSAGES"].get("IMPORT_PST_FILE", "Εισαγωγή αρχείου .pst")
    )

    def _on_import_pst(_instance=None):
        popup.dismiss()
        _show_import_maintenance_pst_dialog(app, ui, parent_popup=parent_popup)

    import_pst_btn.bind(on_press=_on_import_pst)
    buttons_row.add_widget(import_pst_btn)

    import_pdf_btn = Button(
        text=S["MESSAGES"].get("IMPORT_PDF_FILE", "Εισαγωγή αρχείου .pdf")
    )

    def _on_import_pdf(_instance=None):
        popup.dismiss()
        _show_import_maintenance_pdf_dialog(app, ui, parent_popup=parent_popup)

    import_pdf_btn.bind(on_press=_on_import_pdf)
    buttons_row.add_widget(import_pdf_btn)

    layout.add_widget(buttons_row)

    cancel_btn = Button(text=S["BUTTONS"]["CANCEL"], size_hint_y=0.25)
    cancel_btn.bind(on_press=popup.dismiss)
    layout.add_widget(cancel_btn)

    popup.content = layout
    popup.open()


def _show_import_maintenance_eml_dialog(app, ui, parent_popup=None):
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
        fp = ask_open_file(
            title="Select .eml file", filetypes=(("EML files", "*.eml"),)
        )
    except ImportError:
        allow_fallback = True
        fp = None
    except Exception:
        fp = None

    if fp:
        try:
            if parent_popup:
                parent_popup.dismiss()

            app._import_maintenance_from_email_file(fp)
            return
        except Exception:
            import traceback

            traceback.print_exc()
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
            fp = ask_open_file(
                title="Select .eml file", filetypes=(("EML files", "*.eml"),)
            )
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
            show_message_popup(
                "Σφάλμα", "Παρακαλώ εισάγετε διαδρομή ή επιλέξτε αρχείο!"
            )
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


def _show_import_maintenance_pst_dialog(app, ui, parent_popup=None):
    ui = _make_ui_dict(ui)
    ask_open_file = ui["ask_open_file"]
    Popup = ui["Popup"]
    BoxLayout = ui["BoxLayout"]
    Label = ui["Label"]
    show_message_popup = ui["show_message_popup"]

    fp = ask_open_file(
        title="Select .pst file",
        filetypes=(("Outlook PST files", "*.pst"),),
    )
    if not fp:
        return

    try:
        if parent_popup:
            parent_popup.dismiss()
    except Exception:
        pass

    # Show progress dialog
    progress_popup = Popup(
        title=S["MESSAGES"].get("IMPORT_PST_FILE", "Εισαγωγή αρχείου .pst"),
        size_hint=(0.8, 0.5),
    )
    progress_layout = BoxLayout(orientation="vertical", padding=15, spacing=15)

    status_label = Label(
        text="Ανάγνωση αρχείου .pst...\nΠαρακαλώ περιμένετε...",
        size_hint_y=0.5,
        markup=True,
    )
    progress_layout.add_widget(status_label)

    # Will be added dynamically when email processing starts
    progress_bar = None
    progress_label = None
    progress_bar_container = None

    progress_popup.content = progress_layout
    progress_popup.open()

    # Import in background thread
    def _do_import():
        import time

        # Give the dialog time to render before starting the heavy operation
        time.sleep(0.5)

        try:
            from import_pst_file import import_maintenance_from_pst
            from kivy.clock import Clock

            def progress_callback(
                current=None, imported=None, failed=None, status=None
            ):
                """Update progress dialog - called from background thread."""
                try:
                    # If status message provided, display it (for loading phase)
                    if status:
                        # During loading, only update status label
                        Clock.schedule_once(
                            lambda dt, s=status: setattr(status_label, "text", s),
                            0,
                        )
                    else:
                        # Email processing phase - show real progress
                        msg = f"E-mail {current} | Επιτυχείς: {imported} | Αποτυχίες: {failed}"
                        Clock.schedule_once(
                            lambda dt, m=msg: setattr(status_label, "text", m),
                            0,
                        )

                        # Add progress bar on first email (lazy initialization)
                        if progress_bar_container is None:

                            def add_progress_bar():
                                nonlocal \
                                    progress_bar, \
                                    progress_label, \
                                    progress_bar_container
                                if progress_bar_container is None:
                                    try:
                                        from kivy.garden.progressbar import ProgressBar

                                        progress_bar = ProgressBar(
                                            max=100, value=0, size_hint_y=0.3
                                        )
                                        progress_layout.add_widget(progress_bar)
                                        progress_bar_container = True  # Mark as added
                                    except Exception:
                                        progress_label = Label(
                                            text="0%", size_hint_y=0.3
                                        )
                                        progress_layout.add_widget(progress_label)
                                        progress_bar_container = True

                            Clock.schedule_once(lambda dt: add_progress_bar(), 0)

                        # Update progress bar
                        pct = min(100, (current / max(1, current + 5)) * 100)
                        if progress_bar:
                            Clock.schedule_once(
                                lambda dt, p=pct: setattr(progress_bar, "value", p),
                                0,
                            )
                        elif progress_label:
                            pct_text = f"{int(pct)}%"
                            Clock.schedule_once(
                                lambda dt, t=pct_text: setattr(
                                    progress_label, "text", t
                                ),
                                0,
                            )
                except Exception:
                    pass

            summary = import_maintenance_from_pst(
                fp, db_path=app.db_path, progress_callback=progress_callback
            )

            # Schedule UI update on main thread
            def show_results(_dt):
                try:
                    progress_popup.dismiss()
                except Exception:
                    pass

                imported = summary.get("imported", 0)
                failed = summary.get("failed", 0)
                skipped = summary.get("skipped", 0)
                scanned = summary.get("scanned", 0)
                failures = summary.get("failures", [])

                message_lines = [
                    "✓ Ολοκληρώθηκε η εισαγωγή από αρχείο .pst.",
                    f"Συνολικά e-mail: {scanned}",
                    f"Επιτυχείς εισαγωγές: {imported}",
                    f"Αποτυχίες: {failed}",
                    f"Παραλείψεις: {skipped}",
                ]

                if failures:
                    message_lines.append("")
                    message_lines.append("Πρώτες αποτυχίες:")
                    for item in failures[:5]:
                        message_lines.append(f"- {item}")

                show_message_popup("Εισαγωγή .pst", "\n".join(message_lines))

            Clock.schedule_once(show_results, 0)

        except Exception as exc:
            from kivy.clock import Clock

            # Capture error message now, before the callback is scheduled
            error_msg = str(exc)

            def show_error(_dt):
                try:
                    progress_popup.dismiss()
                except Exception:
                    pass
                show_message_popup("Σφάλμα", f"Αποτυχία εισαγωγής .pst:\n{error_msg}")

            Clock.schedule_once(show_error, 0)

    thread = threading.Thread(target=_do_import, daemon=True)
    thread.start()


def _import_maintenance_from_email_file(app, ui, file_path):
    parse_eml_file = ui.get("parse_eml_file")
    show_message_popup = ui.get("show_message_popup")
    try:
        payload = parse_eml_file(file_path)
    except Exception as exc:
        show_message_popup("Σφάλμα", f"Αποτυχία ανάγνωσης .emλ:\n{str(exc)}")
        return

    app._open_maintenance_from_email_payload(payload)


def _show_import_maintenance_pdf_dialog(app, ui, parent_popup=None):
    ui = _make_ui_dict(ui)
    ask_open_file = ui["ask_open_file"]
    show_message_popup = ui["show_message_popup"]

    try:
        fp = ask_open_file(
            title="Select .pdf file", filetypes=(("PDF files", "*.pdf"),)
        )
    except ImportError:
        fp = None
    except Exception:
        fp = None

    if fp:
        try:
            if parent_popup:
                parent_popup.dismiss()
        except Exception:
            pass
        app._import_maintenance_from_pdf_file(fp)
        return

    show_message_popup(
        "Σφάλμα",
        "Δεν ήταν δυνατή η εμφάνιση επιλογέα αρχείων. Χρησιμοποιήστε το --file από γραμμή εντολών.",
    )


def _import_maintenance_from_pdf_file(app, ui, file_path):
    parse_pdf_file = ui.get("parse_pdf_file")
    show_message_popup = ui.get("show_message_popup")
    try:
        payload = parse_pdf_file(file_path)
    except Exception as exc:
        show_message_popup("Σφάλμα", f"Αποτυχία ανάγνωσης .pdf:\n{str(exc)}")
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

    c.execute(
        "SELECT person_id, role FROM maintenance_people WHERE maintenance_id=?",
        (maintenance_id,),
    )
    people_rows = c.fetchall()
    crew_ids = {pid for pid, role in people_rows if role == "crew"}
    if not responsible_id:
        for pid, role in people_rows:
            if role == "responsible":
                responsible_id = pid
                break

    c.execute(
        "SELECT element_id FROM maintenance_elements WHERE maintenance_id=?",
        (maintenance_id,),
    )
    element_ids = {row[0] for row in c.fetchall()}

    return {
        "maintenance_type": maint_type,
        "overall_comments": comments,
        "responsible_id": responsible_id,
        "crew_ids": crew_ids,
        "element_ids": element_ids,
    }


def _extract_calendar_date(date_time_value: str) -> str:
    text = str(date_time_value or "").strip()
    if not text:
        return ""
    for fmt in (
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
    ):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return text[:10] if len(text) >= 10 else ""


def _format_email_comment_date_label(
    received_at: str, fallback_date_time: str = ""
) -> str:
    for candidate in (received_at, fallback_date_time):
        text = str(candidate or "").strip()
        if not text:
            continue
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return f"{dt.day}/{dt.month}/{dt.year}"
        except Exception:
            pass
        date_only = _extract_calendar_date(text)
        if date_only:
            try:
                dt = datetime.strptime(date_only, "%Y-%m-%d")
                return f"{dt.day}/{dt.month}/{dt.year}"
            except Exception:
                continue
    return ""


def _date_diff_days(start_date: str, end_date: str):
    if not start_date or not end_date:
        return None
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    except Exception:
        return None
    return (end_dt.date() - start_dt.date()).days


def _normalize_email_reference_tokens(value) -> set[str]:
    tokens = set()
    values = value if isinstance(value, (list, tuple, set)) else [value]
    for raw_value in values:
        text = str(raw_value or "").strip()
        if not text:
            continue
        angle_tokens = re.findall(r"<[^>]+>", text)
        if angle_tokens:
            tokens.update(
                token.strip().lower() for token in angle_tokens if token.strip()
            )
            continue
        for token in re.split(r"[\s,;]+", text):
            normalized = token.strip().strip("<>").lower()
            if normalized:
                tokens.add(f"<{normalized}>")
    return tokens


def _normalize_email_thread_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"^\s*(?:re|fw|fwd)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", " ", text)
    text = re.sub(r"\b\d{4}[./-]\d{1,2}[./-]\d{1,2}\b", " ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _extract_email_import_metadata(payload):
    payload = payload or {}
    headers = payload.get("headers") or {}
    received_at = str(payload.get("received_at") or "").strip()
    received_dates = []
    calendar_date = _extract_calendar_date(received_at)
    if calendar_date:
        received_dates.append(calendar_date)
    subject_root = _normalize_email_thread_text(payload.get("subject") or "")
    thread_topic = _normalize_email_thread_text(headers.get("thread_topic") or "")
    metadata = {
        "message_ids": sorted(
            _normalize_email_reference_tokens(
                [headers.get("message_id"), payload.get("message_id")]
            )
        ),
        "reference_ids": sorted(
            _normalize_email_reference_tokens(
                [
                    headers.get("references"),
                    headers.get("in_reply_to"),
                    payload.get("references"),
                    payload.get("in_reply_to"),
                ]
            )
        ),
        "received_at_values": [received_at] if received_at else [],
        "received_dates": received_dates,
        "subject_roots": [subject_root] if subject_root else [],
        "thread_topics": [thread_topic] if thread_topic else [],
    }
    provided_metadata = payload.get("email_import_metadata") or {}
    if isinstance(provided_metadata, dict):
        metadata["message_ids"] = sorted(
            _normalize_email_reference_tokens(
                metadata.get("message_ids")
                + list(provided_metadata.get("message_ids") or [])
            )
        )
        metadata["reference_ids"] = sorted(
            _normalize_email_reference_tokens(
                metadata.get("reference_ids")
                + list(provided_metadata.get("reference_ids") or [])
            )
        )
        metadata["received_at_values"] = sorted(
            {
                str(value or "").strip()
                for value in (metadata.get("received_at_values") or [])
                + list(provided_metadata.get("received_at_values") or [])
                if str(value or "").strip()
            }
        )
        metadata["received_dates"] = sorted(
            {
                str(value or "").strip()
                for value in (metadata.get("received_dates") or [])
                + list(provided_metadata.get("received_dates") or [])
                if str(value or "").strip()
            }
        )
        metadata["subject_roots"] = sorted(
            {
                _normalize_email_thread_text(value)
                for value in (metadata.get("subject_roots") or [])
                + list(provided_metadata.get("subject_roots") or [])
                if _normalize_email_thread_text(value)
            }
        )
        metadata["thread_topics"] = sorted(
            {
                _normalize_email_thread_text(value)
                for value in (metadata.get("thread_topics") or [])
                + list(provided_metadata.get("thread_topics") or [])
                if _normalize_email_thread_text(value)
            }
        )
    return metadata


def _normalize_stored_email_import_metadata(metadata, fallback_date_time=""):
    metadata = metadata if isinstance(metadata, dict) else {}
    normalized = {
        "message_ids": sorted(
            _normalize_email_reference_tokens(metadata.get("message_ids") or [])
        ),
        "reference_ids": sorted(
            _normalize_email_reference_tokens(metadata.get("reference_ids") or [])
        ),
        "received_at_values": sorted(
            {
                str(value or "").strip()
                for value in (metadata.get("received_at_values") or [])
                if str(value or "").strip()
            }
        ),
        "received_dates": sorted(
            {
                str(value or "").strip()
                for value in (metadata.get("received_dates") or [])
                if str(value or "").strip()
            }
        ),
        "subject_roots": sorted(
            {
                _normalize_email_thread_text(value)
                for value in (metadata.get("subject_roots") or [])
                if _normalize_email_thread_text(value)
            }
        ),
        "thread_topics": sorted(
            {
                _normalize_email_thread_text(value)
                for value in (metadata.get("thread_topics") or [])
                if _normalize_email_thread_text(value)
            }
        ),
    }
    fallback_date = _extract_calendar_date(fallback_date_time)
    if fallback_date and fallback_date not in normalized["received_dates"]:
        normalized["received_dates"].append(fallback_date)
    return normalized


def _load_stored_email_import_metadata(raw_data_json, fallback_date_time=""):
    if not raw_data_json:
        return _normalize_stored_email_import_metadata({}, fallback_date_time)
    try:
        payload = json.loads(raw_data_json)
    except Exception:
        payload = {}
    metadata = payload.get("email_import") if isinstance(payload, dict) else {}
    return _normalize_stored_email_import_metadata(metadata, fallback_date_time)


def _get_maintenance_completion_state(raw_data_json, has_pending_tasks_row: bool):
    if has_pending_tasks_row:
        return False
    if not raw_data_json:
        return None
    try:
        payload = json.loads(raw_data_json)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    workflow = (
        payload.get("workflow") if isinstance(payload.get("workflow"), dict) else {}
    )
    stage_key = str(workflow.get("current_stage") or "").strip().lower()
    if not stage_key:
        return None
    return stage_key == "completed"


def _score_open_maintenance_match(
    incoming_metadata,
    candidate_metadata,
    incoming_date,
    candidate_date,
):
    incoming_message_ids = set(incoming_metadata.get("message_ids") or [])
    incoming_reference_ids = set(incoming_metadata.get("reference_ids") or [])
    candidate_message_ids = set(candidate_metadata.get("message_ids") or [])
    candidate_reference_ids = set(candidate_metadata.get("reference_ids") or [])
    incoming_subjects = set(incoming_metadata.get("subject_roots") or [])
    candidate_subjects = set(candidate_metadata.get("subject_roots") or [])
    incoming_topics = set(incoming_metadata.get("thread_topics") or [])
    candidate_topics = set(candidate_metadata.get("thread_topics") or [])

    same_thread = bool(
        (incoming_message_ids and incoming_message_ids & candidate_reference_ids)
        or (incoming_reference_ids and incoming_reference_ids & candidate_message_ids)
        or (incoming_reference_ids and incoming_reference_ids & candidate_reference_ids)
        or (incoming_subjects and incoming_subjects & candidate_subjects)
        or (incoming_topics and incoming_topics & candidate_topics)
        or (incoming_subjects and incoming_subjects & candidate_topics)
        or (incoming_topics and incoming_topics & candidate_subjects)
    )

    candidate_anchor_date = max(
        candidate_metadata.get("received_dates") or [candidate_date or ""]
    )
    effective_gap = _date_diff_days(
        candidate_anchor_date or candidate_date, incoming_date
    )
    within_ongoing_window = effective_gap is not None and 0 <= effective_gap <= 10

    if same_thread:
        return {
            "score": 100 - min(max(effective_gap or 0, 0), 20),
            "same_thread": True,
            "within_ongoing_window": within_ongoing_window,
            "effective_gap": effective_gap,
        }
    if within_ongoing_window:
        return {
            "score": 50 - max(effective_gap or 0, 0),
            "same_thread": False,
            "within_ongoing_window": True,
            "effective_gap": effective_gap,
        }
    return None


def _resolve_candidate_isolation_request_id(
    app,
    substation_id: int,
    maintenance_date_time: str,
    stored_isolation_request_id=None,
    isolation_matcher=None,
):
    if stored_isolation_request_id:
        return stored_isolation_request_id
    if not callable(isolation_matcher):
        return None
    try:
        return isolation_matcher(app.conn, substation_id, maintenance_date_time)
    except Exception:
        return None


def _find_matching_open_maintenance_candidate(
    app,
    substation_id: int,
    date_time_value: str,
    payload=None,
    incoming_isolation_request_id=None,
    isolation_matcher=None,
):
    incoming_date = _extract_calendar_date(date_time_value)
    if not substation_id or not incoming_date:
        return None

    incoming_metadata = _extract_email_import_metadata(payload or {})

    c = app.conn.cursor()
    c.execute(
        """
        SELECT
            m.id,
            m.date_time,
            m.data_json,
            t.maintenance_id IS NOT NULL,
            m.isolation_request_id
        FROM maintenance m
        LEFT JOIN maintenance_pending_tasks t ON t.maintenance_id = m.id
        WHERE m.substation_id = ?
        ORDER BY m.date_time DESC, m.id DESC
        """,
        (substation_id,),
    )

    best_reuse_candidate = None
    best_reuse_score = None
    best_prompt_candidate = None
    best_prompt_score = None
    for (
        maintenance_id,
        maintenance_date_time,
        raw_data_json,
        has_pending_tasks_row,
        stored_isolation_request_id,
    ) in c.fetchall() or []:
        is_completed = _get_maintenance_completion_state(
            raw_data_json, bool(has_pending_tasks_row)
        )
        if is_completed is True:
            continue
        candidate_date = _extract_calendar_date(maintenance_date_time)
        candidate_metadata = _load_stored_email_import_metadata(
            raw_data_json, maintenance_date_time
        )
        match_info = _score_open_maintenance_match(
            incoming_metadata,
            candidate_metadata,
            incoming_date,
            candidate_date,
        )
        if match_info is None:
            continue

        candidate_isolation_request_id = _resolve_candidate_isolation_request_id(
            app,
            substation_id,
            maintenance_date_time,
            stored_isolation_request_id=stored_isolation_request_id,
            isolation_matcher=isolation_matcher,
        )
        if (
            incoming_isolation_request_id
            and candidate_isolation_request_id
            and candidate_isolation_request_id != incoming_isolation_request_id
        ):
            continue

        adjusted_score = match_info["score"]
        if is_completed is not False:
            adjusted_score -= 5

        candidate = {
            "maintenance_id": maintenance_id,
            "maintenance_date_time": maintenance_date_time,
            "candidate_isolation_request_id": candidate_isolation_request_id,
            "incoming_isolation_request_id": incoming_isolation_request_id,
            "same_thread": bool(match_info.get("same_thread")),
            "within_ongoing_window": bool(match_info.get("within_ongoing_window")),
            "effective_gap": match_info.get("effective_gap"),
            "decision": "reuse"
            if match_info.get("same_thread")
            or (
                incoming_isolation_request_id
                and candidate_isolation_request_id == incoming_isolation_request_id
            )
            else "prompt",
        }

        if candidate["decision"] == "reuse":
            if best_reuse_score is None or adjusted_score > best_reuse_score:
                best_reuse_score = adjusted_score
                best_reuse_candidate = candidate
            continue

        if best_prompt_score is None or adjusted_score > best_prompt_score:
            best_prompt_score = adjusted_score
            best_prompt_candidate = candidate

    return best_reuse_candidate or best_prompt_candidate


def _show_existing_maintenance_import_choice_popup(
    ui,
    *,
    substation_name: str,
    match_candidate,
    on_link_existing,
    on_create_new,
):
    ui = _make_ui_dict(ui)
    Popup = ui.get("Popup")
    BoxLayout = ui.get("BoxLayout")
    Label = ui.get("Label")
    Button = ui.get("Button")
    if not Popup or not BoxLayout or not Label or not Button:
        return False

    maintenance_date = str(match_candidate.get("maintenance_date_time") or "").strip()
    gap_days = match_candidate.get("effective_gap")
    gap_label = f"Απόσταση: {gap_days} ημέρες." if isinstance(gap_days, int) else ""
    message = (
        "Βρέθηκε πρόσφατη ανοιχτή συντήρηση για τον ίδιο υποσταθμό.\n\n"
        f"Υποσταθμός: {substation_name}\n"
        f"Υπάρχουσα συντήρηση: {maintenance_date or '-'}\n"
        f"{gap_label}\n\n"
        "Αν πρόκειται για συνέχεια της ίδιας εργασίας, συνδέστε το e-mail στην υπάρχουσα συντήρηση. "
        "Αν πρόκειται για νέα περίπτωση, δημιουργήστε νέα συντήρηση."
    ).strip()

    popup = Popup(title="Επιλογή Συντήρησης", size_hint=(0.78, 0.42))
    layout = BoxLayout(orientation="vertical", padding=12, spacing=10)
    layout.add_widget(Label(text=message))

    buttons = BoxLayout(size_hint_y=None, height=48, spacing=8)
    existing_btn = Button(text="Σύνδεση σε υπάρχουσα")
    new_btn = Button(text="Νέα συντήρηση")
    cancel_btn = Button(text="Ακύρωση")
    buttons.add_widget(existing_btn)
    buttons.add_widget(new_btn)
    buttons.add_widget(cancel_btn)
    layout.add_widget(buttons)
    popup.content = layout

    def _run_and_close(callback):
        def _inner(_instance=None):
            popup.dismiss()
            callback()

        return _inner

    existing_btn.bind(on_press=_run_and_close(on_link_existing))
    new_btn.bind(on_press=_run_and_close(on_create_new))
    cancel_btn.bind(on_press=lambda _instance=None: popup.dismiss())
    popup.open()
    return True


def open_maintenance_from_email_payload(
    app,
    ui,
    payload,
    forced_substation=None,
    after_save_callback=None,
    after_cancel_callback=None,
):
    # this mirrors the logic previously on SubstationApp but keeps UI/API via app
    subject = payload.get("subject", "")
    body = payload.get("body", "")
    sender_name = payload.get("sender_name", "")
    sender_email = payload.get("sender_email", "")
    received_at = payload.get("received_at", "")
    attachment_paths = payload.get("attachment_paths", []) or []

    try:
        from maintenance_email_importer import (
            _find_elements_in_body,
            _find_people_in_body,
            _match_person_by_sender,
            find_matching_isolation_request_id,
            infer_maintenance_type_from_subject,
            infer_substation_from_email,
        )
    except Exception:
        _find_elements_in_body = None
        _find_people_in_body = None
        _match_person_by_sender = None
        infer_maintenance_type_from_subject = None
        infer_substation_from_email = None
        find_matching_isolation_request_id = None

    c = app.conn.cursor()
    c.execute("SELECT id, name FROM substations ORDER BY name")
    substations = c.fetchall()
    from popups import show_message_popup

    if not substations:
        show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["NO_SUBSTATIONS"])
        return

    date_time_value = ""
    if received_at:
        try:
            dt = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
            date_time_value = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            date_time_value = ""
    if not date_time_value:
        date_time_value = datetime.now().strftime("%Y-%m-%d %H:%M")

    substation = None
    if forced_substation:
        for sub_id, sub_name in substations:
            if sub_name == forced_substation:
                substation = (sub_id, sub_name)
                break
    if not substation and callable(infer_substation_from_email):
        inferred = infer_substation_from_email(
            app.conn,
            subject=subject,
            body=body,
            date_time_value=date_time_value,
            received_at=received_at,
        )
        if inferred:
            substation = (inferred["id"], inferred["name"])
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

    c.execute(
        "SELECT id, name, role FROM people WHERE active=1 ORDER BY COALESCE(surname, name) COLLATE NOCASE"
    )
    people = c.fetchall()
    if not people:
        show_message_popup(
            "Σφάλμα",
            "Δεν υπάρχουν καταχωρημένα άτομα. Παρακαλώ προσθέστε προσωπικό.",
        )
        return

    responsible_id = None
    if callable(_match_person_by_sender):
        person = _match_person_by_sender(app.conn, sender_email, sender_name)
        responsible_id = person["id"] if person else None
    if responsible_id is None:
        responsible_id = app._match_person_by_sender(sender_name, people)

    crew_ids = set()
    if callable(_find_people_in_body):
        crew_ids = _find_people_in_body(
            app.conn,
            body,
            exclude_ids={responsible_id} if responsible_id else set(),
        )
    else:
        crew_ids = app._find_people_in_body(
            body, people, exclude_ids={responsible_id} if responsible_id else set()
        )

    people_name_by_id = {pid: name for pid, name, _role in people}
    log_import_diagnostic(
        "email_ui_people_detected",
        sender_name=sender_name or "",
        subject=subject or "",
        substation_id=substation_id,
        substation_name=substation_name,
        body_length=len(body or ""),
        detected_responsible_id=responsible_id,
        detected_responsible_name=people_name_by_id.get(responsible_id),
        detected_crew_ids=sorted(crew_ids),
        detected_crew_names=[people_name_by_id.get(pid) for pid in sorted(crew_ids)],
    )

    if callable(_find_elements_in_body):
        element_ids = _find_elements_in_body(app.conn, body, substation_id)
    else:
        element_ids = app._find_elements_in_body(body, substation_id)
    incomplete_elements = set(element_ids)

    default_maintenance_type = S.get("MESSAGES", {}).get(
        "MAINT_TYPE_DEFAULT", "Επαναληπτική συντήρηση"
    )
    if callable(infer_maintenance_type_from_subject):
        default_maintenance_type = infer_maintenance_type_from_subject(
            subject, default_maintenance_type
        )

    linked_isolation_request_id = None
    if callable(find_matching_isolation_request_id):
        linked_isolation_request_id = find_matching_isolation_request_id(
            app.conn, substation_id, date_time_value
        )

    prefill = {
        "substation_id": substation_id,
        "substation_name": substation_name,
        "maintenance_type": default_maintenance_type,
        "date_time": date_time_value,
        "overall_comments": body,
        "responsible_id": responsible_id,
        "crew_ids": crew_ids,
        "element_ids": element_ids,
        "incomplete_elements": incomplete_elements,
        "attachment_paths": attachment_paths,
        "linked_isolation_request_id": linked_isolation_request_id,
        "_diag_origin": "email_ui_prefill",
        "_diag_detected_responsible_id": responsible_id,
        "_diag_detected_crew_ids": sorted(crew_ids),
        "_diag_sender_name": sender_name or "",
        "_diag_subject": subject or "",
        "_email_comment_label": _format_email_comment_date_label(
            received_at,
            date_time_value,
        ),
        "_email_comment_preformatted": bool(payload.get("_email_comment_preformatted")),
        "pending_tasks_text": "Ανοιχτή Συντήρηση",
    }

    prev = _get_previous_maintenance_defaults(app, substation_id, date_time_value)
    if prev:
        if not prefill["responsible_id"] and prev.get("responsible_id"):
            prefill["responsible_id"] = prev.get("responsible_id")
        # Don't use previous crew - only include explicitly mentioned crew from email body
        # if not prefill["crew_ids"] and prev.get("crew_ids"):
        #     prefill["crew_ids"] = prev.get("crew_ids")
        if not prefill["maintenance_type"] and prev.get("maintenance_type"):
            prefill["maintenance_type"] = prev.get("maintenance_type")
        if not prefill["overall_comments"] and prev.get("overall_comments"):
            prefill["overall_comments"] = prev.get("overall_comments")

    email_import_metadata = _extract_email_import_metadata(payload)

    open_maintenance_match = _find_matching_open_maintenance_candidate(
        app,
        substation_id,
        date_time_value,
        payload=payload,
        incoming_isolation_request_id=linked_isolation_request_id,
        isolation_matcher=find_matching_isolation_request_id,
    )

    def _open_existing_maintenance():
        existing_prefill = dict(prefill)
        existing_prefill["_wizard_stage"] = "elements"
        existing_prefill["email_import_metadata"] = email_import_metadata
        app.show_maintenance_menu(
            preselected_substation_name=substation_name,
            parent_popup=None,
            maintenance_id=open_maintenance_match["maintenance_id"],
            after_save_callback=after_save_callback,
            after_cancel_callback=after_cancel_callback,
            prefill_data=existing_prefill,
        )

    def _open_new_maintenance():
        new_prefill = {
            **prefill,
            "email_import_metadata": email_import_metadata,
        }
        if not new_prefill["responsible_id"]:
            app._prompt_responsible_selection(people, new_prefill)
            return

        app.show_maintenance_menu(
            preselected_substation_name=substation_name,
            parent_popup=None,
            maintenance_id=None,
            after_save_callback=after_save_callback,
            after_cancel_callback=after_cancel_callback,
            prefill_data=new_prefill,
        )

    if open_maintenance_match:
        if open_maintenance_match["decision"] == "reuse":
            _open_existing_maintenance()
            return

        prompt_choice = getattr(app, "_prompt_existing_maintenance_import_choice", None)
        if callable(prompt_choice):
            prompt_choice(
                match_candidate=open_maintenance_match,
                prefill_data=dict(prefill),
                open_existing=_open_existing_maintenance,
                open_new=_open_new_maintenance,
            )
            return

        if _show_existing_maintenance_import_choice_popup(
            ui,
            substation_name=substation_name,
            match_candidate=open_maintenance_match,
            on_link_existing=_open_existing_maintenance,
            on_create_new=_open_new_maintenance,
        ):
            return

        _open_existing_maintenance()
        return

    if not prefill["responsible_id"]:
        app._prompt_responsible_selection(people, prefill)
        return

    app.show_maintenance_menu(
        preselected_substation_name=substation_name,
        parent_popup=None,
        maintenance_id=None,
        after_save_callback=after_save_callback,
        after_cancel_callback=after_cancel_callback,
        prefill_data={
            **prefill,
            "email_import_metadata": email_import_metadata,
        },
    )
