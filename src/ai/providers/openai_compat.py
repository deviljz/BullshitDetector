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
from ai.debug_log import make_entry, make_stage, set_result, write_entry, sanitize_messages

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
    ) -> tuple[str | None, list[dict], dict]:
        """
        Run multi-round tool loop (ReAct pattern).
        force_first_tool=True: first round forces tool_choice="required" (analyze/source).
        force_first_tool=False: all rounds use "auto" (summarize/explain).
        max_rounds: overrides MAX_TOOL_ROUNDS for this call.
        query_cache: shared dict for deduplicating web_search across parallel workers.
        trace: if provided, appends a stage dict {name, messages_in, tool_calls, response, tokens}.
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
            for tc, fn, fa, result in self._exec_tools_parallel(choice.message.tool_calls, query_cache):
                search_log.append({"tool": fn, "query": fa.get("query", ""), "result_preview": result[:200]})
                if _stage is not None:
                    _stage["tool_calls"].append({"fn": fn, "query": fa.get("query", str(fa)[:80]), "result": result[:200]})
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

        if _stage is not None:
            _stage["response"] = (content or "")[:500]
            _stage["tokens"] = {"input": total_in, "output": total_out}

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

    def analyze_article(self, text: str) -> tuple[dict, dict]:
        _dbg = make_entry("analyze_article", {"text_len": len(text)})
        try:
            try:
                from ui.loading_overlay import update_stage
                update_stage("AI 分析中")
            except Exception:
                pass
            messages = [
                {"role": "system", "content": get_article_prompt(self._tone)},
                {"role": "user", "content": [{"type": "text", "text": f"请鉴定以下文章/声明的可信度：\n\n{text[:8000]}"}]},
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
            write_entry(_dbg)

    # ── 分阶段鉴定（staged analysis） ─────────────────────────────────────────

    _CLAIM_VERIFY_RETRY = "请根据搜索结果，输出该声明的核查结论 JSON。"

    def _extract_claims(self, text: str, images: list[str] | None = None, trace: list | None = None):
        """Stage 1: Extract verifiable claims. Images sent only here.
        Returns (list[str] of claims  OR  full result dict, token_dict).
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
            max_tokens=1000,
        )
        tin = resp.usage.prompt_tokens if resp.usage else 0
        tout = resp.usage.completion_tokens if resp.usage else 0
        tokens = {"input_tokens": tin, "output_tokens": tout}
        raw = resp.choices[0].message.content or ""
        if trace is not None:
            trace.append({
                "name": "extract_claims",
                "response": raw[:500],
                "tokens": {"input": tin, "output": tout},
            })
        try:
            if len(raw.strip()) < 20:  # truncated / empty response from API
                return [], tokens
            # Detect truncated JSON: if raw doesn't end with closing brace, response was cut off
            raw_stripped = raw.strip()
            if not raw_stripped.endswith("}") and not raw_stripped.endswith("]"):
                return [], tokens
            data = parse_json(raw)
            if isinstance(data, dict):
                # Only treat as full analysis if it has meaningful content (not a repaired empty shell)
                has_header = isinstance(data.get("header"), dict) and data["header"].get("bullshit_index") is not None
                has_cv = isinstance(data.get("claim_verification"), list) and len(data["claim_verification"]) > 0
                if has_header or has_cv:
                    return data, tokens  # signal to caller: skip stages 2/3
                claims = data.get("claims", [])
            elif isinstance(data, list):
                claims = data
            else:
                claims = []
            normalized = []
            for c in claims[:5]:
                if isinstance(c, dict) and c.get("text"):
                    normalized.append({"text": str(c["text"]), "type": c.get("type", "fact")})
                elif isinstance(c, str) and c:
                    normalized.append({"text": c, "type": "fact"})
            return normalized, tokens
        except Exception:
            return [], tokens

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
            user_text += "\n\n【注意】这是叙事类声明（文章的隐含论点），请搜索对比数据（如与前作/同类作品同期数据对比）来验证或推翻。"
        messages = [
            {"role": "system", "content": get_claim_verify_prompt()},
            {"role": "user", "content": [{"type": "text", "text": user_text}]},
        ]
        content, search_log, tokens = self._tool_loop(
            messages, 800, self._CLAIM_VERIFY_RETRY, force_first_tool=True,
            max_rounds=3, query_cache=query_cache,
            trace=trace, stage_name=f"verify: {claim_text[:40]}",
            temperature=0,
        )
        try:
            result = parse_json(content)
        except Exception:
            result = {"verdict": "? 无法核实", "effective_sources": 0,
                      "best_source_type": "none", "note": "核查解析失败", "sources": []}
        result["claim"] = claim_text
        result["claim_type"] = claim_type
        result["_search_log"] = search_log
        result["_tokens"] = tokens
        return result

    def _reflect(self, article_text: str, claim_results: list[dict], trace: list | None = None) -> list[str]:
        """Stage 2.5: Decide if additional claims need investigation."""
        clean = [{k: v for k, v in r.items() if not k.startswith("_")} for r in claim_results]
        resp = self._create_with_retry(
            model=self._model,
            messages=[
                {"role": "system", "content": get_reflect_prompt()},
                {"role": "user", "content": [{"type": "text", "text":
                    f"文章（摘要）：{article_text[:600]}\n\n已核查结果：{json.dumps(clean, ensure_ascii=False)}"}]},
            ],
            max_tokens=600,
        )
        raw = resp.choices[0].message.content or ""
        tin = resp.usage.prompt_tokens if resp.usage else 0
        tout = resp.usage.completion_tokens if resp.usage else 0
        if trace is not None:
            trace.append({
                "name": "reflect",
                "response": raw[:300],
                "tokens": {"input": tin, "output": tout},
            })
        try:
            data = parse_json(raw)
            return data.get("additional_claims", [])[:2]
        except Exception:
            return []

    def _final_verdict(self, article_text: str, claim_results: list[dict],
                       trace: list | None = None) -> tuple[dict, dict]:
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
            temperature=0,
        )
        tin = resp.usage.prompt_tokens if resp.usage else 0
        tout = resp.usage.completion_tokens if resp.usage else 0
        raw = resp.choices[0].message.content or ""
        if trace is not None:
            trace.append({
                "name": "final_verdict",
                "response": raw[:500],
                "tokens": {"input": tin, "output": tout},
            })
        return parse_json(raw), {"input_tokens": tin, "output_tokens": tout}

    def analyze_article_staged(self, text: str, images: list[str] | None = None) -> tuple[dict, dict]:
        """Multi-stage article analysis: isolated per-claim verification + reflection.
        floor enforcement is done by analyzer.py::_enforce_bi_floor (outermost layer).
        """
        _dbg = make_entry("analyze_staged", {"text_len": len(text), "image_count": len(images or [])})
        try:
            from config.manager import load as _load_cfg
            cfg = _load_cfg()
            max_workers = cfg.get("staged_max_workers", 2)

            total = {"input_tokens": 0, "output_tokens": 0}

            # Stage 1: claim extraction (images sent only here)
            try:
                from ui.loading_overlay import update_stage
                update_stage("提取关键声明")
            except Exception:
                pass
            claims, s1_tokens = self._extract_claims(text, images, trace=_dbg["stages"])
            total["input_tokens"] += s1_tokens["input_tokens"]
            total["output_tokens"] += s1_tokens["output_tokens"]

            if isinstance(claims, dict):
                # Model returned full analysis in Stage 1 — use directly
                result = normalize_result(claims)
                result.setdefault("_search_log", [])
                result["_token_usage"] = total
                result["_path"] = "staged_shortcut"
                result["_mode"] = "analyze"
                token_dict = {"model": self._model, "input": total["input_tokens"], "output": total["output_tokens"]}
                _dbg["path"] = "staged_shortcut"
                set_result(_dbg, result, token_dict)
                return result, token_dict

            if not claims:
                _dbg["path"] = "classic_fallback"
                # analyze_article writes its own debug entry; finally will write staged entry
                result, token_dict = self.analyze_article(text)
                result["_path"] = "classic_fallback"
                set_result(_dbg, result, token_dict, "classic_fallback")
                return result, token_dict

            # Stage 2: parallel independent verification
            try:
                from ui.loading_overlay import update_stage
                update_stage("核查声明")
            except Exception:
                pass
            query_cache: dict = {}
            with ThreadPoolExecutor(max_workers=min(len(claims), max_workers)) as ex:
                claim_results = list(ex.map(
                    lambda c: self._verify_claim(c, text, query_cache, trace=_dbg["stages"]), claims
                ))
            for r in claim_results:
                t = r.pop("_tokens", {})
                total["input_tokens"] += t.get("input_tokens", 0)
                total["output_tokens"] += t.get("output_tokens", 0)

            # Stage 2.5: reflection
            try:
                from ui.loading_overlay import update_stage
                update_stage("交叉核查")
            except Exception:
                pass
            extra = self._reflect(text, claim_results, trace=_dbg["stages"])
            if extra:
                # Deduplicate against already-verified claims
                existing_texts = {r.get("claim", "") for r in claim_results}
                extra = [c for c in extra if (c if isinstance(c, str) else c.get("text", "")) not in existing_texts]
            if extra:
                with ThreadPoolExecutor(max_workers=min(len(extra), max_workers)) as ex:
                    extra_results = list(ex.map(
                        lambda c: self._verify_claim(c, text, query_cache, trace=_dbg["stages"]), extra
                    ))
                for r in extra_results:
                    t = r.pop("_tokens", {})
                    total["input_tokens"] += t.get("input_tokens", 0)
                    total["output_tokens"] += t.get("output_tokens", 0)
                claim_results.extend(extra_results)

            # Stage 3: final verdict (no tools, no images)
            try:
                from ui.loading_overlay import update_stage
                update_stage("综合分析中")
            except Exception:
                pass
            try:
                result_raw, vtokens = self._final_verdict(text, claim_results, trace=_dbg["stages"])
                total["input_tokens"] += vtokens["input_tokens"]
                total["output_tokens"] += vtokens["output_tokens"]
                # Filter malformed items (error results Stage 3 expanded into full header/radar_chart objects)
                if isinstance(result_raw, dict):
                    cvs = result_raw.get("claim_verification", [])
                    result_raw["claim_verification"] = [
                        cv for cv in cvs
                        if isinstance(cv, dict) and "header" not in cv and cv.get("claim")
                    ]
            except Exception as s3_err:
                # Stage 3 failed — assemble partial result from Stage 2 claim_results
                clean_cvs = [
                    {k: v for k, v in r.items() if not k.startswith("_")}
                    for r in claim_results if r.get("claim")
                ]
                result_raw = {"claim_verification": clean_cvs}
                _dbg.setdefault("warnings", []).append(f"stage3_failed: {s3_err}")
            result = normalize_result(result_raw)
            all_logs = []
            # Extract claim_types and original claim texts from Stage 2 results
            stage2_types: list[str] = []
            stage2_claims: list[str] = []
            for r in claim_results:
                all_logs.extend(r.pop("_search_log", []))
                stage2_types.append(r.get("claim_type", "fact"))
                stage2_claims.append(r.get("claim", ""))
            # Merge claim_type and restore truncated claim text by position
            final_cvs = result.get("claim_verification", [])
            for i, cv in enumerate(final_cvs):
                if not cv.get("claim_type"):
                    cv["claim_type"] = stage2_types[i] if i < len(stage2_types) else "fact"
                # Restore original claim text if Stage 3 truncated it
                if i < len(stage2_claims) and stage2_claims[i]:
                    orig = stage2_claims[i]
                    curr = cv.get("claim", "")
                    if len(curr) < len(orig) * 0.8:
                        cv["claim"] = orig
            result["_search_log"] = all_logs
            result["_token_usage"] = total
            result["_path"] = "staged_full"
            result["_mode"] = "analyze"

            token_dict = {"model": self._model, "input": total["input_tokens"], "output": total["output_tokens"]}
            _dbg["path"] = "staged_full"
            set_result(_dbg, result, token_dict)
            return result, token_dict
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
