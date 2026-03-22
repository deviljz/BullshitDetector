"""
debug_log.py — 全链路调试日志（精简版）

每次 AI 调用写一条 JSONL 到 logs/debug.jsonl。
每条记录包含：call_id、mode、path、各阶段搜索query+结果摘要+模型回复摘要、token 消耗。
不存完整 system prompt 和 user 消息体，体积小，可用 call_id 与历史记录对应。
"""

import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path


def _get_log_dir() -> str:
    try:
        from config.manager import load as load_config
        cfg = load_config()
        log_dir = cfg.get("debug_log_dir", "logs")
    except Exception:
        log_dir = "logs"
    Path(log_dir).mkdir(exist_ok=True)
    return log_dir


def sanitize_messages(messages: list) -> list:
    """替换 base64 图片为占位符（供外部调用，内部已不存完整 messages）。"""
    out = []
    for msg in messages:
        if not isinstance(msg, dict):
            out.append(msg)
            continue
        content = msg.get("content")
        if isinstance(content, list):
            parts = []
            for p in content:
                if isinstance(p, dict) and p.get("type") == "image_url":
                    url = p.get("image_url", {}).get("url", "")
                    parts.append({"type": "image_url", "size": len(url)})
                else:
                    parts.append(p)
            out.append({**msg, "content": parts})
        else:
            out.append(msg)
    return out


def _user_hint(messages: list) -> str:
    """从 messages 中提取第一条 user 消息的文字摘要（前 150 字）。"""
    for msg in messages:
        if isinstance(msg, dict) and msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        return part.get("text", "")[:150]
            elif isinstance(content, str):
                return content[:150]
    return ""


def make_entry(mode: str, input_info: dict) -> dict:
    """创建一条调试日志 entry，含唯一 call_id。"""
    call_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
    return {
        "call_id": call_id,
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "path": "unknown",
        "input": input_info,
        "stages": [],
        "result_summary": {},
        "total_tokens": {"input": 0, "output": 0},
        "_t0": time.monotonic(),
    }


def make_stage(name: str, messages: list | None = None) -> dict:
    """创建精简 stage dict，可选从 messages 提取 user_hint。"""
    stage: dict = {"name": name, "tool_calls": [], "response": "", "tokens": {}, "_t0": time.monotonic()}
    if messages:
        hint = _user_hint(messages)
        if hint:
            stage["user_hint"] = hint
    return stage


def finish_stage(stage: dict) -> None:
    """记录 stage 耗时（秒），移除内部计时字段。"""
    t0 = stage.pop("_t0", None)
    if t0 is not None:
        stage["elapsed_s"] = round(time.monotonic() - t0, 2)


def set_result(entry: dict, result: dict, token_dict: dict, path: str = ""):
    """将最终结果摘要写入 entry，同时把 call_id 写回 result。"""
    if path:
        entry["path"] = path
    t0 = entry.pop("_t0", None)
    if t0 is not None:
        entry["total_elapsed_s"] = round(time.monotonic() - t0, 2)
    entry["total_tokens"] = {
        "input": token_dict.get("input", 0),
        "output": token_dict.get("output", 0),
    }
    # 把 call_id 和日志文件名写进 result，供 history 存储做关联
    result["_call_id"] = entry["call_id"]
    result["_log_file"] = f"{entry['call_id']}.json"

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
    for key in ("headline", "title", "subject", "found", "confidence"):
        if result.get(key) is not None:
            summary[key] = result[key]
    if result.get("error"):
        summary["error"] = result["error"]
    entry["result_summary"] = summary


def write_entry(entry: dict):
    """每次调用写一个独立 JSON 文件（logs/<call_id>.json）。从不抛异常。"""
    try:
        log_dir = _get_log_dir()
        path = os.path.join(log_dir, f"{entry['call_id']}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[debug_log] write failed: {e}")
