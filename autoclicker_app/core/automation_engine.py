"""
自动化引擎
核心循环：截图 → 检测 → 点击 → 翻页
支持多目标配置、事件回调、线程控制
"""

import time
import threading
from collections import deque


class AutomationEngine:
    """自动化引擎，运行在独立线程中"""

    # 状态常量
    IDLE = 'idle'
    RUNNING = 'running'
    PAUSED = 'paused'
    STOPPED = 'stopped'

    def __init__(self, screen_controller, color_detector, ocr_engine):
        """
        参数:
            screen_controller: ScreenController 实例
            color_detector:    ColorDetector 实例
            ocr_engine:        OCREngine 实例
        """
        self.screen = screen_controller
        self.color_detector = color_detector
        self.ocr = ocr_engine

        self._thread = None
        self._state = self.IDLE
        self._lock = threading.Lock()
        self._stop_event = threading.Event()

        # 配置参数
        self.interval = 1.0           # 检测间隔（秒）
        self.scroll_interval = 2.0    # 翻页间隔（秒）
        self.scroll_percent = 0.4     # 翻页比例
        self.max_scrolls = 50         # 最大翻页次数
        self.target_colors = ['红色', '绿色', '蓝色']  # 目标颜色
        self.target_texts = ['确认', '是', '否', '对', '错', '完成', '未完成']
        self.click_center = True       # 是否点击区域中心

        # 运行时数据
        self._scroll_count = 0
        self._last_action = ''
        self._log_buffer = deque(maxlen=500)
        self._last_clicks = []  # 去重用，记录近期点击坐标

        # 事件回调
        self.on_log = None            # callback(msg)
        self.on_state_change = None   # callback(state)
        self.on_detection = None      # callback(color, text, x, y)
        self.on_screenshot = None     # callback(image)

    # ── 属性 ────────────────────────────────────────────

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

    # ── 日志 ────────────────────────────────────────────

    def log(self, msg):
        self._log_buffer.append(msg)
        if self.on_log:
            self.on_log(msg)

    def get_logs(self, count=50):
        return list(self._log_buffer)[-count:]

    # ── 生命周期 ────────────────────────────────────────

    def start(self):
        """启动自动化循环"""
        with self._lock:
            if self._state == self.RUNNING:
                self.log("已经在运行中")
                return
            self._state = self.RUNNING
            self._stop_event.clear()
            self._scroll_count = 0
            self._last_clicks = []

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self.log("自动化已启动")

        if self.on_state_change:
            self.on_state_change(self.RUNNING)

    def stop(self):
        """停止自动化"""
        self._stop_event.set()
        with self._lock:
            self._state = self.STOPPED
        self.log("自动化已停止")
        if self.on_state_change:
            self.on_state_change(self.STOPPED)

    def pause(self):
        """暂停自动化"""
        with self._lock:
            self._state = self.PAUSED
        self.log("自动化已暂停")
        if self.on_state_change:
            self.on_state_change(self.PAUSED)

    def resume(self):
        """恢复自动化"""
        with self._lock:
            self._state = self.RUNNING
        self.log("自动化已恢复")
        if self.on_state_change:
            self.on_state_change(self.RUNNING)

    def wait_for_completion(self, timeout=None):
        """等待自动化线程结束"""
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout)

    # ── 核心循环 ────────────────────────────────────────

    def _run_loop(self):
        """自动化主循环"""
        while not self._stop_event.is_set():
            try:
                with self._lock:
                    if self._state == self.PAUSED:
                        time.sleep(0.5)
                        continue
                    if self._state != self.RUNNING:
                        break

                self._do_cycle()

                # 间隔等待（支持中途停止）
                for _ in range(int(self.interval / 0.1)):
                    if self._stop_event.is_set():
                        return
                    time.sleep(0.1)

            except Exception as e:
                self.log(f"循环异常: {e}")
                time.sleep(1)

    def _do_cycle(self):
        """执行一轮：截图 → 找到所有色块 → 全部点击 → 翻页 → 继续"""
        try:
            img = self.screen.screenshot()
        except Exception as e:
            self.log(f"截图失败: {e}")
            return

        if self.on_screenshot:
            self.on_screenshot(img)

        # 按优先级遍历目标颜色
        for color in self.target_colors:
            try:
                regions = self.color_detector.find_regions(img, color, min_region=80)

                if regions:
                    # 去重：过滤与近期点击位置重叠的色块
                    new_regions = []
                    for rect in regions:
                        cx = rect[0] + rect[2] // 2
                        cy = rect[1] + rect[3] // 2
                        if not self._is_duplicate(cx, cy):
                            new_regions.append(rect)

                    if not new_regions:
                        self.log(f"{color} 色块已全部点击，跳过")
                        continue

                    # 点击所有找到的色块
                    self.log(f"发现 {len(new_regions)} 个 {color} 色块")
                    for i, rect in enumerate(new_regions):
                        if self._stop_event.is_set():
                            return
                        cx = rect[0] + rect[2] // 2
                        cy = rect[1] + rect[3] // 2

                        self.log(f"点击 {color} ({i+1}/{len(new_regions)}) @ ({cx},{cy})")
                        if self.on_detection:
                            self.on_detection(color, '', cx, cy)

                        self.screen.click(cx, cy)
                        self._last_clicks.append((cx, cy))
                        if len(self._last_clicks) > 50:
                            self._last_clicks = self._last_clicks[-50:]

                        self._last_action = f"点击 {color}"
                        time.sleep(0.3)

                    # 全部点完后翻页
                    self._scroll_count += 1
                    if self._scroll_count > self.max_scrolls:
                        self.log(f"已达最大翻页次数 ({self.max_scrolls})，停止")
                        self.stop()
                        return

                    self.log(f"翻页 ({self._scroll_count}/{self.max_scrolls})")
                    self.screen.scroll_up(self.scroll_percent)
                    self._last_action = '翻页'
                    time.sleep(self.scroll_interval)
                    return

            except Exception as e:
                self.log(f"颜色检测异常({color}): {e}")

        # 所有颜色都没有找到新色块 → 任务完成
        self.log("未找到任何目标色块，任务完成")
        self.stop()

    def _is_duplicate(self, x, y, threshold=50):
        """检查坐标是否与近期点击过的位置重叠（曼哈顿距离）"""
        for lx, ly in self._last_clicks[-20:]:
            if abs(x - lx) + abs(y - ly) < threshold:
                return True
        return False
