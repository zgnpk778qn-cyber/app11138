"""
轻量级 OCR 引擎
基于字体渲染 + 归一化互相关(NCC)模板匹配
精简版：仅支持常见确认/取消类基础汉字
"""

import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# 精简目标单字 — 仅基础 UI 常用字
TARGET_CHARS = sorted(set('是否对错确认完成未提交定取消知道了开始关闭下一步同意拒绝'))

# 目标词语列表（按长度降序）
TARGET_WORDS = sorted([
    '确认', '取消', '完成', '未完成', '提交', '确定',
    '知道了', '开始', '关闭', '下一步', '同意', '拒绝',
    '是', '否', '对', '错',
], key=len, reverse=True)

# 常用系统字体路径
_FONT_CANDIDATES = [
    'C:/Windows/Fonts/simhei.ttf',
    'C:/Windows/Fonts/msyh.ttc',
    'C:/Windows/Fonts/msyhbd.ttc',
    '/System/Library/Fonts/PingFang.ttc',
    '/System/Library/Fonts/STHeiti Light.ttc',
    '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/system/fonts/NotoSansSC-Regular.otf',
    '/system/fonts/DroidSansFallback.ttf',
    '/system/fonts/NotoSansCJK-Regular.ttc',
]

_TEMPLATE_SIZES = [28, 36, 44, 52, 64]


