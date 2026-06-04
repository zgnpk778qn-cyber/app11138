"""
AutoClicker — UI 控制面板
"""
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.clock import Clock
from kivy.lang import Builder
import os

KV = '''
BoxLayout:
    orientation: 'vertical'
    padding: 12
    spacing: 6

    # ---- 标题 ----
    Label:
        text: 'AutoClicker'
        font_size: '22sp'
        size_hint_y: None
        height: 40

    # ---- 颜色 ----
    BoxLayout:
        size_hint_y: None
        height: 44
        Label:
            text: '颜色:'
            size_hint_x: 0.3
        Spinner:
            id: color_sp
            text: '红'
            values: ['红', '绿', '蓝', '黄', '白']
            size_hint_x: 0.7

    # ---- 文字 ----
    BoxLayout:
        size_hint_y: None
        height: 44
        Label:
            text: '文字:'
            size_hint_x: 0.3
        TextInput:
            id: text_ti
            text: ''
            multiline: False
            hint_text: '是/否/对/错/yes/no/和/或'
            size_hint_x: 0.7

    # ---- 关联模式 ----
    BoxLayout:
        size_hint_y: None
        height: 44
        Label:
            text: '关联:'
            size_hint_x: 0.3
        Spinner:
            id: mode_sp
            text: '无'
            values: ['无', '和', '或']
            size_hint_x: 0.7
            # 无=仅颜色  和=颜色+文字  或=颜色或文字

    # ---- 间隔 ----
    BoxLayout:
        size_hint_y: None
        height: 44
        Label:
            text: '间隔(s):'
            size_hint_x: 0.3
        TextInput:
            id: interval_ti
            text: '1.5'
            multiline: False
            size_hint_x: 0.7

    # ---- 按钮 ----
    BoxLayout:
        size_hint_y: None
        height: 52
        spacing: 10
        Button:
            id: btn_start
            text: 'START'
            on_press: app.toggle_service()
            background_color: 0.2, 0.7, 0.2, 1

    # ---- 状态 ----
    Label:
        id: status_lbl
        text: 'Stopped'
        size_hint_y: None
        height: 28
        font_size: '13sp'

    # ---- 日志 ----
    Label:
        id: log_lbl
        text: ''
        text_size: self.width, None
        size_hint_y: None
        height: max(180, self.texture_size[1])
'''

CFG = '/data/data/org.autoclicker.autoclicker/files/service_cfg.txt'
LOG = CFG + '.log'


class AutoClickerApp(App):

    def build(self):
        return Builder.load_string(KV)

    def on_start(self):
        self.root.ids.color_sp.bind(text=self._write_cfg)
        self.root.ids.text_ti.bind(text=self._write_cfg)
        self.root.ids.mode_sp.bind(text=self._write_cfg)
        self.root.ids.interval_ti.bind(text=self._write_cfg)
        Clock.schedule_interval(self._read_log, 2)

    def toggle_service(self):
        btn = self.root.ids.btn_start
        if btn.text == 'START':
            self._start()
        else:
            self._stop()

    def _start(self):
        self._write_cfg()
        try:
            from jnius import autoclass
            cls = autoclass('org.autoclicker.autoclicker.ServiceAutoclicker')
            mActivity = autoclass('org.kivy.android.PythonActivity').mActivity
            intent = autoclass('android.content.Intent')(mActivity, cls)
            mActivity.startService(intent)
            btn = self.root.ids.btn_start
            btn.text = 'STOP'
            btn.background_color = (0.7, 0.2, 0.2, 1)
            self.root.ids.status_lbl.text = 'RUNNING (background)'
        except Exception as e:
            self.root.ids.status_lbl.text = f'Start err: {e}'

    def _stop(self):
        self._write_cfg(cmd='stop')
        try:
            from jnius import autoclass
            cls = autoclass('org.autoclicker.autoclicker.ServiceAutoclicker')
            mActivity = autoclass('org.kivy.android.PythonActivity').mActivity
            intent = autoclass('android.content.Intent')(mActivity, cls)
            mActivity.stopService(intent)
        except Exception:
            pass
        btn = self.root.ids.btn_start
        btn.text = 'START'
        btn.background_color = (0.2, 0.7, 0.2, 1)
        self.root.ids.status_lbl.text = 'Stopped'

    def _write_cfg(self, *args, cmd='start'):
        try:
            color = self.root.ids.color_sp.text
            text_val = self.root.ids.text_ti.text.strip()
            mode = self.root.ids.mode_sp.text
            interval = self.root.ids.interval_ti.text
            with open(CFG, 'w') as f:
                f.write(f'cmd={cmd}\n')
                f.write(f'color={color}\n')
                f.write(f'target_text={text_val}\n')
                f.write(f'match_mode={mode}\n')
                f.write(f'interval={interval}\n')
        except Exception:
            pass

    def _read_log(self, dt):
        try:
            if os.path.exists(LOG):
                with open(LOG) as f:
                    lines = f.readlines()[-25:]
                self.root.ids.log_lbl.text = ''.join(lines)
        except Exception:
            pass


if __name__ == '__main__':
    AutoClickerApp().run()
