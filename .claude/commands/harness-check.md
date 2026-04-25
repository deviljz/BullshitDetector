---
description: 跑 harness check 验证 + gate 判定
argument-hint: [--gate|--on-edit <path>|--warn-only]
---

跑 harness 验证。

## 参数处理

- 无参数 → `harness check`（全量）
- `--gate` → `harness check --gate`（验证最近报告是否放行）
- `--on-edit <path>` → `harness check --on-edit <path>`（增量）
- `--warn-only` → 加 `--warn-only` 标志

原始参数：`$ARGUMENTS`

## 执行步骤

1. 按参数构造命令并运行。
2. 解析 XML 报告：`all_green="true"` 即绿。
3. 有 fail → 读 `raw_output` 字段定位根因 → 自动修复 → 重跑。
4. 连续失败 2 次 → 停下来让用户决策（触发熔断）。

## 输出格式

- 绿：一行摘要 `✅ <target>: N passed`
- 红：列出失败 test + 根因 + 修复建议
- skip：说明原因（如工具缺失）
