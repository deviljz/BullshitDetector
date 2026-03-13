"""JSON 解析工具 —— 5 级容错解析，应对各种模型输出异常"""

import ast
import json
import re


def _extract_json_candidate(text: str) -> str:
    """从文本中提取最可能是 JSON 的片段"""
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end >= start:
        return text[start : end + 1]
    return text


def _regex_extract_fields(text: str) -> dict:
    """当 JSON 解析完全失败时，用正则逐字段提取，构建新 schema 结构"""

    def _grab_int(pattern, default=50):
        m = re.search(pattern, text)
        return int(m.group(1)) if m else default

    def _grab_str(pattern, default=""):
        m = re.search(pattern, text, re.DOTALL)
        return m.group(1).strip().strip('"').strip("'") if m else default

    bs = _grab_int(r'"bullshit_index"\s*:\s*([0-9]+)')
    risk = _risk_level(bs)

    return {
        "header": {
            "bullshit_index": bs,
            "truth_label": _grab_str(r'"truth_label"\s*:\s*"(.*?)"') or "未知",
            "risk_level": risk,
            "verdict": _grab_str(r'"verdict"\s*:\s*"(.*?)"') or "解析失败",
        },
        "radar_chart": {
            "logic_consistency": _grab_int(r'"logic_consistency"\s*:\s*([0-5])'),
            "source_authority": _grab_int(r'"source_authority"\s*:\s*([0-5])'),
            "agitation_level": _grab_int(r'"agitation_level"\s*:\s*([0-5])'),
            "search_match": _grab_int(r'"search_match"\s*:\s*([0-5])'),
        },
        "investigation_report": {
            "time_check": _grab_str(r'"time_check"\s*:\s*"(.*?)"') or "未核查",
            "entity_check": _grab_str(r'"entity_check"\s*:\s*"(.*?)"') or "未核查",
            "physics_check": _grab_str(r'"physics_check"\s*:\s*"(.*?)"') or "未核查",
        },
        "toxic_review": _grab_str(r'"toxic_review"\s*:\s*"(.*?)"') or "鉴屎官正在修炼",
        "flaw_list": [],
        "one_line_summary": _grab_str(r'"one_line_summary"\s*:\s*"(.*?)"') or "解析失败",
    }


def _risk_level(bs: int) -> str:
    if bs <= 30:
        return "✅ 基本可信"
    if bs <= 55:
        return "⚠️ 有所存疑"
    if bs <= 80:
        return "🔶 高度警惕"
    return "🚨 极度危险"


def parse_json(text: str) -> dict:
    """
    从模型响应中提取并解析 JSON，兼容各种格式异常。
    5 级降级：直接解析 → 剥 Markdown → json_repair → ast → 正则兜底
    """
    text = text.strip()

    # 1. 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. 剥离 Markdown 标记后提取 { ... } 片段
    candidate = _extract_json_candidate(text)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # 3. json_repair 修复
    try:
        from json_repair import repair_json  # type: ignore
        repaired = repair_json(candidate)
        if repaired:
            parsed = json.loads(repaired)
            if isinstance(parsed, dict):
                return parsed
    except Exception:
        pass

    # 4. ast.literal_eval（单引号 JSON 变体）
    try:
        parsed = ast.literal_eval(candidate)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # 5. 正则逐字段兜底
    return _regex_extract_fields(text)


def normalize_result(result: dict) -> dict:
    """填充缺失字段，确保新 schema 所有必要字段存在"""
    # 兼容旧格式：若模型返回了旧字段，自动迁移
    if "bullshit_index" in result and "header" not in result:
        result = _migrate_old_schema(result)

    header = result.setdefault("header", {})
    bs = header.setdefault("bullshit_index", 50)
    header.setdefault("truth_label", "未知")
    header.setdefault("risk_level", _risk_level(bs))
    header.setdefault("verdict", "无法判断")

    radar = result.setdefault("radar_chart", {})
    radar.setdefault("logic_consistency", 3)
    radar.setdefault("source_authority", 3)
    radar.setdefault("agitation_level", 3)
    radar.setdefault("search_match", 3)

    report = result.setdefault("investigation_report", {})
    report.setdefault("time_check", "未核查")
    report.setdefault("entity_check", "未核查")
    report.setdefault("physics_check", "未核查")

    result.setdefault("toxic_review", "鉴屎官罢工了")
    result.setdefault("flaw_list", [])
    result.setdefault("one_line_summary", "无法总结")

    return result


def _migrate_old_schema(old: dict) -> dict:
    """将旧版 flat schema 迁移到新版 nested schema（向后兼容）"""
    bs = old.get("bullshit_index", 50)
    return {
        "header": {
            "bullshit_index": bs,
            "truth_label": old.get("truth_index", "未知"),
            "risk_level": _risk_level(bs),
            "verdict": old.get("roast", old.get("toxic_review", "")[:40]),
        },
        "radar_chart": {
            "logic_consistency": 3,
            "source_authority": 3,
            "agitation_level": 3,
            "search_match": 3,
        },
        "investigation_report": {
            "time_check": "未核查（旧格式迁移）",
            "entity_check": "未核查（旧格式迁移）",
            "physics_check": "未核查（旧格式迁移）",
        },
        "toxic_review": old.get("toxic_review", old.get("roast", "鉴屎官罢工了")),
        "flaw_list": old.get("flaw_analysis", []),
        "one_line_summary": old.get("roast", "无法总结"),
        "_search_log": old.get("_search_log", []),
    }
