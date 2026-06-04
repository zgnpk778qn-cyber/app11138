"""
AutoClicker Service — 后台前台服务：截图 → 颜色+文字匹配 → 点击 → 上滑
"""
import os
import time
import threading
import subprocess
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import numpy as np

CFG = '/data/data/org.autoclicker.autoclicker/files/service_cfg.txt'

# ---- 颜色范围 (RGB lo, hi) ----
COLOR_RANGES = {
    '红':  ((180, 0, 0),   (255, 90, 90)),
    '绿':  ((0, 140, 0),   (120, 255, 120)),
    '蓝':  ((0, 0, 180),   (100, 100, 255)),
    '黄':  ((200, 180, 0), (255, 255, 100)),
    '白':  ((190, 190, 190), (255, 255, 255)),
}

# ---- 目标字列表 ----
TARGET_CHARS = ['是', '否', '对', '错', '和', '或', 'y', 'e', 's', 'n', 'o']


# ============================================================
#  轻量 OCR：字体渲染 + NCC 模板匹配
# ============================================================
class TextMatcher:
    """对指定字符集做模板匹配，不依赖外部 OCR 库"""

    FONT_SIZES = [28, 36, 48, 60]

    def __init__(self):
        self._templates = {}   # char -> [(h,w, array), ...]
        font = self._find_font()
        if font:
            for char in TARGET_CHARS:
                temps = []
                for sz in self.FONT_SIZES:
                    arr = self._render(font, char, sz)
                    if arr is not None:
                        temps.append(arr)
                if temps:
                    self._templates[char] = temps
        self.ready = len(self._templates) > 0

    def _find_font(self):
        """Find a CJK-capable font on Android"""
        candidates = [
            '/system/fonts/NotoSansCJK-Regular.ttc',
            '/system/fonts/NotoSansSC-Regular.otf',
            '/system/fonts/DroidSansFallback.ttf',
            '/system/fonts/NotoSerifCJK-Regular.ttc',
            '/system/fonts/Miui-Regular.ttf',
            '/system/fonts/Roboto-Regular.ttf',
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return None

    def _render(self, font_path, char, size):
        try:
            font = ImageFont.truetype(font_path, size)
        except Exception:
            return None
        bbox = font.getbbox(char)
        cw, ch = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if cw <= 0 or ch <= 0:
            return None
        pad = 4
        img = Image.new('L', (cw + pad * 2, ch + pad * 2), 255)
        draw = ImageDraw.Draw(img)
        draw.text((pad - bbox[0], pad - bbox[1]), char, fill=0, font=font)
        return np.array(img, dtype=np.float32)

    def scan(self, gray_img, threshold=0.50):
        """
        在灰度图上扫描所有目标字。
        返回: [(char, x, y, w, h, score), ...]
        """
        if not self.ready:
            return []
        h_img, w_img = gray_img.shape
        matches = []
        for char, templates in self._templates.items():
            for tmpl in templates:
                th, tw = tmpl.shape
                if th > h_img or tw > w_img:
                    continue
                stride = max(3, tw // 4)
                for y in range(0, h_img - th + 1, stride):
                    for x in range(0, w_img - tw + 1, stride):
                        patch = gray_img[y:y + th, x:x + tw]
                        if patch.shape != (th, tw):
                            continue
                        score = self._ncc(patch, tmpl)
                        if score >= threshold:
                            matches.append((char, x, y, tw, th, score))
        return self._nms(matches)

    @staticmethod
    def _ncc(a, b):
        a_flat = a.ravel()
        b_flat = b.ravel()
        a_m, b_m = a_flat.mean(), b_flat.mean()
        a_s, b_s = a_flat.std(), b_flat.std()
        if a_s < 1e-6 or b_s < 1e-6:
            return 0.0
        return float(np.dot((a_flat - a_m) / a_s, (b_flat - b_m) / b_s) / len(a_flat))

    @staticmethod
    def _nms(matches, iou_thresh=0.3):
        if not matches:
            return []
        matches.sort(key=lambda m: m[5], reverse=True)
        kept = []
        for m in matches:
            x1, y1, w, h = m[1:5]
            x2, y2 = x1 + w, y1 + h
            ok = True
            for k in kept:
                kx1, ky1, kw, kh = k[1:5]
                kx2, ky2 = kx1 + kw, ky1 + kh
                ix1, iy1 = max(x1, kx1), max(y1, ky1)
                ix2, iy2 = min(x2, kx2), min(y2, ky2)
                if ix2 > ix1 and iy2 > iy1:
                    inter = (ix2 - ix1) * (iy2 - iy1)
                    union = w * h + kw * kh - inter
                    if inter / union > iou_thresh:
                        ok = False
                        break
            if ok:
                kept.append(m)
        return kept

    def match_word(self, gray_img, word, threshold=0.45):
        """检查图像中是否包含目标词语（连续相邻的字符匹配）"""
        chars = self.scan(gray_img, threshold=threshold)
        if len(chars) < len(word):
            return False, None
        # Sort by x position
        chars.sort(key=lambda c: c[1])
        # Slide window looking for consecutive matching chars
        for i in range(len(chars) - len(word) + 1):
            segment = chars[i:i + len(word)]
            seg_word = ''.join(c[0] for c in segment)
            if seg_word == word:
                # Check if chars are adjacent (no large gaps)
                ok = True
                for j in range(1, len(segment)):
                    prev_right = segment[j - 1][1] + segment[j - 1][3]
                    gap = segment[j][1] - prev_right
                    if gap > segment[j][3] * 2:  # gap > 2x char width
                        ok = False
                        break
                if ok:
                    x1 = segment[0][1]
                    y1 = min(c[2] for c in segment)
                    x2 = max(c[1] + c[3] for c in segment)
                    y2 = max(c[2] + c[4] for c in segment)
                    avg_score = sum(c[5] for c in segment) / len(segment)
                    return True, (x1, y1, x2 - x1, y2 - y1, avg_score)
        return False, None


# ============================================================
#  颜色检测
# ============================================================
def find_color(img, color_name):
    lo, hi = COLOR_RANGES.get(color_name, COLOR_RANGES['红'])
    px = img.load()
    w, h = img.size
    step = 15
    hits = []
    for y in range(0, h - step, step):
        for x in range(0, w - step, step):
            r, g, b = px[x + step // 2, y + step // 2]
            if lo[0] <= r <= hi[0] and lo[1] <= g <= hi[1] and lo[2] <= b <= hi[2]:
                hits.append((x, y, step, step))
    return merge_rects(hits)


def merge_rects(rects, gap=30):
    if len(rects) < 2:
        return rects
    boxes = [(x, y, x + w, y + h) for x, y, w, h in rects]
    changed = True
    while changed:
        changed = False
        out = []
        used = [False] * len(boxes)
        for i, (x1, y1, x2, y2) in enumerate(boxes):
            if used[i]:
                continue
            for j, (rx1, ry1, rx2, ry2) in enumerate(boxes[i + 1:], i + 1):
                if used[j]:
                    continue
                ox = max(0, max(x1, rx1) - min(x2, rx2))
                oy = max(0, max(y1, ry1) - min(y2, ry2))
                if ox <= gap and oy <= gap:
                    x1, y1 = min(x1, rx1), min(y1, ry1)
                    x2, y2 = max(x2, rx2), max(y2, ry2)
                    used[j] = True
                    changed = True
            out.append((x1, y1, x2, y2))
            used[i] = True
        boxes = out
    return [(x1, y1, x2 - x1, y2 - y1) for x1, y1, x2, y2 in boxes]


# ============================================================
#  点击 / 上滑
# ============================================================
def tap(x, y):
    subprocess.run(
        ['input', 'tap', str(int(x)), str(int(y))],
        capture_output=True, timeout=5
    )


def scroll_up():
    """上滑"""
    subprocess.run(
        ['input', 'swipe', '540', '1200', '540', '350', '400'],
        capture_output=True, timeout=5
    )


def screenshot():
    r = subprocess.run(['screencap', '-p'], capture_output=True, timeout=10)
    return Image.open(BytesIO(r.stdout)).convert('RGB')


def log(msg):
    try:
        with open(CFG + '.log', 'a') as f:
            f.write(f'{msg}\n')
    except Exception:
        pass


def read_cfg():
    d = {}
    try:
        if os.path.exists(CFG):
            with open(CFG) as f:
                for line in f:
                    line = line.strip()
                    if '=' in line:
                        k, v = line.split('=', 1)
                        d[k.strip()] = v.strip()
    except Exception:
        pass
    return d


# ============================================================
#  主循环
# ============================================================
def main():
    # ---- 前台服务通知 ----
    try:
        from jnius import autoclass
        PythonService = autoclass('org.kivy.android.PythonService')
        mService = PythonService.mService
        if mService is not None:
            NotificationBuilder = autoclass('android.app.Notification$Builder')
            NotificationManager = autoclass('android.app.NotificationManager')
            nm = mService.getSystemService('notification')
            try:
                NotificationChannel = autoclass('android.app.NotificationChannel')
                ch = NotificationChannel(
                    'ac', 'AutoClicker', NotificationManager.IMPORTANCE_LOW)
                nm.createNotificationChannel(ch)
            except Exception:
                pass
            notify = (
                NotificationBuilder(mService, 'ac')
                .setContentTitle('AutoClicker')
                .setContentText('后台运行中')
                .setSmallIcon(17301552)
                .setOngoing(True)
                .build()
            )
            mService.startForeground(1, notify)
    except Exception as e:
        log(f'Foreground err: {e}')

    log('Service started')

    # ---- 初始化 OCR ----
    text_matcher = TextMatcher()
    log(f'OCR ready: {text_matcher.ready}')

    # ---- 默认参数 ----
    color = '红'
    match_mode = '无'       # "和" / "或" / "无"
    target_text = ''
    interval = 1.5
    click_count = 0
    running = True

    while running:
        # 读配置
        cfg = read_cfg()
        if cfg.get('cmd') == 'stop':
            running = False
            break
        if cfg.get('color'):
            color = cfg['color']
        if cfg.get('match_mode'):
            match_mode = cfg['match_mode']
        if 'target_text' in cfg:
            target_text = cfg['target_text']
        try:
            interval = float(cfg.get('interval', interval))
        except Exception:
            pass

        try:
            img = screenshot()
            gray = np.array(img.convert('L'), dtype=np.float32)

            # Step 1 — 颜色区域
            color_regions = find_color(img, color)
            # Step 2 — 文字匹配
            text_found = False
            text_rect = None
            if target_text and text_matcher.ready:
                text_found, text_rect = text_matcher.match_word(gray, target_text)

            # Step 3 — 根据关联模式决定点击目标
            targets = []

            if match_mode == '和':
                # 必须同时匹配颜色+文字：找颜色区域内的文字
                if target_text and text_found and text_rect and color_regions:
                    tx, ty, tw, th, _ = text_rect
                    for rx, ry, rw, rh in color_regions:
                        # 文字矩形与颜色区域有重叠
                        if (tx < rx + rw and tx + tw > rx and
                                ty < ry + rh and ty + th > ry):
                            # 在重叠区域中心点击
                            cx = max(rx, tx) + min(rx + rw, tx + tw) - max(rx, tx)
                            cy = max(ry, ty) + min(ry + rh, ty + th) - max(ry, ty)
                            targets.append((rx + rw // 2, ry + rh // 2))
                            break

            elif match_mode == '或':
                # 颜色或文字任一匹配即可
                for rx, ry, rw, rh in color_regions[:5]:
                    targets.append((rx + rw // 2, ry + rh // 2))
                if not color_regions and text_found and text_rect:
                    tx, ty, tw, th, _ = text_rect
                    targets.append((tx + tw // 2, ty + th // 2))

            else:  # "无" — 仅颜色
                for rx, ry, rw, rh in color_regions[:5]:
                    targets.append((rx + rw // 2, ry + rh // 2))

            # Step 4 — 执行点击
            clicked = 0
            for cx, cy in targets[:5]:
                if not running:
                    break
                tap(cx, cy)
                clicked += 1
                click_count += 1
                log(f'Clicked ({cx},{cy}) #{click_count}')
                time.sleep(0.3)

            if clicked == 0:
                log('No target — scrolling')
            scroll_up()
            time.sleep(interval)

        except Exception as e:
            log(f'Cycle error: {e}')
            time.sleep(2)

    log(f'Stopped — total clicks: {click_count}')
    try:
        mService.stopForeground(True)
        mService.stopSelf()
    except Exception:
        pass


if __name__ == '__main__':
    main()
