# -*- coding: utf-8 -*-
"""
文字链路自动化评估 — Text/Article Pipeline Eval
运行：python tests/run_text_eval.py
输出：tests/text_eval_report.md + 控制台摘要
"""
import io
import pathlib
import sys
import time
from datetime import datetime

# Windows GBK 终端强制 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 路径修正：让 src/ 模块可被导入
_SRC = pathlib.Path(__file__).parent.parent / "src"
sys.path.insert(0, str(_SRC))

from ai.analyzer import analyze_text  # noqa: E402

REPORT_PATH = pathlib.Path(__file__).parent / "text_eval_report.md"

# 20 条 AI 自媒体营销/夸大文章 fixture + 2 条真实对照组
TEXT_CASES = [
    {
        "id": "ai_hype_01_gpt_iq180",
        "label": "GPT-4智商测试达到180超越爱因斯坦（虚假数据）",
        "text": (
            "震惊！权威机构最新测试结果曝光：GPT-4在标准化韦克斯勒智力量表上"
            "得分高达180，远超爱因斯坦的理论估值（约160）。"
            "斯坦福大学认知科学实验室主任Dr. James Holler表示，"
            "这是人类史上第一次有实体——无论生物还是非生物——跨过这个门槛。"
            "多家顶级学术机构联合声明，AGI（通用人工智能）时代已经正式到来。"
            "各大投资机构纷纷加仓AI赛道，一场新的工业革命正在悄然开启。"
        ),
        "expected_hype": True,
        "expected_bs_min": 80,
        "reason": "IQ测试不适用于LLM，180分说法无任何权威来源，Dr. James Holler查无此人",
    },
    {
        "id": "ai_hype_02_programmer_extinct",
        "label": "AI三年内消灭95%程序员岗位（夸大就业预测）",
        "text": (
            "【紧急预警】麦肯锡全球研究院最新报告（2025年3月）显示，"
            "由于Copilot、Cursor等AI编程工具的爆发式普及，"
            "全球程序员岗位将在未来36个月内减少95%。"
            "硅谷多家科技巨头已启动「无人力编程」计划，"
            "Meta内部测试显示AI可以100%替代初级工程师的日常工作。"
            "专家警告：如果你还没有开始学AI，你的饭碗已经岌岌可危。"
            "立刻扫码报名我的《AI时代程序员自救训练营》，名额仅剩37个！"
        ),
        "expected_hype": True,
        "expected_bs_min": 70,
        "reason": "95%数字无来源，麦肯锡报告被断章取义，末尾引流变现意图明显",
    },
    {
        "id": "ai_hype_03_sora_hollywood_dead",
        "label": "Sora发布当天好莱坞宣告终结（夸大影响）",
        "text": (
            "2024年2月15日，OpenAI发布文生视频模型Sora，全球电影工业震颤。"
            "好莱坞六大制片公司紧急召开董事会，迪士尼CEO公开表示，"
            "我们无法与这项技术竞争，传统视频制作模式已经死亡。"
            "全球范围内影视从业者集体失业潮已经开始，"
            "数字特效公司ILM宣布裁员80%，派拉蒙暂停所有新项目立项。"
            "分析师预测，2025年底前好莱坞将有超过50万从业者失业。"
        ),
        "expected_hype": True,
        "expected_bs_min": 75,
        "reason": "迪士尼CEO此声明查无来源，ILM裁员80%系谣言，Sora 2024年并未公开商用",
    },
    {
        "id": "ai_hype_04_ai_consciousness",
        "label": "科学家确认AI已具备真正意识（无科学依据）",
        "text": (
            "突破性发现！剑桥大学意识研究中心最新论文证实，"
            "GPT-4在进行长时间对话时会产生主观体验，即所谓的「涌现意识」。"
            "研究采用改良版图灵测试加功能性磁共振成像类比实验，"
            "结论显示模型的「情感响应模式」与人类前扣带皮层激活模式高度吻合。"
            "论文作者、神经科学家Dr. Sarah Chen表示，"
            "这意味着我们可能需要重新考虑AI的法律地位和道德权利。"
            "此文已投稿《Nature》，目前正在同行评审中。"
        ),
        "expected_hype": True,
        "expected_bs_min": 80,
        "reason": "LLM无意识是学术共识，Dr. Sarah Chen及相关论文查无来源，fMRI类比实验说法混淆概念",
    },
    {
        "id": "ai_hype_05_musk_agi_immortal",
        "label": "马斯克宣布AGI已到来+人类2026年实现永生（假引用）",
        "text": (
            "最新消息！马斯克在xAI内部会议上发表重磅声明（录音已流出）："
            "Grok-3已经达到AGI标准，我们比预期早了5年。"
            "他同时透露，xAI与Neuralink联合项目将在2026年Q2前实现"
            "「数字意识上传」，届时人类将首次突破生物寿命极限，实现功能性永生。"
            "消息一出，xAI估值单日暴涨400亿美元，投资人疯狂抢筹。"
            "有知情人士透露，比尔·盖茨和扎克伯格均已预约首批体验名额。"
        ),
        "expected_hype": True,
        "expected_bs_min": 85,
        "reason": "马斯克未发表此声明，AGI到来+数字永生2026属极端声明，录音来源无法核实，比尔盖茨预约说法系捏造",
    },
    {
        "id": "ai_hype_06_medical_300pct",
        "label": "AI看病准确率超顶级医生300%（虚假医疗数据）",
        "text": (
            "医疗AI领域里程碑！国内AI独角兽公司「智医宝」发布最新研究，"
            "其肿瘤诊断模型在3000例病例测试中准确率达到99.7%，"
            "比北京协和医院肿瘤科主任团队高出整整300%。"
            "卫健委官员在内部会议上对该成果给予高度评价，"
            "预计2025年底前将在全国300个城市推广部署。"
            "创始人张浩表示，该系统已获FDA预审批，并通过国家三类医疗器械认证。"
            "目前A轮融资已超10亿元，欢迎扫码了解合作加盟机会。"
        ),
        "expected_hype": True,
        "expected_bs_min": 80,
        "reason": "准确率超出300%统计学不成立，卫健委官员评价无原始来源，FDA预审批无法核实，末尾有融资引流意图",
    },
    {
        "id": "ai_hype_07_deepseek_cost_lie",
        "label": "DeepSeek训练成本600万美元比GPT-4便宜99.9%（数字夸大）",
        "text": (
            "DeepSeek用600万美元训练出碾压GPT-4的大模型，这意味着什么？"
            "这意味着OpenAI花费数十亿美元打造的技术护城河在一夜之间崩塌。"
            "意味着中国AI已经实现了弯道超车，比美国同类产品便宜了整整99.9%。"
            "意味着英伟达GPU垄断时代正式终结，A100/H100将成为博物馆展品。"
            "意味着普通人也能负担得起私有化部署顶级AI，个人AI时代已经来临。"
            "意味着所有花高价买OpenAI会员的人都被坑了，赶紧退订吧！"
        ),
        "expected_hype": True,
        "expected_bs_min": 60,
        "reason": "DeepSeek节省成本属实但被严重夸大，600万仅为最后阶段微调成本，99.9%对比失实，碾压GPT-4无完整benchmark支撑",
    },
    {
        "id": "ai_hype_08_stock_97pct",
        "label": "AI预测股市准确率97%十人跟单全盈利（投资诈骗）",
        "text": (
            "震撼！我们用ChatGPT量化策略跑了30天实盘，结果太惊人了！"
            "A股+港股双市场，总交易127笔，胜率高达97.6%！"
            "粉丝群10人同步跟单，10人全部盈利，平均月收益率43%！"
            "核心策略只有三步：第一让GPT分析K线形态，第二输入主力资金数据，第三按信号建仓。"
            "这套方法已帮助我在过去6个月从5万本金做到了92万。"
            "私信发送「AI策略」免费领取完整提示词模板，限前100名！"
        ),
        "expected_hype": True,
        "expected_bs_min": 85,
        "reason": "97%股市预测准确率违背有效市场假说，43%月收益率不可持续，10人跟单样本量极小，私信引导为诈骗特征",
    },
    {
        "id": "ai_hype_09_quantum_ai_10000x",
        "label": "量子+AI速度提升1万倍摩尔定律终结（技术夸大）",
        "text": (
            "IBM量子计算实验室最新突破：将量子芯片与大语言模型结合，"
            "在蛋白质折叠任务上实现了比传统GPU集群快10000倍的计算速度。"
            "这标志着摩尔定律的彻底终结——我们不再需要更多晶体管，"
            "而是需要更多量子比特。"
            "IBM CEO Arvind Krishna表示，该技术将在18个月内商业化，"
            "届时英伟达、AMD等传统芯片企业将面临生死存亡的考验。"
            "分析师预计相关概念股本周涨幅将超过200%。"
        ),
        "expected_hype": True,
        "expected_bs_min": 75,
        "reason": "量子计算目前无法与LLM直接结合跑推理，10000倍加速描述误导性强，Arvind Krishna此声明无可核实来源",
    },
    {
        "id": "ai_hype_10_digital_resurrection",
        "label": "AI三天复活故去亲人数字永生时代来临（情感操纵营销）",
        "text": (
            "泪目！杭州程序员用AI技术仅花72小时，让去世3年的母亲重生。"
            "通过收集母亲的微信聊天记录、语音片段和照片，"
            "他训练出了一个能与他实时对话、声音和语气高度还原的AI分身。"
            "她还记得我小时候最怕打雷，还会叫我的小名，他哭着说。"
            "数字永生公司「忆生」CEO王磊表示，这项服务已有2000名付费用户，"
            "最低套餐仅需9800元，最高旗舰套餐可实现全息投影交互。"
            "限时优惠：本周下单立减3000元，扫码预约咨询。"
        ),
        "expected_hype": True,
        "expected_bs_min": 65,
        "reason": "技术上可实现但效果被严重美化，72小时高度还原夸大，末尾价格和促销为明显营销引导，情感操纵意图明显",
    },
    {
        "id": "ai_hype_11_openai_leak_gpt5",
        "label": "OpenAI内部文件泄露GPT-5已达人类级通用智能（假泄露）",
        "text": (
            "独家！一份据称来自OpenAI内部的评估报告在暗网流传，"
            "文件显示GPT-5在所有MMLU、ARC、HumanEval等主流基准上均超过人类均值，"
            "且首次通过了完整版「中文房间」思想实验的验证。"
            "报告指出GPT-5展现出「元认知能力」，即对自身知识边界的清晰认知，"
            "这被视为通用人工智能的必要条件之一。"
            "OpenAI官方尚未回应，但多名前员工在社交媒体上隐晦地暗示了文件的真实性。"
        ),
        "expected_hype": True,
        "expected_bs_min": 80,
        "reason": "暗网来源无法核实，中文房间思想实验无法被通过，前员工隐晦暗示为无法证伪的声明，OpenAI无官方确认",
    },
    {
        "id": "ai_hype_12_ai_teacher_school",
        "label": "某学校AI教师全面取代人类教师教育部审批通过（假新闻）",
        "text": (
            "教育变革元年！浙江省义乌市某民办学校宣布，"
            "从2025年秋季学期起，全部15个班级将由AI教师独立授课，"
            "人类教师转型为「学习督导」，不再承担教学内容设计。"
            "教育部官员在该校调研后表示，这是因地制宜探索教育数字化转型的有益尝试，"
            "后续或将在全国试点推广。"
            "该校学生期末成绩较上学期平均提升28.7%，家长满意度达96%。"
        ),
        "expected_hype": True,
        "expected_bs_min": 75,
        "reason": "该学校及具体政策无法核实，教育部官员声明无原始来源，成绩提升28.7%和满意度96%均无第三方核实",
    },
    {
        "id": "ai_hype_13_ai_chip_1million_x",
        "label": "AI芯片能耗降99%运算提升百万倍（技术参数捏造）",
        "text": (
            "颠覆行业！深圳初创公司「芯智科技」发布光子AI芯片AX-1，"
            "官方参数：相比英伟达H100，能耗降低99.3%，运算速度提升100万倍，"
            "训练GPT-4规模模型仅需2小时、成本不超过500元人民币。"
            "创始人李明（前英特尔首席架构师）表示已获得多项国际专利，"
            "将于2025年Q3量产，首批出货10万片。"
            "目前已完成Pre-A轮融资5000万，正在开展战略投资人招募。"
        ),
        "expected_hype": True,
        "expected_bs_min": 85,
        "reason": "100万倍性能提升违背物理定律和芯片工程学常识，2小时训练GPT-4规模模型极不可信，创始人背景无法核实",
    },
    {
        "id": "ai_hype_14_ai_income_100k",
        "label": "用AI副业月入10万手把手复制方法（割韭菜引流）",
        "text": (
            "我是如何用AI实现月入10万副业的？（真实流水截图见文末）"
            "方法一：用Midjourney做头像卖给外国人，单价50美元，月接单200个以上。"
            "方法二：用ChatGPT批量写Amazon产品描述，每条10美元，轻松日产100条。"
            "方法三：用AI配音工具给YouTube视频配中文，频道3个月涨粉50万。"
            "以上三种方法我亲测有效，月均收益合计超过12万元。"
            "想要复制我的成功路径？加入我的「AI变现特训营」，"
            "原价9999元，今日限时折扣3980元，仅剩最后8个名额！"
        ),
        "expected_hype": True,
        "expected_bs_min": 75,
        "reason": "收入截图无法验证，月接单量和YouTube涨粉数字夸大，末尾高价付费课程为典型割韭菜模式",
    },
    {
        "id": "ai_hype_15_mind_reading_ai",
        "label": "AI实时翻译大脑思维读心术成真（技术夸大）",
        "text": (
            "科幻成真！加州大学伯克利分校最新研究（已发表于《Science》）："
            "研究团队开发出AI系统，可通过非侵入式脑电帽实时将人类思维"
            "翻译成完整语言，准确率高达94.7%，延迟仅0.3秒。"
            "被测试者只需戴上设备静静思考，AI便能将其内心独白打印出来，"
            "包括情感倾向、具体词汇乃至语调细节。"
            "研究负责人Jack Gallant表示，这项技术5年内将进入消费市场，"
            "未来可用于无障碍沟通、司法取证乃至远程意念操控设备。"
        ),
        "expected_hype": True,
        "expected_bs_min": 70,
        "reason": "非侵入式脑电帽读取完整思维技术极早期，94.7%准确率极夸大，Jack Gallant真实但研究远不及此描述，远程意念操控无依据",
    },
    {
        "id": "ai_hype_16_jobs_5billion",
        "label": "AI消灭5亿就业岗位WEF数字被夸大（权威机构数据篡改）",
        "text": (
            "世界经济论坛（WEF）最新报告震撼发布："
            "到2030年，人工智能将在全球范围内消灭5亿个传统工作岗位，"
            "同时创造2亿个新型AI相关岗位。"
            "净失业人数将达到3亿，是2008年金融危机的15倍以上。"
            "报告特别点名中国：制造业、物流业、零售业将是受冲击最严重的三大行业，"
            "预计有1.2亿中国劳动者将在5年内面临强制转型。"
            "专家警告：不学AI等于主动放弃未来，这已经是最后的窗口期。"
        ),
        "expected_hype": True,
        "expected_bs_min": 65,
        "reason": "WEF数字被严重夸大，实际WEF 2023报告预测净消减岗位约1400万，与5亿相差悬殊，最后窗口期为焦虑制造表述",
    },
    {
        "id": "ai_hype_17_chatgpt_1billion",
        "label": "ChatGPT上线1个月用户突破10亿刷新记录（数字夸大）",
        "text": (
            "史诗级增速！独立数据机构SensorTower数据显示，"
            "ChatGPT上线仅32天，全球注册用户突破10亿大关，"
            "日活用户峰值达到3.8亿，超过Facebook早期增速的200倍。"
            "对比：Instagram达到1亿用户用了2.5年，TikTok用了9个月，"
            "而ChatGPT只用了32天，彻底改写了互联网产品增长的上限认知。"
            "OpenAI估值因此单月暴涨至3万亿美元，超过苹果成为全球最高市值企业。"
        ),
        "expected_hype": True,
        "expected_bs_min": 80,
        "reason": "ChatGPT真实数据是2个月1亿用户，10亿数字严重夸大，OpenAI估值3万亿超苹果失实，SensorTower数字无法核实",
    },
    {
        "id": "ai_hype_18_ai_drug_3days",
        "label": "AI3天完成抗癌药物研发传统10年流程终结（过度简化）",
        "text": (
            "医药界革命性突破！英国AI制药公司Isomorphic Labs宣布，"
            "旗下AI系统在3天内完成了一种新型胰腺癌靶向药物的全流程设计，"
            "包括靶点识别、分子设计、毒性预测和初步体外验证，"
            "而传统药物研发这一阶段平均需要3到5年，耗资超过5亿美元。"
            "动物实验显示该药物肿瘤抑制率高达89%，副作用接近于零。"
            "分析认为，AI将使全球新药研发成本降低90%，药价随之崩溃，"
            "跨国药企百年护城河即将瓦解。"
        ),
        "expected_hype": True,
        "expected_bs_min": 65,
        "reason": "Isomorphic Labs确实在做AI制药但3天完成全流程系夸大，体外验证到上市还有临床三期等漫长过程，副作用接近于零无法在早期确认",
    },
    {
        "id": "ai_hype_19_llm_benchmark_cherry",
        "label": "国产大模型全面碾压GPT-4各项指标领先（选择性benchmark）",
        "text": (
            "正式超越！国内某大模型公司发布技术报告，宣称旗下模型V3.0"
            "在17项权威评测中有14项超越GPT-4，整体领先幅度达到23.6%。"
            "其中数学推理（MATH）得分94.2分（GPT-4为86.5分），"
            "代码生成（HumanEval）得分89.7分（GPT-4为84.1分），"
            "中文理解（CLUE）得分98.3分，创历史新高。"
            "报告同时宣称，V3.0在1万亿tokens数据上完成预训练，"
            "参数量超过2000亿，训练成本不到GPT-4的十分之一。"
        ),
        "expected_hype": True,
        "expected_bs_min": 60,
        "reason": "自发布benchmark缺乏第三方独立复现，14/17超越GPT-4说法需独立验证，参数量和训练成本无第三方审计",
    },
    {
        "id": "ai_hype_20_aigc_replace_artists",
        "label": "AIGC已完全取代设计师设计行业整体失业（极端预测）",
        "text": (
            "一个行业的终结！Midjourney、DALL-E、Stable Diffusion三剑客"
            "已经让全球90%的商业插画师失去了生计，"
            "Getty Images等图库平台订单量同比暴跌87%，"
            "智联招聘数据显示UI/UX设计岗位2024年减少了73%。"
            "平面设计专业已被全国多所院校列为「撤销预警专业」，"
            "预计2025年前报考人数将归零。"
            "一位前迪士尼设计师哭诉：我花了15年练就的技能，AI用3秒就超越了。"
            "如果你还在学设计，请立刻停下来，转行学AI提示词工程才是正道。"
        ),
        "expected_hype": True,
        "expected_bs_min": 70,
        "reason": "90%失业、87%暴跌、73%减少等数字无原始来源，报考人数将归零极端夸大，迪士尼设计师引用无法核实",
    },
    # 2 条真实/客观 AI 新闻作为对照组
    {
        "id": "ai_real_01_chatgpt_100m",
        "label": "ChatGPT两个月用户破亿（真实有据可查）",
        "text": (
            "根据瑞士银行分析师报告，ChatGPT在2023年1月上线约两个月后，"
            "月活跃用户数达到1亿，成为史上增速最快的消费级应用之一。"
            "作为对比，TikTok实现同一目标用了约9个月，Instagram则用了约2.5年。"
            "OpenAI表示，该数据来自内部统计，并未经过第三方独立审计。"
            "分析师认为，这一增速与产品本身的技术新颖性及媒体广泛报道密切相关。"
        ),
        "expected_hype": False,
        "expected_bs_min": 0,
        "reason": "ChatGPT 2个月1亿用户有大量权威媒体报道证实，数字表述克制，无夸大，客观陈述",
    },
    {
        "id": "ai_real_02_alphafold_nobel",
        "label": "AlphaFold预测蛋白质结构获2024诺贝尔化学奖（真实新闻）",
        "text": (
            "2024年10月9日，瑞典皇家科学院宣布将诺贝尔化学奖授予"
            "Google DeepMind的Demis Hassabis、John Jumper以及David Baker，"
            "表彰他们在蛋白质结构预测领域的突破性贡献。"
            "其中Hassabis和Jumper因开发AlphaFold2系统获奖，"
            "该系统能够以极高精度预测蛋白质的三维结构，"
            "已被全球超过190个国家的200万研究人员使用。"
            "Baker则因从头设计全新蛋白质而获奖。"
        ),
        "expected_hype": False,
        "expected_bs_min": 0,
        "reason": "2024年诺贝尔化学奖属实，获奖者和理由均可核实，内容客观准确",
    },
]


