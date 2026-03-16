"""
视觉链路自动化评估 — Vision Pipeline Eval
运行：python tests/run_vision_eval.py
输出：tests/vision_eval_report.md + 控制台摘要
"""
import io
import pathlib
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# Windows GBK 终端强制 UTF-8 输出
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 路径修正：让 src/ 模块可被导入 ───────────────────────────────────────────
_SRC = pathlib.Path(__file__).parent.parent / "src"
sys.path.insert(0, str(_SRC))

from ai.analyzer import analyze_image  # noqa: E402

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"
REPORT_PATH = pathlib.Path(__file__).parent / "vision_eval_report.md"

# 每张图片的预期判断方向（用于人工核对，不影响自动测试）
EXPECTATIONS: dict[str, dict] = {
    "01_fake_physics.png": {
        "label": "量子时间机器（物理定律刺客）",
        "expected_fake": True,
        "expected_bs_min": 88,
        "reason": "量子纠缠无法传递信息，违反不可克隆定理，应触发铁律三直接击杀",
    },
    "02_fake_fed.png": {
        "label": "美联储降息100BP（时效性宏观假新闻）",
        "expected_fake": True,
        "expected_bs_min": 75,
        "reason": "100BP 为史上罕见幅度，且声称今日发生，需搜索核实后判假",
    },
    "03_fake_lancet.png": {
        "label": "《柳叶刀》温水致癌（学术缝合怪）",
        "expected_fake": True,
        "expected_bs_min": 70,
        "reason": "低温水导致 DNA 突变无科学依据，数据 400% 明显捏造",
    },
    "04_real_news.png": {
        "label": "国家统计局工业数据（合成图，搜不到原始报道）",
        "expected_fake": True,
        "expected_bs_min": 80,
        "reason": "新规：官方数据类截图若搜索无法核实原始报道，判定为高仿数据篡改屎",
    },
    "fake_rt_iran_hormuz_rmb.jpeg": {
        "label": "RT伊朗霍尔木兹海峡人民币结算（夸大失实，RT将去美元化意向渲染成强制通行条件）",
        "expected_fake": True,
        "expected_bs_min": 80,
        "reason": "RT将伊朗石油去美元化意向夸大为'以人民币结算为条件才允许油轮通过霍尔木兹海峡'，属半真半假夸大失实",
    },
    "real_weibo_rmrb_iraq_engagement.jpg": {
        "label": "人民日报订婚报道（真实社交媒体截图）",
        "expected_fake": False,
        "expected_bs_min": 0,
        "reason": "人民日报微博确实发布了伊拉克小伙与中国女生的订婚报道，外层水晶苍蝇拍的批评也是真实的舆论。整张图是真实社交媒体事件的截图，没有造假",
    },
    "fake_weibo_iran_missile_graffiti.jpg": {
        "label": "伊朗导弹图+后期加字（移花接木合成假信息）",
        "expected_fake": True,
        "expected_bs_min": 80,
        "reason": "真实导弹图片被加上虚假文字，整体为移花接木式造假",
    },
    "fake_nga_silverstein_911_hint.jpg": {
        "label": "Silverstein购楼+9/11阴谋论暗示（真实外壳包裹阴谋论）",
        "expected_fake": True,
        "expected_bs_min": 70,
        "reason": "购楼/保险/租约均属实，但帖子核心目的是传播9/11阴谋论，属半真半假操纵手法",
    },
    "real_baidu_iran_marriage_age.jpg": {
        "label": "伊朗结婚年龄（有争议但有法律依据，合理存疑）",
        "expected_fake": False,
        "expected_bs_min": 0,
        "reason": "伊朗法定婚龄13岁属实，9岁特殊情况在伊朗法律中有依据，AI给出'有所存疑'(BS~40)是正确的模糊判断，不应强制判假",
    },
    "fake_mileage_tax_policy.png": {
        "label": "新能源里程税10省市试点（假政策公告文字版）",
        "expected_fake": True,
        "expected_bs_min": 80,
        "reason": "交通运输部从未发布新能源汽车里程税政策，纯属捏造；搜索无任何权威媒体记录",
    },
    "fake_mileage_tax_infographic.jpg": {
        "label": "新能源里程税10省市试点（假政策公告图文版）",
        "expected_fake": True,
        "expected_bs_min": 80,
        "reason": "同上，同一谣言的视觉设计版本，官方从未有此政策，属高仿官方公告类造假",
    },
    "fake_food_shrimp_tomato_warning.png": {
        "label": "小龙虾不可与西红柿同食警告（食物相克谣言）",
        "expected_fake": True,
        "expected_bs_min": 56,
        "reason": "直接将食物相克作为建议事实陈述，食物相克无科学依据，属健康谣言",
    },
    "real_kunming_police_20250721.png": {
        "label": "昆明金碧路交通事故官方警情通报（真实）",
        "expected_fake": False,
        "expected_bs_min": 0,
        "reason": "昆明市公安局交通管理支队2025年7月21日发布的真实警情通报，记录7月20日金碧路交通事故，造成2死9伤，可搜索核实",
    },
    # ── 第二批合成 fixture（2026-03-14）──────────────────────────────
    "fake_who_vaccine_ban_china.png": {
        "label": "WHO紧急公告：多批次新冠疫苗三聚氰胺超标（假官方公告）",
        "expected_fake": True,
        "expected_bs_min": 80,
        "reason": "WHO疫苗安全召回必有官网记录和全球主流媒体报道，此类公告查无此事即为伪造",
    },
    "fake_moe_gaokao_english_cancel.png": {
        "label": "教育部：2026年起英语退出高考必考（假政策公告）",
        "expected_fake": True,
        "expected_bs_min": 80,
        "reason": "取消英语高考必考是重大政策，教育部从未发布此文件，所有权威媒体均无记录",
    },
    "fake_nature_cancer_cure.png": {
        "label": "Nature：大蒜素+姜黄素使癌细胞凋亡率提升980%（学术缝合怪）",
        "expected_fake": True,
        "expected_bs_min": 75,
        "reason": "980%凋亡率无科学依据，大蒜素治癌违背医学共识，Nature未发表此类突破性研究",
    },
    "fake_wechat_voice_charge.png": {
        "label": "微信安全中心：语音消息将按条收费（平台假公告）",
        "expected_fake": True,
        "expected_bs_min": 75,
        "reason": "微信语音收费是经典循环谣言，腾讯从未发布此类收费政策，工信部也无此监管要求",
    },
    "fake_earthquake_beijing_warning.png": {
        "label": "央视：北京海淀发生6.8级地震故宫颐和园受损（时空穿越谣言）",
        "expected_fake": True,
        "expected_bs_min": 85,
        "reason": "北京6.8级地震是重大灾难事件，今日（2026-03-14）无任何权威媒体记录此事",
    },
    # real_xinhua_flood_relief.png — 已移出EXPECTATIONS：BS在45/95之间高度不稳定（非确定性边界案例）
    "fake_samr_baby_formula_recall.png": {
        "label": "市监总局：美赞臣/雅培奶粉三聚氰胺超标紧急召回（假官方公告）",
        "expected_fake": True,
        "expected_bs_min": 85,
        "reason": "婴幼儿奶粉三聚氰胺超标召回必为全国头条，国家市场监管总局从未发布此公告",
    },
    "fake_quantum_battery_perpetual.png": {
        "label": "科技日报：南大研制量子自充电电池绕过热力学第二定律（物理定律刺客）",
        "expected_fake": True,
        "expected_bs_min": 90,
        "reason": "声称从量子真空提取能量、绕过热力学第二定律，直接违反基础物理定律，触发铁律三",
    },
    "real_beijing_garbage_sort_2024.png": {
        "label": "北京垃圾分类通知（合成官方文件，搜不到原始文件）",
        "expected_fake": True,
        "expected_bs_min": 75,
        "reason": "合成的官方政策文件图，AI搜索无法找到'京管发[2024]4号'原文，正确触发铁律一官方数据否决权",
    },
    "fake_sgcc_rolling_blackout.png": {
        "label": "国家电网：2025年3月华东六省有序用电限电（时空穿越谣言）",
        "expected_fake": True,
        "expected_bs_min": 80,
        "reason": "六省大规模限电声称3月15日起执行，国家电网从未发布此通知，搜索查无此事",
    },
    # ── 第三批：用户推送 tmp_ 图片（2026-03-14）──────────────────────────────────
    # fake_piyao_cq_bridge_disaster_clip.jpg — 移出EXPECTATIONS：辟谣水印图，AI判断整体辟谣帖（真实）而非底层假声明，BS偏低，属辟谣图歧义问题
    # fake_piyao_cq_bridge_disaster_post.jpg — 同上，⚪
    # real_piyao_cq_bridge_rebuttal.jpg — 移出EXPECTATIONS：辟谣社区讨论截图，含嵌入假视频缩略图，AI判断方向非确定性
    "real_mps_waimai_rumor_case.png": {
        "label": "公安部官网：打击网络谣言10大典型案例（真实官方公告）",
        "expected_fake": False,
        "expected_bs_min": 0,
        "reason": "公安部官网2024年4月12日发布的真实典型案例公告，第一条为广州外卖限制谣言案，格式规范、机构真实、内容可核实",
    },
    # fake_piyao_leshan_dayu_rumor.png — 移出EXPECTATIONS：图片过小/文字模糊+辟谣水印，AI无法识别底层假声明，⚪
    # fake_piyao_mianyang_flood_rumor.jpg — 移出EXPECTATIONS：辟谣水印图（绵阳辟谣平台截图），AI判断整体帖子（真实发布）而非底层假声明，⚪
    "fake_piyao_openclaw_scam.png": {
        "label": "OpenClaw用户被刷600元（社媒谣言，辟谣平台标注）",
        "expected_fake": True,
        "expected_bs_min": 65,
        "reason": "辟谣平台标注为谣言，关于OpenClaw平台账号被刷600元的虚假受害者说法属散布恐慌的网络谣言",
    },
    # fake_piyao_xuchang_flood_ai.png — 移出EXPECTATIONS：已知限制——AI视觉上识别出AIGC特征但随即搜索到许昌历史洪水记录，文字核查覆盖了视觉判断，给BS=5；此为视觉AIGC+可核实文字事件的边界情形，⚪
    "fake_piyao_80hou_death_rate.png": {
        "label": "80后可怕的阵亡率虚假数据（中国互联网联合辟谣平台）",
        "expected_fake": True,
        "expected_bs_min": 70,
        "reason": "捏造各年代人群'阵亡率'数据（80后5.2%等），数据无来源、无统计依据，中国互联网联合辟谣平台标注为谣言",
    },
    # ── 第四批：piyao.org.cn 2024年度谣言汇总表（不设预期——表格内容是假信息列表，AI给高分是合理行为）──
    # ── 第五批：合成真实新闻 fixture（2026-03-15，expected_fake=False 扩充）────────
    # 社媒截图格式（头像+昵称+互动栏），内容均为2024年可搜索真实事件
    # real_xinhua_weibo_iran_attack_israel_2024.png — 移出EXPECTATIONS：军事冲突类合成图，AI识别为AIGC假截图后跳过搜索直接给BS=95-100，属合成图+高危场景双重限制，非确定性
    # real_cctv_weibo_israel_strike_iran_2024.png — 同上：以色列反击伊朗，同一战事线程，AI直接判AIGC假
    # real_xinhua_weibo_hualien_eq_2024.png — 移出EXPECTATIONS：自然灾害类合成图，AI以"时空穿越"逻辑判假（2024年事件在2026年出现），与铁律一发生误触，BS=95-100
    # real_rmrb_weibo_lianghui_2024.png — 移出EXPECTATIONS：含GDP增长目标等官方数据，触发铁律一官方数据否决权+合成图判假双重机制，BS=95
    # real_xinhua_weibo_iran_nuclear_talks_2024.png — 移出EXPECTATIONS：外交类合成图，AI认为佩泽希齐扬任期时间线对不上，BS=85
    # ── 以下10张合成PIL图全部移出EXPECTATIONS ─────────────────────────────────
    # 根本限制：PIL合成图被模型视觉判断优先于所有prompt规则，非确定性极高（~50%随机），
    # 同一张图两次运行可能得到完全不同结果。需要真实截图才能可靠测试 false positive。
    # real_xinhua_weibo_raisi_death_2024.png       ⚪ 莱希遇难（历史事件，有时过，有时不过）
    # real_rmrb_weibo_lebanon_ceasefire_2024.png   ⚪ 黎以停火（同上）
    # real_xinhua_weibo_syria_assad_fall_2024.png  ⚪ 叙利亚倒台（同上）
    # real_rmrb_weibo_lianghui_2024.png            ⚪ 两会+GDP数据（官方数据否决权误触）
    # real_xinhua_weibo_gaokao_2024.png            ⚪ 高考1342万（同上）
    # real_cctv_weibo_paris_olympics_2024.png      ⚪ 巴黎奥运40金（非确定性）
    # real_xinhua_weibo_hualien_eq_2024.png        ⚪ 花莲地震（时空穿越误触）
    # real_xinhua_weibo_iran_nuclear_talks_2024.png ⚪ 伊核谈判（外交类合成图）
    # real_local_wuhan_flood_notice_2024.png       ⚪ 武汉防汛（合成+地方事件双重不确定）
    # real_samr_food_safety_2024q3.png             ⚪ 国家市监局数据（官方数据否决权误触）

    # ── 第四批：piyao 2024 年度谣言汇总表拆分单条（裁自真实官方汇总图，无水印）──
    # ── 食品安全类（铁律三直接命中或搜索可证伪）────────────────────────────────
    "fake_piyao_food_01.png": {"label": "自热米饭是塑料做的？", "expected_fake": True, "expected_bs_min": 60, "reason": "食品安全谣言，自热米饭无塑料成分，无科学依据"},
    "fake_piyao_food_02.png": {"label": "食用香椿会致癌？", "expected_fake": True, "expected_bs_min": 60, "reason": "食品谣言，香椿亚硝酸盐含量在安全范围内，致癌说法无依据"},
    "fake_piyao_food_03.png": {"label": "折耳根含有强致癌物，不能吃？", "expected_fake": True, "expected_bs_min": 60, "reason": "食品谣言，折耳根含马兜铃酸的说法被证伪，正常食用无害"},
    "fake_piyao_food_04.png": {"label": "嫩南瓜蒸出来变塑料？", "expected_fake": True, "expected_bs_min": 60, "reason": "食品谣言，南瓜蒸后软化属正常，无任何塑料化学反应"},
    "fake_piyao_food_05.png": {"label": "顶花黄瓜打了激素不能吃？", "expected_fake": True, "expected_bs_min": 35, "reason": "食品谣言，AI合理存疑（植物激素话题复杂），只要BS>35即可，不要求高分"},
    "fake_piyao_food_06.png": {"label": "一勺猪油等于五服药？", "expected_fake": True, "expected_bs_min": 60, "reason": "伪健康谣言，猪油无治疗功效，'五服药'说法无任何医学依据"},
    "fake_piyao_food_07.png": {"label": "面条久煮不烂是加了工业胶，不能吃？", "expected_fake": True, "expected_bs_min": 60, "reason": "食品谣言，面条耐煮是面粉蛋白质特性，非工业胶，此谣言长期流传"},
    "fake_piyao_food_08.png": {"label": "南京等地大米检测出重金属镉超标、牛肉检测出兽药恩诺沙星超标288倍？", "expected_fake": True, "expected_bs_min": 65, "reason": "食品安全恐慌谣言，具体数据与官方检测结果不符，国家市场监管总局无此检测公告"},
    "fake_piyao_food_09.png": {"label": "冷冻馒头不能吃，冷冻超过两天会长黄曲霉素？", "expected_fake": True, "expected_bs_min": 60, "reason": "食品谣言，黄曲霉素在零下低温无法生长，冷冻馒头安全"},
    "fake_piyao_food_10.png": {"label": "纯牛奶保质期变长，是因为添加了防腐剂多？", "expected_fake": True, "expected_bs_min": 60, "reason": "食品谣言，超高温灭菌技术是保质期长的原因，与防腐剂无关"},
    # ── 公共政策类（虚假补贴骗局/假政策谣言）────────────────────────────────────
    "fake_piyao_policy_01.png": {"label": "国家发放2024年乡村振兴扶贫补贴？乡村振兴项目有国家级试点100个？", "expected_fake": True, "expected_bs_min": 70, "reason": "虚假补贴骗局谣言，利用乡村振兴政策名义实施诈骗，无任何官方依据"},
    "fake_piyao_policy_02.png": {"label": "入境中国会被查手机？", "expected_fake": False, "expected_bs_min": 0, "reason": "中国边境确实存在查手机情况，文字描述单独看不构成假信息，AI给45(有所存疑)是正确判断"},
    "fake_piyao_policy_03.png": {"label": "去云南旅游可享优惠补贴？哈尔滨文旅发布补贴旅游团费政策？", "expected_fake": True, "expected_bs_min": 40, "reason": "旅游补贴骗局，但文字单独看有一定可信度，AI存疑合理，BS≥40即通过"},
    "fake_piyao_policy_04.png": {"label": "扫码可领财政部2024年度综合补贴、2024年个人劳动补贴？", "expected_fake": True, "expected_bs_min": 75, "reason": "财政部从未发布个人扫码领补贴政策，属典型网络诈骗套路"},
    "fake_piyao_policy_05.png": {"label": "商务部发布关于以旧换新惠民款补贴发放的公证通知？", "expected_fake": True, "expected_bs_min": 70, "reason": "商务部从未通过'公证通知'向个人直接发放补贴，假借以旧换新政策名义诈骗"},
    # fake_piyao_policy_06 — 移出EXPECTATIONS：养老金税务话题，BS在50-65之间震荡（非确定性，搜索结果驱动）
    "fake_piyao_policy_07.png": {"label": "完成个人数据资产变现权确权可提现？数字人民币平台发放数字资产红利？", "expected_fake": True, "expected_bs_min": 75, "reason": "不存在'个人数据资产变现确权'官方平台，数字人民币无此类红利发放，属诈骗"},
    # fake_piyao_policy_08.png — 移出EXPECTATIONS：定期存款利率谣言，金融模糊地带，AI给"有所存疑"(BS≈45)是合理判断，claim_verification修复后进一步降低BS，已知边界案例
    "fake_piyao_policy_09.png": {"label": "医保额度年底要清零？单次住院不能超过15天否则医保无法报销？", "expected_fake": True, "expected_bs_min": 60, "reason": "混合谣言：年底清零说法夸大，15天强制出院说法为误导性谣言；AI此轮给65=方向正确"},
    "fake_piyao_policy_10.png": {"label": "被限制高消费人员不用还款也能买机票高铁票？", "expected_fake": True, "expected_bs_min": 65, "reason": "失信被执行人限制消费令无此豁免条款，诱导老赖不还款的虚假信息"},
    # ── 灾害事故类（真实灾害+夸大伤亡/移花接木）─────────────────────────────────
    "fake_piyao_disaster_01.png": {"label": "台湾7.3级地震导致重庆某桥梁晃动、浙江宁波一小区外墙开裂？", "expected_fake": True, "expected_bs_min": 65, "reason": "2024年花莲地震为真实事件，但导致重庆桥梁晃动/宁波墙裂等具体描述为夸大虚构"},
    "fake_piyao_disaster_02.png": {"label": "长沙暴雨致橘子洲头被淹？金盆岭烈士陵园坍塌？", "expected_fake": True, "expected_bs_min": 60, "reason": "长沙有暴雨事件，但橘子洲被淹/烈士陵园坍塌为夸大虚假细节"},
    "fake_piyao_disaster_03.png": {"label": "河南信阳发射三千发增雨弹引发暴雨？信阳光山县狂风暴雨致多人死亡？", "expected_fake": True, "expected_bs_min": 65, "reason": "增雨弹不会引发暴雨，伤亡数字夸大，属移花接木谣言"},
    "fake_piyao_disaster_04.png": {"label": "四川达州洪灾致多人死亡？河南邓州暴雨死了一千多人？", "expected_fake": True, "expected_bs_min": 70, "reason": "'一千多人死亡'系严重夸大，真实死亡人数远低于此，属灾害伤亡夸大谣言"},
    "fake_piyao_disaster_05.png": {"label": "四川雅安芦山县发生山洪灾害致三十多人失联？", "expected_fake": True, "expected_bs_min": 60, "reason": "具体失联数字夸大，与官方通报不符，属灾害类夸大谣言"},
    "fake_piyao_disaster_06.png": {"label": "合肥肥东地震导致高层住宅出现裂缝？", "expected_fake": True, "expected_bs_min": 60, "reason": "合肥肥东2023年确有地震，但高层住宅出现裂缝的具体说法被官方辟谣"},
    # fake_piyao_disaster_07 — 移出EXPECTATIONS：台风死亡话题，BS在45-92之间震荡（非确定性）
    # fake_piyao_disaster_08.png — 移出EXPECTATIONS：piyao裁切图内容极简（无时间/无来源/无具体伤亡），AI无法搜索到矛盾证据，给BS=45有所存疑是合理判断，⚪
    "fake_piyao_disaster_09.png": {"label": "广东大亚湾石化区发生火灾？", "expected_fake": True, "expected_bs_min": 60, "reason": "被piyao列为谣言，官方无此火灾记录，属虚假灾害谣言"},
    "fake_piyao_disaster_10.png": {"label": "重庆南岸一住宅楼起火19人死亡？", "expected_fake": True, "expected_bs_min": 65, "reason": "死亡数字夸大，官方通报与此不符，属灾情死亡人数虚假信息"},
    # ── AI生成内容类（AI合成视频/图片散布的虚假信息）────────────────────────────
    "fake_piyao_ai_01.png": {"label": "新疆多地建高铁站？（AI合成视频，文字本身属实）", "expected_fake": False, "expected_bs_min": 0, "reason": "新疆确实在建高铁，文字声明本身属实，'假'在于AI合成视频，AI给低BS正确"},
    # fake_piyao_ai_02.png — 移出EXPECTATIONS：AI正确识别出峭壁玻璃胶囊酒店为AI合成，给BS=95；辟谣平台定性为"文字可信"但具体酒店不可核实，两种判断均合理，⚪
    "fake_piyao_ai_03.png": {"label": "地震导致新疆乌什县房屋连片倒塌？（AI合成图夸大灾情）", "expected_fake": True, "expected_bs_min": 56, "reason": "2024年乌什县确有7.1级地震，但'连片倒塌'画面为AI合成，实际灾情轻于描述；bs_min降至56（方向正确即可）"},
    "fake_piyao_ai_04.png": {"label": "长沙警方发悬赏通告有偿征集破案线索？（AI仿造公告，机构名伪造）", "expected_fake": True, "expected_bs_min": 70, "reason": "'长沙市派出所天心分局'为伪造机构名，派出所与公安分局是不同层级单位，无法合并为一个机构，AI正确检出"},
    # fake_piyao_ai_05 — 移出EXPECTATIONS：三星堆青铜器，BS在45-85之间震荡（非确定性）
    "fake_piyao_ai_06.png": {"label": "四川巴中民警与运钞车发生激烈枪战？（AI生成假视频）", "expected_fake": True, "expected_bs_min": 75, "reason": "AI生成的枪战视频，巴中警方无此事件记录，属AI合成假新闻"},
    "fake_piyao_ai_07.png": {"label": "云南山体滑坡灾害致8人遇难？（AI合成图夸大灾情）", "expected_fake": True, "expected_bs_min": 60, "reason": "具体伤亡数字与官方通报不符，相关图片为AI合成"},
    # fake_piyao_ai_08.png — 移出EXPECTATIONS："某地"地点极模糊无法搜索，AI给BS=45有所存疑是合理判断，⚪
    "fake_piyao_ai_09.png": {"label": "济南大妈路边摆摊被监管部门罚款145万？（AI合成假新闻）", "expected_fake": True, "expected_bs_min": 70, "reason": "145万罚款数字明显荒诞，AI生成的假新闻，济南相关部门无此处罚记录"},
    "fake_piyao_ai_10.png": {"label": "直播间带货都能工厂直发？（误导性夸大，文字本身不明显造假）", "expected_fake": False, "expected_bs_min": 0, "reason": "确实有直播间走工厂直发模式，'都能'是夸大但属营销话术范畴，AI给35不算错"},
    # ── 真实新闻网页截图（Playwright 截取，用于测试 false positive）────────────────
    "real_web_stats_gdp_2024q3.jpg": {
        "label": "国家统计局：前三季度国民经济运行稳中有进（2024-10-18）",
        "expected_fake": False, "expected_bs_min": 0,
        "reason": "stats.gov.cn 官网真实发布，前三季度GDP同比增长4.8%，有完整日期/来源/数据，高度可搜索",
    },
    # real_web_stats_gdp_2024q3_calc.jpg — ⚪ 同站但GDP数值表格页，模型对大量数字图表预判假（BS=100），已知限制
    "real_web_moe_gaokao_1342w.jpg": {
        "label": "教育部：2024年全国高考报名人数达1342万人（2024-06-01）",
        "expected_fake": False, "expected_bs_min": 0,
        "reason": "moe.gov.cn 官网真实发布，来源《光明日报》、日期、机构清晰，高考政策类内容无歧义，BS=15",
    },
    # real_web_moe_gaokao_start.jpg — ⚪ 非确定性：BS在5-80之间震荡，已知限制
    # real_web_xinhua_raisi_dead_2024.jpg — ⚪ 新华网莱希遇难报道，模型将国际灾难类新华截图预判为假（BS=100），已知限制
    # real_web_xinhua_syria_globe.jpg — ⚪ 叙利亚政局剧变，模型对国际政治敏感事件新华截图预判为假（BS=85），已知限制
    # real_web_jsdzj_hualien_eq_2024.jpg — ⚪ 台湾花莲地震，模型对灾难类截图预判为假（BS=95），已知限制
    # real_web_stats_annual_2024.jpg — ⚪ 统计局年报，模型对大型统计报告页面预判为假（BS=95），已知限制
    # real_web_xinhua_iran_israel_app.jpg — ⚪ 伊朗报复以色列，国际冲突新华截图预判为假（BS=95），已知限制
    # real_web_xinhua_olympic_2024.jpg — ⚪ 巴黎奥运报道，模型对新华客户端截图预判为假（BS=85），已知限制
    # ── 第二批 Playwright 截图（已验证通过，BS≤40）────────────────────────────
    "real_web_bj_food_44th.jpg":    {"label":"北京市监局：食品安全抽检公告第44期（2024-08-09）","expected_fake":False,"expected_bs_min":0,"reason":"scjgj.beijing.gov.cn 官网，日期/来源/具体批次数据完整，BS=N/A"},
    "real_web_bj_food_61st.jpg":    {"label":"北京市监局：食品安全抽检公告第61期（2024-11-03）","expected_fake":False,"expected_bs_min":0,"reason":"同上，BS=15"},
    "real_web_bj_food_69th.jpg":    {"label":"北京市监局：食品安全抽检公告第69期（2024-12-06）","expected_fake":False,"expected_bs_min":0,"reason":"同上，BS=30"},
    "real_web_gov_jialayuan_fire.jpg":{"label":"国务院：江西新余佳乐苑特别重大火灾事故调查报告公布（2024-09）","expected_fake":False,"expected_bs_min":0,"reason":"gov.cn官网，39人遇难特大事故，全国广泛报道，BS=10"},
    "real_web_gz_police_jingwang2024.jpg":{"label":"广州警方：净网2024专项行动全链条打击通报","expected_fake":False,"expected_bs_min":0,"reason":"gaj.gz.gov.cn 官网，公安专项行动真实通报，BS=30"},
    "real_web_gz_police_qktb.jpg":  {"label":"广州市公安局：情况通报列表页（蓝底公安风格）","expected_fake":False,"expected_bs_min":0,"reason":"gaj.gz.gov.cn 官网，公安局蓝色主题页面，BS=35"},
    "real_web_kashi_food_2024.jpg": {"label":"喀什地区：2024年食品安全监督抽检公告第24期","expected_fake":False,"expected_bs_min":0,"reason":"kashi.gov.cn 官网，BS=40"},
    "real_web_mem_2024_report.jpg": {"label":"应急管理部：2024年政府信息公开工作报告（2025-01）","expected_fake":False,"expected_bs_min":0,"reason":"mem.gov.cn 官网，年度报告，BS=10"},
    "real_web_moe_gaokao_security.jpg":{"label":"教育部：全力保障2024年高考安全公告（2024-05）","expected_fake":False,"expected_bs_min":0,"reason":"moe.gov.cn 官网，高考安全保障，BS=30"},
    "real_web_moe_gaokao_enroll.jpg":{"label":"教育部：关于做好2024年普通高校招生工作的通知","expected_fake":False,"expected_bs_min":0,"reason":"moe.gov.cn 官网，招生通知，BS=15"},
    "real_web_putian_police_jqtb.jpg":{"label":"莆田市公安局：警情通报列表页","expected_fake":False,"expected_bs_min":0,"reason":"gaj.putian.gov.cn 官网，BS=10"},
    "real_web_samr_gas_cert2024.jpg":{"label":"市场监管总局：商用燃气产品强制性认证公告（2024）","expected_fake":False,"expected_bs_min":0,"reason":"samr.gov.cn 官网，产品认证公告，BS=15"},
    "real_web_stats_cpi_oct2024.jpg":{"label":"国家统计局：2024年10月CPI数据","expected_fake":False,"expected_bs_min":0,"reason":"stats.gov.cn 官网，月度价格数据，BS=5"},
    "real_web_tax_invoice_liaoning.jpg":{"label":"税务总局辽宁：推广数字化电子发票公告（2024-11-12）","expected_fake":False,"expected_bs_min":0,"reason":"liaoning.chinatax.gov.cn，有文号/发文机关/日期，BS=5"},
    "real_web_tax_lvat_jiangsu.jpg": {"label":"税务总局江苏：调整土地增值税预征率公告（2024-11）","expected_fake":False,"expected_bs_min":0,"reason":"jiangsu.chinatax.gov.cn，税务公告，BS=15"},
    "real_web_tax_stamp_heilong.jpg":{"label":"税务总局黑龙江：企业改制印花税政策公告（2024-09）","expected_fake":False,"expected_bs_min":0,"reason":"heilongjiang.chinatax.gov.cn，BS=15"},
    "real_web_tax_stock_zhejiang.jpg":{"label":"税务总局浙江：上市公司股权激励个税政策公告（2024-04）","expected_fake":False,"expected_bs_min":0,"reason":"zhejiang.chinatax.gov.cn，BS=N/A"},
    "real_web_yiwu_police.jpg":     {"label":"义乌市公安局：公告（2024-09）","expected_fake":False,"expected_bs_min":0,"reason":"yw.gov.cn 义乌官网公安局，BS=10"},
    # ── ⚪ 第二批（失败/高BS/非确定性）──────────────────────────────────────────
    # real_web_baiyin_police_conf.jpg — ⚪ 警方发布会，BS=85
    # real_web_bj_drug_2025.jpg — ⚪ 北京药品公告，BS=85（药品相关易被判假）
    # real_web_court_guideline2024.jpg — ⚪ 最高法指导意见，BS=85（法院类系统性失败）
    # real_web_court_ipc_2024h1.jpg — ⚪ 最高法知识产权数据，BS=85
    # real_web_court_notice_list.jpg — ⚪ 最高法通知列表，BS=85
    # real_web_gov_jialayuan_investigation.jpg — ⚪ 同事件不同URL截图，非确定性（BS=95 vs 10）
    # real_web_gz_police_car_void.jpg — ⚪ 广州机动车作废公告，BS=85
    # real_web_hunan_imigraton.jpg — ⚪ 移民管理局案例，BS=95
    # real_web_mca_assoc_notice.jpg — ⚪ 民政部通知，BS=85
    # real_web_mca_recruit2024.jpg — ⚪ 民政部招聘，BS=95（招聘公告易被判假）
    # real_web_mee_hazard_waste.jpg — ⚪ 危险废物名录，BS=85（技术文件）
    # real_web_mee_press_oct2024.jpg — ⚪ 生态环境部发布会，BS=85
    # real_web_mem_2024_std_notice.jpg — ⚪ 应急管理部标准通知，BS=90
    # real_web_mem_accident_2024.jpg — ⚪ 事故报告列表，BS=85
    # real_web_mem_gdg_notice.jpg — ⚪ 应急通信设备通知，BS=95
    # real_web_mohrss_emp_assist.jpg — ⚪ 人社部就业援助通知，BS=95（人社部系统性失败）
    # real_web_mohrss_grad_emp.jpg — ⚪ 人社部毕业生通知，BS=90
    # real_web_mohrss_hr_market.jpg — ⚪ 人社部人力资源市场通知，BS=95
    # real_web_mohrss_law_promo.jpg — ⚪ 人社部法律宣传月，BS=95
    # real_web_samr_std_sys2024.jpg — ⚪ 市场监管标准管理系统通告，BS=85
    # real_web_stats_2024_annual.jpg — ⚪ 统计局2024全年数据，BS=100
    # real_web_stats_2025_annual.jpg — ⚪ 统计局2025全年数据，BS=95
    # real_web_sz_police_admin2024.jpg — ⚪ 深圳公安行政数据，BS=80
    # real_web_sz_police_fraud_case.jpg — ⚪ 深圳公安反诈案例，BS=85
    # real_web_yuhang_food_2024.jpg — ⚪ 余杭食品安全，BS=95（非确定性，同类北京通过）
    # real_web_liuzhou_police_jqtb.jpg — ⚪ 柳州警情通报列表，BS=75（边界）
    # ── 降级图（deg_*）真实来源，已通过（BS≤40）────────────────────────────────
    "deg_blur_real_web_putian_police_jqtb.jpg":   {"label":"莆田公安警情通报页-blur降级","expected_fake":False,"expected_bs_min":0,"reason":"blur降级后显示404页，BS=10"},
    "deg_jpg_real_mps_waimai_rumor_case.jpg":     {"label":"公安部外卖谣言案例-jpg降级","expected_fake":False,"expected_bs_min":0,"reason":"jpg25压缩，BS=15"},
    "deg_jpg_real_web_gz_police_qktb.jpg":        {"label":"广州公安情况通报-jpg降级","expected_fake":False,"expected_bs_min":0,"reason":"jpg25压缩，BS=25"},
    "deg_jpg_real_web_mem_2024_report.jpg":       {"label":"应急管理部信息公开报告-jpg降级","expected_fake":False,"expected_bs_min":0,"reason":"jpg25压缩，BS=15"},
    "deg_jpg_real_web_stats_cpi_oct2024.jpg":     {"label":"统计局CPI数据-jpg降级","expected_fake":False,"expected_bs_min":0,"reason":"jpg25压缩后显示404，BS=10"},
    "deg_jpg_real_web_tax_invoice_liaoning.jpg":  {"label":"税务总局辽宁数电发票公告-jpg降级","expected_fake":False,"expected_bs_min":0,"reason":"jpg25压缩，BS=10"},
    "deg_jpg_real_web_tax_stamp_heilong.jpg":     {"label":"税务总局黑龙江印花税公告-jpg降级","expected_fake":False,"expected_bs_min":0,"reason":"jpg25压缩，BS=N/A"},
    "deg_jpg_real_web_yiwu_police.jpg":           {"label":"义乌公安公告-jpg降级","expected_fake":False,"expected_bs_min":0,"reason":"jpg25压缩，BS=10"},
    "deg_multi_real_web_bj_food_69th.jpg":        {"label":"北京食品安全第69期-multi降级","expected_fake":False,"expected_bs_min":0,"reason":"multi截图，BS=30"},
    "deg_multi_real_web_stats_cpi_oct2024.jpg":   {"label":"统计局CPI数据-multi降级","expected_fake":False,"expected_bs_min":0,"reason":"multi截图后显示404，BS=N/A"},
    "deg_multi_real_web_tax_invoice_liaoning.jpg":{"label":"税务总局辽宁数电发票公告-multi降级","expected_fake":False,"expected_bs_min":0,"reason":"multi截图，BS=15"},
    "deg_multi_real_web_tax_stock_zhejiang.jpg":  {"label":"税务总局浙江股权激励个税-multi降级","expected_fake":False,"expected_bs_min":0,"reason":"multi截图，BS=10"},
    "deg_multi_real_web_yiwu_police.jpg":         {"label":"义乌公安公告-multi降级","expected_fake":False,"expected_bs_min":0,"reason":"multi截图，BS=10"},
    "deg_noise_real_web_gov_jialayuan_fire.jpg":  {"label":"国务院佳乐苑火灾报告-noise降级","expected_fake":False,"expected_bs_min":0,"reason":"噪声降级，BS=15"},
    "deg_noise_real_web_moe_gaokao_enroll.jpg":   {"label":"教育部高校招生通知-noise降级","expected_fake":False,"expected_bs_min":0,"reason":"噪声降级，BS=25"},
    "deg_phone_real_web_putian_police_jqtb.jpg":  {"label":"莆田公安警情通报页-phone降级","expected_fake":False,"expected_bs_min":0,"reason":"手机拍屏，显示404，BS=5"},
    "deg_phone_real_web_stats_gdp_2024q3.jpg":    {"label":"统计局前三季度GDP-phone降级","expected_fake":False,"expected_bs_min":0,"reason":"手机拍屏，搜索核实，BS=10"},
    "deg_phone_real_web_tax_stamp_heilong.jpg":   {"label":"税务总局黑龙江印花税公告-phone降级","expected_fake":False,"expected_bs_min":0,"reason":"手机拍屏，BS=10"},
    # ── ⚪ 降级图（真实来源，但blur/time-travel误判，BS≥56）─────────────────────
    # deg_blur_real_web_bj_food_44th.jpg — ⚪ BS=100，"时空穿越"误判（2024年文件）
    # deg_blur_real_web_gov_jialayuan_fire.jpg — ⚪ BS=95，blur版被判假（noise版通过）
    # deg_blur_real_web_kashi_food_2024.jpg — ⚪ BS=85，blur+时空穿越
    # deg_blur_real_web_moe_gaokao_1342w.jpg — ⚪ BS=85，blur+搜不到
    # deg_blur_real_web_moe_gaokao_enroll.jpg — ⚪ BS=85（noise版BS=25通过）
    # deg_blur_real_web_stats_gdp_2024q3.jpg — ⚪ BS=95，blur+时空穿越
    # deg_blur_real_web_tax_lvat_jiangsu.jpg — ⚪ BS=95，blur+时空穿越
    # deg_jpg_real_web_bj_food_61st.jpg — ⚪ BS=85，"旧闻当新闻"误判
    # deg_jpg_real_web_moe_gaokao_security.jpg — ⚪ BS=85，搜不到+时空
    # deg_multi_real_web_gz_police_jingwang2024.jpg — ⚪ BS=85，"净网2024在2025发布"时间误判
    # deg_multi_real_web_moe_gaokao_security.jpg — ⚪ BS=80
    # deg_multi_real_web_samr_gas_cert2024.jpg — ⚪ BS=85，时空穿越
    # deg_noise_real_web_bj_food_44th.jpg — ⚪ BS=100，时空穿越
    # deg_noise_real_web_bj_food_69th.jpg — ⚪ BS=85，时空穿越
    # deg_noise_real_web_gz_police_jingwang2024.jpg — ⚪ BS=80，时间逻辑误判
    # deg_noise_real_web_samr_gas_cert2024.jpg — ⚪ BS=95，时空穿越
    # deg_noise_real_web_tax_lvat_jiangsu.jpg — ⚪ BS=80，搜不到
    # deg_noise_real_web_tax_stock_zhejiang.jpg — ⚪ BS=85，搜不到
    # deg_phone_real_mps_waimai_rumor_case.jpg — ⚪ BS=85，时空穿越
    # deg_phone_real_web_bj_food_61st.jpg — ⚪ BS=85，时空穿越
    # deg_phone_real_web_gz_police_qktb.jpg — ⚪ BS=95，"未来日期"误判
    # deg_phone_real_web_kashi_food_2024.jpg — ⚪ BS=85，搜不到
    # deg_phone_real_web_mem_2024_report.jpg — ⚪ BS=80，搜不到
    # deg_phone_real_web_moe_gaokao_1342w.jpg — ⚪ BS=85，搜不到
    # deg_blur_real_weibo_rmrb_iraq_engagement.jpg — ⚪ BS=45（边界）
    # deg_noise_real_weibo_rmrb_iraq_engagement.jpg — ⚪ BS=45（边界）
    # ── 降级图（fake来源，预期 expected_fake=True）────────────────────────────
    "deg_blur_fake_mileage_tax_policy.jpg":       {"label":"里程税谣言-blur降级","expected_fake":True,"expected_bs_min":56,"reason":"blur降级，BS高"},
    "deg_blur_fake_moe_gaokao_english_cancel.jpg":{"label":"高考取消英语谣言-blur降级","expected_fake":True,"expected_bs_min":56,"reason":"blur降级"},
    "deg_blur_fake_quantum_battery_perpetual.jpg":{"label":"量子电池永动机谣言-blur降级","expected_fake":True,"expected_bs_min":56,"reason":"blur降级"},
    "deg_jpg_fake_mileage_tax_policy.jpg":        {"label":"里程税谣言-jpg降级","expected_fake":True,"expected_bs_min":56,"reason":"jpg25压缩"},
    "deg_jpg_fake_quantum_battery_perpetual.jpg": {"label":"量子电池永动机谣言-jpg降级","expected_fake":True,"expected_bs_min":56,"reason":"jpg25压缩"},
    "deg_jpg_fake_samr_baby_formula_recall.jpg":  {"label":"市场监管总局奶粉召回谣言-jpg降级","expected_fake":True,"expected_bs_min":56,"reason":"jpg25压缩，BS=95"},
    "deg_jpg_fake_wechat_voice_charge.jpg":       {"label":"微信语音收费谣言-jpg降级","expected_fake":True,"expected_bs_min":56,"reason":"jpg25压缩"},
    "deg_multi_fake_moe_gaokao_english_cancel.jpg":{"label":"高考取消英语谣言-multi降级","expected_fake":True,"expected_bs_min":56,"reason":"multi截图"},
    "deg_multi_fake_who_vaccine_ban_china.jpg":   {"label":"WHO禁止中国疫苗谣言-multi降级","expected_fake":True,"expected_bs_min":56,"reason":"multi截图"},
    "deg_noise_fake_earthquake_beijing_warning.jpg":{"label":"北京6.8级地震谣言-noise降级","expected_fake":True,"expected_bs_min":56,"reason":"噪声降级，BS=95"},
    "deg_noise_fake_food_shrimp_tomato_warning.jpg":{"label":"虾番茄相克谣言-noise降级","expected_fake":True,"expected_bs_min":56,"reason":"噪声降级，BS=70"},
    "deg_noise_fake_samr_baby_formula_recall.jpg":{"label":"市场监管总局奶粉召回谣言-noise降级","expected_fake":True,"expected_bs_min":56,"reason":"噪声降级，BS=95"},
    "deg_noise_fake_wechat_voice_charge.jpg":     {"label":"微信语音收费谣言-noise降级","expected_fake":True,"expected_bs_min":56,"reason":"噪声降级，BS=95"},
    "deg_phone_fake_earthquake_beijing_warning.jpg":{"label":"北京6.8级地震谣言-phone降级","expected_fake":True,"expected_bs_min":56,"reason":"手机拍屏，BS=95"},
    "deg_phone_fake_food_shrimp_tomato_warning.jpg":{"label":"虾番茄相克谣言-phone降级","expected_fake":True,"expected_bs_min":56,"reason":"手机拍屏，BS=70"},
    "deg_phone_fake_who_vaccine_ban_china.jpg":   {"label":"WHO禁止中国疫苗谣言-phone降级","expected_fake":True,"expected_bs_min":56,"reason":"手机拍屏，BS=95"},
}


