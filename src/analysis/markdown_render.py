"""把 per_case_summary 列表渲染成给 Claude 看的结构化 markdown。

输出固定结构方便 Claude 解析：
- 元数据头
- 真实 case 全局聚合统计
- 真实 case 详情
- Dev replay 时序演变（如有）
- Dev replay case 详情
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from statistics import median


def _fmt_token(n: int) -> str:
    if n >= 1000:
        return f"{n/1000:.1f}K"
    return str(n)


def _pct(arr: list[int], p: float) -> int:
    if not arr:
        return 0
    idx = max(0, min(len(arr) - 1, int(round(p * (len(arr) - 1)))))
    return arr[idx]


def render_global_stats(cases: list[dict], label: str = "全局聚合统计",
                        min_cases_for_stats: int = 5) -> str:
    """case 数 < min_cases_for_stats 时改为列举式（不算 median/p95，避免统计假象）。"""
    if not cases:
        return f"## {label}\n\n（无可分析的 case）\n\n"

    if len(cases) < min_cases_for_stats:
        # 列举式：逐条简洁列
        parts = [
            f"## {label}",
            "",
            f"> case 数 {len(cases)} < {min_cases_for_stats}，统计指标无意义，改为列举式。",
            "",
        ]
        for c in cases:
            parts.append(
                f"- `{c['case_id']}` | input={_fmt_token(c['tokens']['input'])} "
                f"elapsed={c['elapsed_s']:.0f}s | claims={c['claim_count']} "
                f"({c['claim_verdicts']}) | outliers={c['outliers'] or '无'}"
            )
        parts.append("")
        return "\n".join(parts) + "\n"

    inputs = sorted(c["tokens"]["input"] for c in cases)
    elapsed = [c["elapsed_s"] for c in cases if c["elapsed_s"]]
    claim_counts = [c["claim_count"] for c in cases if c["claim_count"]]

    verdict_counter: Counter = Counter()
    for c in cases:
        for v, n in c["claim_verdicts"].items():
            verdict_counter[v] += n
    verdict_lines = [f"- `{v}`: {n}" for v, n in verdict_counter.most_common()]

    outlier_counter: Counter = Counter()
    for c in cases:
        for o in c["outliers"]:
            tag = o.split("=")[0] if "=" in o else o
            outlier_counter[tag] += 1
    outlier_lines = [f"- `{tag}`: 出现 {n} case" for tag, n in outlier_counter.most_common()]

    bullshit_dist = Counter(c["bullshit_nature"] for c in cases if c["bullshit_nature"])
    bullshit_lines = [f"- `{k}`: {v}" for k, v in bullshit_dist.most_common()]

    median_in = _pct(inputs, 0.5)
    p95_in = _pct(inputs, 0.95)
    max_in = inputs[-1] if inputs else 0
    median_elapsed = median(elapsed) if elapsed else 0

    parts = [
        f"## {label}",
        "",
        f"- case 总数: **{len(cases)}**",
        f"- input tokens 中位数 / p95 / max: **{_fmt_token(median_in)} / {_fmt_token(p95_in)} / {_fmt_token(max_in)}**",
        f"- 平均耗时（中位数）: **{median_elapsed:.1f}s**",
        f"- claim 数（中位数 / max）: **{int(median(claim_counts)) if claim_counts else 0} / {max(claim_counts) if claim_counts else 0}**",
        "",
        "### verdict 分布（所有 case 累加）",
    ]
    parts.extend(verdict_lines or ["（无）"])
    parts.extend(["", "### bullshit_nature 分布"])
    parts.extend(bullshit_lines or ["（无）"])
    parts.extend(["", "### outlier 标记分布"])
    parts.extend(outlier_lines or ["（无 outlier）"])
    parts.append("")
    return "\n".join(parts) + "\n"


def render_case(c: dict) -> str:
    parts = [
        f"### case `{c['case_id']}` ({c['timestamp']})",
        "",
        f"- log_file: `logs/{c['log_file']}`",
        f"- title: {c['title'] or '(无)'}",
        f"- path: `{c['path']}` | mode: `{c['mode']}`",
        f"- tokens: input={_fmt_token(c['tokens']['input'])} output={_fmt_token(c['tokens']['output'])} | elapsed={c['elapsed_s']:.1f}s",
        f"- stages: 总 {c['stages_count']} (phase1={c['phase1_stages_count']}, phase2={c['phase2_stages_count']})",
        f"- claims: {c['claim_count']} 个; verdicts={c['claim_verdicts']}",
        f"- bullshit_index: {c['bullshit_index']} | nature: `{c['bullshit_nature']}`",
        f"- header verdict 文本长度: {len(c['header_verdict'])} 字{' (空!)' if not c['header_verdict'] else ''}",
        f"- search: 总 {c['search_total']} 次, unique {c['search_unique']}, 跨轮重复 {c['cross_round_repeats']} 次",
        f"- url_count (累计 source): {c['url_count']}",
        f"- outliers: {c['outliers'] or '无'}",
        "",
        "**top 3 stages by input tokens**:",
    ]
    for ts_ in c["top_stages"]:
        parts.append(f"  - `{ts_['name'][:60]}`: in={_fmt_token(ts_['input'])} elapsed={ts_.get('elapsed_s')}s")

    if c["queries_by_round"]:
        parts.append("")
        parts.append("**search queries by round**:")
        for r in sorted(c["queries_by_round"].keys()):
            qs = c["queries_by_round"][r]
            sample = qs[0] if qs else ""
            parts.append(f"  - round {r}: {len(qs)} 次 (e.g. \"{sample[:60]}\")")

    if c["claims"]:
        parts.append("")
        parts.append("**claim 详情**:")
        for i, cl in enumerate(c["claims"]):
            parts.append(f"  - [{i}] `{cl['verdict']}` ({cl['sources_count']} src) {cl['claim']}")
            if cl["note"]:
                parts.append(f"    note: {cl['note']}")

    parts.append("")
    return "\n".join(parts)


def render_dev_replay_timeline(replays: list[dict]) -> str:
    """按 title 分组，按时间序列展示 token / claim_count 演变。"""
    if not replays:
        return ""
    by_title: dict[str, list[dict]] = defaultdict(list)
    for c in replays:
        key = c.get("title") or "(no-title)"
        by_title[key].append(c)

    parts = ["## Dev Replay 时序演变",
             "",
             "（同 title 24h 内 ≥3 次出现，按时间排序展示 token 演变。用于观察调优期间数据漂移。）",
             ""]
    for title, items in sorted(by_title.items(), key=lambda kv: -len(kv[1])):
        items.sort(key=lambda x: x.get("timestamp", ""))
        parts.append(f"### {title}（{len(items)} 次 replay）")
        parts.append("")
        parts.append("| 时间 | input | Δinput | output | elapsed | claim数 | stages |")
        parts.append("|------|-------|--------|--------|---------|---------|--------|")
        prev_in = None
        for c in items:
            cur_in = c["tokens"]["input"]
            if prev_in is None:
                delta_str = "—"
            else:
                d = cur_in - prev_in
                sign = "+" if d >= 0 else "-"
                delta_str = f"{sign}{_fmt_token(abs(d))}"
            parts.append(
                f"| {c['timestamp'][:19]} | {_fmt_token(cur_in)} | {delta_str} | "
                f"{_fmt_token(c['tokens']['output'])} | {c['elapsed_s']:.0f}s | "
                f"{c['claim_count']} | {c['stages_count']} |"
            )
            prev_in = cur_in
        parts.append("")
    return "\n".join(parts) + "\n"


def render_report(cases: list[dict], since_dt: datetime, now_dt: datetime,
                  git_commit: str = "") -> str:
    """完整结构化 markdown 输出。"""
    real_cases = [c for c in cases if not c.get("is_dev_replay")]
    dev_replays = [c for c in cases if c.get("is_dev_replay")]

    head = [
        "# 鉴定日志分析快报（数据准备产出）",
        "",
        "> 由 `scripts/prepare_log_data.py` 自动生成。**这不是最终报告**，",
        "> 是给 Claude 读的结构化数据；Claude 据此识别系统性问题并写报告。",
        "",
        "## 元数据",
        "",
        f"- 分析时间窗: 从 **{since_dt.isoformat()}** 至 **{now_dt.isoformat()}**",
        f"- case 总数（仅 plan_execute 路径）: **{len(cases)}**（其中真实 {len(real_cases)}，dev replay {len(dev_replays)}）",
        f"- 生成时间: {now_dt.isoformat()}",
        f"- git_commit: {git_commit or '(unknown)'}",
        "",
    ]
    parts = "\n".join(head)
    parts += render_global_stats(real_cases, label="真实 case 全局聚合统计")

    if real_cases:
        parts += "## 真实 case 详情\n\n"
        for c in real_cases:
            parts += render_case(c) + "\n"
    else:
        parts += "## 真实 case 详情\n\n（无真实 case）\n\n"

    if dev_replays:
        parts += render_dev_replay_timeline(dev_replays)
        parts += "## Dev Replay case 详情（参考；不计入主统计）\n\n"
        for c in dev_replays:
            parts += render_case(c) + "\n"

    return parts