class OCREngine:
    """轻量级 OCR 引擎，用模板匹配识别中文字符"""

    def __init__(self, font_path=None):
        self.font_path = font_path or self._find_font()
        self._templates = {}
        self._font_cache = {}
        if self.font_path:
            self._build_templates()
            self._available = True
        else:
            self._available = False

    @property
    def is_available(self):
        return self._available

    def _find_font(self):
        for path in _FONT_CANDIDATES:
            if os.path.exists(path):
                return path
        try:
            import subprocess
            result = subprocess.run(
                ['fc-match', '-f', '%{file}', 'sans:lang=zh'],
                capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0 and os.path.exists(result.stdout.strip()):
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def _get_font(self, size):
        if size not in self._font_cache:
            try:
                self._font_cache[size] = ImageFont.truetype(self.font_path, size)
            except Exception:
                self._font_cache[size] = ImageFont.load_default()
        return self._font_cache[size]

    def _build_templates(self):
        for char in TARGET_CHARS:
            templates = []
            for size in _TEMPLATE_SIZES:
                try:
                    arr = self._render_char(char, size)
                    if arr.size > 0:
                        templates.append((size, arr))
                except Exception:
                    continue
            if templates:
                self._templates[char] = templates

    def _render_char(self, char, font_size):
        font = self._get_font(font_size)
        bbox = font.getbbox(char)
        if not bbox or (bbox[2] == 0 and bbox[3] == 0):
            try:
                w, h = font.getsize(char)
            except Exception:
                w, h = font_size, font_size
            bbox = (0, 0, w, h)
        cw = bbox[2] - bbox[0]
        ch = bbox[3] - bbox[1]
        if cw <= 0 or ch <= 0:
            return np.array([], dtype=np.float32)
        pad = 4
        img = Image.new('L', (cw + pad * 2, ch + pad * 2), 255)
        draw = ImageDraw.Draw(img)
        draw.text((pad - bbox[0], pad - bbox[1]), char, fill=0, font=font)
        return np.array(img, dtype=np.float32)

    @staticmethod
    def _ncc(patch, template):
        p = patch.ravel()
        t = template.ravel()
        p_mean = p.mean()
        t_mean = t.mean()
        p_std = p.std()
        t_std = t.std()
        if p_std < 1e-6 or t_std < 1e-6:
            return 0.0
        p_norm = (p - p_mean) / p_std
        t_norm = (t - t_mean) / t_std
        return float(np.dot(p_norm, t_norm) / len(p))

    def _scan_for_char(self, gray_img, char, threshold=0.48, stride_ratio=0.25):
        templates = self._templates.get(char)
        if not templates:
            return []
        h_img, w_img = gray_img.shape
        all_matches = []
        for tmpl_size, tmpl_arr in templates:
            th, tw = tmpl_arr.shape
            if th > h_img or tw > w_img:
                continue
            stride = max(2, int(tw * stride_ratio))
            for y in range(0, h_img - th + 1, stride):
                for x in range(0, w_img - tw + 1, stride):
                    patch = gray_img[y:y + th, x:x + tw]
                    if patch.shape != (th, tw):
                        continue
                    score = self._ncc(patch, tmpl_arr)
                    if score >= threshold:
                        all_matches.append((x, y, tw, th, score))
        return self._nms(all_matches, iou_threshold=0.3)

    @staticmethod
    def _nms(matches, iou_threshold=0.3):
        if not matches:
            return []
        matches = sorted(matches, key=lambda m: m[4], reverse=True)
        kept = []
        for match in matches:
            x1, y1, w, h, s = match
            x2, y2 = x1 + w, y1 + h
            overlap = False
            for kx1, ky1, kw, kh, _ in kept:
                kx2, ky2 = kx1 + kw, ky1 + kh
                ix1, iy1 = max(x1, kx1), max(y1, ky1)
                ix2, iy2 = min(x2, kx2), min(y2, ky2)
                if ix2 > ix1 and iy2 > iy1:
                    inter = (ix2 - ix1) * (iy2 - iy1)
                    union = w * h + kw * kh - inter
                    if inter / union > iou_threshold:
                        overlap = True
                        break
            if not overlap:
                kept.append(match)
        return kept

    def _group_chars_into_words(self, char_matches, gap_ratio=1.5):
        all_items = []
        for char, rects in char_matches.items():
            for x, y, w, h, s in rects:
                all_items.append((char, x, y, w, h, s))
        all_items.sort(key=lambda t: (t[2], t[1]))
        if not all_items:
            return []
        rows = []
        used = [False] * len(all_items)
        for i, item in enumerate(all_items):
            if used[i]:
                continue
            _, _, yi, _, hi, _ = item
            row = [item]
            used[i] = True
            row_center = yi + hi / 2
            for j in range(i + 1, len(all_items)):
                if used[j]:
                    continue
                _, _, yj, _, hj, _ = all_items[j]
                other_center = yj + hj / 2
                if abs(row_center - other_center) < max(hi, hj) * 0.8:
                    row.append(all_items[j])
                    used[j] = True
            row.sort(key=lambda t: t[1])
            rows.append(row)
        results = []
        for row in rows:
            i = 0
            while i < len(row):
                best_word = None
                best_end = i
                best_x1 = best_y1 = best_x2 = best_y2 = 0
                best_score = 0
                for word in TARGET_WORDS:
                    if i + len(word) > len(row):
                        continue
                    segment = row[i:i + len(word)]
                    word_chars = ''.join(t[0] for t in segment)
                    if word_chars == word:
                        x1 = segment[0][1]
                        y1 = min(t[2] for t in segment)
                        x2 = max(t[1] + t[3] for t in segment)
                        y2 = max(t[2] + t[4] for t in segment)
                        avg_s = sum(t[5] for t in segment) / len(segment)
                        best_word = word
                        best_end = i + len(word)
                        best_x1, best_y1, best_x2, best_y2 = x1, y1, x2, y2
                        best_score = avg_s
                        break
                if best_word:
                    results.append((
                        best_word,
                        best_x1, best_y1,
                        best_x2 - best_x1, best_y2 - best_y1,
                        best_score
                    ))
                    i = best_end
                else:
                    i += 1
        return results

    def extract_text(self, image):
        if not self._available:
            return []
        if image.mode != 'L':
            gray = np.array(image.convert('L'), dtype=np.float32)
        else:
            gray = np.array(image, dtype=np.float32)
        scales = [1.0, 0.75, 0.5]
        all_char_matches = {}
        for scale in scales:
            if scale < 1.0:
                h_new = int(gray.shape[0] * scale)
                w_new = int(gray.shape[1] * scale)
                img_pil = Image.fromarray(gray.astype(np.uint8))
                try:
                    img_scaled = np.array(
                        img_pil.resize((w_new, h_new), Image.LANCZOS),
                        dtype=np.float32
                    )
                except Exception:
                    continue
            else:
                img_scaled = gray
            for char in TARGET_CHARS:
                matches = self._scan_for_char(img_scaled, char, threshold=0.48)
                if matches:
                    if scale != 1.0:
                        inv = 1.0 / scale
                        matches = [
                            (int(x * inv), int(y * inv),
                             int(w * inv), int(h * inv), s)
                            for x, y, w, h, s in matches
                        ]
                    if char not in all_char_matches:
                        all_char_matches[char] = []
                    all_char_matches[char].extend(matches)
        for char in all_char_matches:
            all_char_matches[char] = self._nms(all_char_matches[char])
        word_results = self._group_chars_into_words(all_char_matches)
        output = []
        for word, x, y, w, h, score in word_results:
            output.append((word, score, (x, y, w, h)))
        for char, rects in all_char_matches.items():
            for x, y, w, h, s in rects:
                output.append((char, s, (x, y, w, h)))
        return output

    def find_text(self, image, target_texts=None):
        if target_texts is None:
            target_texts = TARGET_WORDS
        all_texts = self.extract_text(image)
        results = []
        for text, confidence, rect in all_texts:
            for target in target_texts:
                if self.fuzzy_match(text, target):
                    results.append((target, confidence, rect))
                    break
        return results

    def find_text_in_region(self, image, region):
        x, y, w, h = region
        if w <= 0 or h <= 0:
            return []
        crop = image.crop((x, y, x + w, y + h))
        texts = self.extract_text(crop)
        return [
            (text, conf, (rx + x, ry + y, rw, rh))
            for text, conf, (rx, ry, rw, rh) in texts
        ]

    @staticmethod
    def fuzzy_match(text, target):
        if not text or not target:
            return False
        return text == target or target in text or text in target
