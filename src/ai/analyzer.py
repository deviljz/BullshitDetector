from openai import OpenAI
from src.config import OPENAI_API_KEY, OPENAI_MODEL

SYSTEM_PROMPT = """你是一个专业的信息真实性分析专家（BullshitDetector）。
用户会给你一张网络内容的截图，请你：

1. **识别截图中的核心主张**——提取文字中的关键事实性声明。
2. **逐条分析真实性**——对每条声明给出判断：✅ 基本属实 / ⚠️ 存疑待查 / ❌ 明显不实，并简要说明理由。
3. **识别常见话术**——指出是否使用了以下手法：诉诸权威、偷换概念、数据造假、情感煽动、以偏概全等。
4. **给出总体评分**——Bullshit 指数 0-100（0=完全可信，100=纯属胡扯）。
5. **一句话总结**——用一句话概括这段内容的可信度。

回复请使用中文，格式清晰易读。"""


def analyze_screenshot(image_base64: str) -> str:
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "请分析这张截图中的内容真实性："},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}",
                        },
                    },
                ],
            },
        ],
        max_tokens=2048,
    )
    return response.choices[0].message.content
