"""
_PlanExecuteMixin — Plan-and-Execute pipeline methods.
Mixed into OpenAICompatibleProvider; no __init__, uses self.* from the host class.
"""

import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from ai.prompts import (
    get_claim_verify_prompt, get_title_logic_prompt, get_hype_check_prompt,
    get_planner_prompt, get_replanner_prompt,
)
from ai.prompts.shared import _current_date
from ai.json_utils import parse_json, normalize_result, _risk_level
from ai.tools import PLAN_EXECUTE_TOOLS, PLANNER_TOOLS, web_search_with_sources, FETCH_URL_TOOL

# _NO_THINKING imported from host module to avoid duplication
_NO_THINKING = {"reasoning_effort": "none"}

_DECAY = [1.0, 0.6, 0.4, 0.25]
_WEIGHT = {"决定性": 60, "重要": 35, "一般": 18, "次要": 7, "无关": 2}


import re as _re

_NUM_RE = _re.compile(r"\d{3,}")  # 3 位以上数字序列


def _claim_similarity(a: str, b: str) -> float:
    """字符 bigram Jaccard 相似度（中文友好；短句下 bigram 比 trigram 灵敏）。返回 0~1。"""
    a = "".join((a or "").split())
    b = "".join((b or "").split())
    if len(a) < 2 or len(b) < 2:
        return 1.0 if a == b else 0.0
    ga = {a[i:i+2] for i in range(len(a) - 1)}
    gb = {b[i:i+2] for i in range(len(b) - 1)}
    if not ga or not gb:
        return 0.0
    inter = len(ga & gb)
    # 用 min 分母：短 claim 整体被长 claim 包住时也能命中
    return inter / min(len(ga), len(gb))


def _shared_numbers(a: str, b: str) -> int:
    """两 claim 共享的不同 3 位以上数字数量（弱实体匹配信号）。"""
    na = set(_NUM_RE.findall(a or ""))
    nb = set(_NUM_RE.findall(b or ""))
    return len(na & nb)


def _is_duplicate_claim(new_claim: str, existing_claims: list[str]) -> bool:
    """检查 new_claim 是否与已有任一 claim 实质重复。

    双信号判定：
    - 高 bigram 相似度（≥0.65）→ 措辞接近的同义改写，判重
    - 共享 ≥2 个具体数字（如"3500""5000"）且 bigram ≥0.30 → 同事实不同措辞，判重
    """
    for ec in existing_claims:
        sim = _claim_similarity(new_claim, ec)
        if sim >= 0.65:
            return True
        if sim >= 0.30 and _shared_numbers(new_claim, ec) >= 2:
            return True
    return False


def _claim_polarity(r: dict) -> str:
    """Return claim polarity. Default 'supports_article' for backward compatibility.

    'supports_article': claim restates what the article asserts (✓=article OK, ✗=article wrong)
    'refutes_article': claim challenges the article's premise (✓=rebuttal stands → article wrong)
    """
    p = r.get("polarity")
    return p if p == "refutes_article" else "supports_article"


def _claim_is_fake(r: dict) -> bool:
    """True iff this claim signals the article is wrong (polarity-aware)."""
    polarity = _claim_polarity(r)
    if "fact_layer" in r:
        fact = r.get("fact_layer")
        if polarity == "refutes_article":
            return fact == "✓ 存在"
        return fact == "✗ 不存在"
    verdict = r.get("verdict") or ""
    if polarity == "refutes_article":
        return "✓" in verdict
    return "✗" in verdict


def _claim_is_verified(r: dict) -> bool:
    """True iff this claim signals the article is right (polarity-aware)."""
    polarity = _claim_polarity(r)
    if "fact_layer" in r:
        fact = r.get("fact_layer")
        if polarity == "refutes_article":
            return fact == "✗ 不存在"
        return fact == "✓ 存在"
    verdict = r.get("verdict") or ""
    if polarity == "refutes_article":
        return "✗" in verdict
    return "✓" in verdict


def _claim_is_uncertain(r: dict) -> bool:
    """True iff verdict is ? (uncertain). Polarity-invariant."""
    if "fact_layer" in r:
        return r.get("fact_layer") == "? 无法核实"
    return "?" in (r.get("verdict") or "")


def _claim_penalty_ratio(r: dict) -> float:
    """Map a claim result to a 0.0–1.0 penalty score (polarity-aware).

    For supports_article (default): ✓→0, ✗→1, ?→0.25
    For refutes_article:           ✓→1, ✗→0, ?→0.25 (verdict swap)
    """
    polarity = _claim_polarity(r)
    if "fact_layer" not in r:
        # Legacy format: single verdict string
        verdict = r.get("verdict", "")
        if "✗" in verdict:
            return 0.0 if polarity == "refutes_article" else 1.0
        if "?" in verdict:
            return 0.25
        if "✓" in verdict:
            return 1.0 if polarity == "refutes_article" else 0.0
        return 0.0
    # Timeout/failure is more suspicious than ordinary "无法核实"
    if "核查超时或失败" in (r.get("note") or ""):
        return 0.5
    fact = r.get("fact_layer", "? 无法核实")
    if fact == "○ 非事实声明":
        return 0.0
    if polarity == "refutes_article":
        base = {"✓ 存在": 1.0, "? 无法核实": 0.25, "✗ 不存在": 0.0}.get(fact, 0.25)
    else:
        base = {"✗ 不存在": 1.0, "? 无法核实": 0.25, "✓ 存在": 0.0}.get(fact, 0.25)
    extra = 0.0
    if r.get("number_layer") == "✗ 错误":
        extra += 0.55
    elif r.get("number_layer") == "⚠️ 近似":
        extra += 0.08
    if r.get("name_layer") == "✗ 误导性命名":
        extra += 0.25
    elif r.get("name_layer") == "⚠️ 俗称夸大":
        extra += 0.08
    if r.get("cause_layer") == "✗ 谬误":
        extra += 0.35
    elif r.get("cause_layer") == "⚠️ 存疑":
        extra += 0.08
    return min(1.0, base + extra)


