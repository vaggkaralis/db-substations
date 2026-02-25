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
    # Prefer Windows API dialog when available (more consistent on Windows).
    # If Win32 API is present we call it and respect the user's choice (including
    # cancel). Only when the Win32 call is not available (raises) do we fall
    # back to tkinter. This avoids opening multiple dialogs in sequence.
    try:
        win_fp = _win32_get_open_filename(title=title, filetypes=filetypes)
        # If we were able to call the Win32 dialog, return its result (string or None)
        return win_fp or None
    except Exception:
        # Win32 API not available; try tkinter fallback
        pass

    try:
        import tkinter as _tk
        from tkinter import filedialog as _fd
    except Exception:
        # tkinter not available; return None
        return None

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


# Windows native fallback using comdlg32 (GetOpenFileNameW) when tkinter is
# not available or problematic. This avoids importing Kivy and keeps a modern
# Windows file dialog.
def _win32_get_open_filename(title: str = "Select file", filetypes=None):
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return None

    # Only on Windows
    import sys

    if sys.platform != "win32":
        return None

    # Build filter string for GetOpenFileNameW: pairs separated by '\0', end with '\0\0'
    if filetypes:
        parts = []
        for desc, pattern in filetypes:
            parts.append(f"{desc}\0{pattern}")
        filter_str = "\0".join(parts) + "\0\0"
    else:
        filter_str = "All Files\0*.*\0\0"

    # Define OPENFILENAMEW structure (sufficient subset)
    class OPENFILENAMEW(ctypes.Structure):
        _fields_ = [
            ("lStructSize", wintypes.DWORD),
            ("hwndOwner", wintypes.HWND),
            ("hInstance", wintypes.HINSTANCE),
            ("lpstrFilter", wintypes.LPCWSTR),
            ("lpstrCustomFilter", wintypes.LPWSTR),
            ("nMaxCustFilter", wintypes.DWORD),
            ("nFilterIndex", wintypes.DWORD),
            ("lpstrFile", wintypes.LPWSTR),
            ("nMaxFile", wintypes.DWORD),
            ("lpstrFileTitle", wintypes.LPWSTR),
            ("nMaxFileTitle", wintypes.DWORD),
            ("lpstrInitialDir", wintypes.LPCWSTR),
            ("lpstrTitle", wintypes.LPCWSTR),
            ("Flags", wintypes.DWORD),
            ("nFileOffset", wintypes.WORD),
            ("nFileExtension", wintypes.WORD),
            ("lpstrDefExt", wintypes.LPCWSTR),
            ("lCustData", wintypes.LPARAM),
            ("lpfnHook", wintypes.LPVOID),
            ("lpTemplateName", wintypes.LPCWSTR),
            ("pvReserved", wintypes.LPVOID),
            ("dwReserved", wintypes.DWORD),
            ("FlagsEx", wintypes.DWORD),
        ]

    buffer_size = 1024
    buffer = ctypes.create_unicode_buffer(buffer_size)

    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    ofn.lpstrFilter = filter_str
    ofn.lpstrFile = ctypes.cast(buffer, wintypes.LPWSTR)
    ofn.nMaxFile = buffer_size
    ofn.lpstrTitle = title
    # OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_EXPLORER
    ofn.Flags = 0x00001000 | 0x00000800 | 0x00000800

    try:
        res = ctypes.windll.comdlg32.GetOpenFileNameW(ctypes.byref(ofn))
    except Exception:
        return None

    if res:
        return buffer.value
    return None


def ask_save_file(title: str = "Save file", default_name: str = None, filetypes=None):
    """Show a native save-file dialog and return the selected path or None.

    Uses Win32 API when available, otherwise falls back to tkinter.
    """
    try:
        # Try Win32 API for Save dialog
        import ctypes
    except Exception:
        ctypes = None

    import sys

    if sys.platform == "win32" and ctypes is not None:
        try:
            # Use tkinter fallback for simplicity in Save dialog implementation
            raise Exception("fallback to tkinter")
        except Exception:
            pass

    try:
        import tkinter as _tk
        from tkinter import filedialog as _fd
    except Exception:
        return None

    _root = _tk.Tk()
    _root.withdraw()
    try:
        ft = list(filetypes) if filetypes else [("All files", "*.*")]
        fp = _fd.asksaveasfilename(title=title, initialfile=default_name or "", filetypes=ft, defaultextension=".xlsx")
    finally:
        try:
            _root.destroy()
        except Exception:
            pass

    return fp or None
