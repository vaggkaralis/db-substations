"""Change-log preview and apply UI extracted from `DBrun.py`.

This module provides a single entrypoint `import_android_changes_from_file(app, file_path)`
that shows a preview of a JSONL change-log, offers an optional DB backup, and applies
the change-log using `apply_change_log_to_db` from `DBrun.py`.
"""

import json


def _normalize_change_log_text(raw_text):
    text = (raw_text or "").strip()
    if not text:
        return ""

    # Support files that contain a single JSON string wrapping the payload.
    try:
        decoded = json.loads(text)
        if isinstance(decoded, str):
            text = decoded.strip()
        elif isinstance(decoded, dict):
            return json.dumps(decoded, ensure_ascii=False)
    except Exception:
        pass

    # Support files manually edited into: "{...}" or
    # a leading quote on the first line and trailing quote on the last line.
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        inner = text[1:-1].strip()
        if inner.startswith("{") or inner.startswith("["):
            text = inner

    return text


def import_android_changes_from_file(app, file_path):
    try:
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label
        from kivy.uix.popup import Popup
        from kivy.uix.textinput import TextInput
    except Exception:
        Popup = BoxLayout = Label = Button = TextInput = object

    from popups import show_message_popup

    # Note: `apply_change_log_to_db` lives in `DBrun.py`; this module does not
    # call it directly so we avoid importing it here to prevent unused-name
    # lints in CI.

    # Try to produce a structured, human-readable preview of the change-log.
    # Parse JSONL and render maintenance rows as a form-like summary so users
    # can review what will be imported.
    preview_items = []
    try:
        # Try reading file with common encodings first
        text = None
        for enc in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                with open(file_path, "r", encoding=enc) as fh:
                    text = fh.read()
                break
            except Exception:
                text = None
        if text is None:
            # Binary fallback
            with open(file_path, "rb") as fh:
                b = fh.read(65536)
            text = b.decode("utf-8", errors="replace")

        text = _normalize_change_log_text(text)
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if len(lines) == 1:
            single_line = lines[0].strip()
            if single_line.startswith("{") and single_line.endswith("}"):
                lines = [single_line]
        for idx, ln in enumerate(lines[:50], start=1):
            try:
                obj = json.loads(ln)
            except Exception:
                preview_items.append(f"{idx}) (invalid JSON) {ln[:200]}")
                continue

            op = obj.get("operation")
            table = obj.get("table")
            data = obj.get("data") or {}

            header = f"{idx}) {op.upper() if op else 'OP'} {table or ''}"
            preview_items.append(header)

            if table == "maintenance" and isinstance(data, dict):
                # Render maintenance fields in a readable form
                for key in (
                    "id",
                    "substation_id",
                    "date_time",
                    "maintenance_type",
                    "overall_comments",
                    "user_name",
                ):
                    if key in data:
                        preview_items.append(f"   {key}: {data.get(key)}")
                # Render elements with indentation
                elems = data.get("elements") or []
                if elems:
                    preview_items.append("   elements:")
                    for e in elems:
                        eid = e.get("element_id") or e.get("id")
                        e_comment = e.get("element_comments") or e.get("comments")
                        preview_items.append(
                            f"     - element_id: {eid}  comments: {e_comment}"
                        )
                        # show any extra element fields (measurements)
                        extras = {
                            k: v
                            for k, v in e.items()
                            if k
                            not in ("element_id", "id", "element_comments", "comments")
                        }
                        if extras:
                            for ek, ev in extras.items():
                                preview_items.append(f"         {ek}: {ev}")
                preview_items.append("")
            else:
                # Generic pretty JSON for other tables
                pretty = json.dumps(data, ensure_ascii=False, indent=2)
                for pl in pretty.splitlines():
                    preview_items.append(f"   {pl}")
                preview_items.append("")
    except Exception:
        preview_items = ["(empty or unreadable)"]

    preview_text = (
        "\n".join(preview_items) if preview_items else "(empty or unreadable)"
    )

    # If there is exactly one maintenance entry, open the real maintenance
    # editor prefilled with that data. If multiple, present a chooser where
    # each maintenance can be opened in the editor for review/editing.
    from strings_proxy import STRINGS as S

    entries = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
        except Exception:
            # try normalizing quoted line
            try:
                decoded = json.loads(ln.strip('"'))
                obj = decoded
            except Exception:
                continue

        table = obj.get("table")
        # Accept both singular and plural forms produced by different Android versions
        if table not in ("maintenance", "inspection", "inspections"):
            continue

        data = obj.get("data") or {}
        sub_name = None
        try:
            c = app.conn.cursor()
            if data.get("substation_id") is not None:
                c.execute(
                    "SELECT name FROM substations WHERE id=?",
                    (data.get("substation_id"),),
                )
                r = c.fetchone()
                if r:
                    sub_name = r[0]
        except Exception:
            sub_name = None

        entries.append({"type": table, "data": data, "_substation_name": sub_name})

    def _open_maintenance_in_editor(data, resolved_sub_name=None):
        # Build prefill similar to email payload handler
        prefill = {}
        prefill["substation_id"] = data.get("substation_id")
        prefill["maintenance_type"] = data.get("maintenance_type")
        prefill["date_time"] = data.get("date_time")
        prefill["overall_comments"] = data.get("overall_comments")
        prefill["responsible_id"] = None
        elems = data.get("elements") or []
        element_ids = [
            e.get("element_id") or e.get("id")
            for e in elems
            if e.get("element_id") or e.get("id")
        ]
        prefill["element_ids"] = element_ids
        prefill["incomplete_elements"] = set(element_ids)
        prefill["attachment_paths"] = []
        prefill["_diag_origin"] = "android_change_log"
        # Resolve substation name if possible
        sub_name = resolved_sub_name
        if sub_name is None:
            try:
                c = app.conn.cursor()
                if prefill.get("substation_id") is not None:
                    c.execute(
                        "SELECT name FROM substations WHERE id=?",
                        (prefill["substation_id"],),
                    )
                    r = c.fetchone()
                    if r:
                        sub_name = r[0]
            except Exception:
                sub_name = None

        # Open the desktop maintenance editor with prefill
        try:
            app.show_maintenance_menu(
                preselected_substation_name=sub_name,
                parent_popup=None,
                maintenance_id=None,
                after_save_callback=None,
                prefill_data=prefill,
            )
        except Exception:
            try:
                show_message_popup(
                    S.get("TITLES", {}).get("ERROR", "Σφάλμα"),
                    "Αδύνατο άνοιγμα φόρμας συντήρησης",
                )
            except Exception:
                pass

    if len(entries) == 0:
        # No maintenance entries detected — fall back to textual preview
        preview_popup = Popup(title="Preview change log", size_hint=(0.9, 0.9))
        layout = BoxLayout(orientation="vertical", spacing=10, padding=10)
        layout.add_widget(Label(text=f"File: {file_path}", size_hint_y=0.08))
        preview_area = TextInput(text=preview_text, readonly=True)
        layout.add_widget(preview_area)
        btn = Button(
            text=S.get("BUTTONS", {}).get("CLOSE", "Κλείσιμο"),
            size_hint_y=None,
            height=48,
        )
        btn.bind(on_press=preview_popup.dismiss)
        layout.add_widget(btn)
        preview_popup.content = layout
        preview_popup.open()
        return

    if len(entries) == 1:
        entry = entries[0]
        if entry.get("type") == "maintenance":
            _open_maintenance_in_editor(
                entry.get("data"), entry.get("_substation_name")
            )
        else:
            # Open inspection editor (prefill support requires DBrun.show_inspection_entry_popup to accept prefill_data)
            prefill = {
                "substation_id": entry.get("data", {}).get("substation_id"),
                "form_number": entry.get("data", {}).get("form_number"),
                "date_time": entry.get("data", {}).get("date_time"),
                "region": entry.get("data", {}).get("region"),
                "fields": entry.get("data", {}).get("fields"),
            }
            if entry.get("_substation_name"):
                prefill["substation_name"] = entry.get("_substation_name")
            try:
                app.show_inspection_entry_popup(
                    None,
                    preselected_substation_name=entry.get("_substation_name"),
                    parent_popup=None,
                    prefill_data=prefill,
                )
            except Exception:
                try:
                    show_message_popup(
                        S.get("TITLES", {}).get("ERROR", "Σφάλμα"),
                        "Αδύνατο άνοιγμα φόρμας ελέγχου",
                    )
                except Exception:
                    pass
        return

    # Multiple entries (maintenance and/or inspection): present chooser
    chooser = Popup(
        title=S.get("MESSAGES", {}).get("MAINT_CHOOSER", "Επιλέξτε συντήρηση"),
        size_hint=(0.9, 0.9),
    )
    layout = BoxLayout(orientation="vertical", spacing=8, padding=8)
    layout.add_widget(Label(text=f"File: {file_path}", size_hint_y=None, height=28))
    for idx, entry in enumerate(entries, start=1):
        data = entry.get("data") or {}
        sub_name = entry.get("_substation_name")
        sub_display = sub_name if sub_name else data.get("substation_id")
        typ = entry.get("type")
        if typ == "maintenance":
            type_label = data.get("maintenance_type") or "maintenance"
            time_val = data.get("date_time")
        else:
            type_label = "inspection"
            time_val = data.get("date") or data.get("date_time")

        line = f"{idx}) {type_label} @ substation={sub_display} time={time_val}"
        row = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=42, spacing=8
        )
        row.add_widget(Label(text=line))
        btn = Button(
            text=S.get("BUTTONS", {}).get("OPEN", "Άνοιγμα"),
            size_hint_x=None,
            width=120,
        )

        def _make_open(ent):
            def _open_and_close(_btn):
                if ent.get("type") == "maintenance":
                    _open_maintenance_in_editor(
                        ent.get("data"), ent.get("_substation_name")
                    )
                else:
                    prefill = {
                        "substation_id": ent.get("data", {}).get("substation_id"),
                        "form_number": ent.get("data", {}).get("form_number"),
                        "date_time": ent.get("data", {}).get("date_time"),
                        "region": ent.get("data", {}).get("region"),
                        "fields": ent.get("data", {}).get("fields"),
                    }
                    if ent.get("_substation_name"):
                        prefill["substation_name"] = ent.get("_substation_name")
                    try:
                        app.show_inspection_entry_popup(
                            None,
                            preselected_substation_name=ent.get("_substation_name"),
                            parent_popup=None,
                            prefill_data=prefill,
                        )
                    except Exception:
                        try:
                            show_message_popup(
                                S.get("TITLES", {}).get("ERROR", "Σφάλμα"),
                                "Αδύνατο άνοιγμα φόρμας ελέγχου",
                            )
                        except Exception:
                            pass
                try:
                    chooser.dismiss()
                except Exception:
                    pass

            return _open_and_close

        btn.bind(on_press=_make_open(entry))
        row.add_widget(btn)
        layout.add_widget(row)

    def _open_for_index(i, dismiss_popup=None):
        if dismiss_popup:
            try:
                dismiss_popup.dismiss()
            except Exception:
                pass

        if i < 0 or i >= len(entries):
            return

        entry = entries[i]

        def _on_next(popup=None):
            if popup:
                try:
                    popup.dismiss()
                except Exception:
                    pass
            _open_for_index(i + 1)

        def _on_prev(popup=None):
            if popup:
                try:
                    popup.dismiss()
                except Exception:
                    pass
            _open_for_index(i - 1)

        prefill = {}
        data = entry.get("data") or {}
        if entry.get("type") == "maintenance":
            prefill["substation_id"] = data.get("substation_id")
            prefill["maintenance_type"] = data.get("maintenance_type")
            prefill["date_time"] = data.get("date_time")
            prefill["overall_comments"] = data.get("overall_comments")
            prefill["element_ids"] = [
                e.get("element_id") or e.get("id")
                for e in (data.get("elements") or [])
                if e.get("element_id") or e.get("id")
            ]
            prefill["attachment_paths"] = []
        else:
            # inspection prefill
            prefill["substation_id"] = data.get("substation_id")
            prefill["form_number"] = data.get("form_number")
            prefill["date_time"] = data.get("date_time") or data.get("date")
            prefill["region"] = data.get("region")
            prefill["fields"] = data.get("fields")

        prefill["_diag_origin"] = "android_change_log"
        prefill["_nav"] = {
            "index": i,
            "total": len(entries),
            "on_next": _on_next if i + 1 < len(entries) else None,
            "on_prev": _on_prev if i - 1 >= 0 else None,
        }

        # Pass resolved substation name when available
        if entry.get("_substation_name"):
            prefill["substation_name"] = entry.get("_substation_name")

        try:
            if entry.get("type") == "maintenance":
                app.show_maintenance_menu(
                    preselected_substation_name=entry.get("_substation_name"),
                    parent_popup=None,
                    maintenance_id=None,
                    after_save_callback=None,
                    prefill_data=prefill,
                )
            else:
                app.show_inspection_entry_popup(
                    None,
                    preselected_substation_name=entry.get("_substation_name"),
                    parent_popup=None,
                    prefill_data=prefill,
                )
        except Exception:
            try:
                show_message_popup(
                    S.get("TITLES", {}).get("ERROR", "Σφάλμα"), "Αδύνατο άνοιγμα φόρμας"
                )
            except Exception:
                pass

    open_all_btn = Button(
        text=S.get("BUTTONS", {}).get("OPEN_ALL", "Άνοιγμα όλων"),
        size_hint_y=None,
        height=48,
    )

    def _on_open_all(_inst=None):
        _open_for_index(0, dismiss_popup=chooser)

    open_all_btn.bind(on_press=_on_open_all)
    layout.add_widget(open_all_btn)

    close_btn = Button(
        text=S.get("BUTTONS", {}).get("CLOSE", "Κλείσιμο"), size_hint_y=None, height=48
    )
    close_btn.bind(on_press=chooser.dismiss)
    layout.add_widget(close_btn)
    chooser.content = layout
    chooser.open()
