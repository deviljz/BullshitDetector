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
from ai.json_utils import parse_json, normalize_result
from ai.tools import PLAN_EXECUTE_TOOLS, PLANNER_TOOLS

# _NO_THINKING imported from host module to avoid duplication
_NO_THINKING = {"reasoning_effort": "none"}

_DECAY = [1.0, 0.6, 0.4, 0.25]
_WEIGHT = {"决定性": 60, "重要": 35, "一般": 18, "次要": 7, "无关": 2}


def _claim_penalty_ratio(r: dict) -> float:
    """Map a claim result to a 0.0–1.0 penalty score.

    Supports both new multi-dim format (fact_layer) and legacy (verdict).
    """
    if "fact_layer" not in r:
        # Legacy format: single verdict string
        verdict = r.get("verdict", "")
        if "✗" in verdict:
            return 1.0
        if "?" in verdict:
            return 0.25
        return 0.0
    # Timeout/failure is more suspicious than ordinary "无法核实"
    if "核查超时或失败" in (r.get("note") or ""):
        return 0.5
    fact = r.get("fact_layer", "? 无法核实")
    if fact == "○ 非事实声明":
        return 0.0
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

    def _verify_claim(self, claim: str | dict, article_text: str, query_cache: dict | None = None,
                      trace: list | None = None) -> dict:
        """Stage 2: Independent verification of one claim using submit_claim_result tool."""
        from ai.tools import SUBMIT_CLAIM_RESULT_TOOL, TOOLS, execute_tool

        if isinstance(claim, dict):
            claim_text = claim.get("text", "")
            claim_type = claim.get("type", "fact")
            claim_importance = claim.get("importance", "一般")
        else:
            claim_text = claim
            claim_type = "fact"
            claim_importance = "一般"

        user_text = f"文章背景（摘要）：{article_text[:400]}\n\n需核查的声明：{claim_text}"
        if claim_type == "narrative":
            user_text += "\n\n【注意】这是叙事类声明（文章的隐含论点/因果解释），此类声明通常难以直接证伪。若搜不到直接矛盾，fact_layer 应判'? 无法核实'。"

        messages = [
            {"role": "system", "content": get_claim_verify_prompt()},
            {"role": "user", "content": [{"type": "text", "text": user_text}]},
        ]
        verify_tools = [TOOLS[0], SUBMIT_CLAIM_RESULT_TOOL]  # web_search + submit

        result = None
        search_log: list = []
        tokens: dict = {"input_tokens": 0, "output_tokens": 0}
        _t0 = time.monotonic()

        for _round in range(5):
            try:
                resp = self._create_with_retry(
                    model=self._model,
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
            submit_tc = None
            for tc in choice.message.tool_calls:
                if tc.function.name == "submit_claim_result":
                    submit_tc = tc
                elif tc.function.name == "web_search":
                    search_tcs.append(tc)

            # Execute all web_search calls in this round in parallel
            if search_tcs:
                def _run_one_search(tc, _round=_round):
                    try:
                        args = json.loads(tc.function.arguments)
                        query = args.get("query", "")
                        if query_cache is not None and query in query_cache:
                            content = query_cache[query]
                        else:
                            content = execute_tool("web_search", args)
                            if query_cache is not None:
                                query_cache[query] = content
                        return tc.id, content, {"query": query, "round": _round}
                    except Exception as e:
                        return tc.id, f"搜索失败: {e}", None

                with ThreadPoolExecutor(max_workers=len(search_tcs)) as _pool:
                    for tc_id, content, log_entry in _pool.map(_run_one_search, search_tcs):
                        tool_msgs.append({"role": "tool", "tool_call_id": tc_id, "content": content})
                        if log_entry:
                            search_log.append(log_entry)

            if submit_tc:
                try:
                    result = json.loads(submit_tc.function.arguments)
                except Exception:
                    result = {}
                tool_msgs.append({"role": "tool", "tool_call_id": submit_tc.id,
                                  "content": '{"status":"ok"}'})

            messages.extend(tool_msgs)
            if result is not None:
                break

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
        bi = 0
        for rank, (ratio, weight, _c) in enumerate(scored):
            decay = _DECAY[rank] if rank < len(_DECAY) else _DECAY[-1]
            bi += round(ratio * weight * decay)
        if "有问题" in (title_logic.get("verdict") or ""):
            bi += 15
        if "有夸大" in (hype.get("verdict") or ""):
            bi += 12 if hype.get("type") == "第三方估算当事实" else 6
        bi = min(bi, 100)
        risk = ("🚨 极度危险" if bi > 80 else
                "🔶 高度警惕" if bi > 55 else
                "⚠️ 有所存疑" if bi > 30 else
                "✅ 基本可信")
        return bi, risk

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
    def _nature_from_inputs(bi: int, claim_results: list[dict], title_logic: dict, hype: dict) -> str:
        """Determine bullshit_nature from already-computed plan-execute inputs.

        Supports both multi-dim (fact_layer) and legacy (verdict) claim formats.
        """
        def _is_fake(c: dict) -> bool:
            if "fact_layer" in c:
                return c.get("fact_layer") == "✗ 不存在"
            return "✗" in c.get("verdict", "")

        def _is_verified(c: dict) -> bool:
            if "fact_layer" in c:
                return c.get("fact_layer") == "✓ 存在"
            return "✓" in c.get("verdict", "")

        def _is_uncertain(c: dict) -> bool:
            if "fact_layer" in c:
                return c.get("fact_layer") == "? 无法核实"
            return "?" in c.get("verdict", "")

        fake_count = sum(1 for c in claim_results if _is_fake(c))
        verified_count = sum(1 for c in claim_results if _is_verified(c))
        has_uncertain = any(_is_uncertain(c) for c in claim_results)

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
            return "局部失实"
        return "基本属实"

    @staticmethod
    def _calculate_radar(claim_results: list[dict], title_logic: dict, hype: dict) -> dict:
        n = max(len(claim_results), 1)

        def _is_fake(c: dict) -> bool:
            if "fact_layer" in c:
                return c.get("fact_layer") == "✗ 不存在"
            return "✗" in c.get("verdict", "")

        def _is_uncertain(c: dict) -> bool:
            if "fact_layer" in c:
                return c.get("fact_layer") == "? 无法核实"
            return "?" in c.get("verdict", "")

        fake = sum(1 for c in claim_results if _is_fake(c))
        unverified = sum(1 for c in claim_results if _is_uncertain(c))
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
                max_tokens=300,
                tools=[SUBMIT_TITLE_LOGIC_TOOL],
                tool_choice={"type": "required"},
                **_NO_THINKING,
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
                max_tokens=300,
                tools=[SUBMIT_HYPE_TOOL],
                tool_choice={"type": "required"},
                **_NO_THINKING,
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
            all_verify_results: list[dict] = []
            all_search_log: list[dict] = []
            title_logic: dict = {}
            hype_check: dict = {}
            submit_args: dict | None = None

            # Build user message
            article_snippet = text[:10000]
            if images:
                user_content = self._image_content(
                    images, f"请分析以下文章内容（如有图片请一并参考）：\n\n{article_snippet}"
                )
            else:
                user_content = [{"type": "text", "text": f"请分析以下文章：\n\n{article_snippet}"}]

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
                for tc in choice.message.tool_calls:
                    name = tc.function.name
                    if name == "submit_verdict":
                        submit_tc = tc
                    elif name == "verify_claim":
                        verify_tcs.append(tc)
                    else:
                        other_tcs.append(tc)

                # Run verify_claims in parallel
                if verify_tcs:
                    try:
                        from ui.loading_overlay import update_stage
                        update_stage("核查声明")
                    except Exception:
                        pass

                    def _run_verify(tc, _text=text, _cache=query_cache, _stages=_dbg["stages"]):
                        args = json.loads(tc.function.arguments)
                        claim_obj = {
                            "text": args.get("claim", ""),
                            "type": args.get("claim_type", "fact"),
                            "importance": args.get("claim_importance", "一般"),
                        }
                        result = self._verify_claim(claim_obj, _text, _cache, _stages)
                        tokens = result.pop("_tokens", {})
                        slog = result.pop("_search_log", []) or []
                        return tc, result, tokens, slog

                    with ThreadPoolExecutor(max_workers=min(len(verify_tcs), max_workers)) as ex:
                        verify_outcomes = list(ex.map(_run_verify, verify_tcs))

                    for tc, result, tokens, slog in verify_outcomes:
                        all_search_log.extend(slog)
                        all_verify_results.append(result)
                        total["input_tokens"] += tokens.get("input_tokens", 0)
                        total["output_tokens"] += tokens.get("output_tokens", 0)
                        clean = {k: v for k, v in result.items() if not k.startswith("_")}
                        messages.append({"role": "tool", "tool_call_id": tc.id,
                                         "content": json.dumps(clean, ensure_ascii=False)})

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

            # Fallback: no submit_verdict received
            if submit_args is None:
                submit_args = {
                    "claim_verification": [
                        {k: v for k, v in r.items() if not k.startswith("_")}
                        for r in all_verify_results
                    ],
                    "investigation_report": {
                        "title_logic_check": title_logic,
                        "hype_check": hype_check,
                        "caveats": [],
                    },
                    "one_line_summary": "",
                    "toxic_review": "",
                    "verdict_text": "",
                }

            # Merge: ensure all Python-tracked verify results are in submit_verdict
            submitted_texts = {r.get("claim", "") for r in submit_args.get("claim_verification", [])}
            for r in all_verify_results:
                if r.get("claim", "") not in submitted_texts:
                    submit_args.setdefault("claim_verification", []).append(
                        {k: v for k, v in r.items() if not k.startswith("_")}
                    )

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
                hype_check = self._check_hype(_ctx_text, _dbg["stages"])

            # Deterministic bi calculation — always use Python-tracked results (authoritative 4-layer data)
            cv_python = [
                {k: v for k, v in r.items() if not k.startswith("_")}
                for r in all_verify_results
            ]
            # Fall back to re-planner's version only if Python has nothing
            cv = cv_python or submit_args.get("claim_verification", [])
            bi, risk_level = self._calculate_bi(cv, title_logic, hype_check)
            radar = self._calculate_radar(cv, title_logic, hype_check)

            ai_nature = submit_args.get("bullshit_nature")
            final_nature = ai_nature if ai_nature else self._nature_from_inputs(bi, cv, title_logic, hype_check)

            result = normalize_result({
                "_mode": "analyze",
                "header": {
                    "bullshit_index": bi,
                    "bullshit_nature": final_nature,
                    "risk_level": risk_level,
                    "verdict": submit_args.get("verdict_text", ""),
                    "truth_label": f"{100 - bi}% 属实" if isinstance(bi, int) else "分析中",
                },
                "claim_verification": cv,
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
