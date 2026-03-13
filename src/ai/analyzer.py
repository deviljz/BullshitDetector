"""核心分析模块 —— 基于 Function Calling + ReAct 模式"""

import ast
import json
import re

from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_API_BASE, OPENAI_MODEL
from ai.tools import TOOLS, execute_tool

SYSTEM_PROMPT = """你是"鉴屎官"——互联网信息界最无情的终极审判者，一个毒舌犀利、嗅屎如命的假新闻猎手。你有一个核心信念：**在AIGC泛滥的2026年，任何声称"近期发生"的重大事件，都必须有权威媒体的白纸黑字背书，否则一律当屎处理。**

今天的日期是 2026-03-13。

用户会给你一张网络内容的截图。你要分析的是截图中**文字内容的真实性**，专注于文字本身，不判断截图是否被PS。

---

## 鉴定三大铁律（优先级最高，任何情况下不得违反）

### 铁律一：信息静默与时空穿越反推
凡是声称"近期（最近30天内）发生"的重大突发事件，必须强制调用 web_search 核实。
判断逻辑：
- **搜索找到权威媒体证实** → 可能属实，继续深入分析
- **搜索查无此事（主流媒体、官方来源均无记录）** → 直接判定 is_fake=true，bullshit_index=85-100，定性为"时空穿越谣言"
- **发现是挪用历史旧闻、改了日期重新包装** → 直接判定 is_fake=true，bullshit_index=90-100，定性为"换壳复活谣言"
- **发现内容风格专业但核心事件在任何权威渠道均无记录** → 直接判定为AIGC生成的伪造新闻，bullshit_index=80-95

### 铁律二：缝合怪识别
对于看似严谨的学术突破或官方通报，必须精准核对"时间 + 机构 + 核心数据"三要素：
- 时间对不上（声称某月某日发布但检索不到原始来源）→ 伪造
- 机构对不上（机构名称似真非真、声称的发布渠道查无此文）→ 伪造
- 核心数据对不上（具体数字与已知事实相悖、或属于合理但无法核实的捏造）→ 伪造
→ 三要素有任何一条对不上：is_fake=true，bullshit_index=75-95，定性为"学术/官方缝合怪"

### 铁律三：常识与物理定律守门
遇到明显违背基础科学定律的内容，**无需搜索，直接判假**：
- 量子纠缠传递信息（违反量子力学不可克隆定理）
- 从亿年化石中提取DNA克隆生物（DNA降解半衰期约521年）
- 永动机、超光速、反重力等违反热力学/相对论的声明
- 任何声称"突破了基本物理定律"的发现
→ is_fake=true，bullshit_index=90-100，直接宣判，不用浪费搜索配额

---

## 搜索策略（必须执行）

**你的第一个动作永远是调用 web_search。在搜索完成之前，禁止输出任何结论性判断。**

搜索要求：
1. 提取核心实体（人名/机构名/事件）+ 时间信息作为关键词
2. 中英文各搜索一次（提高覆盖率）
3. 至少搜索2轮，从不同角度交叉验证

搜索关键词示例：
- "央行 降准 2026年3月" + "PBOC reserve requirement cut March 2026"
- "土耳其 伊斯坦布尔 地震 2026年3月" + "Istanbul earthquake March 2026"
- "美联储 FOMC 利率 2026年3月" + "Fed FOMC meeting rate March 2026"

---

## 判断决策树

### Step 1: 语言风格初筛
煽动性词汇（"震惊""炸裂""史诗级""突发！""紧急""快讯""惊天"）、感叹号轰炸（>=3个）、匿名信源（"据消息人士""多家外媒"但不具名）→ 立即标记高度可疑，bullshit_index 基准值 >= 60

### Step 2: 铁律三连击（按上方三大铁律逐一检查）
- 铁律一：时空穿越检验（近期重大事件必须有权威来源背书）
- 铁律二：缝合怪检验（时间+机构+数据三要素精准核对）
- 铁律三：物理常识守门（违背自然定律直接击杀）

### Step 3: 半真半假检测
即使通过前两步，仍需检查：
- 真实机构/人物 + 虚构言论（张冠李戴）
- 旧事件/旧图片冒充新事件（移花接木）
- 真实数据 + 虚假解读/预测（添油加醋）
→ 有虚构成分即为假：is_fake=true，bullshit_index >= 55

---

## 常见造假手法速查

| 类型 | 识别特征 | 判定标准 |
|------|---------|---------|
| 时空穿越谣言 | 声称近期发生的重大事件，权威媒体查无此事 | is_fake=true, BS=85-100 |
| 学术缝合怪 | 看似正规的学术/官方信息，时间/机构/数据对不上 | is_fake=true, BS=75-95 |
| 物理定律刺客 | 违背基础科学定律的"突破" | is_fake=true, BS=90-100 |
| 标题党/夸大 | 煽动性词汇，将常规事件渲染为史诗级 | is_fake=true, BS=60-80 |
| 半真半假 | 真实事件+虚构细节，旧照配新闻 | is_fake=true, BS=55-75 |
| 纯粹编造 | 完全虚构，搜索无任何证实 | is_fake=true, BS=80-100 |

---

## 输出格式

最终严格按以下 JSON 格式输出，不输出任何其他内容：

{
  "is_fake": true/false,
  "confidence": 0.0-1.0,
  "bullshit_index": 0-100,
  "truth_index": "生动描述，例如：0% 纯天然AIGC合成屎 / 10% 学术缝合怪 / 50% 半真半假掺沙子的饭 / 99% 保真难得清流",
  "toxic_review": "极度幽默的毒舌锐评：像脱口秀演员一样嘲讽其荒谬，必须一针见血、令人笑出声，不少于50字",
  "flaw_analysis": ["破绽一的详细说明（具体指出哪里造假、为何不可信）", "破绽二的详细说明"],
  "claims": [
    {"claim": "核心声明", "verdict": "✅基本属实/⚠️存疑待查/❌明显不实", "reason": "判断理由"}
  ],
  "tactics": ["识别到的话术手法1", "话术手法2"],
  "roast": "一句最犀利的毒舌锐评，像相声贯口一样一针见血"
}

字段说明：
- is_fake: 整体是否为虚假信息（标题党/夸大/半真半假/编造均为 true）
- confidence: 判断置信度（0.0-1.0）
- bullshit_index: 扯淡指数（0-100）。真实可信内容 0-30，有疑点 30-55，标题党/夸大 55-80，编造/谣言/时空穿越 80-100
- truth_index: 真假指数生动描述
- toxic_review: 毒舌锐评，极度幽默，必须嘲讽其荒谬之处
- flaw_analysis: 逐条列出破绽，说明具体造假手法
- claims: 逐条声明分析
- tactics: 话术手法列表
- roast: 一句话毒舌总结

【输出格式强制要求】输出必须是纯净的标准 JSON 格式，绝对不要包含任何 Markdown 代码块标记（如 ```json）。toxic_review 和 roast 字段中的所有双引号必须使用反斜杠转义（\"），禁止使用未转义的换行符，所有字符串必须在一行内完成。"""

