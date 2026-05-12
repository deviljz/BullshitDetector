"""鉴定日志数据准备脚本（不做分析，输出结构化 markdown 到 stdout）。

用法：
    python scripts/prepare_log_data.py --last 7
    python scripts/prepare_log_data.py --since 2026-05-01
    python scripts/prepare_log_data.py --last 7 --exclude-dev   # 完全过滤 dev replay
    python scripts/prepare_log_data.py --token-outlier 150000   # 自定义 token 阈值

输出：给 Claude 读的结构化 markdown（含元数据、全局统计、每 case 详情）。
"""
from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from analysis.log_loader import collect_cases, Thresholds
from analysis.markdown_render import render_report


def _git_commit() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or ""
    except Exception:
        return ""


def main() -> int:
    p = argparse.ArgumentParser(description="鉴定日志数据准备（输出结构化 markdown 到 stdout）")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--last", type=int, default=7, help="分析最近 N 天（默认 7）")
    g.add_argument("--since", type=str, help="ISO 日期，如 2026-05-01")
    p.add_argument("--logs-dir", default="logs")
    p.add_argument("--history", default="history.json")
    p.add_argument("--exclude-dev", action="store_true",
                   help="完全过滤 dev replay case（默认保留并标记到独立 section）")
    p.add_argument("--include-dev-as-real", action="store_true",
                   help="跳过 dev replay 启发式检测，强制所有 case 视为真实（适用于同篇真实文章被多次鉴定的场景）")
    p.add_argument("--token-outlier", type=int, default=200_000,
                   help="input tokens 异常阈值（默认 200K）")
    p.add_argument("--elapsed-outlier", type=float, default=120.0,
                   help="耗时异常阈值秒（默认 120）")
    args = p.parse_args()

    if args.since:
        try:
            since_dt = datetime.fromisoformat(args.since)
        except ValueError:
            print(f"无法解析 --since: {args.since!r}（需 ISO 格式如 2026-05-01）", file=sys.stderr)
            return 2
    else:
        since_dt = datetime.now(timezone.utc) - timedelta(days=args.last)
    if since_dt.tzinfo is None:
        since_dt = since_dt.replace(tzinfo=timezone.utc)

    thresholds = Thresholds(
        token_high=args.token_outlier,
        elapsed_high_s=args.elapsed_outlier,
    )
    cases = collect_cases(
        since_dt,
        logs_dir=args.logs_dir,
        history_path=args.history,
        thresholds=thresholds,
        exclude_dev_replay=args.exclude_dev,
        include_dev_as_real=args.include_dev_as_real,
    )
    now_dt = datetime.now(timezone.utc)
    markdown = render_report(cases, since_dt, now_dt, git_commit=_git_commit())

    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    print(markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
