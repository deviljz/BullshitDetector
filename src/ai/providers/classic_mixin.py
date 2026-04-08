"""
_ClassicMixin — classic (single-pass) analysis methods.
Mixed into OpenAICompatibleProvider; no __init__, uses self.* from the host class.
"""

import traceback

from ai.prompts import (
    get_system_prompt, get_article_prompt, get_summary_prompt,
    get_explain_prompt, get_explain_classify_prompt,
    get_source_prompt, get_source_classify_prompt,
    get_follow_up_prompt,
)
from ai.json_utils import parse_json, normalize_result
from ai.tools import TOOLS, SOURCE_TOOLS, execute_tool, set_source_image, get_last_vision_urls, get_last_vision_page_urls
from ai.debug_log import make_entry, set_result, write_entry

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


_VALID_BULLSHIT_NATURE = {"事实错误", "夸大渲染", "真实但离谱", "标题党", "断章取义", "逻辑混乱"}


def _analyze_schema_ok(parsed: dict) -> bool:
    inv = parsed.get("investigation_report", {})
    header = parsed.get("header", {})
    return (
        bool(inv.get("content_nature"))
        and parsed.get("claim_verification") is not None
        and header.get("bullshit_nature") in _VALID_BULLSHIT_NATURE
    )


class _ClassicMixin:
    """Classic single-pass analysis methods. No __init__."""

    # ── 截图/文章鉴定 ─────────────────────────────────────────────────────────

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
            from ai.providers.openai_compat import _error_result
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
            from ai.providers.openai_compat import _error_result
            return _error_result(f"{type(e).__name__}: {e}\n{traceback.format_exc()}"), self._zero_tokens()
        finally:
            if _write_debug:
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
            result["_vision_page_urls"] = page_urls if page_urls else []
            if not result.get("source_page_urls"):
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

    # ── 追问 ──────────────────────────────────────────────────────────────────

    def follow_up(self, context_text: str, history: list[dict], question: str, mode: str = "analyze") -> tuple[str, dict]:
        """Plain-text follow-up conversation (no tools). Returns (response, token_dict)."""
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
            resp = self._create_with_retry(
                model=self._model,
                messages=messages,
                max_tokens=4096,
            )
            tin = resp.usage.prompt_tokens if resp.usage else 0
            tout = resp.usage.completion_tokens if resp.usage else 0
            text = resp.choices[0].message.content or "（无回复）"
            token_dict = {"model": self._model, "input": tin, "output": tout}
            return text, token_dict
        except Exception as e:
            return f"追问失败：{type(e).__name__}: {e}", self._zero_tokens()
