---
name: analyze-logs
description: 分析近期鉴定日志，识别 plan_execute 路径的系统性问题并生成 markdown 报告
---

# /analyze-logs

分析项目近期的鉴定日志，找出系统性问题，写报告到 `reports/`。

## 触发参数

- `--last N`：分析最近 N 天（默认 7）
- `--since DATE`：从 ISO 日期起（如 `--since 2026-05-01`）

## 执行步骤

1. **跑数据准备脚本**（输出会很长，用重定向到文件方便 Read）：

   ```bash
   python scripts/prepare_log_data.py --last 7 > reports/_log_data.md
   ```

   或 `--since` 形式。命令运行需要 < 5 秒。

2. **用 Read 工具读 `reports/_log_data.md`**——里面已经按 case 聚合好关键字段（tokens、stages、search queries、claims、verdict、outliers）。

3. **分析**（核心环节，主 Claude 干这个）：

   - **找系统性问题，不是单 case 偶发**：
     - 多个 case 同时出现的模式（如 50% case 都 cross_round_repeats > 0、verdict_text_empty 高频）
     - 趋势性变化（如最近几个 case 的 token 比早期高很多）
     - 看起来"不该这样"的现象（如所有 case claim 数都是 5——可能是 prompt 引导太强）

   - **不要只看预设 outlier 标记**：脚本只标了 input_tokens > 200K、elapsed > 120s、all_unverified、cross_round_repeats、verdict_text_empty 这几条。**用你的推理找未标的模式**：
     - search queries 是否在不同 case 间出现"模板化"（说明 prompt 让模型只会这几种问法）
     - top stages 的耗时分布是否畸形（某一类 claim 总是最贵）
     - claims 的 note 里有没有反复出现的失败原因（如多 case 都说"网络连接失败"）
     - bullshit_index 与 claim verdicts 是否经常自相矛盾

   - **每个结论必须引用具体 case_id 作为证据**：不能"我觉得 token 高"，要"case `20260511-XXXX` 单 claim 跑到 88K、case `20260511-YYYY` 也是 75K"。

4. **写报告**：用 Write 工具写到 `reports/log_analysis_<YYYYMMDD-HHMM>.md`，结构如下：

   ```markdown
   # 鉴定日志分析报告

   ## 元数据
   - 时间窗、case 数、生成时间、git_commit（从输入复用）

   ## 基本统计
   （从 _log_data.md 的全局聚合段提炼，加你的解读）

   ## Top N 问题诊断
   ### 问题 1: <标题>
   - 现象：（具体描述）
   - 证据：（case_id 列表 + 关键数字）
   - 影响：（对 verdict 质量 / token 成本的影响）

   ### 问题 2: ...

   ## 建议修法
   - 针对问题 1：<可执行修法>（具体到改哪个文件/函数/prompt 段）
   - 针对问题 2：...

   ## 工具自身改进建议
   （反思本次分析过程中工具的不足）
   - 脚本 `scripts/prepare_log_data.py` 还缺哪些字段？
   - 本 SKILL.md 哪些指令不够清晰让你走了弯路？
   - 报告结构有什么可优化的？
   - 至少一条；即使无明显缺陷也要写"当前数据足够，无明显工具缺陷"。

   ## 附录
   - outlier case 列表（带 logs/ 相对路径链接）
   ```

5. **报告写完后**，删除中间文件 `reports/_log_data.md`，然后**主动告知用户**：

   > "分析完成，报告：`reports/log_analysis_<日期>.md`。工具改进建议见报告末尾——要我现在实施吗？"

   **等待用户明确指示再改脚本或本 SKILL.md**。未经同意不能默默改。

## 硬约束

- **零外部 LLM API 调用**：所有分析由当前 Claude 会话完成
- **不主动改源码**：除非用户明确要求实施工具改进建议
- **不主动重跑历史 case**：成本不可控
- **报告写到 `reports/`**，不进 git（已在 `.gitignore`）
- **每个结论必须有 case_id 证据**——禁止"可能"、"似乎"、"通常"这种无证据描述

## 找未知模式的提示

不要只看脚本预聚合的 outlier。问自己：
- "如果我每周都跑这个分析，**下次我希望能看到什么但这次没看到**？"——那就是工具改进点。
- "这批 case 里**最让我觉得奇怪**的现象是什么？"——可能是未知模式。
- "如果模型行为最近**变了**，哪些字段会暴露这个变化？"——time-series 维度。

## Dev replay 处理

脚本会自动识别 dev replay（24h 内同 title 出现 ≥3 次、或 空 title + 无 history），标记 `is_dev_replay=True`，并输出到独立 section `## Dev Replay case 详情`（默认不过滤，便于观察调优过程）。

**报告中分开处理**：
- "Top N 问题诊断" 主要基于**真实 case**——dev replay 是开发期人工跑的，不代表线上分布
- "调优演变观察"（如有）放进单独段落，引用 `## Dev Replay 时序演变` 里同 title case 的 token 序列
- 不要把 dev replay 的 outlier 与真实 case 的混在一起报告

**命令选项**：
- 默认：保留 dev replay 并标记
- `--exclude-dev`：完全过滤 dev replay（适合纯线上趋势分析）
- `--token-outlier=N` / `--elapsed-outlier=N`：自定义 outlier 阈值（默认 200K / 120s）
