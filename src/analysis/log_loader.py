"""日志与 history 加载、按 case 聚合关键字段。纯 stdlib，不依赖 src/ai/。

主要 API：
- load_logs_since(since_dt, logs_dir) → list[dict]
- load_history(path) → dict[call_id -> history_entry]
- per_case_summary(log_entry, history_entry, thresholds) → dict
- collect_cases(since_dt, ..., thresholds, exclude_dev_replay) → list[dict]
- detect_dev_replays(cases) → 标记 is_dev_replay
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Iterable, NamedTuple


class Thresholds(NamedTuple):
    """outlier 判定阈值。None 表示不做对应检查。"""
    token_high: int = 200_000          # input tokens 异常上限
    elapsed_high_s: float = 120.0      # 单 case 耗时异常上限
    cross_round_repeats_high: int = 0  # 跨轮重复 query 异常下限（> 此值算 outlier）


def _parse_ts(ts: str) -> datetime | None:
    """解析 ISO timestamp，失败返回 None。"""
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def load_logs_since(since_dt: datetime, logs_dir: str = "logs") -> list[dict]:
    """加载 logs_dir 下所有 .json 文件，过滤 ts >= since_dt。按 ts 升序返回。"""
    out = []
    if not os.path.isdir(logs_dir):
        return out
    for fname in os.listdir(logs_dir):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(logs_dir, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue  # 忽略非 log 文件（如 history.json 是 list）
        ts = _parse_ts(data.get("ts", ""))
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        cmp_since = since_dt if since_dt.tzinfo else since_dt.replace(tzinfo=timezone.utc)
        if ts < cmp_since:
            continue
        data["_file"] = fname
        out.append(data)
    out.sort(key=lambda d: d.get("ts", ""))
    return out


def load_history(path: str = "history.json") -> dict[str, dict]:
    """加载 history.json，返回 call_id → entry 映射。"""
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
    out = {}
    for e in entries:
        result = e.get("result", {}) or {}
        cid = result.get("_call_id")
        if cid:
            out[cid] = e
    return out


def _stage_tokens(stage: dict) -> int:
    t = stage.get("tokens", {}) or {}
    return int(t.get("input_tokens") or t.get("input") or 0)


def _split_phases(stages: list[dict]) -> tuple[list[dict], list[dict]]:
    """以 hype_check stage 为分隔，前为 phase 1，后为 phase 2。"""
    pivot = None
    for i, s in enumerate(stages):
        if s.get("name", "") == "hype_check":
            pivot = i
            break
    if pivot is None:
        return list(stages), []
    return list(stages[:pivot]), list(stages[pivot + 1 :])


def per_case_summary(log_entry: dict, history_entry: dict | None,
                     thresholds: Thresholds | None = None) -> dict:
    """提取单个 case 的关键字段。"""
    th = thresholds or Thresholds()
    call_id = log_entry.get("call_id", "")
    mode = log_entry.get("mode", "")
    path = log_entry.get("path", "")
    ts = log_entry.get("ts", "")
    stages = log_entry.get("stages", []) or []
    total_tokens = log_entry.get("total_tokens", {}) or {}
    elapsed = log_entry.get("total_elapsed_s", 0) or 0
    log_file = log_entry.get("_file", "")

    phase1_stages, phase2_stages = _split_phases(stages)

    stage_info = [
        {"name": s.get("name", ""), "input": _stage_tokens(s), "elapsed_s": s.get("elapsed_s")}
        for s in stages
    ]
    top_stages = sorted(stage_info, key=lambda x: -x["input"])[:3]

    title = ""
    claim_summaries: list[dict] = []
    header_verdict = ""
    bullshit_index = None
    bullshit_nature = ""
    search_log: list = []
    url_snippets_count = 0
    if history_entry:
        title = history_entry.get("title", "") or ""
        result = history_entry.get("result", {}) or {}
        header = result.get("header", {}) or {}
        header_verdict = header.get("verdict", "") or ""
        bullshit_index = header.get("bullshit_index")
        bullshit_nature = header.get("bullshit_nature", "") or ""
        for c in result.get("claim_verification", []) or []:
            claim_summaries.append({
                "claim": (c.get("claim") or "")[:120],
                "verdict": c.get("verdict", ""),
                "fact_layer": c.get("fact_layer", ""),
                "sources_count": len(c.get("sources", []) or []),
                "note": (c.get("note") or "")[:200],
            })
        search_log = result.get("_search_log", []) or []
        all_urls = set()
        for c in result.get("claim_verification", []) or []:
            for u in (c.get("sources") or []):
                all_urls.add(u)
        url_snippets_count = len(all_urls)

    queries_by_round: dict = {}
    for s in search_log:
        r = s.get("round", -1)
        queries_by_round.setdefault(r, []).append(s.get("query", ""))
    search_total = sum(len(v) for v in queries_by_round.values())
    search_unique = len({q for qs in queries_by_round.values() for q in qs})
    seen = set()
    cross_round_repeats = 0
    for r in sorted(queries_by_round.keys()):
        for q in queries_by_round[r]:
            if q in seen:
                cross_round_repeats += 1
            else:
                seen.add(q)

    verdict_dist = Counter(c["verdict"] for c in claim_summaries)

    in_tokens = int(total_tokens.get("input_tokens") or total_tokens.get("input") or 0)
    out_tokens = int(total_tokens.get("output_tokens") or total_tokens.get("output") or 0)

    outliers: list[str] = []
    if th.token_high and in_tokens > th.token_high:
        outliers.append(f"input_tokens={in_tokens}")
    if th.elapsed_high_s and elapsed > th.elapsed_high_s:
        outliers.append(f"elapsed={elapsed:.0f}s")
    if claim_summaries and all(c["verdict"].startswith("? 无法") for c in claim_summaries):
        outliers.append("all_unverified")
    if cross_round_repeats > th.cross_round_repeats_high:
        outliers.append(f"cross_round_repeat_queries={cross_round_repeats}")
    # verdict_text_empty：去掉 bullshit_index is not None 的 guard，
    # 让 replay 场景也能暴露"模型没 submit_verdict"问题
    if claim_summaries and not header_verdict:
        outliers.append("verdict_text_empty")

    return {
        "case_id": call_id,
        "timestamp": ts,
        "log_file": log_file,
        "mode": mode,
        "path": path,
        "title": title,
        "elapsed_s": elapsed,
        "tokens": {"input": in_tokens, "output": out_tokens, "total": in_tokens + out_tokens},
        "stages_count": len(stages),
        "phase1_stages_count": len(phase1_stages),
        "phase2_stages_count": len(phase2_stages),
        "top_stages": top_stages,
        "search_total": search_total,
        "search_unique": search_unique,
        "cross_round_repeats": cross_round_repeats,
        "queries_by_round": queries_by_round,
        "claim_count": len(claim_summaries),
        "claim_verdicts": dict(verdict_dist),
        "claims": claim_summaries,
        "url_count": url_snippets_count,
        "header_verdict": header_verdict[:300],
        "bullshit_index": bullshit_index,
        "bullshit_nature": bullshit_nature,
        "outliers": outliers,
        "is_dev_replay": False,  # collect_cases 后处理填
    }


def detect_dev_replays(cases: list[dict], cluster_window_hours: int = 24,
                       min_cluster_size: int = 3) -> list[dict]:
    """启发式标记 dev replay：
    - 24h 内同 title（含空 title）出现 >= min_cluster_size 次 → 全组标记
    - 空 title + 无 history（claim_count=0）也是强信号
    返回原 list（in-place 修改 is_dev_replay 字段）。
    """
    # 1) 按 title 分桶，时间排序
    by_title: dict[str, list[dict]] = defaultdict(list)
    for c in cases:
        key = c.get("title") or "(no-title)"
        by_title[key].append(c)
    # 2) 对每桶内按 timestamp 滑窗
    window = timedelta(hours=cluster_window_hours)
    for title, items in by_title.items():
        items.sort(key=lambda x: x.get("timestamp", ""))
        timestamps = []
        for c in items:
            t = _parse_ts(c.get("timestamp", ""))
            timestamps.append(t)
        # 滑动窗口找 cluster
        marked_idx: set[int] = set()
        for i in range(len(items)):
            if timestamps[i] is None:
                continue
            # 找窗口内有多少个
            j_end = i
            for j in range(i, len(items)):
                if timestamps[j] is None:
                    continue
                if (timestamps[j] - timestamps[i]) <= window:
                    j_end = j
                else:
                    break
            if (j_end - i + 1) >= min_cluster_size:
                for k in range(i, j_end + 1):
                    marked_idx.add(k)
        for k in marked_idx:
            items[k]["is_dev_replay"] = True
    # 3) 兜底：无 history + 空 title + plan_execute → 也算 dev replay
    for c in cases:
        if (not c["title"]) and c["claim_count"] == 0 and c["path"] == "plan_execute":
            c["is_dev_replay"] = True
    return cases


def collect_cases(since_dt: datetime, logs_dir: str = "logs",
                  history_path: str = "history.json",
                  paths_filter: Iterable[str] = ("plan_execute",),
                  thresholds: Thresholds | None = None,
                  exclude_dev_replay: bool = False,
                  include_dev_as_real: bool = False) -> list[dict]:
    """高层 API：加载并聚合 case summary。默认只保留 plan_execute 路径。

    exclude_dev_replay=True 时过滤掉 is_dev_replay 标记的 case
    include_dev_as_real=True 时跳过 dev replay 启发式检测（强制所有 case 视为真实）
    """
    logs = load_logs_since(since_dt, logs_dir)
    history = load_history(history_path)
    out = []
    for log in logs:
        if paths_filter and log.get("path") not in paths_filter:
            continue
        cid = log.get("call_id", "")
        hist = history.get(cid)
        out.append(per_case_summary(log, hist, thresholds))
    if not include_dev_as_real:
        out = detect_dev_replays(out)
    if exclude_dev_replay:
        out = [c for c in out if not c["is_dev_replay"]]
    return out
