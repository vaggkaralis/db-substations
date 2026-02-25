import json
import os
from datetime import datetime

from strings_proxy import STRINGS as S


def _get_inspection_fallback_fields():
    base = S["MESSAGES"].get(
        "INSPECTION_BASE_FIELDS",
        [
            "Υποσταθμός",
            "Αρ. Δελτίου",
            "Μήνας",
            "Ονομ. Επιθεωρητή",
            "Περιοχή",
            "Ημέρα",
            "Έτος",
            "Ημερομηνία",
        ],
    )

    inspection_rows = S["MESSAGES"].get("INSPECTION_ROWS", [])

    # Return a combined list: basic metadata fields followed by the inspection rows.
    return base + inspection_rows

# Try to parse stored JSON and show a structured, categorized popup listing all fields

def _format_inspection_value(value):
    if value is None:
        return ""
    try:
        import math

        if isinstance(value, float) and math.isnan(value):
            return ""
    except Exception:
        pass

    if hasattr(value, "to_pydatetime"):
        try:
            value = value.to_pydatetime()
        except Exception:
            pass

    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")

    if isinstance(value, float) and value.is_integer():
        value = int(value)

    return str(value).strip()


def _parse_inspection_date(value):
    if value is None:
        return ""
    if hasattr(value, "to_pydatetime"):
        try:
            value = value.to_pydatetime()
        except Exception:
            pass
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")

    text = str(value).strip()
    if not text:
        return ""

    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass

    return text


