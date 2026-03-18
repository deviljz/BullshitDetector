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
from ai.prompts import get_system_prompt, get_article_prompt, get_summary_prompt, get_explain_prompt, get_source_prompt
from ai.json_utils import parse_json, normalize_result
from ai.tools import TOOLS, SOURCE_TOOLS, execute_tool, set_source_image, get_last_vision_urls

MAX_TOOL_ROUNDS = 5

_ANALYZE_RETRY_PROMPT = (
    "请根据以上所有信息，严格按照系统提示定义的 JSON 格式输出最终分析结果。\n"
    "重要字段提醒（缺任何一个都视为格式错误）：\n"
    "1. investigation_report 必须包含 content_nature 字段（内容性质：社交媒体截图/新闻报道/官方公文等）\n"
    "2. claim_verification 必须包含至少1条声明核查，每条含 claim / verdict / effective_sources / best_source_type / note\n"
    "3. verdict 只能填：✓ 独立核实属实 / ✓ 官方自述 / ✗ 伪造 / ? 无法核实"
)
_ANALYZE_ARTICLE_RETRY_PROMPT = (
    "请根据以上所有信息，严格按照系统提示定义的 JSON 格式输出最终分析结果。\n"
    "重要字段提醒（缺任何一个都视为格式错误）：\n"
    "1. investigation_report 必须包含 content_nature 字段（内容性质：自媒体公众号/科技媒体/官方新闻等）\n"
    "2. claim_verification 必须包含至少1条声明核查，每条含 claim / verdict / effective_sources / best_source_type / note\n"
    "3. verdict 只能填：✓ 独立核实属实 / ✓ 官方自述 / ✗ 伪造 / ? 无法核实"
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

    def _exec_tools_parallel(self, tool_calls) -> list[tuple]:
        """Execute all tool calls in a round in parallel."""
        def _run(tc):
            fn = tc.function.name
            fa = json.loads(tc.function.arguments)
            print(f"  🔍 [{self._model}] 调用工具: {fn}({fa})")
            return tc, fn, fa, execute_tool(fn, fa)
        with ThreadPoolExecutor(max_workers=len(tool_calls)) as ex:
            return list(ex.map(_run, tool_calls))

    @staticmethod
    def _image_content(images: list[str], prefix: str) -> list[dict]:
        """Build user content list for image input."""
        content = [{"type": "text", "text": prefix}]
        for b64 in images:
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
        return content

    def _tool_loop(
        self,
        messages: list[dict],
        max_tokens: int,
        retry_prompt: str | None = None,
        schema_check: Callable[[dict], bool] | None = None,
        tools: list | None = None,
    ) -> tuple[str | None, list[dict], dict]:
        """
        Run multi-round tool loop (ReAct pattern).
        First round forces tool_choice="required"; subsequent rounds are "auto".
        Returns (content, search_log, token_usage).
        """
        _tools = tools if tools is not None else TOOLS
        search_log: list[dict] = []
        total_in = total_out = 0
        choice = None

        for i in range(MAX_TOOL_ROUNDS):
            resp = self._create_with_retry(
                model=self._model,
                messages=messages,
                tools=_tools,
                tool_choice="required" if i == 0 else "auto",
                max_tokens=max_tokens,
            )
            if resp.usage:
                total_in += resp.usage.prompt_tokens or 0
                total_out += resp.usage.completion_tokens or 0
            choice = resp.choices[0]

            if choice.finish_reason != "tool_calls" and not choice.message.tool_calls:
                break

            messages.append(choice.message)
            for tc, fn, fa, result in self._exec_tools_parallel(choice.message.tool_calls):
                search_log.append({"tool": fn, "query": fa.get("query", ""), "result_preview": result[:200]})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

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

        return content, search_log, {"input_tokens": total_in, "output_tokens": total_out}

    def _run_single(self, system_prompt: str, user_content, max_tokens: int, defaults: dict) -> dict:
        """Single call without tool loop (for summarize/explain)."""
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
            result = parse_json(resp.choices[0].message.content)
            for k, v in defaults.items():
                result.setdefault(k, v)
            return result
        except Exception as e:
            return {**defaults, "error": f"{type(e).__name__}: {e}"}

    # ── 截图/文章鉴定 ─────────────────────────────────────────────────────────

    def analyze(self, images: list[str]) -> dict:
        try:
            label = "这些截图" if len(images) > 1 else "这张截图"
            messages = [
                {"role": "system", "content": get_system_prompt(self._tone)},
                {"role": "user", "content": self._image_content(images, f"请分析{label}中的内容真实性：")},
            ]
            content, search_log, tokens = self._tool_loop(messages, 4096, _ANALYZE_RETRY_PROMPT, _analyze_schema_ok)
            result = normalize_result(parse_json(content))
            result["_search_log"] = search_log
            result["_token_usage"] = tokens
            return result
        except Exception as e:
            return _error_result(f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

    def analyze_article(self, text: str) -> dict:
        try:
            messages = [
                {"role": "system", "content": get_article_prompt(self._tone)},
                {"role": "user", "content": [{"type": "text", "text": f"请鉴定以下文章/声明的可信度：\n\n{text[:8000]}"}]},
            ]
            content, search_log, tokens = self._tool_loop(messages, 4096, _ANALYZE_ARTICLE_RETRY_PROMPT, _analyze_schema_ok)
            result = normalize_result(parse_json(content))
            result["_search_log"] = search_log
            result["_token_usage"] = tokens
            return result
        except Exception as e:
            return _error_result(f"{type(e).__name__}: {e}\n{traceback.format_exc()}")

    # ── 一键总结 ──────────────────────────────────────────────────────────────

    _SUMMARY_DEFAULTS = {"_mode": "summary", "headline": "", "key_points": [], "original_language": "zh", "bias_note": ""}

    def summarize(self, images: list[str]) -> dict:
        return self._run_single(get_summary_prompt(), self._image_content(images, "请总结这些内容："), 1024, self._SUMMARY_DEFAULTS)

    def summarize_article(self, text: str) -> dict:
        return self._run_single(get_summary_prompt(), f"请总结以下内容：\n\n{text[:8000]}", 1024, self._SUMMARY_DEFAULTS)

    # ── 一键解释 ──────────────────────────────────────────────────────────────

    _EXPLAIN_DEFAULTS = {
        "_mode": "explain", "type": "concept", "subject": "", "short_answer": "",
        "characters": [], "detail": "", "origin": "", "usage": "", "original_language": "zh",
    }

    def explain(self, images: list[str]) -> dict:
        return self._run_single(get_explain_prompt(), self._image_content(images, "请解释这些内容："), 4096, self._EXPLAIN_DEFAULTS)

    def explain_article(self, text: str) -> dict:
        return self._run_single(get_explain_prompt(), f"请解释以下内容：\n\n{text[:8000]}", 4096, self._EXPLAIN_DEFAULTS)

    # ── 求出处 ────────────────────────────────────────────────────────────────

    _SOURCE_DEFAULTS = {
        "_mode": "source", "found": False, "title": "", "original_title": "",
        "media_type": "other", "year": "", "studio": "", "episode": "",
        "episode_title": "", "scene": "", "characters": [], "confidence": "low", "note": "",
        "reference_image_urls": [],
    }

    def source_find(self, images: list[str]) -> dict:
        try:
            set_source_image(images[0] if images else None)
            from config.manager import load as _load_cfg
            _vkey = _load_cfg().get("google_vision_api_key", "")
            _active_tools = SOURCE_TOOLS if (_vkey and not _vkey.startswith("AIzaSy-YOUR")) else TOOLS
            messages = [
                {"role": "system", "content": get_source_prompt()},
                {"role": "user", "content": self._image_content(images, "请识别这张截图来自哪部作品：")},
            ]
            content, search_log, tokens = self._tool_loop(
                messages, 2048, _SOURCE_RETRY_PROMPT, tools=_active_tools
            )
            result = parse_json(content)
            for k, v in self._SOURCE_DEFAULTS.items():
                result.setdefault(k, v)
            # Vision API 的视觉相似图优先；AI 自填的 URL 只作无 Vision 时的 fallback
            vision_urls = get_last_vision_urls()
            if vision_urls:
                result["reference_image_urls"] = vision_urls
            elif not result.get("reference_image_urls"):
                result["reference_image_urls"] = []
            result["_search_log"] = search_log
            result["_token_usage"] = tokens
            result["_vision_used"] = _active_tools is SOURCE_TOOLS
            return result
        except Exception as e:
            return {**self._SOURCE_DEFAULTS, "error": f"{type(e).__name__}: {e}"}
        finally:
            set_source_image(None)

    def source_find_article(self, text: str) -> dict:
        try:
            messages = [
                {"role": "system", "content": get_source_prompt()},
                {"role": "user", "content": [{"type": "text", "text": f"请根据以下描述识别来自哪部作品：\n\n{text[:4000]}"}]},
            ]
            content, search_log, tokens = self._tool_loop(messages, 2048, _SOURCE_RETRY_PROMPT)
            result = parse_json(content)
            for k, v in self._SOURCE_DEFAULTS.items():
                result.setdefault(k, v)
            result["_search_log"] = search_log
            result["_token_usage"] = tokens
            return result
        except Exception as e:
            return {**self._SOURCE_DEFAULTS, "error": f"{type(e).__name__}: {e}"}


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
