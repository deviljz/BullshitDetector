"""Replay 2026-04-22 05:29 鉴定（cache_id=56d19b683181e5f1），验证
SUBMIT_CLAIM_RESULT_TOOL 的 fact_layer description 加固后，
'推文发布日期'类 claim 不再被误判 ✓。
"""
import sys, os, json, base64
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ai.analyzer import analyze_screenshot_staged

CACHE = "historyCache/56d19b683181e5f1"
with open(f"{CACHE}/images/0.jpg", "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

print(f"Running staged analyze on cache_id=56d19b683181e5f1 ...")
result = analyze_screenshot_staged([img_b64], extra_text="")

print("\n=== HEADER ===")
for k, v in result.get("header", {}).items():
    print(f"  {k}: {v}")

print("\n=== CLAIM VERIFICATION ===")
for i, c in enumerate(result.get("claim_verification", [])):
    print(f"\n[{i}] {c.get('claim','')[:200]}")
    print(f"    verdict:      {c.get('verdict')}")
    print(f"    fact_layer:   {c.get('fact_layer')}")
    print(f"    note:         {str(c.get('note',''))[:300]}")

# Save full result for inspection
with open("tests/_replay_result.json", "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print("\nFull result saved to tests/_replay_result.json")

# 关键断言：包含日期/推文类声明时，不应再判 ✓ 存在
DATE_KEYWORDS = ["4月21", "4-21", "04-21", "04/21", "发布", "推特", "推文"]
wrong = []
for c in result.get("claim_verification", []):
    claim = c.get("claim", "")
    fl = c.get("fact_layer") or c.get("verdict", "")
    if any(k in claim for k in DATE_KEYWORDS) and "✓" in str(fl):
        wrong.append((claim, fl, c.get("note","")[:200]))

if wrong:
    print(f"\n⚠ 仍有 {len(wrong)} 条日期/推文类 claim 被判 ✓，prompt 加固未生效：")
    for claim, fl, note in wrong:
        print(f"  - claim: {claim[:120]}")
        print(f"    fl={fl}  note={note}")
    sys.exit(1)
else:
    print("\n✓ 日期/推文类 claim 均未被判 ✓，prompt 加固生效。")
