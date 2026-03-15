# -*- coding: utf-8 -*-
"""
文字链路 HTML 测试报告生成器
用法：python tests/run_text_html_report.py
报告保存至：tests/reports/text_report_<timestamp>.html
"""

import io
import math
import pathlib
import sys
import time
from datetime import datetime

# Windows GBK 终端强制 UTF-8 输出
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_ROOT = pathlib.Path(__file__).parent.parent
_SRC = _ROOT / "src"
sys.path.insert(0, str(_SRC))
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from ai.analyzer import analyze_text       # noqa: E402
from run_text_eval import TEXT_CASES       # noqa: E402

REPORTS_DIR = pathlib.Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def build_gauge_svg(value):
    if value is None:
        return ('<svg width="120" height="70" viewBox="0 0 120 70">'
                '<path d="M10,60 A50,50 0 0 1 110,60" fill="none" stroke="#333" stroke-width="10" stroke-linecap="round"/>'
                '<text x="60" y="55" text-anchor="middle" font-size="18" fill="#888">—</text>'
                '</svg>')
    v = max(0, min(100, value))
    color = "#4caf50" if v <= 30 else "#ffb300" if v <= 55 else "#ff7043" if v <= 75 else "#e53935"
    theta = math.pi * (1.0 - v / 100.0)
    ex = 60 + 50 * math.cos(theta)
    ey = 60 - 50 * math.sin(theta)
    large_arc = 1 if v > 50 else 0
    return (f'<svg width="120" height="70" viewBox="0 0 120 70">'
            f'<path d="M10,60 A50,50 0 0 1 110,60" fill="none" stroke="#2a2a3a" stroke-width="10" stroke-linecap="round"/>'
            f'<path d="M10,60 A50,50 0 {large_arc} 1 {ex:.2f},{ey:.2f}" fill="none" stroke="{color}" stroke-width="10" stroke-linecap="round"/>'
            f'<text x="60" y="56" text-anchor="middle" font-size="22" font-weight="bold" fill="{color}">{v}</text>'
            f'<text x="60" y="68" text-anchor="middle" font-size="9" fill="#888">BS指数</text>'
            f'</svg>')


def evaluate(result, case):
    if result.get("error"):
        return "fail"
    bs = result.get("header", {}).get("bullshit_index")
    if bs is None:
        return "fail"
    predicted_hype = bs >= 56
    exp_hype = case["expected_hype"]
    exp_bs_min = case["expected_bs_min"]
    if predicted_hype != exp_hype:
        return "fail"
    if exp_hype and bs < exp_bs_min:
        return "warn"   # 方向对但分数偏低
    return "pass"


