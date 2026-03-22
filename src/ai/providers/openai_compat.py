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
from ai.prompts import get_system_prompt, get_article_prompt, get_summary_prompt, get_explain_prompt, get_explain_classify_prompt, get_source_prompt, get_source_classify_prompt, get_follow_up_prompt, get_claim_extract_prompt, get_claim_verify_prompt, get_reflect_prompt, get_final_verdict_prompt
from ai.json_utils import parse_json, normalize_result
from ai.tools import TOOLS, SOURCE_TOOLS, execute_tool, set_source_image, get_last_vision_urls, get_last_vision_page_urls

MAX_TOOL_ROUNDS = 8  # 并行调用后每轮可发多个请求，8轮足够复杂案例

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

    def _exec_tools_parallel(self, tool_calls) -> list[tuple]:
        """Execute all tool calls in a round in parallel."""
        def _run(tc):
            fn = tc.function.name
            fa = json.loads(tc.function.arguments)
            try:
                print(f"  🔍 [{self._model}] 调用工具: {fn}({fa})")
            except UnicodeEncodeError:
                print(f"  [search] [{self._model}] {fn}({fa})")
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
    ) -> tuple[str | None, list[dict], dict]:
        """
        Run multi-round tool loop (ReAct pattern).
        force_first_tool=True: first round forces tool_choice="required" (analyze/source).
        force_first_tool=False: all rounds use "auto" (summarize/explain).
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
                tool_choice="required" if (force_first_tool and i == 0) else "auto",
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

    def _zero_tokens(self) -> dict:
        return {"model": self._model, "input": 0, "output": 0}

    def analyze(self, images: list[str], extra_text: str = "") -> tuple[dict, dict]:
        try:
            label = "这些截图" if len(images) > 1 else "这张截图"
            messages = [
                {"role": "system", "content": get_system_prompt(self._tone)},
                {"role": "user", "content": self._image_content(images, f"请分析{label}中的内容真实性：", extra_text)},
            ]
            content, search_log, raw_tokens = self._tool_loop(messages, 4096, _ANALYZE_RETRY_PROMPT, _analyze_schema_ok)
            result = normalize_result(parse_json(content))
            result["_search_log"] = search_log
            result["_token_usage"] = raw_tokens
            token_dict = {"model": self._model, "input": raw_tokens["input_tokens"], "output": raw_tokens["output_tokens"]}
            return result, token_dict
        except Exception as e:
            return _error_result(f"{type(e).__name__}: {e}\n{traceback.format_exc()}"), self._zero_tokens()

    def analyze_article(self, text: str) -> tuple[dict, dict]:
        try:
            messages = [
                {"role": "system", "content": get_article_prompt(self._tone)},
                {"role": "user", "content": [{"type": "text", "text": f"请鉴定以下文章/声明的可信度：\n\n{text[:8000]}"}]},
            ]
            content, search_log, raw_tokens = self._tool_loop(messages, 4096, _ANALYZE_ARTICLE_RETRY_PROMPT, _analyze_schema_ok)
            result = normalize_result(parse_json(content))
            result["_search_log"] = search_log
            result["_token_usage"] = raw_tokens
            token_dict = {"model": self._model, "input": raw_tokens["input_tokens"], "output": raw_tokens["output_tokens"]}
            return result, token_dict
        except Exception as e:
            return _error_result(f"{type(e).__name__}: {e}\n{traceback.format_exc()}"), self._zero_tokens()

    # ── 分阶段鉴定（staged analysis） ─────────────────────────────────────────

    _CLAIM_VERIFY_RETRY = "请根据搜索结果，输出该声明的核查结论 JSON。"

    def _extract_claims(self, text: str, images: list[str] | None = None):
        """Stage 1: Extract verifiable claims. Images sent only here.
        Returns list[str] of claims, OR a full result dict if the model did a complete analysis.
        """
        if images:
            user_content = self._image_content(images, f"文章内容：\n\n{text[:6000]}")
        else:
            user_content = [{"type": "text", "text": f"文章内容：\n\n{text[:6000]}"}]
        resp = self._create_with_retry(
            model=self._model,
            messages=[
                {"role": "system", "content": get_claim_extract_prompt()},
                {"role": "user", "content": user_content},
            ],
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or ""
        try:
            data = parse_json(raw)
            if isinstance(data, dict):
                # Model returned a full analysis — use it directly
                if "header" in data or "claim_verification" in data:
                    return data  # signal to caller: skip stages 2/3
                claims = data.get("claims", [])
            elif isinstance(data, list):
                claims = data
            else:
                claims = []
            return [str(c) for c in claims[:4] if c]
        except Exception:
            return []

    def _verify_claim(self, claim: str, article_text: str) -> dict:
        """Stage 2: Independent verification of one claim (fresh context, no images)."""
        messages = [
            {"role": "system", "content": get_claim_verify_prompt()},
            {"role": "user", "content": [{"type": "text", "text":
                f"文章背景（摘要）：{article_text[:400]}\n\n需核查的声明：{claim}"}]},
        ]
        content, search_log, tokens = self._tool_loop(
            messages, 800, self._CLAIM_VERIFY_RETRY, force_first_tool=True,
        )
        try:
            result = parse_json(content)
        except Exception:
            result = {"verdict": "? 无法核实", "effective_sources": 0,
                      "best_source_type": "none", "note": "核查解析失败", "sources": []}
        result["claim"] = claim
        result["_search_log"] = search_log
        result["_tokens"] = tokens
        return result

    def _reflect(self, article_text: str, claim_results: list[dict]) -> list[str]:
        """Stage 2.5: Decide if additional claims need investigation."""
        clean = [{k: v for k, v in r.items() if not k.startswith("_")} for r in claim_results]
        resp = self._create_with_retry(
            model=self._model,
            messages=[
                {"role": "system", "content": get_reflect_prompt()},
                {"role": "user", "content": [{"type": "text", "text":
                    f"文章（摘要）：{article_text[:600]}\n\n已核查结果：{json.dumps(clean, ensure_ascii=False)}"}]},
            ],
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        try:
            data = parse_json(resp.choices[0].message.content)
            return data.get("additional_claims", [])[:2]
        except Exception:
            return []

    def _final_verdict(self, article_text: str, claim_results: list[dict]) -> tuple[dict, dict]:
        """Stage 3: Final verdict using pre-computed claim results, no tools, no images."""
        clean = [{k: v for k, v in r.items() if not k.startswith("_")} for r in claim_results]
        user_text = (f"文章内容：\n\n{article_text[:8000]}\n\n"
                     f"---\n【已完成的逐条声明核查，原样复制到输出的 claim_verification，禁止修改】：\n"
                     f"{json.dumps(clean, ensure_ascii=False)}")
        resp = self._create_with_retry(
            model=self._model,
            messages=[
                {"role": "system", "content": get_final_verdict_prompt(self._tone)},
                {"role": "user", "content": [{"type": "text", "text": user_text}]},
            ],
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
        tin = resp.usage.prompt_tokens if resp.usage else 0
        tout = resp.usage.completion_tokens if resp.usage else 0
        return parse_json(resp.choices[0].message.content), {"input_tokens": tin, "output_tokens": tout}

    def _apply_floor(self, result: dict) -> dict:
        """Enforce bullshit_index floor based on claim_verification verdicts."""
        _final_cv = result.get("claim_verification", []) or []
        _fake_count = sum(1 for r in _final_cv if "\u2717" in r.get("verdict", ""))
        _has_unverified = any("?" in r.get("verdict", "") for r in _final_cv)
        _header = result.setdefault("header", {})
        _bi = _header.get("bullshit_index", 0)
        if _fake_count >= 2:
            _bi = max(_bi, 76)
        elif _fake_count == 1:
            _bi = max(_bi, 56)
        elif _has_unverified:
            _bi = max(_bi, 31)
        _header["bullshit_index"] = _bi
        _risk_map = [(80, "🚨 极度危险"), (55, "🔶 高度警惕"), (30, "⚠️ 有所存疑"), (-1, "✅ 基本可信")]
        for threshold, label in _risk_map:
            if _bi > threshold:
                _header["risk_level"] = label
                break
        return result

    def analyze_article_staged(self, text: str, images: list[str] | None = None) -> tuple[dict, dict]:
        """Multi-stage article analysis: isolated per-claim verification + reflection."""
        try:
            total = {"input_tokens": 0, "output_tokens": 0}

            # Stage 1: claim extraction (images sent only here)
            # Returns list[str] of claims, OR a full result dict if model did complete analysis
            claims = self._extract_claims(text, images)

            if isinstance(claims, dict):
                # Model already did a full analysis in Stage 1 — normalize, apply floor, return
                result = normalize_result(claims)
                result = self._apply_floor(result)
                result.setdefault("_search_log", [])
                result["_token_usage"] = total
                token_dict = {"model": self._model, "input": 0, "output": 0}
                return normalize_result(result), token_dict

            if not claims:
                return self.analyze_article(text)  # fallback to classic

            # Stage 2: parallel independent verification (max 2 workers for free-tier RPM)
            with ThreadPoolExecutor(max_workers=min(len(claims), 2)) as ex:
                claim_results = list(ex.map(lambda c: self._verify_claim(c, text), claims))
            for r in claim_results:
                t = r.pop("_tokens", {})
                total["input_tokens"] += t.get("input_tokens", 0)
                total["output_tokens"] += t.get("output_tokens", 0)

            # Stage 2.5: reflection — one optional extra round
            extra = self._reflect(text, claim_results)
            if extra:
                with ThreadPoolExecutor(max_workers=min(len(extra), 2)) as ex:
                    extra_results = list(ex.map(lambda c: self._verify_claim(c, text), extra))
                for r in extra_results:
                    t = r.pop("_tokens", {})
                    total["input_tokens"] += t.get("input_tokens", 0)
                    total["output_tokens"] += t.get("output_tokens", 0)
                claim_results.extend(extra_results)

            # Stage 3: final verdict (no tools, no images)
            result, vtokens = self._final_verdict(text, claim_results)
            total["input_tokens"] += vtokens["input_tokens"]
            total["output_tokens"] += vtokens["output_tokens"]

            result = normalize_result(result)
            result = self._apply_floor(result)

            all_logs = []
            for r in claim_results:
                all_logs.extend(r.pop("_search_log", []))
            result["_search_log"] = all_logs
            result["_token_usage"] = total
            token_dict = {"model": self._model, "input": total["input_tokens"], "output": total["output_tokens"]}
            return result, token_dict
        except Exception as e:
            return _error_result(f"{type(e).__name__}: {e}\n{traceback.format_exc()}"), self._zero_tokens()

    # ── 一键总结 ──────────────────────────────────────────────────────────────

    _SUMMARY_DEFAULTS = {
        "_mode": "summary", "content_type": "other", "headline": "", "core_idea": "",
        "key_points": [], "structured_outline": [], "timeline": [], "key_quote": "",
        "original_language": "zh", "bias_note": "",
    }

    _SUMMARY_RETRY = "请直接输出 JSON，不要加任何 markdown 代码块或其他文字。"

    def summarize(self, images: list[str], extra_text: str = "") -> tuple[dict, dict]:
        try:
            messages = [
                {"role": "system", "content": get_summary_prompt()},
                {"role": "user", "content": self._image_content(images, "请总结这些内容：", extra_text)},
            ]
            content, _, raw_tokens = self._tool_loop(messages, 2048, self._SUMMARY_RETRY, force_first_tool=False)
            result = parse_json(content)
            for k, v in self._SUMMARY_DEFAULTS.items():
                result.setdefault(k, v)
            token_dict = {"model": self._model, "input": raw_tokens["input_tokens"], "output": raw_tokens["output_tokens"]}
            return result, token_dict
        except Exception as e:
            return {**self._SUMMARY_DEFAULTS, "error": str(e)}, self._zero_tokens()

    def summarize_article(self, text: str) -> tuple[dict, dict]:
        # 文字输入内容自洽，无需 web_search，直接 _run_single 省去工具定义开销
        return self._run_single(
            get_summary_prompt(),
            f"请总结以下内容：\n\n{text[:8000]}",
            2048,
            self._SUMMARY_DEFAULTS,
        ), self._zero_tokens()

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
        try:
            user_content = self._image_content(images, "请解释这些内容：", extra_text)

            # Stage 1: 分类
            cls = self._classify_explain(user_content)
            subtype = cls["subtype"]

            # Stage 2: 专化 prompt
            messages = [
                {"role": "system", "content": get_explain_prompt(subtype)},
                {"role": "user", "content": user_content},
            ]
            content, _, raw_tokens = self._tool_loop(messages, 4096, self._EXPLAIN_RETRY, force_first_tool=False)
            result = parse_json(content)
            result["_subtype"] = subtype
            if cls["grid_rows"]:
                result.setdefault("grid_rows", cls["grid_rows"])
            if cls["grid_cols"]:
                result.setdefault("grid_cols", cls["grid_cols"])
            for k, v in self._EXPLAIN_DEFAULTS.items():
                result.setdefault(k, v)
            token_dict = {"model": self._model, "input": raw_tokens["input_tokens"], "output": raw_tokens["output_tokens"]}
            return result, token_dict
        except Exception as e:
            return {**self._EXPLAIN_DEFAULTS, "error": str(e)}, self._zero_tokens()

    def explain_article(self, text: str) -> tuple[dict, dict]:
        try:
            text_content = f"请解释以下内容：\n\n{text[:8000]}"

            # 文字内容：先分类
            cls = self._classify_explain(text_content)
            subtype = cls["subtype"]

            messages = [
                {"role": "system", "content": get_explain_prompt(subtype)},
                {"role": "user", "content": text_content},
            ]
            content, _, raw_tokens = self._tool_loop(messages, 4096, self._EXPLAIN_RETRY, force_first_tool=False)
            result = parse_json(content)
            result["_subtype"] = subtype
            for k, v in self._EXPLAIN_DEFAULTS.items():
                result.setdefault(k, v)
            token_dict = {"model": self._model, "input": raw_tokens["input_tokens"], "output": raw_tokens["output_tokens"]}
            return result, token_dict
        except Exception as e:
            return {**self._EXPLAIN_DEFAULTS, "error": str(e)}, self._zero_tokens()

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
        try:
            set_source_image(images[0] if images else None)
            from config.manager import load as _load_cfg
            _vkey = _load_cfg().get("google_vision_api_key", "")
            _active_tools = SOURCE_TOOLS if (_vkey and not _vkey.startswith("AIzaSy-YOUR")) else TOOLS

            user_content = self._image_content(images, "请识别这张截图来自哪部作品：", extra_text)

            # Stage 1: 分类
            meta = self._classify_source(user_content)
            subtype = meta["subtype"]

            # Stage 2: 专化 prompt
            messages = [
                {"role": "system", "content": get_source_prompt(subtype=subtype)},
                {"role": "user", "content": user_content},
            ]
            content, search_log, raw_tokens = self._tool_loop(
                messages, 4096, _SOURCE_RETRY_PROMPT, tools=_active_tools
            )
            result = parse_json(content)
            result["_subtype"] = subtype
            for k, v in self._SOURCE_DEFAULTS.items():
                result.setdefault(k, v)
            # 参考图只用 Vision API 精确/部分匹配结果（visual_similar 已在 tools.py 过滤）
            # 模型自填的 URL 不可信（web_search 无法返回真实图片 URL），一律忽略
            vision_urls = get_last_vision_urls()
            result["reference_image_urls"] = vision_urls if vision_urls else []
            # 作品来源页面链接（来自 Vision pagesWithMatchingImages）
            page_urls = get_last_vision_page_urls()
            if page_urls:
                result["source_page_urls"] = page_urls
            elif not result.get("source_page_urls"):
                result["source_page_urls"] = []
            result["_search_log"] = search_log
            result["_token_usage"] = raw_tokens
            result["_vision_used"] = _active_tools is SOURCE_TOOLS
            token_dict = {"model": self._model, "input": raw_tokens["input_tokens"], "output": raw_tokens["output_tokens"]}
            return result, token_dict
        except Exception as e:
            return {**self._SOURCE_DEFAULTS, "error": f"{type(e).__name__}: {e}"}, self._zero_tokens()
        finally:
            set_source_image(None)

    def source_find_article(self, text: str) -> tuple[dict, dict]:
        try:
            text_content = f"请根据以下描述识别来自哪部作品：\n\n{text[:4000]}"

            # Stage 1: 分类
            meta = self._classify_source(text_content)
            subtype = meta["subtype"]

            # Stage 2: 专化 prompt
            messages = [
                {"role": "system", "content": get_source_prompt(subtype=subtype)},
                {"role": "user", "content": [{"type": "text", "text": text_content}]},
            ]
            content, search_log, raw_tokens = self._tool_loop(messages, 4096, _SOURCE_RETRY_PROMPT)
            result = parse_json(content)
            result["_subtype"] = subtype
            for k, v in self._SOURCE_DEFAULTS.items():
                result.setdefault(k, v)
            result["_search_log"] = search_log
            result["_token_usage"] = raw_tokens
            token_dict = {"model": self._model, "input": raw_tokens["input_tokens"], "output": raw_tokens["output_tokens"]}
            return result, token_dict
        except Exception as e:
            return {**self._SOURCE_DEFAULTS, "error": f"{type(e).__name__}: {e}"}, self._zero_tokens()


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
