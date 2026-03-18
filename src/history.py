"""history.py —— 本地历史记录存储（NDJSON，最新在前）"""

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

# 与 config.json 同目录
if getattr(sys, "frozen", False):
    _HISTORY_FILE = Path(sys.executable).parent / "history.json"
else:
    _HISTORY_FILE = Path(__file__).parent.parent / "history.json"

_MODE_LABELS = {
    "analyze": "🔍 鉴屎官",
    "summary": "📝 总结",
    "explain": "❓ 解释",
    "source":  "🎬 求出处",
}


def _derive_title(result: dict) -> str:
    mode = result.get("_mode", "analyze")
    if mode == "summary":
        return (result.get("headline") or "")[:60]
    elif mode == "explain":
        return (result.get("subject") or "")[:60]
    elif mode == "source":
        title = result.get("title") or ""
        orig = result.get("original_title") or ""
        return (f"{title}（{orig}）" if orig else title)[:60]
    else:  # analyze
        s = result.get("one_line_summary") or ""
        if not s:
            h = result.get("header") or {}
            s = h.get("truth_label") or h.get("verdict") or ""
        return s[:60]


def load_all() -> list[dict]:
    if not _HISTORY_FILE.exists():
        return []
    try:
        return json.loads(_HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_all(entries: list[dict]) -> None:
    _HISTORY_FILE.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add(result: dict, thumbnail: str | None = None) -> str:
    """保存新记录，返回 entry_id。thumbnail 为 JPEG base64 字符串（可选）。"""
    entries = load_all()
    entry_id = str(uuid.uuid4())
    mode = result.get("_mode", "analyze")
    entry = {
        "id": entry_id,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "type_label": _MODE_LABELS.get(mode, mode),
        "title": _derive_title(result),
        "thumbnail": thumbnail,
        "result": result,
        "chat": [],
    }
    entries.insert(0, entry)
    _save_all(entries[:200])
    return entry_id


def update_chat(entry_id: str, chat: list[dict]) -> None:
    entries = load_all()
    for e in entries:
        if e["id"] == entry_id:
            e["chat"] = chat
            break
    _save_all(entries)


def delete(entry_id: str) -> None:
    _save_all([e for e in load_all() if e["id"] != entry_id])


def clear_all() -> None:
    _save_all([])
