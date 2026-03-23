# BullshitDetector 新架构设计文档

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

---

## 2. 架构选型：Plan-and-Execute with Re-planner

### 2.1 为什么选 Plan-and-Execute 而不是纯 ReAct

**纯 ReAct**（Reasoning + Acting）：每轮都需要完整 LLM 推理再决定下一步行动，适合完全开放式的探索任务。

**Plan-and-Execute with Re-planner**：先由 Planner 生成核查计划，Executor 并行执行（不需要 LLM），Re-planner 看结果后决定继续还是完成。

对于事实核查这个场景，Plan-and-Execute 更合适，原因：

1. **Executor 不需要 LLM**：搜索工具直接执行，节省时间和 token
2. **天然并行**：Planner 一次给出所有待核查声明，Executor 全部并行跑
3. **Re-planner 支持多轮**：看到搜索结果后可以追加新的核查步骤，具备动态适应能力
4. **现有代码天然对应**：extract_claims ≈ Planner，parallel verify ≈ Executor，reflect ≈ Re-planner

### 2.2 与现有架构的对应关系

| 现有阶段 | Plan-and-Execute 角色 | 变化 |
|---------|----------------------|------|
| Stage 1 extract_claims | **Planner** | 不变 |
| Stage 2 verify（并行）| **Executor** | `_verify_claim` 变成工具 |
| Stage 2.5 reflect | **Re-planner** | 增强：能真正决定继续/完成 |
| Stage 3 parallel checks | 由 Re-planner 按需调用 | 不再强制执行 |
| Stage 4 final_verdict | Re-planner 决定完成时触发 | 简化 |

### 2.3 执行时间对比

Plan-and-Execute **不比现有架构慢**，中等复杂度下更快：

```
现有 staged（固定 5 Stage）：
  LLM1(extract) → LLM2×N(verify 并行) → LLM3(reflect) → LLM4×3(checks 并行) → LLM5(verdict)
  串行 LLM 调用：5 次（固定，无论文章简单复杂）

Plan-and-Execute：
  LLM1(Planner) → 工具×N(verify 并行，0 次 LLM) → LLM2(Re-planner) → [可选追加] → LLM3(verdict)
  串行 LLM 调用：3 次起（简单文章），复杂文章按需增加
```

---

## 3. 两层工具体系

### 3.1 核心设计：`verify_claim` 作为工具

最关键的架构决策：将 `verify_claim` 封装为一个工具，形成两层结构：

```
外层 Agent（Planner / Re-planner）
  关注：要核查哪些声明、是否需要检查标题逻辑、何时完成
  工具：
    ├─ verify_claim(claim, context)   ← 核查单条声明（内部自己搜索）
    ├─ analyze_title_logic(...)       ← 按需调用，不强制
    ├─ analyze_hype(...)              ← 按需调用，不强制
    └─ submit_verdict(...)            ← 终止信号

内层（verify_claim 工具实现）
  关注：如何核查这一条声明（搜索策略、证据评估）
  内部运行：web_search loop → 结构化结果
```

外层 Agent 只管"核查哪些"，完全不关心"怎么核查"。`_verify_claim()` 方法已经存在，只需将其注册为工具定义暴露给外层 Agent。

### 3.2 工具定义

#### `verify_claim` — 核查单条声明（核心工具）

```json
{
  "name": "verify_claim",
  "description": "核查文章中的一条具体事实性声明。工具内部会自动搜索相关证据并返回核查结论。适用于含具体数字、人名、事件的声明；主观观点和无法核查的预测不需要核查。",
  "parameters": {
    "claim": "string   // 待核查的声明原文",
    "claim_type": "fact | narrative  // fact：有具体数字/事件可搜索；narrative：因果/评价类",
    "context": "string // 声明所在的文章标题和核心背景（100字以内）"
  }
}
```

**返回**（结构化 JSON）：
```json
{
  "verdict": "✓ 独立核实属实 | ✓ 官方自述 | ✗ 伪造 | ? 无法核实",
  "effective_sources": 3,
  "best_source_type": "independent | official | none",
  "source_genealogy": "multi_independent | same_source_syndicated | official_only | unknown",
  "note": "核查说明"
}
```

