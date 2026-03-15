"""
OpenAICompatibleProvider —— 覆盖所有兼容 OpenAI 接口的大模型。

支持：Gemini（via Google AI Studio OpenAI endpoint）、DeepSeek、
      Kimi（月之暗面）、通义千问、智谱 GLM、以及任何自定义 base_url。
"""

import json
import traceback

from openai import OpenAI

from ai.providers.base import BaseLLMProvider
from ai.prompts import get_system_prompt, get_article_prompt
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

            choice = None
            for round_idx in range(MAX_TOOL_ROUNDS):
                # 第一轮强制调用工具（保证至少搜索一次），后续轮次模型自主决定
                tool_choice = "required" if round_idx == 0 else "auto"
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice=tool_choice,
                    max_tokens=4096,
                )
                choice = response.choices[0]

                if choice.finish_reason != "tool_calls" and not choice.message.tool_calls:
                    break

                assistant_msg = choice.message
                messages.append(assistant_msg)

                for tool_call in assistant_msg.tool_calls:
                    func_name = tool_call.function.name
                    func_args = json.loads(tool_call.function.arguments)
                    print(f"  🔍 [{self._model}] 调用工具: {func_name}({func_args})")
                    tool_result = execute_tool(func_name, func_args)
                    search_log.append({
                        "tool": func_name,
                        "query": func_args.get("query", ""),
                        "result_preview": tool_result[:200],
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
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
                    parse_json(content)
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
                    "content": "请根据以上所有信息，严格按照 JSON 格式输出最终分析结果。",
                })
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    max_tokens=4096,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content

            result = parse_json(content)
            result = normalize_result(result)
            result["_search_log"] = search_log
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

            choice = None
            for round_idx in range(MAX_TOOL_ROUNDS):
                tool_choice = "required" if round_idx == 0 else "auto"
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice=tool_choice,
                    max_tokens=4096,
                )
                choice = response.choices[0]

                if choice.finish_reason != "tool_calls" and not choice.message.tool_calls:
                    break

                assistant_msg = choice.message
                messages.append(assistant_msg)

                for tool_call in assistant_msg.tool_calls:
                    func_name = tool_call.function.name
                    func_args = json.loads(tool_call.function.arguments)
                    print(f"  🔍 [{self._model}] 调用工具: {func_name}({func_args})")
                    tool_result = execute_tool(func_name, func_args)
                    search_log.append({
                        "tool": func_name,
                        "query": func_args.get("query", ""),
                        "result_preview": tool_result[:200],
                    })
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
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
                    parse_json(content)
                except (json.JSONDecodeError, ValueError):
                    needs_retry = True

            if needs_retry:
                last = messages[-1]
                if isinstance(last, dict) and last.get("role") != "assistant":
                    if choice and choice.message and choice.message.content:
                        messages.append(choice.message)
                messages.append({
                    "role": "user",
                    "content": "请根据以上所有信息，严格按照 JSON 格式输出最终分析结果。",
                })
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    max_tokens=4096,
                    response_format={"type": "json_object"},
                )
                content = response.choices[0].message.content

            result = parse_json(content)
            result = normalize_result(result)
            result["_search_log"] = search_log
            return result

        except json.JSONDecodeError as e:
            return _error_result(f"JSONDecodeError: {e}")
        except Exception as e:
            return _error_result(f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


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
