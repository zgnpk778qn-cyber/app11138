AutoClicker APK 构建指南
=========================

方式一：GitHub Actions 云端编译（推荐）
--------------------------------------
1. 打开 github.com，新建一个仓库（New Repository）
2. 本项目已经包含了 .github/workflows/build-apk.yml，推送即自动编译
3. 在项目目录执行：
   cd autoclicker_app
   git init
   git add .
   git commit -m "init"
   git remote add origin https://github.com/你的用户名/仓库名.git
   git push -u origin main
4. 打开 GitHub → 仓库 → Actions 页面，等待 "Build APK" 运行完成
5. 在运行结果中下载 "autoclicker-apk" -> 解压得到 .apk 文件

方式二：本地 Linux / WSL 构建
-----------------------------
需要一台 Linux 机器或 Windows WSL（Ubuntu 22.04/24.04）

安装依赖：
  sudo apt update
  sudo apt install -y python3-pip python3-dev libssl-dev libffi-dev \
    wget unzip file git autoconf automake autopoint libtool \
    pkg-config ccache cmake openjdk-17-jdk zlib1g-dev
  pip install --upgrade pip buildozer cython

编译：
  cd autoclicker_app
  buildozer android debug

APK 位置：autoclicker_app/bin/autoclicker-1.0.0-arm64-v8a-debug.apk

安装测试：
  adb install autoclicker_app/bin/autoclicker-1.0.0-arm64-v8a-debug.apk

注意事项：
- 首次编译需要下载 Android SDK/NDK，约 2-3GB，耗时 10-30 分钟
- APK 安装后需要开启无障碍服务（用于点击）和悬浮窗权限
