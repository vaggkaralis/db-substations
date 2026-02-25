"""
Build script to create Windows executable for Substation Management App
Uses PyInstaller to bundle the Kivy application
"""

import os

import PyInstaller.__main__

from settings import DB_FILENAME

# Get the directory of this script
script_dir = os.path.dirname(os.path.abspath(__file__))

data_files = [
    "database.py",
    "importers.py",
    "popups.py",
    "templates.py",
    "logo_deddie.png",
    "deddie_logo.png",
    "DejaVuSans.ttf",
    "VERSION",
    "elements_import_template.xlsx",
    "επιθεωρήσεις_template.xlsx",
    DB_FILENAME,
]

add_data_args = []
for file_name in data_files:
    file_path = os.path.join(script_dir, file_name)
    if os.path.exists(file_path):
        add_data_args.append(f"--add-data={file_path};.")

PyInstaller.__main__.run(
    [
        "DBrun.py",
        "--name=SubstationManager",
        "--onedir",
        "--windowed",
        "--icon=NONE",
        "--noconfirm",
        *add_data_args,
        "--hidden-import=kivy.core.window.window_sdl2",
        "--hidden-import=kivy.core.image.img_sdl2",
        "--hidden-import=kivy.core.text.text_sdl2",
        "--hidden-import=pandas",
        "--hidden-import=openpyxl",
        "--hidden-import=sqlite3",
        "--clean",
    ]
)
