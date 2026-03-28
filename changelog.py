"""Change-log preview and apply UI extracted from `DBrun.py`.

This module provides a single entrypoint `import_android_changes_from_file(app, file_path)`
that shows a preview of a JSONL change-log, offers an optional DB backup, and applies
the change-log using `apply_change_log_to_db` from `DBrun.py`.
"""


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

    # Reuse apply_change_log_to_db from DBrun (kept at module level there)
    try:
        from DBrun import apply_change_log_to_db
    except Exception:
        # If import fails, continue but operations will raise later
        apply_change_log_to_db = None

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

        lines = [ln for ln in text.splitlines() if ln.strip()]
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
                for key in ("id", "substation_id", "date_time", "maintenance_type", "overall_comments", "user_name"):
                    if key in data:
                        preview_items.append(f"   {key}: {data.get(key)}")
                # Render elements with indentation
                elems = data.get("elements") or []
                if elems:
                    preview_items.append("   elements:")
                    for e in elems:
                        eid = e.get("element_id") or e.get("id")
                        e_comment = e.get("element_comments") or e.get("comments")
                        preview_items.append(f"     - element_id: {eid}  comments: {e_comment}")
                        # show any extra element fields (measurements)
                        extras = {k: v for k, v in e.items() if k not in ("element_id", "id", "element_comments", "comments")}
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

    preview_text = "\n".join(preview_items) if preview_items else "(empty or unreadable)"

    preview_popup = Popup(title="Preview change log", size_hint=(0.9, 0.9))
    layout = BoxLayout(orientation="vertical", spacing=10, padding=10)
    layout.add_widget(Label(text=f"File: {file_path}", size_hint_y=0.08))
    preview_area = TextInput(text=preview_text, readonly=True)
    layout.add_widget(preview_area)

    btns = BoxLayout(size_hint_y=0.12, spacing=10)

    def _backup_and_apply(_):
        preview_popup.dismiss()
        try:
            # determine DB file path from connection
            db_file = None
            try:
                r = app.conn.execute("PRAGMA database_list").fetchall()
                for row in r:
                    if row[1] == "main":
                        db_file = row[2]
                        break
            except Exception:
                db_file = None
            if not db_file:
                try:
                    from settings import DB_PATH as _dbpath

                    db_file = _dbpath
                except Exception:
                    db_file = "substations.db"
            import shutil
            import time

            backup_path = f"{db_file}.backup.{int(time.time())}.bak"
            shutil.copy2(db_file, backup_path)
            if apply_change_log_to_db:
                apply_change_log_to_db(app.conn, file_path)
            show_message_popup(
                "Εισαγωγή αλλαγών από Android",
                f"Επιτυχής εισαγωγή. Backup: {backup_path}",
            )
        except Exception as e:
            show_message_popup(S["TITLES"]["ERROR"], f"Σφάλμα κατά την εισαγωγή: {e}")

    def _apply_only(_):
        preview_popup.dismiss()
        try:
            if apply_change_log_to_db:
                apply_change_log_to_db(app.conn, file_path)
            show_message_popup("Εισαγωγή αλλαγών από Android", "Επιτυχής εισαγωγή.")
        except Exception as e:
            show_message_popup(S["TITLES"]["ERROR"], f"Σφάλμα κατά την εισαγωγή: {e}")

    from strings_proxy import STRINGS as S

    apply_btn = Button(text=S["BUTTONS"]["APPLY"])
    apply_btn.bind(on_press=_apply_only)
    backup_btn = Button(text=S["BUTTONS"]["BACKUP_APPLY"])
    backup_btn.bind(on_press=_backup_and_apply)
    cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
    cancel_btn.bind(on_press=preview_popup.dismiss)

    btns.add_widget(backup_btn)
    btns.add_widget(apply_btn)
    btns.add_widget(cancel_btn)

    layout.add_widget(btns)
    preview_popup.content = layout
    preview_popup.open()
