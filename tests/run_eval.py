"""
BullshitDetector 自动化评估脚本
将测试用例文本渲染为图片，调用 analyze_screenshot 进行分析，评估准确率。
"""
import sys
import os
import json
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from PIL import Image, ImageDraw, ImageFont
import base64
import io

from ai.analyzer import analyze_screenshot
from config import OPENAI_API_KEY


def text_to_image_base64(text: str, width=800, font_size=20, padding=30) -> str:
    """将文本渲染为图片并返回 base64 编码"""
    font = None
    font_paths = [
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()

    # 自动换行
    max_chars_per_line = (width - 2 * padding) // (font_size // 2 + 2)
    lines = []
    for paragraph in text.split('\n'):
        while len(paragraph) > max_chars_per_line:
            lines.append(paragraph[:max_chars_per_line])
            paragraph = paragraph[max_chars_per_line:]
        lines.append(paragraph)

    line_height = font_size + 8
    height = max(padding * 2 + len(lines) * line_height, 200)

    img = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(img)
    y = padding
    for line in lines:
        draw.text((padding, y), line, fill='black', font=font)
        y += line_height

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode('utf-8')


def evaluate_result(result: dict, test_case: dict) -> dict:
    """评估单个测试用例的结果"""
    tc_type = test_case["type"]
    expected_level = test_case["expected_truth_level"]

    is_fake = result.get("is_fake", False)
    confidence = result.get("confidence", 0.0)
    bullshit_index = result.get("bullshit_index", 50)
    roast = result.get("roast", "")
    error = result.get("error", None)

    # 有错误时直接判定为失败，不计入准确率
    if error:
        correct = False
    elif expected_level == "high":
        correct = not is_fake and bullshit_index <= 40
    elif expected_level == "low":
        correct = is_fake or bullshit_index >= 50
    elif expected_level == "very_low":
        correct = is_fake and bullshit_index >= 60
    else:
        correct = False

    roast_quality = "good" if len(roast) > 10 and roast not in ["无法判断", "分析过程翻车了"] else "weak"

    return {
        "id": test_case["id"],
        "type": tc_type,
        "category": test_case["category"],
        "expected_level": expected_level,
        "is_fake": is_fake,
        "confidence": confidence,
        "bullshit_index": bullshit_index,
        "correct": correct,
        "roast": roast,
        "roast_quality": roast_quality,
        "error": error,
    }


def run_evaluation(data_path: str) -> list:
    """运行完整评估"""
    if not OPENAI_API_KEY:
        print("❌ 错误: OPENAI_API_KEY 未配置，无法运行评估")
        print("请设置环境变量: export OPENAI_API_KEY=your_key")
        sys.exit(1)

    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    test_cases = data["test_cases"]
    results = []

    for i, tc in enumerate(test_cases):
        print(f"\n[{i+1}/{len(test_cases)}] 测试用例 #{tc['id']}: {tc['type']} - {tc['category']}")
        print(f"  输入: {tc['input_text'][:60]}...")

        img_b64 = text_to_image_base64(tc["input_text"])
        t0 = time.time()
        result = analyze_screenshot(img_b64)
        elapsed = time.time() - t0

        eval_result = evaluate_result(result, tc)
        eval_result["elapsed_seconds"] = round(elapsed, 1)
        results.append(eval_result)

        # 记录搜索日志
        search_log = result.get("_search_log", [])
        eval_result["search_triggered"] = len(search_log) > 0
        eval_result["search_queries"] = [s.get("query", "") for s in search_log]
        eval_result["search_results_preview"] = [s.get("result_preview", "") for s in search_log]

        status = "✅ 正确" if eval_result["correct"] else "❌ 错误"
        triggered = "是" if eval_result["search_triggered"] else "否"
        print(f"  结果: is_fake={result.get('is_fake')}, BS={result.get('bullshit_index')}, "
              f"confidence={result.get('confidence')} -> {status} ({elapsed:.1f}s)")
        print(f"  搜索触发: {triggered}")
        if eval_result["search_triggered"]:
            print(f"  搜索关键词: {eval_result['search_queries']}")
        print(f"  锐评: {result.get('roast', 'N/A')}")

        if eval_result["error"]:
            print(f"  ⚠️ 错误: {eval_result['error']}")

    return results


def generate_report(results: list, iteration: int = 0, prompt_changes: list = None) -> str:
    """生成评估报告 Markdown"""
    total = len(results)
    errors = sum(1 for r in results if r["error"])
    correct = sum(1 for r in results if r["correct"])
    accuracy = correct / total * 100 if total > 0 else 0

    type_stats = {}
    for r in results:
        t = r["type"]
        if t not in type_stats:
            type_stats[t] = {"total": 0, "correct": 0, "errors": 0}
        type_stats[t]["total"] += 1
        if r["correct"]:
            type_stats[t]["correct"] += 1
        if r["error"]:
            type_stats[t]["errors"] += 1

    good_roasts = sum(1 for r in results if r["roast_quality"] == "good")

    type_labels = {
        "real_news": "真实新闻",
        "clickbait": "标题党/夸大",
        "half_true": "半真半假",
        "fabricated": "纯粹编造",
        "time_sensitive_real": "时效性真实新闻",
        "time_sensitive_fake": "时效性假新闻",
    }

    lines = [
        f"# BullshitDetector 评估报告",
        f"",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**迭代次数**: {iteration}",
        f"",
        f"## 总体结果",
        f"",
        f"| 指标 | 结果 |",
        f"|------|------|",
        f"| 总测试用例 | {total} |",
        f"| 正确判断 | {correct} |",
        f"| **准确率** | **{accuracy:.1f}%** {'✅ 达标' if accuracy >= 80 else '❌ 未达标'} |",
        f"| API 错误数 | {errors} {'⚠️ 有错误未正确分析' if errors > 0 else '✅'} |",
        f"| 毒舌锐评质量 | {good_roasts}/{total} 优质 |",
        f"",
        f"## 分类型准确率",
        f"",
        f"| 类型 | 正确/总数 | 准确率 |",
        f"|------|----------|--------|",
    ]

    for t, stats in sorted(type_stats.items()):
        label = type_labels.get(t, t)
        acc = stats["correct"] / stats["total"] * 100
        lines.append(f"| {label} | {stats['correct']}/{stats['total']} | {acc:.0f}% |")

    lines += [
        f"",
        f"## 详细结果",
        f"",
        f"| # | 类型 | 分类 | 预期 | is_fake | BS指数 | 判定 | 耗时 |",
        f"|---|------|------|------|---------|--------|------|------|",
    ]

    for r in results:
        label = type_labels.get(r["type"], r["type"])
        status = "✅" if r["correct"] else "❌"
        err = f" ⚠️{r['error']}" if r["error"] else ""
        lines.append(
            f"| {r['id']} | {label} | {r['category']} | {r['expected_level']} | "
            f"{r['is_fake']} | {r['bullshit_index']} | {status}{err} | {r['elapsed_seconds']}s |"
        )

    lines += [
        f"",
        f"## 毒舌锐评精选",
        f"",
    ]
    for r in results:
        if r["roast_quality"] == "good":
            lines.append(f"- **用例#{r['id']}** ({type_labels.get(r['type'], r['type'])}): {r['roast']}")

    # 时效性用例详细报告
    time_sensitive_results = [r for r in results if r["type"] in ("time_sensitive_real", "time_sensitive_fake")]
    if time_sensitive_results:
        lines += [
            f"",
            f"## 时效性用例详细分析",
            f"",
        ]
        for r in time_sensitive_results:
            label = type_labels.get(r["type"], r["type"])
            status = "✅ 正确" if r["correct"] else "❌ 错误"
            triggered = "是" if r.get("search_triggered") else "否"
            lines.append(f"### 用例 #{r['id']} ({label}) {status}")
            lines.append(f"")
            lines.append(f"- **分类**: {r['category']}")
            lines.append(f"- **预期**: {r['expected_level']}")
            lines.append(f"- **实际**: is_fake={r['is_fake']}, bullshit_index={r['bullshit_index']}")
            lines.append(f"- **搜索触发**: {triggered}")
            if r.get("search_queries"):
                lines.append(f"- **搜索关键词**: {', '.join(r['search_queries'])}")
            if r.get("search_results_preview"):
                for i, preview in enumerate(r["search_results_preview"], 1):
                    lines.append(f"- **搜索结果{i}预览**: {preview[:100]}...")
            lines.append(f"- **锐评**: {r['roast']}")
            lines.append(f"")

    if prompt_changes:
        lines += [
            f"",
            f"## Prompt 迭代历史",
            f"",
        ]
        for i, change in enumerate(prompt_changes, 1):
            lines.append(f"### 迭代 {i}")
            lines.append(f"")
            lines.append(f"**修改内容**: {change['description']}")
            lines.append(f"**准确率变化**: {change['before_accuracy']:.1f}% -> {change['after_accuracy']:.1f}%")
            lines.append(f"")

    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    data_path = os.path.join(os.path.dirname(__file__), "data.json")
    results = run_evaluation(data_path)

    report = generate_report(results)
    report_path = os.path.join(os.path.dirname(__file__), "eval_report.md")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)

    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    accuracy = correct / total * 100 if total > 0 else 0
    print(f"\n{'='*50}")
    print(f"评估完成: {correct}/{total} 正确, 准确率 {accuracy:.1f}%")
    print(f"报告已保存至: {report_path}")

    # 输出 JSON 结果供迭代脚本使用
    json_path = os.path.join(os.path.dirname(__file__), "eval_results.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({"accuracy": accuracy, "results": results}, f, ensure_ascii=False, indent=2)
