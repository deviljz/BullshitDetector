"""
OpenAICompatibleProvider — covers all OpenAI-compatible models.
Supports: Gemini, DeepSeek, Kimi, Qwen, GLM, and any custom base_url.
"""

import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from openai import OpenAI
import openai

from ai.providers.base import BaseLLMProvider

_SEARCH_QUOTA_PATTERNS = ("usage limit", "exceeds your plan", "upgrade your plan", "quota exceeded")


class SearchUnavailableError(Exception):
    """搜索服务不可用（配额耗尽或系统性失败），分析结果不可信。"""

from ai.prompts import get_system_prompt, get_article_prompt, get_summary_prompt, get_explain_prompt, get_explain_classify_prompt, get_source_prompt, get_source_classify_prompt, get_follow_up_prompt, get_claim_verify_prompt, get_final_verdict_prompt, get_title_logic_prompt, get_hype_check_prompt, get_framing_check_prompt, get_planner_prompt, get_replanner_prompt
from ai.json_utils import parse_json, normalize_result
from ai.tools import TOOLS, SOURCE_TOOLS, PLAN_EXECUTE_TOOLS, PLANNER_TOOLS, execute_tool, set_source_image, get_last_vision_urls, get_last_vision_page_urls
from ai.debug_log import make_entry, make_stage, finish_stage, set_result, write_entry, sanitize_messages

MAX_TOOL_ROUNDS = 8  # 并行调用后每轮可发多个请求，8轮足够复杂案例

# 关闭思考模式（适用于简单提取/决策步骤，节省 token 和延迟）
_NO_THINKING = {"reasoning_effort": "none"}

_ANALYZE_RETRY_PROMPT = (
    "请根据以上所有信息，严格按照系统提示定义的 JSON 格式输出最终分析结果。\n"
    "重要字段提醒（缺任何一个都视为格式错误）：\n"
    "1. investigation_report 必须包含 content_nature 字段（内容性质：社交媒体截图/新闻报道/官方公文等）\n"
    "2. claim_verification 必须包含至少1条声明核查，每条含 claim / verdict / effective_sources / best_source_type / note / sources\n"
    "3. verdict 只能填：✓ 独立核实属实 / ✓ 官方自述 / ✗ 伪造 / ? 无法核实\n"
    "4. sources：填入支持该判断的参考链接（最多3条，格式：[{\"url\": \"https://...\", \"title\": \"页面标题\"}]）；搜不到填 []"
)
_ANALYZE_ARTICLE_RETRY_PROMPT = (
    "请根据以上所有信息，严格按照系统提示定义的 JSON 格式输出最终分析结果。\n"
    "重要字段提醒（缺任何一个都视为格式错误）：\n"
    "1. investigation_report 必须包含 content_nature 字段（内容性质：自媒体公众号/科技媒体/官方新闻等）\n"
    "2. claim_verification 必须包含至少1条声明核查，每条含 claim / verdict / effective_sources / best_source_type / note / sources\n"
    "3. verdict 只能填：✓ 独立核实属实 / ✓ 官方自述 / ✗ 伪造 / ? 无法核实\n"
    "4. sources：填入支持该判断的参考链接（最多3条，格式：[{\"url\": \"https://...\", \"title\": \"页面标题\"}]）；搜不到填 []\n"
    "5. investigation_report.title_logic_check：分析标题是否存在因果谬误（相关≠因果）或用无关数据为核心论点背书"
)
_SOURCE_RETRY_PROMPT = "请根据以上搜索结果，严格按照系统提示定义的 JSON 格式输出最终识别结果。"


def _analyze_schema_ok(parsed: dict) -> bool:
    inv = parsed.get("investigation_report", {})
    return bool(inv.get("content_nature")) and parsed.get("claim_verification") is not None


