# -*- coding: utf-8 -*-
"""
模型横向对比脚本
用法：python tests/compare_models.py
对比范围：EXPECTATIONS 中所有有预期配置的 fixture（可确定 pass/fail/warn 的用例）
对比模型：见 MODELS 列表
不修改任何应用代码，仅临时写 config.json 的 model 字段后还原
"""
import json
import pathlib
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_ROOT = pathlib.Path(__file__).parent.parent
_SRC  = _ROOT / "src"
sys.path.insert(0, str(_SRC))
sys.path.insert(0, str(pathlib.Path(__file__).parent))

CONFIG_PATH = _ROOT / "config.json"

# ── 对比模型列表 ───────────────────────────────────────────────────────────────
MODELS = [
    ("gemini-3-flash-preview",  "Gemini 3 Flash Preview（当前基准）"),
    ("gemini-2.5-pro",          "Gemini 2.5 Pro"),
    ("gemini-3.1-pro-preview",  "Gemini 3.1 Pro Preview"),
]


def patch_model(model_id: str) -> str:
    """临时修改 config.json 中的 model 字段，返回原始值"""
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    provider = cfg["active_provider"]
    original = cfg["providers"][provider]["model"]
    cfg["providers"][provider]["model"] = model_id
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return original


def restore_model(model_id: str):
    """还原 config.json 中的 model 字段"""
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    provider = cfg["active_provider"]
    cfg["providers"][provider]["model"] = model_id
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def evaluate(result: dict, exp: dict) -> str:
    bs = result.get("header", {}).get("bullshit_index")
    if bs is None:
        return "fail"
    predicted_fake = bs >= 56
    exp_fake = exp.get("expected_fake")
    exp_bs_min = exp.get("expected_bs_min", 0)
    if predicted_fake != exp_fake:
        return "fail"
    if exp_fake and bs < exp_bs_min:
        return "warn"
    return "pass"


def run_for_model(model_id: str, fixtures: list) -> dict:
    """对一个模型跑全部 fixtures，返回 {filename: (status, bs, elapsed)} 字典"""
    # config.manager.load() 每次都从磁盘读，无缓存，直接用即可
    from ai.analyzer import analyze_image

    results = {}
    total = len(fixtures)
    for i, (filename, image_path, exp) in enumerate(fixtures, 1):
        print(f"  [{i}/{total}] {filename[:50]:<50}", end=" ", flush=True)
        t0 = time.time()
        try:
            result = analyze_image(str(image_path))
            elapsed = time.time() - t0
            status = evaluate(result, exp)
            bs = result.get("header", {}).get("bullshit_index", "?")
        except Exception as e:
            elapsed = time.time() - t0
            status = "fail"
            bs = "ERR"
            result = {}
        print(f"BS={str(bs):<5} [{status}] ({elapsed:.1f}s)")
        results[filename] = (status, bs, elapsed)
    return results


