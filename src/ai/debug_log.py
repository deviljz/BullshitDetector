"""
debug_log.py — 全链路调试日志

每次 AI 调用（鉴定/解释/总结/求出处）写一条 JSONL 到 logs/debug.jsonl，
记录：发送的 prompt、每轮工具调用+搜索结果、模型返回、token 消耗。
用于事后复盘 bug，不影响主流程。
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _sanitize(obj, _depth=0):
    """
    递归处理日志对象：
    - image_url 的 data:image base64 替换为占位符
    - 超长字符串截断
    """
    if _depth > 8:
        return "..."
    if isinstance(obj, str):
        if obj.startswith("data:image") and len(obj) > 200:
            return f"[IMAGE_B64 ~{len(obj)} chars]"
        if len(obj) > 3000:
            return obj[:3000] + f"...[{len(obj)} total]"
        return obj
    if isinstance(obj, list):
        return [_sanitize(i, _depth + 1) for i in obj]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "url" and isinstance(v, str) and v.startswith("data:image"):
                out[k] = f"[IMAGE_B64 ~{len(v)} chars]"
            else:
                out[k] = _sanitize(v, _depth + 1)
        return out
    return obj


def sanitize_messages(messages: list) -> list:
    """返回消息列表的安全副本（替换 base64 图片）。"""
    return _sanitize(messages)


def _get_log_path() -> str:
    try:
        from config.manager import load as load_config
        cfg = load_config()
        log_dir = cfg.get("debug_log_dir", "logs")
    except Exception:
        log_dir = "logs"
    Path(log_dir).mkdir(exist_ok=True)
    return os.path.join(log_dir, "debug.jsonl")


def make_entry(mode: str, input_info: dict) -> dict:
    """创建一条空的调试日志 entry。"""
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "path": "unknown",
        "input": input_info,
        "stages": [],
        "result_summary": {},
        "total_tokens": {"input": 0, "output": 0},
    }


def set_result(entry: dict, result: dict, token_dict: dict, path: str = ""):
    """将最终结果摘要写入 entry。支持所有模式（analyze/summary/explain/source）。"""
    if path:
        entry["path"] = path
    entry["total_tokens"] = {
        "input": token_dict.get("input", 0),
        "output": token_dict.get("output", 0),
    }
    hdr = result.get("header") or {}
    cv = result.get("claim_verification") or []
    summary: dict = {"mode": result.get("_mode")}
    if hdr.get("bullshit_index") is not None:
        summary["bullshit_index"] = hdr["bullshit_index"]
    if hdr.get("risk_level"):
        summary["risk_level"] = hdr["risk_level"]
    if hdr.get("verdict"):
        summary["verdict"] = hdr["verdict"]
    if cv:
        summary["claim_count"] = len(cv)
        summary["fake_count"] = sum(1 for c in cv if "\u2717" in c.get("verdict", ""))
    # 其他模式字段
    for key in ("headline", "title", "subject", "found", "confidence"):
        if result.get(key) is not None:
            summary[key] = result[key]
    if result.get("error"):
        summary["error"] = result["error"]
    entry["result_summary"] = summary


def write_entry(entry: dict):
    """追加写一条 JSONL。从不抛异常。"""
    try:
        with open(_get_log_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[debug_log] write failed: {e}")
