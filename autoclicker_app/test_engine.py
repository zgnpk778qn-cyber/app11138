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


def create_test_image():
    img = Image.new('RGB', (1080, 1920), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    draw.rectangle([100, 200, 200, 300], fill=(255, 50, 50))
    draw.rectangle([400, 500, 500, 600], fill=(255, 40, 40))
    draw.rectangle([700, 800, 800, 900], fill=(255, 60, 60))
    draw.rectangle([100, 1000, 200, 1100], fill=(50, 255, 50))
    draw.rectangle([500, 1200, 600, 1300], fill=(40, 255, 40))
    draw.rectangle([300, 1500, 400, 1600], fill=(50, 50, 255))
    return img


def test_color_detection():
    print("=" * 50)
    print("Test 1: Color Detection")
    print("=" * 50)
    img = create_test_image()
    detector = ColorDetector()
    for color in ['红色', '绿色', '蓝色', '橙色', '黄色']:
        regions = detector.find_regions(img, color, min_region=80)
        print(f"  {color}: found {len(regions)} regions")
    return img


def test_deduplication():
    print("\n" + "=" * 50)
    print("Test 2: Click Deduplication")
    print("=" * 50)
    engine = AutomationEngine(None, None, None)
    engine._last_clicks = [(100, 200), (400, 500)]
    assert engine._is_duplicate(105, 198, threshold=50), "Should dedupe close click"
    print("  Close dedupe: PASS")
    assert not engine._is_duplicate(800, 900, threshold=50), "Should NOT dedupe far"
    print("  Far no-dedupe: PASS")
    assert engine._is_duplicate(100 + 25, 200 + 24, threshold=50), "Border dedupe"
    print("  Border dedupe: PASS")


def test_feature_matching():
    print("\n" + "=" * 50)
    print("Test 3: Feature Matching")
    print("=" * 50)
    screen = ScreenController(backend='mock', screen_size=(1080, 1920))
    detector = ColorDetector()
    ocr = OCREngine(font_path=None)
    engine = AutomationEngine(screen, detector, ocr)
    engine.set_target_features([
        {'color': '红色', 'text': '', 'enabled': True},
        {'color': '绿色', 'text': '', 'enabled': True},
        {'color': '蓝色', 'text': '', 'enabled': True},
    ])
    img = create_test_image()
    found = 0
    for feature in engine.target_features:
        regions = engine._find_matching_regions(
            img, feature['color'], feature['text']
        )
        found += len(regions)
    assert found == 6, f"Expected 6 regions, got {found}"
    print(f"  Total: {found} regions -> PASS")


def test_feature_config_roundtrip():
    print("\n" + "=" * 50)
    print("Test 4: Feature Config Filtering")
    print("=" * 50)
    engine = AutomationEngine(None, None, None)
    features = [
        {'color': '红色', 'text': '', 'enabled': True},
        {'color': '绿色', 'text': '确认', 'enabled': True},
        {'color': '', 'text': '完成', 'enabled': True},
        {'color': '蓝色', 'text': '是', 'enabled': False},
    ]
    engine.set_target_features(features)
    assert len(engine.target_features) == 3, f"Disabled should be filtered, got {len(engine.target_features)}"
    print(f"  {len(features)} input -> {len(engine.target_features)} after filter: PASS")

    engine2 = AutomationEngine(None, None, None)
    engine2.set_target_features([
        {'color': '', 'text': '', 'enabled': True},
        {'color': '红色', 'text': '', 'enabled': True},
    ])
    assert len(engine2.target_features) == 1, f"Empty feature should be filtered"
    print(f"  Empty feature filtered: PASS")


def test_automation_engine():
    print("\n" + "=" * 50)
    print("Test 5: Full Automation Cycle (mock)")
    print("=" * 50)
    screen = ScreenController(backend='mock', screen_size=(1080, 1920))
    detector = ColorDetector()
    ocr = OCREngine(font_path=None)
    engine = AutomationEngine(screen, detector, ocr)
    engine.set_target_features([
        {'color': '红色', 'text': '', 'enabled': True},
        {'color': '绿色', 'text': '', 'enabled': True},
    ])
    engine.interval = 0.3
    engine.scroll_interval = 0.5
    engine.max_empty_cycles = 2

    logs = []
    engine.on_log = lambda msg: logs.append(msg)

    test_img = create_test_image()
    original = screen.screenshot
    call_count = [0]
    def mock_screenshot(filename=None):
        call_count[0] += 1
        if call_count[0] <= 2:
            return test_img.copy()
        else:
            return Image.new('RGB', (1080, 1920), color=(240, 240, 240))
    screen.screenshot = mock_screenshot

    engine.start()
    engine.wait_for_completion(timeout=15)

    print(f"  Final state: {engine.state}")
    print(f"  Scrolls: {engine._scroll_count}")
    stopped = engine.state == AutomationEngine.STOPPED
    print(f"  Auto-stop: {'PASS' if stopped else 'FAIL'}")

    scroll_found = any('翻页' in log for log in logs)
    print(f"  Scroll triggered: {'PASS' if scroll_found else 'FAIL'}")

    screen.screenshot = original
    assert stopped, "Engine should auto-stop"


if __name__ == '__main__':
    test_color_detection()
    test_deduplication()
    test_feature_matching()
    test_feature_config_roundtrip()
    test_automation_engine()
    print("\n" + "=" * 50)
    print("All tests completed")
    print("=" * 50)