def html_escape(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


# ── HTML 模板 ─────────────────────────────────────────────────────────────────

HTML_HEAD = """\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BullshitDetector · 文字链路评估报告</title>
<style>
:root {
  --bg: #0f0f1a; --card: #1a1a2e; --border: #2a2a45;
  --text: #cdd6f4; --muted: #6c7086;
  --pass: #a6e3a1; --fail: #f38ba8; --warn: #f9e2af; --noexp: #89b4fa;
  --purple: #cba6f7; --blue: #89dceb;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text);
  font-family: "Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; padding: 24px; }
h1 { font-size: 1.6rem; margin-bottom: 4px; }
.meta { color: var(--muted); font-size: 0.85rem; margin-bottom: 18px; }
.stats-bar { display: flex; gap: 14px; margin-bottom: 20px; flex-wrap: wrap; }
.stat { background: var(--card); border: 1px solid var(--border);
  border-radius: 10px; padding: 12px 20px; min-width: 80px; }
.stat-num { font-size: 1.6rem; font-weight: 700; }
.stat-label { font-size: 0.72rem; color: var(--muted); margin-top: 2px; }
.filters { display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }
.filter-btn { padding: 6px 16px; border-radius: 20px; border: 1px solid var(--border);
  background: var(--card); color: var(--text); cursor: pointer;
  font-size: 0.85rem; transition: all .2s; }
.filter-btn.active, .filter-btn:hover { background: #313244; border-color: #585b70; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); gap: 20px; }
.card { background: var(--card); border: 1px solid var(--border);
  border-radius: 14px; overflow: hidden;
  display: flex; flex-direction: column; transition: box-shadow .2s; }
.card:hover { box-shadow: 0 6px 24px rgba(0,0,0,.55); }
.card.pass  { border-left: 4px solid var(--pass); }
.card.fail  { border-left: 4px solid var(--fail); }
.card.warn  { border-left: 4px solid var(--warn); }
.card.noexp { border-left: 4px solid var(--noexp); }
/* article text preview */
.article-preview { background: #0c0c18; padding: 12px 14px; font-size: 0.78rem;
  color: #a6adc8; line-height: 1.55; max-height: 80px; overflow: hidden;
  transition: max-height .35s ease; cursor: pointer; border-bottom: 1px solid var(--border); }
.article-preview.expanded { max-height: 600px; }
.article-label { font-size: 0.65rem; color: var(--muted); padding: 4px 14px 0;
  background: #0c0c18; border-bottom: 1px solid var(--border); letter-spacing: .06em; }
.card-body { padding: 14px; flex: 1; display: flex; flex-direction: column; gap: 10px; }
.card-top { display: flex; align-items: flex-start; gap: 12px; }
.gauge-wrap { flex-shrink: 0; }
.card-info { flex: 1; min-width: 0; }
.cid { font-size: 0.7rem; color: var(--muted); word-break: break-all; }
.label { font-size: 0.92rem; font-weight: 600; margin: 4px 0; line-height: 1.35; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 10px;
  font-size: 0.75rem; font-weight: 700; }
.badge.pass  { background: #1e3a1e; color: var(--pass); }
.badge.fail  { background: #3a1e1e; color: var(--fail); }
.badge.warn  { background: #3a2e00; color: var(--warn); }
.badge.noexp { background: #1e2a3a; color: var(--noexp); }
.section { background: #131320; border-radius: 8px; padding: 10px 13px;
  font-size: 0.82rem; }
.section-title { color: var(--muted); font-size: 0.7rem; text-transform: uppercase;
  letter-spacing: .06em; margin-bottom: 6px; }
.review-text { line-height: 1.55; }
.expect-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.expect-item { background: #0d0d1a; border-radius: 6px; padding: 6px 10px; }
.expect-key { font-size: 0.68rem; color: var(--muted); margin-bottom: 2px; }
.expect-val { font-size: 0.82rem; }
.expect-val.hype { color: var(--fail); }
.expect-val.real { color: var(--pass); }
.reason-text { color: #a6adc8; font-size: 0.78rem; line-height: 1.45; margin-top: 6px; }
.radar { display: flex; gap: 6px; flex-wrap: wrap; }
.radar-item { background: #0d0d1a; border-radius: 6px; padding: 5px 10px;
  flex: 1; min-width: 80px; }
.radar-key { font-size: 0.66rem; color: var(--muted); }
.radar-bar { height: 4px; background: #2a2a3a; border-radius: 2px; margin-top: 4px; }
.radar-fill { height: 100%; border-radius: 2px; background: var(--purple); }
.hype-grid { display: flex; flex-direction: column; gap: 5px; font-size: 0.8rem; }
.hype-row { display: flex; gap: 8px; }
.hype-key { color: var(--blue); white-space: nowrap; min-width: 52px;
  font-size: 0.7rem; padding-top: 2px; }
.hype-val { color: #a6adc8; line-height: 1.45; }
.flaw-list { padding-left: 16px; font-size: 0.79rem; line-height: 1.6; color: #a6adc8; }
.error-box { background: #2a0a0a; border-radius: 8px; padding: 10px 12px; }
.error-text { color: var(--fail); font-size: 0.77rem; font-family: monospace;
  white-space: pre-wrap; word-break: break-all; }
.toggle-btn { font-size: 0.72rem; color: var(--muted); cursor: pointer;
  background: none; border: none; padding: 2px 6px; border-radius: 4px; }
.toggle-btn:hover { background: #2a2a3a; color: var(--text); }
.collapsed { display: none; }
</style>
</head>
<body>
<h1>💩 BullshitDetector · 文字链路评估报告</h1>
"""

HTML_FOOT = """\
<script>
function filterCards(type) {
  document.querySelectorAll('.card').forEach(c => {
    c.style.display = (type==='all' || c.dataset.status===type) ? '' : 'none';
  });
  document.querySelectorAll('.filter-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.filter===type);
  });
}
function toggleArticle(el) {
  el.classList.toggle('expanded');
}
function toggleSection(btn) {
  const sec = btn.nextElementSibling;
  sec.classList.toggle('collapsed');
  btn.textContent = sec.classList.contains('collapsed') ? '▶ 展开' : '▼ 收起';
}
document.querySelector('[data-filter="all"]').click();
</script>
</body></html>
"""


def build_card(case, result, elapsed, status):
    cid = html_escape(case["id"])
    label = html_escape(case["label"])
    article_text = html_escape(case["text"])
    reason = html_escape(case.get("reason", ""))

    header = result.get("header", {})
    bs = header.get("bullshit_index")
    risk = html_escape(header.get("risk_level", ""))
    truth_label = html_escape(header.get("truth_label", ""))
    verdict = html_escape(header.get("verdict", ""))
    toxic = html_escape(result.get("toxic_review", ""))
    one_line = html_escape(result.get("one_line_summary", ""))
    radar = result.get("radar_chart", {})
    inv = result.get("investigation_report", {})
    flaw_list = result.get("flaw_list", [])
    error = result.get("error", "")

    badge_map = {"pass": "✅ 通过", "fail": "❌ 失败", "warn": "⚠️ 方向对/分偏低", "noexp": "⚪ 无预期"}
    badge_text = badge_map.get(status, status)

    exp_hype = case["expected_hype"]
    exp_bs_min = case["expected_bs_min"]
    actual_bs_str = str(bs) if bs is not None else "N/A"
    actual_hype_str = ("❌ 夸大" if (bs or 0) >= 56 else "✅ 属实") if bs is not None else "N/A"
    exp_hype_str = "❌ 夸大/假" if exp_hype else "✅ 基本属实"
    exp_hype_cls = "hype" if exp_hype else "real"

    gauge = build_gauge_svg(bs)

    # 文章文本区
    article_html = (
        f'<div class="article-label">📄 原文（点击展开/收起）</div>'
        f'<div class="article-preview" onclick="toggleArticle(this)">{article_text}</div>'
    )

    # 雷达
    radar_items = [
        ("逻辑自洽", radar.get("logic_consistency", 0)),
        ("来源权威", radar.get("source_authority", 0)),
        ("煽动烈度", radar.get("agitation_level", 0)),
        ("搜索核实", radar.get("search_match", 0)),
    ]
    radar_html = '<div class="radar">' + "".join(
        f'<div class="radar-item"><div class="radar-key">{k}</div>'
        f'<div class="radar-bar"><div class="radar-fill" style="width:{min((v or 0)*20,100)}%"></div></div>'
        f'<div style="font-size:0.68rem;margin-top:2px;color:var(--muted)">{v}/5</div></div>'
        for k, v in radar_items
    ) + "</div>"

    # 夸大/遗漏/意图三维
    hype_check = html_escape(inv.get("hype_check", ""))
    missing_info = html_escape(inv.get("missing_info", ""))
    intent_check = html_escape(inv.get("intent_check", ""))
    hype_html = ""
    if hype_check or missing_info or intent_check:
        rows = ""
        if hype_check:
            rows += f'<div class="hype-row"><div class="hype-key">夸大</div><div class="hype-val">{hype_check}</div></div>'
        if missing_info:
            rows += f'<div class="hype-row"><div class="hype-key">遗漏</div><div class="hype-val">{missing_info}</div></div>'
        if intent_check:
            rows += f'<div class="hype-row"><div class="hype-key">意图</div><div class="hype-val">{intent_check}</div></div>'
        hype_html = f'<div class="section"><div class="section-title">专项分析</div><div class="hype-grid">{rows}</div></div>'

    # 调查报告（可折叠）
    inv_exclude = {"hype_check", "missing_info", "intent_check"}
    inv_rows = "".join(
        f'<div style="margin-bottom:5px"><span style="color:var(--muted);font-size:0.72rem">{html_escape(k)}：</span>'
        f'<span style="font-size:0.8rem">{html_escape(str(v))}</span></div>'
        for k, v in inv.items() if v and k not in inv_exclude
    )
    inv_html = ""
    if inv_rows:
        inv_html = (
            f'<div><button class="toggle-btn" onclick="toggleSection(this)">▼ 收起</button>'
            f'<div class="section"><div class="section-title">调查报告</div>'
            f'<div style="line-height:1.6">{inv_rows}</div></div></div>'
        )

    # 破绽列表（可折叠）
    flaw_html = ""
    if flaw_list:
        items = "".join(f'<li>{html_escape(f)}</li>' for f in flaw_list)
        flaw_html = (
            f'<div><button class="toggle-btn" onclick="toggleSection(this)">▼ 收起</button>'
            f'<div class="section"><div class="section-title">破绽列表（{len(flaw_list)}条）</div>'
            f'<ul class="flaw-list">{items}</ul></div></div>'
        )

    error_html = ""
    if error:
        error_html = (
            f'<div class="error-box"><div class="section-title" style="color:var(--fail)">错误</div>'
            f'<div class="error-text">{html_escape(error[:300])}</div></div>'
        )

    return f"""\
<div class="card {status}" data-status="{status}">
  {article_html}
  <div class="card-body">
    <div class="card-top">
      <div class="gauge-wrap">{gauge}</div>
      <div class="card-info">
        <div class="cid">{cid}</div>
        <div class="label">{label}</div>
        <div style="margin-top:5px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <span class="badge {status}">{badge_text}</span>
          <span style="font-size:0.78rem;color:var(--purple)">{risk}</span>
        </div>
        <div style="margin-top:4px;font-size:0.76rem;color:var(--muted)">{truth_label}</div>
      </div>
    </div>
    <div class="section">
      <div class="section-title">核心判决</div>
      <div class="review-text" style="color:var(--warn)">{verdict}</div>
    </div>
    <div class="section">
      <div class="section-title">锐评</div>
      <div class="review-text">{toxic}</div>
    </div>
    <div class="section">
      <div class="section-title">一句话总结</div>
      <div class="review-text" style="color:var(--pass)">{one_line}</div>
    </div>
    {radar_html}
    {hype_html}
    <div class="section">
      <div class="section-title">预期 vs 实际</div>
      <div class="expect-grid">
        <div class="expect-item">
          <div class="expect-key">预期判断</div>
          <div class="expect-val {exp_hype_cls}">{exp_hype_str}</div>
        </div>
        <div class="expect-item">
          <div class="expect-key">实际判断</div>
          <div class="expect-val">{actual_hype_str}（BS={actual_bs_str}）</div>
        </div>
        <div class="expect-item">
          <div class="expect-key">BS 下限要求</div>
          <div class="expect-val">≥ {exp_bs_min}</div>
        </div>
        <div class="expect-item">
          <div class="expect-key">耗时</div>
          <div class="expect-val">{elapsed:.1f}s</div>
        </div>
      </div>
      <div class="reason-text">{reason}</div>
    </div>
    {inv_html}
    {flaw_html}
    {error_html}
  </div>
</div>"""


def generate(cases):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"text_report_{timestamp}.html"
    total = len(cases)

    records = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{total}] {case['id']} ...", end=" ", flush=True)
        t0 = time.time()
        try:
            result = analyze_text(case["text"])
            elapsed = time.time() - t0
            status = evaluate(result, case)
        except Exception as e:
            result = {
                "header": {"bullshit_index": None, "risk_level": "💥", "truth_label": "", "verdict": str(e)},
                "toxic_review": "", "flaw_list": [], "radar_chart": {},
                "investigation_report": {}, "error": str(e), "one_line_summary": "",
            }
            elapsed = time.time() - t0
            status = "fail"
        bs = result.get("header", {}).get("bullshit_index", "N/A")
        print(f"BS={bs} [{status}] ({elapsed:.1f}s)")
        records.append((case, result, elapsed, status))

    n_pass = sum(1 for *_, s in records if s == "pass")
    n_fail = sum(1 for *_, s in records if s == "fail")
    n_warn = sum(1 for *_, s in records if s == "warn")
    n_total = len(records)
    pass_rate = f"{n_pass}/{n_pass+n_fail+n_warn}"

    # fail 优先排序
    order = {"fail": 0, "warn": 1, "pass": 2, "noexp": 3}
    records.sort(key=lambda r: order.get(r[-1], 9))

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pass_color = "var(--pass)" if n_fail == 0 else "var(--fail)"

    stats_html = f"""\
<div class="meta">生成时间：{now_str} | 共 {n_total} 条文本案例</div>
<div class="stats-bar">
  <div class="stat"><div class="stat-num">{n_total}</div><div class="stat-label">总计</div></div>
  <div class="stat"><div class="stat-num" style="color:var(--pass)">{n_pass}</div><div class="stat-label">✅ 通过</div></div>
  <div class="stat"><div class="stat-num" style="color:var(--fail)">{n_fail}</div><div class="stat-label">❌ 失败</div></div>
  <div class="stat"><div class="stat-num" style="color:var(--warn)">{n_warn}</div><div class="stat-label">⚠️ 方向对/分偏低</div></div>
  <div class="stat"><div class="stat-num" style="color:{pass_color}">{pass_rate}</div><div class="stat-label">通过率</div></div>
</div>
<div class="filters">
  <button class="filter-btn" data-filter="all" onclick="filterCards('all')">全部 ({n_total})</button>
  <button class="filter-btn" data-filter="fail" onclick="filterCards('fail')">❌ 失败 ({n_fail})</button>
  <button class="filter-btn" data-filter="warn" onclick="filterCards('warn')">⚠️ 分偏低 ({n_warn})</button>
  <button class="filter-btn" data-filter="pass" onclick="filterCards('pass')">✅ 通过 ({n_pass})</button>
</div>
<div class="grid">"""

    cards_html = "\n".join(build_card(c, r, e, s) for c, r, e, s in records)
    html = HTML_HEAD + stats_html + cards_html + "\n</div>\n" + HTML_FOOT
    report_path.write_text(html, encoding="utf-8")
    print(f"\n报告已保存：{report_path}")
    print(f"结果：{n_pass} 通过 / {n_fail} 失败 / {n_warn} 分偏低（共 {n_total} 条）")
    return report_path


if __name__ == "__main__":
    path = generate(TEXT_CASES)
    import webbrowser
    webbrowser.open(path.as_uri())
