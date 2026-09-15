"""Popup helpers with a non-Kivy fallback for headless/testing environments.

When Kivy is available the module exposes Kivy `show_message_popup`,
`ask_open_file`, and `ask_save_file` implementations used by the app's UI.
If Kivy is not importable the module provides lightweight console/tkinter
fallbacks so logic that depends on these helpers can run while Kivy is
not installed.
"""

import importlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import uuid

_LAUNCHED_CHILD_PROCESSES = []

try:
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.button import Button
    from kivy.uix.label import Label
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView

    KIVY_AVAILABLE = True
except Exception:
    KIVY_AVAILABLE = False


def _resolve_app_icon_path():
    base_dir = os.path.dirname(__file__)
    ico_candidates = [
        os.path.join(base_dir, "deddie_logo.ico"),
        os.path.join(base_dir, "logo_deddie.ico"),
    ]
    for candidate in ico_candidates:
        try:
            if os.path.isfile(candidate):
                return os.path.abspath(candidate)
        except Exception:
            continue

    png_candidates = [
        os.path.join(base_dir, "logo_deddie.png"),
        os.path.join(base_dir, "deddie_logo.png"),
        os.path.join(base_dir, "res", "icons", "android_launcher.png"),
    ]
    for candidate in png_candidates:
        try:
            if os.path.isfile(candidate):
                generated = _ensure_runtime_ico_from_png(candidate)
                if generated:
                    return generated
        except Exception:
            continue
    return ""


def _read_png_dimensions(png_path):
    try:
        with open(png_path, "rb") as handle:
            blob = handle.read(64)
        if len(blob) < 24 or blob[:8] != b"\x89PNG\r\n\x1a\n" or blob[12:16] != b"IHDR":
            return None
        width = int.from_bytes(blob[16:20], byteorder="big", signed=False)
        height = int.from_bytes(blob[20:24], byteorder="big", signed=False)
        if width <= 0 or height <= 0:
            return None
        return width, height
    except Exception:
        return None


def _wrap_png_as_ico(png_path, ico_path):
    dims = _read_png_dimensions(png_path)
    if not dims:
        return ""
    width, height = dims
    if width > 256 or height > 256:
        return ""

    with open(png_path, "rb") as handle:
        png_bytes = handle.read()

    width_byte = 0 if width == 256 else width
    height_byte = 0 if height == 256 else height

    header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack(
        "<BBBBHHII",
        width_byte,
        height_byte,
        0,
        0,
        1,
        32,
        len(png_bytes),
        6 + 16,
    )
    with open(ico_path, "wb") as handle:
        handle.write(header)
        handle.write(entry)
        handle.write(png_bytes)
    return ico_path if os.path.isfile(ico_path) else ""


def _ensure_runtime_ico_from_png(png_path):
    png_path = os.path.abspath(str(png_path or "").strip())
    if not png_path or not os.path.isfile(png_path):
        return ""

    ico_path = os.path.join(tempfile.gettempdir(), "dbsubstations_runtime_icon.ico")

    try:
        from PIL import Image as PILImage

        with PILImage.open(png_path) as image:
            rgba = image.convert("RGBA")
            rgba.thumbnail((256, 256))
            rgba.save(ico_path, format="ICO")
        if os.path.isfile(ico_path):
            return ico_path
    except Exception:
        pass

    return _wrap_png_as_ico(png_path, ico_path)


def _preferred_python_executable():
    executable = os.path.abspath(sys.executable or "")
    if not executable:
        return sys.executable

    exe_name = os.path.basename(executable).lower()
    if exe_name == "python.exe":
        pythonw_candidate = os.path.join(os.path.dirname(executable), "pythonw.exe")
        if os.path.isfile(pythonw_candidate):
            return pythonw_candidate
    return executable


