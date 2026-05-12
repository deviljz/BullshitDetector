"""Replay 2026-05-09 17:20 全球通史 case (cache_id=c94b6e58e73edd10)
验证 P0+P1+P2 后：
- claim 2/3 是否仍判 ? 无法核实
- phase 2 重核是否触发并改善 verdict
- fetch_url 是否被调用
"""
import sys, os, json, base64, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

from ai.analyzer import analyze_screenshot_staged

CACHE = "historyCache/c94b6e58e73edd10"
with open(f"{CACHE}/images/0.jpg", "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

print(f"Running plan_execute on cache_id=c94b6e58e73edd10 (全球通史)…\n")
result = analyze_screenshot_staged([img_b64], extra_text="")

print("=" * 70)
print("=== HEADER ===")
for k, v in result.get("header", {}).items():
    print(f"  {k}: {v}")

print("\n=== CLAIM VERIFICATION ===")
for i, c in enumerate(result.get("claim_verification", [])):
    print(f"\n[{i}] {c.get('claim','')[:150]}")
    print(f"    verdict:     {c.get('verdict')}")
    print(f"    fact_layer:  {c.get('fact_layer')}")
    print(f"    sources:     {len(c.get('sources',[]))} 个")
    note = str(c.get('note','')).replace('\n',' ')[:300]
    print(f"    note:        {note}")

print("\n=== _path:", result.get("_path"))
print("=== _token_usage:", result.get("_token_usage"))

# 检查 phase 2 是否触发
search_log = result.get("_search_log", [])
phase2_keywords = ["evidence pool", "证据池", "phase 2"]
print(f"\n=== search_log 共 {len(search_log)} 条查询")

# Save full result
out_path = "scripts/_replay_global_history.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f"\n完整结果已保存: {out_path}")
