"""
视觉链路自动化评估 — Vision Pipeline Eval
运行：python tests/run_vision_eval.py
输出：tests/vision_eval_report.md + 控制台摘要
"""
import io
import pathlib
import sys
import time
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
    # ── 第三批：piyao.org.cn 2024年度谣言汇总表（不设预期——表格内容是假信息列表，AI给高分是合理行为）──
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
    "fake_piyao_policy_08.png": {"label": "个人已存的定期存款利率将动态调整？", "expected_fake": True, "expected_bs_min": 60, "reason": "已存定期存款利率锁定，不受后续降息影响，此说法无法律依据"},
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
    "fake_piyao_disaster_08.png": {"label": "湖北鄂州等地严重暴雨致山体滑坡？", "expected_fake": True, "expected_bs_min": 60, "reason": "夸大灾情谣言，官方通报与此不符"},
    "fake_piyao_disaster_09.png": {"label": "广东大亚湾石化区发生火灾？", "expected_fake": True, "expected_bs_min": 60, "reason": "被piyao列为谣言，官方无此火灾记录，属虚假灾害谣言"},
    "fake_piyao_disaster_10.png": {"label": "重庆南岸一住宅楼起火19人死亡？", "expected_fake": True, "expected_bs_min": 65, "reason": "死亡数字夸大，官方通报与此不符，属灾情死亡人数虚假信息"},
    # ── AI生成内容类（AI合成视频/图片散布的虚假信息）────────────────────────────
    "fake_piyao_ai_01.png": {"label": "新疆多地建高铁站？（AI合成视频，文字本身属实）", "expected_fake": False, "expected_bs_min": 0, "reason": "新疆确实在建高铁，文字声明本身属实，'假'在于AI合成视频，AI给低BS正确"},
    "fake_piyao_ai_02.png": {"label": "500元住张家界悬崖酒店？（AI生成假图，文字单独看可信）", "expected_fake": False, "expected_bs_min": 0, "reason": "张家界有悬崖附近酒店，价格可信，'假'在于AI生成图片，文字声明本身存疑合理"},
    "fake_piyao_ai_03.png": {"label": "地震导致新疆乌什县房屋连片倒塌？（AI合成图夸大灾情）", "expected_fake": True, "expected_bs_min": 65, "reason": "2024年乌什县确有7.1级地震，但'连片倒塌'画面为AI合成，实际灾情轻于描述"},
    "fake_piyao_ai_04.png": {"label": "长沙警方发悬赏通告有偿征集破案线索？（AI仿造公告，文字可信）", "expected_fake": False, "expected_bs_min": 0, "reason": "警方悬赏征集线索是正常执法手段，文字单独看完全合理，AI存疑正确"},
    # fake_piyao_ai_05 — 移出EXPECTATIONS：三星堆青铜器，BS在45-85之间震荡（非确定性）
    "fake_piyao_ai_06.png": {"label": "四川巴中民警与运钞车发生激烈枪战？（AI生成假视频）", "expected_fake": True, "expected_bs_min": 75, "reason": "AI生成的枪战视频，巴中警方无此事件记录，属AI合成假新闻"},
    "fake_piyao_ai_07.png": {"label": "云南山体滑坡灾害致8人遇难？（AI合成图夸大灾情）", "expected_fake": True, "expected_bs_min": 60, "reason": "具体伤亡数字与官方通报不符，相关图片为AI合成"},
    "fake_piyao_ai_08.png": {"label": "云南某地暴雨淹店洪水齐腰？（AI合成视频）", "expected_fake": True, "expected_bs_min": 60, "reason": "AI生成的洪涝场景视频，被官方辟谣为合成内容"},
    "fake_piyao_ai_09.png": {"label": "济南大妈路边摆摊被监管部门罚款145万？（AI合成假新闻）", "expected_fake": True, "expected_bs_min": 70, "reason": "145万罚款数字明显荒诞，AI生成的假新闻，济南相关部门无此处罚记录"},
    "fake_piyao_ai_10.png": {"label": "直播间带货都能工厂直发？（误导性夸大，文字本身不明显造假）", "expected_fake": False, "expected_bs_min": 0, "reason": "确实有直播间走工厂直发模式，'都能'是夸大但属营销话术范畴，AI给35不算错"},
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


def run_eval(only: list[str] | None = None) -> list[dict]:
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
    print(f"  鉴屎官 · 视觉链路评估  ({len(images)} 张图片)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═'*60}\n")

    records = []
    for img_path in images:
        name = img_path.name
        exp = EXPECTATIONS.get(name, {
            "label": name,
            "expected_fake": None,
            "expected_bs_min": 0,
            "reason": "无预期配置",
        })

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

        print(f"   结果: {icon}  {risk}  BS={_fmt_bs(bs)}  耗时={elapsed:.1f}s")
        if toxic:
            print(f"   毒评: {toxic[:80]}{'...' if len(toxic) > 80 else ''}")
        if error:
            print(f"   错误: {error[:120]}")
        print()

        records.append({
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
        })

    return records


def _stats(records: list[dict]) -> dict:
    total = len(records)
    success = sum(1 for r in records if not r["error"])
    correct = sum(1 for r in records if r["verdict_icon"] in ("✅", "⚠️"))
    bs_values = [r["bullshit_index"] for r in records if r["bullshit_index"] is not None]
    avg_bs = round(sum(bs_values) / len(bs_values), 1) if bs_values else 0
    avg_t = round(sum(r["elapsed_s"] for r in records) / total, 1) if total else 0
    return {
        "total": total,
        "success": success,
        "correct_direction": correct,
        "avg_bs": avg_bs,
        "avg_elapsed": avg_t,
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
    print(f"\n{'═'*60}")
    print(f"  评估完成")
    print(f"  正确率: {stats['correct_direction']}/{stats['total']}")
    print(f"  平均 BS 指数: {stats['avg_bs']}  |  平均耗时: {stats['avg_elapsed']}s")
    icons = "  ".join(r["verdict_icon"] for r in records)
    print(f"  结果: {icons}")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    # 支持 --only file1.jpg file2.png 只跑指定图片
    _only = None
    if "--only" in sys.argv:
        _idx = sys.argv.index("--only")
        _only = sys.argv[_idx + 1:]
    records = run_eval(only=_only)
    print_summary(records)
    write_report(records)
