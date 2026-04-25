---
description: 独立 subagent 双 pass 审查 diff：功能实现 + 用户流程可达性
argument-hint: <spec-path>
---

审查当前 diff 是否符合 spec `$ARGUMENTS`。

## 执行步骤

1. 运行 `harness review-data --spec "$ARGUMENTS"`，stdout 是 JSON，含 `spec_content` / `diff_content` / `template`。
2. **Pass A — 功能实现**（用 `template` 默认模板）：
   - 把 spec + diff 塞进 template 得到 prompt A。
   - 用 Agent 工具起**全新** `general-purpose` subagent（禁止 SendMessage 续跑旧 agent，防止上下文污染）。
   - prompt 只包含 spec + diff + 模板文字，**禁止**附加本会话讨论过的结论 / 倾向 / 你自己的判断。
   - 返回 JSON `{"consistent": bool, "issues": [...]}`。
3. **Pass B — 用户流程可达性**（仅当 spec 有 User Flow 段且非 "N/A" 时跑）：
   - 组装 prompt B（见下方模板），同样塞完整 spec + diff。
   - **另起一个全新** subagent（不复用 Pass A 的 agent id）。
   - 返回 JSON `{"consistent": bool, "issues": [...]}`。
4. 合并两 pass 的 `issues`。只要任一 pass `consistent: false` → 整体判 false。
5. 输出：
   - 整体 `true` → 报"审查通过"
   - 整体 `false` → 按"文件:行号 - 问题"格式列出所有 issues，标注来自 A / B
6. 追加到 `reports/review_<ts>.md`，记录两 pass 的 raw 返回。

## Pass B prompt 模板

```
你是独立审查员。下方是 spec 和代码 diff。

## Spec
{spec_content}

## Diff
```diff
{diff_content}
```

## 任务
针对 spec 里「User Flow」段的**每一步**，trace 实际代码路径到可运行的触发条件：

1. **找到该步涉及的关键 symbol**（函数名、widget 名、button 名、路由）
2. **用 Grep 工具在整个工程里搜该 symbol 的调用方**（diff 只显示改动，门槛/触发条件可能在未改动的老代码里 —— 必须 Read 相关文件完整上下文，不能只看 diff 片段）
3. **逐层 trace**：这个 symbol 被谁调用？调用处有什么 if/guard？guard 是否与 spec 的时机要求（"立即"、"上传后"、"任何时候"）冲突？
4. 若 spec 说"上传后立即看到 X"但代码在 `if (已答完 Y)` 里才渲染入口 → 这就是偏差，报 `文件:行号 - 门槛 A，spec 要求 B`

**硬禁**：
- 禁止只看 diff 片段判通过。diff 是"改了什么"，不是"全部实现"。必须读全文件找 trigger。
- 禁止看到函数定义就默认"在合适时机调用"。必须找到调用点并验证其 guard。
- 若 diff 新增了 widget W 但没改 W 的渲染条件，必须去源文件看 W 的渲染条件。

你可以用 Grep / Read / Glob 工具在 F:/Project/MiaoStudy 工程里读任意文件。

最终只回 JSON：`{"consistent": true|false, "issues": ["flow步骤N - 实际入口是 file:line，guard 是 XXX，spec 要求 YYY，不一致"]}`
```

## 硬约束

- 禁止自己判断而不调 subagent
- Pass A / Pass B 必须是**两个独立** subagent（每次新起 Agent，禁用 SendMessage）
- prompt 内**禁止**带当前会话讨论过的倾向性结论
- subagent 必须拿完整 spec + diff，不允许 summarize
- `consistent: false` 必须至少一条具体 issue
- 如 spec 无 User Flow 段或明确 "N/A"，Pass B 跳过并在报告里注明
