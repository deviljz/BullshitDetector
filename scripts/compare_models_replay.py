"""双模型 replay 对比：gemini-3-flash-preview vs gemini-3.1-flash-lite，3 个真实历史 case。

⚠ 调用真实 LLM + 真实搜索 API。用户明确同意才跑。
"""

import base64
import json
import os
import pathlib
import sys
import time
import traceback

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))


CASES = [
    {"id": "96d575236f8eee31", "label": "Doraemon (image+text)", "extra": "这么多年了，还有读者记得第二行台词说翻译不对"},
    {"id": "aab19cfdd4f55645", "label": "image-only (recent)", "extra": ""},
    {"id": "baa9c7d8ed6159c4", "label": "text-only 恶之花", "extra": "恶之花是什么梗"},
]

# 每个 setup = (label, active_provider, main_model, verify_claim_override)
# verify_claim_override 非空 → planner 用 main_model，verify 并行用 override（混合 D 模式）
SETUPS = [
    ("mixed-D", "openai_compatible", "gemini-3-flash-preview", "gemini-3.1-flash-lite"),
    ("dsv4-flash", "opencode_zen", "deepseek-v4-flash", ""),
]
MODELS = [s[0] for s in SETUPS]


def load_case(cid: str):
    meta_path = f"historyCache/{cid}/meta.json"
    meta = json.load(open(meta_path, "r", encoding="utf-8"))
    n_img = meta.get("image_count", 0)
    imgs_b64 = []
    for i in range(n_img):
        p = f"historyCache/{cid}/images/{i}.jpg"
        if os.path.exists(p):
            with open(p, "rb") as f:
                imgs_b64.append(base64.b64encode(f.read()).decode())
    return meta, imgs_b64


def set_model(active_provider: str, model: str, verify_override: str = ""):
    cfg = json.load(open("config.json", "r", encoding="utf-8"))
    # Guard: 若 config.json 已被污染（缺 providers），中止以免进一步破坏
    if "providers" not in cfg or active_provider not in cfg["providers"]:
        raise RuntimeError(
            f"config.json 结构异常 (keys={list(cfg.keys())[:8]})，set_model 中止；请手动恢复 config.json"
        )
    cfg["active_provider"] = active_provider
    cfg["providers"][active_provider]["model"] = model
    cfg["verify_claim_model"] = verify_override
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def run_one(cid: str, extra_text: str, imgs_b64: list) -> dict:
    # 强制 reload analyzer 让新 model 生效
    for mod in list(sys.modules):
        if mod.startswith("ai.") or mod == "ai":
            sys.modules.pop(mod, None)
    sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))
    from ai.analyzer import analyze_screenshot_staged
    t0 = time.time()
    try:
        if imgs_b64:
            r = analyze_screenshot_staged(imgs_b64, extra_text=extra_text)
        else:
            # text-only path
            from ai.analyzer import analyze_text_staged  # might not exist; fallback
            r = analyze_text_staged(extra_text) if "analyze_text_staged" in dir() else None
            if r is None:
                # use staged with empty image list
                r = analyze_screenshot_staged([], extra_text=extra_text)
        elapsed = time.time() - t0
        return {"ok": True, "elapsed": elapsed, "result": r}
    except Exception as e:
        return {"ok": False, "elapsed": time.time() - t0, "error": f"{type(e).__name__}: {e}", "tb": traceback.format_exc()[:500]}


def summarize(res: dict) -> dict:
    if not res.get("ok"):
        return {"err": res["error"][:200]}
    r = res["result"]
    h = r.get("header", {}) or {}
    cv = r.get("claim_verification") or []
    return {
        "bi": h.get("bullshit_index"),
        "nature": h.get("bullshit_nature"),
        "risk": h.get("risk_level"),
        "verdict_text": (h.get("verdict") or "")[:120],
        "claims": len(cv),
        "claims_fake": sum(1 for c in cv if "✗" in (c.get("verdict") or "")),
        "claims_ok": sum(1 for c in cv if "✓" in (c.get("verdict") or "")),
        "one_line": (r.get("one_line_summary") or "")[:120],
    }


