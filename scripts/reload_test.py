"""测试 reload() 和追问对齐"""
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
    "toxic_review": "编得比小说精彩，造假者智商税收得彻底。",
    "flaw_list": ["时间线矛盾", "无权威来源"],
    "one_line_summary": "一坨假新闻。",
    "claim_verification": [{"claim": "某官员被捕", "verdict": "✗ 伪造", "effective_sources": 0, "best_source_type": "none", "note": "无报道"}],
}

SUMMARY = {
    "_mode": "summary",
    "headline": "科学家发现新型电池材料续航提升40%",
    "core_idea": "作者认为固态电池技术已接近商业化临界点，主张投资者应关注这一赛道。",
    "key_points": ["实验室条件下能量密度提升40%", "成本较低有望3年内量产", "仍处原型阶段"],
    "original_language": "zh",
    "bias_note": "来源为企业自发PR稿",
}

CHAT_HISTORY = [
    {"user": "这个造假的目的是什么？", "ai": "根据传播链分析，这条内容的目的是制造恐慌情绪，引导受众点击钓鱼链接。造假者利用了真实事件的部分细节加以包装，属于典型的「真实外壳+虚假核心」手法。"},
    {"user": "有没有反例？", "ai": "有。同一时期该地区的官方媒体发布了完全不同的版本，且警方通报中并无相关记录。这两条反例已在侦查报告的破绽列表中列出。"},
]

step = [0]
win = None

def run():
    global win
    # 步骤1：打开 analyze 窗口，展开追问，添加历史对话
    win = ResultWindow(ANALYZE, position=None, history_id="test-id-1",
                       chat_history=CHAT_HISTORY)
    win._toggle_chat_panel()
    win.show()
    print("[1] analyze 窗口已打开，追问面板展开，历史对话已填充")
    QTimer.singleShot(800, step2)

def step2():
    # 截图：analyze + 追问
    px = win.grab()
    px.save("tests/reload_test_1_analyze.png")
    print("[2] analyze+追问截图已保存")
    QTimer.singleShot(200, step3)

def step3():
    # 步骤3：reload 为 summary 模式（跨模式切换）
    win.reload(result=SUMMARY, image=None, history_id="test-id-2", chat_history=[])
    print("[3] reload() 完成，切换到 summary 模式")
    QTimer.singleShot(600, step4)

def step4():
    # 截图：summary（追问面板保持打开状态）
    px = win.grab()
    px.save("tests/reload_test_2_summary.png")
    chat_visible = win._chat_panel.isVisible()
    print(f"[4] summary+追问截图已保存，追问面板可见={chat_visible}")
    QTimer.singleShot(200, step5)

def step5():
    # 步骤5：再 reload 回 analyze，带追问历史
    win.reload(result=ANALYZE, image=None, history_id="test-id-1",
               chat_history=CHAT_HISTORY)
    print("[5] reload() 回 analyze")
    QTimer.singleShot(600, step6)

def step6():
    px = win.grab()
    px.save("tests/reload_test_3_back_analyze.png")
    print("[6] 回到 analyze 截图已保存")
    print("\n=== 所有截图已保存，请检查 tests/ 目录 ===")
    app.quit()

QTimer.singleShot(200, run)
sys.exit(app.exec())
