"""求出处 (source_find) 跨模型对比：preview vs lite，3 个真实图片 case。

⚠ 调用 Google Vision API + 真实 LLM。用户明确同意才跑。
"""

import base64
import json
import os
import pathlib
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))


CASES = [
    {"id": "96d575236f8eee31", "label": "Doraemon (image+text)"},
    {"id": "e897e449e782fd3e", "label": "image-only A"},
    {"id": "2ab4a66a9a2ed933", "label": "image-only B"},
]

MODELS = ["gemini-3-flash-preview", "gemini-3.1-flash-lite"]


def load_imgs(cid: str):
    meta = json.load(open(f"historyCache/{cid}/meta.json", "r", encoding="utf-8"))
    n = meta.get("image_count", 0)
    imgs = []
    for i in range(n):
        p = f"historyCache/{cid}/images/{i}.jpg"
        if os.path.exists(p):
            with open(p, "rb") as f:
                imgs.append(base64.b64encode(f.read()).decode())
    return imgs


def set_model(model: str):
    cfg = json.load(open("config.json", "r", encoding="utf-8"))
    if "providers" not in cfg or "openai_compatible" not in cfg["providers"]:
        raise RuntimeError(
            f"config.json 结构异常 (keys={list(cfg.keys())[:8]})，set_model 中止"
        )
    cfg["providers"]["openai_compatible"]["model"] = model
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def run_source_find(imgs):
    for mod in list(sys.modules):
        if mod.startswith("ai.") or mod == "ai":
            sys.modules.pop(mod, None)
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))
    from ai.analyzer import source_find_screenshot
    t0 = time.time()
    try:
        r = source_find_screenshot(imgs, extra_text="")
        return {"ok": True, "elapsed": time.time() - t0, "result": r}
    except Exception as e:
        return {"ok": False, "elapsed": time.time() - t0, "error": f"{type(e).__name__}: {e}"}


def main():
    orig = json.load(open("config.json", "r", encoding="utf-8"))["providers"]["openai_compatible"]["model"]
    print(f"原 model: {orig}")
    print(f"\n跑 {len(MODELS)} 模型 × {len(CASES)} case = {len(MODELS)*len(CASES)} 次求出处\n")
    results = {}
    try:
        for model in MODELS:
            print(f"\n========== MODEL: {model} ==========")
            set_model(model)
            for case in CASES:
                key = f"{model}|{case['id']}"
                print(f"\n--- {case['label']} ({case['id']}) ---")
                imgs = load_imgs(case["id"])
                if not imgs:
                    print("  no imgs")
                    continue
                res = run_source_find(imgs)
                results[key] = res
                if res["ok"]:
                    r = res["result"]
                    preview_keys = list((r if isinstance(r, dict) else {}).keys())[:8]
                    print(f"  {res['elapsed']:.1f}s | result keys={preview_keys}")
                    # 尝试打印关键字段
                    for k in ("source", "answer", "verdict", "summary", "explain", "title", "name", "content"):
                        v = (r or {}).get(k)
                        if v:
                            print(f"    {k}: {str(v)[:200]}")
                            break
                else:
                    print(f"  FAIL {res['elapsed']:.1f}s: {res['error'][:200]}")
    finally:
        set_model(orig)
        print(f"\n已还原 model 为 {orig}")

    # 报告
    lines = [f"# 求出处对比 (preview vs lite)\n", f"- 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"]
    lines.append("## 汇总\n")
    lines.append("| case | model | 耗时 | result 摘要 |")
    lines.append("|---|---|---|---|")
    for case in CASES:
        for model in MODELS:
            res = results.get(f"{model}|{case['id']}", {})
            if res.get("ok"):
                r = res["result"] or {}
                # 找一个非空字段当摘要
                summary = ""
                for k in ("source", "answer", "verdict", "summary", "explain", "title", "name", "content"):
                    if r.get(k):
                        summary = f"{k}={str(r[k])[:120]}"
                        break
                if not summary:
                    summary = f"keys={list(r.keys())[:6]}"
                lines.append(f"| {case['label']} | {model} | {res['elapsed']:.1f}s | {summary} |")
            else:
                lines.append(f"| {case['label']} | {model} | {res.get('elapsed',0):.1f}s | ❌ {res.get('error','')[:80]} |")
    lines.append("\n## 详细 result\n")
    for case in CASES:
        lines.append(f"### {case['label']} (`{case['id']}`)\n")
        for model in MODELS:
            res = results.get(f"{model}|{case['id']}", {})
            if not res.get("ok"):
                lines.append(f"**{model}** — ❌ {res.get('error','')[:200]}\n")
                continue
            r = res["result"] or {}
            lines.append(f"**{model}** ({res['elapsed']:.1f}s)")
            lines.append("```json")
            lines.append(json.dumps(r, ensure_ascii=False, indent=2)[:2000])
            lines.append("```\n")

    out = "scripts/_compare_source_find.md"
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n✅ {out}")


if __name__ == "__main__":
    main()
