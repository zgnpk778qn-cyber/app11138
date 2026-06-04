[app]

title = AutoClicker
package.name = autoclicker
package.domain = org.autoclicker
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0.3

# pyjnius = Android API access for foreground service
requirements = python3,kivy,Pillow,pyjnius

# Background service
services = autoclicker:service/main.py

# Permissions for background operation
android.permissions = INTERNET,FOREGROUND_SERVICE,POST_NOTIFICATIONS,SYSTEM_ALERT_WINDOW,WAKE_LOCK
android.api = 34
android.minapi = 24
android.ndk = 25b
android.accept_sdk_license = True

# Only arm64 for speed
android.archs = arm64-v8a

android.release = False
android.debug = True

orientation = portrait
fullscreen = 0

[buildozer]

log_level = 2
warn_on_root = 1
