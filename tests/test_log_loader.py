"""log_loader + markdown_render 单元测试。"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from analysis.log_loader import (
    load_logs_since,
    load_history,
    per_case_summary,
    collect_cases,
    detect_dev_replays,
    Thresholds,
)
from analysis.markdown_render import render_report


def _make_log(call_id: str, ts: str, path: str = "plan_execute",
              total_in: int = 100000, total_out: int = 3000,
              stages: list[dict] | None = None) -> dict:
    return {
        "call_id": call_id,
        "ts": ts,
        "mode": "analyze",
        "path": path,
        "input": {"image_count": 1},
        "stages": stages or [
            {"name": "verify: claim A", "elapsed_s": 10, "tokens": {"input_tokens": 30000, "output_tokens": 500}},
            {"name": "hype_check", "elapsed_s": 5, "tokens": {"input": 700, "output": 30}},
            {"name": "verify: claim A 重核", "elapsed_s": 8, "tokens": {"input_tokens": 15000, "output_tokens": 300}},
        ],
        "total_tokens": {"input_tokens": total_in, "output_tokens": total_out},
        "total_elapsed_s": 25.0,
    }


def _make_history(call_id: str, title: str = "测试 case",
                  verdicts: list[str] | None = None,
                  search_queries: list[tuple[int, str]] | None = None,
                  header_verdict: str = "verdict 文本") -> dict:
    verdicts = verdicts or ["✓ 存在"]
    claims = [
        {"claim": f"claim {i}", "verdict": v, "fact_layer": v,
         "sources": ["http://a.com", "http://b.com"], "note": "some note"}
        for i, v in enumerate(verdicts)
    ]
    search_log = [{"round": r, "query": q} for r, q in (search_queries or [(0, "q1")])]
    return {
        "id": call_id,
        "timestamp": "2026-05-11T15:00:00",
        "mode": "analyze",
        "title": title,
        "result": {
            "_call_id": call_id,
            "_path": "plan_execute",
            "header": {"verdict": header_verdict, "bullshit_index": 30, "bullshit_nature": "基本属实"},
            "claim_verification": claims,
            "_search_log": search_log,
        },
    }


def test_load_logs_filters_by_date():
    """logs 早于 since_dt 应被过滤掉。"""
    with tempfile.TemporaryDirectory() as td:
        # 一个老 log（2026-04-01），一个新 log（2026-05-11）
        old = _make_log("c_old", "2026-04-01T10:00:00+00:00")
        new = _make_log("c_new", "2026-05-11T10:00:00+00:00")
        with open(os.path.join(td, "old.json"), "w", encoding="utf-8") as f:
            json.dump(old, f)
        with open(os.path.join(td, "new.json"), "w", encoding="utf-8") as f:
            json.dump(new, f)

        since = datetime(2026, 5, 1, tzinfo=timezone.utc)
        result = load_logs_since(since, logs_dir=td)
    assert len(result) == 1
    assert result[0]["call_id"] == "c_new"


def test_per_case_summary_extracts_key_fields():
    log = _make_log(
        "c1", "2026-05-11T10:00:00+00:00",
        stages=[
            {"name": "verify: A", "elapsed_s": 12, "tokens": {"input_tokens": 50000, "output_tokens": 800}},
            {"name": "verify: B", "elapsed_s": 8,  "tokens": {"input_tokens": 20000, "output_tokens": 400}},
            {"name": "hype_check", "elapsed_s": 5, "tokens": {"input": 700, "output": 30}},
            {"name": "verify: A 重核", "elapsed_s": 9, "tokens": {"input_tokens": 12000, "output_tokens": 200}},
        ],
    )
    hist = _make_history(
        "c1",
        verdicts=["✓ 存在", "? 无法核实"],
        search_queries=[(0, "q1"), (0, "q2"), (1, "q1"), (1, "q3")],  # round 1 的 q1 是 round 0 已有
        header_verdict="详细 verdict 文本",
    )
    s = per_case_summary(log, hist)

    assert s["case_id"] == "c1"
    assert s["mode"] == "analyze"
    assert s["path"] == "plan_execute"
    assert s["tokens"]["input"] == 100000
    assert s["stages_count"] == 4
    assert s["phase1_stages_count"] == 2  # 切到 hype_check 前 = A、B
    assert s["phase2_stages_count"] == 1  # 之后 = A 重核
    assert s["claim_count"] == 2
    assert s["claim_verdicts"] == {"✓ 存在": 1, "? 无法核实": 1}
    assert s["search_total"] == 4
    assert s["search_unique"] == 3  # q1 q2 q3 unique
    assert s["cross_round_repeats"] == 1  # round 1 的 q1
    assert s["top_stages"][0]["name"].startswith("verify: A")  # 最高 input
    assert "cross_round_repeat_queries=1" in " | ".join(s["outliers"])


def test_per_case_summary_no_history_works():
    """无 history 也能跑（只有 log 字段）。"""
    log = _make_log("c2", "2026-05-11T10:00:00+00:00")
    s = per_case_summary(log, None)
    assert s["case_id"] == "c2"
    assert s["title"] == ""
    assert s["claim_count"] == 0
    assert s["header_verdict"] == ""


def test_render_report_contains_metadata_and_cases():
    log = _make_log("c1", "2026-05-11T10:00:00+00:00")
    hist = _make_history("c1", verdicts=["✓ 存在"])
    cases = [per_case_summary(log, hist)]
    since = datetime(2026, 5, 1, tzinfo=timezone.utc)
    now = datetime(2026, 5, 12, tzinfo=timezone.utc)
    out = render_report(cases, since, now, git_commit="abc1234")

    assert "鉴定日志分析快报" in out
    assert "abc1234" in out
    assert "c1" in out
    assert "case 总数" in out
    # outlier 标记 verdict_text_empty 不应出现（hist 给了 verdict 文本）
    assert "verdict_text_empty" not in out


def test_collect_cases_filters_to_plan_execute():
    """非 plan_execute 路径默认被过滤。"""
    with tempfile.TemporaryDirectory() as td:
        pe = _make_log("c_pe", "2026-05-11T10:00:00+00:00", path="plan_execute")
        cl = _make_log("c_classic", "2026-05-11T10:00:00+00:00", path="classic")
        with open(os.path.join(td, "pe.json"), "w", encoding="utf-8") as f:
            json.dump(pe, f)
        with open(os.path.join(td, "cl.json"), "w", encoding="utf-8") as f:
            json.dump(cl, f)
        # 空 history
        hist_path = os.path.join(td, "history.json")
        with open(hist_path, "w", encoding="utf-8") as f:
            json.dump([], f)

        since = datetime(2026, 5, 1, tzinfo=timezone.utc)
        cases = collect_cases(since, logs_dir=td, history_path=hist_path)
    assert len(cases) == 1
    assert cases[0]["case_id"] == "c_pe"


def test_load_history_indexes_by_call_id():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "history.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                [_make_history("call_A"), _make_history("call_B")],
                f, ensure_ascii=False,
            )
        h = load_history(path)
    assert set(h.keys()) == {"call_A", "call_B"}


def test_detect_dev_replays_marks_clustered_titles():
    """同 title 24h 内 ≥3 次出现 → 全部标记为 dev replay。"""
    cases = [
        {"title": "X", "timestamp": "2026-05-11T01:00:00+00:00", "claim_count": 5, "path": "plan_execute"},
        {"title": "X", "timestamp": "2026-05-11T02:00:00+00:00", "claim_count": 5, "path": "plan_execute"},
        {"title": "X", "timestamp": "2026-05-11T03:00:00+00:00", "claim_count": 5, "path": "plan_execute"},
        {"title": "Y", "timestamp": "2026-05-11T01:00:00+00:00", "claim_count": 5, "path": "plan_execute"},  # 单独，不标
    ]
    # 初始化 is_dev_replay 字段
    for c in cases:
        c["is_dev_replay"] = False
    out = detect_dev_replays(cases)
    assert out[0]["is_dev_replay"] is True
    assert out[1]["is_dev_replay"] is True
    assert out[2]["is_dev_replay"] is True
    assert out[3]["is_dev_replay"] is False  # 单 Y title


def test_detect_dev_replays_no_history_fallback():
    """空 title + claim_count=0 + plan_execute → 兜底标记为 dev replay。"""
    cases = [
        {"title": "", "timestamp": "2026-05-11T01:00:00+00:00", "claim_count": 0, "path": "plan_execute",
         "is_dev_replay": False},
    ]
    out = detect_dev_replays(cases)
    assert out[0]["is_dev_replay"] is True


def test_thresholds_param_affects_outliers():
    """传入 Thresholds 应改变 outlier 触发条件。"""
    log = _make_log("c1", "2026-05-11T10:00:00+00:00", total_in=150000)
    hist = _make_history("c1")
    # 默认阈值（200K）→ 不触发 token outlier
    s1 = per_case_summary(log, hist)
    assert not any("input_tokens=" in o for o in s1["outliers"])
    # 自定义低阈值（100K）→ 触发
    s2 = per_case_summary(log, hist, thresholds=Thresholds(token_high=100_000))
    assert any("input_tokens=150000" in o for o in s2["outliers"])


def test_collect_cases_exclude_dev_replay():
    """exclude_dev_replay=True 时过滤掉 dev replay case。"""
    with tempfile.TemporaryDirectory() as td:
        # 3 个同时间 dev replay log（空 history） + 1 个真实
        for i in range(3):
            log = _make_log(f"dev_{i}", f"2026-05-11T0{i+1}:00:00+00:00")
            with open(os.path.join(td, f"dev_{i}.json"), "w", encoding="utf-8") as f:
                json.dump(log, f)
        real = _make_log("real_1", "2026-05-11T05:00:00+00:00")
        with open(os.path.join(td, "real.json"), "w", encoding="utf-8") as f:
            json.dump(real, f)
        hist_path = os.path.join(td, "history.json")
        with open(hist_path, "w", encoding="utf-8") as f:
            json.dump([_make_history("real_1")], f)

        since = datetime(2026, 5, 1, tzinfo=timezone.utc)
        kept = collect_cases(since, logs_dir=td, history_path=hist_path,
                             exclude_dev_replay=True)
    case_ids = {c["case_id"] for c in kept}
    assert case_ids == {"real_1"}
