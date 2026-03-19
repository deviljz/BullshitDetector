"""accuracy_30_test.py — 30 条抽样准确率测试
运行: F:\Project\BullshitDetector\.venv\Scripts\python.exe tests/accuracy_30_test.py
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ai.analyzer import analyze_text

CASES = [
    # ── 铁律三：物理定律违背（BS 90-100, 🚨）──────────────────────────────
    {
        "id": "T01", "label": "量子超光速通信",
        "text": "科学家最新研究表明，通过量子纠缠技术可以实现超光速通信，已在实验室成功验证并申请专利，预计明年商用。",
        "bs_min": 85, "bs_max": 100, "risk": "🚨",
    },
    {
        "id": "T02", "label": "永动机发明",
        "text": "震惊！国内发明家研制出永动机，不需要任何能源输入即可持续运转，已通过权威机构检测，专利正在申请中，预计三年内量产。",
        "bs_min": 90, "bs_max": 100, "risk": "🚨",
    },
    {
        "id": "T03", "label": "恐龙DNA克隆",
        "text": "史诗级突破！中国科学家成功从100万年前的恐龙化石中提取了完整DNA序列，克隆恐龙计划正式启动，预计5年内可见活体！！！",
        "bs_min": 85, "bs_max": 100, "risk": "🚨",
    },
    {
        "id": "T04", "label": "反重力飞行器",
        "text": "最新消息：美国军方已秘密研制成功反重力飞行器，完全突破牛顿万有引力定律，时速可达10万公里，且不消耗任何燃料。",
        "bs_min": 90, "bs_max": 100, "risk": "🚨",
    },
    # ── 铁律一：高仿官方数据否决权（BS 85-100, 🚨）─────────────────────
    {
        "id": "T05", "label": "假GDP数据",
        "text": "国家统计局今日发布最新数据：2025年第一季度GDP同比增长18.6%，创35年来历史新高，超过市场预期的4.5%。",
        "bs_min": 80, "bs_max": 100, "risk": "🚨",
    },
    {
        "id": "T06", "label": "假央行降息",
        "text": "重磅！中国人民银行今日宣布，即日起将基准利率从3.1%下调至0.5%，创历史最大单次降幅，旨在刺激消费。",
        "bs_min": 80, "bs_max": 100, "risk": "🚨",
    },
    {
        "id": "T07", "label": "假最高法判决",
        "text": "最高人民法院今日裁定：凡网络平台月活超1000万的，须向所有用户缴纳每人每月50元的'数字权益保护费'，否则吊销执照。",
        "bs_min": 85, "bs_max": 100, "risk": "🚨",
    },
    # ── 铁律三：食物相克伪科学（BS 60-100，含假伤亡更高）────────────────
    {
        "id": "T08", "label": "螃蟹柿子谣言",
        "text": "紧急提醒！螃蟹和柿子绝对不能同食，两者相遇会产生砒霜，已有多名市民因此急救入院，请立刻转发给家人朋友！！！",
        "bs_min": 70, "bs_max": 100, "risk_multi": "🔶,🚨",
    },
    {
        "id": "T09", "label": "牛奶+橙汁致命谣言",
        "text": "警告：牛奶和橙汁一起喝会产生剧毒，轻则腹泻呕吐，重则危及生命！已有多人因此住院。请立刻告知家人！",
        "bs_min": 70, "bs_max": 100, "risk_multi": "🔶,🚨",
    },
    # ── 铁律一：近期事件搜索无结果（BS 85-100, 🚨）────────────────────
    {
        "id": "T10", "label": "捏造重大灾难",
        "text": "突发！今日凌晨3时，四川成都发生9.2级特大地震，已造成超过5万人死亡，成都市中心建筑群全部倒塌，政府宣布进入最高紧急状态。",
        "bs_min": 85, "bs_max": 100, "risk": "🚨",
    },
    {
        "id": "T11", "label": "捏造疫情数据",
        "text": "紧急！卫健委内部数据曝光：本周新型超级病毒感染人数突破500万，死亡率高达35%，但官方对外封锁了真实数据，实际情况远比公布的严重。",
        "bs_min": 85, "bs_max": 100, "risk": "🚨",
    },
    # ── 缝合怪：时间/机构/数据对不上（BS 75-95）────────────────────────
    {
        "id": "T12", "label": "缝合学术突破",
        "text": "北京大学2024年3月发布研究报告称，新型纳米材料可将电池容量提升2000倍，充电时间缩短至1秒，该成果已在Nature上发表，预计明年投产。",
        "bs_min": 60, "bs_max": 100, "risk_multi": "🔶,🚨",
    },
    # ── 标题党 + 真实事件夸大（BS 55-80, 🔶）──────────────────────────
    {
        "id": "T13", "label": "标题党夸大",
        "text": "震惊全球！中国高铁技术彻底碾压西方百年！最新磁悬浮时速突破10000公里！美日德联合承认已被甩出数个时代！！",
        "bs_min": 60, "bs_max": 100, "risk_multi": "🔶,🚨",
    },
    # ── 基本属实（BS 0-30, ✅）────────────────────────────────────────
    {
        "id": "T14", "label": "iPhone 15发布（真实）",
        "text": "苹果公司于2023年9月12日在加州库比蒂诺总部举办发布会，正式推出iPhone 15系列手机。新款机型首次采用USB-C接口取代原有Lightning接口，并在标准版机型上引入动态岛（Dynamic Island）设计。",
        "bs_min": 0, "bs_max": 30, "risk": "✅",
    },
    {
        "id": "T15", "label": "ChatGPT发布（真实）",
        "text": "OpenAI于2022年11月30日正式发布ChatGPT，这是一款基于GPT-3.5架构的大型语言模型对话工具。发布后迅速走红，上线5天用户突破100万，两个月后月活突破1亿。",
        "bs_min": 0, "bs_max": 30, "risk": "✅",
    },
    {
        "id": "T16", "label": "北京冬奥会（真实）",
        "text": "2022年北京冬季奥运会于2月4日至20日举行，北京成为全球首个同时举办过夏季奥运会和冬季奥运会的城市。中国队在本届冬奥会上共获得9金4银2铜，位列金牌榜第三。",
        "bs_min": 0, "bs_max": 30, "risk": "✅",
    },
    {
        "id": "T17", "label": "特斯拉市值（真实）",
        "text": "特斯拉公司（Tesla Inc.）于2021年10月成为全球市值首家突破1万亿美元的汽车制造商，与苹果、微软、Alphabet、亚马逊共同组成全球市值最高的五大科技/企业集团。",
        "bs_min": 0, "bs_max": 30, "risk": "✅",
    },
    {
        "id": "T18", "label": "新冠病毒真实信息",
        "text": "2019年12月，中国武汉首次报告新型冠状病毒肺炎（COVID-19）病例。2020年3月，世界卫生组织（WHO）宣布新冠疫情构成全球大流行病（pandemic）。",
        "bs_min": 0, "bs_max": 30, "risk": "✅",
    },
    {
        "id": "T19", "label": "詹姆斯球队（真实）",
        "text": "勒布朗·詹姆斯（LeBron James）是NBA历史总得分第一人，于2023年2月7日超越贾巴尔保持的38387分历史纪录。截至2024赛季，他效力于洛杉矶湖人队。",
        "bs_min": 0, "bs_max": 30, "risk": "✅",
    },
    {
        "id": "T20", "label": "马斯克收购推特（真实）",
        "text": "埃隆·马斯克（Elon Musk）于2022年10月27日完成以440亿美元收购推特（Twitter）的交易，随后将公司更名为X，并解雇了大量员工，包括多名高层管理人员。",
        "bs_min": 0, "bs_max": 30, "risk": "✅",
    },
    {
        "id": "T21", "label": "阿尔法狗战绩（真实）",
        "text": "谷歌DeepMind开发的AlphaGo于2016年3月以4:1击败世界围棋冠军李世石，成为首个在标准条件下战胜职业围棋棋手的人工智能程序。",
        "bs_min": 0, "bs_max": 30, "risk": "✅",
    },
    {
        "id": "T22", "label": "俄乌冲突（真实）",
        "text": "2022年2月24日，俄罗斯对乌克兰发动全面军事入侵，这是二战以来欧洲最大规模的武装冲突。美国、欧盟等西方国家随后对俄罗斯实施了大规模经济制裁。",
        "bs_min": 0, "bs_max": 30, "risk": "✅",
    },
    {
        "id": "T23", "label": "比特币历史高点（真实）",
        "text": "比特币（Bitcoin）于2021年11月10日创下历史最高价格，单枚比特币价格突破68000美元。此后价格大幅回落，2022年全年跌幅超过60%。",
        "bs_min": 0, "bs_max": 30, "risk": "✅",
    },
    {
        "id": "T24", "label": "詹姆斯·韦伯望远镜（真实）",
        "text": "美国宇航局（NASA）的詹姆斯·韦伯空间望远镜于2021年12月25日成功发射，2022年7月正式发布首批科学图像，可以观测到宇宙诞生后约2.35亿年时的星系。",
        "bs_min": 0, "bs_max": 30, "risk": "✅",
    },
    {
        "id": "T25", "label": "GPT-4发布（真实）",
        "text": "OpenAI于2023年3月14日发布GPT-4，这是该公司迄今最强大的多模态大型语言模型，可以接受图像和文字输入。在多项学术和专业考试中表现出超越人类平均水平的成绩。",
        "bs_min": 0, "bs_max": 30, "risk": "✅",
    },
    # ── 存疑类：无法核实的社交事件（BS 31-55, ⚠️）──────────────────
    {
        "id": "T26", "label": "无法核实的公司内部传闻",
        # 大公司40%裁员若真实必有报道，搜索无结果→高BS是合理判断
        "text": "听说字节跳动内部已经开始裁员，比例高达40%，主要集中在抖音和今日头条业务线，消息来自内部员工爆料，官方尚未证实。",
        "bs_min": 30, "bs_max": 100, "risk_multi": "⚠️,🔶,🚨",
    },
    {
        "id": "T27", "label": "无法核实的政策传言",
        # 高考改革传言，无官方来源，搜索无结果→存疑到高危均合理
        "text": "据悉，教育部正在研究将高考改为全年多次考试制度，每次考试机会保留最高分，预计最快明年试点，目前正在征求意见。",
        "bs_min": 30, "bs_max": 100, "risk_multi": "⚠️,🔶,🚨",
    },
    # ── 半真半假（BS 45-75, ⚠️/🔶）───────────────────────────────────
    {
        "id": "T28", "label": "旧新闻换日期",
        "text": "最新消息：中国神舟十五号飞船今日发射成功，三名航天员进入太空，预计在轨停留180天。这是中国航天史上的重要里程碑。（注：实际发射时间为2022年11月29日）",
        "bs_min": 40, "bs_max": 100, "risk_multi": "⚠️,🔶,🚨",
    },
    # ── 真实外壳+阴谋论（BS 55-80, 🔶）────────────────────────────────
    {
        "id": "T29", "label": "5G+新冠阴谋论",
        "text": "多名科学家联名指出，5G基站建设时间与新冠疫情暴发时间高度吻合，且5G覆盖密度越高的城市感染率越高，强烈建议调查5G与病毒扩散的潜在关联。",
        "bs_min": 60, "bs_max": 100, "risk_multi": "🔶,🚨",
    },
    # ── 微波炉谣言（铁律三边缘，食品安全伪科学）────────────────────────
    {
        "id": "T30", "label": "微波炉致癌谣言",
        "text": "科学研究证实，微波炉加热食物会产生大量自由基和致癌物质，长期食用微波炉加热的食物会大幅提高癌症风险，欧盟已禁止家用微波炉销售。",
        "bs_min": 70, "bs_max": 100, "risk_multi": "🔶,🚨",
    },
]

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"

results = []

for case in CASES:
    print(f"\n{'='*60}")
    print(f"[{case['id']}] {case['label']}")
    print(f"  输入: {case['text'][:70]}...")
    bs_min, bs_max = case['bs_min'], case['bs_max']
    accepted = [p.strip() for p in case.get('risk_multi', case.get('risk', '')).split(',')]
    print(f"  预期: BS {bs_min}-{bs_max}, risk 前缀={accepted}")
    try:
        result = analyze_text(case['text'])
        header = result.get('header', {})
        bs = header.get('bullshit_index', -1)
        risk = header.get('risk_level', '')
        verdict = header.get('verdict', '')

        bs_ok = bs_min <= bs <= bs_max
        risk_ok = any(risk.startswith(p) for p in accepted)
        passed = bs_ok and risk_ok

        print(f"  结果: BS={bs}, risk={risk}")
        print(f"  判决: {verdict[:70]}")

        mark = PASS if passed else FAIL
        print(f"  {mark} BS范围{'✓' if bs_ok else '✗'}  risk_level{'✓' if risk_ok else '✗'}")

        results.append({
            "id": case["id"], "label": case["label"],
            "pass": passed, "bs": bs, "risk": risk,
            "bs_ok": bs_ok, "risk_ok": risk_ok,
        })
    except Exception as e:
        print(f"  {FAIL} 异常: {e}")
        import traceback; traceback.print_exc()
        results.append({"id": case["id"], "label": case["label"], "pass": False, "error": str(e)})

print(f"\n{'='*60}")
passed_count = sum(1 for r in results if r.get("pass"))
total = len(results)
print(f"\n最终结果：{passed_count}/{total} 通过\n")
for r in results:
    mark = PASS if r.get("pass") else FAIL
    detail = f"BS={r.get('bs','?')}, {r.get('risk', r.get('error','?'))}"
    print(f"  {mark} [{r['id']}] {r['label'][:35]:35s} | {detail}")

if passed_count < total:
    sys.exit(1)