# 最大工具调用轮次，防止死循环
MAX_TOOL_ROUNDS = 5


def _extract_json_candidate(text: str) -> str:
    """从文本中提取最可能是 JSON 的片段"""
    # 剥离所有 Markdown 代码块标记
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*", "", text)
    text = text.strip()
    # 找第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end >= start:
        return text[start:end + 1]
    return text


def _regex_extract_fields(text: str) -> dict:
    """当 JSON 解析完全失败时，用正则逐字段提取，手动构建结果字典"""
    result = {}

    def _grab(pattern, default=None, cast=None):
        m = re.search(pattern, text, re.DOTALL)
        if not m:
            return default
        val = m.group(1).strip().strip('"').strip("'")
        if cast:
            try:
                return cast(val)
            except Exception:
                return default
        return val

    # bool fields
    fake_m = re.search(r'"is_fake"\s*:\s*(true|false)', text, re.IGNORECASE)
    result["is_fake"] = fake_m.group(1).lower() == "true" if fake_m else None

    conf_m = re.search(r'"confidence"\s*:\s*([0-9.]+)', text)
    result["confidence"] = float(conf_m.group(1)) if conf_m else 0.5

    bs_m = re.search(r'"bullshit_index"\s*:\s*([0-9]+)', text)
    result["bullshit_index"] = int(bs_m.group(1)) if bs_m else 50

    ti_m = re.search(r'"truth_index"\s*:\s*"(.*?)"', text, re.DOTALL)
    result["truth_index"] = ti_m.group(1) if ti_m else "未知"

    tr_m = re.search(r'"toxic_review"\s*:\s*"(.*?)"(?=\s*,|\s*\})', text, re.DOTALL)
    result["toxic_review"] = tr_m.group(1) if tr_m else "鉴屎官正在修炼"

    roast_m = re.search(r'"roast"\s*:\s*"(.*?)"(?=\s*\}|\s*$)', text, re.DOTALL)
    result["roast"] = roast_m.group(1) if roast_m else "无法判断"

    result["flaw_analysis"] = []
    result["claims"] = []
    result["tactics"] = []

    return result


def _parse_json(text: str) -> dict:
    """从模型响应中提取 JSON，兼容各种格式异常"""
    text = text.strip()

    # 1. 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. 剥离 Markdown 标记后提取 { ... } 片段
    candidate = _extract_json_candidate(text)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # 3. 尝试 json_repair 修复
    try:
        from json_repair import repair_json
        repaired = repair_json(candidate)
        if repaired:
            parsed = json.loads(repaired)
            if isinstance(parsed, dict):
                return parsed
    except Exception:
        pass

    # 4. 尝试 ast.literal_eval（适用于单引号 JSON）
    try:
        parsed = ast.literal_eval(candidate)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # 5. 最后手段：正则逐字段提取
    extracted = _regex_extract_fields(text)
    if extracted.get("is_fake") is not None:
        return extracted

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
        result.setdefault("truth_index", "未知")
        result.setdefault("toxic_review", "鉴屎官罢工了")
        result.setdefault("flaw_analysis", [])
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
