"""专项测试：追问气泡对齐 + 底色宽度"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from ui.result_window import ResultWindow

app = QApplication(sys.argv)

ANALYZE = {
    "_mode": "analyze",
    "header": {"bullshit_index": 72, "truth_label": "高度可疑", "risk_level": "🔶 高度警惕", "verdict": "时间线矛盾"},
    "radar_chart": {"logic_consistency": 2, "source_authority": 1, "agitation_level": 4, "search_match": 1},
    "investigation_report": {"content_nature": "社交媒体截图", "time_check": "矛盾", "entity_check": "可疑", "physics_check": "正常", "source_independence_note": "0个有效信源"},
    "toxic_review": "编得比小说精彩。",
    "flaw_list": ["时间线矛盾", "无权威来源"],
    "one_line_summary": "一坨假新闻。",
    "claim_verification": [{"claim": "某官员被捕", "verdict": "✗ 伪造", "effective_sources": 0, "best_source_type": "none", "note": "无报道"}],
}

CHAT = [
    {"user": "宇树没来吗?", "ai": "宇树确实去了，但他们不是以独立参展商的身份在大搞自己的发布会，而是作为「跨界嘉宾」出现在松下（Panasonic）的展位上。\n\n在 2024 AWE 现场，宇树的机器人在松下洗护展区担任了「特邀推荐官」。它们现场表演了挥手、握手、合影，甚至还给松下的洗衣机跳舞点赞，以此来展示家电品牌对未来科技感和智能化的追求。"},
    {"user": "有反例吗?", "ai": "有。同一时期该地区的官方媒体发布了完全不同的版本。"},
]

win = None

def run():
    global win
    win = ResultWindow(ANALYZE, position=None, history_id="test", chat_history=CHAT)
    win._toggle_chat_panel()
    win.show()
    QTimer.singleShot(600, screenshot)

def screenshot():
    # 截聊天面板部分
    chat_panel = win._chat_panel
    px = chat_panel.grab()
    px.save("tests/chat_align_test.png")
    print("saved tests/chat_align_test.png")
    app.quit()

QTimer.singleShot(200, run)
sys.exit(app.exec())
