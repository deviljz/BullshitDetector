"""usage.py —— Token 用量记录与查询（存储于 usage.json）"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

if getattr(sys, "frozen", False):
    _USAGE_FILE = Path(sys.executable).parent / "usage.json"
else:
    _USAGE_FILE = Path(__file__).parent.parent / "usage.json"


def _load_all() -> dict:
    if not _USAGE_FILE.exists():
        return {"sessions": []}
    try:
        return json.loads(_USAGE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"sessions": []}


def _save_all(data: dict) -> None:
    _USAGE_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def create_session(session_id: str, mode: str, history_id: str | None = None) -> None:
    """创建新会话记录。"""
    try:
        data = _load_all()
        session = {
            "id": session_id,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "mode": mode,
            "calls": [],
        }
        if history_id:
            session["history_id"] = history_id
        data["sessions"].insert(0, session)
        # 保留最近 1000 个 session
        data["sessions"] = data["sessions"][:1000]
        _save_all(data)
    except Exception as e:
        print(f"[usage] create_session 失败: {e}")


def record_call(
    session_id: str,
    call_type: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> None:
    """记录一次 API 调用的 token 用量。"""
    try:
        data = _load_all()
        call = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "model": model,
            "type": call_type,
            "input": input_tokens,
            "output": output_tokens,
        }
        for session in data["sessions"]:
            if session["id"] == session_id:
                session["calls"].append(call)
                break
        else:
            # session 不存在时自动创建（容错）
            data["sessions"].insert(0, {
                "id": session_id,
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "mode": call_type,
                "calls": [call],
            })
        _save_all(data)
    except Exception as e:
        print(f"[usage] record_call 失败: {e}")


def get_sessions(days: int = 30) -> list[dict]:
    """返回最近 N 天的 session 列表，最新在前。"""
    try:
        data = _load_all()
        cutoff = datetime.now() - timedelta(days=days)
        result = []
        for s in data["sessions"]:
            try:
                started = datetime.fromisoformat(s["started_at"])
                if started >= cutoff:
                    result.append(s)
            except Exception:
                pass
        return result
    except Exception:
        return []


def get_daily_totals(days: int = 30) -> dict:
    """返回 {date_str: {model: {"input": int, "output": int}}} 按天聚合。"""
    try:
        sessions = get_sessions(days)
        totals: dict = {}
        for s in sessions:
            for call in s.get("calls", []):
                try:
                    ts = datetime.fromisoformat(call["ts"])
                    date_str = ts.strftime("%Y-%m-%d")
                    model = call.get("model", "unknown")
                    if date_str not in totals:
                        totals[date_str] = {}
                    if model not in totals[date_str]:
                        totals[date_str][model] = {"input": 0, "output": 0}
                    totals[date_str][model]["input"] += call.get("input", 0)
                    totals[date_str][model]["output"] += call.get("output", 0)
                except Exception:
                    pass
        return totals
    except Exception:
        return {}
