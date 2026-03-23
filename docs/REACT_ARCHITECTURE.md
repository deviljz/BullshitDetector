# BullshitDetector ReAct 架构设计文档

## 1. 背景与动机

### 现有架构的问题

当前鉴屎官（analyze_staged）采用固定流水线：

```
extract_claims → verify × N（并行）→ reflect → [title_logic + hype + framing]（并行）→ final_verdict
```

这套架构本质上是 **固定流水线伪装成 Agent**，存在三个根本缺陷：

| 问题 | 表现 | 根因 |
|------|------|------|
| 智能性不足 | 边界情况靠堆 prompt 规则，越改越复杂 | 模型只能在固定格子里执行，无自主决策权 |
| 缺乏灵活性 | 简单/复杂任务都执行同样的 5 个 Stage | 控制流硬编码在 Python，模型无法跳过或增加步骤 |
| 工具强制绑定 | title_logic / hype_check 强制执行，不管是否需要 | 工具调用是 Stage 的一部分，而非 Agent 的选择 |

### ReAct 方案

**ReAct（Reasoning + Acting）**：Agent 在每轮中先推理当前状态，再决定下一步行动，循环直到主动调用 `submit_verdict` 终止。

核心转变：**控制流从 Python 移交给模型**，Python 只负责工具执行和最终 bi 计算。

---

## 2. 整体架构

### 2.1 流程图

```
用户输入（文章 / 截图）
        ↓
  [Complexity Router]        ← 快速判断：简单 or 复杂
        ↓
  ┌─────┴─────┐
  │           │
[Fast Path]  [Full ReAct Agent]
  │           │
  │    ┌──────▼──────────────────────────────┐
  │    │  System Prompt（角色 + 工具说明）    │
  │    │  User Message（文章内容）            │
  │    └──────┬──────────────────────────────┘
  │           │
  │    ┌──────▼──────┐
  │    │  推理轮次 1  │  Agent 分析文章，决定第一步
  │    └──────┬──────┘
  │           │ tool_call（可能多个并行）
  │    ┌──────▼──────────────────────────────┐
  │    │  工具执行（Python 层）               │
  │    │  web_search / check_title_logic /   │
  │    │  check_hype / submit_verdict        │
  │    └──────┬──────────────────────────────┘
  │           │ tool_result
  │    ┌──────▼──────┐
  │    │  推理轮次 2  │  根据结果决定继续调查 or 终止
  │    └──────┬──────┘
  │           │  ...（最多 MAX_ROUNDS 轮）
  │    ┌──────▼──────┐
  │    │ submit_verdict（结构化 JSON）│  ← Agent 主动终止
  │    └──────┬──────┘
  │           │
  └─────┬─────┘
        ↓
  [Python 后处理]
    - 解析 submit_verdict 参数
    - 计算 bi（确定性 Python 逻辑，不依赖模型）
    - 写 debug 日志
        ↓
  最终结果 → UI
```

### 2.2 与现有架构对比

| 维度 | 现有 staged pipeline | ReAct Agent |
|------|---------------------|-------------|
| 控制流 | Python 硬编码 | 模型自主决定 |
| Stage 数量 | 固定 5 个 | 0 到 MAX_ROUNDS 不等 |
| 工具调用 | 强制绑定到 Stage | Agent 按需调用 |
| 简单文章 | 跑完整流程（慢） | 1-2 轮即终止（快） |
| 复杂文章 | 固定轮次（可能不够） | 动态加轮（更深入） |
| bi 计算 | 模型输出 + Python 兜底 | 纯 Python（确定性） |
| 边界情况 | 靠 prompt 规则处理 | 靠模型推理处理 |

---

## 3. 工具定义

### 3.1 核心工具

#### `web_search` — 网络搜索（现有，保留）

```json
{
  "name": "web_search",
  "description": "搜索网络获取最新信息。用于验证时效性新闻、数据、事件、人物、政策等事实性声明。",
  "parameters": {
    "query": "string  // 精简的搜索关键词，不要含声明里的具体数字"
  }
}
```

#### `submit_verdict` — 提交最终结论（新增，终止信号）

Agent 调用此工具时，ReAct 循环立即终止。参数即为结构化输出。

