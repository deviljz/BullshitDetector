---
description: 一条龙跑完 harness：execute → check → review → commit，全程无人工介入
argument-hint: <spec-path>
---

按 spec `$ARGUMENTS` **自动跑完整链**，全程不询问用户，失败时停下来汇报。

## 执行步骤

### 第 1 步：execute
按 `.claude/commands/harness-execute.md` 的规则跑：
- 读 spec，确认 complexity
- complex → 每个执行项起独立 subagent（Agent 工具，subagent_type=general-purpose）
- 按 Structure 区列出的文件逐项改
- PostToolUse hook 自动跑 `harness check --on-edit` 增量验证
- 单个 hook fail → **当场自修**，不打断流程

### 第 2 步：check（全量）
所有改动完成后，运行 `harness check`，解析 XML 报告：
- `all_green="true"` → 进入第 3 步
- 有 fail → 读 raw_output 定位根因 → **自修一次** → 重跑
- 连续 2 次失败 → 停下来汇报具体哪个 test 红、根因是什么，**不要继续 review/commit**

### 第 3 步：review
按 `.claude/commands/harness-review.md` 的规则跑：
- `harness review-data --spec "$ARGUMENTS"` 拿 JSON
- 起新的 subagent 跑 Pass A（功能实现）
- 若 spec 有 User Flow 段且非 N/A → 起第二个新 subagent 跑 Pass B（用户流程可达性）
- 合并 issues，整体 `consistent: false` 时 → **停下来列出所有 issues**，不进入 commit

### 第 4 步：commit
全部绿后：
- `git status` 看改动
- 当前必须在 dev 分支（按 [[feedback_git_workflow]] 规则）
- 写 commit message：`feat: 完成 spec <spec-名>` + spec 里 Objective 段一句话摘要
- `git add` 仅 spec 列出的 Structure 文件 + 测试文件 + spec 本身（不要 add 未追踪的临时文件）
- commit 到 dev（不 push，让用户决定是否 push）

### 第 5 步：汇报
最后打印：
- ✅ spec 名 + 4 步全绿
- 改动文件清单
- 提示：「dev 分支已 commit，未 push。需要的话跑 `git push origin dev`」

## 失败汇报格式

任一步骤失败立刻停下来，输出：

```
❌ harness-full 在第 X 步失败：<execute / check / review / commit>

失败详情：
<具体的 fail test / issue / git 错误>

已完成：
- 第 1 步：✅/❌
- 第 2 步：✅/❌
- 第 3 步：✅/❌

建议下一步：
<人工修复点的具体提示>
```

## 硬约束

- **全程不问用户**：不弹 AskUserQuestion、不调 EnterPlanMode
- check / review 失败时**不要继续往后跑**
- commit 前必须验证 dev 分支
- subagent 必须独立起新会话（不复用 SendMessage）
- 每步 fail 自修上限 1 次，超过就停

## 何时该用

- spec 已经写好且 deviljz 确认过（plan 阶段已通过）
- 一次性想跑完一个或多个需求 section
- 信任 AI 在 fail 时停下来汇报，而不是糊弄过去
