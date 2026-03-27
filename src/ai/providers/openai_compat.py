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
from ai.providers.classic_mixin import _ClassicMixin
from ai.providers.plan_mixin import _PlanExecuteMixin

_SEARCH_QUOTA_PATTERNS = ("usage limit", "exceeds your plan", "upgrade your plan", "quota exceeded")


class SearchUnavailableError(Exception):
    """搜索服务不可用（配额耗尽或系统性失败），分析结果不可信。"""


from ai.json_utils import parse_json, normalize_result
from ai.tools import TOOLS, execute_tool
from ai.debug_log import make_stage, finish_stage

MAX_TOOL_ROUNDS = 8  # 并行调用后每轮可发多个请求，8轮足够复杂案例

# 关闭思考模式（适用于简单提取/决策步骤，节省 token 和延迟）
_NO_THINKING = {"reasoning_effort": "none"}


def _analyze_schema_ok(parsed: dict) -> bool:
    inv = parsed.get("investigation_report", {})
    return bool(inv.get("content_nature")) and parsed.get("claim_verification") is not None


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


class OpenAICompatibleProvider(_ClassicMixin, _PlanExecuteMixin, BaseLLMProvider):
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

    def _zero_tokens(self) -> dict:
        return {"model": self._model, "input": 0, "output": 0}
