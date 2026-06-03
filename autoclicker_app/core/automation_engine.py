"""
自动化引擎
核心循环：截图 → 特征匹配(颜色+文字) → 点击 → 翻页
支持多特征配置、事件回调、线程控制
点击完成后自动翻页，直到无法翻页时停止
"""

import time
import threading
from collections import deque


class AutomationEngine:
    """自动化引擎，运行在独立线程中"""

    IDLE = 'idle'
    RUNNING = 'running'
    PAUSED = 'paused'
    STOPPED = 'stopped'

    def __init__(self, screen_controller, color_detector, ocr_engine):
        self.screen = screen_controller
        self.color_detector = color_detector
        self.ocr = ocr_engine
        self._thread = None
        self._state = self.IDLE
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self.interval = 1.0
        self.scroll_interval = 2.0
        self.scroll_percent = 0.4
        self.scroll_direction = 'up'
        self.max_empty_cycles = 3
        self.target_features = []
        self._scroll_count = 0
        self._last_action = ''
        self._log_buffer = deque(maxlen=500)
        self._last_clicks = []
        self._empty_cycles = 0
        self.on_log = None
        self.on_state_change = None
        self.on_detection = None
        self.on_screenshot = None

    @property
    def state(self):
        with self._lock:
            return self._state

    @state.setter
    def state(self, value):
        with self._lock:
            old = self._state
            self._state = value
        if old != value and self.on_state_change:
            self.on_state_change(value)

    @property
    def scroll_count(self):
        return self._scroll_count

    def set_target_features(self, features):
        self.target_features = [
            f for f in features
            if f.get('enabled', True) and (f.get('color') or f.get('text'))
        ]

    def log(self, msg):
        self._log_buffer.append(msg)
        if self.on_log:
            self.on_log(msg)

    def get_logs(self, count=50):
        return list(self._log_buffer)[-count:]

    def start(self):
        with self._lock:
            if self._state == self.RUNNING:
                self.log("已经在运行中")
                return
            self._state = self.RUNNING
            self._stop_event.clear()
            self._scroll_count = 0
            self._last_clicks = []
            self._empty_cycles = 0
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self.log("自动化已启动")
        if self.on_state_change:
            self.on_state_change(self.RUNNING)

    def stop(self):
        self._stop_event.set()
        with self._lock:
            self._state = self.STOPPED
        self.log("自动化已停止")
        if self.on_state_change:
            self.on_state_change(self.STOPPED)

    def pause(self):
        with self._lock:
            self._state = self.PAUSED
        self.log("自动化已暂停")
        if self.on_state_change:
            self.on_state_change(self.PAUSED)

    def resume(self):
        with self._lock:
            self._state = self.RUNNING
        self.log("自动化已恢复")
        if self.on_state_change:
            self.on_state_change(self.RUNNING)

    def wait_for_completion(self, timeout=None):
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout)

    def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                with self._lock:
                    if self._state == self.PAUSED:
                        time.sleep(0.5)
                        continue
                    if self._state != self.RUNNING:
                        break
                found_any = self._do_cycle()
                if not found_any:
                    self._empty_cycles += 1
                    self.log(f"未找到目标 ({self._empty_cycles}/{self.max_empty_cycles})")
                    if self._empty_cycles >= self.max_empty_cycles:
                        self.log("连续多次未找到目标，已到达内容底部，任务完成")
                        self.stop()
                        return
                else:
                    self._empty_cycles = 0
                for _ in range(int(self.interval / 0.1)):
                    if self._stop_event.is_set():
                        return
                    time.sleep(0.1)
            except Exception as e:
                self.log(f"循环异常: {e}")
                time.sleep(1)

    def _do_cycle(self):
        try:
            img = self.screen.screenshot()
        except Exception as e:
            self.log(f"截图失败: {e}")
            return False
        if self.on_screenshot:
            self.on_screenshot(img)
        total_clicked = 0
        for feature in self.target_features:
            if self._stop_event.is_set():
                return total_clicked > 0
            color = feature.get('color', '')
            text = feature.get('text', '')
            try:
                matched_regions = self._find_matching_regions(img, color, text)
            except Exception as e:
                self.log(f"特征匹配异常(color={color}, text={text}): {e}")
                continue
            if not matched_regions:
                continue
            new_regions = []
            for rect in matched_regions:
                cx = rect[0] + rect[2] // 2
                cy = rect[1] + rect[3] // 2
                if not self._is_duplicate(cx, cy):
                    new_regions.append(rect)
            if not new_regions:
                self.log(f"[{color or '任意色'}][{text or '任意文'}] 色块已全部点击，跳过")
                continue
            label_parts = []
            if color:
                label_parts.append(color)
            if text:
                label_parts.append(f"「{text}」")
            label = ' '.join(label_parts) if label_parts else '目标'
            self.log(f"发现 {len(new_regions)} 个 {label} 匹配")
            for i, rect in enumerate(new_regions):
                if self._stop_event.is_set():
                    return total_clicked > 0
                cx = rect[0] + rect[2] // 2
                cy = rect[1] + rect[3] // 2
                self.log(f"点击 {label} ({i + 1}/{len(new_regions)}) @ ({cx},{cy})")
                if self.on_detection:
                    self.on_detection(color, text, cx, cy)
                self.screen.click(cx, cy)
                self._last_clicks.append((cx, cy))
                if len(self._last_clicks) > 50:
                    self._last_clicks = self._last_clicks[-50:]
                self._last_action = f"点击 {label}"
                total_clicked += 1
                time.sleep(0.3)
        if total_clicked > 0:
            self._scroll_count += 1
            self.log(f"翻页 ({self._scroll_count})")
            self._do_scroll()
            self._last_action = '翻页'
            time.sleep(self.scroll_interval)
            return True
        self._scroll_count += 1
        self.log(f"尝试翻页寻找目标 ({self._scroll_count})")
        self._do_scroll()
        time.sleep(self.scroll_interval)
        try:
            img2 = self.screen.screenshot()
            for feature in self.target_features:
                if self._stop_event.is_set():
                    break
                color = feature.get('color', '')
                text = feature.get('text', '')
                matched = self._find_matching_regions(img2, color, text)
                new_regions = []
                for rect in matched:
                    cx = rect[0] + rect[2] // 2
                    cy = rect[1] + rect[3] // 2
                    if not self._is_duplicate(cx, cy):
                        new_regions.append(rect)
                if new_regions:
                    self.log(f"翻页后发现 {len(new_regions)} 个新目标，将在下一轮点击")
                    return True
        except Exception:
            pass
        return False

    def _find_matching_regions(self, img, color, text):
        matched = []
        if color:
            regions = self.color_detector.find_regions(img, color, min_region=60)
            if text:
                for rect in regions:
                    texts_in_region = self.ocr.find_text_in_region(img, rect)
                    for t, conf, _ in texts_in_region:
                        if self.ocr.fuzzy_match(t, text):
                            matched.append(rect)
                            break
            else:
                matched = regions
        elif text:
            text_matches = self.ocr.find_text(img, [text])
            for t, conf, (x, y, w, h) in text_matches:
                pad_x, pad_y = 10, 5
                matched.append((
                    max(0, x - pad_x),
                    max(0, y - pad_y),
                    w + pad_x * 2,
                    h + pad_y * 2,
                ))
        return matched

    def _do_scroll(self):
        if self.scroll_direction == 'down':
            self.screen.scroll_down(self.scroll_percent)
        else:
            self.screen.scroll_up(self.scroll_percent)

    def _is_duplicate(self, x, y, threshold=50):
        for lx, ly in self._last_clicks[-30:]:
            if abs(x - lx) + abs(y - ly) < threshold:
                return True
        return False
