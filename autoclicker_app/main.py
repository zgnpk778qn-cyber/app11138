"""
Simple AutoClicker - 自动检测屏幕上的色块并点击
"""
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.clock import Clock
from kivy.lang import Builder
from PIL import Image
from io import BytesIO
import subprocess
import threading
import time
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
        height: 48
        Label:
            text: 'Max Clicks/cycle:'
            size_hint_x: 0.35
        TextInput:
            id: max_clicks_ti
            text: '5'
            multiline: False
            size_hint_x: 0.65

    BoxLayout:
        size_hint_y: None
        height: 56
        spacing: 10
        Button:
            id: btn_start
            text: 'START (3s)'
            on_press: app.start_countdown()
            background_color: 0.2, 0.7, 0.2, 1
        Button:
            text: 'STOP'
            on_press: app.stop()
            background_color: 0.7, 0.2, 0.2, 1

    Label:
        id: status_lbl
        text: 'Ready'
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

# Simple RGB color ranges (lo, hi)
COLOR_RANGES = {
    'Red':    ((180, 0, 0),   (255, 90, 90)),
    'Green':  ((0, 140, 0),   (120, 255, 120)),
    'Blue':   ((0, 0, 180),   (100, 100, 255)),
    'Yellow': ((200, 180, 0), (255, 255, 100)),
    'White':  ((190, 190, 190), (255, 255, 255)),
}


class AutoClickerApp(App):
    def build(self):
        self.running = False
        self.thread = None
        self.click_count = 0
        self._logs = []
        return Builder.load_string(KV)

    def log(self, msg):
        self._logs.append(msg)
        if len(self._logs) > 40:
            self._logs = self._logs[-40:]
        Clock.schedule_once(lambda dt: setattr(
            self.root.ids.log_lbl, 'text', '\n'.join(self._logs)), 0)

    def start_countdown(self):
        if self.running:
            return
        btn = self.root.ids.btn_start
        btn.disabled = True
        btn.text = '3...'
        Clock.schedule_once(lambda dt: setattr(btn, 'text', '2...'), 1)
        Clock.schedule_once(lambda dt: setattr(btn, 'text', '1...'), 2)
        Clock.schedule_once(self._do_start, 3)

    def _do_start(self, dt=None):
        self.running = True
        btn = self.root.ids.btn_start
        btn.text = 'RUNNING'
        btn.disabled = False
        self.root.ids.status_lbl.text = 'Status: RUNNING'
        self.log('Started')
        self.click_count = 0
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        self.root.ids.status_lbl.text = 'Status: Stopped'
        self.root.ids.btn_start.text = 'START (3s)'
        self.log(f'Stopped — total clicks: {self.click_count}')

    # ---- core logic (runs in background thread) ----

    def _run_loop(self):
        color = self.root.ids.color_sp.text
        try:
            interval = float(self.root.ids.interval_ti.text)
        except ValueError:
            interval = 1.5
        try:
            max_clicks = int(self.root.ids.max_clicks_ti.text)
        except ValueError:
            max_clicks = 5

        while self.running:
            try:
                img = self._screenshot()
                regions = self._find_color(img, color)
                clicked = 0
                for rx, ry, rw, rh in regions:
                    if not self.running:
                        return
                    if clicked >= max_clicks:
                        break
                    cx, cy = rx + rw // 2, ry + rh // 2
                    self._tap(cx, cy)
                    clicked += 1
                    self.click_count += 1
                    self.log(f'Clicked ({cx},{cy}) #{self.click_count}')
                    time.sleep(0.3)

                if clicked == 0:
                    self._scroll()
                    self.log('Scrolled (no targets found)')
                else:
                    time.sleep(interval)
                    self._scroll()
                    self.log(f'Scrolled — {clicked} clicks this cycle')
            except Exception as e:
                self.log(f'Error: {e}')
                time.sleep(2)

    def _screenshot(self):
        """Take screenshot via Android screencap"""
        r = subprocess.run(['screencap', '-p'], capture_output=True, timeout=10)
        return Image.open(BytesIO(r.stdout)).convert('RGB')

    def _find_color(self, img, color_name):
        """Find regions matching the target color (grid scan + merge)"""
        lo, hi = COLOR_RANGES.get(color_name, COLOR_RANGES['Red'])
        px = img.load()
        w, h = img.size
        step = 15  # scan stride for performance
        hits = []
        for y in range(0, h - step, step):
            for x in range(0, w - step, step):
                # sample center of each cell
                r, g, b = px[x + step // 2, y + step // 2]
                if lo[0] <= r <= hi[0] and lo[1] <= g <= hi[1] and lo[2] <= b <= hi[2]:
                    hits.append((x, y, step, step))
        # simple greedy merge of overlapping cells
        return self._merge(hits, gap=step * 2)

    def _merge(self, rects, gap=30):
        """Merge nearby rectangles"""
        if len(rects) < 2:
            return rects
        # convert to (x1,y1,x2,y2)
        boxes = [(x, y, x + w, y + h) for x, y, w, h in rects]
        merged = True
        while merged:
            merged = False
            out = []
            used = [False] * len(boxes)
            for i, (x1, y1, x2, y2) in enumerate(boxes):
                if used[i]:
                    continue
                for j, (rx1, ry1, rx2, ry2) in enumerate(boxes[i + 1:], i + 1):
                    if used[j]:
                        continue
                    # check overlap or proximity
                    ox = max(0, max(x1, rx1) - min(x2, rx2))
                    oy = max(0, max(y1, ry1) - min(y2, ry2))
                    if ox <= gap and oy <= gap:
                        x1 = min(x1, rx1)
                        y1 = min(y1, ry1)
                        x2 = max(x2, rx2)
                        y2 = max(y2, ry2)
                        used[j] = True
                        merged = True
                out.append((x1, y1, x2, y2))
                used[i] = True
            boxes = out
        return [(x1, y1, x2 - x1, y2 - y1) for x1, y1, x2, y2 in boxes]

    def _tap(self, x, y):
        subprocess.run(['input', 'tap', str(int(x)), str(int(y))],
                       capture_output=True, timeout=5)

    def _scroll(self):
        """Swipe up to scroll content (from 60%→25% screen height)"""
        subprocess.run(
            ['input', 'swipe', '540', '1100', '540', '350', '400'],
            capture_output=True, timeout=5)


if __name__ == '__main__':
    AutoClickerApp().run()
