from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView


def show_message_popup(title: str, message: str, callback=None) -> None:
    """Show a Kivy popup with dynamic sizing based on message length."""
    msg_len = len(message)
    if msg_len < 100:
        size_hint = (0.7, 0.3)
    elif msg_len < 200:
        size_hint = (0.85, 0.4)
    else:
        size_hint = (0.9, 0.55)

    popup = Popup(title=title, size_hint=size_hint)
    layout = BoxLayout(orientation="vertical", padding=10, spacing=10)

    scroll = ScrollView()
    msg_label = Label(text=message, size_hint_y=None, markup=False)
    msg_label.bind(texture_size=msg_label.setter("size"))
    scroll.add_widget(msg_label)
    layout.add_widget(scroll)

    close_btn = Button(text="OK", size_hint_y=0.15)

    def on_close(btn):
        popup.dismiss()
        if callback:
            callback()

    close_btn.bind(on_press=on_close)
    layout.add_widget(close_btn)

    popup.content = layout
    popup.open()


def ask_open_file(title: str = "Select file", filetypes=None):
    """Show a native open-file dialog and return the selected path or None.

    Uses tkinter when available; returns None if unavailable or cancelled.
    """
    try:
        import tkinter as _tk
        from tkinter import filedialog as _fd
    except Exception:
        raise ImportError("tkinter not available")

    _root = _tk.Tk()
    _root.withdraw()
    try:
        ft = list(filetypes) if filetypes else [("All files", "*.*")]
        fp = _fd.askopenfilename(title=title, filetypes=ft)
    finally:
        try:
            _root.destroy()
        except Exception:
            pass
    return fp or None
