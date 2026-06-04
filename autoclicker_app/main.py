"""
AutoClicker - UI 控制面板，启动/停止后台自动点击服务
"""
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.clock import Clock
from kivy.lang import Builder
import os

KV = '''
BoxLayout:
    orientation: 'vertical'
    padding: 12
    spacing: 8

    Label:
        text: 'AutoClicker'
        font_size: '22sp'
        size_hint_y: None
        height: 44

    BoxLayout:
        size_hint_y: None
        height: 48
        Label:
            text: 'Target Color:'
            size_hint_x: 0.35
        Spinner:
            id: color_sp
            text: 'Red'
            values: ['Red', 'Green', 'Blue', 'Yellow', 'White']
            size_hint_x: 0.65

    BoxLayout:
        size_hint_y: None
        height: 48
        Label:
            text: 'Interval (s):'
            size_hint_x: 0.35
        TextInput:
            id: interval_ti
            text: '1.5'
            multiline: False
            size_hint_x: 0.65

    BoxLayout:
        size_hint_y: None
        height: 56
        spacing: 10
        Button:
            id: btn_start
            text: 'START'
            on_press: app.toggle_service()
            background_color: 0.2, 0.7, 0.2, 1
        Button:
            text: 'OPEN ACCESSIBILITY'
            on_press: app.open_accessibility()
            background_color: 0.2, 0.4, 0.7, 1

    Label:
        id: status_lbl
        text: 'Status: Stopped'
        size_hint_y: None
        height: 30
        font_size: '14sp'

    Label:
        id: log_lbl
        text: ''
        text_size: self.width, None
        size_hint_y: None
        height: max(200, self.texture_size[1])
'''

CFG = '/data/data/org.autoclicker.autoclicker/files/service_cfg.txt'
LOG = CFG + '.log'


class AutoClickerApp(App):

    def build(self):
        self._poll_event = None
        return Builder.load_string(KV)

    def on_start(self):
        self.root.ids.color_sp.bind(text=self._write_cfg)
        self.root.ids.interval_ti.bind(text=self._write_cfg)
        Clock.schedule_interval(self._read_log, 2)

    def toggle_service(self):
        btn = self.root.ids.btn_start
        if btn.text == 'START':
            self._start_service()
        else:
            self._stop_service()

    def _start_service(self):
        self._write_cfg()
        try:
            from jnius import autoclass
            service_name = 'org.autoclicker.autoclicker.ServiceAutoclicker'
            mActivity = autoclass('org.kivy.android.PythonActivity').mActivity
            service_intent = autoclass('android.content.Intent')(mActivity,
                autoclass(service_name))
            mActivity.startService(service_intent)
            self.root.ids.btn_start.text = 'STOP'
            self.root.ids.btn_start.background_color = (0.7, 0.2, 0.2, 1)
            self.root.ids.status_lbl.text = 'Status: RUNNING (background)'
        except Exception as e:
            self.root.ids.status_lbl.text = f'Start failed: {e}'

    def _stop_service(self):
        self._write_cfg(cmd='stop')
        try:
            from jnius import autoclass
            mActivity = autoclass('org.kivy.android.PythonActivity').mActivity
            service_intent = autoclass('android.content.Intent')(
                mActivity,
                autoclass('org.autoclicker.autoclicker.ServiceAutoclicker')
            )
            mActivity.stopService(service_intent)
        except Exception:
            pass
        self.root.ids.btn_start.text = 'START'
        self.root.ids.btn_start.background_color = (0.2, 0.7, 0.2, 1)
        self.root.ids.status_lbl.text = 'Status: Stopped'

    def _write_cfg(self, *args, cmd='start'):
        try:
            color = self.root.ids.color_sp.text
            interval = self.root.ids.interval_ti.text
            with open(CFG, 'w') as f:
                f.write(f'cmd={cmd}\n')
                f.write(f'color={color}\n')
                f.write(f'interval={interval}\n')
        except Exception:
            pass  # not on Android yet

    def _read_log(self, dt):
        try:
            if os.path.exists(LOG):
                with open(LOG) as f:
                    lines = f.readlines()[-30:]
                self.root.ids.log_lbl.text = ''.join(lines)
        except Exception:
            pass

    def open_accessibility(self):
        try:
            from jnius import autoclass
            Intent = autoclass('android.content.Intent')
            Settings = autoclass('android.provider.Settings')
            mActivity = autoclass('org.kivy.android.PythonActivity').mActivity
            intent = Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)
            mActivity.startActivity(intent)
        except Exception:
            self.root.ids.status_lbl.text = 'Cannot open settings'


if __name__ == '__main__':
    AutoClickerApp().run()
