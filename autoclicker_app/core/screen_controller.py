"""
屏幕控制模块
截图、点击、滑动功能，支持多种后端：
  - adb:    通过 ADB 连接（需电脑或 ADB WiFi）
  - android:通过 Android API (pyjnius，需打包为 APK 运行)
  - mock:   模拟模式（用于桌面开发测试）
"""

import os
import re
import time
import subprocess
from io import BytesIO

import numpy as np
from PIL import Image


class ScreenController:
    """屏幕控制器，统一管理截图和点击操作"""

    def __init__(self, backend='mock', adb_device=None, screen_size=None):
        """
        参数:
            backend: 'adb' / 'android' / 'mock'
            adb_device: ADB 设备序列号（backend='adb' 时使用）
            screen_size: (w, h) 屏幕分辨率，可选
        """
        self.backend = backend
        self.adb_device = adb_device
        self._screen_size = screen_size
        self._android_context = None

        if backend == 'adb':
            self._init_adb()
        elif backend == 'android':
            self._init_android()

    # ── 初始化 ──────────────────────────────────────────

    def _init_adb(self):
        """初始化 ADB 连接"""
        try:
            if self.adb_device:
                subprocess.run(
                    ['adb', '-s', self.adb_device, 'get-state'],
                    capture_output=True, timeout=5
                )
            else:
                subprocess.run(
                    ['adb', 'get-state'], capture_output=True, timeout=5
                )
        except Exception as e:
            raise RuntimeError(f"ADB 连接失败: {e}\n请确保已连接设备并启用 USB 调试")

    def _init_android(self):
        """初始化 Android API（pyjnius）"""
        try:
            from jnius import autoclass
            self._android_context = autoclass('org.kivy.android.PythonActivity')
        except ImportError:
            raise RuntimeError(
                "jnius 不可用，android 后端只能在打包后的 APK 中使用"
            )

    # ── 截图 ────────────────────────────────────────────

    def screenshot(self, filename=None):
        """
        截取屏幕
        返回: PIL Image 对象
        """
        if self.backend == 'adb':
            return self._screenshot_adb(filename)
        elif self.backend == 'android':
            return self._screenshot_android(filename)
        else:
            return self._screenshot_mock(filename)

    def _screenshot_adb(self, filename=None):
        """通过 ADB 截图"""
        result = subprocess.run(
            ['adb', 'exec-out', 'screencap', '-p'],
            capture_output=True, timeout=10
        )
        img = Image.open(BytesIO(result.stdout))
        img = img.convert('RGB')
        self._screen_size = img.size
        if filename:
            img.save(filename)
        return img

    def _screenshot_android(self, filename=None):
        """通过 Android MediaProjection API 截图"""
        try:
            import android
            from jnius import autoclass, cast

            PythonActivity = self._android_context
            activity = PythonActivity.mActivity

            # 获取 MediaProjectionManager
            media_projection_mgr = activity.getSystemService('media_projection')

            # 需要用户授权 - 简化版本使用 screencap shell 命令
            result = subprocess.run(
                ['screencap', '-p'], capture_output=True, timeout=10
            )
            if result.returncode == 0:
                img = Image.open(BytesIO(result.stdout))
                img = img.convert('RGB')
                self._screen_size = img.size
                if filename:
                    img.save(filename)
                return img
        except Exception:
            pass

        # 降级到文件截屏
        try:
            tmp_path = '/sdcard/autoclicker_temp.png'
            subprocess.run(['screencap', '-p', tmp_path], timeout=10)
            img = Image.open(tmp_path)
            img = img.convert('RGB')
            self._screen_size = img.size
            if filename:
                img.save(filename)
            return img
        except Exception as e:
            raise RuntimeError(f"Android 截图失败: {e}")

    def _screenshot_mock(self, filename=None):
        """模拟截图（用于桌面测试，加载示例图片或生成纯色图）"""
        if filename and os.path.exists(filename):
            img = Image.open(filename)
            img = img.convert('RGB')
        else:
            w, h = self._screen_size or (1080, 1920)
            img = Image.new('RGB', (w, h), color=(240, 240, 240))

        self._screen_size = img.size
        return img

    # ── 点击 ────────────────────────────────────────────

    def click(self, x, y):
        """
        点击屏幕指定坐标
        返回: bool 是否成功
        """
        x, y = int(x), int(y)
        if self.backend == 'adb':
            return self._click_adb(x, y)
        elif self.backend == 'android':
            return self._click_android(x, y)
        else:
            return self._click_mock(x, y)

    def _click_adb(self, x, y):
        try:
            args = ['adb', 'shell', 'input', 'tap', str(x), str(y)]
            if self.adb_device:
                args = ['adb', '-s', self.adb_device, 'shell', 'input', 'tap',
                        str(x), str(y)]
            subprocess.run(args, capture_output=True, timeout=5)
            return True
        except Exception:
            return False

    def _click_android(self, x, y):
        try:
            from jnius import autoclass
            PythonActivity = self._android_context
            context = PythonActivity.mActivity

            # 使用 Instrumentation 或 input 命令
            subprocess.run(
                ['input', 'tap', str(x), str(y)],
                capture_output=True, timeout=5
            )
            return True
        except Exception:
            return False

    def _click_mock(self, x, y):
        print(f"[模拟] 点击 ({x}, {y})")
        return True

    # ── 滑动 ────────────────────────────────────────────

    def swipe(self, x1, y1, x2, y2, duration=300):
        """
        滑动操作
        duration: 滑动持续时间（毫秒）
        """
        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
        if self.backend == 'adb':
            return self._swipe_adb(x1, y1, x2, y2, duration)
        elif self.backend == 'android':
            return self._swipe_android(x1, y1, x2, y2, duration)
        else:
            return self._swipe_mock(x1, y1, x2, y2, duration)

    def _swipe_adb(self, x1, y1, x2, y2, duration):
        try:
            args = ['adb', 'shell', 'input', 'swipe',
                    str(x1), str(y1), str(x2), str(y2), str(duration)]
            if self.adb_device:
                args = ['adb', '-s', self.adb_device, 'shell', 'input', 'swipe',
                        str(x1), str(y1), str(x2), str(y2), str(duration)]
            subprocess.run(args, capture_output=True, timeout=5)
            return True
        except Exception:
            return False

    def _swipe_android(self, x1, y1, x2, y2, duration):
        try:
            subprocess.run(
                ['input', 'swipe', str(x1), str(y1), str(x2), str(y2),
                 str(duration)],
                capture_output=True, timeout=5
            )
            return True
        except Exception:
            return False

    def _swipe_mock(self, x1, y1, x2, y2, duration):
        print(f"[模拟] 滑动 ({x1},{y1}) → ({x2},{y2}) dur={duration}ms")
        return True

    def scroll_up(self, percent=0.4):
        """向上滑动（翻下一页/下拉）"""
        w, h = self._screen_size or (1080, 1920)
        start_y = int(h * 0.6)
        end_y = int(h * (0.6 - percent))
        return self.swipe(w // 2, start_y, w // 2, end_y)

    def scroll_down(self, percent=0.4):
        """向下滑动（上拉）"""
        w, h = self._screen_size or (1080, 1920)
        start_y = int(h * 0.3)
        end_y = int(h * (0.3 + percent))
        return self.swipe(w // 2, start_y, w // 2, end_y)

    # ── 屏幕信息 ────────────────────────────────────────

    def get_screen_size(self):
        """获取屏幕分辨率"""
        if self._screen_size:
            return self._screen_size

        if self.backend == 'adb':
            try:
                result = subprocess.run(
                    ['adb', 'shell', 'wm', 'size'],
                    capture_output=True, text=True, timeout=5
                )
                match = re.search(r'(\d+)x(\d+)', result.stdout)
                if match:
                    self._screen_size = (int(match.group(1)), int(match.group(2)))
            except Exception:
                pass

        return self._screen_size or (1080, 1920)

    def set_screen_size(self, w, h):
        """手动设置屏幕分辨率"""
        self._screen_size = (w, h)
