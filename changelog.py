"""Change-log preview and apply UI extracted from `DBrun.py`.

This module provides a single entrypoint `import_android_changes_from_file(app, file_path)`
that shows a preview of a JSONL change-log, offers an optional DB backup, and applies
the change-log using `apply_change_log_to_db` from `DBrun.py`.
"""

import os

def import_android_changes_from_file(app, file_path):
    try:
        from kivy.uix.popup import Popup
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.label import Label
        from kivy.uix.button import Button
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

    # Preview first few lines
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            lines = [next(fh).strip() for _ in range(5)]
    except StopIteration:
        lines = []
    except Exception:
        lines = []

    preview_text = "\n".join(lines) or "(empty or unreadable)"

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
                "Εισαγωγή αλλαγών από Android", f"Επιτυχής εισαγωγή. Backup: {backup_path}"
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

    from strings import STRINGS as S

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

