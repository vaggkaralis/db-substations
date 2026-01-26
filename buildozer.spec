[app]
title = DB Substations
package.name = dbsubstations
package.domain = org.dbsubstations

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,ttf

version = 1.0
requirements = python3,kivy,requests,pyjnius

permissions = INTERNET,ACCESS_NETWORK_STATE

orientation = portrait
fullscreen = 0

[buildozer]
log_level = 2
warn_on_root = 1
