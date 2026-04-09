"""Function Calling 工具定义 + 搜索执行（支持 DuckDuckGo / Tavily / Google Vision）"""

from typing import List

# 求出处模式临时存放当前图片 base64（单用户桌面应用，无并发问题）
_current_image_b64: str | None = None
_last_vision_urls: list[str] = []
_last_vision_page_urls: list[dict] = []  # [{"title": str, "url": str}, ...]


def set_source_image(b64: str | None) -> None:
    global _current_image_b64, _last_vision_urls, _last_vision_page_urls
    _current_image_b64 = b64
    _last_vision_urls = []
    _last_vision_page_urls = []


def get_last_vision_urls() -> list[str]:
    return list(_last_vision_urls)


def get_last_vision_page_urls() -> list[dict]:
    return list(_last_vision_page_urls)


def _search_ddg(query: str, max_results: int = 5) -> List[dict]:
    try:
        from ddgs import DDGS
        with DDGS(timeout=15) as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            return [
                {"title": r["title"], "snippet": r["body"], "url": r["href"]}
                for r in results
            ]
    except Exception as e:
        return [{"error": f"DuckDuckGo 搜索失败（可能需要代理）: {e}"}]


def _search_tavily(query: str, api_key: str, max_results: int = 5) -> List[dict]:
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        resp = client.search(query, max_results=max_results)
        return [
            {"title": r.get("title", ""), "snippet": r.get("content", ""), "url": r.get("url", "")}
            for r in resp.get("results", [])
        ]
    except Exception as e:
        return [{"error": f"Tavily 搜索失败: {e}"}]


def _search_bailian(query: str, api_key: str, max_results: int = 5) -> List[dict]:
    """百炼 WebSearch MCP 搜索（国内直连，中文优化）。"""
    try:
        import requests as _req
        import json as _json

        url = "https://dashscope.aliyuncs.com/api/v1/mcps/WebSearch/mcp"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        def _post(payload):
            r = _req.post(url, headers=headers, json=payload, timeout=20)
            r.raise_for_status()
            # MCP 可能返回 SSE 流或单条 JSON，统一处理
            text = r.text.strip()
            # SSE 格式: "data: {...}\n\n"
            if text.startswith("data:"):
                line = [l for l in text.splitlines() if l.startswith("data:")][-1]
                text = line[len("data:"):].strip()
            return _json.loads(text)

        # Step 1: Initialize
        _post({
            "jsonrpc": "2.0", "id": 0, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "BullshitDetector", "version": "1.0"},
            },
        })

        # Step 2: Notify initialized
        _req.post(url, headers=headers, json={
            "jsonrpc": "2.0", "method": "notifications/initialized",
        }, timeout=10)

        # Step 3: Call search tool
        resp = _post({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {
                "name": "bailian_web_search",
                "arguments": {"query": query, "count": max_results},
            },
        })

        # Parse MCP content
        content = resp.get("result", {}).get("content", [])
        raw_text = ""
        for block in content:
            if block.get("type") == "text":
                raw_text += block.get("text", "")

        # Content may be JSON array of results or plain text
        try:
            items = _json.loads(raw_text)
            if isinstance(items, list):
                return [
                    {
                        "title": r.get("title", ""),
                        "snippet": r.get("snippet", r.get("content", r.get("abstract", ""))),
                        "url": r.get("url", r.get("link", "")),
                    }
                    for r in items[:max_results] if isinstance(r, dict)
                ]
        except Exception:
            pass

        # Fallback: return raw text as single result
        if raw_text:
            return [{"title": "百炼搜索结果", "snippet": raw_text[:500], "url": ""}]
        return [{"error": "百炼搜索未返回结果"}]

    except Exception as e:
        return [{"error": f"百炼搜索失败: {e}"}]


_TAVILY_QUOTA_PATTERNS = ("usage limit", "exceeds your plan", "upgrade your plan", "quota exceeded")
_tavily_quota_exhausted: bool = False  # 运行期 flag：Tavily 配额耗尽后直接走 DDG


class SearchProvider:
    """搜索引擎门面，根据 config 自动选择 DDG / Tavily / 百炼。"""

    def search(self, query: str, max_results: int = 5) -> List[dict]:
        global _tavily_quota_exhausted
        from config.manager import load as _load_cfg
        cfg = _load_cfg()
        provider = cfg.get("search_provider", "ddg")
        if provider == "tavily":
            key = cfg.get("tavily_api_key", "")
            if not key or key.startswith("tvly-xxx"):
                return [{"error": "Tavily API Key 未配置，请在 config.json 中填写 tavily_api_key"}]
            if not _tavily_quota_exhausted:
                results = _search_tavily(query, key, max_results)
                if results and "error" in results[0]:
                    err = results[0].get("error", "")
                    if any(p in err for p in _TAVILY_QUOTA_PATTERNS):
                        _tavily_quota_exhausted = True
                        try:
                            print("  [!] Tavily 配额耗尽，本次运行自动切换至 DuckDuckGo")
                        except Exception:
                            pass
                        return _search_ddg(query, max_results)
                return results
            # 配额已耗尽，本次运行直接走 DDG
            return _search_ddg(query, max_results)
        if provider == "bailian":
            key = cfg.get("bailian_api_key", "")
            if not key:
                return [{"error": "百炼 API Key 未配置，请在 config.json 中填写 bailian_api_key"}]
            return _search_bailian(query, key, max_results)
        return _search_ddg(query, max_results)


