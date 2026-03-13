import json

from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_MODEL
from ai.search import search_news, format_search_results

SYSTEM_PROMPT = """你是一个专业的信息真实性分析专家（BullshitDetector）。
用户会给你一张网络内容的截图，请你：

1. **识别截图中的核心主张**——提取文字中的关键事实性声明。
2. **逐条分析真实性**——对每条声明给出判断：✅ 基本属实 / ⚠️ 存疑待查 / ❌ 明显不实，并简要说明理由。
3. **识别常见话术**——指出是否使用了以下手法：诉诸权威、偷换概念、数据造假、情感煽动、以偏概全等。
4. **给出总体评分**——Bullshit 指数 0-100（0=完全可信，100=纯属胡扯）。
5. **一句毒舌锐评**——用一句犀利、毒舌的话概括这段内容的可信度。

你必须严格按照以下 JSON 格式回复，不要输出任何其他内容：
{
  "is_fake": true/false,
  "confidence": 0.0-1.0,
  "bullshit_index": 0-100,
  "claims": [
    {"claim": "...", "verdict": "✅/⚠️/❌", "reason": "..."}
  ],
  "tactics": ["话术1", "话术2"],
  "roast": "一句毒舌锐评"
}

其中：
- is_fake: 整体是否为虚假信息
- confidence: 你对判断的置信度（0.0-1.0）
- bullshit_index: 扯淡指数（0-100）
- claims: 逐条分析
- tactics: 识别到的话术手法
- roast: 一句毒舌锐评，要犀利、有趣"""

EXTRACT_PROMPT = """请提取这张截图中的关键事实性声明和主要话题，用简短的关键词概括，方便用于搜索引擎查询。
只输出搜索关键词，不要其他内容。如果图片中没有明确的事实性声明或新闻事件，请回复"无需搜索"。"""


def _build_client() -> OpenAI:
    """构建 OpenAI 兼容客户端（支持 Gemini 等第三方 API）"""
    kwargs = {"api_key": OPENAI_API_KEY}
    if OPENAI_API_BASE:
        kwargs["base_url"] = OPENAI_API_BASE
    return OpenAI(**kwargs)


def _extract_search_query(client: OpenAI, image_base64: str) -> str:
    """从截图中提取搜索关键词"""
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": EXTRACT_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_base64}",
                            },
                        },
                    ],
                },
            ],
            max_tokens=100,
        )
        query = response.choices[0].message.content.strip()
        if "无需搜索" in query:
            return ""
        return query
    except Exception:
        return ""


def analyze_screenshot(image_base64: str) -> dict:
    """分析截图内容真实性，返回结构化 JSON 结果。"""
    try:
        client = _build_client()

        # Step 1: 提取搜索关键词
        search_query = _extract_search_query(client, image_base64)

        # Step 2: 搜索验证（如果有关键词）
        search_context = ""
        if search_query:
            results = search_news(search_query)
            search_context = format_search_results(results)

        # Step 3: 结合搜索结果进行分析
        user_content = [
            {"type": "text", "text": "请分析这张截图中的内容真实性："},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{image_base64}",
                },
            },
        ]

        if search_context:
            user_content.append({
                "type": "text",
                "text": f"\n\n以下是关于截图内容的网络搜索结果，请结合这些信息进行判断：\n{search_context}",
            })

        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=2048,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        result = json.loads(content)

        # 确保必要字段存在
        result.setdefault("is_fake", False)
        result.setdefault("confidence", 0.5)
        result.setdefault("bullshit_index", 50)
        result.setdefault("claims", [])
        result.setdefault("tactics", [])
        result.setdefault("roast", "无法判断")

        return result

    except json.JSONDecodeError:
        return {
            "is_fake": False,
            "confidence": 0.0,
            "bullshit_index": 0,
            "claims": [],
            "tactics": [],
            "roast": "AI 返回了无法解析的结果，这本身就很可疑 🤔",
            "error": "JSON 解析失败",
        }
    except Exception as e:
        return {
            "is_fake": False,
            "confidence": 0.0,
            "bullshit_index": 0,
            "claims": [],
            "tactics": [],
            "roast": "分析过程翻车了，比假新闻还离谱 💀",
            "error": f"{type(e).__name__}: 分析请求失败",
        }
