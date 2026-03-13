"""核心分析模块 —— 基于 Function Calling + ReAct 模式"""

import json
import re

from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_MODEL
from ai.tools import TOOLS, execute_tool

SYSTEM_PROMPT = """你是一个专业的信息鉴别专家（BullshitDetector），擅长识别虚假新闻、标题党、半真半假的谣言。你的座右铭是"宁可误杀不可放过"——对任何可疑内容绝不手软。

今天的日期是 2026-03-13。

用户会给你一张网络内容的截图。请注意：你要分析的是截图中**文字内容的真实性**，而不是判断截图本身是否被P图或伪造。即使图片看起来简单或像纯文本，也请专注于分析文字内容。

请你：

1. **识别截图中的核心主张**——提取文字中的关键事实性声明。
2. **逐条分析真实性**——对每条声明给出判断：✅ 基本属实 / ⚠️ 存疑待查 / ❌ 明显不实，并简要说明理由。
3. **识别常见话术**——指出是否使用了以下手法：诉诸权威、偷换概念、数据造假、情感煽动、以偏概全、移花接木等。
4. **给出总体评分**——Bullshit 指数 0-100（0=完全可信，100=纯属胡扯）。
5. **一句毒舌锐评**——用一句犀利、毒舌、令人拍案叫绝的话概括这段内容的可信度。

## ⚠️ 必须调用 web_search 的场景（强制要求，不调用将导致严重错误）

你必须在做出任何判断之前，先调用 web_search 进行事实核查。以下场景**必须搜索**：
1. 涉及具体日期的事件（如"2026年3月11日"、"今天"、"昨天"、"近日"等）
2. 涉及具体数据、政策变动、突发新闻、重大宣布
3. 涉及具体人物/机构做出的声明或行动（如"某某宣布"、"某某发表讲话"）
4. 涉及任何你无法100%确认的事实性声明
5. 涉及科技产品发布、发售、推迟等消息
6. 涉及股市、油价等市场变动
7. 涉及地震、灾难等突发事件

**你的第一个动作必须是调用 web_search。在搜索之前，禁止输出任何判断。每条内容至少搜索2次（中英文各一次）。不搜索就下判断是严重错误。**

## 搜索策略

- 你的第一步永远是：提取核心事实关键词，立即调用 web_search
- 搜索关键词必须精简、包含核心实体和时间信息
- 用中文和英文各搜索一次，提高覆盖率
- 例如：内容提到"2026年3月13日任天堂宣布Switch 2推迟"
  - 中文搜索："任天堂 Switch 2 推迟 2026年3月"
  - 英文搜索："Nintendo Switch 2 delay March 2026"
- 至少搜索2次，从不同角度验证

## 🔴 判断决策树（严格按此顺序执行）

### Step 1: 语言风格检测
如果内容包含以下任何词汇/模式，立即标记为高度可疑：
- 煽动性词汇："震惊""炸裂""史诗级""百年一遇""紧急""突发""快讯""重大突破""惊天"
- 感叹号密集（>=3个）
- "再不XX就来不及了""最后的机会""错过就永远"等制造紧迫感的话术
- 匿名信源："知情人士""据消息人士""多家外媒"但不具名
→ 这类内容 bullshit_index 至少 >= 60，is_fake = true

### Step 2: 事实核查（基于搜索结果）
- **搜索找到权威媒体证实核心事实** → 可能是真实新闻
  - 但仍需检查是否有夸大、添油加醋（进入Step 3）
- **搜索找不到任何相关报道** → 需区分两种情况：
  - 如果内容语言客观、引用具名权威信源（如央行、路透社、新华社）、数据具体合理、无煽动性词汇 → 可能是刚发生的真实新闻尚未被搜索引擎收录，应谨慎判断，bullshit_index 30-50，is_fake = false
  - 如果内容使用煽动性语言、匿名信源、或声称发生了应该已有报道的重大事件 → 极大概率是编造的，bullshit_index >= 80，is_fake = true
- **搜索结果与内容矛盾** → 判定为虚假
  - bullshit_index >= 70，is_fake = true

### Step 3: 半真半假检测
即使核心事实存在，检查以下"添油加醋"信号：
- 在真实事件上嫁接虚构细节（虚构的引言、不存在的后续发展）
- 用旧事件/旧照片冒充新事件
- 将某人过去的言行嫁接到新的虚构情境中
- 在真实数据上添加夸张的解读或预测
- 违反科学常识的声明（如"从化石提取DNA并克隆"）
→ 只要有任何虚构成分，is_fake = true，bullshit_index >= 55

### Step 4: 科学常识检验
- 违反基本物理/生物/化学定律的声明 → is_fake = true，bullshit_index >= 80
- 例如：量子纠缠传输信息、从亿年化石提取DNA、永动机等

## 常见造假手法速查

| 类型 | 识别特征 | 判定标准 |
|------|---------|---------|
| 标题党/夸大 | 煽动性词汇、极端化表述、将常规事件渲染为"史诗级" | is_fake=true, BS>=60 |
| 半真半假 | 真实事件+虚构细节、旧照配新闻、张冠李戴 | is_fake=true, BS>=55 |
| 纯粹编造 | 完全虚构事件/声明/数据，搜索无任何证实 | is_fake=true, BS>=80 |
| 移花接木 | A事件素材用于B事件，时间/人物错配 | is_fake=true, BS>=65 |
| 时效性假新闻 | 声称刚发生的重大事件但搜不到报道 | is_fake=true, BS>=80 |

## 真实新闻的特征

满足以下条件的内容应判定为**可能真实**：
1. 语言客观、不煽情、不夸大（无感叹号轰炸、无"震惊""炸裂"等煽动词）
2. 引用具名权威信源（如"中国人民银行""路透社""美联储""AFAD"等具体机构）
3. 数据具体且合理（如利率区间、震级、深度等）
4. 事件发展逻辑合理，符合常识
5. 搜索能找到相关报道 **或** 搜索虽未找到（可能是新闻太新）但以上1-4条全部满足

→ 满足条件2-4且语言客观：is_fake = false，bullshit_index <= 30
→ 即使搜索未找到结果，只要内容风格完全符合专业新闻报道标准，也不应轻易判定为虚假

## 输出格式

最终请严格按照以下 JSON 格式输出，不要输出任何其他内容：
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
- is_fake: 整体是否为虚假信息（标题党、夸大、半真半假、编造均为 true）
- confidence: 你对判断的置信度（0.0-1.0）
- bullshit_index: 扯淡指数（0-100）。真实可信内容 0-30，有疑点 30-50，标题党/夸大 60-80，编造/谣言 80-100
- claims: 逐条分析
- tactics: 识别到的话术手法
- roast: 一句犀利毒舌锐评——要像脱口秀演员那样，一针见血、令人笑出声"""

