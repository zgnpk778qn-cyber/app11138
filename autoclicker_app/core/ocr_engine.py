"""
轻量级 OCR 引擎
基于字体渲染 + 归一化互相关(NCC)模板匹配
无需 Tesseract / OpenCV，纯 PIL + numpy

支持文字：确认、是、否、对、错、完成、未完成（可扩展）
"""

import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# 目标字符列表（单字）
TARGET_CHARS = ['确', '认', '是', '否', '对', '错', '完', '成', '未']
# 目标词语列表（多字组合）
TARGET_WORDS = ['确认', '是', '否', '对', '错', '完成', '未完成']

# 常用系统字体路径
_FONT_CANDIDATES = [
    # Windows
    'C:/Windows/Fonts/simhei.ttf',
    'C:/Windows/Fonts/msyh.ttc',
    'C:/Windows/Fonts/msyhbd.ttc',
    # macOS
    '/System/Library/Fonts/PingFang.ttc',
    '/System/Library/Fonts/STHeiti Light.ttc',
    # Linux / Android
    '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/system/fonts/NotoSansSC-Regular.otf',
    '/system/fonts/DroidSansFallback.ttf',
    '/system/fonts/NotoSansCJK-Regular.ttc',
]

# 模板渲染尺寸（对应手机 UI 文字常见像素大小）
_TEMPLATE_SIZES = [28, 36, 44, 52]