def main():
    from run_vision_eval import EXPECTATIONS, FIXTURES_DIR

    # 两轮独立运行中均失败的顽固用例（Pro模型专项测试）
    FAILING_FIXTURES = [
        "fake_rt_iran_hormuz_rmb.jpeg",       # 4个Flash模型全败，最顽固
        "fake_piyao_ai_07.png",               # 2.0/2.5 Flash均败
        "real_mps_waimai_rumor_case.png",     # 2.0 Flash两轮均败
        "real_web_mem_2024_report.jpg",       # 2.0 Flash两轮均败
    ]

    # 只测失败的 fixture
    fixtures = []
    for filename in FAILING_FIXTURES:
        exp = EXPECTATIONS.get(filename)
        if exp is None:
            print(f"警告：{filename} 不在 EXPECTATIONS 中，跳过")
            continue
        image_path = FIXTURES_DIR / filename
        if not image_path.exists():
            print(f"警告：找不到 {filename}，跳过")
            continue
        fixtures.append((filename, image_path, exp))

    print(f"\n针对失败用例对比，共 {len(fixtures)} 个\n")
    print("=" * 70)

    all_results: dict[str, dict] = {}  # model_id -> {filename: (status, bs, elapsed)}

    original_model = None
    try:
        for model_id, model_label in MODELS:
            print(f"\n{'='*70}")
            print(f"模型：{model_label}")
            print(f"ID  ：{model_id}")
            print(f"{'='*70}")

            original_model = patch_model(model_id)
            results = run_for_model(model_id, fixtures)
            all_results[model_id] = results

            n_pass = sum(1 for s, _, _ in results.values() if s == "pass")
            n_fail = sum(1 for s, _, _ in results.values() if s == "fail")
            n_warn = sum(1 for s, _, _ in results.values() if s == "warn")
            print(f"\n  小计：✅{n_pass} 通过  ❌{n_fail} 失败  ⚠️{n_warn} 偏差")

    finally:
        if original_model:
            restore_model(original_model)
            print(f"\n已还原 model → {original_model}")

    # ── 汇总对比表 ──────────────────────────────────────────────────────────────
    print("\n\n" + "=" * 80)
    print("模型对比汇总")
    print("=" * 80)
    header = f"{'模型':<35} {'通过':>6} {'失败':>6} {'偏差':>6} {'通过率':>8}"
    print(header)
    print("-" * 65)
    for model_id, model_label in MODELS:
        res = all_results.get(model_id, {})
        n_pass = sum(1 for s, _, _ in res.values() if s == "pass")
        n_fail = sum(1 for s, _, _ in res.values() if s == "fail")
        n_warn = sum(1 for s, _, _ in res.values() if s == "warn")
        n_total = n_pass + n_fail + n_warn
        rate = f"{n_pass/n_total*100:.1f}%" if n_total else "N/A"
        print(f"{model_label:<35} {n_pass:>6} {n_fail:>6} {n_warn:>6} {rate:>8}")

    # ── 逐用例差异（找出在基准中失败、在其他模型中通过的）──────────────────────
    baseline_id = MODELS[0][0]
    baseline = all_results.get(baseline_id, {})
    failing_in_baseline = {f for f, (s, _, _) in baseline.items() if s in ("fail", "warn")}

    if failing_in_baseline:
        print(f"\n\n基准模型（{MODELS[0][1]}）失败/偏差的用例（{len(failing_in_baseline)}个）在各模型的表现：")
        print("-" * 80)
        col_w = 22
        header2 = f"{'fixture':<45}" + "".join(f"{ml[:col_w]:<{col_w}}" for _, ml in MODELS)
        print(header2)
        print("-" * (45 + col_w * len(MODELS)))
        for filename in sorted(failing_in_baseline):
            exp = EXPECTATIONS[filename]
            label = exp.get("label", filename)[:40]
            row = f"{filename[:44]:<45}"
            for model_id, _ in MODELS:
                res = all_results.get(model_id, {})
                s, bs, _ = res.get(filename, ("N/A", "?", 0))
                cell = f"{s}(BS={bs})"
                row += f"{cell:<{col_w}}"
            print(row)
            print(f"  └ {label}")

    # ── 保存文字报告 ────────────────────────────────────────────────────────────
    report_lines = []
    report_lines.append("# 模型对比报告\n")
    report_lines.append(f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    report_lines.append(f"测试用例数：{len(fixtures)}\n\n")
    report_lines.append("## 汇总\n\n")
    report_lines.append(f"| 模型 | 通过 | 失败 | 偏差 | 通过率 |\n|---|---|---|---|---|\n")
    for model_id, model_label in MODELS:
        res = all_results.get(model_id, {})
        n_pass = sum(1 for s, _, _ in res.values() if s == "pass")
        n_fail = sum(1 for s, _, _ in res.values() if s == "fail")
        n_warn = sum(1 for s, _, _ in res.values() if s == "warn")
        n_total = n_pass + n_fail + n_warn
        rate = f"{n_pass/n_total*100:.1f}%" if n_total else "N/A"
        report_lines.append(f"| {model_label} | {n_pass} | {n_fail} | {n_warn} | {rate} |\n")
    report_lines.append("\n## 失败用例逐一对比\n\n")
    for filename in sorted(failing_in_baseline):
        exp = EXPECTATIONS[filename]
        label = exp.get("label", filename)
        report_lines.append(f"### {filename}\n**{label}**\n\n")
        for model_id, model_label in MODELS:
            res = all_results.get(model_id, {})
            s, bs, elapsed = res.get(filename, ("N/A", "?", 0))
            report_lines.append(f"- {model_label}：`{s}` BS={bs} ({elapsed:.1f}s)\n")
        report_lines.append("\n")

    report_path = pathlib.Path(__file__).parent / "model_compare_report.md"
    report_path.write_text("".join(report_lines), encoding="utf-8")
    print(f"\n详细报告已保存：{report_path}")


if __name__ == "__main__":
    main()
