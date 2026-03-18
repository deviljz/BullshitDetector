"""analyze_accuracy_test.py — 鉴屎官准确率抽样测试
对 5 条已知真相的文本用例测试 analyze_text()，验证 bullshit_index 和 risk_level 是否符合预期。

运行: F:\Project\BullshitDetector\.venv\Scripts\python.exe tests/analyze_accuracy_test.py
"""
import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from ai.analyzer import analyze_text

CASES = [
    {
        "id": "T01",
        "label": "物理定律违背（铁律三，无需搜索）",
        "text": "科学家最新研究表明，通过量子纠缠技术可以实现超光速通信，已在实验室成功验证并申请专利，预计明年商用。",
        "expect_bs_min": 85,
        "expect_bs_max": 100,
        "expect_risk_prefix": "🚨",
    },
    {
        "id": "T02",
        "label": "高仿官方数据（铁律一否决权）",
        "text": "国家统计局今日发布最新数据：2025年第一季度GDP同比增长18.6%，创35年来历史新高，超过市场预期的4.5%。",
        "expect_bs_min": 80,
        "expect_bs_max": 100,
        "expect_risk_prefix": "🚨",
    },
    {
        "id": "T03",
        "label": "食物相克谣言（铁律三，含假伤亡声明）",
        # 含食物相克伪科学 + 假伤亡声明，双重造假 BS 应在 70+ 甚至更高
        "text": "紧急提醒！螃蟹和柿子绝对不能同食，两者相遇会产生砒霜，已有多名市民因此急救入院，请立刻转发给家人朋友！！！",
        "expect_bs_min": 70,
        "expect_bs_max": 100,
        "expect_risk_prefix": "🔶,🚨",  # 食物相克+假伤亡声明，高风险均可接受
    },
    {
        "id": "T04",
        "label": "基本属实新闻（有权威来源）",
        "text": "苹果公司于2023年9月12日在加州库比蒂诺总部举办发布会，正式推出iPhone 15系列手机。新款机型首次采用USB-C接口取代原有Lightning接口，并在标准版机型上引入动态岛（Dynamic Island）设计。",
        "expect_bs_min": 0,
        "expect_bs_max": 30,
        "expect_risk_prefix": "✅",
    },
    {
        "id": "T05",
        "label": "古代DNA克隆谣言（铁律三+标题党）",
        "text": "震惊！史诗级突破！中国科学家成功从100万年前的恐龙化石中提取了完整DNA序列，克隆恐龙计划正式启动，预计5年内可见活体！！！",
        "expect_bs_min": 85,
        "expect_bs_max": 100,
        "expect_risk_prefix": "🚨",
    },
]

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"

results = []

for case in CASES:
    print(f"\n{'='*60}")
    print(f"[{case['id']}] {case['label']}")
    print(f"  输入: {case['text'][:70]}...")
    print(f"  预期: BS {case['expect_bs_min']}-{case['expect_bs_max']}, risk 前缀={case['expect_risk_prefix']}")
    try:
        result = analyze_text(case['text'])
        header = result.get('header', {})
        bs = header.get('bullshit_index', -1)
        risk = header.get('risk_level', '')
        verdict = header.get('verdict', '')
        truth_label = header.get('truth_label', '')

        bs_ok = case['expect_bs_min'] <= bs <= case['expect_bs_max']
        # expect_risk_prefix 可以是逗号分隔的多个前缀（如 "🔶,🚨"）
        accepted = [p.strip() for p in case['expect_risk_prefix'].split(',')]
        risk_ok = any(risk.startswith(p) for p in accepted)
        passed = bs_ok and risk_ok

        print(f"  结果: BS={bs}, risk={risk}")
        print(f"  判决: {verdict[:70]}")
        print(f"  标签: {truth_label[:60]}")

        claim_verdicts = [c.get('verdict', '') for c in result.get('claim_verification', [])]
        print(f"  声明核查: {claim_verdicts}")

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
    print(f"  {mark} [{r['id']}] {r['label'][:30]:30s} | {detail}")

if passed_count < total:
    sys.exit(1)
