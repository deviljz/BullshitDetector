"""
HTML 视觉测试报告生成器
========================
用法：
  python tests/run_html_report.py                          # 测试所有 EXPECTATIONS fixtures
  python tests/run_html_report.py path/to/img1.jpg img2.png  # 测试指定图片（无预期判断）

报告保存至：tests/reports/report_<timestamp>.html
"""

import base64
import io
import math
import pathlib
import sys
import time
from datetime import datetime
from typing import Optional

# Windows GBK 终端强制 UTF-8 输出
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ── 路径修正 ──────────────────────────────────────────────────────────────────
_ROOT = pathlib.Path(__file__).parent.parent
_SRC = _ROOT / "src"
sys.path.insert(0, str(_SRC))

from ai.analyzer import analyze_image  # noqa: E402

# ── 导入 EXPECTATIONS ─────────────────────────────────────────────────────────
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from run_vision_eval import EXPECTATIONS, FIXTURES_DIR  # noqa: E402

REPORTS_DIR = pathlib.Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def img_to_base64(path: pathlib.Path) -> str:
    """将图片编码为 base64 data URL"""
    suffix = path.suffix.lower()
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".gif": "image/gif",
            ".bmp": "image/bmp", ".webp": "image/webp"}.get(suffix, "image/png")
    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{data}"


def build_gauge_svg(value: Optional[int]) -> str:
    """生成半圆形 BS 分数仪表盘 SVG（宽120 高70）"""
    if value is None:
        return '''<svg width="120" height="70" viewBox="0 0 120 70">
  <path d="M10,60 A50,50 0 0 1 110,60" fill="none" stroke="#333" stroke-width="10" stroke-linecap="round"/>
  <text x="60" y="55" text-anchor="middle" font-size="18" fill="#888">—</text>
</svg>'''

    v = max(0, min(100, value))
    # 颜色：绿→黄→橙→红
    if v <= 30:
        color = "#4caf50"
    elif v <= 55:
        color = "#ffb300"
    elif v <= 75:
        color = "#ff7043"
    else:
        color = "#e53935"

    # 弧线：从左端(10,60)到右端(110,60)，扫过 v/100 的比例
    # θ = π * (1 - v/100)，终点 = (60 + 50cosθ, 60 - 50sinθ)
    theta = math.pi * (1.0 - v / 100.0)
    ex = 60 + 50 * math.cos(theta)
    ey = 60 - 50 * math.sin(theta)
    large_arc = 1 if v > 50 else 0

    return f'''<svg width="120" height="70" viewBox="0 0 120 70">
  <path d="M10,60 A50,50 0 0 1 110,60" fill="none" stroke="#2a2a3a" stroke-width="10" stroke-linecap="round"/>
  <path d="M10,60 A50,50 0 {large_arc} 1 {ex:.2f},{ey:.2f}" fill="none" stroke="{color}" stroke-width="10" stroke-linecap="round"/>
  <text x="60" y="56" text-anchor="middle" font-size="22" font-weight="bold" fill="{color}">{v}</text>
  <text x="60" y="68" text-anchor="middle" font-size="9" fill="#888">BS指数</text>
</svg>'''


def evaluate_result(result: dict, exp: Optional[dict]) -> str:
    """根据分析结果和预期，返回 'pass' / 'fail' / 'noexp'"""
    if exp is None:
        return "noexp"
    bs = result.get("header", {}).get("bullshit_index")
    if bs is None:
        return "fail"
    predicted_fake = bs >= 56
    exp_fake = exp.get("expected_fake")
    exp_bs_min = exp.get("expected_bs_min", 0)
    if predicted_fake != exp_fake:
        return "fail"
    if exp_fake and bs < exp_bs_min:
        return "fail"
    if not exp_fake and bs >= 56:
        return "fail"
    return "pass"


