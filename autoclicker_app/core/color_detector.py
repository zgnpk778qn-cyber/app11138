"""
颜色识别模块
支持识别：红、橙、绿、蓝、白
使用 HSV 颜色空间进行颜色检测，对光照变化有一定鲁棒性
"""

import numpy as np
from PIL import Image
from collections import defaultdict


# 预设颜色定义（HSV 范围 + RGB 参考值）
COLOR_PRESETS = {
    '红色': {
        'h_ranges': [(0, 10), (156, 180)],  # 红色在 HSV 色调环两端
        's_range': (60, 255),
        'v_range': (60, 255),
        'rgb': (255, 50, 50),
    },
    '橙色': {
        'h_ranges': [(11, 25)],
        's_range': (100, 255),
        'v_range': (100, 255),
        'rgb': (255, 165, 0),
    },
    '黄色': {
        'h_ranges': [(26, 34)],
        's_range': (80, 255),
        'v_range': (100, 255),
        'rgb': (255, 255, 50),
    },
    '绿色': {
        'h_ranges': [(35, 85)],
        's_range': (60, 255),
        'v_range': (60, 255),
        'rgb': (50, 255, 50),
    },
    '蓝色': {
        'h_ranges': [(100, 140)],
        's_range': (60, 255),
        'v_range': (60, 255),
        'rgb': (50, 50, 255),
    },
    '白色': {
        'h_ranges': [(0, 180)],
        's_range': (0, 40),
        'v_range': (180, 255),
        'rgb': (240, 240, 240),
    },
}


class ColorDetector:
    """颜色检测器，支持在图像中查找指定颜色的区域"""

    def __init__(self, tolerance=10):
        """
        初始化颜色检测器
        tolerance: 颜色容差，越大检测到的颜色范围越宽
        """
        self.tolerance = tolerance
        self.colors = COLOR_PRESETS

    def create_mask(self, img_array, color_name):
        """
        创建指定颜色的二值掩码
        返回: (h, w) 的布尔数组，True 表示匹配颜色
        """
        if isinstance(img_array, Image.Image):
            img_array = np.array(img_array.convert('RGB'))

        hsv = Image.fromarray(img_array).convert('HSV')
        hsv_array = np.array(hsv, dtype=np.int16)

        h, s, v = hsv_array[:, :, 0], hsv_array[:, :, 1], hsv_array[:, :, 2]
        color_def = self.colors.get(color_name)
        if not color_def:
            raise ValueError(f"不支持的颜色: {color_name}，可选: {list(self.colors.keys())}")

        mask = np.zeros(img_array.shape[:2], dtype=bool)
        for h_lo, h_hi in color_def['h_ranges']:
            h_mask = (h >= h_lo) & (h <= h_hi)
            s_mask = (s >= color_def['s_range'][0]) & (s <= color_def['s_range'][1])
            v_mask = (v >= color_def['v_range'][0]) & (v <= color_def['v_range'][1])
            mask |= h_mask & s_mask & v_mask

        return mask

    def find_regions(self, image, color_name, min_region=80, stride=5):
        """
        查找图像中指定颜色的所有区域
        使用网格扫描 + 区域合并

        参数:
            image: PIL Image 或文件路径或 numpy array
            color_name: 颜色名称（红色、橙色、绿色、蓝色、白色）
            min_region: 最小区域像素数
            stride: 扫描步长

        返回:
            [(x, y, w, h), ...] 区域矩形列表
        """
        if isinstance(image, str):
            image = Image.open(image)
        elif isinstance(image, np.ndarray):
            image = Image.fromarray(image)

        img_array = np.array(image.convert('RGB'))
        mask = self.create_mask(img_array, color_name)

        h, w = mask.shape
        grid_cells = []

        for y in range(0, h, stride):
            for x in range(0, w, stride):
                cell_end_y = min(y + stride, h)
                cell_end_x = min(x + stride, w)
                cell = mask[y:cell_end_y, x:cell_end_x]
                match_ratio = np.sum(cell) / (stride * stride)
                if match_ratio > 0.3:
                    grid_cells.append((x, y, cell_end_x - x, cell_end_y - y))

        merged = self._merge_rects(grid_cells)
        merged = [rect for rect in merged if rect[2] * rect[3] >= min_region]
        return merged

    def find_colored_regions_with_text(
        self, image, color_name, ocr_engine, target_texts, min_region=80
    ):
        """
        查找指定颜色区域内是否包含目标文字
        返回匹配的 (rect, matched_text) 列表
        """
        regions = self.find_regions(image, color_name, min_region)
        img = image if isinstance(image, Image.Image) else Image.open(image)
        results = []

        for rect in regions:
            x, y, rw, rh = rect
            crop = img.crop((x, y, x + rw, y + rh))
            texts = ocr_engine.extract_text(crop)
            for text, confidence, text_rect in texts:
                for target in target_texts:
                    if ocr_engine.fuzzy_match(text, target):
                        results.append((rect, text, target))
                        break

        return results

    def _merge_rects(self, rects, gap_threshold=10):
        """合并相邻或重叠的矩形"""
        if not rects:
            return []

        rects = [(x, y, x + w, y + h) for x, y, w, h in rects]

        merged = True
        while merged:
            merged = False
            new_rects = []
            used = [False] * len(rects)

            for i in range(len(rects)):
                if used[i]:
                    continue
                x1, y1, x2, y2 = rects[i]
                for j in range(i + 1, len(rects)):
                    if used[j]:
                        continue
                    rx1, ry1, rx2, ry2 = rects[j]
                    gap_x = max(0, max(x1, rx1) - min(x2, rx2))
                    gap_y = max(0, max(y1, ry1) - min(y2, ry2))
                    if gap_x <= gap_threshold and gap_y <= gap_threshold:
                        x1 = min(x1, rx1)
                        y1 = min(y1, ry1)
                        x2 = max(x2, rx2)
                        y2 = max(y2, ry2)
                        used[j] = True
                        merged = True
                new_rects.append((x1, y1, x2, y2))
                used[i] = True
            rects = new_rects

        return [(x1, y1, x2 - x1, y2 - y1) for x1, y1, x2, y2 in rects]

    def get_dominant_color(self, image, region=None):
        """获取指定区域的主色调"""
        if isinstance(image, str):
            image = Image.open(image)
        img = np.array(image.convert('RGB'))
        if region:
            x, y, w, h = region
            img = img[y:y + h, x:x + w]

        avg_color = np.mean(img.reshape(-1, 3), axis=0)
        best_color = min(self.colors.keys(), key=lambda c: np.linalg.norm(
            np.array(avg_color) - np.array(self.colors[c]['rgb'])
        ))
        return best_color, tuple(map(int, avg_color))

    @staticmethod
    def list_supported_colors():
        """返回支持的颜色列表"""
        return list(COLOR_PRESETS.keys())
