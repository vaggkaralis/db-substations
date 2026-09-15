import os

from strings_proxy import STRINGS as S


def _open_file_chooser_and_import(
    app,
    parent_popup,
    import_callback,
    title=S["TITLES"]["IMPORT_MENU"],
    filetypes=None,
    chooser_filters=None,
):
    # Prefer native Windows file chooser when available; fall back to Kivy chooser.
    from popups import show_message_popup

    if os.name == "nt":
        try:
            import tkinter as _tk
            from tkinter import filedialog as _filedialog

            root = _tk.Tk()
            root.withdraw()
            ft = (
                list(filetypes)
                if filetypes
                else [
                    (
                        S["MESSAGES"].get("FILE_DIALOG_EXCEL_FILES", "Αρχεία Excel"),
                        "*.xlsx *.xls",
                    ),
                    (S["MESSAGES"].get("FILE_DIALOG_CSV_FILES", "Αρχεία CSV"), "*.csv"),
                    (
                        S["MESSAGES"].get("FILE_DIALOG_ALL_FILES", "Όλα τα αρχεία"),
                        "*.*",
                    ),
                ]
            )
            file_path = _filedialog.askopenfilename(title=title, filetypes=ft)
            try:
                root.destroy()
            except Exception:
                pass

            # If user cancelled the native dialog, silently return (no message).
            if not file_path:
                return
            if not os.path.exists(file_path):
                show_message_popup(
                    S["TITLES"]["ERROR"], S["MESSAGES"]["FILE_NOT_FOUND"]
                )
                return

            try:
                import_callback(file_path)
            except Exception as e:
                show_message_popup(
                    S["TITLES"]["ERROR"], f"{S['MESSAGES']['IMPORT_FAILED']}\n{str(e)}"
                )
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
    path_label = Label(
        text=S.get("MESSAGES", {}).get("FILE_PATH_LABEL", "Διαδρομή αρχείου:"),
        size_hint_y=0.1,
    )
    layout.add_widget(path_label)

    path_input = TextInput(
        hint_text=S.get("MESSAGES", {}).get("FILE_PATH_HINT", "Διαδρομή αρχείου"),
        size_hint_y=0.15,
        multiline=False,
    )
    layout.add_widget(path_input)

    # File chooser with default path
    layout.add_widget(
        Label(
            text=S["MESSAGES"].get(
                "IMPORT_OR_SELECT_FROM_LIST", "Ή επιλέξτε από τη λίστα:"
            ),
            size_hint_y=0.1,
        )
    )
    chooser = FileChooserListView(
        filters=(chooser_filters or ["*.xlsx", "*.csv"]), path=os.path.dirname(__file__)
    )
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
                file_path = file_path.strip().strip("\"'")
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
            show_message_popup(
                S["TITLES"]["ERROR"], f"{S['MESSAGES']['IMPORT_FAILED']}\n{str(e)}"
            )
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
        return

    try:
        from reports import export_full_db_ui
    except Exception:
        export_full_db_ui = None

    popup = Popup(
        title=S["TITLES"].get("IMPORT_MENU", "Εισαγωγή από αρχείο"),
        size_hint=(0.72, 0.62),
    )
    layout = BoxLayout(orientation="vertical", padding=10, spacing=10)
    layout.add_widget(
        Label(
            text=S["MESSAGES"].get(
                "IMPORT_MENU_PROMPT", "Επιλέξτε τι θέλετε να εισάγετε:"
            ),
            size_hint_y=None,
            height=40,
        )
    )

    actions = BoxLayout(orientation="vertical", spacing=8)

    buttons = [
        (
            S["MESSAGES"].get(
                "IMPORT_ELEMENTS_BUTTON", "Εισαγωγή Στοιχείων από Αρχείο"
            ),
            lambda: _show_import_elements_from_menu(app, popup),
            False,
        ),
        (
            S["MESSAGES"].get(
                "IMPORT_TEMPLATE_ELEMENTS_BUTTON", "Δημιουργία Template Εισαγωγής"
            ),
            lambda: app.create_elements_template(None),
            True,
        ),
        (
            S["TITLES"].get("IMPORT_ANDROID", "Εισαγωγή αλλαγών από Android"),
            lambda: _show_import_android_changes_from_menu(app, popup),
            False,
        ),
    ]
    if export_full_db_ui is not None:
        buttons.append(
            (
                S["MESSAGES"].get("IMPORT_EXPORT_DB_BUTTON", "Εξαγωγή Βάσης (Excel)"),
                lambda: export_full_db_ui(app, popup),
                False,
            )
        )

    def _run_action(action, close_menu=False):
        if close_menu:
            try:
                popup.dismiss()
            except Exception:
                pass
        try:
            action()
        except Exception:
            pass

    for label_text, callback, close_menu in buttons:
        action_btn = Button(text=label_text, size_hint_y=None, height=42)
        action_btn.bind(
            on_press=lambda _btn, cb=callback, close=close_menu: _run_action(cb, close)
        )
        actions.add_widget(action_btn)

    layout.add_widget(actions)

    cancel_btn = Button(text=S["BUTTONS"]["CANCEL"], size_hint_y=None, height=42)
    cancel_btn.bind(on_press=popup.dismiss)
    layout.add_widget(cancel_btn)

    popup.content = layout
    popup.open()


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

    _open_file_chooser_and_import(
        app,
        parent_popup,
        import_callback,
        title=S["TITLES"].get("IMPORT_SUBSTATIONS_TITLE", "Εισαγωγή Υποσταθμών"),
    )


def show_import_elements_dialog(app, instance_or_parent_popup=None):
    parent_popup = instance_or_parent_popup

    def import_callback(file_path):
        app.import_elements_from_file(file_path)

    _open_file_chooser_and_import(
        app,
        parent_popup,
        import_callback,
        title=S["TITLES"].get("IMPORT_ELEMENTS", "Εισαγωγή Στοιχείων"),
    )


def show_import_android_changes_dialog(app, instance_or_parent_popup=None):
    parent_popup = instance_or_parent_popup

    def import_callback(file_path):
        app.import_android_changes_from_file(file_path)

    _open_file_chooser_and_import(
        app,
        parent_popup,
        import_callback,
        title=S["TITLES"].get("IMPORT_ANDROID", "Εισαγωγή αλλαγών από Android"),
        filetypes=(
            (
                S["MESSAGES"].get(
                    "FILE_DIALOG_ANDROID_CHANGELOG_FILES",
                    "Αρχεία change log Android",
                ),
                "*.json *.jsonl *.txt",
            ),
        ),
        chooser_filters=["*.json", "*.jsonl", "*.txt"],
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
