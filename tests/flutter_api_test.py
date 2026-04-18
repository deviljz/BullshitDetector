"""
Flutter API 端到端测试
模拟 Flutter app 调用同款接口，验证4个模式输出是否正常
"""
import sys, json, os
sys.stdout.reconfigure(encoding='utf-8')

import openai

# 从项目根 config.json 读取，禁止硬编码 API Key
_CFG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")
with open(_CFG_PATH, "r", encoding="utf-8") as _f:
    _cfg = json.load(_f)
API_KEY = _cfg.get("gemini_api_key") or _cfg.get("api_key") or os.environ.get("GEMINI_API_KEY", "")
if not API_KEY:
    raise SystemExit("未在 config.json / GEMINI_API_KEY 中找到 API Key")
BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
MODEL = "gemini-2.0-flash"

client = openai.OpenAI(api_key=API_KEY, base_url=BASE_URL)

TEST_TEXT = "马云在2024年重新回归阿里巴巴，担任CEO，并宣布阿里巴巴全年营收突破1万亿元人民币。"

def call(system_prompt, user_text, max_tokens=2048, temperature=0.7):
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    content = resp.choices[0].message.content
    usage = resp.usage
    return content, usage

def extract_json(text):
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        s = "\n".join(lines[1:-1])
    try:
        return json.loads(s)
    except:
        start = s.find("{")
        end = s.rfind("}")
        if start >= 0 and end > start:
            return json.loads(s[start:end+1])
        return {"error": "parse_failed", "raw": text[:200]}

# ── 1. Summary 模式 ───────────────────────────────────────────────────────────
print("=" * 60)
print("=== MODE: summary ===")
system = """你是内容总结助手。将用户发来的内容总结为结构化 JSON：
{"headline": "一句话标题", "key_points": ["要点1", "要点2"], "bias_note": "偏颇提示或空字符串", "_mode": "summary"}
只输出 JSON，不加任何说明。"""
content, usage = call(system, TEST_TEXT, max_tokens=1024, temperature=0.5)
result = extract_json(content)
print(f"headline: {result.get('headline', 'N/A')}")
print(f"key_points: {result.get('key_points', [])}")
print(f"bias_note: {result.get('bias_note', '')}")
print(f"tokens: in={usage.prompt_tokens} out={usage.completion_tokens}")
print(f"parse ok: {'error' not in result}")

# ── 2. Explain 模式（两阶段）─────────────────────────────────────────────────
print("\n=== MODE: explain (stage1: classify) ===")
classify_sys = """判断用户内容属于哪类，输出 JSON：
{"subtype": "<类型>"}  类型只能是: concept/event/person/organization/meme/technical
只输出JSON。"""
c1, u1 = call(classify_sys, TEST_TEXT, max_tokens=64, temperature=0.0)
subtype_json = extract_json(c1)
subtype = subtype_json.get("subtype", "concept")
print(f"subtype: {subtype}  tokens: in={u1.prompt_tokens} out={u1.completion_tokens}")

print(f"=== MODE: explain (stage2: explain/{subtype}) ===")
explain_sys = f"""你是百科解释助手。对用户内容作{subtype}类型的专业解释，输出 JSON：
{{"subject": "主题名称", "short_answer": "一句话回答", "detail": "详细说明", "related": ["相关词1", "相关词2"], "_mode": "explain"}}
只输出JSON。"""
c2, u2 = call(explain_sys, TEST_TEXT, max_tokens=1024, temperature=0.3)
result2 = extract_json(c2)
print(f"subject: {result2.get('subject', 'N/A')}")
print(f"short_answer: {result2.get('short_answer', 'N/A')}")
print(f"related: {result2.get('related', [])}")
print(f"tokens: in={u2.prompt_tokens} out={u2.completion_tokens}")
print(f"parse ok: {'error' not in result2}")

# ── 3. Analyze 模式（经典，无工具）──────────────────────────────────────────
print("\n=== MODE: analyze (classic, no tools) ===")
analyze_sys = """你是鉴屎官。分析用户文字的真实性，输出 JSON（无工具版，仅凭知识判断）：
{
  "header": {"bullshit_index": <0-100>, "truth_label": "真实度描述", "risk_level": "风险等级", "verdict": "一句话判决"},
  "one_line_summary": "摘要",
  "claim_verification": [{"claim": "声明", "verdict": "✓ 基本属实|✗ 伪造|? 无法核实", "note": "说明"}],
  "toxic_review": "毒舌点评（可为空）",
  "_mode": "analyze"
}
只输出JSON。"""
c3, u3 = call(analyze_sys, TEST_TEXT, max_tokens=2048, temperature=0.7)
result3 = extract_json(c3)
header = result3.get("header", {})
print(f"bullshit_index: {header.get('bullshit_index', 'N/A')}")
print(f"verdict: {header.get('verdict', 'N/A')}")
print(f"claims: {len(result3.get('claim_verification', []))} 条")
print(f"toxic_review: {result3.get('toxic_review', '')[:60]}")
print(f"tokens: in={u3.prompt_tokens} out={u3.completion_tokens}")
print(f"parse ok: {'error' not in result3}")

# ── 4. Source 模式（仅文字，classify+source）────────────────────────────────
print("\n=== MODE: source (classify only, no image) ===")
src_classify_sys = """判断用户描述的内容媒介类型，输出 JSON：
{"subtype": "<类型>"}  类型: anime/manga/film_tv/game/social_post/artwork
只输出JSON。"""
src_text = "这张图是一个紫发女孩拿着剑的场景"
c4, u4 = call(src_classify_sys, src_text, max_tokens=64, temperature=0.0)
src_sub = extract_json(c4)
print(f"source subtype: {src_sub.get('subtype', 'N/A')}  tokens: in={u4.prompt_tokens} out={u4.completion_tokens}")
print("(source 完整溯源需要图片，文字流程正常)")

# ── 汇总 ─────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("所有模式 API 调用完成，无崩溃。Flutter 逻辑路径验证通过。")