#### `analyze_title_logic` — 标题逻辑检查（可选）

```json
{
  "name": "analyze_title_logic",
  "description": "检查标题是否存在因果谬误或用无关数据背书核心论点。适用于标题含'因为X所以Y'、'凭借X实现Y'类逻辑链条的文章。简单陈述类标题无需调用。",
  "parameters": {
    "title": "string",
    "body_summary": "string  // 文章核心论点，200字以内"
  }
}
```

**返回**：`{"verdict": "无问题 | 有问题", "reason": "string"}`

#### `analyze_hype` — 夸大程度检查（可选）

```json
{
  "name": "analyze_hype",
  "description": "检查文章是否存在夸大表述：第三方估算被当作事实陈述、含'最''首''唯一'等绝对化表述。含大量财务数据或极端形容词时调用。",
  "parameters": {
    "text": "string  // 含疑似夸大表述的核心段落"
  }
}
```

**返回**：`{"verdict": "无夸大 | 有夸大", "type": "第三方估算当事实 | 绝对化表述", "reason": "string"}`

#### `submit_verdict` — 提交结论（终止信号）

```json
{
  "name": "submit_verdict",
  "description": "完成所有必要核查后提交最终结论。调用此工具将立即结束分析流程。",
  "parameters": {
    "claim_verification": ["// verify_claim 的返回结果数组"],
    "investigation_report": {
      "title_logic_check": {"verdict": "...", "reason": "..."},
      "hype_check": {"verdict": "...", "type": "...", "reason": "..."},
      "caveats": ["string"]
    },
    "one_line_summary": "string",
    "toxic_review": "string",
    "verdict_text": "string"
  }
}
```

---

## 4. 完整执行流程

### 4.1 流程图

```
用户输入（文章 / 截图）
        ↓
  ┌─────────────────────────────┐
  │  Planner LLM                │
  │  - 读取文章                  │
  │  - 识别可核查的事实性声明      │
  │  - 输出核查计划（claim 列表）  │
  └──────────────┬──────────────┘
                 │ 生成计划：[claim1, claim2, ...]
                 ↓
  ┌─────────────────────────────┐
  │  Executor（纯工具，无 LLM）  │
  │  并行调用：                  │
  │  verify_claim(claim1)       │
  │  verify_claim(claim2)  ───→ │  每个 verify_claim 内部
  │  verify_claim(claim3)       │  独立运行搜索 loop
  └──────────────┬──────────────┘
                 │ 返回所有核查结果
                 ↓
  ┌─────────────────────────────────────────┐
  │  Re-planner LLM                         │
  │  - 审阅所有核查结果                       │
  │  - 决策：                               │
  │    ├─ 完成 → 可选调用 analyze_title_logic │
  │    │         可选调用 analyze_hype        │
  │    │         调用 submit_verdict（终止）  │
  │    └─ 继续 → 追加新的 verify_claim 调用   │
  └──────────────┬──────────────────────────┘
                 │（如需追加）
                 ↓
           [再次 Executor]
                 ↓
           [Re-planner 再次决策]
                 ↓ submit_verdict
  ┌─────────────────────────────┐
  │  Python 后处理              │
  │  - 解析 submit_verdict 参数  │
  │  - _calculate_bi()（确定性） │
  │  - 写 debug 日志            │
  └─────────────────────────────┘
        ↓
     最终结果 → UI
```

### 4.2 典型场景行为

**简单文章**（主观评论为主，1-2 条事实）：
```
Planner → [verify_claim × 1-2（并行）] → Re-planner → submit_verdict
串行 LLM：3 次，总时长 ~10-15s
```

**中等文章**（3-5 条事实声明，有标题党特征）：
```
Planner → [verify_claim × 3-5（并行）] → Re-planner
→ analyze_title_logic → submit_verdict
串行 LLM：3-4 次，总时长 ~15-25s
```

