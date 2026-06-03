"""
AutoClickerApp - 自动点击屏幕按钮的 Kivy App
功能：颜色+文字特征识别、自动点击、自动翻页、到达底部自动停止
"""

import os
import sys
import json
from PIL import Image

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.togglebutton import ToggleButton
from kivy.properties import (
    StringProperty, ListProperty, NumericProperty, BooleanProperty, ObjectProperty
)
from kivy.lang import Builder

from core.color_detector import ColorDetector
from core.ocr_engine import OCREngine
from core.screen_controller import ScreenController
from core.automation_engine import AutomationEngine


# ============================================================
# FeatureRow - 可重用的特征行组件
# ============================================================

class FeatureRow(BoxLayout):
    """单条目标特征配置行"""

    def __init__(self, color='', text='', enabled=True, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint_y = None
        self.height = 45
        self.spacing = 5

        self.enabled_btn = ToggleButton(
            text='V' if enabled else 'X',
            state='down' if enabled else 'normal',
            size_hint_x=0.08,
            font_size='14sp',
            background_color=(0.2, 0.8, 0.2, 1) if enabled else (0.5, 0.5, 0.5, 1),
        )
        self.enabled_btn.bind(state=self._on_enabled_toggle)

        all_colors = ColorDetector.list_supported_colors()
        self.color_spinner = Spinner(
            text=color if color else '任意颜色',
            values=['任意颜色'] + all_colors,
            size_hint_x=0.25,
            font_size='12sp',
        )
        if color:
            self.color_spinner.text = color

        self.text_input = TextInput(
            text=text,
            multiline=False,
            size_hint_x=0.25,
            font_size='12sp',
            hint_text='留空=任意文字',
            padding_y=8,
        )

        desc_parts = []
        desc_parts.append(color if color else '任意颜色')
        desc_parts.append(f"「{text}」" if text else '任意文字')
        self.desc_label = Label(
            text=' + '.join(desc_parts),
            size_hint_x=0.27,
            font_size='11sp',
            color=(0.7, 0.7, 0.7, 1),
            halign='left',
            text_size=(200, 45),
            valign='middle',
        )

        self.del_btn = Button(
            text='X',
            size_hint_x=0.08,
            font_size='14sp',
            background_color=(0.8, 0.2, 0.2, 1),
        )

        self.add_widget(self.enabled_btn)
        self.add_widget(self.color_spinner)
        self.add_widget(self.text_input)
        self.add_widget(self.desc_label)
        self.add_widget(self.del_btn)

        self.color_spinner.bind(text=self._update_desc)
        self.text_input.bind(text=self._update_desc)

    def _update_desc(self, *args):
        color = self.color_spinner.text
        if color == '任意颜色':
            color = ''
        text = self.text_input.text.strip()
        parts = []
        parts.append(color if color else '任意颜色')
        parts.append(f"「{text}」" if text else '任意文字')
        self.desc_label.text = ' + '.join(parts)

    def _on_enabled_toggle(self, btn, state):
        if state == 'down':
            btn.text = 'V'
            btn.background_color = (0.2, 0.8, 0.2, 1)
        else:
            btn.text = 'X'
            btn.background_color = (0.5, 0.5, 0.5, 1)
        self._update_desc()

    def get_data(self):
        color = self.color_spinner.text
        if color == '任意颜色':
            color = ''
        return {
            'color': color,
            'text': self.text_input.text.strip(),
            'enabled': self.enabled_btn.state == 'down',
        }


# ============================================================
# ConfigScreen - 系统参数配置
# ============================================================

class ConfigScreen(Screen):
    """系统配置屏幕：时间参数、连接设置"""

    def on_enter(self):
        app = App.get_running_app()
        cfg = app.config_data
        self.ids.color_spinner.text = cfg.get('color', '红色')
        self.ids.interval_input.text = str(cfg.get('interval', 1.0))
        self.ids.scroll_interval_input.text = str(cfg.get('scroll_interval', 2.0))
        self.ids.max_empty_cycles_input.text = str(cfg.get('max_empty_cycles', 3))
        self.ids.scroll_direction_spinner.text = (
            '上滑(看下方内容)' if cfg.get('scroll_direction', 'up') == 'up'
            else '下滑(看上方内容)'
        )
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

    def set_scroll_direction(self, text):
        if '上滑' in text:
            App.get_running_app().config_data['scroll_direction'] = 'up'
        else:
            App.get_running_app().config_data['scroll_direction'] = 'down'

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
            data['max_empty_cycles'] = int(self.ids.max_empty_cycles_input.text or '3')
        except ValueError:
            data['max_empty_cycles'] = 3
        app.save_config()
        app.show_toast('系统配置已保存')


# ============================================================
# FeatureConfigScreen - 点击特征配置
# ============================================================

class FeatureConfigScreen(Screen):
    """点击目标特征配置屏幕"""

    def on_enter(self):
        app = App.get_running_app()
        self._load_features(app.config_data.get('target_features', []))

    def _load_features(self, features):
        feature_list = self.ids.feature_list
        feature_list.clear_widgets()
        if not features:
            features = [
                {'color': '红色', 'text': '', 'enabled': True},
                {'color': '绿色', 'text': '确认', 'enabled': True},
                {'color': '蓝色', 'text': '', 'enabled': True},
            ]
        for f in features:
            row = FeatureRow(
                color=f.get('color', ''),
                text=f.get('text', ''),
                enabled=f.get('enabled', True),
            )
            row.del_btn.bind(on_press=lambda btn, r=row: self._remove_row(r))
            feature_list.add_widget(row)

    def add_feature_row(self, color='', text='', enabled=True):
        row = FeatureRow(color=color, text=text, enabled=enabled)
        row.del_btn.bind(on_press=lambda btn, r=row: self._remove_row(r))
        self.ids.feature_list.add_widget(row)

    def add_preset(self, color, text):
        self.add_feature_row(color=color, text=text, enabled=True)

    def _remove_row(self, row):
        parent = row.parent
        if parent:
            parent.remove_widget(row)

    def save_features(self):
        feature_list = self.ids.feature_list
        features = []
        for child in feature_list.children:
            if isinstance(child, FeatureRow):
                features.append(child.get_data())
        features.reverse()
        app = App.get_running_app()
        app.config_data['target_features'] = features
        app.save_config()
        app.show_toast(f'已保存 {len(features)} 条特征')

    def go_back(self):
        App.get_running_app().root.current = 'main'


# ============================================================
# MainScreen - 主控制界面
# ============================================================

class MainScreen(Screen):
    """主控制屏幕"""

    status_text = StringProperty('就绪')
    status_color = ListProperty([0.5, 0.5, 0.5, 1])
    log_text = StringProperty('')
    scroll_count = NumericProperty(0)
    last_action = StringProperty('')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._countdown_event = None
        self._countdown_value = 0
        self._log_cache = []

    def on_enter(self):
        app = App.get_running_app()
        if app.engine:
            app.engine.on_log = self._on_engine_log
            app.engine.on_state_change = self._on_engine_state
            app.engine.on_detection = self._on_engine_detection

    def start_with_countdown(self):
        app = App.get_running_app()
        if not app.engine:
            return
        if app.engine.state == AutomationEngine.RUNNING:
            app.show_toast('已在运行中')
            return
        self.ids.btn_start.disabled = True
        self.ids.btn_start.text = '等待...'
        self.ids.btn_start.background_color = (0.5, 0.5, 0.5, 1)
        countdown_label = self.ids.countdown_label
        countdown_label.opacity = 1
        self._countdown_value = 3
        countdown_label.text = str(self._countdown_value)
        self._countdown_event = Clock.schedule_interval(self._countdown_tick, 1.0)

    def _countdown_tick(self, dt):
        self._countdown_value -= 1
        label = self.ids.countdown_label
        if self._countdown_value > 0:
            label.text = str(self._countdown_value)
        else:
            label.text = '开始!'
            label.color = (0, 1, 0, 1)
            if self._countdown_event:
                self._countdown_event.cancel()
                self._countdown_event = None
            Clock.schedule_once(lambda dt2: self._do_start(), 0.5)

    def _do_start(self):
        app = App.get_running_app()
        cfg = app.config_data
        app.engine.interval = cfg.get('interval', 1.0)
        app.engine.scroll_interval = cfg.get('scroll_interval', 2.0)
        app.engine.max_empty_cycles = cfg.get('max_empty_cycles', 3)
        app.engine.scroll_direction = cfg.get('scroll_direction', 'up')
        features = cfg.get('target_features', [])
        if not features:
            features = [
                {'color': c, 'text': '', 'enabled': True}
                for c in ColorDetector.list_supported_colors()
            ]
        app.engine.set_target_features(features)
        app.start_automation()
        self.ids.countdown_label.opacity = 0
        self.ids.btn_start.disabled = False
        self.ids.btn_start.text = '开始 (3s)'
        self.ids.btn_start.background_color = (0.2, 0.8, 0.2, 1)

    def open_feature_settings(self):
        App.get_running_app().root.current = 'feature_config'

    def stop_auto(self):
        app = App.get_running_app()
        if app.engine:
            app.engine.stop()
        if self._countdown_event:
            self._countdown_event.cancel()
            self._countdown_event = None
            self.ids.countdown_label.opacity = 0
            self.ids.btn_start.disabled = False
            self.ids.btn_start.text = '开始 (3s)'
            self.ids.btn_start.background_color = (0.2, 0.8, 0.2, 1)

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
        self._log_cache = []

    def _on_engine_log(self, msg):
        self._log_cache.append(msg)
        if len(self._log_cache) > 200:
            self._log_cache = self._log_cache[-200:]
        Clock.schedule_once(lambda dt: setattr(
            self, 'log_text', '\n'.join(self._log_cache[-30:])
        ), 0)

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
            parts = []
            if color:
                parts.append(f"[{color}]")
            if text:
                parts.append(f"[{text}]")
            label = ' '.join(parts) if parts else '目标'
            self.last_action = f"检测到 {label} @ ({x},{y})"
            self._log_cache.append(f"-> 点击 ({x},{y})")
            app = App.get_running_app()
            if app.engine:
                self.scroll_count = app.engine.scroll_count
        Clock.schedule_once(update, 0)


# ============================================================
# AutoClickerApp - 主应用
# ============================================================

class AutoClickerApp(App):
    """自动点击器主应用"""

    config_data = ObjectProperty({
        'color': '红色',
        'target_features': [
            {'color': '红色', 'text': '', 'enabled': True},
            {'color': '绿色', 'text': '确认', 'enabled': True},
            {'color': '蓝色', 'text': '', 'enabled': True},
        ],
        'interval': 1.0,
        'scroll_interval': 2.0,
        'max_empty_cycles': 3,
        'scroll_direction': 'up',
        'backend': 'mock',
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
        sm.add_widget(FeatureConfigScreen(name='feature_config'))
        return sm

    def _init_components(self):
        self.color_detector = ColorDetector()
        self.ocr_engine = OCREngine(font_path=None)
        if self.ocr_engine.is_available:
            print(f"OCR 引擎可用，字体: {self.ocr_engine.font_path}")
        else:
            print("未找到中文字体，文字识别功能不可用")
        backend = self.config_data.get('backend', 'mock')
        adb_device = self.config_data.get('adb_device', '') or None
        self.screen_controller = ScreenController(
            backend=backend, adb_device=adb_device
        )
        self.engine = AutomationEngine(
            self.screen_controller, self.color_detector, self.ocr_engine
        )

    def start_automation(self):
        if not self.engine:
            return
        self.engine.start()

    def save_config(self):
        path = self._config_path()
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")

    def load_config(self):
        path = self._config_path()
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    self.config_data.update(loaded)
        except Exception as e:
            print(f"加载配置失败: {e}")

    def _config_path(self):
        data_dir = os.path.join(os.path.dirname(__file__), 'data')
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, 'config.json')

    def show_toast(self, message, duration=2):
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
