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


class _PlanExecuteMixin:
    """Plan-and-Execute pipeline methods. No __init__."""

    _CLAIM_VERIFY_RETRY = "请根据搜索结果，输出该声明的核查结论 JSON。"

    def _verify_claim(self, claim: str | dict, article_text: str, query_cache: dict | None = None,
                      trace: list | None = None) -> dict:
        """Stage 2: Independent verification of one claim (fresh context, no images)."""
        if isinstance(claim, dict):
            claim_text = claim.get("text", "")
            claim_type = claim.get("type", "fact")
        else:
            claim_text = claim
            claim_type = "fact"
        user_text = f"文章背景（摘要）：{article_text[:400]}\n\n需核查的声明：{claim_text}"
        if claim_type == "narrative":
            user_text += "\n\n【注意】这是叙事类声明（文章的隐含论点/因果解释），此类声明通常难以直接证伪。请搜索是否有具体反驳证据；若搜不到直接矛盾，应判'? 无法核实'。"
        messages = [
            {"role": "system", "content": get_claim_verify_prompt()},
            {"role": "user", "content": [{"type": "text", "text": user_text}]},
        ]
        content, search_log, tokens = self._tool_loop(
            messages, 4000, self._CLAIM_VERIFY_RETRY, force_first_tool=True,
            max_rounds=3, query_cache=query_cache,
            trace=trace, stage_name=f"verify: {claim_text[:40]}",
            temperature=0, extra_create_kwargs={"reasoning_effort": "low"},
        )
        try:
            result = parse_json(content)
            if isinstance(result, list) and result:
                result = result[0]
            if not isinstance(result, dict):
                raise ValueError("not a dict")
        except Exception:
            result = {"verdict": "? 无法核实", "effective_sources": 0,
                      "best_source_type": "none", "note": "核查解析失败", "sources": []}
        # Hard enforcement: no sources → cannot be ✗ 伪造
        if result.get("verdict") == "✗ 伪造" and result.get("effective_sources", 0) == 0:
            result["verdict"] = "? 无法核实"
            result["note"] = result.get("note", "") + " [effective_sources=0，自动改判为无法核实]"
        result["claim"] = claim_text
        result["claim_type"] = claim_type
        result["_search_log"] = search_log
        result["_tokens"] = tokens
        return result

    @staticmethod
    def _calculate_bi(claim_results: list[dict], title_logic: dict, hype: dict) -> tuple[int, str]:
        """Deterministic bi calculation from structured inputs."""
        fake = sum(1 for c in claim_results if "✗" in c.get("verdict", ""))
        unverified = sum(1 for c in claim_results if "?" in c.get("verdict", ""))
        narrative_true = sum(1 for c in claim_results
                             if c.get("claim_type") == "narrative" and "✓" in c.get("verdict", ""))
        if fake >= 2:
            bi = 76
        elif fake == 1:
            bi = 56
        elif unverified > 0:
            bi = 31
        else:
            bi = 15
        bi += 5 * max(0, fake - 2)
        bi += 2 * unverified
        bi += 10 * narrative_true
        if "有问题" in (title_logic.get("verdict") or ""):
            bi += 10
        if "有夸大" in (hype.get("verdict") or ""):
            bi += 10 if hype.get("type") == "第三方估算当事实" else 5
        bi = min(bi, 100)
        risk = ("🚨 极度危险" if bi > 80 else
                "🔶 高度警惕" if bi > 55 else
                "⚠️ 有所存疑" if bi > 30 else
                "✅ 基本可信")
        return bi, risk

    @staticmethod
    def _calculate_radar(claim_results: list[dict], title_logic: dict, hype: dict) -> dict:
        n = max(len(claim_results), 1)
        fake = sum(1 for c in claim_results if "✗" in c.get("verdict", ""))
        unverified = sum(1 for c in claim_results if "?" in c.get("verdict", ""))
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
        """Stage 3a: Title logic check (no tools)."""
        clean = [{k: v for k, v in r.items() if not k.startswith("_")} for r in claim_results]
        _t0 = time.monotonic()
        resp = self._create_with_retry(
            model=self._model,
            messages=[
                {"role": "system", "content": get_title_logic_prompt()},
                {"role": "user", "content": [{"type": "text", "text":
                    f"今天日期：{_current_date}\n\n文章内容（摘要）：{article_text[:1000]}\n\n声明核查结果：{json.dumps(clean, ensure_ascii=False)}"}]},
            ],
            max_tokens=500,
            **_NO_THINKING,
        )
        raw = resp.choices[0].message.content or ""
        if trace is not None:
            trace.append({"name": "title_logic_check", "response": raw[:200],
                          "tokens": {"input": resp.usage.prompt_tokens if resp.usage else 0,
                                     "output": resp.usage.completion_tokens if resp.usage else 0},
                          "elapsed_s": round(time.monotonic() - _t0, 2)})
        try:
            return parse_json(raw) or {"verdict": "无问题", "reason": ""}
        except Exception:
            return {"verdict": "无问题", "reason": ""}

    def _check_hype(self, article_text: str, trace: list | None = None) -> dict:
        """Stage 3b: Hype/exaggeration check (no tools)."""
        _t0 = time.monotonic()
        resp = self._create_with_retry(
            model=self._model,
            messages=[
                {"role": "system", "content": get_hype_check_prompt()},
                {"role": "user", "content": [{"type": "text", "text": f"今天日期：{_current_date}\n\n文章内容：{article_text[:1500]}"}]},
            ],
            max_tokens=300,
            **_NO_THINKING,
        )
        raw = resp.choices[0].message.content or ""
        if trace is not None:
            trace.append({"name": "hype_check", "response": raw[:200],
                          "tokens": {"input": resp.usage.prompt_tokens if resp.usage else 0,
                                     "output": resp.usage.completion_tokens if resp.usage else 0},
                          "elapsed_s": round(time.monotonic() - _t0, 2)})
        try:
            return parse_json(raw) or {"verdict": "无夸大", "type": "无", "reason": ""}
        except Exception:
            return {"verdict": "无夸大", "type": "无", "reason": ""}

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
                        claim_obj = {"text": args.get("claim", ""), "type": args.get("claim_type", "fact")}
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
            if not hype_check and inv.get("hype_check"):
                hype_check = inv["hype_check"]

            # Deterministic bi calculation
            cv = submit_args.get("claim_verification", [])
            bi, risk_level = self._calculate_bi(cv, title_logic, hype_check)
            radar = self._calculate_radar(cv, title_logic, hype_check)

            result = normalize_result({
                "_mode": "analyze",
                "header": {
                    "bullshit_index": bi,
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
                "flaw_list": [],
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