class OpenAICompatibleProvider(BaseLLMProvider):
    """Universal provider for OpenAI-compatible APIs."""

    def __init__(self, api_key: str, base_url: str | None = None, model: str = "gemini-2.0-flash", tone: str = "toxic"):
        if not api_key:
            raise ValueError("api_key 不能为空，请在 config.json 或环境变量中配置")
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self._model = model
        self._tone = tone
    def _create_with_retry(self, max_retries: int = 5, **kwargs):
        """Exponential backoff for rate limits and timeouts."""
        delay = 10
        for attempt in range(max_retries):
            try:
                return self._client.chat.completions.create(**kwargs)
            except (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError) as e:
                if attempt == max_retries - 1:
                    raise
                wait = delay * (2 ** attempt)
                print(f"  ⏳ [{self._model}] {wait}s 后重试 ({attempt+1}/{max_retries}): {type(e).__name__}")
                time.sleep(wait)

    def _exec_tools_parallel(self, tool_calls, query_cache: dict | None = None) -> list[tuple]:
        """Execute all tool calls in a round in parallel. query_cache deduplicates web_search."""
        def _run(tc):
            fn = tc.function.name
            fa = json.loads(tc.function.arguments)
            try:
                print(f"  🔍 [{self._model}] 调用工具: {fn}({fa})")
            except UnicodeEncodeError:
                safe = f"  [search] [{self._model}] {fn}({fa})".encode("gbk", errors="replace").decode("gbk")
                print(safe)
            try:
                from ui.loading_overlay import update_stage
                if fn == "web_search":
                    q = json.loads(tc.function.arguments).get("query", "")
                    short = q[:18] + "…" if len(q) > 18 else q
                    update_stage(f"搜索：{short}")
                else:
                    update_stage(f"调用工具…")
            except Exception:
                pass
            if fn == "web_search" and query_cache is not None:
                q = fa.get("query", "")
                if q in query_cache:
                    return tc, fn, fa, query_cache[q]
                result = execute_tool(fn, fa)
                query_cache[q] = result
                return tc, fn, fa, result
            return tc, fn, fa, execute_tool(fn, fa)
        with ThreadPoolExecutor(max_workers=len(tool_calls)) as ex:
            return list(ex.map(_run, tool_calls))

    @staticmethod
    def _image_content(images: list[str], prefix: str, extra_text: str = "") -> list[dict]:
        """Build user content list for image input."""
        content = [{"type": "text", "text": prefix}]
        for b64 in images:
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
        if extra_text:
            content.append({"type": "text", "text": f"补充说明：\n{extra_text[:4000]}"})
        return content

    def _tool_loop(
        self,
        messages: list[dict],
        max_tokens: int,
        retry_prompt: str | None = None,
        schema_check: Callable[[dict], bool] | None = None,
        tools: list | None = None,
        force_first_tool: bool = True,
        max_rounds: int | None = None,
        query_cache: dict | None = None,
        trace: list | None = None,
        stage_name: str = "tool_loop",
        temperature: float | None = None,
        extra_create_kwargs: dict | None = None,
    ) -> tuple[str | None, list[dict], dict]:
        """
        Run multi-round tool loop (ReAct pattern).
        force_first_tool=True: first round forces tool_choice="required" (analyze/source).
        force_first_tool=False: all rounds use "auto" (summarize/explain).
        max_rounds: overrides MAX_TOOL_ROUNDS for this call.
        query_cache: shared dict for deduplicating web_search across parallel workers.
        trace: if provided, appends a stage dict {name, messages_in, tool_calls, response, tokens}.
        extra_create_kwargs: extra kwargs forwarded to every _create_with_retry call (e.g. reasoning_effort).
        Returns (content, search_log, token_usage).
        """
        _tools = tools if tools is not None else TOOLS
        search_log: list[dict] = []
        total_in = total_out = 0
        choice = None
        rounds = max_rounds if max_rounds is not None else MAX_TOOL_ROUNDS

        _stage: dict | None = None
        if trace is not None:
            _stage = make_stage(stage_name, messages)
            trace.append(_stage)

        _temp_kwargs = {"temperature": temperature} if temperature is not None else {}
        if extra_create_kwargs:
            _temp_kwargs.update(extra_create_kwargs)
        for i in range(rounds):
            resp = self._create_with_retry(
                model=self._model,
                messages=messages,
                tools=_tools,
                tool_choice="required" if (force_first_tool and i == 0) else "auto",
                max_tokens=max_tokens,
                **_temp_kwargs,
            )
            if resp.usage:
                total_in += resp.usage.prompt_tokens or 0
                total_out += resp.usage.completion_tokens or 0
            choice = resp.choices[0]

            if choice.finish_reason != "tool_calls" and not choice.message.tool_calls:
                break

            messages.append(choice.message)
            _round_results = self._exec_tools_parallel(choice.message.tool_calls, query_cache)
            _search_results_this_round = []
            for tc, fn, fa, result in _round_results:
                search_log.append({"tool": fn, "query": fa.get("query", ""), "result_preview": result[:600]})
                if _stage is not None:
                    _stage["tool_calls"].append({"fn": fn, "query": fa.get("query", str(fa)[:80]), "result": result[:600]})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
                if fn == "web_search":
                    _search_results_this_round.append(result)
            # Detect systematic search quota failure: all searches failed in this round
            if _search_results_this_round and all(
                any(p in r for p in _SEARCH_QUOTA_PATTERNS) for r in _search_results_this_round
            ):
                raise SearchUnavailableError(
                    "搜索服务配额已耗尽，无法完成事实核查。请检查搜索 API 配额后重试。"
                )

        content = choice.message.content if choice and choice.message else None
        needs_retry = (
            content is None
            or bool(choice and choice.finish_reason == "tool_calls")
            or bool(choice and choice.message.tool_calls)
        )

        if not needs_retry and schema_check and content:
            try:
                if not schema_check(parse_json(content)):
                    needs_retry = True
            except (json.JSONDecodeError, ValueError):
                needs_retry = True

        if needs_retry and retry_prompt:
            last = messages[-1]
            if isinstance(last, dict) and last.get("role") != "assistant":
                if choice and choice.message and choice.message.content:
                    messages.append(choice.message)
            messages.append({"role": "user", "content": retry_prompt})
            resp = self._create_with_retry(
                model=self._model,
                messages=messages,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            if resp.usage:
                total_in += resp.usage.prompt_tokens or 0
                total_out += resp.usage.completion_tokens or 0
            content = resp.choices[0].message.content

        if _stage is not None:
            _stage["response"] = (content or "")[:500]
            _stage["tokens"] = {"input": total_in, "output": total_out}
            finish_stage(_stage)

        return content, search_log, {"input_tokens": total_in, "output_tokens": total_out}

    def _run_single(
        self, system_prompt: str, user_content, max_tokens: int, defaults: dict,
        trace: list | None = None, stage_name: str = "single_call",
    ) -> tuple[dict, dict]:
        """Single call without tool loop. Returns (result_dict, token_dict)."""
        try:
            content = user_content if isinstance(user_content, list) else [{"type": "text", "text": user_content}]
            resp = self._create_with_retry(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": content},
                ],
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            tin = resp.usage.prompt_tokens if resp.usage else 0
            tout = resp.usage.completion_tokens if resp.usage else 0
            raw = resp.choices[0].message.content or ""
            if trace is not None:
                trace.append({
                    "name": stage_name,
                    "response": raw[:500],
                    "tokens": {"input": tin, "output": tout},
                })
            result = parse_json(raw)
            for k, v in defaults.items():
                result.setdefault(k, v)
            return result, {"input": tin, "output": tout}
        except Exception as e:
            return {**defaults, "error": f"{type(e).__name__}: {e}"}, {"input": 0, "output": 0}

    # ── 截图/文章鉴定 ─────────────────────────────────────────────────────────

    def _zero_tokens(self) -> dict:
        return {"model": self._model, "input": 0, "output": 0}

    def analyze(self, images: list[str], extra_text: str = "") -> tuple[dict, dict]:
        _dbg = make_entry("analyze", {"image_count": len(images), "extra_text_len": len(extra_text)})
        try:
            label = "这些截图" if len(images) > 1 else "这张截图"
            messages = [
                {"role": "system", "content": get_system_prompt(self._tone)},
                {"role": "user", "content": self._image_content(images, f"请分析{label}中的内容真实性：", extra_text)},
            ]
            content, search_log, raw_tokens = self._tool_loop(
                messages, 4096, _ANALYZE_RETRY_PROMPT, _analyze_schema_ok,
                trace=_dbg["stages"], stage_name="analyze_main",
            )
            result = normalize_result(parse_json(content))
            result["_search_log"] = search_log
            result["_token_usage"] = raw_tokens
            token_dict = {"model": self._model, "input": raw_tokens["input_tokens"], "output": raw_tokens["output_tokens"]}
            set_result(_dbg, result, token_dict, "classic")
            return result, token_dict
        except Exception as e:
            _dbg["error"] = str(e)
            return _error_result(f"{type(e).__name__}: {e}\n{traceback.format_exc()}"), self._zero_tokens()
        finally:
            write_entry(_dbg)

    def analyze_article(self, text: str, images: list[str] | None = None, _write_debug: bool = True, _ext_stages: list | None = None) -> tuple[dict, dict]:
        _dbg = make_entry("analyze_article", {"text_len": len(text), "image_count": len(images) if images else 0})
        if _ext_stages is not None:
            _dbg["stages"] = _ext_stages  # merge into caller's stages list
        try:
            try:
                from ui.loading_overlay import update_stage
                update_stage("AI 分析中")
            except Exception:
                pass
            user_text = f"请鉴定以下文章/声明的可信度：\n\n{text[:8000]}"
            user_content = self._image_content(images, user_text) if images else [{"type": "text", "text": user_text}]
            messages = [
                {"role": "system", "content": get_article_prompt(self._tone)},
                {"role": "user", "content": user_content},
            ]
            content, search_log, raw_tokens = self._tool_loop(
                messages, 4096, _ANALYZE_ARTICLE_RETRY_PROMPT, _analyze_schema_ok,
                trace=_dbg["stages"], stage_name="analyze_main",
            )
            result = normalize_result(parse_json(content))
            result["_search_log"] = search_log
            result["_token_usage"] = raw_tokens
            token_dict = {"model": self._model, "input": raw_tokens["input_tokens"], "output": raw_tokens["output_tokens"]}
            set_result(_dbg, result, token_dict, "classic")
            return result, token_dict
        except Exception as e:
            _dbg["error"] = str(e)
            return _error_result(f"{type(e).__name__}: {e}\n{traceback.format_exc()}"), self._zero_tokens()
        finally:
            if _write_debug:
                write_entry(_dbg)

    # ── 分阶段鉴定（staged analysis） ─────────────────────────────────────────

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
                    f"文章内容（摘要）：{article_text[:1000]}\n\n声明核查结果：{json.dumps(clean, ensure_ascii=False)}"}]},
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
                {"role": "user", "content": [{"type": "text", "text": f"文章内容：{article_text[:1500]}"}]},
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
        _dbg = make_entry("analyze_staged", {"text_len": len(text), "image_count": len(images or [])})
        try:
            from config.manager import load as _load_cfg
            cfg = _load_cfg()
            max_workers = cfg.get("staged_max_workers", 5)
            max_replan = cfg.get("plan_execute_max_replan", 2)

            total = {"input_tokens": 0, "output_tokens": 0}
            query_cache: dict = {}
            all_verify_results: list[dict] = []
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

                # submit_verdict terminates the loop
                if submit_tc:
                    try:
                        submit_args = json.loads(submit_tc.function.arguments)
                    except Exception:
                        submit_args = {}
                    messages.append({"role": "tool", "tool_call_id": submit_tc.id, "content": '{"status": "ok"}'})
                    break

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
                        result.pop("_search_log", None)
                        return tc, result, tokens

                    with ThreadPoolExecutor(max_workers=min(len(verify_tcs), max_workers)) as ex:
                        verify_outcomes = list(ex.map(_run_verify, verify_tcs))

                    for tc, result, tokens in verify_outcomes:
                        all_verify_results.append(result)
                        total["input_tokens"] += tokens.get("input_tokens", 0)
                        total["output_tokens"] += tokens.get("output_tokens", 0)
                        clean = {k: v for k, v in result.items() if not k.startswith("_")}
                        messages.append({"role": "tool", "tool_call_id": tc.id,
                                         "content": json.dumps(clean, ensure_ascii=False)})

                # Run other tools (analyze_title_logic, analyze_hype)
                for tc in other_tcs:
                    name = tc.function.name
                    if name == "analyze_title_logic":
                        title_logic = self._check_title_logic(text, all_verify_results, _dbg["stages"])
                        messages.append({"role": "tool", "tool_call_id": tc.id,
                                         "content": json.dumps(title_logic, ensure_ascii=False)})
                    elif name == "analyze_hype":
                        hype_check = self._check_hype(text, _dbg["stages"])
                        messages.append({"role": "tool", "tool_call_id": tc.id,
                                         "content": json.dumps(hype_check, ensure_ascii=False)})

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
                "radar_chart": {},
                "flaw_list": [],
            })
            result["_search_log"] = []
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

    # ── 一键总结 ──────────────────────────────────────────────────────────────

    _SUMMARY_DEFAULTS = {
        "_mode": "summary", "content_type": "other", "headline": "", "core_idea": "",
        "key_points": [], "structured_outline": [], "timeline": [], "key_quote": "",
        "original_language": "zh", "bias_note": "",
    }

    _SUMMARY_RETRY = "请直接输出 JSON，不要加任何 markdown 代码块或其他文字。"

    def summarize(self, images: list[str], extra_text: str = "") -> tuple[dict, dict]:
        _dbg = make_entry("summarize", {"image_count": len(images)})
        try:
            messages = [
                {"role": "system", "content": get_summary_prompt()},
                {"role": "user", "content": self._image_content(images, "请总结这些内容：", extra_text)},
            ]
            content, _, raw_tokens = self._tool_loop(
                messages, 2048, self._SUMMARY_RETRY, force_first_tool=False,
                trace=_dbg["stages"], stage_name="summarize_main",
            )
            result = parse_json(content)
            for k, v in self._SUMMARY_DEFAULTS.items():
                result.setdefault(k, v)
            token_dict = {"model": self._model, "input": raw_tokens["input_tokens"], "output": raw_tokens["output_tokens"]}
            set_result(_dbg, result, token_dict, "single")
            return result, token_dict
        except Exception as e:
            _dbg["error"] = str(e)
            return {**self._SUMMARY_DEFAULTS, "error": str(e)}, self._zero_tokens()
        finally:
            write_entry(_dbg)

    def summarize_article(self, text: str) -> tuple[dict, dict]:
        _dbg = make_entry("summarize_article", {"text_len": len(text)})
        try:
            result, raw = self._run_single(
                get_summary_prompt(),
                f"请总结以下内容：\n\n{text[:8000]}",
                2048,
                self._SUMMARY_DEFAULTS,
                trace=_dbg["stages"], stage_name="summarize_main",
            )
            token_dict = {"model": self._model, "input": raw["input"], "output": raw["output"]}
            set_result(_dbg, result, token_dict, "single")
            return result, token_dict
        except Exception as e:
            _dbg["error"] = str(e)
            return {**self._SUMMARY_DEFAULTS, "error": str(e)}, self._zero_tokens()
        finally:
            write_entry(_dbg)

    # ── 一键解释 ──────────────────────────────────────────────────────────────

    _EXPLAIN_DEFAULTS = {
        "_mode": "explain", "_subtype": "concept",
        "type": "concept", "subject": "", "short_answer": "",
        "characters": [], "detail": "", "origin": "", "usage": "",
        "still_active": True, "cultural_note": "",
        "grid_rows": 0, "grid_cols": 0,
        "known_for": "", "current_status": "", "product_specs": "",
        "original_language": "zh",
    }

    _EXPLAIN_RETRY = "请直接输出 JSON，不要加任何 markdown 代码块或其他文字。"

    def _classify_explain(self, user_content) -> dict:
        """Stage 1: 轻量分类，不使用工具，返回 {subtype, grid_rows, grid_cols, brief}"""
        try:
            content = user_content if isinstance(user_content, list) else [{"type": "text", "text": user_content}]
            resp = self._create_with_retry(
                model=self._model,
                messages=[
                    {"role": "system", "content": get_explain_classify_prompt()},
                    {"role": "user", "content": content},
                ],
                max_tokens=200,
                response_format={"type": "json_object"},
            )
            result = parse_json(resp.choices[0].message.content)
            return {
                "subtype": result.get("subtype", "concept"),
                "grid_rows": result.get("grid_rows", 0),
                "grid_cols": result.get("grid_cols", 0),
                "brief": result.get("brief", ""),
            }
        except Exception:
            return {"subtype": "concept", "grid_rows": 0, "grid_cols": 0, "brief": ""}

    def explain(self, images: list[str], extra_text: str = "") -> tuple[dict, dict]:
        _dbg = make_entry("explain", {"image_count": len(images)})
        try:
            user_content = self._image_content(images, "请解释这些内容：", extra_text)
            cls = self._classify_explain(user_content)
            _dbg["stages"].append({"name": "classify_explain", "result": cls})
            subtype = cls["subtype"]
            messages = [
                {"role": "system", "content": get_explain_prompt(subtype)},
                {"role": "user", "content": user_content},
            ]
            content, _, raw_tokens = self._tool_loop(
                messages, 4096, self._EXPLAIN_RETRY, force_first_tool=False,
                trace=_dbg["stages"], stage_name="explain_main",
            )
            result = parse_json(content)
            result["_subtype"] = subtype
            if cls["grid_rows"]:
                result.setdefault("grid_rows", cls["grid_rows"])
            if cls["grid_cols"]:
                result.setdefault("grid_cols", cls["grid_cols"])
            for k, v in self._EXPLAIN_DEFAULTS.items():
                result.setdefault(k, v)
            token_dict = {"model": self._model, "input": raw_tokens["input_tokens"], "output": raw_tokens["output_tokens"]}
            set_result(_dbg, result, token_dict, "classify+explain")
            return result, token_dict
        except Exception as e:
            _dbg["error"] = str(e)
            return {**self._EXPLAIN_DEFAULTS, "error": str(e)}, self._zero_tokens()
        finally:
            write_entry(_dbg)

    def explain_article(self, text: str) -> tuple[dict, dict]:
        _dbg = make_entry("explain_article", {"text_len": len(text)})
        try:
            text_content = f"请解释以下内容：\n\n{text[:8000]}"
            cls = self._classify_explain(text_content)
            _dbg["stages"].append({"name": "classify_explain", "result": cls})
            subtype = cls["subtype"]
            messages = [
                {"role": "system", "content": get_explain_prompt(subtype)},
                {"role": "user", "content": text_content},
            ]
            content, _, raw_tokens = self._tool_loop(
                messages, 4096, self._EXPLAIN_RETRY, force_first_tool=False,
                trace=_dbg["stages"], stage_name="explain_main",
            )
            result = parse_json(content)
            result["_subtype"] = subtype
            for k, v in self._EXPLAIN_DEFAULTS.items():
                result.setdefault(k, v)
            token_dict = {"model": self._model, "input": raw_tokens["input_tokens"], "output": raw_tokens["output_tokens"]}
            set_result(_dbg, result, token_dict, "classify+explain")
            return result, token_dict
        except Exception as e:
            _dbg["error"] = str(e)
            return {**self._EXPLAIN_DEFAULTS, "error": str(e)}, self._zero_tokens()
        finally:
            write_entry(_dbg)

    # ── 求出处 ────────────────────────────────────────────────────────────────

    _SOURCE_DEFAULTS = {
        "_mode": "source",
        "found": False,
        "title": "",
        "original_title": "",
        "media_type": "other",
        "year": "",
        "studio": "",
        "episode": "",
        "episode_title": "",
        "scene": "",
        "characters": [],
        "confidence": "low",
        "note": "",
        "_vision_used": False,
        "_subtype": "anime",
        # manga
        "volume": "",
        "chapter": "",
        "publisher": "",
        "artist": "",
        # film_tv
        "director": "",
        "actors": [],
        # game
        "game_title": "",
        "developer": "",
        "platform": "",
        # social_post
        "account": "",
        "post_date": "",
        "content_summary": "",
        "original_url": "",
        # artwork
        "source_site": "",
        "reference_image_urls": [],
        "source_page_urls": [],
        "_search_log": [],
    }

    def _classify_source(self, user_content) -> dict:
        """Stage 1: 轻量分类，不使用工具，返回 {subtype, brief}"""
        try:
            content = user_content if isinstance(user_content, list) else [{"type": "text", "text": user_content}]
            resp = self._create_with_retry(
                model=self._model,
                messages=[
                    {"role": "system", "content": get_source_classify_prompt()},
                    {"role": "user", "content": content},
                ],
                max_tokens=200,
                response_format={"type": "json_object"},
            )
            result = parse_json(resp.choices[0].message.content)
            return {
                "subtype": result.get("subtype", "anime"),
                "brief": result.get("brief", ""),
            }
        except Exception:
            return {"subtype": "anime", "brief": ""}

    def source_find(self, images: list[str], extra_text: str = "") -> tuple[dict, dict]:
        _dbg = make_entry("source_find", {"image_count": len(images)})
        try:
            set_source_image(images[0] if images else None)
            from config.manager import load as _load_cfg
            _vkey = _load_cfg().get("google_vision_api_key", "")
            _active_tools = SOURCE_TOOLS if (_vkey and not _vkey.startswith("AIzaSy-YOUR")) else TOOLS

            user_content = self._image_content(images, "请识别这张截图来自哪部作品：", extra_text)
            meta = self._classify_source(user_content)
            _dbg["stages"].append({"name": "classify_source", "result": meta})
            subtype = meta["subtype"]

            messages = [
                {"role": "system", "content": get_source_prompt(subtype=subtype)},
                {"role": "user", "content": user_content},
            ]
            content, search_log, raw_tokens = self._tool_loop(
                messages, 4096, _SOURCE_RETRY_PROMPT, tools=_active_tools,
                trace=_dbg["stages"], stage_name="source_main",
            )
            result = parse_json(content)
            result["_subtype"] = subtype
            for k, v in self._SOURCE_DEFAULTS.items():
                result.setdefault(k, v)
            vision_urls = get_last_vision_urls()
            result["reference_image_urls"] = vision_urls if vision_urls else []
            page_urls = get_last_vision_page_urls()
            if page_urls:
                result["source_page_urls"] = page_urls
            elif not result.get("source_page_urls"):
                result["source_page_urls"] = []
            result["_search_log"] = search_log
            result["_token_usage"] = raw_tokens
            result["_vision_used"] = _active_tools is SOURCE_TOOLS
            token_dict = {"model": self._model, "input": raw_tokens["input_tokens"], "output": raw_tokens["output_tokens"]}
            set_result(_dbg, result, token_dict, "classify+source")
            return result, token_dict
        except Exception as e:
            _dbg["error"] = str(e)
            return {**self._SOURCE_DEFAULTS, "error": f"{type(e).__name__}: {e}"}, self._zero_tokens()
        finally:
            set_source_image(None)
            write_entry(_dbg)

    def source_find_article(self, text: str) -> tuple[dict, dict]:
        _dbg = make_entry("source_find_article", {"text_len": len(text)})
        try:
            text_content = f"请根据以下描述识别来自哪部作品：\n\n{text[:4000]}"
            meta = self._classify_source(text_content)
            _dbg["stages"].append({"name": "classify_source", "result": meta})
            subtype = meta["subtype"]

            messages = [
                {"role": "system", "content": get_source_prompt(subtype=subtype)},
                {"role": "user", "content": [{"type": "text", "text": text_content}]},
            ]
            content, search_log, raw_tokens = self._tool_loop(
                messages, 4096, _SOURCE_RETRY_PROMPT,
                trace=_dbg["stages"], stage_name="source_main",
            )
            result = parse_json(content)
            result["_subtype"] = subtype
            for k, v in self._SOURCE_DEFAULTS.items():
                result.setdefault(k, v)
            result["_search_log"] = search_log
            result["_token_usage"] = raw_tokens
            token_dict = {"model": self._model, "input": raw_tokens["input_tokens"], "output": raw_tokens["output_tokens"]}
            set_result(_dbg, result, token_dict, "classify+source")
            return result, token_dict
        except Exception as e:
            _dbg["error"] = str(e)
            return {**self._SOURCE_DEFAULTS, "error": f"{type(e).__name__}: {e}"}, self._zero_tokens()
        finally:
            write_entry(_dbg)


    def follow_up(self, context_text: str, history: list[dict], question: str, mode: str = "analyze") -> tuple[str, dict]:
        """Plain-text follow-up conversation with optional web_search. Returns (response, token_dict)."""
        messages = [
            {"role": "system", "content": get_follow_up_prompt(mode)},
            {"role": "user", "content": f"【分析背景】\n{context_text}"},
            {"role": "assistant", "content": "好的，我已了解以上分析内容，请问有什么想追问的？"},
        ]
        for turn in history:
            messages.append({"role": "user", "content": turn["user"]})
            messages.append({"role": "assistant", "content": turn["ai"]})
        messages.append({"role": "user", "content": question})
        try:
            content, _, raw = self._tool_loop(messages, 4096, force_first_tool=False)
            text = content or "（无回复）"
            token_dict = {"model": self._model, "input": raw["input_tokens"], "output": raw["output_tokens"]}
            return text, token_dict
        except Exception as e:
            return f"追问失败：{type(e).__name__}: {e}", self._zero_tokens()


def _error_result(error_msg: str) -> dict:
    return {
        "header": {
            "bullshit_index": None,
            "truth_label": "分析失败",
            "risk_level": "💥 分析出错",
            "verdict": "分析过程出错",
        },
        "radar_chart": {"logic_consistency": 0, "source_authority": 0, "agitation_level": 0, "search_match": 0},
        "investigation_report": {"time_check": "未完成", "entity_check": "未完成", "physics_check": "未完成"},
        "toxic_review": "鉴屎官崩溃了，分析过程出错",
        "flaw_list": [],
        "one_line_summary": "分析失败",
        "error": error_msg,
    }