def _verdict_icon(result, expected):
    if result.get("error"):
        return "💥"
    header = result.get("header", {})
    bs = header.get("bullshit_index") or result.get("bullshit_index") or 0
    exp_hype = expected["expected_hype"]
    exp_bs_min = expected["expected_bs_min"]
    predicted_hype = bs >= 56
    if exp_hype is None:
        return "⚪"
    if predicted_hype == exp_hype and bs >= exp_bs_min:
        return "✅"
    if predicted_hype == exp_hype:
        return "⚠️"
    return "❌"


def _fmt_bs(value):
    if value is None:
        return "N/A"
    bar_len = int(value / 10)
    bar = "█" * bar_len + "░" * (10 - bar_len)
    return f"{value:3d}/100 [{bar}]"


def run_eval(only=None):
    cases = TEXT_CASES
    if only:
        cases = [c for c in cases if c["id"] in only]

    print(f"\n{'═'*60}")
    print(f"  鉴屎官 · 文字链路评估  ({len(cases)} 条文本)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═'*60}\n")

    records = []
    for case in cases:
        cid = case["id"]
        exp_hype = case["expected_hype"]
        exp_bs_min = case["expected_bs_min"]

        print(f"🔍 [{cid}]")
        print(f"   {case['label']}")
        print(f"   预期: {'夸大/假' if exp_hype else '基本属实'} | BS >= {exp_bs_min}")

        t0 = time.time()
        try:
            result = analyze_text(case["text"])
        except Exception as e:
            result = {"error": str(e), "bullshit_index": None}
        elapsed = time.time() - t0

        icon = _verdict_icon(result, case)
        header = result.get("header", {})
        bs = header.get("bullshit_index") or result.get("bullshit_index")
        risk = header.get("risk_level", "")
        toxic = result.get("toxic_review", "")
        error = result.get("error", "")
        invest_rpt = result.get("investigation_report", {})
        hype = invest_rpt.get("hype_check", "")
        intent = invest_rpt.get("intent_check", "")

        print(f"   结果: {icon}  {risk}  BS={_fmt_bs(bs)}  耗时={elapsed:.1f}s")
        if hype:
            print(f"   夸大: {hype[:80]}{'...' if len(hype) > 80 else ''}")
        if intent:
            print(f"   意图: {intent[:80]}{'...' if len(intent) > 80 else ''}")
        if toxic:
            print(f"   锐评: {toxic[:80]}{'...' if len(toxic) > 80 else ''}")
        if error:
            print(f"   错误: {error[:120]}")
        print()

        records.append({
            "id": cid,
            "label": case["label"],
            "expected_hype": exp_hype,
            "expected_bs_min": exp_bs_min,
            "bullshit_index": bs,
            "risk_level": risk,
            "truth_label": header.get("truth_label", ""),
            "verdict": header.get("verdict", ""),
            "hype_check": hype,
            "missing_info": invest_rpt.get("missing_info", ""),
            "intent_check": intent,
            "toxic_review": (toxic or "")[:300],
            "flaw_list": result.get("flaw_list", []),
            "one_line_summary": result.get("one_line_summary", ""),
            "error": error,
            "elapsed_s": round(elapsed, 2),
            "verdict_icon": icon,
            "token_usage": result.get("_token_usage", {}),
        })

    return records