def open_desktop_menu_window(
    title,
    message,
    buttons,
    *,
    close_label="Close",
    width=460,
    height=340,
):
    """Open a small native desktop menu window on Windows using tkinter.

    The app uses a single Kivy window, so this helper is only for the top-level
    desktop menus that should appear as separate windows.
    """
    if not KIVY_AVAILABLE:
        return False

    try:
        from kivy.clock import Clock
    except Exception:
        return False

    normalized_buttons = list(buttons or [])

    action_map = {}
    serialized_buttons = []
    for index, (label_text, callback) in enumerate(normalized_buttons):
        action_id = f"action_{index}"
        action_map[action_id] = callback
        serialized_buttons.append({"id": action_id, "label": str(label_text)})

    result_path = os.path.join(
        tempfile.gettempdir(), f"db_substations_menu_{uuid.uuid4().hex}.json"
    )

    helper_script = r"""
import json
import pathlib
import sys
import tkinter as tk

title = json.loads(sys.argv[1])
message = json.loads(sys.argv[2])
buttons = json.loads(sys.argv[3])
close_label = json.loads(sys.argv[4])
result_path = pathlib.Path(sys.argv[5])
width = int(sys.argv[6])
height = int(sys.argv[7])
icon_path = json.loads(sys.argv[8]) if len(sys.argv) > 8 else ""

BG = "#0f2f5f"
PANEL = "#123a74"
BUTTON = "#1f4e8c"
BUTTON_ACTIVE = "#2d6ab3"
TEXT = "#ffffff"
SUBTEXT = "#dbe7f5"

def write_result(action_id):
    try:
        result_path.write_text(json.dumps({"action": action_id}), encoding="utf-8")
    except Exception:
        pass

root = tk.Tk()
try:
    import ctypes

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("HEDNO.SubstationManager")
except Exception:
    pass
root.title(str(title or "Menu"))
root.geometry(f"{width}x{height}")
root.minsize(max(320, int(width * 0.8)), max(220, int(height * 0.8)))
root.configure(bg=BG)
_icon_ref = None
try:
    if icon_path:
        if str(icon_path).lower().endswith(".ico"):
            root.iconbitmap(str(icon_path))
        else:
            _icon_ref = tk.PhotoImage(file=str(icon_path))
            root.iconphoto(True, _icon_ref)
except Exception:
    pass
try:
    root.attributes("-topmost", True)
except Exception:
    pass

frame = tk.Frame(root, padx=16, pady=16, bg=BG)
frame.pack(fill="both", expand=True)

header = tk.Frame(frame, bg=PANEL, padx=14, pady=12)
header.pack(fill="x", pady=(0, 14))

title_label = tk.Label(
    header,
    text=str(title or "Menu"),
    bg=PANEL,
    fg=TEXT,
    anchor="w",
    font=("Segoe UI", 13, "bold"),
)
title_label.pack(fill="x")

if message:
    label = tk.Label(
        frame,
        text=str(message),
        bg=BG,
        fg=SUBTEXT,
        justify="left",
        anchor="w",
        wraplength=max(240, int(width) - 48),
        font=("Segoe UI", 10, "bold"),
    )
    label.pack(fill="x", pady=(0, 12))

button_frame = tk.Frame(frame, bg=BG)
button_frame.pack(fill="both", expand=True)

def choose(action_id):
    write_result(action_id)
    try:
        root.destroy()
    except Exception:
        pass

for item in buttons:
    tk.Button(
        button_frame,
        text=str(item.get("label", "")),
        bg=BUTTON,
        fg=TEXT,
        activebackground=BUTTON_ACTIVE,
        activeforeground=TEXT,
        relief="flat",
        bd=0,
        padx=12,
        pady=10,
        command=lambda action_id=item.get("id", ""): choose(action_id),
    ).pack(fill="x", pady=4)

tk.Button(
    frame,
    text=str(close_label or "Close"),
    bg="#3a5f92",
    fg=TEXT,
    activebackground="#5479a8",
    activeforeground=TEXT,
    relief="flat",
    bd=0,
    padx=12,
    pady=8,
    command=lambda: choose("__close__"),
).pack(fill="x", pady=(10, 0))

def on_close():
    choose("__close__")

root.protocol("WM_DELETE_WINDOW", on_close)
try:
    root.lift()
except Exception:
    pass
root.after(100, lambda: root.attributes("-topmost", False) if root.winfo_exists() else None)
root.mainloop()
"""

    command = [
        _preferred_python_executable(),
        "-c",
        helper_script,
        json.dumps(title, ensure_ascii=False),
        json.dumps(message, ensure_ascii=False),
        json.dumps(serialized_buttons, ensure_ascii=False),
        json.dumps(close_label, ensure_ascii=False),
        result_path,
        str(int(width)),
        str(int(height)),
        json.dumps(_resolve_app_icon_path(), ensure_ascii=False),
    ]

    try:
        subprocess.Popen(
            command,
            cwd=os.getcwd(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return False

    def _poll_result(_dt):
        if not os.path.exists(result_path):
            return True
        try:
            with open(result_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            return True

        action_id = payload.get("action")
        try:
            os.remove(result_path)
        except Exception:
            pass

        callback = action_map.get(action_id)
        if callback is not None:
            try:
                callback()
            except Exception:
                pass
        return False

    Clock.schedule_interval(_poll_result, 0.2)
    return True


def _resolve_app_entry_script():
    """Return a usable app entry path for a second-process launch.

    `sys.argv[0]` can be empty, a console stub, or an executable path depending on
    how the app was launched. Prefer an actual project script or executable that
    can re-open the app without requiring a Python interpreter wrapper.
    """
    candidates = []
    argv0 = (sys.argv[0] if sys.argv else "") or ""
    cwd = os.getcwd()
    module_dir = os.path.dirname(__file__)
    for candidate in [
        os.path.join(cwd, "DBrun.py"),
        os.path.join(cwd, "DBrun.exe"),
        os.path.join(cwd, "dbsubstations.exe"),
        os.path.join(module_dir, "DBrun.py"),
        os.path.join(module_dir, "DBrun.exe"),
        os.path.join(module_dir, "dbsubstations.exe"),
        argv0,
    ]:
        if not candidate:
            continue
        normalized = os.path.abspath(candidate)
        if os.path.isfile(normalized):
            candidates.append(normalized)
    if not candidates:
        return None
    return candidates[0]


def _build_launch_command(script, screen_name, payload=None, parent_pid=None):
    """Build a command that works for both Python scripts and bundled EXEs.

    Kivy treats any flags before a ``--`` separator as its own CLI options. The
    app-specific ``--dbs-open-*`` flags must therefore be passed after ``--`` so
    Kivy leaves them alone and the child app can still parse them.
    """
    command = []
    if script and script.lower().endswith(".exe"):
        command.append(script)
    else:
        command.extend([_preferred_python_executable(), script])
    command.append("--")
    command.append(f"--dbs-open-screen={screen_name}")
    if parent_pid is not None:
        command.append(f"--dbs-parent-pid={int(parent_pid)}")
    if payload is not None:
        command.append(f"--dbs-open-payload={json.dumps(payload, ensure_ascii=False)}")
    return command


def launch_app_screen(screen_name, payload=None):
    """Launch a second copy of the app directly into a named screen.

    The current app remains open; this helper starts a new process that can
    navigate to a dedicated screen after login.
    """
    try:
        script = _resolve_app_entry_script()
        if not script:
            return False
        command = _build_launch_command(
            script,
            screen_name,
            payload,
            parent_pid=os.getpid(),
        )
        child_proc = subprocess.Popen(
            command,
            cwd=os.getcwd(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        _LAUNCHED_CHILD_PROCESSES.append(child_proc)
        return True
    except Exception:
        return False


def terminate_launched_child_processes():
    """Best-effort shutdown of child app windows started by this process."""
    for child_proc in list(_LAUNCHED_CHILD_PROCESSES):
        try:
            poll = getattr(child_proc, "poll", None)
            if callable(poll) and poll() is not None:
                continue
            terminate = getattr(child_proc, "terminate", None)
            if callable(terminate):
                terminate()
        except Exception:
            continue


if KIVY_AVAILABLE:

    def create_popup(title, size_hint, **kwargs):
        """Create a popup while tolerating Kivy versions that reject unsupported kwargs.

        This project historically passed a `modal` kwarg, but the installed Kivy
        popup API does not accept it. We silently drop unsupported arguments and
        keep the valid ones such as `auto_dismiss`.
        """
        popup_module = importlib.import_module("kivy.uix.popup")
        popup_cls = popup_module.Popup

        popup_kwargs = dict(kwargs)
        popup_kwargs.pop("modal", None)

        try:
            return popup_cls(title=title, size_hint=size_hint, **popup_kwargs)
        except TypeError as exc:
            msg = str(exc)
            if (
                "unexpected keyword argument" not in msg
                and "positional argument" not in msg
            ):
                raise
            return popup_cls(title=title, size_hint=size_hint)

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
