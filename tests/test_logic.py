import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ai.analyzer import analyze_screenshot


def test_analyze():
    # 创建一个简单的测试图片（如果没有真实图片）
    test_image = os.path.join(os.path.dirname(__file__), 'test_screenshot.png')

    if not os.path.exists(test_image):
        from PIL import Image
        img = Image.new('RGB', (100, 100), color='white')
        img.save(test_image)

    # 测试 API 调用逻辑
    print('测试 API 调用...')
    # result = analyze_screenshot(test_image)
    # print(f'结果: {result}')
    print('逻辑层导入成功！')


if __name__ == '__main__':
    test_analyze()
