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


def source_find_screenshot(images: list[str]) -> dict:
    """识别截图来自哪部作品（动漫/游戏/电影等）。"""
    return _load_provider().source_find(images)


def source_find_text(text: str) -> dict:
    """根据文字描述识别来自哪部作品。"""
    return _load_provider().source_find_article(text)


def _result_to_context(result: dict) -> str:
    """Serialize a result dict to a plain-text context string for follow-up."""
    mode = result.get("_mode", "analyze")
    lines = []
    if mode == "analyze":
        h = result.get("header", {})
        if h.get("verdict"):
            lines.append(f"鉴定结论：{h['verdict']}")
        if h.get("risk_level"):
            lines.append(f"风险级别：{h['risk_level']}")
        if result.get("toxic_review"):
            lines.append(f"核查评语：{result['toxic_review']}")
        for c in result.get("claim_verification", []):
            lines.append(f"声明：{c.get('verdict', '')} {c.get('claim', '')}  {c.get('note', '')}")
        for f in result.get("flaw_list", []):
            lines.append(f"破绽：{f}")
    elif mode == "summary":
        if result.get("headline"):
            lines.append(f"标题：{result['headline']}")
        for pt in result.get("key_points", []):
            lines.append(f"要点：{pt}")
        if result.get("bias_note"):
            lines.append(f"偏向备注：{result['bias_note']}")
    elif mode == "explain":
        if result.get("subject"):
            lines.append(f"主题：{result['subject']}")
        if result.get("short_answer"):
            lines.append(f"简短回答：{result['short_answer']}")
        if result.get("detail"):
            lines.append(f"详细说明：{result['detail']}")
        if result.get("origin"):
            lines.append(f"来源：{result['origin']}")
    elif mode == "source":
        lines.append(f"作品名：{result.get('title', '')} ({result.get('original_title', '')})")
        lines.append(f"类型：{result.get('media_type', '')}  年份：{result.get('year', '')}  制作：{result.get('studio', '')}")
        if result.get("episode"):
            lines.append(f"集数：{result.get('episode', '')} {result.get('episode_title', '')}")
        if result.get("scene"):
            lines.append(f"场景：{result['scene']}")
        if result.get("characters"):
            lines.append(f"角色：{', '.join(result['characters'])}")
        if result.get("note"):
            lines.append(f"备注：{result['note']}")
    return "\n".join(l for l in lines if l.strip())


def follow_up_text(result: dict, history: list[dict], question: str) -> str:
    """Ask a follow-up question about a previous analysis result."""
    context = _result_to_context(result)
    mode = result.get("_mode", "analyze")
    return _load_provider().follow_up(context, history, question, mode)


def analyze_image(image_path: str) -> dict:
    """从本地文件路径分析图片真实性（测试 / 批处理链路）。"""
    from PIL import Image

    img = Image.open(image_path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return _load_provider().analyze([b64])
