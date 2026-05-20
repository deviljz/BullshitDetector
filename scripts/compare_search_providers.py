"""跨 search provider 对比：从 logs/*.json 抽 verify claim 文本作为 query，跑各 provider 输出对比报告。

⚠ 调用真实搜索 API（DDG / Tavily / AnySearch），需要用户明确同意才跑。
不在 CI / 自动测试中执行。

用法：
    python scripts/compare_search_providers.py            # 默认抽 3 个 query，对比 ddg+anysearch
    python scripts/compare_search_providers.py --n 5      # 抽 5 个
    python scripts/compare_search_providers.py --tavily   # 同时跑 tavily（需 config.json 有 key）
"""

import argparse
import glob
import json
import os
import pathlib
import sys
import time
from typing import List, Tuple

# Windows 控制台 GBK 无法显示中文/emoji，强制 UTF-8
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from ai.tools import _search_ddg, _search_tavily, _search_anysearch  # type: ignore


VERIFY_PREFIX = "verify: "


def extract_queries_from_logs(log_dir: str, n: int) -> List[Tuple[str, str]]:
    """从 plan_execute log 抽 verify stage 的 claim 文本。返回 [(log_file, claim_text)]"""
    files = sorted(glob.glob(os.path.join(log_dir, "*.json")), key=os.path.getmtime, reverse=True)
    out: List[Tuple[str, str]] = []
    seen: set = set()
    for f in files:
        try:
            d = json.load(open(f, "r", encoding="utf-8"))
        except Exception:
            continue
        if d.get("path") != "plan_execute":
            continue
        for s in d.get("stages") or []:
            name = (s.get("name") or "").strip()
            if not name.startswith(VERIFY_PREFIX):
                continue
            claim = name[len(VERIFY_PREFIX):].strip()
            if not claim or claim in seen:
                continue
            seen.add(claim)
            out.append((os.path.basename(f), claim))
            if len(out) >= n:
                return out
    return out


def fmt_results(results: List[dict], max_lines: int = 3) -> str:
    if not results:
        return "  (空)"
    if "error" in results[0]:
        return f"  ❌ {results[0]['error'][:200]}"
    lines = []
    for i, r in enumerate(results[:max_lines], 1):
        title = (r.get("title") or "").strip()[:80]
        url = r.get("url") or ""
        snippet = (r.get("snippet") or "").strip()[:100].replace("\n", " ")
        lines.append(f"  {i}. {title}\n     {url}\n     {snippet}")
    return "\n".join(lines)


def run_one_provider(name: str, func, query: str, max_results: int) -> Tuple[List[dict], float]:
    t0 = time.time()
    try:
        results = func(query, max_results=max_results) if name == "ddg" else func(query, "", max_results) if name == "anysearch" else func(query, _tavily_key(), max_results)
    except Exception as e:
        results = [{"error": f"{name} 异常: {e}"}]
    return results, time.time() - t0


def _tavily_key() -> str:
    try:
        from config.manager import load as _load
        return _load().get("tavily_api_key", "") or ""
    except Exception:
        return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=3, help="抽取多少条 query（默认 3）")
    parser.add_argument("--max-results", type=int, default=3, help="每 provider 取前 N 条结果（默认 3）")
    parser.add_argument("--tavily", action="store_true", help="同时跑 Tavily（需要配置 key）")
    parser.add_argument("--log-dir", default="logs", help="日志目录（默认 logs）")
    parser.add_argument("--output", default="scripts/_compare_search_providers.md", help="输出报告路径")
    args = parser.parse_args()

    print(f"[1/3] 从 {args.log_dir} 抽取 {args.n} 条 verify claim 作为 query...")
    queries = extract_queries_from_logs(args.log_dir, args.n)
    if not queries:
        print("❌ 没找到 plan_execute log，无法继续。")
        return 1
    print(f"  抽到 {len(queries)} 条：")
    for f, q in queries:
        print(f"    [{f}] {q[:60]}")

    providers = [("ddg", _search_ddg), ("anysearch", _search_anysearch)]
    if args.tavily and _tavily_key():
        providers.append(("tavily", _search_tavily))

    print(f"\n[2/3] 跑 {len(providers)} 个 provider × {len(queries)} 个 query = {len(providers)*len(queries)} 次搜索...")
    print("  [!] 调用真实 API（DDG 走代理 / AnySearch 直连匿名 / Tavily 占用免费配额）。\n")
    report: List[str] = ["# 搜索 provider 对比报告\n"]
    report.append(f"- 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"- query 数: {len(queries)}")
    report.append(f"- 每 provider 取前 {args.max_results} 条\n")

    for log_f, q in queries:
        print(f"\n--- query: {q[:80]} ---")
        report.append(f"\n## Query: {q}")
        report.append(f"_source log: `{log_f}`_\n")
        for name, func in providers:
            results, elapsed = run_one_provider(name, func, q, args.max_results)
            print(f"  [{name}] {elapsed:.2f}s, {len(results)} 结果")
            report.append(f"### {name} ({elapsed:.2f}s, {len(results)} 结果)\n")
            report.append("```")
            report.append(fmt_results(results, args.max_results))
            report.append("```\n")

    print(f"\n[3/3] 写报告: {args.output}")
    with open(args.output, "w", encoding="utf-8") as f:
        f.write("\n".join(report))
    print("✅ 完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
