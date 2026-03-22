"""测试鉴屎官路径分析头条文章"""
import sys, json
sys.path.insert(0, "src")

text = """两天回本，首月流水16亿：这群天才，解决了开放世界最大痛点

今天葡萄君在GDC上看到了一个关于开放世界设计的演讲，内容非常有价值。

《羊蹄山之魂》首席玩法程序员兼设计师塞缪尔・霍利（Samuel Hawley）分享了"事件卡组"设计方案。游戏两天便收回全部开发成本，上线首月全球销量破330万份（PS5独占），总收入超16亿元；MC媒体评分87分，玩家评分8.5。

他们用《龙与地下城》DM发牌的逻辑代替了传统的平铺式任务列表，设计了5条黄金设计法则的"事件卡组"任务系统。"""

from ai.analyzer import analyze_text_staged
print("分析中…")
result = analyze_text_staged(text)

with open("tests/jianshiguan_result.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print("saved to tests/jianshiguan_result.json")
