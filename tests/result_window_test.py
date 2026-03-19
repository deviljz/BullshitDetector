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
            {"claim": "某官员于2025年1月被反腐部门带走调查", "verdict": "✗ 伪造", "effective_sources": 0,
             "best_source_type": "none", "note": "搜索多个关键词，无任何官方媒体报道",
             "sources": [
                 {"url": "https://example.com/fact-check/1", "title": "人民日报官方辟谣：该消息不实"},
             ]},
            {"claim": "涉案金额逾10亿元", "verdict": "? 无法核实", "effective_sources": 0,
             "best_source_type": "none", "note": "无来源，数字疑似捏造",
             "sources": []},
        ],
        "_search_log": [
            {"tool": "web_search", "query": "某官员被捕 2025", "result_preview": "未找到相关结果"},
        ],
    },
    "summary": {
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
    },
    "summary_analysis": {
        "_mode": "summary",
        "content_type": "analysis",
        "headline": "AI大模型竞争格局：中美差距正在缩小但关键差异犹存",
        "core_idea": "作者认为中国大模型在参数规模上已接近美国顶级模型，但在数据质量、推理能力和生态系统方面仍存在系统性差距。",
        "key_points": [],
        "structured_outline": [
            {"section": "技术差距现状", "points": ["参数规模已相当", "推理benchmark仍落后20-30%", "多模态能力差距明显"]},
            {"section": "差距根本原因", "points": ["高质量中文语料不足", "RLHF数据标注体系薄弱", "芯片算力受限"]},
            {"section": "未来趋势预测", "points": ["18个月内差距有望进一步缩小", "细分垂直领域中国模型有望领先"]},
        ],
        "timeline": [],
        "key_quote": "中国模型的进步速度超出了大多数西方观察者的预期。",
        "bias_note": "",
        "original_language": "zh",
    },
    "explain": {
        "_mode": "explain",
        "type": "meme",
        "subject": "I'm not a cat",
        "short_answer": "2021年美国律师开庭时意外开启猫咪滤镜无法关闭的名场面",
        "detail": "2021年1月，美国德州一名律师罗德·庞巴尔在视频庭审时，因助手不小心开启了猫咪 Zoom 滤镜。整个庭审过程他以猫的形象出现，并一度声称「I'm not a cat, I'm here live, I'm not a cat」，引发全球热议。",
        "origin": "2021年1月德州法庭视频庭审事故",
        "usage": "用于形容身份认证失败、技术事故或尴尬处境",
        "still_active": True,
        "cultural_note": "该梗折射出远程办公时代技术失控的普遍焦虑，也体现了严肃场合意外出糗的反差喜剧效果。",
        "original_language": "en",
    },
    "explain_outdated": {
        "_mode": "explain",
        "type": "meme",
        "subject": "元芳你怎么看",
        "short_answer": "2012年走红的网络迷因，源自电视剧《神探狄仁杰》中的经典台词",
        "detail": "2012年，电视剧《神探狄仁杰》中狄仁杰频繁向助手李元芳征求意见，'元芳，你怎么看？'因重复出现而被网友截图恶搞，迅速成为讨论任何话题时的万能句式。",
        "origin": "电视剧《神探狄仁杰》，2012年网络爆红",
        "usage": "对任何事情征求意见或表示困惑时使用",
        "still_active": False,
        "cultural_note": "该梗反映了2012年前后中国网络迷因文化的草根性，是早期微博时代最具代表性的集体创作现象之一。",
        "original_language": "zh",
    },
    "source": {
        "_mode": "source",
        "_subtype": "anime",
        "found": True,
        "title": "孤独摇滚！",
        "original_title": "ぼっち・ざ・ろっく！",
        "media_type": "anime",
        "year": "2022",
        "studio": "CloverWorks",
        "episode": "第3话（最新话）",
        "episode_title": "转动吧！我的吉他",
        "scene": "后藤一里在学校天台独自练习吉他，神情专注而略带紧张，阳光从背后照射形成剪影效果。",
        "characters": ["后藤一里", "伊地知虹夏"],
        "confidence": "high",
        "note": "原作漫画为はまじあき作品，动画由CloverWorks制作，2022年秋季番",
        "_vision_used": True,
        "reference_image_urls": [],
        "source_page_urls": [
            {"title": "ぼっち・ざ・ろっく！ - CloverWorks", "url": "https://example.com/anime/bocchi"},
        ],
        "_search_log": [],
    },
    "source_manga": {
        "_mode": "source",
        "_subtype": "manga",
        "found": True,
        "title": "后宫开在离婚时",
        "original_title": "バツハレ",
        "media_type": "manga",
        "year": "2023",
        "studio": "",
        "episode": "",
        "episode_title": "",
        "volume": "第1卷",
        "chapter": "第5话",
        "publisher": "集英社",
        "artist": "作者名",
        "scene": "主角与前妻重逢后意外进入后宫生活的开场场景",
        "characters": ["渋谷久留美"],
        "confidence": "high",
        "note": "バツハレ = バツイチ（离过婚）+ ハーレム（后宫）的复合词，周刊少年Jump连载",
        "_vision_used": True,
        "reference_image_urls": [],
        "source_page_urls": [
            {"title": "バツハレ - 集英社コミックス", "url": "https://example.com/manga/batsuhare"},
        ],
        "_search_log": [],
    },
    "source_game": {
        "_mode": "source",
        "_subtype": "game",
        "found": True,
        "title": "艾尔登法环",
        "original_title": "Elden Ring",
        "media_type": "game",
        "year": "2022",
        "studio": "",
        "episode": "",
        "episode_title": "",
        "game_title": "艾尔登法环",
        "developer": "FromSoftware",
        "platform": "PC / PS5 / Xbox Series X",
        "scene": "玩家角色站在史东薇尔城堡外，画面右上角显示血量/FP/耐力三条属性条，远处可见熔岩地貌。",
        "characters": [],
        "confidence": "high",
        "note": "由宫崎英高与乔治·R·R·马丁联合创作，2022年2月发售，GOTY年度游戏得主",
        "_vision_used": False,
        "reference_image_urls": [],
        "source_page_urls": [],
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