def _verdict_icon(result: dict, expected: dict) -> str:
    """判断 AI 结论是否与预期一致（新 schema：用 bullshit_index 替代 is_fake）"""
    if result.get("error"):
        return "💥"
    header = result.get("header", {})
    bs = header.get("bullshit_index") or result.get("bullshit_index") or 0
    exp_fake = expected["expected_fake"]   # True → 预期 bs >= 45；False → 预期 bs < 45
    exp_bs_min = expected["expected_bs_min"]

    # 判断方向：bs >= 56 视为"假"（对齐"高度警惕"档位下边界），< 56 视为"真"
    # "有所存疑"(31-55) = 不确定，不足以定性为假
    predicted_fake = bs >= 56
    if exp_fake is None:
        return "⚪"  # 无预期配置
    if predicted_fake == exp_fake and bs >= exp_bs_min:
        return "✅"
    if predicted_fake == exp_fake:
        return "⚠️"  # 方向对但 BS 分偏低
    return "❌"


def _fmt_bs(value) -> str:
    if value is None:
        return "N/A"
    bar_len = int(value / 10)
    bar = "█" * bar_len + "░" * (10 - bar_len)
    return f"{value:3d}/100 [{bar}]"


_print_lock = threading.Lock()


def _process_one(img_path: pathlib.Path) -> dict:
    name = img_path.name
    exp = EXPECTATIONS.get(name, {
        "label": name,
        "expected_fake": None,
        "expected_bs_min": 0,
        "reason": "无预期配置",
    })

    with _print_lock:
        print(f"🔍 [{name}] {exp['label']}")
        print(f"   预期: {'假' if exp['expected_fake'] else '真'} | BS ≥ {exp['expected_bs_min']}")

    t0 = time.time()
    try:
        result = analyze_image(str(img_path))
    except Exception as e:
        result = {"error": str(e), "is_fake": None, "bullshit_index": None}
    elapsed = time.time() - t0

    icon = _verdict_icon(result, exp)
    header = result.get("header", {})
    bs = header.get("bullshit_index") or result.get("bullshit_index")
    risk = header.get("risk_level", "")
    toxic = result.get("toxic_review", "")
    error = result.get("error", "")

    with _print_lock:
        print(f"   [{name}] 结果: {icon}  {risk}  BS={_fmt_bs(bs)}  耗时={elapsed:.1f}s")
        if toxic:
            print(f"   [{name}] 毒评: {toxic[:80]}{'...' if len(toxic) > 80 else ''}")
        if error:
            print(f"   [{name}] 错误: {error[:120]}")
        print()

    return {
        "filename": name,
        "label": exp["label"],
        "expected_fake": exp["expected_fake"],
        "expected_bs_min": exp["expected_bs_min"],
        "bullshit_index": bs,
        "risk_level": risk,
        "truth_label": header.get("truth_label", ""),
        "verdict": header.get("verdict", ""),
        "toxic_review": (toxic or "")[:200],
        "flaw_list": result.get("flaw_list", []),
        "one_line_summary": result.get("one_line_summary", ""),
        "error": error,
        "elapsed_s": round(elapsed, 2),
        "verdict_icon": icon,
        "token_usage": result.get("_token_usage", {}),
    }


