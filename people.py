from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput

from popups import ask_open_file, show_message_popup
from strings_proxy import STRINGS as S
from validation import PEOPLE_ROLES, canonical_role, group_people_by_category
from ui.shared import IconOnlyButton


class PeopleManager:
    def __init__(self, app):
        self.app = app

    def show_people_management(self, instance=None):
        popup = Popup(title=S["MESSAGES"].get("PEOPLE_BUTTON", "Διαχείριση Προσωπικού"), size_hint=(0.7, 0.8))
        main_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        form_layout = GridLayout(cols=2, size_hint_y=None, height=140, spacing=5)
        form_layout.add_widget(Label(text=S["MESSAGES"].get("SURNAME_LABEL", "Επώνυμο:"), size_hint_x=0.3))
        surname_input = TextInput(multiline=False, size_hint_x=0.7)
        form_layout.add_widget(surname_input)

        form_layout.add_widget(Label(text=S["MESSAGES"].get("NAME_LABEL", "Όνομα:"), size_hint_x=0.3))
        given_input = TextInput(multiline=False, size_hint_x=0.7)
        form_layout.add_widget(given_input)

        form_layout.add_widget(Label(text=S["MESSAGES"].get("ROLE_LABEL", "Ρόλος:"), size_hint_x=0.3))
        role_spinner = Spinner(
            text=PEOPLE_ROLES[0] if PEOPLE_ROLES else "",
            values=PEOPLE_ROLES,
            size_hint_x=0.7,
        )
        form_layout.add_widget(role_spinner)

        form_layout.add_widget(Label(text=S["MESSAGES"].get("EMAIL_LABEL", "Email:"), size_hint_x=0.3))
        email_input = TextInput(multiline=False, size_hint_x=0.7)
        form_layout.add_widget(email_input)

        main_layout.add_widget(form_layout)

        receiver_layout = BoxLayout(size_hint_y=None, height=30, spacing=5)
        receiver_checkbox = CheckBox(size_hint_x=0.1, color=self.app.theme.get("primary", (0.05, 0.18, 0.36, 1)))
        receiver_layout.add_widget(receiver_checkbox)
        receiver_layout.add_widget(Label(text=S["MESSAGES"].get("EMAIL_RECIPIENT_LABEL", "Παραλήπτης email αναφοράς"), size_hint_x=0.9))
        main_layout.add_widget(receiver_layout)

        active_layout = BoxLayout(size_hint_y=None, height=30, spacing=5)
        active_checkbox = CheckBox(size_hint_x=0.1, active=True, color=self.app.theme.get("primary", (0.05, 0.18, 0.36, 1)))
        active_layout.add_widget(active_checkbox)
        active_layout.add_widget(Label(text=S["MESSAGES"].get("ACTIVE_LABEL", "Ενεργός"), size_hint_x=0.9))
        main_layout.add_widget(active_layout)

        add_btn = Button(text=S["BUTTONS"]["ADD"], size_hint_y=None, height=40)

        list_scroll = ScrollView(bar_width=10, scroll_type=["bars", "content"])
        list_layout = GridLayout(cols=1, spacing=5, size_hint_y=None, padding=5)
        list_layout.bind(minimum_height=list_layout.setter("height"))

        def refresh_list():
            list_layout.clear_widgets()
            c = self.app.conn.cursor()
            c.execute(
                "SELECT id, name, role, email, report_receiver, active FROM people ORDER BY active DESC, CASE\n                    WHEN role LIKE '%Τομεαρ%' COLLATE NOCASE OR role LIKE '%Τομεάρχ%' COLLATE NOCASE THEN 0\n                    WHEN role LIKE '%Υποτο%' COLLATE NOCASE THEN 1\n                    WHEN role LIKE '%Ειδικ%' COLLATE NOCASE OR role LIKE '%Ειδικό Στέλεχος%' COLLATE NOCASE THEN 2\n                    WHEN role LIKE '%Μηχανικ%' COLLATE NOCASE THEN 3\n                    WHEN role LIKE '%Εργοδηγ%' COLLATE NOCASE THEN 4\n                    WHEN role LIKE '%Αρχιτεχν%' COLLATE NOCASE THEN 5\n                    WHEN role LIKE '%Τεχν%' COLLATE NOCASE THEN 6\n                    WHEN role LIKE '%Χειριστ%' COLLATE NOCASE THEN 7\n                    WHEN role LIKE '%Υποστ%' COLLATE NOCASE THEN 8\n                    ELSE 99 END, COALESCE(surname, name) COLLATE NOCASE"
            )
            rows = c.fetchall()
            grouped = group_people_by_category(rows)
            for cat, items in grouped.items():
                if not items:
                    continue
                header = Label(text=f"[b]{cat} ({len(items)})[/b]", markup=True, color=self.app.theme.get("primary", (0.05, 0.18, 0.36, 1)), size_hint_y=None, height=30)
                list_layout.add_widget(header)

                def _role_priority(role):
                    try:
                        canon = canonical_role(role)
                        if canon and canon in PEOPLE_ROLES:
                            return PEOPLE_ROLES.index(canon)
                    except Exception:
                        pass
                    return 99

                items_sorted = sorted(items, key=lambda r: (_role_priority(r[2] if len(r) > 2 else None), (r[1] or "").lower()))
                for person_id, name, role, email, report_receiver, active in items_sorted:
                    row = BoxLayout(size_hint_y=None, height=35, spacing=5)
                    status = S["MESSAGES"].get("ACTIVE_LABEL", "Ενεργός") if active else S["MESSAGES"].get("INACTIVE_LABEL", "Ανενεργός")
                    email_text = email if email else S["MESSAGES"].get("DASH", "-")
                    receiver_text = S["BUTTONS"].get("YES", "Ναι") if report_receiver else S["BUTTONS"].get("NO", "Όχι")
                    row.add_widget(Label(text=f"{name} ({role}) | {email_text} | Παραλήπτης: {receiver_text} | {status}", size_hint_x=0.8))

                    edit_btn = IconOnlyButton(icon_type="edit", icon_color=(0.2, 0.6, 1, 1), size=(35, 35))
                    edit_btn.size_hint_x = 0.1
                    delete_btn = IconOnlyButton(icon_type="delete", icon_color=(1, 0.0, 0.0, 1), size=(35, 35))
                    delete_btn.size_hint_x = 0.1

                    def make_delete(pid, pname):
                        return lambda x: self._confirm_delete_person(pid, pname, refresh_list)

                    def make_edit(pid):
                        return lambda x: self._show_edit_person_popup(pid, refresh_list)

                    row.add_widget(edit_btn)
                    row.add_widget(delete_btn)
                    edit_btn.bind(on_press=make_edit(person_id))
                    delete_btn.bind(on_press=make_delete(person_id, name))
                    list_layout.add_widget(row)

        def add_person(instance):
            surname = surname_input.text.strip()
            given = given_input.text.strip()
            role = role_spinner.text.strip()
            email = email_input.text.strip()
            if not surname or not role:
                show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["SURNAME_ROLE_REQUIRED"])
                return
            composite = f"{surname} {given}".strip()
            c = self.app.conn.cursor()
            c.execute(
                "INSERT INTO people (name, given_name, surname, role, email, report_receiver, active) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    composite,
                    given,
                    surname,
                    role,
                    email,
                    1 if receiver_checkbox.active else 0,
                    1 if active_checkbox.active else 0,
                ),
            )
            self.app.conn.commit()
            surname_input.text = ""
            given_input.text = ""
            role_spinner.text = PEOPLE_ROLES[0] if PEOPLE_ROLES else ""
            active_checkbox.active = True
            email_input.text = ""
            receiver_checkbox.active = False
            refresh_list()

        add_btn.bind(on_press=add_person)
        main_layout.add_widget(add_btn)

        def _show_people_io_popup(_instance=None):
            try:
                from excel_io import (export_people, export_people_template,
                                      import_people)
            except Exception:
                show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"].get("EXCEL_HELPERS_MISSING", "Οι βοηθητικές συναρτήσεις Excel δεν είναι διαθέσιμες."))
                return

            io_popup = Popup(title=S["MESSAGES"].get("IMPORT_EXPORT_PEOPLE", "Εισαγωγή/Εξαγωγή Προσωπικού"), size_hint=(0.5, 0.4))
            io_layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

            def _import_people(_btn=None):
                try:
                    fp = ask_open_file(title="Επιλέξτε αρχείο εισαγωγής (Excel)", filetypes=(("Excel files", "*.xlsx"),))
                except Exception:
                    fp = None
                if not fp:
                    return
                try:
                    import_people(self.app.conn, fp)
                    show_message_popup(S["TITLES"]["SUCCESS"], "Εισαγωγή προσωπικού ολοκληρώθηκε.")
                    refresh_list()
                except Exception as exc:
                    show_message_popup(S["TITLES"]["ERROR"], f"Αποτυχία εισαγωγής προσωπικού:\n{str(exc)}")

            def _export_people(_btn=None):
                try:
                    export_people(self.app.conn)
                except Exception as exc:
                    show_message_popup(S["TITLES"]["ERROR"], f"Αποτυχία εξαγωγής προσωπικού:\n{str(exc)}")

            def _export_template(_btn=None):
                try:
                    export_people_template()
                except Exception as exc:
                    show_message_popup(S["TITLES"]["ERROR"], f"Αποτυχία δημιουργίας προτύπου:\n{str(exc)}")

            imp_btn = Button(text=S["MESSAGES"].get("IMPORT_PEOPLE_BTN", "Εισαγωγή Προσωπικού (Excel)"))
            imp_btn.bind(on_press=_import_people)
            io_layout.add_widget(imp_btn)

            exp_btn = Button(text=S["MESSAGES"].get("EXPORT_PEOPLE_BTN", "Εξαγωγή Προσωπικού (Excel)"))
            exp_btn.bind(on_press=_export_people)
            io_layout.add_widget(exp_btn)

            tpl_btn = Button(text=S["MESSAGES"].get("EXPORT_PEOPLE_TEMPLATE_BTN", "Δημιουργία Template Προσωπικού"))
            tpl_btn.bind(on_press=_export_template)
            io_layout.add_widget(tpl_btn)

            close_btn = Button(text=S["BUTTONS"]["CLOSE"], size_hint_y=None, height=40)
            close_btn.bind(on_press=io_popup.dismiss)
            io_layout.add_widget(close_btn)

            io_popup.content = io_layout
            io_popup.open()

        people_io_btn = Button(text=S["MESSAGES"].get("IMPORT_EXPORT_PEOPLE", "Εισαγωγή/Εξαγωγή Προσωπικού"), size_hint_y=None, height=40)
        people_io_btn.bind(on_press=_show_people_io_popup)
        main_layout.add_widget(people_io_btn)

        refresh_list()
        list_scroll.add_widget(list_layout)
        main_layout.add_widget(list_scroll)

        close_btn = Button(text=S["BUTTONS"]["CLOSE"], size_hint_y=None, height=40)
        close_btn.bind(on_press=popup.dismiss)
        main_layout.add_widget(close_btn)

        popup.content = main_layout
        popup.open()

    def _toggle_person_active(self, person_id, active, refresh_cb=None):
        c = self.app.conn.cursor()
        c.execute("UPDATE people SET active=? WHERE id=?", (active, person_id))
        self.app.conn.commit()
        if refresh_cb:
            refresh_cb()

    def _toggle_person_receiver(self, person_id, report_receiver, refresh_cb=None):
        c = self.app.conn.cursor()
        c.execute("UPDATE people SET report_receiver=? WHERE id=?", (report_receiver, person_id))
        self.app.conn.commit()
        if refresh_cb:
            refresh_cb()

    def _confirm_delete_person(self, person_id, person_name, refresh_cb=None):
        c = self.app.conn.cursor()
        c.execute("SELECT COUNT(*) FROM maintenance_people WHERE person_id=?", (person_id,))
        usage_count = c.fetchone()[0]
        if usage_count > 0:
            show_message_popup(S["TITLES"]["INFO"], S["MESSAGES"]["PERSON_IN_USE"])
            return

        from reports import show_confirm

        def confirm_delete():
            c.execute("DELETE FROM people WHERE id=?", (person_id,))
            self.app.conn.commit()
            if refresh_cb:
                refresh_cb()

        show_confirm(
            S["MESSAGES"].get("CONFIRM_DELETE_TITLE", "Επιβεβαίωση Διαγραφής"),
            f'{S["MESSAGES"].get("CONFIRM_DELETE_PERSON", ("Είστε σίγουροι ότι θέλετε να διαγράψετε\nτο άτομο \"{person_name}\";"))}',
            yes_callback=confirm_delete,
            yes_color=(1, 0, 0, 1),
        )

    def _migrate_people_name_columns(self):
        c = self.app.conn.cursor()
        cols = [r[1] for r in c.execute("PRAGMA table_info(people)")]
        need_commit = False
        if "given_name" not in cols:
            c.execute("ALTER TABLE people ADD COLUMN given_name TEXT")
            need_commit = True
        if "surname" not in cols:
            c.execute("ALTER TABLE people ADD COLUMN surname TEXT")
            need_commit = True
        if need_commit:
            self.app.conn.commit()

        c.execute("SELECT id, name, given_name, surname FROM people")
        rows = c.fetchall()
        for pid, fullname, gname, sname in rows:
            if (gname and gname.strip()) or (sname and sname.strip()):
                continue
            if not fullname:
                continue
            parts = fullname.strip().rsplit(" ", 1)
            if len(parts) == 1:
                given = ""
                surname = parts[0]
            else:
                given, surname = parts[0], parts[1]
            composite = f"{surname} {given}".strip()
            c.execute("UPDATE people SET given_name=?, surname=?, name=? WHERE id=?", (given, surname, composite, pid))
        self.app.conn.commit()

    def _show_edit_person_popup(self, person_id, refresh_cb=None):
        c = self.app.conn.cursor()
        c.execute("SELECT name, given_name, surname, role, email, report_receiver, active FROM people WHERE id=?", (person_id,))
        row = c.fetchone()
        if not row:
            show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["PERSON_NOT_FOUND"])
            return

        name, given, surname, role, email, report_receiver, active = row

        popup = Popup(title="Επεξεργασία Προσώπου", size_hint=(0.6, 0.5))
        layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

        form = GridLayout(cols=2, size_hint_y=None, height=160, spacing=5)
        form.add_widget(Label(text="Επώνυμο:", size_hint_x=0.3))
        surname_input = TextInput(text=surname or "", multiline=False, size_hint_x=0.7)
        form.add_widget(surname_input)

        form.add_widget(Label(text="Όνομα:", size_hint_x=0.3))
        name_input = TextInput(text=given or "", multiline=False, size_hint_x=0.7)
        form.add_widget(name_input)

        form.add_widget(Label(text="Ρόλος:", size_hint_x=0.3))
        role_values = list(PEOPLE_ROLES)
        if role and role not in role_values:
            role_values.insert(0, role)
        role_spinner = Spinner(text=role or (role_values[0] if role_values else ""), values=role_values, size_hint_x=0.7)
        form.add_widget(role_spinner)

        form.add_widget(Label(text="Email:", size_hint_x=0.3))
        email_input = TextInput(text=email or "", multiline=False, size_hint_x=0.7)
        form.add_widget(email_input)

        layout.add_widget(form)

        receiver_layout = BoxLayout(size_hint_y=None, height=30, spacing=5)
        receiver_checkbox = CheckBox(size_hint_x=0.1, active=bool(report_receiver), color=self.app.theme.get("primary", (0.05, 0.18, 0.36, 1)))
        receiver_layout.add_widget(receiver_checkbox)
        receiver_layout.add_widget(Label(text="Παραλήπτης email αναφοράς", size_hint_x=0.9))
        layout.add_widget(receiver_layout)

        active_layout = BoxLayout(size_hint_y=None, height=30, spacing=5)
        active_checkbox = CheckBox(size_hint_x=0.1, active=bool(active), color=self.app.theme.get("primary", (0.05, 0.18, 0.36, 1)))
        active_layout.add_widget(active_checkbox)
        active_layout.add_widget(Label(text="Ενεργός", size_hint_x=0.9))
        layout.add_widget(active_layout)

        buttons_layout = BoxLayout(size_hint_y=None, height=40, spacing=10)

        def save_changes():
            new_surname = surname_input.text.strip()
            new_given = name_input.text.strip()
            new_role = role_spinner.text.strip()
            new_email = email_input.text.strip()
            if not new_surname or not new_role:
                show_message_popup("Σφάλμα", "Το επώνυμο και ο ρόλος είναι υποχρεωτικά!")
                return
            composite = f"{new_surname} {new_given}".strip()
            c.execute(
                "UPDATE people SET name=?, given_name=?, surname=?, role=?, email=?, report_receiver=?, active=? WHERE id=?",
                (
                    composite,
                    new_given,
                    new_surname,
                    new_role,
                    new_email,
                    1 if receiver_checkbox.active else 0,
                    1 if active_checkbox.active else 0,
                    person_id,
                ),
            )
            self.app.conn.commit()
            popup.dismiss()
            if refresh_cb:
                refresh_cb()

        save_btn = Button(text=S["BUTTONS"]["SAVE"])
        save_btn.bind(on_press=lambda x: save_changes())
        cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
        cancel_btn.bind(on_press=popup.dismiss)

        buttons_layout.add_widget(save_btn)
        buttons_layout.add_widget(cancel_btn)
        layout.add_widget(buttons_layout)

        popup.content = layout
        popup.open()