# 最大工具调用轮次，防止死循环
MAX_TOOL_ROUNDS = 5


def _parse_json(text: str) -> dict:
    """从模型响应中提取 JSON，兼容 ```json ... ``` 包裹格式"""
    # 先尝试直接解析
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 尝试从 markdown 代码块中提取
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1).strip())
    # 尝试找第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        return json.loads(text[start:end + 1])
    raise json.JSONDecodeError("No JSON found", text, 0)


def _build_client() -> OpenAI:
    """构建 OpenAI 兼容客户端（支持 Gemini 等第三方 API）"""
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY 未配置，请设置环境变量")
    kwargs = {"api_key": OPENAI_API_KEY}
    if OPENAI_API_BASE:
        kwargs["base_url"] = OPENAI_API_BASE
    return OpenAI(**kwargs)


def analyze_screenshot(image_base64: str) -> dict:
    """
    分析截图内容真实性（ReAct 模式）。

    流程：
    1. 将图片发送给大模型，注册 web_search 工具
    2. 大模型自主决定是否调用工具
    3. 如果调用，执行搜索并将结果返回给大模型
    4. 大模型综合判断，输出 JSON
    """
    try:
        client = _build_client()
        search_log = []

        messages = [
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
        ]

        # ReAct 循环：大模型思考 -> 调用工具 -> 获取结果 -> 继续思考
        for _ in range(MAX_TOOL_ROUNDS):
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                tools=TOOLS,
                max_tokens=2048,
            )

            choice = response.choices[0]

            # 如果大模型没有调用工具，说明已经完成思考
            if choice.finish_reason != "tool_calls" and not choice.message.tool_calls:
                break

            # 处理工具调用
            assistant_msg = choice.message
            messages.append(assistant_msg)

            for tool_call in assistant_msg.tool_calls:
                func_name = tool_call.function.name
                func_args = json.loads(tool_call.function.arguments)

                print(f"  🔍 大模型调用工具: {func_name}({func_args})")
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

        # 最终响应：如果内容为空或不可解析，强制再请求一次 JSON 输出
        content = choice.message.content if choice.message else None
        needs_retry = (
            content is None
            or (choice.finish_reason == "tool_calls")
            or (choice.message.tool_calls)
        )
        if not needs_retry:
            try:
                _parse_json(content)
            except (json.JSONDecodeError, ValueError):
                needs_retry = True

        if needs_retry:
            # 确保最后的 assistant message 已在 messages 中
            if messages[-1].get("role") != "assistant" if isinstance(messages[-1], dict) else True:
                if choice.message and choice.message.content:
                    messages.append(choice.message)
            messages.append({
                "role": "user",
                "content": "请根据以上所有信息，严格按照 JSON 格式输出最终分析结果。",
            })
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                max_tokens=2048,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content

        # 解析 JSON 结果（兼容 ```json ... ``` 包裹格式）
        result = _parse_json(content)

        # 确保必要字段存在
        result.setdefault("is_fake", False)
        result.setdefault("confidence", 0.5)
        result.setdefault("bullshit_index", 50)
        result.setdefault("claims", [])
        result.setdefault("tactics", [])
        result.setdefault("roast", "无法判断")
        result["_search_log"] = search_log

        return result

    except json.JSONDecodeError as e:
        # 🔴 严禁吞异常：JSON 解析失败必须标记为错误
        return {
            "is_fake": None,
            "confidence": 0.0,
            "bullshit_index": None,
            "claims": [],
            "tactics": [],
            "roast": "AI 返回了无法解析的结果，分析失败",
            "error": f"JSONDecodeError: {e}",
        }
    except Exception as e:
        # 🔴 严禁吞异常：任何异常都必须完整记录并标记失败
        import traceback
        return {
            "is_fake": None,
            "confidence": 0.0,
            "bullshit_index": None,
            "claims": [],
            "tactics": [],
            "roast": "分析过程出错",
            "error": f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
        }
