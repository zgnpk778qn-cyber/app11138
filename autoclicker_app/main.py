"""
AutoClicker
"""
from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
import os

KV = '''
ScrollView:
    BoxLayout:
        orientation: 'vertical'
        padding: 14
        spacing: 8
        size_hint_y: None
        height: self.minimum_height

        # ---- 标题 + 状态 ----
        Label:
            text: 'AutoClicker'
            font_size: '20sp'
            size_hint_y: None
            height: 36
            halign: 'center'

        Label:
            id: status_lbl
            text: '●  Stopped'
            font_size: '13sp'
            size_hint_y: None
            height: 24
            halign: 'center'

        # ---- 颜色 ----
        BoxLayout:
            size_hint_y: None
            height: 42
            Label:
                text: 'Color:'
                size_hint_x: 0.28
                halign: 'right'
                text_size: self.width, None
            Spinner:
                id: color_sp
                text: 'Red'
                values: ['Red', 'Green', 'Blue', 'Yellow', 'White']
                size_hint_x: 0.72

        # ---- 文字 + 关联模式 同行 ----
        BoxLayout:
            size_hint_y: None
            height: 42
            spacing: 6
            Label:
                text: 'Text:'
                size_hint_x: 0.16
                halign: 'right'
                text_size: self.width, None
            TextInput:
                id: text_ti
                text: ''
                multiline: False
                hint_text: '(empty=off)'
                size_hint_x: 0.42
                padding_y: 8
            Label:
                text: '|'
                size_hint_x: 0.04
                halign: 'center'
                text_size: self.width, None
            Spinner:
                id: mode_sp
                text: 'OR'
                values: ['OR', 'AND', 'OFF']
                size_hint_x: 0.38

        # ---- 间隔 ----
        BoxLayout:
            size_hint_y: None
            height: 42
            Label:
                text: 'Interval (s):'
                size_hint_x: 0.5
                halign: 'right'
                text_size: self.width, None
            TextInput:
                id: interval_ti
                text: '1.5'
                multiline: False
                size_hint_x: 0.5
                padding_y: 8

        # ---- 按钮 ----
        Button:
            id: btn_start
            text: 'START'
            on_press: app.toggle()
            size_hint_y: None
            height: 50
            background_color: 0.2, 0.7, 0.2, 1
            font_size: '18sp'

        # ---- 日志 ----
        Label:
            text: '——— Log ———'
            font_size: '11sp'
            size_hint_y: None
            height: 20
            halign: 'center'
            color: 0.5, 0.5, 0.5, 1

        Label:
            id: log_lbl
            text: ''
            text_size: self.width - 10, None
            size_hint_y: None
            height: max(120, self.texture_size[1])
            font_size: '10sp'
            color: 0.6, 0.6, 0.6, 1
            valign: 'bottom'
'''

CFG = '/data/data/org.autoclicker.autoclicker/files/service_cfg.txt'
LOG = CFG + '.log'


class AutoClickerApp(App):

    def build(self):
        return Builder.load_string(KV)

    def on_start(self):
        ids = self.root.ids
        ids.color_sp.bind(text=self._write)
        ids.text_ti.bind(text=self._write)
        ids.mode_sp.bind(text=self._write)
        ids.interval_ti.bind(text=self._write)
        Clock.schedule_interval(self._read_log, 2)

    def toggle(self):
        btn = self.root.ids.btn_start
        if btn.text == 'START':
            self._start()
        else:
            self._stop()

    def _start(self):
        self._write()
        try:
            from jnius import autoclass
            cls = autoclass('org.autoclicker.autoclicker.ServiceAutoclicker')
            a = autoclass('org.kivy.android.PythonActivity').mActivity
            a.startService(autoclass('android.content.Intent')(a, cls))
            b = self.root.ids.btn_start
            b.text = 'STOP'
            b.background_color = (0.7, 0.2, 0.2, 1)
            self.root.ids.status_lbl.text = '●  RUNNING'
        except Exception as e:
            self.root.ids.status_lbl.text = f'Err: {e}'

    def _stop(self):
        self._write(cmd='stop')
        try:
            from jnius import autoclass
            cls = autoclass('org.autoclicker.autoclicker.ServiceAutoclicker')
            a = autoclass('org.kivy.android.PythonActivity').mActivity
            a.stopService(autoclass('android.content.Intent')(a, cls))
        except Exception:
            pass
        b = self.root.ids.btn_start
        b.text = 'START'
        b.background_color = (0.2, 0.7, 0.2, 1)
        self.root.ids.status_lbl.text = '●  Stopped'

    def _write(self, *args, cmd='start'):
        try:
            ids = self.root.ids
            mode_map = {'OR': '或', 'AND': '和', 'OFF': '无'}
            with open(CFG, 'w') as f:
                f.write(f'cmd={cmd}\n')
                f.write(f'color={ids.color_sp.text}\n')
                f.write(f'target_text={ids.text_ti.text.strip()}\n')
                f.write(f'match_mode={mode_map.get(ids.mode_sp.text, "无")}\n')
                f.write(f'interval={ids.interval_ti.text}\n')
        except Exception:
            pass

    def _read_log(self, dt):
        try:
            if os.path.exists(LOG):
                with open(LOG) as f:
                    lines = f.readlines()[-20:]
                self.root.ids.log_lbl.text = ''.join(lines)
        except Exception:
            pass


if __name__ == '__main__':
    AutoClickerApp().run()
