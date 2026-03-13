"""
analyzer.py —— 对外唯一入口，保持接口签名不变。

内部通过 ConfigManager + Provider 工厂完成解耦，
上层调用者（main.py、tests/）无需感知底层模型。

公开接口：
  analyze_screenshot(image_base64)  — 来自截图遮罩的 base64 流（GUI 调用）
  analyze_image(image_path)         — 来自本地文件路径（测试 / 批处理调用）
"""

import base64
import io

from config.manager import load as load_config
from ai.providers import get_provider


def _load_provider():
    return get_provider(load_config())


def analyze_screenshot(image_base64: str) -> dict:
    """
    分析截图内容真实性（GUI 主链路）。

    Args:
        image_base64: PNG 图片的 base64 字符串（不含 data:image 前缀）
    """
    return _load_provider().analyze(image_base64)


def analyze_image(image_path: str) -> dict:
    """
    从本地文件路径分析图片真实性（测试 / 批处理链路）。

    Args:
        image_path: 本地图片路径（支持 PNG / JPG / BMP 等 Pillow 可读格式）

    Returns:
        标准化结果字典（is_fake, bullshit_index, toxic_review 等字段）
    """
    from PIL import Image

    img = Image.open(image_path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    image_base64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return _load_provider().analyze(image_base64)