def run_analysis(image_path: pathlib.Path) -> tuple[dict, float]:
    """运行分析，返回 (result, elapsed_seconds)"""
    t0 = time.time()
    result = analyze_image(str(image_path))
    elapsed = time.time() - t0
    return result, elapsed


# ── HTML 生成 ─────────────────────────────────────────────────────────────────

HTML_HEADER = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BullshitDetector 测试报告</title>
<style>
:root {
  --bg: #0f0f1a;
  --card: #1a1a2e;
  --border: #2a2a45;
  --text: #cdd6f4;
  --muted: #6c7086;
  --pass: #a6e3a1;
  --fail: #f38ba8;
  --noexp: #89b4fa;
  --warn: #f9e2af;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: "Segoe UI", "PingFang SC", sans-serif; padding: 20px; }
h1 { font-size: 1.6rem; margin-bottom: 4px; }
.meta { color: var(--muted); font-size: 0.85rem; margin-bottom: 16px; }
.stats-bar { display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }
.stat { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 10px 18px; }
.stat-num { font-size: 1.5rem; font-weight: bold; }
.stat-label { font-size: 0.75rem; color: var(--muted); }
.filters { display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }
.filter-btn { padding: 6px 14px; border-radius: 20px; border: 1px solid var(--border);
  background: var(--card); color: var(--text); cursor: pointer; font-size: 0.85rem; transition: all .2s; }
.filter-btn.active, .filter-btn:hover { background: #313244; border-color: #585b70; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(380px, 1fr)); gap: 20px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; overflow: hidden;
  display: flex; flex-direction: column; transition: box-shadow .2s; }
.card:hover { box-shadow: 0 4px 20px rgba(0,0,0,.5); }
.card.pass { border-left: 4px solid var(--pass); }
.card.fail { border-left: 4px solid var(--fail); }
.card.noexp { border-left: 4px solid var(--noexp); }
.card-img { width: 100%; max-height: 240px; object-fit: contain; background: #0a0a14;
  cursor: pointer; transition: max-height .3s; }
.card-img.expanded { max-height: none; }
.card-body { padding: 14px; flex: 1; display: flex; flex-direction: column; gap: 10px; }
.card-top { display: flex; align-items: flex-start; gap: 12px; }
.gauge-wrap { flex-shrink: 0; }
.card-info { flex: 1; min-width: 0; }
.filename { font-size: 0.75rem; color: var(--muted); word-break: break-all; }
.label { font-size: 0.92rem; font-weight: 600; margin: 4px 0; line-height: 1.35; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 10px; font-size: 0.75rem; font-weight: bold; }
.badge.pass { background: #1e3a1e; color: var(--pass); }
.badge.fail { background: #3a1e1e; color: var(--fail); }
.badge.noexp { background: #1e2a3a; color: var(--noexp); }
.verdict-row { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.verdict { font-size: 0.85rem; color: var(--warn); flex: 1; }
.time-label { font-size: 0.72rem; color: var(--muted); white-space: nowrap; }
.section { background: #131320; border-radius: 8px; padding: 10px 12px; font-size: 0.82rem; }
.section-title { color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: .05em; margin-bottom: 6px; }
.review-text { line-height: 1.5; color: var(--text); }
.expect-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.expect-item { background: #0d0d1a; border-radius: 6px; padding: 6px 10px; }
.expect-key { font-size: 0.7rem; color: var(--muted); margin-bottom: 2px; }
.expect-val { font-size: 0.82rem; }
.expect-val.fake { color: var(--fail); }
.expect-val.real { color: var(--pass); }
.expect-val.noexp { color: var(--noexp); }
.reason-text { color: #a6adc8; line-height: 1.45; }
.radar { display: flex; gap: 6px; flex-wrap: wrap; }
.radar-item { background: #0d0d1a; border-radius: 6px; padding: 5px 10px; flex: 1; min-width: 80px; }
.radar-key { font-size: 0.68rem; color: var(--muted); }
.radar-bar { height: 4px; background: #2a2a3a; border-radius: 2px; margin-top: 4px; }
.radar-fill { height: 100%; border-radius: 2px; background: #cba6f7; }
.error-box { background: #2a0a0a; border-radius: 8px; padding: 10px 12px; }
.error-text { color: var(--fail); font-size: 0.78rem; font-family: monospace; white-space: pre-wrap; word-break: break-all; }
.collapsed { display: none; }
.toggle-btn { font-size: 0.75rem; color: var(--muted); cursor: pointer; background: none; border: none;
  padding: 2px 6px; border-radius: 4px; }
.toggle-btn:hover { background: #2a2a3a; color: var(--text); }
</style>
</head>
<body>
<h1>💩 BullshitDetector 测试报告</h1>
"""

HTML_FOOTER = """
<script>
function filterCards(type) {
  document.querySelectorAll('.card').forEach(c => {
    c.style.display = (type === 'all' || c.dataset.status === type) ? '' : 'none';
  });
  document.querySelectorAll('.filter-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.filter === type);
  });
}
function toggleImg(img) {
  img.classList.toggle('expanded');
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


def build_card(filename: str, image_path: pathlib.Path, result: dict,
               exp: Optional[dict], elapsed: float, status: str) -> str:
    header = result.get("header", {})
    bs = header.get("bullshit_index")
    verdict = header.get("verdict", "—")
    risk = header.get("risk_level", "")
    truth_label = header.get("truth_label", "—")
    toxic = result.get("toxic_review", "")
    flaw_list = result.get("flaw_list", [])
    radar = result.get("radar_chart", {})
    inv = result.get("investigation_report", {})
    error = result.get("error", "")
    one_line = result.get("one_line_summary", "")

    badge_text = {"pass": "✅ 通过", "fail": "❌ 失败", "noexp": "⚪ 无预期"}[status]
    label = (exp or {}).get("label", filename)

    # 图片 base64
    img_src = img_to_base64(image_path) if image_path.exists() else ""
    img_html = f'<img class="card-img" src="{img_src}" alt="{filename}" onclick="toggleImg(this)" title="点击展开/收起">' if img_src else '<div style="height:60px;background:#0a0a14;display:flex;align-items:center;justify-content:center;color:#444">图片不可用</div>'

    gauge_svg = build_gauge_svg(bs)

    # 预期区
    if exp is not None:
        exp_fake_val = exp.get("expected_fake")
        exp_bs_min = exp.get("expected_bs_min", 0)
        exp_fake_str = "❌ 假信息" if exp_fake_val else "✅ 真实信息"
        exp_fake_cls = "fake" if exp_fake_val else "real"
        actual_bs_str = str(bs) if bs is not None else "N/A"
        actual_fake_str = ("❌ 假" if (bs or 0) >= 56 else "✅ 真") if bs is not None else "N/A"
        reason = exp.get("reason", "")
        expect_html = f"""
<div class="section">
  <div class="section-title">预期 vs 实际</div>
  <div class="expect-grid">
    <div class="expect-item">
      <div class="expect-key">预期判断</div>
      <div class="expect-val {exp_fake_cls}">{exp_fake_str}</div>
    </div>
    <div class="expect-item">
      <div class="expect-key">实际判断</div>
      <div class="expect-val">{actual_fake_str}（BS={actual_bs_str}）</div>
    </div>
    <div class="expect-item">
      <div class="expect-key">BS下限要求</div>
      <div class="expect-val">≥ {exp_bs_min}</div>
    </div>
    <div class="expect-item">
      <div class="expect-key">耗时</div>
      <div class="expect-val">{elapsed:.1f}s</div>
    </div>
  </div>
  <div style="margin-top:8px;">
    <div class="expect-key">核实依据</div>
    <div class="reason-text" style="margin-top:4px;font-size:0.8rem;">{reason}</div>
  </div>
</div>"""
    else:
        expect_html = f"""
<div class="section">
  <div class="section-title">本图无预期（自由测试）</div>
  <div style="color:var(--muted);font-size:0.82rem;">耗时 {elapsed:.1f}s | BS={bs if bs is not None else 'N/A'}</div>
</div>"""

    # 雷达图
    radar_items = [
        ("逻辑", radar.get("logic_consistency", 0)),
        ("来源", radar.get("source_authority", 0)),
        ("煽动", radar.get("agitation_level", 0)),
        ("搜索", radar.get("search_match", 0)),
    ]
    radar_html = '<div class="radar">' + "".join(
        f'<div class="radar-item"><div class="radar-key">{k}</div>'
        f'<div class="radar-bar"><div class="radar-fill" style="width:{min(v,100)}%"></div></div>'
        f'<div style="font-size:0.7rem;margin-top:2px;color:var(--muted)">{v}</div></div>'
        for k, v in radar_items
    ) + "</div>"

    # 调查报告（可折叠）
    inv_rows = "".join(
        f'<div style="margin-bottom:4px"><span style="color:var(--muted);font-size:0.75rem">{k}：</span>{v}</div>'
        for k, v in inv.items() if v
    )
    inv_html = ""
    if inv_rows:
        inv_html = f"""
<div>
  <button class="toggle-btn" onclick="toggleSection(this)">▼ 收起</button>
  <div class="section">
    <div class="section-title">调查报告</div>
    <div style="font-size:0.8rem;line-height:1.6">{inv_rows}</div>
  </div>
</div>"""

    # 瑕疵列表
    flaw_html = ""
    if flaw_list:
        items = "".join(f'<li style="margin-bottom:4px">{f}</li>' for f in flaw_list)
        flaw_html = f"""
<div>
  <button class="toggle-btn" onclick="toggleSection(this)">▼ 收起</button>
  <div class="section">
    <div class="section-title">瑕疵列表（{len(flaw_list)}条）</div>
    <ul style="padding-left:16px;font-size:0.8rem;line-height:1.6">{items}</ul>
  </div>
</div>"""

    # 错误信息
    error_html = ""
    if error:
        short = error[:300] + ("..." if len(error) > 300 else "")
        error_html = f'<div class="error-box"><div class="section-title" style="color:var(--fail)">错误</div><div class="error-text">{short}</div></div>'

    return f"""
<div class="card {status}" data-status="{status}">
  {img_html}
  <div class="card-body">
    <div class="card-top">
      <div class="gauge-wrap">{gauge_svg}</div>
      <div class="card-info">
        <div class="filename">{filename}</div>
        <div class="label">{label}</div>
        <div style="margin-top:4px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <span class="badge {status}">{badge_text}</span>
          <span style="font-size:0.78rem;color:#cba6f7">{risk}</span>
          <span style="font-size:0.78rem;color:var(--muted)">{truth_label}</span>
        </div>
      </div>
    </div>
    <div class="section">
      <div class="section-title">一句话总结</div>
      <div class="review-text">{one_line or verdict}</div>
    </div>
    <div class="section">
      <div class="section-title">锐评</div>
      <div class="review-text">{toxic}</div>
    </div>
    {radar_html}
    {expect_html}
    {inv_html}
    {flaw_html}
    {error_html}
  </div>
</div>"""


def generate_report(items: list[tuple[str, pathlib.Path, Optional[dict]]]) -> pathlib.Path:
    """
    items: [(filename, image_path, exp_or_None), ...]
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"report_{timestamp}.html"

    results = []
    total = len(items)
    for i, (filename, image_path, exp) in enumerate(items, 1):
        print(f"[{i}/{total}] 分析: {filename} ...", end=" ", flush=True)
        try:
            result, elapsed = run_analysis(image_path)
            status = evaluate_result(result, exp)
        except Exception as e:
            result = {"header": {"bullshit_index": None, "verdict": f"异常: {e}", "risk_level": "💥", "truth_label": ""},
                      "toxic_review": "", "flaw_list": [], "radar_chart": {}, "investigation_report": {},
                      "error": str(e), "one_line_summary": "分析异常"}
            elapsed = 0.0
            status = "fail" if exp is not None else "noexp"
        bs = result.get("header", {}).get("bullshit_index", "N/A")
        print(f"BS={bs} [{status}] ({elapsed:.1f}s)")
        results.append((filename, image_path, result, exp, elapsed, status))

    # 统计
    n_pass = sum(1 for *_, s in results if s == "pass")
    n_fail = sum(1 for *_, s in results if s == "fail")
    n_noexp = sum(1 for *_, s in results if s == "noexp")
    n_total = len(results)
    n_expected = n_pass + n_fail

    # 排序：fail 优先 → pass → noexp
    order = {"fail": 0, "pass": 1, "noexp": 2}
    results.sort(key=lambda r: order[r[-1]])

    # 构建 HTML
    stats_html = f"""
<div class="meta">生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 共 {n_total} 张图片</div>
<div class="stats-bar">
  <div class="stat"><div class="stat-num" style="color:var(--text)">{n_total}</div><div class="stat-label">总计</div></div>
  <div class="stat"><div class="stat-num" style="color:var(--pass)">{n_pass}</div><div class="stat-label">通过</div></div>
  <div class="stat"><div class="stat-num" style="color:var(--fail)">{n_fail}</div><div class="stat-label">失败</div></div>
  <div class="stat"><div class="stat-num" style="color:var(--noexp)">{n_noexp}</div><div class="stat-label">无预期</div></div>
  <div class="stat"><div class="stat-num" style="color:{'var(--pass)' if n_fail == 0 else 'var(--fail)'}">{n_pass}/{n_expected}</div><div class="stat-label">通过率</div></div>
</div>
<div class="filters">
  <button class="filter-btn" data-filter="all" onclick="filterCards('all')">全部 ({n_total})</button>
  <button class="filter-btn" data-filter="fail" onclick="filterCards('fail')">❌ 失败 ({n_fail})</button>
  <button class="filter-btn" data-filter="pass" onclick="filterCards('pass')">✅ 通过 ({n_pass})</button>
  <button class="filter-btn" data-filter="noexp" onclick="filterCards('noexp')">⚪ 无预期 ({n_noexp})</button>
</div>
<div class="grid">"""

    cards_html = "".join(
        build_card(filename, image_path, result, exp, elapsed, status)
        for filename, image_path, result, exp, elapsed, status in results
    )

    html = HTML_HEADER + stats_html + cards_html + "\n</div>\n" + HTML_FOOTER

    report_path.write_text(html, encoding="utf-8")
    print(f"\n报告已保存：{report_path}")
    print(f"结果：{n_pass} 通过 / {n_fail} 失败 / {n_noexp} 无预期 （共 {n_total} 张）")
    return report_path


# ── 主入口 ────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) > 1:
        # 命令行指定图片路径（无预期）
        items = []
        for arg in sys.argv[1:]:
            p = pathlib.Path(arg)
            if not p.exists():
                print(f"警告：找不到文件 {p}，跳过")
                continue
            items.append((p.name, p, None))
        if not items:
            print("没有有效的图片路径，退出。")
            sys.exit(1)
    else:
        # 默认：测试所有 EXPECTATIONS fixtures
        items = []
        for filename, exp in EXPECTATIONS.items():
            image_path = FIXTURES_DIR / filename
            if not image_path.exists():
                print(f"警告：找不到 fixture {filename}，跳过")
                continue
            items.append((filename, image_path, exp))
        print(f"将测试 {len(items)} 张 fixture 图片\n")

    report_path = generate_report(items)

    # 尝试在浏览器中打开报告
    import webbrowser
    webbrowser.open(report_path.as_uri())


if __name__ == "__main__":
    main()
