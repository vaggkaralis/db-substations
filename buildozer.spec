[app]
title = DB Substations
package.name = dbsubstations
package.domain = org.dbsubstations

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf,json,xlsx,pdf,txt,xml
source.exclude_dirs = .git,.github,.venv,__pycache__,tests,scripts,tools,dist,.pytest_cache,.ruff_cache,.VSCodeCounter
source.exclude_patterns = tests/*,tests/_shims/*,scripts/*,tools/*,dist/*,__pycache__/*,*.pyc,*.pyo,test_*.py,build_*.py
icon.filename = res/icons/android_launcher.png

version = 0.5.0
requirements = python3,kivy==2.3.0,plyer,pillow,certifi,urllib3,charset-normalizer,idna,requests

permissions = WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,MANAGE_EXTERNAL_STORAGE

android.permissions = WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE,MANAGE_EXTERNAL_STORAGE

# Bootstrap and backend
p4a.bootstrap = sdl2
p4a.backend = kivy
# Pin p4a to the last stable release for reproducible builds
p4a.branch = v2024.01.21

orientation = portrait
fullscreen = 0

# Target API 34 (Android 14) to ensure modern permission model and Play Store
# compatibility.  The native hwui mutex crash (FORTIFY SIGABRT in hwuiTask) on
# Android 16 + SDL2 is resolved by disabling hardware acceleration in the
# manifest (see android/AndroidManifest.tmpl and the CI sed patch).
android.api = 34
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True

# Enable logcat output
android.logcat_filters = *:S python:D

[buildozer]
log_level = 2
warn_on_root = 1
