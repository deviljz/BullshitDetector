"""
skill vs app 对比评估脚本
合并图片(215) + 文字(23) 共238个用例，随机抽样，按 skill 标准评判差距。
用法：python tests/run_skill_comparison.py --round 1 --seed 42 --n 10
"""
import sys, json, random, argparse, time, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# ── 加载文字用例 ──────────────────────────────────────────────────────────────
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "run_text_eval", os.path.join(os.path.dirname(__file__), "run_text_eval.py")
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
TEXT_CASES = _mod.TEXT_CASES

# ── 加载图片用例（EXPECTATIONS + fixtures 目录） ──────────────────────────────
_vspec = importlib.util.spec_from_file_location(
    "run_vision_eval", os.path.join(os.path.dirname(__file__), "run_vision_eval.py")
)
_vmod = importlib.util.module_from_spec(_vspec)
_vspec.loader.exec_module(_vmod)
EXPECTATIONS = _vmod.EXPECTATIONS

FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

IMAGE_CASES = []
for fname, exp in EXPECTATIONS.items():
    fpath = os.path.join(FIXTURE_DIR, fname)
    if os.path.exists(fpath):
        IMAGE_CASES.append({
            "id": fname,
            "label": exp.get("label", fname),
            "file_path": fpath,
            "expected_hype": exp.get("expected_fake"),   # True/False/None
            "expected_bs_min": exp.get("expected_bs_min", 0),
            "type": "image",
        })

TEXT_CASES_WRAPPED = [
    {**c, "type": "text"}
    for c in TEXT_CASES
]

ALL_CASES = TEXT_CASES_WRAPPED + IMAGE_CASES
print(f"[加载] 文字用例: {len(TEXT_CASES_WRAPPED)}  图片用例: {len(IMAGE_CASES)}  合计: {len(ALL_CASES)}", flush=True)

# ── app 调用 ──────────────────────────────────────────────────────────────────
from ai.analyzer import analyze_text, analyze_image

def run_case(case):
    if case["type"] == "text":
        return analyze_text(case["text"])
    else:
        return analyze_image(case["file_path"])

# ── skill 标准评判 ─────────────────────────────────────────────────────────────
def skill_judge(case, result):
    """
    按 fact-check skill 5维度评判，返回 (score/5, gaps[])
    D1 内容性质识别
    D2 逐点声明核查（verdict 标准格式）
    D3 有效信源数存在
    D4 来源类型标注
    D5 综合方向正确
    """
    gaps = []
    score = 0

    if result.get("error"):
        gaps.append("💥 API错误")
        return 0, gaps

    header = result.get("header", {})
    inv = result.get("investigation_report", {})
    claims = result.get("claim_verification", [])
    bs = header.get("bullshit_index") or 0

    # D1 内容性质（>3字即视为有效，避免短描述误判）
    cn = inv.get("content_nature", "")
    if cn and len(cn) > 3:
        score += 1
    else:
        gaps.append("D1[内容性质缺失]")

    # D2 verdict 格式
    VALID_VERDICTS = {"独立核实属实", "官方自述", "伪造", "无法核实", "存疑"}
    if not claims:
        gaps.append("D2[无逐点声明]")
    else:
        bad = [c for c in claims if not any(v in c.get("verdict","") for v in VALID_VERDICTS)]
        if bad:
            gaps.append(f"D2[verdict格式错误] {len(bad)}条: e.g. '{bad[0].get('verdict','')[:40]}'")
        else:
            score += 1

    # D3 有效信源数
    has_eff = any(c.get("effective_sources") is not None for c in claims)
    if has_eff:
        score += 1
    else:
        gaps.append("D3[有效信源缺失]")

    # D4 来源类型
    VALID_TYPES = {"primary","independent","syndicated","self_reported","none"}
    has_type = any(c.get("best_source_type","").lower() in VALID_TYPES for c in claims)
    if has_type:
        score += 1
    else:
        gaps.append("D4[来源类型缺失]")

    # D5 方向
    exp_hype = case.get("expected_hype")
    predicted_hype = bs >= 56
    if exp_hype is None:
        score += 1   # ⚪ 跳过
    elif predicted_hype == exp_hype:
        score += 1
    else:
        gaps.append(f"D5[方向错误] 预期fake={exp_hype} BS={bs}(hype={predicted_hype})")

    return score, gaps