def _reverse_image_search_vision(image_b64: str, api_key: str) -> str:
    """调用 Google Vision WEB_DETECTION 以图搜图。"""
    import requests as _req
    payload = {
        "requests": [{
            "image": {"content": image_b64},
            "features": [{"type": "WEB_DETECTION", "maxResults": 10}],
        }]
    }
    try:
        resp = _req.post(
            f"https://vision.googleapis.com/v1/images:annotate?key={api_key}",
            json=payload, timeout=30,
        )
        if resp.status_code != 200:
            return f"Vision API 错误: {resp.status_code} {resp.text[:200]}"
        det = resp.json()["responses"][0].get("webDetection", {})
    except Exception as e:
        return f"Vision API 请求失败: {e}"

    lines = []
    entities = det.get("webEntities", [])
    if entities:
        lines.append("【作品名候选】")
        for e in entities[:6]:
            if e.get("description"):
                lines.append(f"  [{e.get('score', 0):.2f}] {e['description']}")
    pages = det.get("pagesWithMatchingImages", [])
    global _last_vision_page_urls
    if pages:
        lines.append(f"\n【匹配页面（{len(pages)} 条）】")
        for p in pages[:5]:
            title = p.get("pageTitle", "").strip()
            url = p.get("url", "")
            lines.append(f"  {title} — {url}" if title else f"  {url}")
        _last_vision_page_urls = [
            {"title": p.get("pageTitle", "").strip(), "url": p.get("url", "")}
            for p in pages[:5] if p.get("url")
        ]
    # 参考图：只取精确/部分匹配，视觉相似仅作文字提示不作参考图
    global _last_vision_urls
    full_match = det.get("fullMatchingImages", [])
    partial_match = det.get("partialMatchingImages", [])
    visual_similar = det.get("visuallySimilarImages", [])
    display_pool = full_match or partial_match  # 仅精确/部分匹配才显示为参考图
    if display_pool:
        _last_vision_urls = [s["url"] for s in display_pool[:3] if s.get("url")]
        match_type = "精确匹配" if full_match else "部分匹配"
        lines.append(f"\n【参考图片（{match_type}，{len(display_pool)} 条）】")
        for url in _last_vision_urls:
            lines.append(f"  {url}")
    else:
        _last_vision_urls = []
    if visual_similar and not display_pool:
        lines.append(f"\n【视觉相似图片（仅供参考，{len(visual_similar)} 条，不代表同一作品）】")
        for s in visual_similar[:3]:
            if s.get("url"):
                lines.append(f"  {s['url']}")
    return "\n".join(lines) if lines else "未找到匹配结果"


# 注册给大模型的工具定义
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "搜索网络获取最新信息。用于验证时效性新闻、数据、事件、政策等事实性声明。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "精简的搜索关键词",
                    }
                },
                "required": ["query"],
            },
        },
    }
]

