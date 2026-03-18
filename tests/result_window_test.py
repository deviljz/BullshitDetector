"""快速测试 ResultWindow 各模式 + 追问面板布局"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from ui.result_window import ResultWindow

app = QApplication(sys.argv)

MODE = sys.argv[1] if len(sys.argv) > 1 else "analyze"

_RESULTS = {
    "analyze": {
        "header": {
            "bullshit_index": 72,
            "truth_label": "高度可疑",
            "risk_level": "⚠️ 高度存疑",
            "verdict": "✗ 伪造",
        },
        "radar_chart": {"logic_consistency": 2, "source_authority": 1, "agitation_level": 4, "search_match": 1},
        "investigation_report": {
            "content_nature": "社交媒体截图",
            "time_check": "时间线存在矛盾",
            "entity_check": "无法核实发文账号真实性",
            "physics_check": "正常",
        },
        "toxic_review": "这条消息编得比小说还精彩，发文时间、账号信息全都对不上，造假者的智商税收得相当彻底，受害者的好奇心也配合得天衣无缝。",
        "flaw_list": ["时间线矛盾", "无权威媒体背书", "账号注册时间可疑"],
        "one_line_summary": "一坨披着突发新闻外皮的、发着恶臭的智商税。",
        "claim_verification": [
            {"claim": "某官员被捕", "verdict": "✗ 伪造", "effective_sources": 0,
             "best_source_type": "none", "note": "无任何官方媒体报道"},
        ],
        "_search_log": [
            {"tool": "web_search", "query": "某官员被捕 2025", "result_preview": "未找到相关结果"},
        ],
    },
    "summary": {
        "_mode": "summary",
        "headline": "科学家发现新型材料可大幅提升电池续航",
        "key_points": [
            "研究团队在实验室条件下实现了能量密度提升 40%",
            "该材料成本较低，有望在 3 年内量产",
            "目前仍处于原型阶段，商业化尚需验证",
        ],
        "bias_note": "来源为企业自发布新闻稿，缺乏独立同行评审",
        "original_language": "en",
    },
    "explain": {
        "_mode": "explain",
        "type": "meme",
        "subject": "I'm not a cat",
        "short_answer": "2021年美国律师开庭时意外开启猫咪滤镜无法关闭的名场面",
        "detail": "2021年1月，美国德州一名律师罗德·庞巴尔在视频庭审时，因助手不小心开启了猫咪 Zoom 滤镜。整个庭审过程他以猫的形象出现，并一度声称「I'm not a cat, I'm here live, I'm not a cat」，引发全球热议，成为年度最著名网络迷因之一。",
        "origin": "2021年1月德州法庭视频庭审事故",
        "usage": "用于形容身份认证失败、技术事故或尴尬处境",
        "original_language": "en",
    },
    "source": {
        "_mode": "source",
        "found": True,
        "title": "后宫开在离婚时",
        "original_title": "バツハレ",
        "media_type": "manga",
        "year": "2023",
        "studio": "集英社",
        "episode": "",
        "episode_title": "",
        "scene": "主角与前妻重逢后意外进入后宫生活的开场场景",
        "characters": ["渋谷久留美", "主角"],
        "confidence": "high",
        "note": "バツハレ = バツイチ（离过婚）+ ハーレム（后宫）的复合词",
        "_vision_used": True,
        "reference_image_urls": [],
        "source_page_urls": [
            {"title": "バツハレ - 集英社コミックス", "url": "https://example.com/manga/batsuhare"},
        ],
        "_search_log": [],
    },
}

from PyQt6.QtCore import QTimer

OUTFILE = sys.argv[2] if len(sys.argv) > 2 else None

result = _RESULTS.get(MODE, _RESULTS["analyze"])
win = ResultWindow(result, position=None, image=None)
win.show()

def _grab_and_maybe_exit():
    if OUTFILE:
        px = win.grab()
        px.save(OUTFILE)
        print(f"[test] saved to {OUTFILE}")
        app.quit()
    else:
        print(f"[test] showing mode={MODE}")

QTimer.singleShot(500, _grab_and_maybe_exit)
sys.exit(app.exec())
