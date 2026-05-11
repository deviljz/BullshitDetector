"""非 GUI 逻辑测试：history、extra_text、core_idea、wechat fetcher"""
import sys, os, tempfile, pathlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
errors = []

def check(name, cond, detail=""):
    if cond:
        print(f"  {PASS} {name}")
    else:
        print(f"  {FAIL} {name}" + (f": {detail}" if detail else ""))
        errors.append(name)

# ── 1. history.py CRUD ────────────────────────────────────────────────────────
print("\n[1] history CRUD")
import history as hs

_orig = hs._HISTORY_FILE
hs._HISTORY_FILE = pathlib.Path(tempfile.mktemp(suffix=".json"))
try:
    check("初始为空", hs.load_all() == [])

    r_analyze = {"_mode": "analyze", "one_line_summary": "一坨假新闻"}
    r_summary = {"_mode": "summary", "headline": "AWE展览新趋势"}
    r_explain  = {"_mode": "explain", "subject": "I'm not a cat"}
    r_source   = {"_mode": "source",  "title": "进击的巨人", "original_title": "Shingeki no Kyojin"}

    id1 = hs.add(r_analyze)
    id2 = hs.add(r_summary)
    id3 = hs.add(r_explain)
    id4 = hs.add(r_source)

    entries = hs.load_all()
    check("保存4条", len(entries) == 4)
    check("最新在前(source)", entries[0]["mode"] == "source")
    check("analyze 标题", entries[3]["title"] == "一坨假新闻")
    check("summary 标题", entries[2]["title"] == "AWE展览新趋势")
    check("explain 标题", entries[1]["title"] == "I'm not a cat")
    check("source 标题含原名", entries[0]["title"] == "进击的巨人（Shingeki no Kyojin）")
    check("type_label 鉴屎官", entries[3]["type_label"] == "🔍 鉴屎官")
    check("type_label 总结",   entries[2]["type_label"] == "📝 总结")

    hs.update_chat(id1, [{"user": "真的假的", "ai": "当然假的"}])
    entries = hs.load_all()
    target = next(e for e in entries if e["id"] == id1)
    check("update_chat条目数", len(target["chat"]) == 1)
    check("update_chat内容",   target["chat"][0]["user"] == "真的假的")

    id5 = hs.add(r_analyze, thumbnail="fakeb64data")
    check("thumbnail存入", hs.load_all()[0]["thumbnail"] == "fakeb64data")

    hs.delete(id2)
    entries = hs.load_all()
    check("删除后剩4条", len(entries) == 4)
    check("被删条目不存在", all(e["id"] != id2 for e in entries))

    for i in range(200):
        hs.add({"_mode": "summary", "headline": f"test{i}"})
    check("上限200条", len(hs.load_all()) == 200)
finally:
    hs._HISTORY_FILE.unlink(missing_ok=True)
    hs._HISTORY_FILE = _orig

# ── 2. _derive_title 边界 ─────────────────────────────────────────────────────
print("\n[2] _derive_title 边界")
from history import _derive_title
check("analyze 无summary用truth_label",
      _derive_title({"_mode": "analyze", "header": {"truth_label": "高度可疑"}}) == "高度可疑")
check("analyze 完全空不崩溃",
      isinstance(_derive_title({"_mode": "analyze"}), str))
check("source 无original_title",
      _derive_title({"_mode": "source", "title": "进击的巨人"}) == "进击的巨人")
check("标题超60字截断",
      len(_derive_title({"_mode": "summary", "headline": "x" * 100})) <= 60)

# ── 3. _image_content extra_text ─────────────────────────────────────────────
print("\n[3] _image_content extra_text")
from ai.providers.openai_compat import OpenAICompatibleProvider as P

c1 = P._image_content(["b64"], "请分析：")
check("无extra_text 2块", len(c1) == 2)

c2 = P._image_content(["b64"], "请分析：", "这是补充说明")
check("有extra_text 3块", len(c2) == 3)
check("extra_text 内容正确", "补充说明" in c2[2]["text"])

c3 = P._image_content(["b64"], "x", "A" * 5000)
check("extra_text 截断4000字", len(c3[2]["text"]) < 4200)

c4 = P._image_content(["b1", "b2"], "多图：", "extra")
check("多图+extra 共4块", len(c4) == 4)

# ── 4. summary prompt 含 core_idea ───────────────────────────────────────────
print("\n[4] summary prompt")
from ai.prompts import get_summary_prompt
prompt = get_summary_prompt()
check("含 core_idea 字段",  "core_idea" in prompt)
check("含中心思想描述", "中心思想" in prompt or "核心观点" in prompt)
check("含 headline 字段", "headline" in prompt)

# ── 5. text_fetcher 微信路径 ──────────────────────────────────────────────────
print("\n[5] text_fetcher")
import text_fetcher, unittest.mock as mock

with mock.patch("text_fetcher._extract_wechat") as mw, \
     mock.patch("requests.get") as mg:
    mg.return_value.text = "<html><head><title>T</title></head><body>content here</body></html>"
    mg.return_value.raise_for_status = lambda: None
    mg.return_value.apparent_encoding = "utf-8"
    text_fetcher.fetch_article("https://example.com/article")
    check("非微信URL不调_extract_wechat", not mw.called)

with mock.patch("text_fetcher._extract_wechat", return_value="文章正文") as mw2, \
     mock.patch("requests.get") as mg2:
    mg2.return_value.text = "<html><body></body></html>"
    mg2.return_value.raise_for_status = lambda: None
    mg2.return_value.apparent_encoding = "utf-8"
    result = text_fetcher.fetch_article("https://mp.weixin.qq.com/s/abc")
    check("微信URL调_extract_wechat", mw2.called)
    check("微信URL返回提取内容", result == "文章正文")

# ── 结果 ──────────────────────────────────────────────────────────────────────
print()
if errors:
    print(f"\033[31m失败 {len(errors)} 项: {errors}\033[0m")
    sys.exit(1)
else:
    print("\033[32m全部通过！\033[0m")
