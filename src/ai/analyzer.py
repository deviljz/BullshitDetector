"""
analyzer.py —— 对外唯一入口，保持接口签名不变。

内部通过 ConfigManager + Provider 工厂完成解耦，
上层调用者（main.py、tests/）无需感知底层模型。

公开接口：
  analyze_screenshot(image_base64)  — 来自截图遮罩的 base64 流（GUI 调用）
  analyze_image(image_path)         — 来自本地文件路径（测试 / 批处理调用）
  analyze_text(text)                — 文章/声明文字鉴定（文字/链接分析链路）
"""

import base64
import io

from config.manager import load as load_config
from ai.providers import get_provider


def _load_provider():
    return get_provider(load_config())


def analyze_screenshot(images: list[str]) -> dict:
    """分析截图内容真实性。images 为 base64 字符串列表（可多张）。"""
    return _load_provider().analyze(images)


def analyze_text(text: str) -> dict:
    """分析文章/声明文字的可信度。"""
    return _load_provider().analyze_article(text)


def summarize_screenshot(images: list[str]) -> dict:
    """截图内容一键总结（中文输出，外文自动翻译）。"""
    return _load_provider().summarize(images)


def summarize_text(text: str) -> dict:
    """文章/声明一键总结（中文输出，外文自动翻译）。"""
    return _load_provider().summarize_article(text)


def explain_screenshot(images: list[str]) -> dict:
    """截图内容一键解释（中文输出）。"""
    return _load_provider().explain(images)


def explain_text(text: str) -> dict:
    """文章/文字内容一键解释（中文输出）。"""
    return _load_provider().explain_article(text)


def analyze_image(image_path: str) -> dict:
    """从本地文件路径分析图片真实性（测试 / 批处理链路）。"""
    from PIL import Image

    img = Image.open(image_path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return _load_provider().analyze([b64])
