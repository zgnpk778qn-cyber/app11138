"""
AutoClickerApp - 自动点击屏幕按钮的 Kivy App
功能：颜色识别、文字识别、自动点击、自动翻页
"""

import os
import sys
import json
from PIL import Image

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.properties import (
    StringProperty, ListProperty, NumericProperty, BooleanProperty, ObjectProperty
)
from kivy.lang import Builder

# 导入核心模块
from core.color_detector import ColorDetector
from core.ocr_engine import OCREngine
from core.screen_controller import ScreenController
from core.automation_engine import AutomationEngine


# ============================================================
# 配置界面
# ============================================================

class ConfigScreen(Screen):
    """配置屏幕：设置检测参数"""

    def on_enter(self):
        app = App.get_running_app()
        cfg = app.config_data

        self.ids.color_spinner.text = cfg.get('color', '红色')
        self.ids.interval_input.text = str(cfg.get('interval', 1.0))
        self.ids.scroll_interval_input.text = str(cfg.get('scroll_interval', 2.0))
        self.ids.max_scrolls_input.text = str(cfg.get('max_scrolls', 50))
        self.ids.color_targets_input.text = ', '.join(cfg.get('target_colors', []))
        self.ids.backend_spinner.text = cfg.get('backend', 'mock')
        self.ids.adb_device_input.text = cfg.get('adb_device', '')
        self._update_color_list()

    def _update_color_list(self):
        colors = ColorDetector.list_supported_colors()
        self.ids.color_spinner.values = colors

    def on_color_selected(self, spinner, text):
        App.get_running_app().config_data['color'] = text

    def set_backend(self, backend_name):
        App.get_running_app().config_data['backend'] = backend_name

    def save_config(self):
        app = App.get_running_app()
        data = app.config_data

        try:
            data['interval'] = float(self.ids.interval_input.text or '1.0')
        except ValueError:
            data['interval'] = 1.0

        try:
            data['scroll_interval'] = float(self.ids.scroll_interval_input.text or '2.0')
        except ValueError:
            data['scroll_interval'] = 2.0

        try:
            data['max_scrolls'] = int(self.ids.max_scrolls_input.text or '50')
        except ValueError:
            data['max_scrolls'] = 50

        data['target_colors'] = [
            c.strip() for c in self.ids.color_targets_input.text.replace('，', ',').split(',')
            if c.strip()
        ]

        app.save_config()
        app.show_toast('配置已保存')


# ============================================================
# 主控制界面
# ============================================================

class MainScreen(Screen):
    """主控制屏幕"""

    status_text = StringProperty('就绪')
    status_color = ListProperty([0.5, 0.5, 0.5, 1])  # 灰色
    log_text = StringProperty('')
    scroll_count = NumericProperty(0)
    last_action = StringProperty('')

    def on_enter(self):
        app = App.get_running_app()
        if app.engine:
            app.engine.on_log = self._on_engine_log
            app.engine.on_state_change = self._on_engine_state
            app.engine.on_detection = self._on_engine_detection

    def start_auto(self):
        app = App.get_running_app()
        if app.engine and app.engine.state == AutomationEngine.IDLE:
            app.start_automation()

    def stop_auto(self):
        app = App.get_running_app()
        if app.engine:
            app.engine.stop()

    def pause_auto(self):
        app = App.get_running_app()
        if app.engine:
            app.engine.pause()

    def resume_auto(self):
        app = App.get_running_app()
        if app.engine:
            app.engine.resume()

    def clear_log(self):
        self.log_text = ''
        if hasattr(self, '_log_cache'):
            self._log_cache = []

    def _on_engine_log(self, msg):
        self._log_cache = getattr(self, '_log_cache', [])
        self._log_cache.append(msg)
        if len(self._log_cache) > 200:
            self._log_cache = self._log_cache[-200:]

        # 更新 UI（在 UI 线程中执行）
        def update_log(dt):
            self.log_text = '\n'.join(self._log_cache[-30:])

        Clock.schedule_once(update_log, 0)

    def _on_engine_state(self, state):
        def update(dt):
            status_map = {
                AutomationEngine.RUNNING: ('运行中', [0.2, 0.8, 0.2, 1]),
                AutomationEngine.PAUSED: ('已暂停', [0.8, 0.8, 0.2, 1]),
                AutomationEngine.STOPPED: ('已停止', [0.8, 0.3, 0.3, 1]),
                AutomationEngine.IDLE: ('就绪', [0.5, 0.5, 0.5, 1]),
            }
            text, color = status_map.get(state, ('未知', [0.5, 0.5, 0.5, 1]))
            self.status_text = text
            self.status_color = color

        Clock.schedule_once(update, 0)

    def _on_engine_detection(self, color, text, x, y):
        def update(dt):
            self.last_action = f"检测到 [{color}] [{text}] @ ({x},{y})"
            if hasattr(self, '_log_cache'):
                self._log_cache.append(f"→ 点击 ({x},{y})")
            app = App.get_running_app()
            if app.engine:
                self.scroll_count = app.engine.scroll_count

        Clock.schedule_once(update, 0)