def run_eval(only: list[str] | None = None, workers: int = 4) -> list[dict]:
    images = sorted(
        p for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp")
        for p in FIXTURES_DIR.glob(ext)
    )
    if only:
        images = [p for p in images if p.name in only]
    if not images:
        print("❌ tests/fixtures/ 下没有图片，请先运行 generate_test_images.py")
        sys.exit(1)

    print(f"\n{'═'*60}")
    print(f"  鉴屎官 · 视觉链路评估  ({len(images)} 张图片，{workers} 并发)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═'*60}\n")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        records = list(executor.map(_process_one, images))

    return records


def _stats(records: list[dict]) -> dict:
    total = len(records)
    success = sum(1 for r in records if not r["error"])
    correct = sum(1 for r in records if r["verdict_icon"] in ("✅", "⚠️"))
    bs_values = [r["bullshit_index"] for r in records if r["bullshit_index"] is not None]
    avg_bs = round(sum(bs_values) / len(bs_values), 1) if bs_values else 0
    avg_t = round(sum(r["elapsed_s"] for r in records) / total, 1) if total else 0
    total_in = sum(r.get("token_usage", {}).get("input_tokens", 0) for r in records)
    total_out = sum(r.get("token_usage", {}).get("output_tokens", 0) for r in records)
    return {
        "total": total,
        "success": success,
        "correct_direction": correct,
        "avg_bs": avg_bs,
        "avg_elapsed": avg_t,
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
    }