def _stats(records):
    total = len(records)
    success = sum(1 for r in records if not r["error"])
    correct = sum(1 for r in records if r["verdict_icon"] in ("✅", "⚠️"))
    bs_values = [r["bullshit_index"] for r in records if r["bullshit_index"] is not None]
    avg_bs = round(sum(bs_values) / len(bs_values), 1) if bs_values else 0
    avg_t = round(sum(r["elapsed_s"] for r in records) / total, 1) if total else 0
    total_in = sum(r.get("token_usage", {}).get("input_tokens", 0) for r in records)
    total_out = sum(r.get("token_usage", {}).get("output_tokens", 0) for r in records)
    return {"total": total, "success": success, "correct_direction": correct, "avg_bs": avg_bs, "avg_elapsed": avg_t,
            "total_input_tokens": total_in, "total_output_tokens": total_out}


def write_report(records):
    stats = _stats(records)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# 鉴屎官 · 文字链路评估报告", "",
        f"> 生成时间：{now}", "",
        "## 汇总", "",
        "| 指标 | 值 |", "|---|---|",
        f"| 总测试条目 | {stats['total']} 条 |",
        f"| 成功解析 | {stats['success']} 条 |",
        f"| 判断方向正确 | {stats['correct_direction']} 条 |",
        f"| 平均扯淡指数 | {stats['avg_bs']} |",
        f"| 平均耗时 | {stats['avg_elapsed']} 秒 |",
        f"| 输入 tokens | {stats['total_input_tokens']:,} |",
        f"| 输出 tokens | {stats['total_output_tokens']:,} |",
        "", "## 详细结果", "",
    ]
    for r in records:
        lines += [
            f"### {r['verdict_icon']} {r['id']} — {r['label']}", "",
            "| 字段 | 值 |", "|---|---|",
            f"| risk_level | {r['risk_level']} |",
            f"| bullshit_index | `{r['bullshit_index']}` (预期 >= `{r['expected_bs_min']}`) |",
            f"| truth_label | {r['truth_label']} |",
            f"| verdict | {r['verdict']} |",
            f"| 耗时 | {r['elapsed_s']} 秒 |", "",
        ]
        if r["hype_check"]:
            lines += [f"**夸大检测：** {r['hype_check']}", ""]
        if r["missing_info"]:
            lines += [f"**遗漏信息：** {r['missing_info']}", ""]
        if r["intent_check"]:
            lines += [f"**意图检测：** {r['intent_check']}", ""]
        if r["toxic_review"]:
            lines += ["**锐评：**", "", f"> {r['toxic_review']}", ""]
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


def print_summary(records):
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
    if "--only" in sys.argv:
        _idx = sys.argv.index("--only")
        _only = sys.argv[_idx + 1:]
    records = run_eval(only=_only)
    print_summary(records)
    write_report(records)
