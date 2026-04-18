"""
python_ref_capture.py — 抓取 Python 版所有 UI 截图作为 Flutter 对比的黄金标准。
输出到 tests/python_ref/ 目录，每次执行覆盖（一次性固定参考）。

运行方式：
    cd F:/Project/BullshitDetector
    .venv/Scripts/python tests/python_ref_capture.py
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QPixmap

OUT = Path(__file__).parent / "python_ref"
OUT.mkdir(exist_ok=True)

app = QApplication(sys.argv)
app.setStyle("Fusion")
app.setQuitOnLastWindowClosed(False)  # prevent auto-quit when a window closes

_queue: list = []   # list of (delay_ms, fn)
_done_count = [0]

def _save(widget, name: str):
    path = str(OUT / name)
    px: QPixmap = widget.grab()
    px.save(path)
    print(f"  [OK] {name}  ({px.width()}x{px.height()})")

def _schedule(delay_ms: int, fn):
    _queue.append((delay_ms, fn))

def _run_queue():
    if not _queue:
        app.quit()
        return
    delay, fn = _queue.pop(0)
    QTimer.singleShot(delay, lambda: (_run_fn(fn), _run_queue()))

def _run_fn(fn):
    try:
        fn()
    except Exception as e:
        print(f"  [ERR] {e}")

# ─────────────────────────────────────────────────────────────────────────────
# Mock data (mirrors result_window_test.py)
# ─────────────────────────────────────────────────────────────────────────────

RESULT_ANALYZE = {
    "header": {
        "bullshit_index": 72,
        "truth_label": "高度可疑",
        "risk_level": "⚠️ 高度存疑",
        "verdict": "✗ 伪造",
    },
    "radar_chart": {"logic_consistency": 2, "source_authority": 1,
                    "agitation_level": 4, "search_match": 1},
    "investigation_report": {
        "content_nature": "社交媒体截图",
        "time_check": "时间线存在矛盾",
        "entity_check": "无法核实发文账号真实性",
        "physics_check": "正常",
    },
    "toxic_review": "这条消息编得比小说还精彩，发文时间、账号信息全都对不上，造假者的智商税收得相当彻底。",
    "flaw_list": ["时间线矛盾", "无权威媒体背书", "账号注册时间可疑"],
    "one_line_summary": "一坨披着突发新闻外皮的、发着恶臭的智商税。",
    "claim_verification": [
        {"claim": "某官员于2025年1月被反腐部门带走调查", "verdict": "✗ 伪造",
         "effective_sources": 0, "best_source_type": "none",
         "note": "搜索多个关键词，无任何官方媒体报道",
         "sources": [{"url": "https://example.com/1", "title": "人民日报官方辟谣：该消息不实"}]},
        {"claim": "涉案金额逾10亿元", "verdict": "? 无法核实",
         "effective_sources": 0, "best_source_type": "none",
         "note": "无来源，数字疑似捏造", "sources": []},
    ],
    "dimension_scores": {"逻辑一致性": 25, "信源权威性": 15, "煽动程度": 80, "搜索匹配度": 20},
}

RESULT_SUMMARY = {
    "_mode": "summary",
    "content_type": "news",
    "headline": "科学家发现新型材料可大幅提升电池续航",
    "core_idea": "研究团队发布了一种低成本固态电池材料，在实验室条件下能量密度提升40%，商业化预计3年内落地。",
    "key_points": [],
    "structured_outline": [],
    "timeline": [
        {"time": "2024-11", "event": "研究团队完成实验室样品制备"},
        {"time": "2025-01", "event": "论文发表于《Nature Energy》"},
        {"time": "2025-03", "event": "某车企宣布合作量产研究"},
    ],
    "key_quote": "We achieved a 40% increase in energy density without significant cost increase.",
    "bias_note": "来源为企业自发布新闻稿，缺乏独立同行评审",
    "original_language": "en",
}

RESULT_EXPLAIN = {
    "_mode": "explain",
    "type": "meme",
    "subject": "I'm not a cat",
    "short_answer": "2021年美国律师开庭时意外开启猫咪滤镜无法关闭的名场面",
    "detail": "2021年1月，美国德州一名律师罗德·庞巴尔在视频庭审时，因助手不小心开启了猫咪 Zoom 滤镜。整个庭审过程他以猫的形象出现，并一度声称「I'm not a cat, I'm here live, I'm not a cat」，引发全球热议。",
    "origin": "2021年1月德州法庭视频庭审事故",
    "usage": "用于形容身份认证失败、技术事故或尴尬处境",
    "still_active": True,
    "cultural_note": "该梗折射出远程办公时代技术失控的普遍焦虑。",
    "original_language": "en",
}

RESULT_SOURCE = {
    "_mode": "source",
    "_subtype": "anime",
    "found": True,
    "title": "孤独摇滚！",
    "original_title": "ぼっち・ざ・ろっく！",
    "media_type": "anime",
    "year": "2022",
    "studio": "CloverWorks",
    "confidence": "high",
    "description": "讲述内向少女后藤一里（Bocchi）加入乐队、克服社交恐惧的成长故事。",
    "where_to_watch": ["Netflix", "Crunchyroll"],
    "sources": [{"url": "https://example.com/bocchi", "title": "孤独摇滚官网"}],
}

MOCK_HISTORY = [
    {
        "id": "hist001",
        "ts": "2025-03-20T10:23:00",
        "mode": "analyze",
        "input_text": "Apple revenue 394 billion dollars 2023. Record breaking year according to CEO Cook.",
        "result": RESULT_ANALYZE,
    },
    {
        "id": "hist002",
        "ts": "2025-03-19T15:44:00",
        "mode": "summary",
        "input_text": "科学家发现新型固态电池材料，能量密度提升40%",
        "result": RESULT_SUMMARY,
    },
    {
        "id": "hist003",
        "ts": "2025-03-18T09:10:00",
        "mode": "explain",
        "input_text": "I'm not a cat",
        "result": RESULT_EXPLAIN,
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Captures
# ─────────────────────────────────────────────────────────────────────────────

_open_widgets = []   # keep references alive

def cap_input_empty():
    """输入窗口——空白状态"""
    from ui.unified_input_dialog import UnifiedInputDialog
    w = UnifiedInputDialog()
    w.show()
    _open_widgets.append(w)
    QTimer.singleShot(400, lambda: (_save(w, "py_input_empty.png"), w.close()))

def cap_input_with_text():
    """输入窗口——已填入文字"""
    from ui.unified_input_dialog import UnifiedInputDialog
    w = UnifiedInputDialog()
    w.show()
    _open_widgets.append(w)
    # Set text via the text edit widget
    try:
        te = w.findChild(__import__('PyQt6.QtWidgets', fromlist=['QTextEdit']).QTextEdit)
        if te:
            te.setPlainText("Apple revenue 394 billion dollars 2023. Record breaking year according to CEO Cook.")
    except Exception:
        pass
    QTimer.singleShot(400, lambda: (_save(w, "py_input_with_text.png"), w.close()))

def cap_loading(mode: str, stages: list[str], out_name: str):
    """LoadingOverlay 各模式"""
    import ui.loading_overlay as _lo_mod
    from ui.loading_overlay import LoadingOverlay
    from PyQt6.QtCore import QTimer as _QT
    overlay = LoadingOverlay(mode)
    _lo_mod._active_overlay = overlay
    overlay.show()
    _open_widgets.append(overlay)
    idx = [0]
    t = _QT()
    def tick():
        if idx[0] < len(stages):
            _lo_mod.update_stage(stages[idx[0]])
            idx[0] += 1
        else:
            t.stop()      # stop FIRST to prevent further calls
            _save(overlay, out_name)
            overlay.close()
    t.setInterval(120)
    t.timeout.connect(tick)
    t.start()
    _open_widgets.append(t)
    return t

def cap_result(result: dict, out_name: str, with_chat: bool = False):
    """ResultWindow 各模式"""
    from ui.result_window import ResultWindow
    w = ResultWindow(result, position=None, image=None)
    w.show()
    _open_widgets.append(w)
    delay = 600
    if with_chat:
        def _open_chat():
            # Toggle chat panel if button exists
            from PyQt6.QtWidgets import QPushButton
            for btn in w.findChildren(QPushButton):
                if '追问' in btn.text() or 'chat' in btn.objectName().lower():
                    btn.click()
                    break
        QTimer.singleShot(400, _open_chat)
        delay = 900
    QTimer.singleShot(delay, lambda: (_save(w, out_name), w.close()))

def cap_history():
    """HistoryWindow with mock entries"""
    from ui.history_window import HistoryWindow
    w = HistoryWindow()
    # Inject mock data directly
    try:
        w._all_entries = MOCK_HISTORY
        w._render_entries(MOCK_HISTORY)
    except Exception:
        pass
    w.show()
    _open_widgets.append(w)
    QTimer.singleShot(600, lambda: (_save(w, "py_history.png"), w.close()))

def cap_usage():
    """UsageWindow — may be empty if no real usage.json"""
    from ui.usage_window import UsageWindow
    w = UsageWindow()
    w.show()
    _open_widgets.append(w)
    QTimer.singleShot(800, lambda: (_save(w, "py_usage.png"), w.close()))


# ─────────────────────────────────────────────────────────────────────────────
# Schedule all captures (sequential via delay accumulation)
# ─────────────────────────────────────────────────────────────────────────────

LOADING_STAGES = ["提取关键声明", "核查：Apple revenue 394B…", "搜索：CEO Cook statement", "综合分析中"]

captures = [
    (200,  cap_input_empty),
    (1200, cap_input_with_text),
    (1200, lambda: cap_loading("analyze", LOADING_STAGES, "py_loading_analyze.png")),
    (1800, lambda: cap_loading("summary", ["解析结构", "提取大纲", "生成摘要中"], "py_loading_summary.png")),
    (1800, lambda: cap_loading("explain", ["识别内容", "检索来源", "生成解释中"], "py_loading_explain.png")),
    (1800, lambda: cap_loading("source",  ["提取特征", "以图搜图", "匹配数据库中"], "py_loading_source.png")),
    (1800, lambda: cap_result(RESULT_ANALYZE,  "py_result_analyze.png")),
    (1500, lambda: cap_result(RESULT_SUMMARY,  "py_result_summary.png")),
    (1500, lambda: cap_result(RESULT_EXPLAIN,  "py_result_explain.png")),
    (1500, lambda: cap_result(RESULT_SOURCE,   "py_result_source.png")),
    (1500, lambda: cap_result(RESULT_ANALYZE,  "py_result_chat.png", with_chat=True)),
    (1800, cap_history),
    (1500, cap_usage),
]

print("=" * 60)
print("Python 参考截图抓取")
print(f"输出目录: {OUT}")
print("=" * 60)

# Run all captures sequentially with accumulated delay
total_delay = 0
for delay, fn in captures:
    total_delay += delay
    QTimer.singleShot(total_delay, fn)

# Quit after all are done
QTimer.singleShot(total_delay + 2000, app.quit)

sys.exit(app.exec())