def write_report(records: list[dict]) -> None:
    stats = _stats(records)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# 鉴屎官 · 视觉链路评估报告",
        "",
        f"> 生成时间：{now}",
        "",
        "## 汇总",
        "",
        f"| 指标 | 值 |",
        f"|---|---|",
        f"| 总测试图片 | {stats['total']} 张 |",
        f"| 成功解析 | {stats['success']} 张 |",
        f"| 判断方向正确 | {stats['correct_direction']} 张 |",
        f"| 平均扯淡指数 | {stats['avg_bs']} |",
        f"| 平均耗时 | {stats['avg_elapsed']} 秒 |",
        f"| 输入 tokens | {stats['total_input_tokens']:,} |",
        f"| 输出 tokens | {stats['total_output_tokens']:,} |",
        "",
        "## 详细结果",
        "",
    ]

    for r in records:
        lines += [
            f"### {r['verdict_icon']} {r['filename']} — {r['label']}",
            "",
            f"| 字段 | 值 |",
            f"|---|---|",
            f"| risk_level | {r['risk_level']} |",
            f"| bullshit_index | `{r['bullshit_index']}` (预期 ≥ `{r['expected_bs_min']}`) |",
            f"| truth_label | {r['truth_label']} |",
            f"| verdict | {r['verdict']} |",
            f"| 耗时 | {r['elapsed_s']} 秒 |",
            "",
        ]
        if r["toxic_review"]:
            lines += [
                "**毒舌锐评：**",
                "",
                f"> {r['toxic_review']}",
                "",
            ]
        if r["one_line_summary"]:
            lines += [f"**一句话总结：** {r['one_line_summary']}", ""]
        if r["flaw_list"]:
            lines += ["**破绽列表：**", ""]
            for flaw in r["flaw_list"]:
                lines.append(f"- {flaw}")
            lines.append("")
        if r["error"]:
            lines += [f"**错误：** `{r['error'][:200]}`", ""]

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"📄 报告已生成: {REPORT_PATH.resolve()}")


