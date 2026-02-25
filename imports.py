import os

from strings import STRINGS as S


def _open_file_chooser_and_import(app, parent_popup, import_callback, title=S["TITLES"]["IMPORT_MENU"], filetypes=None, chooser_filters=None):
    # Prefer native Windows file chooser when available; fall back to Kivy chooser.
    from popups import show_message_popup

    if os.name == "nt":
        try:
            import tkinter as _tk
            from tkinter import filedialog as _filedialog

            root = _tk.Tk()
            root.withdraw()
            ft = list(filetypes) if filetypes else [
                ("Excel files", "*.xlsx *.xls"),
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ]
            file_path = _filedialog.askopenfilename(title=title, filetypes=ft)
            try:
                root.destroy()
            except Exception:
                pass

            # If user cancelled the native dialog, silently return (no message).
            if not file_path:
                return
            if not os.path.exists(file_path):
                show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["FILE_NOT_FOUND"])
                return

            try:
                import_callback(file_path)
            except Exception as e:
                show_message_popup(S["TITLES"]["ERROR"], f"{S['MESSAGES']['IMPORT_FAILED']}\n{str(e)}")
                return

            if parent_popup:
                try:
                    parent_popup.dismiss()
                except Exception:
                    pass

            return
        except Exception:
            # If tkinter isn't available or fails, fall back to Kivy chooser below.
            pass

    # Fallback: build a Kivy popup with FileChooser
    try:
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.filechooser import FileChooserListView
        from kivy.uix.label import Label
        from kivy.uix.popup import Popup
        from kivy.uix.textinput import TextInput
    except Exception:
        Popup = BoxLayout = Label = Button = TextInput = FileChooserListView = object

    popup = Popup(title=title, size_hint=(0.9, 0.9))
    layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    # Path input
    path_label = Label(text=S.get("MESSAGES", {}).get("FILE_PATH_LABEL", "Διαδρομή αρχείου:"), size_hint_y=0.1)
    layout.add_widget(path_label)

    path_input = TextInput(hint_text=S.get("MESSAGES", {}).get("FILE_PATH_HINT", "Διαδρομή αρχείου"), size_hint_y=0.15, multiline=False)
    layout.add_widget(path_input)

    # File chooser with default path
    layout.add_widget(Label(text="Ή επιλέξτε από τη λίστα:", size_hint_y=0.1))
    chooser = FileChooserListView(filters=(chooser_filters or ["*.xlsx", "*.csv"]), path=os.path.dirname(__file__))
    layout.add_widget(chooser)

    # Buttons
    buttons_layout = BoxLayout(size_hint_y=0.1, spacing=10)

    def import_file():
        file_path = (
            path_input.text.strip()
            if path_input.text.strip()
            else (chooser.selection[0] if getattr(chooser, "selection", None) else None)
        )

        try:
            if isinstance(file_path, str):
                file_path = file_path.strip().strip('"\'')
        except Exception:
            pass

        if not file_path:
            show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["ENTER_PATH"])
            return
        if not os.path.exists(file_path):
            show_message_popup(S["TITLES"]["ERROR"], S["MESSAGES"]["FILE_NOT_FOUND"])
            return

        try:
            import_callback(file_path)
        except Exception as e:
            show_message_popup(S["TITLES"]["ERROR"], f"{S['MESSAGES']['IMPORT_FAILED']}\n{str(e)}")
            return
        popup.dismiss()
        if parent_popup:
            try:
                parent_popup.dismiss()
            except Exception:
                pass

    import_btn = Button(text=S["BUTTONS"]["IMPORT"])
    import_btn.bind(on_press=lambda x: import_file())
    buttons_layout.add_widget(import_btn)
    cancel_btn = Button(text=S["BUTTONS"]["CANCEL"])
    cancel_btn.bind(on_press=popup.dismiss)
    buttons_layout.add_widget(cancel_btn)

    layout.add_widget(buttons_layout)
    popup.content = layout
    popup.open()


