[app]
title = DB Substations
package.name = dbsubstations
package.domain = org.dbsubstations

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf

version = 1.0.0
requirements = python3,kivy==2.3.0,pillow,certifi,urllib3,charset-normalizer,idna,requests

permissions = INTERNET,ACCESS_NETWORK_STATE,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE

android.permissions = INTERNET,ACCESS_NETWORK_STATE

# Bootstrap and backend
p4a.bootstrap = sdl2
p4a.backend = kivy

orientation = portrait
fullscreen = 0

android.api = 31
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True

# Enable logcat output
android.logcat_filters = *:S python:D

[buildozer]
log_level = 2
warn_on_root = 1
