[app]

# 应用信息
title = AutoClicker
package.name = autoclicker
package.domain = org.autoclicker
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0.0
requirements = python3,kivy,Pillow,numpy,pyjnius,android

# 权限
android.permissions = INTERNET,READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,SYSTEM_ALERT_WINDOW,FOREGROUND_SERVICE
android.api = 34
android.minapi = 24
android.ndk = 25b
android.accept_sdk_license = True

# 编译架构
android.archs = arm64-v8a,armeabi-v7a

# 图标
android.icon = icon.png

# 是否为发行版
android.release = False

# 调试模式
android.debug = True
android.ndk_path =
android.sdk_path =

# 默认布局
orientation = portrait
fullscreen = 0

# Tesseract 集成（通过自定义 recipe）
# 注意：需要在 .buildozer/android/platform/build-*/recipes 下添加 tesseract recipe
# 或者使用预编译的 tesseract 二进制文件

[buildozer]

log_level = 2
warn_on_root = 1