```json
{
  "name": "submit_verdict",
  "description": "完成核查后提交最终结论。调用此工具将立即结束分析。确认已完成足够的核查工作后再调用。",
  "parameters": {
    "claim_verification": [
      {
        "claim": "string          // 原始声明文本",
        "claim_type": "fact|narrative",
        "verdict": "✓ 独立核实属实 | ✓ 官方自述 | ✗ 伪造 | ? 无法核实",
        "effective_sources": "integer  // 有效来源数量",
        "best_source_type": "independent|official|none",
        "source_genealogy": "multi_independent|same_source_syndicated|official_only|unknown",
        "note": "string           // 核查说明"
      }
    ],
    "investigation_report": {
      "title_logic_check": {
        "verdict": "无问题 | 有问题",
        "reason": "string"
      },
      "hype_check": {
        "verdict": "无夸大 | 有夸大",
        "type": "第三方估算当事实 | 绝对化表述 | 无",
        "reason": "string"
      },
      "caveats": ["string"]
    },
    "one_line_summary": "string   // 一句话总结文章核心问题",
    "toxic_review": "string       // 鉴屎官风格评语（根据 tone 配置）",
    "verdict_text": "string       // 最终判决文本"
  }
}
```

### 3.2 可选辅助工具（Agent 按需调用）

这些工具在现有架构中是强制 Stage，ReAct 中改为可选：

#### `analyze_title_logic` — 标题逻辑检查

```json
{
  "name": "analyze_title_logic",
  "description": "检查标题是否存在因果谬误（将相关性伪装成因果）或用无关数据背书核心论点。适用于标题含'因为X所以Y'类逻辑链条的文章。",
  "parameters": {
    "title": "string",
    "body_summary": "string  // 文章核心论点，200字以内"
  }
}
```

**返回**：`{"verdict": "无问题|有问题", "reason": "string"}`

#### `analyze_hype` — 夸大程度检查

```json
{
  "name": "analyze_hype",
  "description": "检查文章是否存在夸大表述：第三方估算被当作事实、绝对化极端表述等。适用于含财务数据或'最''首''唯一'等极端词汇的文章。",
  "parameters": {
    "text": "string  // 待检查的核心段落"
  }
}
```

**返回**：`{"verdict": "无夸大|有夸大", "type": "...", "reason": "string"}`

---

## 4. Agent 行为规范

### 4.1 System Prompt 核心原则

```
你是一名专业事实核查员。给定文章后，你需要：
1. 自行判断需要核查哪些声明（不是所有句子都要核查）
2. 使用 web_search 搜索证据
3. 需要时调用 analyze_title_logic / analyze_hype 辅助分析
4. 完成核查后调用 submit_verdict 提交结论

核查声明的原则：
- 只核查可通过外部证据验证的事实性声明（具体数字/人物/事件）
- 主观评价、预测、观点不需要核查
- 搜索到近似数字（±10%以内）视为属实
- eff=0 时不得判 ✗ 伪造，只能判 ? 无法核实

何时可以提前终止：
- 文章只有 1-2 条可核查声明且已全部核查完毕
- 文章明显是主观评论/观点文章，无需大量核查
- 核查结果已经非常明确（全部属实 or 存在明显伪造）
```

### 4.2 Agent 决策树（期望行为）

```
收到文章
    ↓
读取文章，识别可核查的事实性声明
    ↓
判断复杂度
  ├─ 简单（1-2 条声明，主观为主）
  │    └─ 直接 web_search × 1-2 → submit_verdict
  │
  ├─ 中等（3-5 条事实声明）
  │    └─ web_search × 3-6（可并行）→ 可选 analyze_title_logic → submit_verdict
  │
  └─ 复杂（多条声明 + 可疑数据 + 标题党特征）
       └─ web_search × N → analyze_title_logic → analyze_hype →
          可能追加搜索 → submit_verdict
```

### 4.3 并行工具调用

Agent 可以在单轮中同时调用多个 `web_search`（现有的并行执行机制保留）：

```
Round 1: [web_search("声明A"), web_search("声明B"), web_search("声明C")]
Round 2: [web_search("追加核查"), analyze_title_logic(...)]
Round 3: submit_verdict(...)
```

---

## 5. Python 后处理层

ReAct Agent 完成后，Python 做确定性后处理（不依赖模型）：