# 求出处专用工具集（含以图搜图）
SOURCE_TOOLS = [
    TOOLS[0],  # web_search
    {
        "type": "function",
        "function": {
            "name": "reverse_image_search",
            "description": (
                "对当前图片进行以图搜图，识别作品来源。"
                "返回匹配的网页标题和 URL、以及作品名候选列表。"
                "在视觉识别不确定时优先调用此工具。"
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

# Plan-and-Execute 外层 Agent 工具集
PLAN_EXECUTE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "verify_claim",
            "description": "核查文章中的一条具体事实性声明。工具内部会自动搜索相关证据并返回核查结论。适用于含具体数字、人名、事件的声明；主观观点和无法核查的预测不需要核查。",
            "parameters": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string", "description": "待核查的声明原文"},
                    "claim_type": {"type": "string", "enum": ["fact", "narrative"], "description": "fact：含具体数字/人名/事件可直接搜索；narrative：因果/评价类隐含论点"},
                    "is_core_claim": {"type": "boolean", "description": "该声明是否直接支撑文章核心结论？true=核心声明（若为假则核心结论崩塌）；false=边角细节（若为假不影响整体结论）"},
                    "context": {"type": "string", "description": "声明所在文章的标题和核心背景（100字以内）"},
                },
                "required": ["claim", "claim_type", "is_core_claim"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_title_logic",
            "description": "检查标题是否存在因果谬误或用无关数据背书核心论点。适用于标题含'因为X所以Y'、'凭借X实现Y'等逻辑链条的文章。简单陈述类标题无需调用。若内容本身没有标题（如纯截图、纯正文），禁止调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_hype",
            "description": "检查文章是否存在夸大表述：第三方估算被当作事实陈述、含'最''首''唯一'等绝对化表述。含大量财务数据或极端形容词时调用。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_verdict",
            "description": "完成所有必要核查后提交最终结论。调用此工具将立即结束分析流程。请确认已核查所有重要声明后再调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "claim_verification": {
                        "type": "array",
                        "description": "所有已核查声明的结果列表（从 verify_claim 工具返回结果中收集，原样复制，禁止修改数字和判断）",
                        "items": {
                            "type": "object",
                            "properties": {
                                "claim": {"type": "string"},
                                "claim_type": {"type": "string"},
                                "is_core_claim": {"type": "boolean"},
                                "verdict": {"type": "string"},
                                "effective_sources": {"type": "integer"},
                                "best_source_type": {"type": "string"},
                                "source_genealogy": {"type": "string"},
                                "note": {"type": "string"},
                            },
                        },
                    },
                    "investigation_report": {
                        "type": "object",
                        "description": "综合调查报告，包含标题逻辑和夸大程度分析结果（从工具返回结果中收集）",
                        "properties": {
                            "title_logic_check": {"type": "object"},
                            "hype_check": {"type": "object"},
                            "caveats": {"type": "array", "items": {"type": "string"}, "description": "重要补充说明（如信息来源单一、时效性限制等），可为空数组"},
                        },
                    },
                    "one_line_summary": {"type": "string", "description": "一句话概括文章核心问题（≤30字）"},
                    "toxic_review": {"type": "string", "description": "鉴屎官风格的辛辣评语（根据文章实际质量，好文章也可以给正面评价）"},
                    "verdict_text": {"type": "string", "description": "最终判决陈述（2-3句话，概括核查发现）"},
                    "bullshit_nature": {
                        "type": "string",
                        "enum": ["事实错误", "局部失实", "基本属实", "夸大渲染",
                                 "真实但离谱", "标题党", "断章取义", "逻辑混乱"],
                        "description": "内容性质八选一，参照 claim_verification 结论综合判断",
                    },
                    "flaw_list": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "核心破绽列表，每条≤20字，最多5条；确实无破绽则填[]",
                    },
                },
                "required": ["claim_verification", "one_line_summary", "verdict_text"],
            },
        },
    },
]

# Planner 阶段只能调用 verify_claim（强制提取核查清单）
PLANNER_TOOLS = [t for t in PLAN_EXECUTE_TOOLS if t["function"]["name"] == "verify_claim"]

# 内部工具：仅在 _check_title_logic / _check_hype 中使用，不暴露给 re-planner
SUBMIT_TITLE_LOGIC_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_title_logic",
        "description": "提交标题逻辑核查结果",
        "parameters": {
            "type": "object",
            "required": ["verdict"],
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": ["有问题", "无问题"],
                    "description": "有问题=标题存在因果谬误或严重夸大；无问题=标题与正文一致",
                },
                "reason": {"type": "string", "description": "简要说明，≤50字"},
            },
        },
    },
}

SUBMIT_HYPE_TOOL = {
    "type": "function",
    "function": {
        "name": "submit_hype_check",
        "description": "提交夸大渲染核查结果",
        "parameters": {
            "type": "object",
            "required": ["verdict"],
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": ["有夸大", "无夸大"],
                    "description": "有夸大=核心叙述被夸大渲染；无夸大=表述克制",
                },
                "type": {
                    "type": "string",
                    "enum": ["数字虚报", "程度夸大", "第三方估算当事实", "情绪渲染", "无"],
                    "description": "夸大类型，无夸大时填'无'",
                },
                "reason": {"type": "string", "description": "简要说明，≤50字"},
            },
        },
    },
}

# 全局搜索实例
_search_provider = SearchProvider()


def execute_tool(name: str, arguments: dict) -> str:
    """执行工具调用，返回结果文本"""
    if name == "web_search":
        query = arguments.get("query", "")
        results = _search_provider.search(query)
        if results and "error" in results[0]:
            return results[0]["error"]
        if not results:
            return "未找到相关搜索结果"
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}\n   {r['snippet']}\n   来源: {r['url']}")
        return "\n".join(lines)

    if name == "reverse_image_search":
        if not _current_image_b64:
            return "当前没有图片可供搜索"
        from config.manager import load as _load_cfg
        api_key = _load_cfg().get("google_vision_api_key", "")
        if not api_key or api_key.startswith("AIzaSy-YOUR"):
            return "Google Vision API Key 未配置，请在 config.json 中填写 google_vision_api_key"
        return _reverse_image_search_vision(_current_image_b64, api_key)

    return f"未知工具: {name}"
