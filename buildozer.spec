[app]
title = DB Substations
package.name = dbsubstations
package.domain = org.dbsubstations

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf

version = 1.0
requirements = python3,kivy==2.0.0,requests,kivy-garden,garden.navigationdrawer

permissions = INTERNET,ACCESS_NETWORK_STATE

orientation = portrait
fullscreen = 0

android.api = 31
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 1
