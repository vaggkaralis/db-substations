"""Popup helpers with a non-Kivy fallback for headless/testing environments.

When Kivy is available the module exposes Kivy `show_message_popup`,
`ask_open_file`, and `ask_save_file` implementations used by the app's UI.
If Kivy is not importable the module provides lightweight console/tkinter
fallbacks so logic that depends on these helpers can run while Kivy is
not installed.
"""

try:
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView

    KIVY_AVAILABLE = True
except Exception:
    KIVY_AVAILABLE = False


if KIVY_AVAILABLE:

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

        scroll = ScrollView(do_scroll_x=False, do_scroll_y=True, bar_width=10)
        msg_label = Label(
            text=str(message),
            size_hint_y=None,
            markup=False,
            halign="left",
            valign="top",
        )

        def _update_wrap_width(instance, width):
            instance.text_size = (max(10, width - 14), None)

        msg_label.bind(
            width=_update_wrap_width,
            texture_size=lambda inst, size: setattr(inst, "height", size[1] + 8),
        )
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

        Uses Win32 API when available, otherwise falls back to tkinter.
        """
        # Prefer Windows API dialog when available; fall back to tkinter.
        try:
            win_fp = _win32_get_open_filename(title=title, filetypes=filetypes)
            return win_fp or None
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
            fp = _fd.askopenfilename(title=title, filetypes=ft)
        finally:
            try:
                _root.destroy()
            except Exception:
                pass

        return fp or None

    def ask_open_files(title: str = "Select files", filetypes=None):
        """Show a native open-file dialog and return selected paths."""
        try:
            win_fps = _win32_get_open_filenames(title=title, filetypes=filetypes)
            return list(win_fps or [])
        except Exception:
            pass

        try:
            import tkinter as _tk
            from tkinter import filedialog as _fd
        except Exception:
            return []

        _root = _tk.Tk()
        _root.withdraw()
        try:
            ft = list(filetypes) if filetypes else [("All files", "*.*")]
            fps = _fd.askopenfilenames(title=title, filetypes=ft)
        finally:
            try:
                _root.destroy()
            except Exception:
                pass

        return list(fps or [])

    def _win32_get_open_filename(title: str = "Select file", filetypes=None):
        try:
            import ctypes
            from ctypes import wintypes
        except Exception:
            return None

        import sys

        if sys.platform != "win32":
            return None

        if filetypes:
            parts = []
            for desc, pattern in filetypes:
                parts.append(f"{desc}\0{pattern}")
            filter_str = "\0".join(parts) + "\0\0"
        else:
            filter_str = "All Files\0*.*\0\0"

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
        ofn.Flags = 0x00001000 | 0x00000800 | 0x00000800

        try:
            res = ctypes.windll.comdlg32.GetOpenFileNameW(ctypes.byref(ofn))
        except Exception:
            return None

        if res:
            return buffer.value
        return None

    def _win32_get_open_filenames(title: str = "Select files", filetypes=None):
        try:
            import ctypes
            from ctypes import wintypes
        except Exception:
            return []

        import sys

        if sys.platform != "win32":
            return []

        if filetypes:
            parts = []
            for desc, pattern in filetypes:
                parts.append(f"{desc}\0{pattern}")
            filter_str = "\0".join(parts) + "\0\0"
        else:
            filter_str = "All Files\0*.*\0\0"

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

        buffer_size = 65536
        buffer = ctypes.create_unicode_buffer(buffer_size)

        ofn = OPENFILENAMEW()
        ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
        ofn.lpstrFilter = filter_str
        ofn.lpstrFile = ctypes.cast(buffer, wintypes.LPWSTR)
        ofn.nMaxFile = buffer_size
        ofn.lpstrTitle = title
        ofn.Flags = 0x00001000 | 0x00000800 | 0x00080000 | 0x00000200

        try:
            res = ctypes.windll.comdlg32.GetOpenFileNameW(ctypes.byref(ofn))
        except Exception:
            return []

        if not res:
            return []

        parts = [part for part in buffer[:].split("\0") if part]
        if not parts:
            return []
        if len(parts) == 1:
            return [parts[0]]

        directory = parts[0]
        return [directory + "\\" + name for name in parts[1:]]

    def ask_save_file(
        title: str = "Save file", default_name: str = None, filetypes=None
    ):
        """Show a native save-file dialog and return the selected path or None.

        Uses Win32 API when available, otherwise falls back to tkinter.
        """
        try:
            import ctypes
        except Exception:
            ctypes = None

        import sys

        if sys.platform == "win32" and ctypes is not None:
            try:
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
            fp = _fd.asksaveasfilename(
                title=title,
                initialfile=default_name or "",
                filetypes=ft,
                defaultextension=".xlsx",
            )
        finally:
            try:
                _root.destroy()
            except Exception:
                pass

        return fp or None

else:
    # Fallback implementations when Kivy is not available. These are
    # intentionally minimal: they print messages to console and use
    # tkinter dialogs when possible for file selection.

    def show_message_popup(title: str, message: str, callback=None) -> None:
        print(f"--- {title} ---")
        try:
            print(str(message))
        except Exception:
            print(repr(message))
        if callback:
            try:
                callback()
            except Exception:
                pass

    def ask_open_file(title: str = "Select file", filetypes=None):
        try:
            import tkinter as _tk
            from tkinter import filedialog as _fd
        except Exception:
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

    def ask_open_files(title: str = "Select files", filetypes=None):
        try:
            import tkinter as _tk
            from tkinter import filedialog as _fd
        except Exception:
            return []

        _root = _tk.Tk()
        _root.withdraw()
        try:
            ft = list(filetypes) if filetypes else [("All files", "*.*")]
            fps = _fd.askopenfilenames(title=title, filetypes=ft)
        finally:
            try:
                _root.destroy()
            except Exception:
                pass
        return list(fps or [])

    def ask_save_file(
        title: str = "Save file", default_name: str = None, filetypes=None
    ):
        try:
            import tkinter as _tk
            from tkinter import filedialog as _fd
        except Exception:
            return None

        _root = _tk.Tk()
        _root.withdraw()
        try:
            ft = list(filetypes) if filetypes else [("All files", "*.*")]
            fp = _fd.asksaveasfilename(
                title=title, initialfile=default_name or "", filetypes=ft
            )
        finally:
            try:
                _root.destroy()
            except Exception:
                pass
        return fp or None
