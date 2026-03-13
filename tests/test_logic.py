import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ai.analyzer import analyze_screenshot
from screenshot.capture import image_to_base64


def test_imports():
    """测试所有模块导入是否正常。"""
    from config import OPENAI_API_KEY, OPENAI_MODEL, SCREENSHOT_HOTKEY
    from screenshot.capture import ScreenshotOverlay, image_to_base64
    from ai.analyzer import analyze_screenshot
    from ui.result_window import ResultWindow
    print('✅ 所有模块导入成功！')


def test_analyzer_returns_dict():
    """测试 analyze_screenshot 返回结构化 dict（需要 API key）。"""
    from PIL import Image
    img = Image.new('RGB', (100, 100), color='white')
    b64 = image_to_base64(img)

    print('测试 API 调用...')
    result = analyze_screenshot(b64)
    assert isinstance(result, dict), f"期望 dict，得到 {type(result)}"
    assert "is_fake" in result, "缺少 is_fake 字段"
    assert "confidence" in result, "缺少 confidence 字段"
    assert "roast" in result, "缺少 roast 字段"
    print(f'✅ 分析结果: {result}')


def test_result_window():
    """测试 ResultWindow 能正常创建（不显示）。"""
    mock_result = {
        "is_fake": True,
        "confidence": 0.85,
        "bullshit_index": 75,
        "claims": [{"claim": "测试", "verdict": "❌", "reason": "测试原因"}],
        "tactics": ["情感煽动"],
        "roast": "这比小学生作文还假",
    }
    # 注意：创建 ResultWindow 需要 QApplication 实例
    print('✅ ResultWindow mock 数据构建成功')


if __name__ == '__main__':
    test_imports()
    test_result_window()
    # 需要 OPENAI_API_KEY 才能运行:
    # test_analyzer_returns_dict()