def direction_icon(case, result):
    if result.get("error"):
        return "💥"
    bs = (result.get("header") or {}).get("bullshit_index") or 0
    exp = case.get("expected_hype")
    if exp is None:
        return "⚪"
    return "✅" if (bs >= 56) == exp else "❌"


# ── 主流程 ────────────────────────────────────────────────────────────────────
def run_round(round_num, seed, n=10):
    rng = random.Random(seed)
    selected = rng.sample(ALL_CASES, min(n, len(ALL_CASES)))

    txt_cnt = sum(1 for c in selected if c["type"] == "text")
    img_cnt = sum(1 for c in selected if c["type"] == "image")
    print(f"\n{'═'*70}", flush=True)
    print(f"  ROUND {round_num}  |  seed={seed}  |  {len(selected)}案例 (文字{txt_cnt} 图片{img_cnt})", flush=True)
    print(f"{'═'*70}", flush=True)

    round_results = []
    total_gaps = {}

    for i, case in enumerate(selected):
        tp = "📄" if case["type"] == "text" else "🖼️"
        print(f"\n[{i+1}/{len(selected)}] {tp} {case['id']} — {case['label']}", flush=True)
        t0 = time.time()
        try:
            result = run_case(case)
        except Exception as e:
            import traceback
            result = {"error": str(e), "header": {}, "investigation_report": {}, "claim_verification": []}
            print(f"  💥 {e}", flush=True)

        elapsed = time.time() - t0
        bs = (result.get("header") or {}).get("bullshit_index") or 0
        score, gaps = skill_judge(case, result)
        icon = direction_icon(case, result)

        print(f"  BS={bs:3d}  方向={icon}  skill对齐={score}/5  耗时={elapsed:.1f}s", flush=True)
        for g in gaps:
            print(f"  ⚠️  {g}", flush=True)

        for c in result.get("claim_verification", []):
            print(f"  📌 [{c.get('verdict','?')[:12]}] src={c.get('effective_sources','?')} type={c.get('best_source_type','?')} | {c.get('claim','')[:50]}", flush=True)

        round_results.append({"id": case["id"], "type": case["type"], "bs": bs, "direction": icon, "skill_score": score, "gaps": gaps})
        for g in gaps:
            key = g.split("]")[0].lstrip("⚠️ ")
            total_gaps[key] = total_gaps.get(key, 0) + 1

    # 汇总
    correct = sum(1 for r in round_results if r["direction"] == "✅")
    skip = sum(1 for r in round_results if r["direction"] == "⚪")
    fail = sum(1 for r in round_results if r["direction"] == "❌")
    avg_score = sum(r["skill_score"] for r in round_results) / len(round_results)

    print(f"\n{'─'*70}", flush=True)
    print(f"  ROUND {round_num} 汇总", flush=True)
    print(f"  方向: ✅{correct} ❌{fail} ⚪{skip} / {len(round_results)}", flush=True)
    print(f"  skill对齐均分: {avg_score:.1f}/5", flush=True)
    if total_gaps:
        print(f"  高频gap:", flush=True)
        for k, v in sorted(total_gaps.items(), key=lambda x: -x[1]):
            print(f"    {k}: {v}次", flush=True)
    else:
        print(f"  ✨ 无gap，全部对齐", flush=True)
    print(f"{'─'*70}", flush=True)

    return round_results, total_gaps


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--n", type=int, default=10)
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else args.round * 42
    run_round(args.round, seed, args.n)
