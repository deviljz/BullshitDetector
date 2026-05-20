"""跨 Gemini 模型对比：gemini-3-flash-preview vs gemini-3.1-flash-lite

⚠ 调用真实 LLM API。用户明确同意才跑。
"""

import json
import pathlib
import sys
import time

# Windows 控制台 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from openai import OpenAI  # noqa


SYSTEM_PROMPT = """你是一位严谨的事实核查员。给你一个声明，请：
1) 判断该声明是「✓ 属实」「✗ 不实」「？ 信息不足」之一
2) 用 1-2 句话给出关键依据或反驳
输出格式严格为：[判断] 解释"""

CLAIMS = [
    "1969 年阿波罗 11 号是人类首次登月。",
    "中国大陆地区的微信支付限额每日不能超过 50 万元人民币。",
    "电影《监狱来的妈妈》是由秦晓宇执导、讲述母亲反抗家暴失手杀夫入狱故事的国产电影。",
    "DeepSeek V4 Pro 模型上下文窗口支持 1 百万 tokens。",
    "2026 年广西柳州在 5 月 18 日 21 时 44 分发生过 5.2 级地震。",
]

MODELS = ["gemini-3-flash-preview", "gemini-3.1-flash-lite"]


def load_client():
    cfg = json.load(open("config.json", "r", encoding="utf-8"))
    p = cfg["providers"]["openai_compatible"]
    return OpenAI(api_key=p["api_key"], base_url=p["base_url"]), p


def run_one(client, model, claim, max_tokens=400):
    t0 = time.time()
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": claim},
            ],
            max_tokens=max_tokens,
            temperature=0.3,
        )
        elapsed = time.time() - t0
        return {
            "ok": True,
            "elapsed": elapsed,
            "content": r.choices[0].message.content or "",
            "prompt_tokens": r.usage.prompt_tokens,
            "gen_tokens": r.usage.completion_tokens,
        }
    except Exception as e:
        return {"ok": False, "elapsed": time.time() - t0, "error": f"{type(e).__name__}: {str(e)[:200]}"}


def main():
    client, _ = load_client()
    print(f"[1/2] 跑 {len(MODELS)} 模型 × {len(CLAIMS)} claim = {len(MODELS)*len(CLAIMS)} 次调用")

    results = []
    for i, claim in enumerate(CLAIMS, 1):
        print(f"\n--- claim {i}: {claim[:60]}")
        row = {"claim": claim}
        for model in MODELS:
            res = run_one(client, model, claim)
            row[model] = res
            tag = "OK" if res["ok"] else "FAIL"
            extra = f"{res['gen_tokens']} tok" if res["ok"] else res["error"][:80]
            print(f"  [{model}] {tag} {res['elapsed']:.2f}s | {extra}")
        results.append(row)

    print(f"\n[2/2] 写报告")
    lines = ["# Gemini 模型对比: 3-flash-preview vs 3.1-flash-lite\n"]
    lines.append(f"- 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- claim 数: {len(CLAIMS)}\n")

    # 汇总表
    lines.append("## 汇总（耗时 / token / 错误）\n")
    lines.append("| # | claim | 3-flash-preview | 3.1-flash-lite |")
    lines.append("|---|---|---|---|")
    for i, r in enumerate(results, 1):
        a = r[MODELS[0]]
        b = r[MODELS[1]]
        fa = f"{a['elapsed']:.1f}s / {a.get('gen_tokens','-')} tok" if a["ok"] else f"❌ {a['error'][:50]}"
        fb = f"{b['elapsed']:.1f}s / {b.get('gen_tokens','-')} tok" if b["ok"] else f"❌ {b['error'][:50]}"
        lines.append(f"| {i} | {r['claim'][:50]} | {fa} | {fb} |")

    # 详细输出对比
    lines.append("\n## 逐条对比\n")
    for i, r in enumerate(results, 1):
        lines.append(f"### Claim {i}: {r['claim']}\n")
        for m in MODELS:
            res = r[m]
            if res["ok"]:
                lines.append(f"**{m}** ({res['elapsed']:.2f}s, {res['gen_tokens']} tok)")
                lines.append(f"> {res['content']}\n")
            else:
                lines.append(f"**{m}** — ❌ {res['error']}\n")

    # 速度/成本统计
    lines.append("\n## 平均指标\n")
    lines.append("| 模型 | 平均耗时 | 平均输出 token | 成功率 |")
    lines.append("|---|---|---|---|")
    for m in MODELS:
        oks = [r[m] for r in results if r[m]["ok"]]
        avg_t = sum(x["elapsed"] for x in oks) / len(oks) if oks else 0
        avg_g = sum(x["gen_tokens"] for x in oks) / len(oks) if oks else 0
        rate = f"{len(oks)}/{len(results)}"
        lines.append(f"| {m} | {avg_t:.2f}s | {avg_g:.0f} | {rate} |")

    output = "scripts/_compare_gemini_models.md"
    with open(output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"✅ {output}")


if __name__ == "__main__":
    main()