```python
def _post_process(submit_args: dict) -> dict:
    claim_results = submit_args["claim_verification"]
    investigation = submit_args["investigation_report"]

    # bi 计算（确定性，与现有 _calculate_bi 一致）
    bi, risk_level = _calculate_bi(
        claim_results,
        investigation.get("title_logic_check", {}),
        investigation.get("hype_check", {}),
    )

    # 组装最终 result
    result = {
        "_mode": "analyze",
        "header": {
            "bullshit_index": bi,
            "risk_level": risk_level,
            "verdict": submit_args.get("verdict_text", ""),
            "truth_label": _bi_to_label(bi),
        },
        "claim_verification": claim_results,
        "investigation_report": investigation,
        "one_line_summary": submit_args.get("one_line_summary", ""),
        "toxic_review": submit_args.get("toxic_review", ""),
    }
    return result
```

---

## 6. Fast Path（简单文章快速通道）

对于明显简单的文章，可跳过 ReAct 直接走单次分析：

**触发条件（满足任意一条）：**
- 文章长度 < 300 字
- 文章为纯主观评论（无具体数字、人名、事件）
- 用户明确选择"快速模式"

**Fast Path 流程：**

```
单次 LLM 调用（含 web_search 工具，force_first_tool=False）
  → 如果模型调用了搜索：执行搜索，给出结论
  → 如果模型直接给出结论：跳过搜索
  → Python 后处理计算 bi
```

Fast Path 仍然可以调用 web_search，区别是不强制，由模型判断是否需要。

---

## 7. 安全兜底机制

| 情况 | 处理方式 |
|------|----------|
| Agent 达到 MAX_ROUNDS 未调用 submit_verdict | 强制终止，用当前已收集的搜索结果构造兜底结果 |
| submit_verdict 参数格式错误 | parse_json 容错解析，缺失字段填默认值 |
| 搜索全部失败（配额耗尽） | 抛 SearchUnavailableError，向用户报错（现有机制） |
| 模型输出乱码 / 空内容 | retry prompt 提示重新输出，最多 2 次 |

---

## 8. 与现有代码的兼容性

### 8.1 保留不变

- `_calculate_bi()`：确定性 bi 计算，直接复用
- `SearchProvider` + DDG fallback：搜索层完全不变
- `execute_tool()`：工具执行层不变，只需新增 `submit_verdict` 和辅助工具的处理
- `debug_log`：日志结构不变，stage 改为 round
- `_error_result()`：错误处理不变
- `analyze_screenshot` / `analyze_text`（classic 路径）：完全不受影响

### 8.2 需要修改

| 文件 | 改动 |
|------|------|
| `ai/tools.py` | 新增 `submit_verdict` / `analyze_title_logic` / `analyze_hype` 工具定义 |
| `ai/prompts/analyze_staged.py` | 重写为 ReAct system prompt |
| `ai/providers/openai_compat.py` | 新增 `analyze_article_react()` 方法，替换 `analyze_article_staged()` |
| `ai/analyzer.py` | `analyze_text_staged` / `analyze_screenshot_staged` 调用新方法 |

### 8.3 迁移策略

分三步渐进迁移，每步可独立验证：

**Step 1**：在现有 `_tool_loop` 加入 `submit_verdict` 工具，让 Agent 能提前终止（无需 Stage5）

**Step 2**：把 `analyze_title_logic` / `analyze_hype` 加为可选工具，废掉强制 Stage3

**Step 3**：去掉强制 Stage1（extract）和 Stage2（verify），统一进入单一 ReAct Agent

---

## 9. 模型要求

| 能力 | 要求 | 原因 |
|------|------|------|
| 工具调用 | 支持并行 tool_calls | 同时搜索多条声明 |
| 推理质量 | 能规划多步核查策略 | ReAct 的核心 |
| 指令遵循 | 准确填充 submit_verdict 参数 | 结构化输出的关键 |
| 上下文长度 | ≥ 32K tokens | 多轮搜索结果累积 |

**推荐模型**：Gemini 2.5 Pro / Flash（已验证工具调用能力），DeepSeek-R1 / V3（备选）

**不推荐**：纯推理模型（o1/R1 思考模式）用于此场景，因为工具调用延迟高，且 ReAct 需要快速迭代。

---

## 10. 预期效果

| 指标 | 现有 staged | ReAct |
|------|------------|-------|
| 简单文章耗时 | ~30s（跑完整流程） | ~8-12s（1-2 轮） |
| 复杂文章准确性 | 受限于固定 Stage 数 | 更高（Agent 可追加调查） |
| 边界情况处理 | 靠 prompt 规则 | 靠模型推理 |
| 可维护性 | 每个 Stage 独立调试 | 需要看完整 trace |
| Token 消耗（简单） | 高（固定 Stage） | 低（早终止） |
| Token 消耗（复杂） | 低（固定轮次） | 高（动态加轮） |