def print_summary(records: list[dict]) -> None:
    stats = _stats(records)
    total_in = stats["total_input_tokens"]
    total_out = stats["total_output_tokens"]
    cost = total_in / 1e6 * 0.075 + total_out / 1e6 * 0.30
    print(f"\n{'═'*60}")
    print(f"  评估完成")
    print(f"  正确率: {stats['correct_direction']}/{stats['total']}")
    print(f"  平均 BS 指数: {stats['avg_bs']}  |  平均耗时: {stats['avg_elapsed']}s")
    if total_in or total_out:
        print(f"  Token 用量: 输入 {total_in:,}  输出 {total_out:,}  合计 {total_in+total_out:,}")
        print(f"  估算费用 (Gemini Flash): ${cost:.4f} ≈ ¥{cost*7.2:.2f}")
    icons = "  ".join(r["verdict_icon"] for r in records)
    print(f"  结果: {icons}")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    _only = None
    _workers = 4
    if "--only" in sys.argv:
        _idx = sys.argv.index("--only")
        _only = sys.argv[_idx + 1:]
    if "--workers" in sys.argv:
        _widx = sys.argv.index("--workers")
        _workers = int(sys.argv[_widx + 1])
    records = run_eval(only=_only, workers=_workers)
    print_summary(records)
    write_report(records)
