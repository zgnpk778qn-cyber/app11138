[app]

title = AutoClicker
package.name = autoclicker
package.domain = org.autoclicker
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0.2

# Minimal dependencies — no numpy, no pyjnius
requirements = python3,kivy,Pillow

# Permissions
android.permissions = INTERNET,SYSTEM_ALERT_WINDOW,FOREGROUND_SERVICE
android.api = 34
android.minapi = 24
android.ndk = 25b
android.accept_sdk_license = True

# Only arm64 for faster build
android.archs = arm64-v8a

# Debug build
android.release = False
android.debug = True

orientation = portrait
fullscreen = 0

[buildozer]

log_level = 1
warn_on_root = 1
