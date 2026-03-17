"""
OpenAICompatibleProvider —— 覆盖所有兼容 OpenAI 接口的大模型。

支持：Gemini（via Google AI Studio OpenAI endpoint）、DeepSeek、
      Kimi（月之暗面）、通义千问、智谱 GLM、以及任何自定义 base_url。
"""

import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI
import openai

from ai.providers.base import BaseLLMProvider
from ai.prompts import get_system_prompt, get_article_prompt, get_summary_prompt, get_explain_prompt
from ai.json_utils import parse_json, normalize_result
from ai.tools import TOOLS, execute_tool

MAX_TOOL_ROUNDS = 5


class OpenAICompatibleProvider(BaseLLMProvider):
    """
    使用 openai Python SDK 的通用 Provider。
    只需在初始化时传入 api_key / base_url / model 即可切换供应商。

    常用配置示例：
        # Gemini
        OpenAICompatibleProvider(
            api_key="AIza...",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
            model="gemini-2.0-flash",
        )
        # DeepSeek
        OpenAICompatibleProvider(
            api_key="sk-...",
            base_url="https://api.deepseek.com",
            model="deepseek-chat",
        )
        # Kimi
        OpenAICompatibleProvider(
            api_key="sk-...",
            base_url="https://api.moonshot.cn/v1",
            model="moonshot-v1-8k",
        )
    """

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
        """带指数退避的 API 调用，处理限速和超时。"""
        delay = 10
        for attempt in range(max_retries):
            try:
                return self._client.chat.completions.create(**kwargs)
            except (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError) as e:
                if attempt == max_retries - 1:
                    raise
                wait = delay * (2 ** attempt)
                print(f"  ⏳ API 限速/超时，{wait}s 后重试 (attempt {attempt+1}/{max_retries}): {type(e).__name__}")
                time.sleep(wait)

    def _exec_tools_parallel(self, tool_calls) -> list[tuple]:
        """并行执行一轮中所有工具调用，返回有序列表 [(tool_call, func_name, func_args, result), ...]"""
        def _run(tc):
            func_name = tc.function.name
            func_args = json.loads(tc.function.arguments)
            print(f"  🔍 [{self._model}] 调用工具: {func_name}({func_args})")
            return tc, func_name, func_args, execute_tool(func_name, func_args)

        with ThreadPoolExecutor(max_workers=len(tool_calls)) as ex:
            return list(ex.map(_run, tool_calls))

    def analyze(self, image_base64: str) -> dict:
        """ReAct 循环：思考 → 工具调用 → 综合输出 JSON"""
        try:
            search_log: list[dict] = []
            messages: list[dict] = [
                {"role": "system", "content": get_system_prompt(self._tone)},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请分析这张截图中的内容真实性："},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_base64}"},
                        },
                    ],
                },
            ]

            total_input_tokens = 0
            total_output_tokens = 0
            choice = None
            for round_idx in range(MAX_TOOL_ROUNDS):
                # 第一轮强制调用工具（保证至少搜索一次），后续轮次模型自主决定
                tool_choice = "required" if round_idx == 0 else "auto"
                response = self._create_with_retry(
                    model=self._model,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice=tool_choice,
                    max_tokens=4096,
                )
                if response.usage:
                    total_input_tokens += response.usage.prompt_tokens or 0
                    total_output_tokens += response.usage.completion_tokens or 0
                choice = response.choices[0]

                if choice.finish_reason != "tool_calls" and not choice.message.tool_calls:
                    break

                assistant_msg = choice.message
                messages.append(assistant_msg)

                for tc, func_name, func_args, tool_result in self._exec_tools_parallel(assistant_msg.tool_calls):
                    search_log.append({
                        "tool": func_name,
                        "query": func_args.get("query", ""),
                        "result_preview": tool_result[:200],
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result,
                    })

            # 检查是否需要强制请求 JSON 输出
            content = choice.message.content if choice and choice.message else None
            needs_retry = (
                content is None
                or (choice.finish_reason == "tool_calls")
                or bool(choice.message.tool_calls)
            )
            if not needs_retry:
                try:
                    parsed = parse_json(content)
                    # 字段完整性检查：核心新 schema 字段缺失时触发 retry
                    inv = parsed.get("investigation_report", {})
                    claims = parsed.get("claim_verification")
                    if not inv.get("content_nature") or claims is None:
                        needs_retry = True
                except (json.JSONDecodeError, ValueError):
                    needs_retry = True

            if needs_retry:
                # 确保最后的 assistant 消息在历史中
                last = messages[-1]
                if isinstance(last, dict) and last.get("role") != "assistant":
                    if choice and choice.message and choice.message.content:
                        messages.append(choice.message)
                messages.append({
                    "role": "user",
                    "content": (
                        "请根据以上所有信息，严格按照系统提示定义的 JSON 格式输出最终分析结果。\n"
                        "重要字段提醒（缺任何一个都视为格式错误）：\n"
                        "1. investigation_report 必须包含 content_nature 字段（内容性质：社交媒体截图/新闻报道/官方公文等）\n"
                        "2. claim_verification 必须包含至少1条声明核查，每条含 claim / verdict / effective_sources / best_source_type / note\n"
                        "3. verdict 只能填：✓ 独立核实属实 / ✓ 官方自述 / ✗ 伪造 / ? 无法核实"
                    ),
                })
                response = self._create_with_retry(
                    model=self._model,
                    messages=messages,
                    max_tokens=4096,
                    response_format={"type": "json_object"},
                )
                if response.usage:
                    total_input_tokens += response.usage.prompt_tokens or 0
                    total_output_tokens += response.usage.completion_tokens or 0
                content = response.choices[0].message.content

            result = parse_json(content)
            result = normalize_result(result)
            result["_search_log"] = search_log
            result["_token_usage"] = {"input_tokens": total_input_tokens, "output_tokens": total_output_tokens}
            return result

        except json.JSONDecodeError as e:
            return _error_result(f"JSONDecodeError: {e}")
        except Exception as e:
            return _error_result(f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


    def analyze_article(self, text: str) -> dict:
        """文章鉴定：纯文字输入，针对数据来源/夸大/遗漏/意图进行分析"""
        try:
            search_log: list[dict] = []
            messages: list[dict] = [
                {"role": "system", "content": get_article_prompt(self._tone)},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"请鉴定以下文章/声明的可信度：\n\n{text[:8000]}"},
                    ],
                },
            ]

            total_input_tokens = 0
            total_output_tokens = 0
            choice = None
            for round_idx in range(MAX_TOOL_ROUNDS):
                tool_choice = "required" if round_idx == 0 else "auto"
                response = self._create_with_retry(
                    model=self._model,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice=tool_choice,
                    max_tokens=4096,
                )
                if response.usage:
                    total_input_tokens += response.usage.prompt_tokens or 0
                    total_output_tokens += response.usage.completion_tokens or 0
                choice = response.choices[0]

                if choice.finish_reason != "tool_calls" and not choice.message.tool_calls:
                    break

                assistant_msg = choice.message
                messages.append(assistant_msg)

                for tc, func_name, func_args, tool_result in self._exec_tools_parallel(assistant_msg.tool_calls):
                    search_log.append({
                        "tool": func_name,
                        "query": func_args.get("query", ""),
                        "result_preview": tool_result[:200],
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_result,
                    })

            content = choice.message.content if choice and choice.message else None
            needs_retry = (
                content is None
                or (choice.finish_reason == "tool_calls")
                or bool(choice.message.tool_calls)
            )
            if not needs_retry:
                try:
                    parsed = parse_json(content)
                    inv = parsed.get("investigation_report", {})
                    claims = parsed.get("claim_verification")
                    if not inv.get("content_nature") or claims is None:
                        needs_retry = True
                except (json.JSONDecodeError, ValueError):
                    needs_retry = True

            if needs_retry:
                last = messages[-1]
                if isinstance(last, dict) and last.get("role") != "assistant":
                    if choice and choice.message and choice.message.content:
                        messages.append(choice.message)
                messages.append({
                    "role": "user",
                    "content": (
                        "请根据以上所有信息，严格按照系统提示定义的 JSON 格式输出最终分析结果。\n"
                        "重要字段提醒（缺任何一个都视为格式错误）：\n"
                        "1. investigation_report 必须包含 content_nature 字段（内容性质：自媒体公众号/科技媒体/官方新闻等）\n"
                        "2. claim_verification 必须包含至少1条声明核查，每条含 claim / verdict / effective_sources / best_source_type / note\n"
                        "3. verdict 只能填：✓ 独立核实属实 / ✓ 官方自述 / ✗ 伪造 / ? 无法核实"
                    ),
                })
                response = self._create_with_retry(
                    model=self._model,
                    messages=messages,
                    max_tokens=4096,
                    response_format={"type": "json_object"},
                )
                if response.usage:
                    total_input_tokens += response.usage.prompt_tokens or 0
                    total_output_tokens += response.usage.completion_tokens or 0
                content = response.choices[0].message.content

            result = parse_json(content)
            result = normalize_result(result)
            result["_search_log"] = search_log
            result["_token_usage"] = {"input_tokens": total_input_tokens, "output_tokens": total_output_tokens}
            return result

        except json.JSONDecodeError as e:
            return _error_result(f"JSONDecodeError: {e}")
        except Exception as e:
            return _error_result(f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


    def summarize(self, image_base64: str) -> dict:
        """截图一键总结（单次调用，无工具循环）"""
        try:
            response = self._create_with_retry(
                model=self._model,
                messages=[
                    {"role": "system", "content": get_summary_prompt()},
                    {"role": "user", "content": [
                        {"type": "text", "text": "请总结这张截图的内容："},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                    ]},
                ],
                max_tokens=1024,
                response_format={"type": "json_object"},
            )
            import json
            result = parse_json(response.choices[0].message.content)
            result.setdefault("_mode", "summary")
            result.setdefault("headline", "")
            result.setdefault("key_points", [])
            result.setdefault("original_language", "zh")
            result.setdefault("bias_note", "")
            return result
        except Exception as e:
            return {"_mode": "summary", "error": f"{type(e).__name__}: {e}",
                    "headline": "总结失败", "key_points": [], "original_language": "zh", "bias_note": ""}

    def summarize_article(self, text: str) -> dict:
        """文章一键总结（单次调用，无工具循环）"""
        try:
            response = self._create_with_retry(
                model=self._model,
                messages=[
                    {"role": "system", "content": get_summary_prompt()},
                    {"role": "user", "content": f"请总结以下内容：\n\n{text[:8000]}"},
                ],
                max_tokens=1024,
                response_format={"type": "json_object"},
            )
            import json
            result = parse_json(response.choices[0].message.content)
            result.setdefault("_mode", "summary")
            result.setdefault("headline", "")
            result.setdefault("key_points", [])
            result.setdefault("original_language", "zh")
            result.setdefault("bias_note", "")
            return result
        except Exception as e:
            return {"_mode": "summary", "error": f"{type(e).__name__}: {e}",
                    "headline": "总结失败", "key_points": [], "original_language": "zh", "bias_note": ""}


    def explain(self, image_base64: str) -> dict:
        """截图内容一键解释（单次调用，无工具循环）"""
        try:
            response = self._create_with_retry(
                model=self._model,
                messages=[
                    {"role": "system", "content": get_explain_prompt()},
                    {"role": "user", "content": [
                        {"type": "text", "text": "请解释这张截图中的内容："},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                    ]},
                ],
                max_tokens=4096,
                response_format={"type": "json_object"},
            )
            result = parse_json(response.choices[0].message.content)
            result.setdefault("_mode", "explain")
            result.setdefault("type", "concept")
            result.setdefault("subject", "")
            result.setdefault("short_answer", "")
            result.setdefault("characters", [])
            result.setdefault("detail", "")
            result.setdefault("origin", "")
            result.setdefault("usage", "")
            result.setdefault("original_language", "zh")
            return result
        except Exception as e:
            return {"_mode": "explain", "error": f"{type(e).__name__}: {e}",
                    "type": "concept", "subject": "解释失败", "short_answer": "解释失败",
                    "characters": [], "detail": "", "origin": "", "usage": "", "original_language": "zh"}

    def explain_article(self, text: str) -> dict:
        """文章/文字内容一键解释（单次调用，无工具循环）"""
        try:
            response = self._create_with_retry(
                model=self._model,
                messages=[
                    {"role": "system", "content": get_explain_prompt()},
                    {"role": "user", "content": f"请解释以下内容：\n\n{text[:8000]}"},
                ],
                max_tokens=4096,
                response_format={"type": "json_object"},
            )
            result = parse_json(response.choices[0].message.content)
            result.setdefault("_mode", "explain")
            result.setdefault("type", "concept")
            result.setdefault("subject", "")
            result.setdefault("short_answer", "")
            result.setdefault("characters", [])
            result.setdefault("detail", "")
            result.setdefault("origin", "")
            result.setdefault("usage", "")
            result.setdefault("original_language", "zh")
            return result
        except Exception as e:
            return {"_mode": "explain", "error": f"{type(e).__name__}: {e}",
                    "type": "concept", "subject": "解释失败", "short_answer": "解释失败",
                    "characters": [], "detail": "", "origin": "", "usage": "", "original_language": "zh"}


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