def main():
    # 备份原 config
    orig_cfg = json.load(open("config.json", "r", encoding="utf-8"))
    orig_active = orig_cfg["active_provider"]
    orig_model = orig_cfg["providers"][orig_active]["model"]
    orig_verify = orig_cfg.get("verify_claim_model", "")
    print(f"原配置: active={orig_active} model={orig_model} verify={orig_verify}")
    print(f"\n[1/2] 跑 {len(MODELS)} setup × {len(CASES)} case = {len(MODELS)*len(CASES)} 次完整鉴定\n")

    results = {}
    try:
        for label, active_provider, main_model, verify_override in SETUPS:
            tag = f"{label} (provider={active_provider}, main={main_model}, verify={verify_override or main_model})"
            print(f"\n========== SETUP: {tag} ==========")
            set_model(active_provider, main_model, verify_override)
            model = label  # use label as key
            for case in CASES:
                key = f"{model}|{case['id']}"
                print(f"\n--- {case['label']} ({case['id']}) ---")
                meta, imgs = load_case(case["id"])
                res = run_one(case["id"], case["extra"], imgs)
                results[key] = res
                if res["ok"]:
                    s = summarize(res)
                    print(f"  {res['elapsed']:.1f}s | bi={s['bi']} nature={s['nature']} claims={s['claims']} (fake={s['claims_fake']} ok={s['claims_ok']})")
                    print(f"  verdict: {s['verdict_text']}")
                else:
                    print(f"  FAIL {res['elapsed']:.1f}s: {res['error'][:200]}")
    finally:
        # 还原 config
        set_model(orig_active, orig_model, orig_verify)
        print(f"\n已还原: active={orig_active} model={orig_model} verify={orig_verify}")

    # 写报告
    lines = ["# 双模型 replay 对比: gemini-3-flash-preview vs gemini-3.1-flash-lite\n"]
    lines.append(f"- 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- case 数: {len(CASES)}\n")
    lines.append("## 汇总\n")
    lines.append("| case | model | 耗时 | bi | nature | claims (fake/ok) | one_line |")
    lines.append("|---|---|---|---|---|---|---|")
    for case in CASES:
        for model in MODELS:
            res = results.get(f"{model}|{case['id']}", {})
            if res.get("ok"):
                s = summarize(res)
                lines.append(f"| {case['label']} | {model} | {res['elapsed']:.1f}s | {s['bi']} | {s['nature']} | {s['claims']} ({s['claims_fake']}/{s['claims_ok']}) | {s['one_line']} |")
            else:
                lines.append(f"| {case['label']} | {model} | {res.get('elapsed',0):.1f}s | ❌ | — | — | {res.get('error','')[:80]} |")

    lines.append("\n## 详细对比\n")
    for case in CASES:
        lines.append(f"### {case['label']} (`{case['id']}`)\n")
        for model in MODELS:
            res = results.get(f"{model}|{case['id']}", {})
            if not res.get("ok"):
                lines.append(f"**{model}** — ❌ {res.get('error','')[:200]}\n")
                continue
            s = summarize(res)
            r = res["result"]
            h = r.get("header", {}) or {}
            cv = r.get("claim_verification") or []
            lines.append(f"**{model}** ({res['elapsed']:.1f}s)")
            lines.append(f"- bi={s['bi']} nature={s['nature']} risk={s['risk']}")
            lines.append(f"- verdict: {h.get('verdict','')}")
            lines.append(f"- one_line: {s['one_line']}")
            lines.append(f"- claims ({len(cv)}):")
            for c in cv:
                claim_txt = (c.get("claim") or "")[:100]
                v = c.get("verdict") or ""
                lines.append(f"  - [{v}] {claim_txt}")
            lines.append("")

    out_path = "scripts/_compare_models_replay.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n[2/2] ✅ 报告写入 {out_path}")


if __name__ == "__main__":
    main()
