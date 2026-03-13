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
    "485b9a1ada6b21cc3687da2c1fd85835.jpg": {
        "label": "人民日报订婚报道（来源归属存疑）",
        "expected_fake": True,
        "expected_bs_min": 60,
        "reason": "订婚事件属实，但人民日报不发此类内容，来源归属伪造，属张冠李戴",
    },
    "7679a22f6713b1684a8c91e76a94dd31.jpg": {
        "label": "伊朗导弹图+后期加字（移花接木合成假信息）",
        "expected_fake": True,
        "expected_bs_min": 80,
        "reason": "真实导弹图片被加上虚假文字，整体为移花接木式造假",
    },
    "90044206a5af0e27f0d7c6876020ea9c.jpg": {
        "label": "Silverstein购楼+9/11阴谋论暗示（真实外壳包裹阴谋论）",
        "expected_fake": True,
        "expected_bs_min": 70,
        "reason": "购楼/保险/租约均属实，但帖子核心目的是传播9/11阴谋论，属半真半假操纵手法",
    },
    "e7ec7463e3c077e87201e0c3e4b8e087.jpg": {
        "label": "伊朗结婚年龄（半真半假）",
        "expected_fake": True,
        "expected_bs_min": 50,
        "reason": "伊朗法律条文有一定依据，但断章取义夸大，有虚构成分即判假",
    },
}


def _verdict_icon(result: dict, expected: dict) -> str:
    """判断 AI 结论是否与预期一致（新 schema：用 bullshit_index 替代 is_fake）"""
    if result.get("error"):
        return "💥"
    header = result.get("header", {})
    bs = header.get("bullshit_index") or result.get("bullshit_index") or 0
    exp_fake = expected["expected_fake"]   # True → 预期 bs >= 45；False → 预期 bs < 45
    exp_bs_min = expected["expected_bs_min"]

    # 判断方向：bs >= 45 视为"假"，< 45 视为"真"
    predicted_fake = bs >= 45
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


def run_eval() -> list[dict]:
    images = sorted(
        p for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp")
        for p in FIXTURES_DIR.glob(ext)
    )
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
    records = run_eval()
    print_summary(records)
    write_report(records)
