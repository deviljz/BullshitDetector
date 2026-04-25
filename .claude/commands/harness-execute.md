---
description: 按 harness spec 逐项执行实现
argument-hint: <spec-path>
---

按 spec `$ARGUMENTS` 执行实现。

## 执行步骤

1. 读 `$ARGUMENTS`，确认 complexity 字段：
   - **simple** → 直接在当前会话实现
   - **complex** → 为每个执行项起 subagent（通过 Agent 工具）
2. 运行 `harness execute "$ARGUMENTS"` 解析执行表（若存在）。
3. 按 Structure 区列出的文件逐项改动。每改完一个文件：
   - 自动有 PostToolUse hook 跑 `harness check --on-edit` 验证
   - 若 hook 报 fail → 先修再继续下一项
4. 全部实现后让用户跑 `/harness-review $ARGUMENTS` 审查。

## 硬约束

- 不允许偏离 spec 的 Boundaries（非目标）
- 每个执行项必须映射到 spec 的某一段
- complex 任务必须用 subagent 隔离，避免污染主上下文
