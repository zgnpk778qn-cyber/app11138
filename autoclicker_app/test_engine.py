"""
测试自动化引擎核心逻辑（mock 后端）
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from PIL import Image, ImageDraw
from core.color_detector import ColorDetector
from core.ocr_engine import OCREngine
from core.screen_controller import ScreenController
from core.automation_engine import AutomationEngine

# 创建测试图像：在一张白底图上画几个红、绿、蓝色块
def create_test_image():
    img = Image.new('RGB', (1080, 1920), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)

    # 3 个红色方块
    draw.rectangle([100, 200, 200, 300], fill=(255, 50, 50))
    draw.rectangle([400, 500, 500, 600], fill=(255, 40, 40))
    draw.rectangle([700, 800, 800, 900], fill=(255, 60, 60))

    # 2 个绿色方块
    draw.rectangle([100, 1000, 200, 1100], fill=(50, 255, 50))
    draw.rectangle([500, 1200, 600, 1300], fill=(40, 255, 40))

    # 1 个蓝色方块
    draw.rectangle([300, 1500, 400, 1600], fill=(50, 50, 255))

    return img

def test_color_detection():
    print("=" * 50)
    print("测试 1: 颜色检测")
    print("=" * 50)

    img = create_test_image()
    detector = ColorDetector()

    for color in ['红色', '绿色', '蓝色', '橙色', '黄色']:
        regions = detector.find_regions(img, color, min_region=80)
        print(f"  {color}: 找到 {len(regions)} 个区域 {regions}")

    return img

def test_automation_engine():
    print("\n" + "=" * 50)
    print("测试 2: 自动化引擎 (mock 后端)")
    print("=" * 50)

    # 创建 mock 组件
    screen = ScreenController(backend='mock', screen_size=(1080, 1920))
    detector = ColorDetector()
    ocr = OCREngine(font_path=None)

    engine = AutomationEngine(screen, detector, ocr)
    engine.target_colors = ['红色', '绿色', '蓝色']
    engine.interval = 0.5
    engine.scroll_interval = 1.0
    engine.max_scrolls = 5

    # 记录日志
    logs = []
    engine.on_log = lambda msg: logs.append(msg)

    # 用自定义截图（测试图像）
    test_img = create_test_image()
    click_count = [0]

    original_screenshot = screen.screenshot
    def mock_screenshot(filename=None):
        return test_img.copy()
    screen.screenshot = mock_screenshot

    # 启动引擎
    engine.start()
    engine.wait_for_completion(timeout=15)

    print(f"  状态: {engine.state}")
    print(f"  翻页次数: {engine._scroll_count}")
    print(f"  日志:")
    for log in logs:
        print(f"    {log}")

    # 验证
    print("\n  验证:")
    # 第一轮应该找到 3 个红色，点击全部 3 个，然后翻页
    # 第二轮 mock 截图还是一样（因为没变），但去重机制会过滤
    red_found = any("发现 3 个 红色" in log for log in logs)
    green_found = any("绿色" in log for log in logs)
    print(f"    检测到红色: {red_found}")
    print(f"    检测到绿色: {green_found}")

    # 恢复
    screen.screenshot = original_screenshot

def test_deduplication():
    print("\n" + "=" * 50)
    print("测试 3: 点击去重")
    print("=" * 50)

    engine = AutomationEngine(None, None, None)
    engine._last_clicks = [(100, 200), (400, 500)]

    # 相同位置应该被去重
    assert engine._is_duplicate(105, 198, threshold=50), "应判定为重复"
    print("  近距离去重: 通过")

    # 远距离位置不应被去重
    assert not engine._is_duplicate(800, 900, threshold=50), "不应判定为重复"
    print("  远距离不去重: 通过")

    # 边界测试
    assert engine._is_duplicate(100 + 25, 200 + 24, threshold=50), "边界应去重"
    print("  边界值去重: 通过")

if __name__ == '__main__':
    test_color_detection()
    test_deduplication()
    test_automation_engine()

    print("\n" + "=" * 50)
    print("所有测试完成")
    print("=" * 50)
