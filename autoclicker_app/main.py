"""
AutoClicker
"""
from kivy.app import App
from kivy.clock import Clock
from kivy.lang import Builder
import os

KV = '''
#:import dp kivy.metrics.dp

<Module@BoxLayout>:
    orientation: 'vertical'
    size_hint_y: None
    height: self.minimum_height + dp(16)
    padding: dp(12), dp(10)
    spacing: dp(6)
    canvas.before:
        Color:
            rgba: 0.1, 0.1, 0.12, 1
        Rectangle:
            pos: self.pos
            size: self.size

<SecTitle@Label>:
    size_hint_y: None
    height: dp(20)
    font_size: '11sp'
    bold: True
    color: 0.4, 0.7, 1, 1

<Row@BoxLayout>:
    size_hint_y: None
    height: dp(42)
    spacing: dp(8)

<Lbl@Label>:
    size_hint_x: 0.32
    halign: 'right'
    valign: 'middle'
    text_size: self.width, self.height
    font_size: '13sp'
    color: 0.75, 0.75, 0.75, 1

ScrollView:
    BoxLayout:
        orientation: 'vertical'
        padding: dp(14)
        spacing: dp(12)
        size_hint_y: None
        height: self.minimum_height

        # ====== STATUS ======
        Module:
            SecTitle:
                text: 'STATUS'
            Label:
                id: status_lbl
                text: 'Stopped'
                font_size: '18sp'
                size_hint_y: None
                height: dp(32)
                halign: 'center'

        # ====== TARGET ======
        Module:
            SecTitle:
                text: 'TARGET'
            Row:
                Lbl:
                    text: 'Color:'
                Spinner:
                    id: color_sp
                    text: 'Red'
                    values: ['Red', 'Green', 'Blue', 'Yellow', 'White']
                    size_hint_x: 0.68
            Row:
                Lbl:
                    text: 'Text:'
                TextInput:
                    id: text_ti
                    text: ''
                    multiline: False
                    hint_text: '(empty = ignore)'
                    size_hint_x: 0.68
                    padding_y: dp(8)
            Row:
                Lbl:
                    text: 'Match:'
                Spinner:
                    id: mode_sp
                    text: 'OR'
                    values: ['OR', 'AND', 'OFF']
                    size_hint_x: 0.68

        # ====== TIMING ======
        Module:
            SecTitle:
                text: 'TIMING'
            Row:
                Lbl:
                    text: 'Interval (s):'
                TextInput:
                    id: interval_ti
                    text: '1.5'
                    multiline: False
                    size_hint_x: 0.68
                    padding_y: dp(8)

        # ====== CONTROL ======
        Module:
            SecTitle:
                text: 'CONTROL'
            Button:
                id: btn_start
                text: 'START'
                on_press: app.toggle()
                size_hint_y: None
                height: dp(48)
                background_color: 0.2, 0.75, 0.2, 1
                font_size: '17sp'

        # ====== LOG ======
        Module:
            SecTitle:
                text: 'LOG'
            Label:
                id: log_lbl
                text: ''
                text_size: self.width - dp(4), None
                size_hint_y: None
                height: max(dp(150), self.texture_size[1])
                font_size: '10sp'
                color: 0.5, 0.5, 0.5, 1
                valign: 'bottom'
                halign: 'left'
'''

CFG = '/data/data/org.autoclicker.autoclicker/files/service_cfg.txt'
LOG = CFG + '.log'
MODE_MAP = {'OR': '或', 'AND': '和', 'OFF': '无'}


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
            self.root.ids.btn_start.text = 'STOP'
            self.root.ids.btn_start.background_color = (0.75, 0.2, 0.2, 1)
            self.root.ids.status_lbl.text = 'RUNNING'
        except Exception as e:
            self.root.ids.status_lbl.text = f'Error: {e}'

    def _stop(self):
        self._write(cmd='stop')
        try:
            from jnius import autoclass
            cls = autoclass('org.autoclicker.autoclicker.ServiceAutoclicker')
            a = autoclass('org.kivy.android.PythonActivity').mActivity
            a.stopService(autoclass('android.content.Intent')(a, cls))
        except Exception:
            pass
        self.root.ids.btn_start.text = 'START'
        self.root.ids.btn_start.background_color = (0.2, 0.75, 0.2, 1)
        self.root.ids.status_lbl.text = 'Stopped'

    def _write(self, *args, cmd='start'):
        try:
            ids = self.root.ids
            with open(CFG, 'w') as f:
                f.write(f'cmd={cmd}\n')
                f.write(f'color={ids.color_sp.text}\n')
                f.write(f'target_text={ids.text_ti.text.strip()}\n')
                f.write(f'match_mode={MODE_MAP.get(ids.mode_sp.text, "无")}\n')
                f.write(f'interval={ids.interval_ti.text}\n')
        except Exception:
            pass

    def _read_log(self, dt):
        try:
            if os.path.exists(LOG):
                with open(LOG) as f:
                    self.root.ids.log_lbl.text = ''.join(f.readlines()[-20:])
        except Exception:
            pass


if __name__ == '__main__':
    AutoClickerApp().run()