def _derive_month_key(date_str):
    if not date_str:
        return datetime.now().strftime("%Y-%m")

    for fmt in (
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M",
        "%d/%m/%Y",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m")
        except Exception:
            pass

    if len(date_str) >= 7 and date_str[4] == "-":
        return date_str[:7]

    return datetime.now().strftime("%Y-%m")


def _detect_inspection_column(columns, keywords):
    for col in columns:
        col_text = str(col).strip().lower()
        for key in keywords:
            if key in col_text:
                return col
    return None


def import_inspections_from_file(app, file_path):
    import pandas as pd

    try:
        if file_path.endswith(".xlsx"):
            df = pd.read_excel(file_path)
        elif file_path.endswith(".csv"):
            df = pd.read_csv(file_path)
        else:
            from popups import show_message_popup

            show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["UNSUPPORTED_FILE_FORMAT"])
            return
    except Exception as e:
        from popups import show_message_popup

        show_message_popup(S["TITLES"]["ERROR"], f"{S['MESSAGES']['IMPORT_FAILED']}\n{str(e)}")
        return

    if df.empty:
        from popups import show_message_popup
        show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["FILE_HAS_NO_DATA"])
        return

    # Process rows and insert into inspections table
    columns = list(df.columns)
    date_col = _detect_inspection_column(columns, ["ημερομην", "ημ/ν", "date"])
    substation_col = _detect_inspection_column(columns, ["υποσταθ", "substation"])

    inserted = 0
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    c = app.conn.cursor()

    for _, row in df.iterrows():
        if hasattr(row, "isna") and row.isna().all():
            continue

        date_value = row.get(date_col) if date_col else None
        inspection_date = _parse_inspection_date(date_value) or datetime.now().strftime("%Y-%m-%d")
        month_key = _derive_month_key(inspection_date)

        substation_name = ""
        if substation_col:
            substation_name = _format_inspection_value(row.get(substation_col))

        substation_id = None
        if substation_name:
            c.execute("SELECT id FROM substations WHERE name=?", (substation_name,))
            sub_row = c.fetchone()
            substation_id = sub_row[0] if sub_row else None

        fields = []
        for col in columns:
            value = row.get(col)
            try:
                if hasattr(value, 'astype'):
                    # pandas scalar handling
                    import pandas as _pd

                    if _pd.isna(value):
                        value = ""
            except Exception:
                pass
            fields.append({"label": str(col), "value": _format_inspection_value(value)})

        data_json = json.dumps({"fields": fields}, ensure_ascii=False)

        c.execute(
            """
            INSERT INTO inspections (
                substation_id, substation_name, inspection_date,
                month_key, data_json, source_file, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                substation_id,
                substation_name,
                inspection_date,
                month_key,
                data_json,
                os.path.basename(file_path),
                created_at,
            ),
        )
        inserted += 1

    app.conn.commit()
    from popups import show_message_popup
    show_message_popup(
        S["MESSAGES"].get("IMPORT_INSPECTIONS_TITLE", "Εισαγωγή Επιθεωρήσεων"),
        S["MESSAGES"].get("IMPORT_INSPECTIONS_DONE", f"Ολοκληρώθηκε η εισαγωγή ({inserted} εγγραφές).").format(inserted=inserted),
        callback=lambda: app.show_inspection_history(None),
    )

def _show_edit_inspection_popup(app, inspection_id, fields):
    """Show an edit form for an inspection and save changes back to DB."""
    try:
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.gridlayout import GridLayout
        from kivy.uix.label import Label
        from kivy.uix.popup import Popup
        from kivy.uix.scrollview import ScrollView
        from kivy.uix.textinput import TextInput

        popup = Popup(title=S["TITLES"].get("INSPECTION_DETAILS", "Επεξεργασία Επιθεώρησης"), size_hint=(0.95, 0.9))
        layout = BoxLayout(orientation="vertical", spacing=8, padding=8)

        # Build a categorized edit form using the same section slices
        # as the details view so users see logical groups of fields.
        scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
        content = GridLayout(cols=1, spacing=4, size_hint_y=None, size_hint_x=1, padding=4)
        content.bind(minimum_height=content.setter("height"))

        inputs = []

        # Ensure fields is a list of dicts; fallback to generated labels if missing
        if not isinstance(fields, list) or not fields:
            # create placeholder fields using inspection rows
            combined = _get_inspection_fallback_fields()
            fields = [{"label": lbl, "value": ""} for lbl in combined]

        rows = S["MESSAGES"].get("INSPECTION_ROWS", [])
        # define same sections as in details (first slices correspond to metadata)
        sections = [
            (S["MESSAGES"].get("INSPECTION_SECTION_2", ""), 0, 4),
            (S["MESSAGES"].get("INSPECTION_SECTION_3", ""), 4, 12),
            (S["MESSAGES"].get("INSPECTION_SECTION_3A", ""), 12, 13),
            (S["MESSAGES"].get("INSPECTION_SECTION_3B", ""), 13, 15),
            (S["MESSAGES"].get("INSPECTION_SECTION_4", ""), 15, 18),
            (S["MESSAGES"].get("INSPECTION_SECTION_5", ""), 18, 19),
            (S["MESSAGES"].get("INSPECTION_SECTION_6", ""), 19, 21),
        ]

        # first 8 items are metadata in the fields list; map them directly
        meta_items = fields[:8]

        def _add_section(title, items):
            # header
            hdr = Button(text=title or "", size_hint_y=None, height=36)
            try:
                hdr.markup = True
            except Exception:
                pass
            content.add_widget(hdr)

            # body: rows with label + input
            for it in items:
                lbl_text = it.get("label") if isinstance(it, dict) else str(it)
                val_text = it.get("value") if isinstance(it, dict) else ""
                row = BoxLayout(orientation='horizontal', size_hint_y=None, height=40, spacing=6)
                lbl = Label(text=f"[b]{lbl_text}[/b]", markup=True, size_hint_x=0.4, halign='left', valign='middle')
                ti = TextInput(text=val_text or '', size_hint_x=0.6)
                # ensure text wraps and aligns properly
                lbl.bind(size=lambda inst, sz: setattr(inst, 'text_size', (inst.width, None)))
                row.add_widget(lbl)
                row.add_widget(ti)
                content.add_widget(row)
                inputs.append((lbl_text, ti))

        # Add metadata section first
        content.add_widget(Label(text="", size_hint_y=None, height=6))
        meta_block = [{"label": f.get('label'), "value": f.get('value')} for f in meta_items]
        _add_section(S["MESSAGES"].get("INSPECTION_SECTION_META", "Μεταδεδομένα"), meta_block)

        # Add the rest of the sections using the rows labels and the body values
        body = fields[8:]
        idx = 0
        for sec_title, start, end in sections:
            sec_items = []
            for i in range(start, min(end, len(rows))):
                if idx >= len(body):
                    sec_items.append({"label": rows[i], "value": ""})
                else:
                    sec_items.append({"label": rows[i], "value": body[idx].get('value')})
                idx += 1
            _add_section(sec_title or f"Ενότητα {start}", sec_items)

        # Remaining fields (opinions / extras)
        if idx < len(body):
            rest_items = [{"label": f.get('label'), "value": f.get('value')} for f in body[idx:]]
            _add_section(S["MESSAGES"].get("INSPECTION_SECTION_7", "Απόψεις"), rest_items)

        scroll.add_widget(content)
        layout.add_widget(scroll)

        def _save(_):
            new_fields = []
            for label, ti in inputs:
                new_fields.append({"label": label, "value": ti.text.strip()})

            # derive main metadata
            substation_name = new_fields[0].get('value') if new_fields else None
            inspection_date = None
            for nf in new_fields:
                if nf.get('label') == S["MESSAGES"].get("DATE_PLAIN", "Ημερομηνία"):
                    inspection_date = nf.get('value')
                    break

            month_key = _derive_month_key(inspection_date) if inspection_date else None

            try:
                c = app.conn.cursor()
                sub_id = None
                if substation_name:
                    c.execute("SELECT id FROM substations WHERE name=?", (substation_name,))
                    r = c.fetchone()
                    sub_id = r[0] if r else None

                data_json = json.dumps({"fields": new_fields}, ensure_ascii=False)
                c.execute(
                    "UPDATE inspections SET substation_id=?, substation_name=?, inspection_date=?, month_key=?, data_json=? WHERE id=?",
                    (sub_id, substation_name, inspection_date, month_key, data_json, inspection_id),
                )
                app.conn.commit()
            except Exception:
                pass

            popup.dismiss()
            try:
                from popups import show_message_popup

                show_message_popup(S["TITLES"].get("SUCCESS", "Επιτυχία"), S["MESSAGES"].get("INSPECTION_SAVED", "Η επιθεώρηση καταχωρήθηκε!"))
            except Exception:
                pass

        btn_row = BoxLayout(size_hint_y=None, height=40, spacing=8)
        save_btn = Button(text=S.get("BUTTONS", {}).get("SAVE", "Αποθήκευση"))
        cancel_btn = Button(text=S.get("BUTTONS", {}).get("CANCEL", "Ακύρωση"))
        save_btn.bind(on_press=_save)
        cancel_btn.bind(on_press=lambda _btn: popup.dismiss())
        btn_row.add_widget(save_btn)
        btn_row.add_widget(cancel_btn)
        layout.add_widget(btn_row)

        popup.content = layout
        popup.open()
    except Exception:
        return None

    


def show_inspection_menu_popup_delegate(app, instance=None):
    """Delegate to the app's `show_inspection_menu_popup` method.

    This avoids referencing module-level functions that remain in `DBrun.py`.
    """
    return getattr(app, "show_inspection_menu_popup")(instance)


def handle_inspection_menu(app, instance=None):
    """Default implementation for the inspection menu.

    This is a non-delegating handler that DBrun can call directly to
    avoid an infinite recursion when the delegate points back to the
    app method. By default it opens the inspection history view.
    """
    # Prefer a private app implementation if provided
    if hasattr(app, "_show_inspection_menu"):
        return getattr(app, "_show_inspection_menu")(instance)

    # Default: show a small menu offering to add a new inspection or view history.
    try:
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.popup import Popup

        title = S.get("BUTTONS", {}).get("INSPECTIONS", "Επιθεωρήσεις")
        popup = Popup(title=title, size_hint=(0.6, 0.3))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        btn_row = BoxLayout(orientation="horizontal", spacing=10, size_hint_y=0.7)
        entry_btn = Button(text=S.get("TITLES", {}).get("INSPECTION_ENTRY", "Καταχώρηση Επιθεώρησης"))
        hist_btn = Button(text=S.get("TITLES", {}).get("INSPECTION_HISTORY", "Ιστορικό Επιθεώρησης"))

        def on_entry(_):
            try:
                popup.dismiss()
            except Exception:
                pass
            if hasattr(app, "show_inspection_entry_popup"):
                return getattr(app, "show_inspection_entry_popup")(None)

        def on_history(_):
            try:
                popup.dismiss()
            except Exception:
                pass
            return handle_inspection_history(app, instance)

        entry_btn.bind(on_press=on_entry)
        hist_btn.bind(on_press=on_history)
        btn_row.add_widget(entry_btn)
        btn_row.add_widget(hist_btn)

        close_btn = Button(text=S.get("BUTTONS", {}).get("CANCEL", "Ακύρωση"), size_hint_y=0.3)
        close_btn.bind(on_press=lambda _: popup.dismiss())

        layout.add_widget(btn_row)
        layout.add_widget(close_btn)

        popup.content = layout
        popup.open()
    except Exception:
        # If UI libs unavailable, fall back to calling history directly
        if hasattr(app, "show_inspection_history"):
            return getattr(app, "show_inspection_history")(instance)

    return None


def show_import_inspections_dialog_delegate(app, instance):
    """Delegate to the app's import dialog creator for inspections."""
    # Some apps expose a helper `_create_file_import_dialog`; fall back to
    # calling the app method `show_import_inspections_dialog` if present.
    if hasattr(app, "_create_file_import_dialog"):
        return app._create_file_import_dialog(
            S["MESSAGES"].get("IMPORT_INSPECTIONS_DIALOG", "Εισαγωγή επιθεωρήσεων από αρχείο"),
            lambda fp: import_inspections_from_file(app, fp),
        )
    return getattr(app, "show_import_inspections_dialog")(instance)


def show_inspection_history_delegate(app, instance=None):
    return getattr(app, "show_inspection_history")(instance)


def handle_inspection_history(app, instance=None):
    """Default non-recursive inspection history handler.

    Shows a simple summary using the app's DB connection or calls a
    private app implementation if available. This prevents delegates
    from calling back into `app.show_inspection_history` and creating
    a recursion loop.
    """
    # If the app provides a private implementation, prefer that.
    if hasattr(app, "_show_inspection_history"):
        return getattr(app, "_show_inspection_history")(instance)

    # Otherwise, attempt a minimal summary popup (safe fallback).
    try:
        # previously logged for debugging; now proceed normally
        c = app.conn.cursor()
        c.execute("SELECT COUNT(*) FROM inspections")
        row = c.fetchone()
        count = row[0] if row else 0
        from popups import show_message_popup

        # If there are no inspections yet, offer to create one directly
        # instead of only showing a count message. This makes the UI
        # discoverable for users who expect to add the first inspection.
        if count == 0:
            # if called from a parent popup, dismiss it so new popup is visible
            try:
                if instance and hasattr(instance, 'dismiss'):
                    instance.dismiss()
            except Exception:
                pass
            show_message_popup(
                S["TITLES"].get("INSPECTION_HISTORY", "Ιστορικό Επιθεώρησης"),
                S["MESSAGES"].get("NO_INSPECTIONS", "Δεν υπάρχουν καταχωρημένες επιθεωρήσεις. Θέλετε να δημιουργήσετε μία;"),
                callback=lambda: getattr(app, "show_inspection_entry_popup")(None),
            )
        else:
            try:
                if instance and hasattr(instance, 'dismiss'):
                    instance.dismiss()
            except Exception:
                pass
            show_message_popup(
                S["TITLES"].get("INSPECTION_HISTORY", "Ιστορικό Επιθεώρησης"),
                S["MESSAGES"].get("INSPECTION_COUNT_FMT", "{count} εγγραφές επιθεώρησης").format(count=count),
            )
    except Exception:
        # Give up silently to avoid crashing the app in this fallback.
        return None

    return None


def handle_substation_inspection_history(app, substation_id, substation_name, parent_display_popup=None):
    """Non-recursive handler for showing a substation's inspection history.

    Safe fallback: shows a simple count or delegates to a private app
    implementation `_show_substation_inspection_history` if present.
    """
    if hasattr(app, "_show_substation_inspection_history"):
        return getattr(app, "_show_substation_inspection_history")(substation_id, substation_name, parent_display_popup)

    try:
        c = app.conn.cursor()
        c.execute("SELECT COUNT(*) FROM inspections WHERE substation_id=?", (substation_id,))
        row = c.fetchone()
        count = row[0] if row else 0
        from popups import show_message_popup

        # Dismiss parent popup if provided so the message is visible
        try:
            if parent_display_popup and hasattr(parent_display_popup, 'dismiss'):
                parent_display_popup.dismiss()
        except Exception:
            pass

            show_message_popup(
                S["MESSAGES"].get("SUBSTATION_INSPECTION_HISTORY_TITLE_FMT", "Ιστορικό Επιθεώσεων - {substation_name}").format(substation_name=substation_name),
                S["MESSAGES"].get("SUBSTATION_INSPECTION_COUNT_FMT", "{count} εγγραφές επιθεώρησης για τον υποσταθμό {substation_name}").format(count=count, substation_name=substation_name),
            )
    except Exception:
        return None

    return None


def handle_inspection_details(app, inspection_id):
    """Non-recursive handler to show inspection details.

    Falls back to a message popup summarizing the inspection if a
    private implementation is not available.
    """
    if hasattr(app, "_show_inspection_details"):
        return getattr(app, "_show_inspection_details")(inspection_id)

    try:
        c = app.conn.cursor()
        c.execute("SELECT substation_name, inspection_date, data_json FROM inspections WHERE id=?", (inspection_id,))
        row = c.fetchone()
        if not row:
            from popups import show_message_popup

            show_message_popup(S["TITLES"].get("INFO", "Πληροφορία"), S["MESSAGES"].get("RECORD_NOT_FOUND", "Το αρχείο δεν βρέθηκε"))
            return None

        sub_name, insp_date, data_json = row

        try:
            data = json.loads(data_json)
            fields = data.get("fields", [])

            from kivy.clock import Clock
            from kivy.uix.boxlayout import BoxLayout
            from kivy.uix.button import Button
            from kivy.uix.gridlayout import GridLayout
            from kivy.uix.label import Label
            from kivy.uix.popup import Popup
            from kivy.uix.scrollview import ScrollView

            popup = Popup(title=S["TITLES"].get("INSPECTION_DETAILS", "Λεπτομέρειες Επιθεώρησης"), size_hint=(0.98, 0.95))
            layout = BoxLayout(orientation="vertical", spacing=8, padding=8)

            # Header: metadata summary
            meta = BoxLayout(orientation="horizontal", size_hint_y=None, height=60, spacing=8)
            meta_left = BoxLayout(orientation="vertical")
            meta_left.add_widget(Label(text=f"[b]{S['MESSAGES'].get('SUBSTATION_LABEL_PLAIN', 'Υποσταθμός')}:[/b] {sub_name or '-'}", markup=True))
            meta_left.add_widget(Label(text=f"[b]{S['MESSAGES'].get('DATE_PLAIN', 'Ημερομηνία')}:[/b] {insp_date}", markup=True))
            meta.add_widget(meta_left)

            # Actions: (removed JSON export/paste - redundant in this view)
            layout.add_widget(meta)

            # Scrollable content with collapsible sections
            scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
            # Ensure the content expands to the scrollview width so child rows
            # receive the full available horizontal space. Setting size_hint_x=1
            # makes the GridLayout follow the ScrollView width when laid out.
            # reduce outer spacing so rows are closer vertically
            content = GridLayout(cols=1, spacing=0, size_hint_y=None, size_hint_x=1, padding=4)
            content.bind(minimum_height=content.setter("height"))

            # Build sections using the same slices as the form builder
            rows = S["MESSAGES"].get("INSPECTION_ROWS", [])
            sections = [
                (S["MESSAGES"].get("INSPECTION_SECTION_2", ""), 0, 4),
                (S["MESSAGES"].get("INSPECTION_SECTION_3", ""), 4, 12),
                (S["MESSAGES"].get("INSPECTION_SECTION_3A", ""), 12, 13),
                (S["MESSAGES"].get("INSPECTION_SECTION_3B", ""), 13, 15),
                (S["MESSAGES"].get("INSPECTION_SECTION_4", ""), 15, 18),
                (S["MESSAGES"].get("INSPECTION_SECTION_5", ""), 18, 19),
                (S["MESSAGES"].get("INSPECTION_SECTION_6", ""), 19, 21),
            ]

            body = fields[8:]
            idx = 0

            def _make_section(title, items, default_expanded=False):
                # Create a collapsible section: header button and hidden body grid
                box = BoxLayout(orientation="vertical", size_hint_y=None)
                header = Button(text=title, size_hint_y=None, height=32)
                # Allow markup in header text (some titles may include markup tags)
                try:
                    header.font_size = '14sp'
                    header.markup = True
                except Exception:
                    pass

                # Use a vertical BoxLayout containing horizontal rows so we can
                # allocate more horizontal space to the value column and allow
                # long text to wrap instead of truncating.
                # Make the body grid expand horizontally to the available width
                # so each row's children (60/40) get the correct widths.
                # Use no spacing to avoid vertical gaps between rows.
                body_grid = BoxLayout(orientation='vertical', spacing=0, size_hint_y=None, size_hint_x=1)

                def _update_box_height():
                    try:
                        total = 0
                        for child in reversed(body_grid.children):
                            total += getattr(child, 'height', 0) or 0
                        body_grid.height = total
                    except Exception:
                        pass

                for lbl_text, val_text in items:
                    # Each row should take the full horizontal space of the body grid
                    # so its children can be allocated 60/40 correctly.
                    row = BoxLayout(orientation='horizontal', size_hint_y=None, size_hint_x=1, spacing=0, padding=(0,0))
                    # Left column: 60% of available width; Right column: 40%
                    lbl = Label(text=f"[b]{lbl_text}[/b]", markup=True, size_hint_x=0.6, size_hint_y=None, halign='left', valign='top')
                    val = Label(text=val_text or '-', size_hint_x=0.4, size_hint_y=None, halign='left', valign='top')

                    # Ensure the label's text box always matches the widget width
                    # so `halign='left'` takes effect. Bind to width changes so
                    # wrapping and alignment update reliably during layout passes.
                    def _bind_text_size(widget):
                        try:
                            widget.text_size = (widget.width, None)
                        except Exception:
                            pass

                    lbl.bind(width=lambda inst, w: _bind_text_size(inst))
                    val.bind(width=lambda inst, w: _bind_text_size(inst))

                    def _update_row_height(*_a):
                        try:
                            # force wrapping to current width
                            lbl.text_size = (lbl.width, None)
                            val.text_size = (val.width, None)
                            try:
                                lbl.texture_update()
                                val.texture_update()
                            except Exception:
                                pass
                            lh = lbl.texture_size[1] if hasattr(lbl, 'texture_size') else lbl.height
                            vh = val.texture_size[1] if hasattr(val, 'texture_size') else val.height
                            # smaller minimum height to tighten vertical spacing
                            h = max(14, int(max(lh, vh)))
                            lbl.height = h
                            val.height = h
                            row.height = h
                            _update_box_height()
                        except Exception:
                            pass

                    # Bind to the row width so updates run when overall space
                    # changes. Also bind child widths so alignment updates
                    # immediately. Schedule an initial update after layout so
                    # the measured widths are correct.
                    row.bind(width=lambda inst, w: _update_row_height())
                    lbl.bind(width=lambda inst, w: _update_row_height())
                    val.bind(width=lambda inst, w: _update_row_height())
                    Clock.schedule_once(lambda dt: _update_row_height(), 0)

                    row.add_widget(lbl)
                    row.add_widget(val)
                    body_grid.add_widget(row)

                # ensure box height matches children when expanded/collapsed
                box._expanded = False
                box.size_hint_y = None
                box.height = header.height

                def _update_height(*_a):
                    try:
                        if getattr(box, '_expanded', False):
                            box.height = header.height + (body_grid.height or 0)
                        else:
                            box.height = header.height
                    except Exception:
                        pass

                # attach toggle behavior
                def _toggle(_):
                    if getattr(box, "_expanded", False):
                        try:
                            box.remove_widget(body_grid)
                        except Exception:
                            pass
                        box._expanded = False
                    else:
                        box.add_widget(body_grid)
                        box._expanded = True
                    _update_height()

                # update box height when body changes
                body_grid.bind(height=lambda inst, h: _update_height())
                header.bind(on_press=_toggle)
                box.add_widget(header)

                # default expansion
                if default_expanded:
                    box.add_widget(body_grid)
                    box._expanded = True
                _update_height()
                return box

            for sec_title, start, end in sections:
                sec_items = []
                for i in range(start, min(end, len(rows))):
                    if idx >= len(body):
                        break
                    sec_items.append((rows[i], body[idx].get('value')))
                    idx += 1
                # expand all sections by default for easier scanning
                content.add_widget(_make_section(sec_title or f"Ενότητα {start}", sec_items, default_expanded=True))

            # Remaining (opinions / extras)
            if idx < len(body):
                rest_items = [(f.get('label'), f.get('value')) for f in body[idx:]]
                content.add_widget(_make_section(S["MESSAGES"].get("INSPECTION_SECTION_7", "Απόψεις"), rest_items, default_expanded=True))

            scroll.add_widget(content)
            layout.add_widget(scroll)

            # JSON export/paste buttons removed as they were redundant here

            # Close button
            close = Button(text=S.get("BUTTONS", {}).get("CLOSE", "Κλείσιμο"), size_hint_y=None, height=40)
            close.bind(on_press=lambda _btn: popup.dismiss())
            layout.add_widget(close)

            popup.content = layout
            popup.open()
        except Exception:
            from popups import show_message_popup

            show_message_popup(
                S["TITLES"].get("INSPECTION_DETAILS", "Λεπτομέρειες Επιθεώρησης"),
                f"{S['MESSAGES'].get('SUBSTATION_LABEL_PLAIN','Υποσταθμός')}: {sub_name}\n{S['MESSAGES'].get('DATE_PLAIN','Ημερομηνία')}: {insp_date}",
            )
    except Exception:
        return None


def show_substation_inspection_history_delegate(app, substation_id, substation_name, parent_display_popup=None):
    return getattr(app, "show_substation_inspection_history")(substation_id, substation_name, parent_display_popup)


def show_inspection_details_delegate(app, inspection_id):
    return getattr(app, "show_inspection_details")(inspection_id)
