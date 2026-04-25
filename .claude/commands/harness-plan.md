---
description: 用 harness 为新任务写 spec（7 段 + complexity）
argument-hint: <task-name>
---

为任务 `$ARGUMENTS` 写 harness spec。

## 前置判断（关键）

**先判断当前会话是否已经讨论过此任务：**

- **已讨论** → 进入"起草模式"：用对话内容直接起草 6 段草稿，给用户过目、逐段微调。**不要**从零开始问问题。
- **未讨论 / 讨论零散** → 进入"引导模式"：逐段问封闭问题帮用户填。

判断依据：翻一下当前 context 里是否已经出现过任务目标、涉及文件、约束条件等信息。只要有 2 段以上相关内容就算"已讨论"。

## 起草模式流程

1. 运行 `harness plan new "$ARGUMENTS"` 生成骨架，记录输出路径。
2. 基于会话内容**直接起草** 7 段 + complexity 字段，一次性给用户看完整草稿：
   ```
   ## Objective
   [从讨论中提炼的目标]

   ## User Flow
   [逐步用户动线：1. 用户在 X 页点 Y → 2. 看到 Z → 3. ...]

   ## Commands
   ...（以此类推 7 段）

   complexity: simple | complex
   ```
3. 逐段问：「这段对吗？有要改的吗？」允许用户一次指出多处。
4. 用户确认一段就写入文件，不要等全部确认完才写（防中断丢内容）。
5. 全部确认后运行 `harness plan validate <path>`，不过就修。
6. 告诉用户：`/harness-execute <path>`。

## 引导模式流程（讨论不足时）

1. 运行 `harness plan new "$ARGUMENTS"`。
2. 按 7 大区逐个问**封闭问题**（"目标用户是谁？"而不是"介绍一下这个任务"）：
   - **Objective**：一句话目标 + 可验证的成功标准
   - **User Flow**：逐步用户动线（上传 → 看到什么 → 点什么 → 结果）。**UI 相关任务必填**；纯后端/工具类可写 "N/A - 无用户交互"
   - **Commands**：需要跑的命令（测试/构建/lint）
   - **Structure**：涉及的文件/模块列表
   - **Style**：编码规范（如有特殊要求）
   - **Testing**：测试策略（单元/集成/E2E）
   - **Boundaries**：非目标（绝不做什么）
3. 问 `complexity: simple | complex`：
   - 1-2 文件 / 单模块 → simple
   - 跨模块 / 改架构 / 改 DB → complex
4. 每段填完立即写入文件（增量更新）。
5. 运行 `harness plan validate <path>`，不过就修。
6. 告诉用户：`/harness-execute <path>`。

## 硬约束

- 起草模式必须把讨论过的**具体细节**（文件名、约束、边界）写进 spec，不允许笼统归纳丢信息
- Boundaries 必须列具体项，不允许空/模糊
- validate 不通过不能结束
- 用户没明确同意的段落不写入文件