# ============================================================
# 主 App
# ============================================================

class AutoClickerApp(App):
    """自动点击器主应用"""

    config_data = ObjectProperty({
        'color': '红色',
        'target_colors': ['红色', '绿色', '蓝色', '橙色', '黄色'],
        'interval': 1.0,
        'scroll_interval': 2.0,
        'max_scrolls': 50,
        'backend': 'mock',  # mock / adb / android
        'adb_device': '',
    })

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.color_detector = None
        self.ocr_engine = None
        self.screen_controller = None
        self.engine = None
        self._toast_event = None

    def build(self):
        self.title = 'AutoClicker'
        self.load_config()
        self._init_components()

        sm = ScreenManager()
        sm.add_widget(MainScreen(name='main'))
        sm.add_widget(ConfigScreen(name='config'))
        return sm

    def _init_components(self):
        """初始化核心组件"""
        # 颜色检测器
        self.color_detector = ColorDetector()

        # OCR 引擎（保留以备将来使用）
        self.ocr_engine = OCREngine(font_path=None)

        if self.ocr_engine.is_available:
            print(f"OCR 引擎可用，字体: {self.ocr_engine.font_path}")
        else:
            print("未找到中文字体，文字识别功能不可用")
            print("请在配置中手动指定字体路径")

        # 屏幕控制器
        backend = self.config_data.get('backend', 'mock')
        adb_device = self.config_data.get('adb_device', '') or None
        self.screen_controller = ScreenController(
            backend=backend, adb_device=adb_device
        )

        # 自动化引擎
        self.engine = AutomationEngine(
            self.screen_controller, self.color_detector, self.ocr_engine
        )

    def start_automation(self):
        """启动自动化，应用最新配置"""
        if not self.engine:
            return

        # 应用配置
        cfg = self.config_data
        self.engine.interval = cfg.get('interval', 1.0)
        self.engine.scroll_interval = cfg.get('scroll_interval', 2.0)
        self.engine.max_scrolls = cfg.get('max_scrolls', 50)
        self.engine.target_colors = cfg.get('target_colors', [])
        self.engine.start()

    def save_config(self):
        """保存配置到本地文件"""
        path = self._config_path()
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")

    def load_config(self):
        """从本地文件加载配置"""
        path = self._config_path()
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    self.config_data.update(loaded)
        except Exception as e:
            print(f"加载配置失败: {e}")

    def _config_path(self):
        """配置文件路径"""
        data_dir = os.path.join(os.path.dirname(__file__), 'data')
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, 'config.json')

    def show_toast(self, message, duration=2):
        """显示短暂提示"""
        if self._toast_event:
            self._toast_event.cancel()

        root = self.root
        if hasattr(root, 'ids') and 'toast' in root.ids:
            toast = root.ids.toast
            toast.text = message
            toast.opacity = 1
            self._toast_event = Clock.schedule_once(
                lambda dt: setattr(toast, 'opacity', 0), duration
            )


if __name__ == '__main__':
    AutoClickerApp().run()