class OCREngine:
    """轻量级 OCR 引擎，用模板匹配识别中文字符"""

    def __init__(self, font_path=None):
        """
        参数:
            font_path: 中文字体路径，None 则自动查找
        """
        self.font_path = font_path or self._find_font()
        self._templates = {}  # {char: [(size, template_array), ...]}
        self._font_cache = {}

        if self.font_path:
            self._build_templates()
            self._available = True
        else:
            self._available = False

    # ── 属性 ────────────────────────────────────────────

    @property
    def is_available(self):
        return self._available

    # ── 字体管理 ───────────────────────────────────────

    def _find_font(self):
        """自动查找系统中的中文字体"""
        for path in _FONT_CANDIDATES:
            if os.path.exists(path):
                return path
        # 尝试通过 fontconfig 查找 (Linux)
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
        """获取指定大小的字体（带缓存）"""
        if size not in self._font_cache:
            try:
                self._font_cache[size] = ImageFont.truetype(self.font_path, size)
            except Exception:
                # 降级到默认字体（不含中文，仅用于避免崩溃）
                self._font_cache[size] = ImageFont.load_default()
        return self._font_cache[size]

    def _build_templates(self):
        """为每个目标字符渲染模板（多个尺寸）"""
        for char in TARGET_CHARS:
            templates = []
            for size in _TEMPLATE_SIZES:
                try:
                    arr = self._render_char(char, size)
                    templates.append((size, arr))
                except Exception:
                    continue
            if templates:
                self._templates[char] = templates

    def _render_char(self, char, font_size):
        """
        将字符渲染为灰度 numpy 数组
        返回: (h, w) float32 数组，背景=255，前景=0
        """
        font = self._get_font(font_size)
        # 用 getbbox 获取精确边界
        bbox = font.getbbox(char)
        if not bbox or (bbox[2] == 0 and bbox[3] == 0):
            # fallback: 用 getsize
            w, h = font.getsize(char)
            bbox = (0, 0, w, h)

        cw = bbox[2] - bbox[0]
        ch = bbox[3] - bbox[1]
        pad = 4  # 留边距
        img = Image.new('L', (cw + pad * 2, ch + pad * 2), 255)
        draw = ImageDraw.Draw(img)
        draw.text((pad - bbox[0], pad - bbox[1]), char, fill=0, font=font)
        return np.array(img, dtype=np.float32)

    # ── 模板匹配 ───────────────────────────────────────

    @staticmethod
    def _ncc(patch, template):
        """归一化互相关 (Normalized Cross-Correlation)"""
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

    def _scan_for_char(self, gray_img, char, threshold=0.55, stride_ratio=0.3):
        """
        在灰度图中扫描单个字符

        返回:
            [(x, y, w, h, score), ...] 匹配到的位置列表
        """
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

            # 扫描
            for y in range(0, h_img - th + 1, stride):
                row_end = min(y + th, h_img)
                for x in range(0, w_img - tw + 1, stride):
                    col_end = min(x + tw, w_img)
                    patch = gray_img[y:row_end, x:col_end]
                    # 动态调整模板大小匹配 patch
                    p_h, p_w = patch.shape
                    if p_h != th or p_w != tw:
                        continue
                    score = self._ncc(patch, tmpl_arr)
                    if score >= threshold:
                        all_matches.append((x, y, tw, th, score))

        # 非极大值抑制
        return self._nms(all_matches, iou_threshold=0.3)

    @staticmethod
    def _nms(matches, iou_threshold=0.3):
        """非极大值抑制，合并重叠的检测框"""
        if not matches:
            return []

        # 按置信度排序
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

    # ── 文字组合 ───────────────────────────────────────

    def _group_chars_into_words(self, char_matches, gap_ratio=1.5):
        """
        将单字匹配结果按水平距离组合成词语
        char_matches: {char: [(x, y, w, h, score), ...]}

        返回:
            [(word, x, y, w, h, avg_score), ...]
        """
        # 扁平化所有字符匹配并排序
        all_items = []
        for char, rects in char_matches.items():
            for x, y, w, h, s in rects:
                all_items.append((char, x, y, w, h, s))
        all_items.sort(key=lambda t: (t[2], t[1]))  # 按 y 再按 x 排序

        if not all_items:
            return []

        # 按行分组（y 坐标相近的为同一行）
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
            row.sort(key=lambda t: t[1])  # 按 x 排序
            rows.append(row)

        # 将行内的连续字符组合成词语
        results = []
        for row in rows:
            i = 0
            while i < len(row):
                # 尝试匹配长词优先
                best_word = None
                best_end = i
                best_x1 = best_y1 = best_x2 = best_y2 = 0
                best_score = 0

                for word in sorted(TARGET_WORDS, key=len, reverse=True):
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
                    # 单字作为单个字符结果
                    char, x, y, w, h, s = row[i]
                    i += 1

        return results

    # ── 对外接口 ───────────────────────────────────────

    def extract_text(self, image):
        """
        从图像中提取文字

        参数:
            image: PIL Image 对象

        返回:
            [(text, confidence, (x, y, w, h)), ...]
        """
        if not self._available:
            return []

        # 转灰度
        if image.mode != 'L':
            gray = np.array(image.convert('L'), dtype=np.float32)
        else:
            gray = np.array(image, dtype=np.float32)

        # 多尺度检测
        scales = [1.0, 0.75, 0.5]
        all_char_matches = {}

        for scale in scales:
            if scale < 1.0:
                h_new = int(gray.shape[0] * scale)
                w_new = int(gray.shape[1] * scale)
                img_pil = Image.fromarray(gray.astype(np.uint8))
                img_scaled = np.array(
                    img_pil.resize((w_new, h_new), Image.LANCZOS),
                    dtype=np.float32
                )
            else:
                img_scaled = gray

            for char in TARGET_CHARS:
                matches = self._scan_for_char(img_scaled, char, threshold=0.50)
                if matches:
                    # 将坐标缩放回原图
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

        # 字符级 NMS
        for char in all_char_matches:
            all_char_matches[char] = self._nms(all_char_matches[char])

        # 组合成词语
        word_results = self._group_chars_into_words(all_char_matches)

        # 转换为统一输出格式
        output = []
        for word, x, y, w, h, score in word_results:
            output.append((word, score, (x, y, w, h)))

        # 同时输出单字结果
        for char, rects in all_char_matches.items():
            for x, y, w, h, s in rects:
                output.append((char, s, (x, y, w, h)))

        return output

    def find_text(self, image, target_texts=None):
        """
        在图像中查找目标文字

        返回:
            [(matched_text, confidence, (x, y, w, h)), ...]
        """
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

    @staticmethod
    def fuzzy_match(text, target):
        """简单的精确匹配"""
        if not text or not target:
            return False
        return text == target or target in text