**复杂文章**（多声明、有疑点、需追加核查）：
```
Planner → [verify_claim × 5（并行）] → Re-planner
→ [verify_claim × 2（追加并行）] → Re-planner
→ analyze_title_logic → analyze_hype → submit_verdict
串行 LLM：5-6 次，总时长 ~30-45s
```

---

## 5. Python 后处理层（不变）

bi 计算保持确定性，不依赖模型：

```python
def _post_process(submit_args: dict) -> dict:
    claim_results = submit_args["claim_verification"]
    investigation = submit_args["investigation_report"]

    # 直接复用现有 _calculate_bi()
    bi, risk_level = _calculate_bi(
        claim_results,
        investigation.get("title_logic_check", {}),
        investigation.get("hype_check", {}),
    )
    return {
        "_mode": "analyze",
        "header": {"bullshit_index": bi, "risk_level": risk_level, ...},
        "claim_verification": claim_results,
        "investigation_report": investigation,
        ...
    }
```

---

## 6. 安全兜底

| 情况 | 处理 |
|------|------|
| Re-planner 循环超过 MAX_ROUNDS | 强制终止，用已有核查结果构造兜底输出 |
| verify_claim 内部搜索全部失败 | 返回 `{verdict: "? 无法核实", effective_sources: 0}`，不抛异常 |
| 搜索服务系统性故障（全部 provider 挂掉）| 抛 SearchUnavailableError，向用户报错（现有机制） |
| submit_verdict 参数格式错误 | parse_json 容错解析，缺失字段填默认值 |

---

## 7. 与现有代码的兼容性

### 7.1 保留不变

- `_verify_claim()`：直接作为 `verify_claim` 工具的实现体
- `_calculate_bi()`：确定性 bi 计算，直接复用
- `SearchProvider` + DDG fallback：搜索层完全不变
- `execute_tool()`：只需新增 `verify_claim` / `analyze_title_logic` / `analyze_hype` / `submit_verdict` 的 dispatch
- `debug_log`：日志结构不变
- `analyze_screenshot` / `analyze_text`（classic 路径）：完全不受影响

### 7.2 需要修改

| 文件 | 改动 |
|------|------|
| `ai/tools.py` | 新增 4 个工具定义；`execute_tool` 新增 dispatch 分支 |
| `ai/prompts/analyze_staged.py` | 重写为 Planner prompt 和 Re-planner prompt |
| `ai/providers/openai_compat.py` | 新增 `analyze_article_plan_execute()` 方法 |
| `ai/analyzer.py` | staged 入口调用新方法 |

### 7.3 三步渐进迁移

**Step 1**：将 `verify_claim` 注册为工具，让外层 Agent 通过工具调用而非 Python 强制调度来触发核查

**Step 2**：将 `analyze_title_logic` / `analyze_hype` 改为可选工具，Re-planner 按需调用；废掉强制 Stage 3

**Step 3**：引入完整的 Planner → Executor → Re-planner 循环，废掉现有 staged pipeline

---

## 8. 模型要求

| 能力 | 要求 | 备注 |
|------|------|------|
| 并行工具调用 | 支持单轮多个 tool_call | Executor 并行执行关键 |
| 结构化输出 | 准确填充 submit_verdict 参数 | 可用 JSON schema 约束 |
| 上下文长度 | ≥ 32K tokens | 多轮结果累积 |
| 推理质量 | 能识别哪些声明值得核查 | Planner 核心能力 |

**推荐**：Gemini 2.5 Flash / Pro（已验证工具调用）；DeepSeek V3（备选）

---

## 9. 预期效果

| 指标 | 现有 staged | 新 Plan-and-Execute |
|------|------------|-------------------|
| 简单文章耗时 | ~30s（固定 5 Stage） | ~10-15s（3 次 LLM） |
| 复杂文章准确性 | 受固定 Stage 限制 | Re-planner 可追加核查 |
| 边界情况处理 | 靠 prompt 规则堆砌 | 靠模型推理自适应 |
| 工具使用 | 强制绑定 Stage | Agent 按需选择 |
| bi 计算 | 确定性（Python） | 确定性（Python，不变） |
| 代码复用率 | — | 高（_verify_claim 直接复用）|