class _PlanExecuteMixin:
    """Plan-and-Execute pipeline methods. No __init__."""

    def _verify_claim_model(self) -> str:
        """返回 verify_claim 阶段使用的 model.

        默认与 self._model 相同。若 config.json 顶层配 verify_claim_model 非空，
        verify 阶段用该 model（典型用法：planner 用 preview，verify 用 lite）。
        """
        try:
            from config.manager import load as _load_cfg
            override = (_load_cfg() or {}).get("verify_claim_model", "")
            if override:
                return override
        except Exception:
            pass
        return self._model

    def _verify_claim(self, claim: str | dict, article_text: str, query_cache: dict | None = None,
                      url_snippets: dict | None = None, trace: list | None = None,
                      extra_system_text: str = "",
                      tools_override: list | None = None,
                      max_rounds: int = 5) -> dict:
        """Stage 2: Independent verification of one claim using submit_claim_result tool.

        phase 2 重核场景可传 tools_override（仅 fetch_url + submit）+ max_rounds=2，
        避免重复 web_search 探索；phase 1 默认 web_search + fetch_url + submit + 5 轮。
        """
        from ai.tools import SUBMIT_CLAIM_RESULT_TOOL, TOOLS, execute_tool

        if isinstance(claim, dict):
            claim_text = claim.get("text", "")
            claim_type = claim.get("type", "fact")
            claim_importance = claim.get("importance", "一般")
            claim_polarity = claim.get("polarity", "supports_article")
        else:
            claim_text = claim
            claim_type = "fact"
            claim_importance = "一般"
            claim_polarity = "supports_article"

        user_text = f"文章背景（摘要）：{article_text[:400]}\n\n需核查的声明：{claim_text}"
        if claim_type == "narrative":
            user_text += "\n\n【注意】这是叙事类声明（文章的隐含论点/因果解释），此类声明通常难以直接证伪。若搜不到直接矛盾，fact_layer 应判'? 无法核实'。"

        system_content = get_claim_verify_prompt()
        if extra_system_text:
            system_content += "\n\n" + extra_system_text
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": [{"type": "text", "text": user_text}]},
        ]
        verify_tools = tools_override if tools_override is not None else [TOOLS[0], FETCH_URL_TOOL, SUBMIT_CLAIM_RESULT_TOOL]

        result = None
        search_log: list = []
        captured_urls: list[str] = []
        tokens: dict = {"input_tokens": 0, "output_tokens": 0}
        fetch_count = 0
        seen_queries: set[str] = set()  # 跨轮 query 跟踪：本轮 query 已被前轮搜过则停损
        _t0 = time.monotonic()

        _verify_model = self._verify_claim_model()
        for _round in range(max_rounds):
            try:
                resp = self._create_with_retry(
                    model=_verify_model,
                    messages=messages,
                    max_tokens=2000,
                    tools=verify_tools,
                    tool_choice="required" if _round == 0 else "auto",
                    temperature=0,
                    reasoning_effort="low",
                )
            except Exception:
                break

            if resp.usage:
                tokens["input_tokens"] += resp.usage.prompt_tokens or 0
                tokens["output_tokens"] += resp.usage.completion_tokens or 0

            choice = resp.choices[0]
            messages.append(choice.message)

            if not choice.message.tool_calls:
                break

            tool_msgs = []
            search_tcs = []
            fetch_tcs = []
            submit_tc = None
            for tc in choice.message.tool_calls:
                if tc.function.name == "submit_claim_result":
                    submit_tc = tc
                elif tc.function.name == "web_search":
                    search_tcs.append(tc)
                elif tc.function.name == "fetch_url":
                    fetch_tcs.append(tc)

            # A: 重复 query 停损检测——本轮任一 query 已在前轮搜过则标记，本轮处理完后跳出
            _repeat_detected = False
            if search_tcs:
                for tc in search_tcs:
                    try:
                        args = json.loads(tc.function.arguments)
                        q = args.get("query", "")
                        if q and q in seen_queries:
                            _repeat_detected = True
                            break
                    except Exception:
                        pass

            # Execute all web_search calls in this round in parallel
            if search_tcs:
                def _run_one_search(tc, _round=_round):
                    try:
                        args = json.loads(tc.function.arguments)
                        query = args.get("query", "")
                        if query_cache is not None and query in query_cache:
                            content, urls = query_cache[query]
                        else:
                            from ai.tools import _search_provider, _format_search_results
                            results = _search_provider.search(query)
                            if results and "error" in results[0]:
                                content = results[0]["error"]
                                urls = []
                                results = []
                            elif results:
                                urls = [r["url"] for r in results if r.get("url")]
                                content = _format_search_results(results)
                            else:
                                content = "未找到相关搜索结果"
                                urls = []
                                results = []
                            if url_snippets is not None:
                                for r in results:
                                    u, s = r.get("url", ""), r.get("snippet", "")
                                    if u and s:
                                        url_snippets.setdefault(u, []).append(
                                            {"query": query, "snippet": s}
                                        )
                            if query_cache is not None:
                                query_cache[query] = (content, urls)
                        return tc.id, content, urls, {"query": query, "round": _round}
                    except Exception as e:
                        return tc.id, f"搜索失败: {e}", [], None

                with ThreadPoolExecutor(max_workers=len(search_tcs)) as _pool:
                    for tc_id, content, urls, log_entry in _pool.map(_run_one_search, search_tcs):
                        tool_msgs.append({"role": "tool", "tool_call_id": tc_id, "content": content})
                        captured_urls.extend(urls)
                        if log_entry:
                            search_log.append(log_entry)
                            q = log_entry.get("query", "")
                            if q:
                                seen_queries.add(q)

            # Execute fetch_url calls serially
            # B': 预算 = "1 次成功 fetch"，失败/超时不计入
            for tc in fetch_tcs:
                if fetch_count >= 1:
                    tool_msgs.append({"role": "tool", "tool_call_id": tc.id,
                                      "content": "fetch budget exhausted"})
                    continue
                try:
                    args = json.loads(tc.function.arguments)
                    url = args.get("url", "")
                    focus = args.get("focus", claim_text)
                    from ai.tools import fetch_url as _fetch_url
                    content = _fetch_url(url, focus)
                    if not (content.startswith("fetch failed:") or content == "fetch timeout"):
                        fetch_count += 1
                        captured_urls.append(url)
                except Exception as e:
                    content = f"fetch_url 失败: {e}"
                tool_msgs.append({"role": "tool", "tool_call_id": tc.id, "content": content})

            if submit_tc:
                try:
                    result = json.loads(submit_tc.function.arguments)
                except Exception:
                    result = {}
                result["sources"] = list(dict.fromkeys(captured_urls))  # dedup, preserve order
                tool_msgs.append({"role": "tool", "tool_call_id": submit_tc.id,
                                  "content": '{"status":"ok"}'})

            messages.extend(tool_msgs)
            if result is not None:
                break
            # A: 重复 query 命中 → 跳出 search 循环，走 force-submit 兜底
            if _repeat_detected:
                break

        # 5 轮跑完仍未提交 → force-submit 兜底
        if result is None and search_log:
            try:
                messages.append({
                    "role": "user",
                    "content": "搜索轮次已用尽，请基于以上搜索结果直接调用 submit_claim_result。"
                               "如果证据不足请填 fact_layer='? 无法核实' 并在 note 里说明你看到了什么、还缺什么。",
                })
                resp = self._create_with_retry(
                    model=self._model,
                    messages=messages,
                    max_tokens=2000,
                    tools=[SUBMIT_CLAIM_RESULT_TOOL],
                    tool_choice="required",
                    temperature=0,
                    reasoning_effort="low",
                )
                if resp.usage:
                    tokens["input_tokens"] += resp.usage.prompt_tokens or 0
                    tokens["output_tokens"] += resp.usage.completion_tokens or 0
                tc = (resp.choices[0].message.tool_calls or [None])[0]
                if tc and tc.function.name == "submit_claim_result":
                    result = json.loads(tc.function.arguments)
                    result["sources"] = list(dict.fromkeys(captured_urls))
            except Exception:
                pass  # force-submit 失败时继续走原有 fallback

        if trace is not None:
            trace.append({
                "name": f"verify: {claim_text[:40]}",
                "elapsed_s": round(time.monotonic() - _t0, 2),
                "tokens": tokens,
            })

        if result is None:
            result = {"fact_layer": "? 无法核实", "effective_sources": 0,
                      "note": "核查超时或失败", "sources": []}

        # Hard enforcement: no sources → cannot be ✗ 不存在
        if result.get("fact_layer") == "✗ 不存在" and result.get("effective_sources", 0) == 0:
            result["fact_layer"] = "? 无法核实"
            result["note"] = result.get("note", "") + " [effective_sources=0，自动改判为无法核实]"

        result["claim"] = claim_text
        result["claim_type"] = claim_type
        result["claim_importance"] = claim_importance
        result["polarity"] = claim_polarity
        result["_search_log"] = search_log
        result["_tokens"] = tokens
        return result

    @staticmethod
    def _calculate_bi(claim_results: list[dict], title_logic: dict, hype: dict) -> tuple[int, str]:
        """Deterministic bi calculation using multi-dim penalty_ratio × importance weight × position decay.

        Penalty ratio: 0.0 (clean) → 1.0 (fully fake), computed by _claim_penalty_ratio.
        Importance weight: 决定性=60, 重要=35, 一般=18, 次要=7, 无关=2
        Position decay applied to claims sorted by (ratio × weight) desc: 1.0 / 0.6 / 0.4 / 0.25
        标题有问题: +15 | 夸大（第三方估算当事实）: +12 | 其他夸大: +6
        """
        def _weight(c: dict) -> int:
            imp = c.get("claim_importance")
            if imp in _WEIGHT:
                return _WEIGHT[imp]
            v = c.get("is_core_claim")
            return _WEIGHT["决定性"] if v is True else _WEIGHT["次要"]

        scored = sorted(
            [(ratio, _weight(c), c) for c in claim_results
             if (ratio := _claim_penalty_ratio(c)) > 0],
            key=lambda x: x[0] * x[1], reverse=True,
        )
        # Cap: at most 2 "决定性" claims keep full weight; extras downgrade to 重要 (35)
        _decisive_seen = 0
        _capped = []
        for ratio, weight, c in scored:
            if c.get("claim_importance") == "决定性":
                _decisive_seen += 1
                if _decisive_seen > 2:
                    weight = _WEIGHT["重要"]
            _capped.append((ratio, weight, c))
        scored = _capped
        bi = 0
        for rank, (ratio, weight, _c) in enumerate(scored):
            decay = _DECAY[rank] if rank < len(_DECAY) else _DECAY[-1]
            bi += round(ratio * weight * decay)
        if "有问题" in (title_logic.get("verdict") or ""):
            bi += 15
        if "有夸大" in (hype.get("verdict") or ""):
            bi += 12 if hype.get("type") == "第三方估算当事实" else 6
        # narrative ✓ 叙事类声明每条属实 +10（叙事论点≠客观事实）
        narrative_verified = sum(
            1 for c in claim_results
            if c.get("claim_type") == "narrative"
            and _claim_penalty_ratio(c) == 0.0
        )
        bi += narrative_verified * 10
        bi = min(bi, 100)
        return bi, _risk_level(bi)

    @staticmethod
    def _text_has_title(text: str) -> bool:
        """判断文本是否有独立标题行。
        标题特征：长度 ≤ 50 字，且不以句号/感叹号/问号结尾（否则是正文句子）。
        """
        if not text:
            return False
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        if len(lines) < 2:
            return False
        first = lines[0]
        if first.endswith(('。', '！', '？', '.', '!', '?')):
            return False
        return len(first) <= 50

    @staticmethod
    def _resolve_verdict_text(verdict_text, nature: str, bi: int, claim_results: list[dict]) -> str:
        """Override LLM verdict_text when it obviously contradicts bi/claim consensus.

        Only catches the most flagrant cases (avoid false positives):
        - bi ≤ 30 (文章属实) but verdict_text contains "并无事实依据"-类否认短语 → 覆盖
        - bi ≥ 56 (文章虚假) but verdict_text contains "完全属实"-类肯定短语 → 覆盖
        - empty verdict_text → fill from template
        Middle bi range is left to the LLM (allow nuance).
        """
        DENY_PHRASES = ("并无事实依据", "并无事实根据", "毫无事实依据", "并无根据",
                        "无任何事实", "没有事实依据", "并不存在", "并非如此")
        AFFIRM_PHRASES = ("完全属实", "完全准确", "完全正确", "完全成立",
                          "完全无误", "事实清楚", "毫无问题")

        def _build_template():
            fake_n = sum(1 for c in claim_results if _claim_is_fake(c))
            verified_n = sum(1 for c in claim_results if _claim_is_verified(c))
            uncertain_n = sum(1 for c in claim_results if _claim_is_uncertain(c))
            parts = []
            if fake_n:
                parts.append(f"{fake_n} 项不成立")
            if verified_n:
                parts.append(f"{verified_n} 项属实")
            if uncertain_n:
                parts.append(f"{uncertain_n} 项暂无法核实")
            stance = {
                "事实错误": "文章核心事实存在重大问题。",
                "局部失实": "文章部分内容失实。",
                "属实": "文章核心事实成立。",
                "基本属实": "文章核心事实大体成立，细节略有出入。",
                "夸大渲染": "文章事实基本成立但表述存在夸大。",
                "真实但离谱": "文章内容真实但表述荒诞。",
                "标题党": "标题与正文事实存在落差。",
                "断章取义": "文章存在断章取义。",
                "逻辑混乱": "文章推理链存在断裂。",
            }.get(nature, "建议进一步核实。")
            prefix = "经核查，" + ("、".join(parts) + "。" if parts else "")
            return prefix + stance

        if not verdict_text:
            return _build_template()
        if bi <= 30 and any(p in verdict_text for p in DENY_PHRASES):
            return _build_template()
        if bi >= 56 and any(p in verdict_text for p in AFFIRM_PHRASES):
            return _build_template()
        return verdict_text

    @staticmethod
    def _resolve_nature(ai_nature, bi: int, claim_results: list[dict], title_logic: dict, hype: dict) -> str:
        """Cross-validate LLM-given bullshit_nature against deterministic signals.

        LLM may return a nature that contradicts the actual bi / claim_verification data
        (e.g. nature="属实" while all claims are ✗ and bi=100). When that happens we
        override with the deterministic value computed from the same data the bi uses,
        guaranteeing header internal consistency.
        """
        deterministic = _PlanExecuteMixin._nature_from_inputs(bi, claim_results, title_logic, hype)
        if not ai_nature:
            return deterministic

        positive = {"属实", "基本属实", "真实但离谱"}
        if ai_nature in positive:
            if any(_claim_is_fake(c) for c in claim_results) or bi >= 56:
                return deterministic
        return ai_nature

    @staticmethod
    def _nature_from_inputs(bi: int, claim_results: list[dict], title_logic: dict, hype: dict) -> str:
        """Determine bullshit_nature from already-computed plan-execute inputs.

        Supports both multi-dim (fact_layer) and legacy (verdict) claim formats.
        Polarity-aware via _claim_is_fake / _claim_is_verified / _claim_is_uncertain.
        """
        fake_count = sum(1 for c in claim_results if _claim_is_fake(c))
        verified_count = sum(1 for c in claim_results if _claim_is_verified(c))
        has_uncertain = any(_claim_is_uncertain(c) for c in claim_results)

        if fake_count > 0:
            if verified_count >= 2 * fake_count:
                return "基本属实"
            if verified_count > fake_count:
                return "局部失实"
            return "事实错误"
        tl_verdict = title_logic.get("verdict") or ""
        if "有问题" in tl_verdict and "无标题" not in tl_verdict:
            return "标题党"
        if "有夸大" in (hype.get("verdict") or ""):
            return "夸大渲染"
        if has_uncertain:
            uncertain_count = sum(1 for c in claim_results if _claim_is_uncertain(c))
            has_decisive_uncertain = any(
                _claim_is_uncertain(c) and c.get("claim_importance") == "决定性"
                for c in claim_results
            )
            if has_decisive_uncertain or uncertain_count >= max(1, verified_count):
                return "局部失实"
        if bi <= 5:
            return "属实"
        return "基本属实"

    @staticmethod
    def _calculate_radar(claim_results: list[dict], title_logic: dict, hype: dict) -> dict:
        n = max(len(claim_results), 1)

        fake = sum(1 for c in claim_results if _claim_is_fake(c))
        unverified = sum(1 for c in claim_results if _claim_is_uncertain(c))
        verified = n - fake - unverified

        # logic_consistency: 5=all verified, penalize fake/unverified/title issues
        lc = max(1, min(5, 5 - fake * 2 - unverified - (1 if "有问题" in (title_logic.get("verdict") or "") else 0)))

        # source_authority: avg effective_sources across claims (1-5)
        avg_eff = sum(c.get("effective_sources", 0) for c in claim_results) / n
        sa = max(1, min(5, round(avg_eff)))

        # agitation_level: hype check (1=calm, 5=very hyped)
        if "有夸大" in (hype.get("verdict") or ""):
            al = 4 if hype.get("type") == "绝对化表述" else 3
        else:
            al = 2

        # search_match: proportion of verified claims (1-5)
        sm = max(1, min(5, round(verified / n * 4) + 1))

        return {"logic_consistency": lc, "source_authority": sa, "agitation_level": al, "search_match": sm}

    def _check_title_logic(self, article_text: str, claim_results: list[dict],
                            trace: list | None = None) -> dict:
        """Stage 3a: Title logic check (tool_use for reliable structured output)."""
        from ai.tools import SUBMIT_TITLE_LOGIC_TOOL
        clean = [{k: v for k, v in r.items() if not k.startswith("_")} for r in claim_results]
        _t0 = time.monotonic()
        resp = None
        try:
            resp = self._create_with_retry(
                model=self._model,
                messages=[
                    {"role": "system", "content": get_title_logic_prompt()},
                    {"role": "user", "content": [{"type": "text", "text":
                        f"今天日期：{_current_date}\n\n文章内容（摘要）：{article_text[:1000]}\n\n声明核查结果：{json.dumps(clean, ensure_ascii=False)}"}]},
                ],
                max_tokens=4000,
                tools=[SUBMIT_TITLE_LOGIC_TOOL],
                tool_choice={"type": "function", "function": {"name": "submit_title_logic"}},
            )
            tc = (resp.choices[0].message.tool_calls or [None])[0]
            result = json.loads(tc.function.arguments) if tc else None
        except Exception as e:
            import logging
            logging.warning("_check_title_logic failed: %s", repr(e))
            result = None
        if result is None:
            result = {"verdict": "无法判断", "reason": "核查失败"}
        # Normalize verdict to canonical values (model sometimes ignores enum)
        _TITLE_CANONICAL = {"有问题", "无问题", "无标题", "不适用", "无法判断"}
        if result.get("verdict") not in _TITLE_CANONICAL:
            v = result.get("verdict", "")
            result["verdict"] = "有问题" if any(
                kw in v for kw in ["问题", "错误", "不成立", "谬误", "夸大", "误导"]
            ) else "无法判断"
        if trace is not None:
            usage = resp.usage if resp else None
            trace.append({"name": "title_logic_check", "response": str(result)[:200],
                          "tokens": {"input": usage.prompt_tokens if usage else 0,
                                     "output": usage.completion_tokens if usage else 0},
                          "elapsed_s": round(time.monotonic() - _t0, 2)})
        return result

    def _check_hype(self, article_text: str, trace: list | None = None) -> dict:
        """Stage 3b: Hype/exaggeration check (tool_use for reliable structured output)."""
        import logging
        from ai.tools import SUBMIT_HYPE_TOOL
        _t0 = time.monotonic()
        resp = None
        _err = None
        try:
            resp = self._create_with_retry(
                model=self._model,
                messages=[
                    {"role": "system", "content": get_hype_check_prompt()},
                    {"role": "user", "content": [{"type": "text", "text": f"今天日期：{_current_date}\n\n文章内容：{article_text[:1500]}"}]},
                ],
                max_tokens=4000,
                tools=[SUBMIT_HYPE_TOOL],
                tool_choice={"type": "function", "function": {"name": "submit_hype_check"}},
            )
            tc = (resp.choices[0].message.tool_calls or [None])[0]
            result = json.loads(tc.function.arguments) if tc else None
        except Exception as e:
            _err = repr(e)
            logging.warning("_check_hype failed: %s", _err)
            result = None
        if result is None:
            result = {"verdict": "无法判断", "type": "无", "reason": f"核查失败: {_err}" if _err else "核查失败"}
        # Normalize verdict to canonical values
        _HYPE_CANONICAL = {"有夸大", "无夸大", "无法判断"}
        if result.get("verdict") not in _HYPE_CANONICAL:
            v = result.get("verdict", "")
            result["verdict"] = "有夸大" if any(
                kw in v for kw in ["夸大", "渲染", "虚报", "过度", "绝对"]
            ) else "无法判断"
        if trace is not None:
            usage = resp.usage if resp else None
            trace.append({"name": "hype_check", "response": str(result)[:200],
                          "tokens": {"input": usage.prompt_tokens if usage else 0,
                                     "output": usage.completion_tokens if usage else 0},
                          "elapsed_s": round(time.monotonic() - _t0, 2)})
        return result

    def _build_evidence_pool(self, url_snippets: dict, max_total: int = 4000, max_per_url: int = 600) -> str:
        """从 url_snippets 构造证据池文本，按 URL 频次排序，限制总长和单 URL 长度。"""
        import hashlib
        if not url_snippets:
            return ""
        sorted_urls = sorted(url_snippets.keys(), key=lambda u: -len(url_snippets[u]))
        lines = []
        total_len = 0
        seen_hashes: set[str] = set()
        for url in sorted_urls:
            if total_len >= max_total:
                break
            url_block = [f"- {url}"]
            url_len = len(url) + 2
            for entry in url_snippets[url]:
                snippet = entry["snippet"].strip()
                query = entry["query"]
                h = hashlib.md5(snippet.encode("utf-8")).hexdigest()
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)
                prefix = f'  片段（来自 query "{query}"）：'
                line = prefix + snippet
                if url_len + len(line) > max_per_url:
                    remaining = max_per_url - url_len - len(prefix) - 5
                    if remaining > 50:
                        line = prefix + snippet[:remaining] + "..."
                        url_block.append(line)
                        url_len = max_per_url
                    break
                url_block.append(line)
                url_len += len(line) + 1
            block_text = "\n".join(url_block)
            if total_len + len(block_text) > max_total:
                break
            lines.append(block_text)
            total_len += len(block_text) + 1
        if not lines:
            return ""
        return (
            "【Phase 2 重核场景 — 其他 claim 已搜证据池】\n"
            "phase 1 已对本文相关 claim 做过 web_search，下列 URL + snippet 是已积累的证据。\n"
            "**本轮你只能调用 fetch_url 或 submit_claim_result，不能再 web_search**——\n"
            "请直接基于 snippet 判断；如需更多细节，从下列 URL 选最相关的 1 个 fetch_url 读取，"
            "然后立即 submit_claim_result。请在 2 轮内完成。\n\n"
            + "\n\n".join(lines)
        )

    _CONSISTENCY_CHECK_TOOL = {
        "type": "function",
        "function": {
            "name": "submit_inconsistencies",
            "description": "提交需要重核的 ✗ 不存在 claim 索引列表（仅当其结论与其他 ✓ 存在 claim 在同一对象上矛盾时）",
            "parameters": {
                "type": "object",
                "required": ["reverify"],
                "properties": {
                    "reverify": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "需重核的 claim 索引列表；无矛盾返回 []",
                    },
                    "reason": {
                        "type": "string",
                        "description": "简要说明判定理由（≤80 字）",
                    },
                },
            },
        },
    }

    def _run_consistency_check(self, claim_results: list[dict]) -> list[int]:
        """轻量一致性检查：仅当 verdict 混合（既有 ✓ 又有 ✗）时触发。
        返回需重核的 ✗ claim 索引列表；无矛盾或不触发返回 []。
        """
        has_exists = any(r.get("fact_layer") == "✓ 存在" for r in claim_results)
        has_not_exists = any(r.get("fact_layer") == "✗ 不存在" for r in claim_results)
        if not (has_exists and has_not_exists):
            return []

        # 构造简洁的 claim 摘要供模型比对
        summary_lines = []
        for i, r in enumerate(claim_results):
            claim = (r.get("claim") or "")[:200]
            note = (r.get("note") or "")[:300]
            summary_lines.append(
                f"[{i}] verdict={r.get('verdict','?')} | fact_layer={r.get('fact_layer','?')}\n"
                f"    claim: {claim}\n    note: {note}"
            )
        summary = "\n\n".join(summary_lines)

        system_prompt = (
            "你是事实核查的一致性审查员。下面是同一篇文章拆出的若干 claim 的核查结论。\n"
            "任务：检查是否存在 ✗ 不存在 claim 与其他 ✓ 存在 claim 在**同一对象**上互相矛盾的情况。\n"
            "典型矛盾：claim A 判 ✓（'X 物体有 Y 特征'），claim B 判 ✗（声明同一 X 物体没有 Y 特征）。\n"
            "或：claim B 的 note 暗示 source 谈论的对象其实跟 claim A 是同一个，但 B 错认为是别的对象。\n"
            "仅返回需重核的 ✗ claim 索引；如所有 ✗ 都是真的不存在、与 ✓ 不冲突，返回空列表。"
        )

        try:
            resp = self._create_with_retry(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": summary},
                ],
                max_tokens=4000,
                tools=[self._CONSISTENCY_CHECK_TOOL],
                tool_choice="required",
                temperature=0,
                reasoning_effort="low",
            )
            tc = (resp.choices[0].message.tool_calls or [None])[0]
            if tc and tc.function.name == "submit_inconsistencies":
                args = json.loads(tc.function.arguments)
                indices = args.get("reverify", [])
                # 防御：过滤非法索引、确保确实是 ✗ 不存在
                return [
                    int(i) for i in indices
                    if isinstance(i, int)
                    and 0 <= i < len(claim_results)
                    and claim_results[i].get("fact_layer") == "✗ 不存在"
                ]
        except Exception:
            return []
        return []

    def _run_phase2_retry(
        self,
        claim_results: list[dict],
        article_text: str,
        url_snippets: dict,
        query_cache: dict,
        trace: list | None = None,
    ) -> list[dict]:
        """phase 2: 串行重核 ? 无法核实 + 被一致性检查标记矛盾的 ✗ 不存在 claim，注入 evidence pool。"""
        unverified_indices = [
            i for i, r in enumerate(claim_results) if r.get("fact_layer") == "? 无法核实"
        ]
        # 一致性检查：仅在 verdict 混合时触发，返回需重核的 ✗ claim 索引
        inconsistent_indices = self._run_consistency_check(claim_results)
        retry_indices = unverified_indices + inconsistent_indices
        if not retry_indices:
            return claim_results
        pool_text = self._build_evidence_pool(url_snippets)
        if not pool_text:
            return claim_results
        # phase 2 工具限制：禁用 web_search，强制依赖 evidence pool + fetch_url；轮数限 2
        from ai.tools import SUBMIT_CLAIM_RESULT_TOOL
        _phase2_tools = [FETCH_URL_TOOL, SUBMIT_CLAIM_RESULT_TOOL]
        results = list(claim_results)
        for i in retry_indices:
            original = results[i]
            claim = {
                "text": original.get("claim", ""),
                "type": original.get("claim_type", "fact"),
                "importance": original.get("claim_importance", "一般"),
            }
            try:
                new_result = self._verify_claim(
                    claim,
                    article_text,
                    query_cache=query_cache,
                    url_snippets=url_snippets,
                    trace=trace,
                    extra_system_text=pool_text,
                    tools_override=_phase2_tools,
                    max_rounds=2,
                )
                # 仅当 fact_layer 实际改变时替换：
                # ? → ✓/✗ 视为查清；✗ → ✓/? 视为撤回过度自信的错判；同向无变化则保留原结果。
                if new_result.get("fact_layer") != original.get("fact_layer"):
                    results[i] = new_result
            except Exception:
                pass  # 失败保留原结果
        return results

    def analyze_article_plan_execute(self, text: str, images: list[str] | None = None) -> tuple[dict, dict]:
        """Plan-and-Execute analysis pipeline.
        Planner → parallel verify_claim Executor → Re-planner (max 2 rounds) → submit_verdict → Python bi.
        """
        from ai.debug_log import make_entry, set_result, write_entry
        from ai.providers.openai_compat import _error_result, SearchUnavailableError

        _dbg = make_entry("analyze_staged", {"text_len": len(text), "image_count": len(images or [])})
        try:
            from config.manager import load as _load_cfg
            cfg = _load_cfg()
            max_workers = cfg.get("staged_max_workers", 5)
            max_replan = cfg.get("plan_execute_max_replan", 2)

            total = {"input_tokens": 0, "output_tokens": 0}
            query_cache: dict = {}
            url_snippets: dict = {}
            from ai.tools import reset_url_cache
            reset_url_cache()  # 每次 analyze 开始时清空 url_cache，确保 cache 随 analyze 生命周期
            all_verify_results: list[dict] = []
            all_search_log: list[dict] = []
            title_logic: dict = {}
            hype_check: dict = {}
            submit_args: dict | None = None

            # Build user message
            article_snippet = text[:10000]
            if images:
                user_content = self._image_content(
                    images, f"请分析以下内容内容（如有图片请一并参考）：\n\n{article_snippet}"
                )
            else:
                user_content = [{"type": "text", "text": f"请分析以下内容：\n\n{article_snippet}"}]

            messages = [
                {"role": "system", "content": get_planner_prompt(self._tone)},
                {"role": "user", "content": user_content},
            ]

            for round_idx in range(max_replan + 1):
                is_planner = (round_idx == 0)
                current_tools = PLANNER_TOOLS if is_planner else PLAN_EXECUTE_TOOLS

                try:
                    from ui.loading_overlay import update_stage
                    update_stage("提取核查声明" if is_planner else "综合分析中")
                except Exception:
                    pass

                resp = self._create_with_retry(
                    model=self._model,
                    messages=messages,
                    tools=current_tools,
                    tool_choice="required" if is_planner else "auto",
                    max_tokens=8192,
                    temperature=0,
                    reasoning_effort="low",
                )
                if resp.usage:
                    total["input_tokens"] += resp.usage.prompt_tokens or 0
                    total["output_tokens"] += resp.usage.completion_tokens or 0

                choice = resp.choices[0]
                messages.append(choice.message)

                if not choice.message.tool_calls:
                    # Re-planner gave up without submit_verdict — break and use fallback
                    break

                # Separate tool calls by type
                verify_tcs, other_tcs, submit_tc = [], [], None
                _narrative_tc = None
                for tc in choice.message.tool_calls:
                    name = tc.function.name
                    if name == "submit_verdict":
                        submit_tc = tc
                    elif name == "verify_claim":
                        verify_tcs.append(tc)
                    elif name == "identify_narrative":
                        _narrative_tc = tc
                    else:
                        other_tcs.append(tc)

                # If planner called identify_narrative with should_verify=true,
                # add it to the parallel verify queue (Python will run _verify_claim for it)
                if _narrative_tc:
                    try:
                        _n = json.loads(_narrative_tc.function.arguments)
                        if _n.get("should_verify") and _n.get("article_conclusion"):
                            verify_tcs.append(_narrative_tc)  # handled in _run_verify below
                        else:
                            messages.append({"role": "tool", "tool_call_id": _narrative_tc.id,
                                             "content": '{"status": "no_verify_needed"}'})
                    except Exception:
                        messages.append({"role": "tool", "tool_call_id": _narrative_tc.id,
                                         "content": '{"status": "parse_error"}'})

                # 去重：覆盖两类重复
                # (a) 跨轮重复：与已 verify 的 claim 实质同义 → 复用已有结果作为 tool 响应
                # (b) 同批次内重复：本批次内多个 verify_claim 互相重复 → 只 verify 第一个，
                #     其余 tc 在 verify 完成后用 canonical 结果回填 tool 响应
                # 必须给每个 tc 都填一条 tool 响应，否则 OpenAI 协议错误。
                duplicate_to_canonical_tc_id: dict = {}  # 同批次重复 tc.id -> canonical tc.id
                canonical_claims = [er.get("claim", "") for er in all_verify_results]
                existing_pool_size = len(canonical_claims)
                if verify_tcs:
                    unique_tcs = []
                    for tc in verify_tcs:
                        try:
                            args = json.loads(tc.function.arguments)
                            if tc.function.name == "identify_narrative":
                                new_claim = args.get("article_conclusion", "")
                            else:
                                new_claim = args.get("claim", "")
                        except Exception:
                            unique_tcs.append(tc)
                            canonical_claims.append("")  # 占位
                            continue
                        dup_idx = None
                        for j, ec in enumerate(canonical_claims):
                            if _is_duplicate_claim(new_claim, [ec]):
                                dup_idx = j
                                break
                        if dup_idx is None:
                            unique_tcs.append(tc)
                            canonical_claims.append(new_claim)
                        elif dup_idx < existing_pool_size:
                            # 跨轮重复：已有结果，直接回填
                            existing = all_verify_results[dup_idx]
                            clean = {k: v for k, v in existing.items() if not k.startswith("_")}
                            messages.append({
                                "role": "tool", "tool_call_id": tc.id,
                                "content": json.dumps(clean, ensure_ascii=False),
                            })
                        else:
                            # 同批次重复：标记，待 canonical verify 完成后回填
                            canonical_tc = unique_tcs[dup_idx - existing_pool_size]
                            duplicate_to_canonical_tc_id[tc.id] = canonical_tc.id
                    verify_tcs = unique_tcs

                # Run verify_claims in parallel
                if verify_tcs:
                    try:
                        from ui.loading_overlay import update_stage
                        update_stage("核查声明")
                    except Exception:
                        pass

                    def _run_verify(tc, _text=text, _cache=query_cache,
                                   _url_snippets=url_snippets, _stages=_dbg["stages"]):
                        args = json.loads(tc.function.arguments)
                        if tc.function.name == "identify_narrative":
                            conclusion = args.get("article_conclusion", "")
                            assumption = args.get("key_assumption", "无")
                            claim_text = (f"{conclusion}（前提：{assumption}）"
                                          if assumption and assumption != "无" else conclusion)
                            claim_obj = {"text": claim_text, "type": "narrative", "importance": "重要"}
                        else:
                            claim_text = args.get("claim", "")
                            quoted_from = args.get("quoted_from", "")
                            if quoted_from:
                                claim_text = f"{claim_text}（此处为引用{quoted_from}的话，核查该引用是否属实）"
                            claim_obj = {
                                "text": claim_text,
                                "type": args.get("claim_type", "fact"),
                                "importance": args.get("claim_importance", "一般"),
                                "polarity": args.get("polarity", "supports_article"),
                            }
                        result = self._verify_claim(claim_obj, _text, _cache, _url_snippets, _stages)
                        tokens = result.pop("_tokens", {})
                        slog = result.pop("_search_log", []) or []
                        return tc, result, tokens, slog

                    with ThreadPoolExecutor(max_workers=min(len(verify_tcs), max_workers)) as ex:
                        verify_outcomes = list(ex.map(_run_verify, verify_tcs))

                    canonical_results_by_tc_id: dict = {}
                    for tc, result, tokens, slog in verify_outcomes:
                        all_search_log.extend(slog)
                        all_verify_results.append(result)
                        total["input_tokens"] += tokens.get("input_tokens", 0)
                        total["output_tokens"] += tokens.get("output_tokens", 0)
                        clean = {k: v for k, v in result.items() if not k.startswith("_")}
                        messages.append({"role": "tool", "tool_call_id": tc.id,
                                         "content": json.dumps(clean, ensure_ascii=False)})
                        canonical_results_by_tc_id[tc.id] = clean

                    # 同批次重复 tc 用 canonical 结果回填 tool 响应
                    for dup_tc_id, canon_tc_id in duplicate_to_canonical_tc_id.items():
                        if canon_tc_id in canonical_results_by_tc_id:
                            messages.append({
                                "role": "tool", "tool_call_id": dup_tc_id,
                                "content": json.dumps(canonical_results_by_tc_id[canon_tc_id], ensure_ascii=False),
                            })

                # Run other tools (analyze_title_logic, analyze_hype)
                # For image-only inputs text is "", fall back to concatenated claims as context
                _ctx_text = text or " | ".join(r.get("claim", "") for r in all_verify_results)
                for tc in other_tcs:
                    name = tc.function.name
                    if name == "analyze_title_logic":
                        # 若内容无可识别标题（首行超长或仅一行），跳过检查，避免误判标题党
                        if not self._text_has_title(text):
                            title_logic = {"verdict": "无标题", "reason": "内容无独立标题行"}
                        else:
                            title_logic = self._check_title_logic(_ctx_text, all_verify_results, _dbg["stages"])
                        messages.append({"role": "tool", "tool_call_id": tc.id,
                                         "content": json.dumps(title_logic, ensure_ascii=False)})
                    elif name == "analyze_hype":
                        hype_check = self._check_hype(_ctx_text, _dbg["stages"])
                        messages.append({"role": "tool", "tool_call_id": tc.id,
                                         "content": json.dumps(hype_check, ensure_ascii=False)})
                    else:
                        messages.append({"role": "tool", "tool_call_id": tc.id,
                                         "content": '{"error": "unknown tool"}'})

                # submit_verdict terminates the loop (checked AFTER other tools so same-round
                # analyze_title_logic / analyze_hype calls are executed first)
                if submit_tc:
                    try:
                        submit_args = json.loads(submit_tc.function.arguments)
                    except Exception:
                        submit_args = {}
                    messages.append({"role": "tool", "tool_call_id": submit_tc.id, "content": '{"status": "ok"}'})
                    break

                # Switch system prompt to Re-planner after first round
                if is_planner:
                    messages[0] = {"role": "system", "content": get_replanner_prompt(self._tone)}

            # Force-submit fallback：re-planner 没主动调 submit_verdict 时，强制 1 次
            # tool_choice 锁死 submit_verdict 的调用，让模型综合写出 verdict 文本，
            # 避免 UI 上 header.verdict 是空字符串。
            if submit_args is None:
                try:
                    messages.append({
                        "role": "user",
                        "content": (
                            "Re-planner 轮次已用尽，但你尚未调用 submit_verdict。"
                            "请基于已完成的所有 claim 核查结果，立即调用 submit_verdict，"
                            "综合写出 verdict_text、one_line_summary、toxic_review、bullshit_nature。"
                            "即使部分 claim 是 ? 无法核实，也请综合现有信息给结论"
                            "（如'多数事实属实但 X 未能核实'）。"
                        ),
                    })
                    resp = self._create_with_retry(
                        model=self._model,
                        messages=messages,
                        max_tokens=2000,
                        tools=PLAN_EXECUTE_TOOLS,
                        tool_choice={"type": "function", "function": {"name": "submit_verdict"}},
                        temperature=0,
                        reasoning_effort="low",
                    )
                    if resp.usage:
                        total["input_tokens"] += resp.usage.prompt_tokens or 0
                        total["output_tokens"] += resp.usage.completion_tokens or 0
                    _tc = (resp.choices[0].message.tool_calls or [None])[0]
                    if _tc and _tc.function.name == "submit_verdict":
                        submit_args = json.loads(_tc.function.arguments)
                except Exception:
                    pass  # 失败回落到下方硬编码 fallback

            # Fallback: 即便 force-submit 也失败，仍走硬编码兜底
            if submit_args is None:
                submit_args = {
                    "investigation_report": {
                        "title_logic_check": title_logic,
                        "hype_check": hype_check,
                        "caveats": [],
                    },
                    "one_line_summary": "",
                    "toxic_review": "",
                    "verdict_text": "",
                }

            # Extract investigation_report fields
            inv = submit_args.get("investigation_report") or {}
            if not title_logic and inv.get("title_logic_check"):
                title_logic = inv["title_logic_check"]
                # Normalize verdict when coming from re-planner free-form output
                _TITLE_CANONICAL = {"有问题", "无问题", "无标题", "不适用", "无法判断"}
                v = (title_logic.get("verdict") or "") if isinstance(title_logic, dict) else ""
                if v and v not in _TITLE_CANONICAL:
                    title_logic = {**title_logic, "verdict": "有问题" if any(
                        kw in v for kw in ["问题", "错误", "不成立", "谬误", "夸大", "误导"]
                    ) else "无法判断"}
            if not hype_check and inv.get("hype_check"):
                hype_check = inv["hype_check"]
                # Normalize verdict when coming from re-planner free-form output
                _HYPE_CANONICAL = {"有夸大", "无夸大", "无法判断"}
                v = (hype_check.get("verdict") or "") if isinstance(hype_check, dict) else ""
                if v and v not in _HYPE_CANONICAL:
                    hype_check = {**hype_check, "verdict": "有夸大" if any(
                        kw in v for kw in ["夸大", "渲染", "虚报", "过度", "绝对"]
                    ) else "无法判断"}
            # Guarantee hype_check always has a verdict (re-planner may skip analyze_hype)
            if not hype_check.get("verdict"):
                # 兜底 _ctx_text：模型不调任何工具时上方未定义此变量
                _fallback_ctx = text or " | ".join(r.get("claim", "") for r in all_verify_results)
                hype_check = self._check_hype(_fallback_ctx, _dbg["stages"])

            # phase 2 重核（仅"? 无法核实" claim 触发）
            if any(r.get("fact_layer") == "? 无法核实" for r in all_verify_results):
                all_verify_results = self._run_phase2_retry(
                    all_verify_results, text, url_snippets, query_cache, trace=_dbg.get("stages")
                )

            # Deterministic bi calculation — always use Python-tracked results (authoritative 4-layer data)
            cv = [
                {k: v for k, v in r.items() if not k.startswith("_")}
                for r in all_verify_results
            ]
            bi, risk_level = self._calculate_bi(cv, title_logic, hype_check)
            radar = self._calculate_radar(cv, title_logic, hype_check)

            ai_nature = submit_args.get("bullshit_nature")
            final_nature = self._resolve_nature(ai_nature, bi, cv, title_logic, hype_check)
            final_verdict = self._resolve_verdict_text(
                submit_args.get("verdict_text", ""), final_nature, bi, cv
            )

            result = normalize_result({
                "_mode": "analyze",
                "header": {
                    "bullshit_index": bi,
                    "bullshit_nature": final_nature,
                    "risk_level": risk_level,
                    "verdict": final_verdict,
                    "truth_label": f"{100 - bi}% 属实" if isinstance(bi, int) else "分析中",
                },
                "claim_verification": [
                    {**c, "verdict": c["verdict"]} if "verdict" in c
                    else {**c, "verdict": c.get("fact_layer", "? 无法核实")}
                    for c in cv
                ],
                "investigation_report": {
                    "title_logic_check": title_logic,
                    "hype_check": hype_check,
                    "caveats": inv.get("caveats", []),
                },
                "one_line_summary": submit_args.get("one_line_summary", ""),
                "toxic_review": submit_args.get("toxic_review", ""),
                "radar_chart": radar,
                "flaw_list": submit_args.get("flaw_list") or [],
            })
            result["_search_log"] = all_search_log
            result["_token_usage"] = total
            result["_path"] = "plan_execute"
            result["_mode"] = "analyze"

            token_dict = {"model": self._model, "input": total["input_tokens"], "output": total["output_tokens"]}
            _dbg["path"] = "plan_execute"
            set_result(_dbg, result, token_dict)
            return result, token_dict

        except SearchUnavailableError as e:
            _dbg["error"] = str(e)
            return _error_result(str(e)), self._zero_tokens()
        except Exception as e:
            _dbg["error"] = str(e)
            return _error_result(f"{type(e).__name__}: {e}\n{traceback.format_exc()}"), self._zero_tokens()
        finally:
            write_entry(_dbg)
