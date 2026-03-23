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
import math

from config.manager import load as load_config
from ai.providers import get_provider


def _load_provider():
    return get_provider(load_config())


def _record(session_id, call_type, tokens):
    """Safely record token usage. Never raises."""
    if not session_id:
        return
    try:
        import usage
        usage.record_call(
            session_id,
            call_type,
            tokens.get("model", "unknown"),
            tokens.get("input", 0),
            tokens.get("output", 0),
        )
    except Exception as e:
        print(f"[usage] record failed: {e}")


def analyze_screenshot(images: list[str], extra_text: str = "", session_id: str | None = None) -> dict:
    """分析截图内容真实性。images 为 base64 字符串列表（可多张）。"""
    result, tokens = _load_provider().analyze(images, extra_text)
    _record(session_id, "analyze", tokens)
    return result


def analyze_text(text: str, session_id: str | None = None) -> dict:
    """分析文章/声明文字的可信度（经典单路径）。"""
    result, tokens = _load_provider().analyze_article(text)
    _record(session_id, "analyze", tokens)
    return result


def _has_title_issue(result: dict) -> bool:
    """title_logic_check.verdict == '有问题' 时返回 True。"""
    tlc = (result.get("investigation_report") or {}).get("title_logic_check") or {}
    if isinstance(tlc, dict):
        return "有问题" in (tlc.get("verdict") or "")
    # fallback: 旧格式字符串
    return False


def _enforce_bi_floor(result: dict) -> dict:
    """Enforce bullshit_index floor based on claim_verification verdicts."""
    cv = result.get("claim_verification", []) or []
    fake = sum(1 for c in cv if "\u2717" in c.get("verdict", ""))
    unverified = any("?" in c.get("verdict", "") for c in cv)
    hdr = result.get("header")
    if not isinstance(hdr, dict):
        return result
    bi = hdr.get("bullshit_index", 0) or 0
    if fake >= 2:
        bi = max(bi, 76)
    elif fake >= 1:
        bi = max(bi, 56)
    elif unverified:
        bi = max(bi, 31)
    if _has_title_issue(result):
        bi = min(100, bi + 10)
    hype = (result.get("investigation_report") or {}).get("hype_check") or {}
    if isinstance(hype, dict) and "有夸大" in (hype.get("verdict") or ""):
        hype_type = hype.get("type", "")
        if hype_type == "第三方估算当事实":
            bi = min(100, bi + 10)
        elif hype_type == "绝对化表述":
            bi = min(100, bi + 5)
    hdr["bullshit_index"] = bi
    rl = ("🚨 极度危险" if bi > 80 else
          "🔶 高度警惕" if bi > 55 else
          "⚠️ 有所存疑" if bi > 30 else
          "✅ 基本可信")
    hdr["risk_level"] = rl
    return result


def analyze_screenshot_staged(images: list[str], extra_text: str = "", session_id: str | None = None) -> dict:
    """截图分析（分阶段多 Agent 路径）。"""
    result, tokens = _load_provider().analyze_article_staged(extra_text or "", images)
    _record(session_id, "analyze", tokens)
    return result


def analyze_text_staged(text: str, images: list[str] | None = None, session_id: str | None = None) -> dict:
    """分析文章/声明文字的可信度（分阶段多 Agent 路径）。"""
    result, tokens = _load_provider().analyze_article_staged(text, images)
    _record(session_id, "analyze", tokens)
    return result


def summarize_screenshot(images: list[str], extra_text: str = "", session_id: str | None = None) -> dict:
    """截图内容一键总结（中文输出，外文自动翻译）。"""
    result, tokens = _load_provider().summarize(images, extra_text)
    _record(session_id, "summarize", tokens)
    return result


def summarize_text(text: str, session_id: str | None = None) -> dict:
    """文章/声明一键总结（中文输出，外文自动翻译）。"""
    result, tokens = _load_provider().summarize_article(text)
    _record(session_id, "summarize", tokens)
    return result


def explain_screenshot(images: list[str], extra_text: str = "", session_id: str | None = None) -> dict:
    """截图内容一键解释（中文输出）。"""
    result, tokens = _load_provider().explain(images, extra_text)
    _record(session_id, "explain", tokens)
    return result


def explain_text(text: str, session_id: str | None = None) -> dict:
    """文章/文字内容一键解释（中文输出）。"""
    result, tokens = _load_provider().explain_article(text)
    _record(session_id, "explain", tokens)
    return result


def source_find_screenshot(images: list[str], extra_text: str = "", session_id: str | None = None) -> dict:
    """识别截图来自哪部作品（动漫/游戏/电影等）。"""
    result, tokens = _load_provider().source_find(images, extra_text)
    _record(session_id, "source_find", tokens)
    return result


def source_find_text(text: str, session_id: str | None = None) -> dict:
    """根据文字描述识别来自哪部作品。"""
    result, tokens = _load_provider().source_find_article(text)
    _record(session_id, "source_find", tokens)
    return result


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


def _estimate_context_tokens(result: dict, images: list = None) -> int:
    """Estimate tokens for follow-up context (result text + images)."""
    text = _result_to_context(result)
    text_tokens = len(text) // 2  # rough: 2 chars per token for mixed Chinese
    image_tokens = 0
    if images:
        for img in images:
            try:
                w, h = img.size
                tiles = math.ceil(w / 768) * math.ceil(h / 768)
                image_tokens += tiles * 258
            except Exception:
                image_tokens += 258  # fallback: 1 tile
    return text_tokens + image_tokens


def check_context_fuse(result: dict, images: list = None) -> tuple[bool, int]:
    """Returns (fuse_triggered, estimated_tokens). Fuse triggers when over limit."""
    try:
        cfg = load_config()
        limit = cfg.get("follow_up_context_limit", 30000)
        if limit == 0:
            return False, 0
        estimated = _estimate_context_tokens(result, images)
        return estimated > limit, estimated
    except Exception:
        return False, 0


def follow_up_text(result: dict, history: list[dict], question: str, session_id: str | None = None) -> str:
    """Ask a follow-up question about a previous analysis result."""
    context = _result_to_context(result)
    mode = result.get("_mode", "analyze")
    text, tokens = _load_provider().follow_up(context, history, question, mode)
    _record(session_id, "follow_up", tokens)
    return text


def analyze_image(image_path: str) -> dict:
    """从本地文件路径分析图片真实性（测试 / 批处理链路）。"""
    from PIL import Image

    img = Image.open(image_path).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    result, _ = _load_provider().analyze([b64])
    return result
