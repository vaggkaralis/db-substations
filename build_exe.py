"""
Build script to create Windows executable for Substation Management App
Uses PyInstaller to bundle the Kivy application
"""

import PyInstaller.__main__
import os

# Get the directory of this script
script_dir = os.path.dirname(os.path.abspath(__file__))

PyInstaller.__main__.run([
    'DBrun.py',
    '--name=SubstationManager',
    '--onefile',
    '--windowed',
    '--icon=NONE',
    f'--add-data={os.path.join(script_dir, "database.py")};.',
    f'--add-data={os.path.join(script_dir, "importers.py")};.',
    f'--add-data={os.path.join(script_dir, "popups.py")};.',
    f'--add-data={os.path.join(script_dir, "templates.py")};.',
    '--hidden-import=kivy.core.window.window_sdl2',
    '--hidden-import=kivy.core.image.img_sdl2',
    '--hidden-import=kivy.core.text.text_sdl2',
    '--hidden-import=pandas',
    '--hidden-import=openpyxl',
    '--hidden-import=sqlite3',
    '--clean',
])
