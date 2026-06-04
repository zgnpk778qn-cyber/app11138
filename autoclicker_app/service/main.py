"""
AutoClicker Service - 后台前台服务，持续执行点击+上滑操作
"""
import os
import time
import threading
import subprocess
from io import BytesIO
from PIL import Image

# ---- config file for IPC with UI ----
CFG = '/data/data/org.autoclicker.autoclicker/files/service_cfg.txt'

# ---- color ranges ----
COLOR_RANGES = {
    'Red':    ((180, 0, 0),   (255, 90, 90)),
    'Green':  ((0, 140, 0),   (120, 255, 120)),
    'Blue':   ((0, 0, 180),   (100, 100, 255)),
    'Yellow': ((200, 180, 0), (255, 255, 100)),
    'White':  ((190, 190, 190), (255, 255, 255)),
}


def log(msg):
    try:
        with open(CFG + '.log', 'a') as f:
            f.write(f'{msg}\n')
    except Exception:
        pass


def read_cfg():
    """Read target color + interval from UI-written file. Returns dict or None."""
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


def screenshot():
    r = subprocess.run(['screencap', '-p'], capture_output=True, timeout=10)
    return Image.open(BytesIO(r.stdout)).convert('RGB')


def find_color(img, color_name):
    lo, hi = COLOR_RANGES.get(color_name, COLOR_RANGES['Red'])
    px = img.load()
    w, h = img.size
    step = 15
    hits = []
    for y in range(0, h - step, step):
        for x in range(0, w - step, step):
            r, g, b = px[x + step // 2, y + step // 2]
            if lo[0] <= r <= hi[0] and lo[1] <= g <= hi[1] and lo[2] <= b <= hi[2]:
                hits.append((x, y, step, step))
    return merge(hits)


def merge(rects, gap=30):
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


def tap(x, y):
    subprocess.run(
        ['input', 'tap', str(int(x)), str(int(y))],
        capture_output=True, timeout=5
    )


def scroll():
    """上滑 - 从屏幕 65% 位置滑到 25%"""
    subprocess.run(
        ['input', 'swipe', '540', '1200', '540', '350', '400'],
        capture_output=True, timeout=5
    )


def main():
    # Setup foreground notification via pyjnius
    try:
        from jnius import autoclass

        PythonService = autoclass('org.kivy.android.PythonService')
        mService = PythonService.mService
        if mService is not None:
            NotificationBuilder = autoclass('android.app.Notification$Builder')
            NotificationManager = autoclass('android.app.NotificationManager')
            PendingIntent = autoclass('android.app.PendingIntent')
            Intent = autoclass('android.content.Intent')
            R = autoclass('org.autoclicker.autoclicker.R$drawable')

            CHANNEL_ID = 'autoclicker_channel'
            # Create notification channel (API 26+)
            nm = mService.getSystemService('notification')
            try:
                NotificationChannel = autoclass('android.app.NotificationChannel')
                channel = NotificationChannel(
                    CHANNEL_ID, 'AutoClicker', NotificationManager.IMPORTANCE_LOW
                )
                nm.createNotificationChannel(channel)
            except Exception:
                pass

            # Build notification
            notify = (
                NotificationBuilder(mService, CHANNEL_ID)
                .setContentTitle('AutoClicker')
                .setContentText('Running in background')
                .setSmallIcon(getattr(R, 'icon', 0) or 17301552)
                .setOngoing(True)
                .build()
            )
            mService.startForeground(1, notify)
    except Exception as e:
        log(f'Foreground setup failed: {e}')

    log('Service started')

    color = 'Red'
    interval = 1.5
    running = True
    click_count = 0

    while running:
        # Re-read config every cycle
        cfg = read_cfg()
        if cfg.get('cmd') == 'stop':
            running = False
            log('Service: stop command received')
            break
        if cfg.get('color'):
            color = cfg['color']
        try:
            interval = float(cfg.get('interval', interval))
        except Exception:
            pass

        try:
            img = screenshot()
            regions = find_color(img, color)
            clicked = 0
            for rx, ry, rw, rh in regions[:5]:
                cx, cy = rx + rw // 2, ry + rh // 2
                tap(cx, cy)
                clicked += 1
                click_count += 1
                log(f'Clicked ({cx},{cy}) #{click_count}')
                time.sleep(0.3)

            if clicked == 0:
                log('No target — scrolling')
            scroll()
            time.sleep(interval)
        except Exception as e:
            log(f'Cycle error: {e}')
            time.sleep(2)

    log(f'Service stopped — total clicks: {click_count}')
    try:
        mService.stopForeground(True)
        mService.stopSelf()
    except Exception:
        pass


if __name__ == '__main__':
    main()