def show_import_menu(app, instance=None):
    try:
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.button import Button
        from kivy.uix.label import Label
        from kivy.uix.popup import Popup
    except Exception:
        Popup = BoxLayout = Label = Button = object

    menu_popup = Popup(title="Εισαγωγή από αρχείο", size_hint=(0.6, 0.55))
    layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    try:
        app._add_logo_to_layout(layout, height=70)
    except Exception:
        pass

    layout.add_widget(Label(text="Επιλέξτε τι θέλετε να εισάγετε:", size_hint_y=0.2))

    import_elements_btn = Button(text="Εισαγωγή Στοιχείων από Αρχείο", size_hint_y=0.2)
    import_elements_btn.bind(on_press=lambda x: _show_import_elements_from_menu(app, menu_popup))
    layout.add_widget(import_elements_btn)

    import_android_btn = Button(text="Εισαγωγή αλλαγών από Android", size_hint_y=0.2)
    import_android_btn.bind(on_press=lambda x: _show_import_android_changes_from_menu(app, menu_popup))
    layout.add_widget(import_android_btn)

    try:
        from reports import export_full_db_ui

        export_db_btn = Button(text="Εξαγωγή Βάσης (Excel)", size_hint_y=0.2)
        export_db_btn.bind(on_press=lambda x: export_full_db_ui(app, menu_popup))
        layout.add_widget(export_db_btn)
    except Exception:
        pass

    layout.add_widget(Label(text="Ή δημιουργήστε πρότυπο εισαγωγής:", size_hint_y=0.15))

    template_elements_btn = Button(text="Δημιουργία Template Εισαγωγής", size_hint_y=0.2)
    template_elements_btn.bind(on_press=app.create_elements_template)
    layout.add_widget(template_elements_btn)

    cancel_btn = Button(text=S["BUTTONS"]["CANCEL"], size_hint_y=0.15)
    cancel_btn.bind(on_press=menu_popup.dismiss)
    layout.add_widget(cancel_btn)

    menu_popup.content = layout
    menu_popup.open()


def _show_import_substations_from_menu(app, menu_popup):
    show_import_substations_dialog(app, menu_popup)


def _show_import_elements_from_menu(app, menu_popup):
    show_import_elements_dialog(app, menu_popup)


def _show_import_android_changes_from_menu(app, menu_popup):
    show_import_android_changes_dialog(app, menu_popup)


def show_import_substations_dialog(app, instance_or_parent_popup=None):
    parent_popup = instance_or_parent_popup

    def import_callback(file_path):
        app.import_substations_from_file(file_path)

    _open_file_chooser_and_import(app, parent_popup, import_callback, title="Εισαγωγή Υποσταθμών")


def show_import_elements_dialog(app, instance_or_parent_popup=None):
    parent_popup = instance_or_parent_popup

    def import_callback(file_path):
        app.import_elements_from_file(file_path)

    _open_file_chooser_and_import(app, parent_popup, import_callback, title="Εισαγωγή Στοιχείων")


def show_import_android_changes_dialog(app, instance_or_parent_popup=None):
    parent_popup = instance_or_parent_popup

    def import_callback(file_path):
        app.import_android_changes_from_file(file_path)
    _open_file_chooser_and_import(
        app,
        parent_popup,
        import_callback,
        title="Εισαγωγή αλλαγών από Android",
        filetypes=(("JSON files", "*.json"),),
        chooser_filters=["*.json"],
    )
"""
Delegating wrappers for import-related UI functions in `DBrun.py`.
"""


def show_import_menu_delegate(app, instance=None):
    return app.show_import_menu(instance)


def show_import_substations_dialog_delegate(app, instance_or_parent_popup):
    return app.show_import_substations_dialog(instance_or_parent_popup)


def show_import_elements_dialog_delegate(app, instance_or_parent_popup):
    return app.show_import_elements_dialog(instance_or_parent_popup)


def show_import_android_changes_dialog_delegate(app, instance_or_parent_popup):
    return app.show_import_android_changes_dialog(instance_or_parent_popup)


def show_import_inspections_dialog_delegate(app, instance):
    return app.show_import_inspections_dialog(instance)
